from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, EmailStr
from sqlalchemy import Column, Integer, String, Boolean
from sqlalchemy.orm import declarative_base, sessionmaker
from sqlalchemy.exc import IntegrityError
from werkzeug.security import generate_password_hash
from sqlalchemy import create_engine
import os

# 🔹 подключение к PostgreSQL
DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://postgres:password@localhost:5432/aeo")

engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)
Base = declarative_base()

router = APIRouter(prefix="/auth", tags=["Auth"])

# 🧩 Модель пользователя
class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    email = Column(String(120), unique=True, nullable=False)
    password = Column(String(255), nullable=False)
    project_name = Column(String(255), nullable=False)
    subscribe = Column(Boolean, default=False)


Base.metadata.create_all(bind=engine)


# 📦 Схема запроса
class RegisterRequest(BaseModel):
    email: EmailStr
    password: str
    projectName: str
    subscribe: bool = False


# 📦 Схема ответа
class RegisterResponse(BaseModel):
    message: str


# 🔐 Эндпоинт регистрации
@router.post("/register", response_model=RegisterResponse)
def register_user(req: RegisterRequest):
    session = SessionLocal()
    try:
        if session.query(User).filter_by(email=req.email).first():
            raise HTTPException(status_code=400, detail="User already exists")

        hashed_password = generate_password_hash(req.password)

        new_user = User(
            email=req.email,
            password=hashed_password,
            project_name=req.projectName,
            subscribe=req.subscribe
        )
        session.add(new_user)
        session.commit()
        return {"message": "User registered successfully"}

    except IntegrityError:
        session.rollback()
        raise HTTPException(status_code=400, detail="User already exists")
    except Exception as e:
        session.rollback()
        raise HTTPException(status_code=500, detail=f"Internal error: {e}")
    finally:
        session.close()
