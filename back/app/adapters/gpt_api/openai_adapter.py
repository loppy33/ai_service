import asyncio
import time
import httpx
from typing import Any, Dict, List, Optional
from urllib.parse import urlparse

from app.api.schemas import (
    QueryRequest,
    QueryResponse,
    Citation,
    Render,
    BatchQueryRequest,
    BatchQueryResponse,
    ItemResult,
    Target,
)

# Используем те же утилиты, что и gpt_chat_parse.py
from app.modes.utiles import (
    build_prompt,
    extract_urls,
    extract_urls_from_html,
    sanitize_markdown_html,
    strip_html_to_text,
    to_query_response,
    _compute_flags_and_position,
)

OPENAI_URL = "https://api.openai.com/v1/chat/completions"
DEFAULT_MODEL = "gpt-4.1-mini"
TOP_CITATIONS_LIMIT = 10


def _coerce_text(c: Any) -> str:
    if isinstance(c, str):
        return c
    if isinstance(c, list):
        # OpenAI может вернуть "content" как список частей
        out: List[str] = []
        for part in c:
            if isinstance(part, dict):
                out.append(str(part.get("text", "")))
            else:
                out.append(str(part))
        return "".join(out)
    return str(c)


async def handle_gpt_api(req: QueryRequest) -> QueryResponse:
    """Режим: обращаемся к OpenAI, но промпт строим так же, как в gpt_chat_parse (через конфиг)."""
    if not req.options or not req.options.api_key:
        raise ValueError("api_key is required for gpt_api")

    start = time.time()
    headers = {"Authorization": f"Bearer {req.options.api_key}"}

    # Превращаем pydantic-модель в dict для build_prompt
    if isinstance(req, dict):
        req_dict: Dict[str, Any] = req
    elif hasattr(req, "model_dump"):
        req_dict = req.model_dump(mode="json")
    elif hasattr(req, "dict"):
        req_dict = req.dict()
    else:
        req_dict = {}

    user_prompt = build_prompt(req_dict)

    payload: Dict[str, Any] = {
        "model": (req.options.model or DEFAULT_MODEL),
        "messages": [
            {"role": "user", "content": user_prompt},
        ],
        "temperature": req.options.temperature if (req.options and req.options.temperature is not None) else 0,
        "top_p": 1.0,
        "frequency_penalty": 0.0,
        "presence_penalty": 0.0,
        "max_tokens": 1200,
    }

    usage: Dict[str, Any] = {}
    content: str = ""

    timeout_sec = (req.options.timeout_ms or 30000) / 1000
    async with httpx.AsyncClient(timeout=timeout_sec) as client:
        resp = await client.post(OPENAI_URL, headers=headers, json=payload)
        resp.raise_for_status()
        data = resp.json()
        usage = data.get("usage", {}) or {}
        content = _coerce_text(data["choices"][0]["message"]["content"])

    # Обрабатываем ответ аналогично gpt_chat_parse: html <- markdown, text, ссылки
    content_html = sanitize_markdown_html(content)
    content_text = strip_html_to_text(content_html)

    text_urls = extract_urls(content_text)
    html_urls = extract_urls_from_html(content_html)
    # уникализируем порядок сохранён
    seen = set()
    urls: List[str] = []
    for u in [*(text_urls or []), *(html_urls or [])]:
        if u and u not in seen:
            seen.add(u)
            urls.append(u)

    citations = [{"url": u, "title": ""} for u in urls]

    # Позиция и флаги — той же функцией, что и в web-режиме
    position_num, flags = _compute_flags_and_position(citations, req.target)

    result: Dict[str, Any] = {
        "position": position_num,
        "answer": content_text.strip(),
        "citations": citations[:TOP_CITATIONS_LIMIT] if TOP_CITATIONS_LIMIT else citations,
        "render": {
            "screenshot_url": None,
            "raw_payload": {
                "model": (req.options.model or DEFAULT_MODEL),
                "usage": usage,
                "flags": flags,
                "from": "openai_adapter",
                "html": content_html,
            },
        },
    }

    duration_ms = int((time.time() - start) * 1000)
    return to_query_response(result, duration_ms)


async def handle_batch_gpt_api(req: BatchQueryRequest) -> BatchQueryResponse:
    """Батч-вариант: та же логика, что и одиночный запрос, для каждой строки."""
    start = time.time()
    sem = asyncio.Semaphore(5)

    async def _one(q: str) -> ItemResult:
        async with sem:
            try:
                single = QueryRequest(
                    query=q,
                    geo=req.geo,
                    target=req.target,
                    source=req.source,
                    options=req.options,
                )
                r: QueryResponse = await handle_gpt_api(single)
                # position уже посчитан внутри handle_gpt_api
                return ItemResult(query=q, response=r)
            except Exception as e:
                return ItemResult(query=q, error=str(e))

    tasks = [asyncio.create_task(_one(q)) for q in req.queries]
    results = await asyncio.gather(*tasks)

    total = int((time.time() - start) * 1000)
    return BatchQueryResponse(results=results, timings_ms={"total": total})
