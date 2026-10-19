import asyncio
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.api.routes import analyze, auth, billing, leads
from app.api.schemas import BatchQueryRequest, BatchQueryResponse, ErrorResponse
from app.core.config import CORS_ORIGINS, JWT_SECRET, SCREENSHOTS_DIR
from app.core.db import Base, engine
from app.core.deps import auth_dep
from app.core.resolver import resolve_query
from app.core.worker import worker_loop
from app.models import email_queue, lead, snapshot, user

REGISTERED_MODELS = (email_queue, lead, snapshot, user)


@asynccontextmanager
async def lifespan(app: FastAPI):
    if not JWT_SECRET:
        raise RuntimeError("JWT_SECRET is not set")
    Base.metadata.create_all(bind=engine)
    SCREENSHOTS_DIR.mkdir(parents=True, exist_ok=True)

    worker_task = asyncio.create_task(worker_loop())
    try:
        yield
    finally:
        worker_task.cancel()
        try:
            await worker_task
        except asyncio.CancelledError:
            pass


app = FastAPI(title="LLM SERP Parser API", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

SCREENSHOTS_DIR.mkdir(parents=True, exist_ok=True)
app.mount("/static", StaticFiles(directory=SCREENSHOTS_DIR), name="static")

app.include_router(auth.router)
app.include_router(analyze.router)
app.include_router(leads.router)
app.include_router(billing.router)


@app.post(
    "/v1/check",
    response_model=BatchQueryResponse,
    responses={400: {"model": ErrorResponse}},
    dependencies=[Depends(auth_dep)],
)
async def check_query(req: BatchQueryRequest):
    try:
        return await resolve_query(req)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.get("/health")
def health():
    return {"status": "ok"}
