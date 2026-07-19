"""
Сияние — backend API (регистрация по email, подтверждение кодом, вход).

Запуск локально:
    uvicorn main:app --reload

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


@app.get("/")
def health_check():
    return {"status": "ok", "service": "Сияние API"}
