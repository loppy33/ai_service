from fastapi import FastAPI, HTTPException

from app.api.schemas import QueryRequest, QueryResponse, ErrorResponse, BatchQueryRequest, BatchQueryResponse
from app.core.db import Base, engine
# 👇 Обязательно импортируем модели, чтобы они зарегистрировались в Base.metadata
from app.models import user as _user      # noqa: F401
from app.models import email_queue as _q  # noqa: F401
from app.core.resolver import resolve_query
from pathlib import Path
from fastapi.staticfiles import StaticFiles
from app.api.routes import auth  # ⬅️ добавляем импорт
from app.api.routes import analyze   # NEW
from app.api.routes import leads     # NEW
from app.api.routes import billing   # NEW
from fastapi.middleware.cors import CORSMiddleware
import asyncio
from app.core.worker import worker_loop
from contextlib import asynccontextmanager

@asynccontextmanager
async def lifespan(app: FastAPI):
    # 1) Сначала создаём таблицы
    Base.metadata.create_all(bind=engine)

    # 2) Потом запускаем воркер
    # Запуск фонового воркера при старте приложения
    worker_task = asyncio.create_task(worker_loop())
    print("🚀 Worker started")

    yield  # <-- пока приложение работает

    # Завершение при остановке FastAPI
    worker_task.cancel()
    try:
        await worker_task
    except asyncio.CancelledError:
        print("🛑 Worker stopped")

app = FastAPI(title="LLM SERP Parser API", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"], # твой фронт
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
STATIC_ROOT = Path("app/data").resolve()
app.mount("/static", StaticFiles(directory=STATIC_ROOT), name="static")

# 🔗 Подключаем маршруты регистрации
app.include_router(auth.router)      # уже есть
app.include_router(analyze.router)   # NEW
app.include_router(leads.router)     # NEW
app.include_router(billing.router)   # NEW

@app.post("/v1/check", response_model=BatchQueryResponse, responses={400: {"model": ErrorResponse}})
async def check_query(req: BatchQueryRequest):
    try:
        result = await resolve_query(req)
        return result
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Internal error: {e}")

@app.get("/health")
def health():
    return {"status": "ok"}

