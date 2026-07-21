from pydantic import BaseModel, EmailStr


class RegisterRequest(BaseModel):
    email: EmailStr
    password: str


class VerifyRequest(BaseModel):
    email: EmailStr
    code: str


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


class MessageResponse(BaseModel):
    message: str


class StartChatRequest(BaseModel):
    email: EmailStr


class ChatOut(BaseModel):
    chat_id: int
    with_email: str
    last_message: str | None = None
    last_message_at: str | None = None


class SendMessageRequest(BaseModel):
    text: str


class MessageOut(BaseModel):
    id: int
    sender_email: str
    text: str
    created_at: str
    is_mine: bool
