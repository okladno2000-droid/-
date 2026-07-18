"""
Подключение к PostgreSQL через SQLAlchemy.

DATABASE_URL берётся из переменной окружения, например:
postgresql://user:password@host:5432/dbname
(Railway/Render/Supabase дают такую строку прямо в панели проекта)
"""
import os
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./siyanie_dev.db")

# connect_args нужен только для локальной разработки на SQLite
connect_args = {"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {}

engine = create_engine(DATABASE_URL, connect_args=connect_args)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
