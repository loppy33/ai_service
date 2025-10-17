from fastapi import FastAPI, HTTPException
from app.api.schemas import QueryRequest, QueryResponse, ErrorResponse, BatchQueryRequest, BatchQueryResponse
from app.core.resolver import resolve_query
from pathlib import Path
from fastapi.staticfiles import StaticFiles
from app.api.routes import auth  # ⬅️ добавляем импорт
from app.api.routes import analyze   # NEW
from app.api.routes import leads     # NEW
from app.api.routes import billing   # NEW
from fastapi.middleware.cors import CORSMiddleware

app = FastAPI(title="LLM SERP Parser API")

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
