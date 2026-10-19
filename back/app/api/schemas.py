from typing import Dict, List, Optional

from pydantic import BaseModel, Field, HttpUrl, model_validator

SOURCE_PATTERN = "^(google_ai|gpt_api|gpt_chat_parse)$"


class Geo(BaseModel):
    country: str
    language: str
    location: Optional[str] = None


class Target(BaseModel):
    url: Optional[HttpUrl] = None
    domain: Optional[str] = None
    brand: Optional[str] = None

    @model_validator(mode="after")
    def at_least_one(self):
        if not (self.url or self.domain or self.brand):
            raise ValueError("target: укажи хотя бы одно из полей: url, domain или brand")
        return self


class Options(BaseModel):
    timeout_ms: Optional[int] = 8000
    cache_ttl_sec: Optional[int] = 120
    model: Optional[str] = None
    temperature: Optional[float] = None
    api_key: Optional[str] = None
    proxy_list: Optional[List[str]] = None


class QueryRequest(BaseModel):
    query: str
    geo: Optional[Geo] = None
    target: Target
    source: str = Field(..., pattern=SOURCE_PATTERN)
    options: Optional[Options] = None


class Citation(BaseModel):
    url: str
    title: Optional[str] = None


class Render(BaseModel):
    screenshot_url: Optional[str] = None
    raw_payload: Dict


class QueryResponse(BaseModel):
    position: Optional[int] = None
    answer: str
    citations: List[Citation]
    render: Render
    timings_ms: Optional[Dict[str, int]] = None


class ErrorResponse(BaseModel):
    error: Dict[str, str]


class BatchQueryRequest(BaseModel):
    queries: List[str] = Field(min_length=1, max_length=50)
    geo: Optional[Geo] = None
    target: Target
    source: str = Field(..., pattern=SOURCE_PATTERN)
    options: Optional[Options] = None
    concurrency: int = Field(default=5, ge=1, le=10)


class ItemResult(BaseModel):
    query: str
    response: Optional[QueryResponse] = None
    error: Optional[str] = None


class BatchQueryResponse(BaseModel):
    results: List[ItemResult]
    timings_ms: Optional[Dict[str, int]] = None
