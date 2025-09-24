from app.api.schemas import QueryRequest, QueryResponse, BatchQueryRequest
from app.adapters.gpt_api.openai_adapter import handle_batch_gpt_api
from app.adapters.gpt_api.google_ai import handle_google_ai, handle_google_ai_batch
from app.adapters.gpt_api.gpt_chat_parse import handle_gpt_chat_parse_batch

async def resolve_query(req: BatchQueryRequest) -> BatchQueryRequest:
    if req.source == "gpt_api":
        return await handle_batch_gpt_api(req)
    
    elif req.source == "google_ai":
        return await handle_google_ai_batch(req)
    
    elif req.source == "gpt_chat_parse":
        return await handle_gpt_chat_parse_batch(req)
    else:
        raise ValueError(f"Unsupported source: {req.source}")
