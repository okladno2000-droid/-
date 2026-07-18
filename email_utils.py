"""
Отправка писем с кодом подтверждения.

Настрой переменные окружения под свой почтовый сервис:
- Для SendGrid/Mailgun/Unisender обычно дают отдельный SMTP-логин и пароль
- SMTP_HOST, SMTP_PORT, SMTP_USER, SMTP_PASSWORD, SMTP_FROM

Пока эти переменные не заданы, письма просто печатаются в консоль —
удобно для локальной разработки без реальной отправки.
"""
import os
import smtplib
from email.mime.text import MIMEText

SMTP_HOST = os.getenv("SMTP_HOST")
SMTP_PORT = int(os.getenv("SMTP_PORT", "587"))
SMTP_USER = os.getenv("SMTP_USER")
SMTP_PASSWORD = os.getenv("SMTP_PASSWORD")
SMTP_FROM = os.getenv("SMTP_FROM", "no-reply@siyanie.app")


def send_verification_email(to_email: str, code: str) -> None:
    subject = "Код подтверждения — Сияние"
    body = f"Твой код подтверждения: {code}\n\nОн действует 15 минут."

    if not SMTP_HOST:
        # Режим разработки без настроенной почты — просто выводим в консоль
        print(f"[DEV EMAIL] Кому: {to_email} | Код: {code}")
        return

    msg = MIMEText(body)
    msg["Subject"] = subject
    msg["From"] = SMTP_FROM
    msg["To"] = to_email

    with smtplib.SMTP(SMTP_HOST, SMTP_PORT) as server:
        server.starttls()
        server.login(SMTP_USER, SMTP_PASSWORD)
        server.sendmail(SMTP_FROM, [to_email], msg.as_string())
