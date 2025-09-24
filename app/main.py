from fastapi import FastAPI, HTTPException
from app.api.schemas import QueryRequest, QueryResponse, ErrorResponse, BatchQueryRequest, BatchQueryResponse
from app.core.resolver import resolve_query
from pathlib import Path
from fastapi.staticfiles import StaticFiles

app = FastAPI(title="LLM SERP Parser API")
STATIC_ROOT = Path("app/data").resolve()
app.mount("/static", StaticFiles(directory=STATIC_ROOT), name="static")

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
