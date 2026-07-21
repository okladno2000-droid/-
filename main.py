"""
Сияние — backend API (регистрация по email, подтверждение кодом, вход).

Запуск локально:
    uvicorn app.main:app --reload

Эндпоинты:
    POST /register  -> {email, password}       создаёт пользователя, шлёт код на почту
    POST /verify     -> {email, code}           подтверждает почту
    POST /login       -> {email, password}       возвращает access_token
    GET  /me          -> (нужен Authorization: Bearer <token>) текущий пользователь
"""
from datetime import datetime

from fastapi import FastAPI, Depends, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.orm import Session

import models, schemas, auth, email_utils
from database import engine, get_db, Base

# Создаёт таблицы при первом запуске (для продакшена лучше Alembic-миграции,
# но для старта и теста этого достаточно)
Base.metadata.create_all(bind=engine)

app = FastAPI(title="Сияние API")

# На старте разрешаем все источники, чтобы сайт с любого адреса мог
# обращаться к API во время разработки. Перед реальным запуском
# замени allow_origins на точный адрес твоего сайта.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

bearer_scheme = HTTPBearer()


def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(bearer_scheme),
    db: Session = Depends(get_db),
) -> models.User:
    email = auth.decode_access_token(credentials.credentials)
    if not email:
        raise HTTPException(status_code=401, detail="Недействительный токен")
    user = db.query(models.User).filter(models.User.email == email).first()
    if not user:
        raise HTTPException(status_code=401, detail="Пользователь не найден")
    return user


@app.post("/register", response_model=schemas.MessageResponse)
def register(payload: schemas.RegisterRequest, db: Session = Depends(get_db)):
    existing = db.query(models.User).filter(models.User.email == payload.email).first()
    if existing and existing.is_verified:
        raise HTTPException(status_code=400, detail="Этот email уже зарегистрирован")

    code = auth.generate_verification_code()
    expires = auth.code_expiry()

    if existing:
        # Пользователь начал регистрацию раньше, но не подтвердил её — обновляем
        existing.password_hash = auth.hash_password(payload.password)
        existing.verification_code = code
        existing.code_expires_at = expires
    else:
        existing = models.User(
            email=payload.email,
            password_hash=auth.hash_password(payload.password),
            is_verified=False,
            verification_code=code,
            code_expires_at=expires,
        )
        db.add(existing)

    db.commit()
    email_utils.send_verification_email(payload.email, code)
    return {"message": "Код подтверждения отправлен на почту"}


@app.post("/verify", response_model=schemas.TokenResponse)
def verify(payload: schemas.VerifyRequest, db: Session = Depends(get_db)):
    user = db.query(models.User).filter(models.User.email == payload.email).first()
    if not user:
        raise HTTPException(status_code=404, detail="Пользователь не найден")
    if user.is_verified:
        raise HTTPException(status_code=400, detail="Почта уже подтверждена")
    if user.verification_code != payload.code:
        raise HTTPException(status_code=400, detail="Неверный код")
    if user.code_expires_at and user.code_expires_at < datetime.utcnow():
        raise HTTPException(status_code=400, detail="Код истёк, запроси новый через /register")

    user.is_verified = True
    user.verification_code = None
    user.code_expires_at = None
    db.commit()

    token = auth.create_access_token(subject=user.email)
    return {"access_token": token}


@app.post("/login", response_model=schemas.TokenResponse)
def login(payload: schemas.LoginRequest, db: Session = Depends(get_db)):
    user = db.query(models.User).filter(models.User.email == payload.email).first()
    if not user or not auth.verify_password(payload.password, user.password_hash):
        raise HTTPException(status_code=401, detail="Неверный email или пароль")
    if not user.is_verified:
        raise HTTPException(status_code=403, detail="Сначала подтверди почту")

    token = auth.create_access_token(subject=user.email)
    return {"access_token": token}


@app.get("/me")
def me(current_user: models.User = Depends(get_current_user)):
    return {"email": current_user.email, "is_verified": current_user.is_verified}


def _get_or_create_chat(db: Session, user_a: models.User, user_b: models.User) -> models.Chat:
    my_chat_ids = {
        m.chat_id for m in db.query(models.ChatMember).filter(models.ChatMember.user_id == user_a.id)
    }
    their_chat_ids = {
        m.chat_id for m in db.query(models.ChatMember).filter(models.ChatMember.user_id == user_b.id)
    }
    shared = my_chat_ids & their_chat_ids
    if shared:
        return db.query(models.Chat).filter(models.Chat.id == list(shared)[0]).first()

    chat = models.Chat()
    db.add(chat)
    db.commit()
    db.refresh(chat)
    db.add(models.ChatMember(chat_id=chat.id, user_id=user_a.id))
    db.add(models.ChatMember(chat_id=chat.id, user_id=user_b.id))
    db.commit()
    return chat


@app.post("/chats/start", response_model=schemas.ChatOut)
def start_chat(
    payload: schemas.StartChatRequest,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if payload.email == current_user.email:
        raise HTTPException(status_code=400, detail="Нельзя начать чат с самим собой")
    other = db.query(models.User).filter(models.User.email == payload.email).first()
    if not other:
        raise HTTPException(status_code=404, detail="Пользователь с такой почтой не найден")

    chat = _get_or_create_chat(db, current_user, other)
    return {"chat_id": chat.id, "with_email": other.email}


@app.get("/chats", response_model=list[schemas.ChatOut])
def list_chats(
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    my_memberships = db.query(models.ChatMember).filter(models.ChatMember.user_id == current_user.id).all()
    result = []
    for m in my_memberships:
        other_membership = (
            db.query(models.ChatMember)
            .filter(models.ChatMember.chat_id == m.chat_id, models.ChatMember.user_id != current_user.id)
            .first()
        )
        if not other_membership:
            continue
        other_user = db.query(models.User).filter(models.User.id == other_membership.user_id).first()
        last_msg = (
            db.query(models.Message)
            .filter(models.Message.chat_id == m.chat_id)
            .order_by(models.Message.created_at.desc())
            .first()
        )
        result.append({
            "chat_id": m.chat_id,
            "with_email": other_user.email if other_user else "неизвестно",
            "last_message": last_msg.text if last_msg else None,
            "last_message_at": last_msg.created_at.isoformat() if last_msg else None,
        })
    result.sort(key=lambda c: c["last_message_at"] or "", reverse=True)
    return result


def _assert_chat_member(db: Session, chat_id: int, user_id: int):
    member = (
        db.query(models.ChatMember)
        .filter(models.ChatMember.chat_id == chat_id, models.ChatMember.user_id == user_id)
        .first()
    )
    if not member:
        raise HTTPException(status_code=403, detail="У тебя нет доступа к этому чату")


@app.get("/chats/{chat_id}/messages", response_model=list[schemas.MessageOut])
def get_messages(
    chat_id: int,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _assert_chat_member(db, chat_id, current_user.id)
    msgs = (
        db.query(models.Message)
        .filter(models.Message.chat_id == chat_id)
        .order_by(models.Message.created_at.asc())
        .all()
    )
    result = []
    for m in msgs:
        sender = db.query(models.User).filter(models.User.id == m.sender_id).first()
        result.append({
            "id": m.id,
            "sender_email": sender.email if sender else "неизвестно",
            "text": m.text,
            "created_at": m.created_at.isoformat(),
            "is_mine": m.sender_id == current_user.id,
        })
    return result


@app.post("/chats/{chat_id}/messages", response_model=schemas.MessageOut)
def send_message(
    chat_id: int,
    payload: schemas.SendMessageRequest,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _assert_chat_member(db, chat_id, current_user.id)
    if not payload.text.strip():
        raise HTTPException(status_code=400, detail="Сообщение не может быть пустым")

    msg = models.Message(chat_id=chat_id, sender_id=current_user.id, text=payload.text.strip())
    db.add(msg)
    db.commit()
    db.refresh(msg)
    return {
        "id": msg.id,
        "sender_email": current_user.email,
        "text": msg.text,
        "created_at": msg.created_at.isoformat(),
        "is_mine": True,
    }


@app.get("/")
def health_check():
    return {"status": "ok", "service": "Сияние API"}
