import re
from datetime import date, timedelta
from typing import List, Optional
from urllib.parse import urlparse

from fastapi import APIRouter, Depends, HTTPException
from fastapi.concurrency import run_in_threadpool
from pydantic import BaseModel, Field, ValidationError
from sqlalchemy.orm import Session

from app.api.schemas import BatchQueryRequest, BatchQueryResponse, Geo, Options, Target
from app.core.config import OPENAI_API_KEY, OPENAI_MODEL, OPENAI_TIMEOUT_MS
from app.core.db import SessionLocal
from app.core.deps import auth_dep
from app.core.resolver import resolve_query
from app.models.snapshot import VisibilitySnapshot
from app.models.user import User

router = APIRouter(prefix="/analyze", tags=["Analyze"], dependencies=[Depends(auth_dep)])

SERIES_DAYS = 14
GEO_NAMES = {
    "us": "the United States",
    "eu": "the European Union",
    "uk": "the United Kingdom",
    "gb": "the United Kingdom",
    "ca": "Canada",
    "au": "Australia",
}
MAX_PHRASES = 30


def _norm_url(u: Optional[str]) -> Optional[str]:
    u = (u or "").strip()
    if not u:
        return None
    return u if u.startswith(("http://", "https://")) else f"https://{u}"


def _extract_domain(u: Optional[str]) -> Optional[str]:
    norm = _norm_url(u)
    return (urlparse(norm).netloc or None) if norm else None


def _geo_name(code: str) -> str:
    return GEO_NAMES.get((code or "").lower(), (code or "").upper())


def _build_target(brand: str, website: Optional[str]) -> Target:
    try:
        return Target(url=_norm_url(website), domain=_extract_domain(website), brand=brand)
    except ValidationError:
        raise HTTPException(status_code=422, detail="Invalid website URL")


async def _run_gpt(queries: List[str], country: str, language: str, target: Target, concurrency: int = 5) -> BatchQueryResponse:
    if not OPENAI_API_KEY:
        raise HTTPException(status_code=503, detail="OPENAI_API_KEY is not configured")

    batch = BatchQueryRequest(
        queries=queries,
        geo=Geo(country=_geo_name(country), language=language),
        target=target,
        source="gpt_api",
        options=Options(api_key=OPENAI_API_KEY, model=OPENAI_MODEL, timeout_ms=OPENAI_TIMEOUT_MS),
        concurrency=max(1, min(concurrency, len(queries))),
    )
    result = await resolve_query(batch)
    if result.results and all(item.response is None for item in result.results):
        reason = next((item.error for item in result.results if item.error), "unknown error")
        raise HTTPException(status_code=502, detail=f"Upstream model request failed: {reason}")
    return result


class BrandInsightReq(BaseModel):
    brand: str = Field(min_length=1, max_length=200)
    website: Optional[str] = None
    country: str = "us"
    language: str = "en"


class BrandInsightResp(BaseModel):
    gpt_answer: str
    understood: bool = True


class CollectPhrasesReq(BaseModel):
    company_name: str = Field(min_length=1, max_length=200)
    geo: str = Field(..., description="country code, e.g. 'US'")


class CollectPhrasesResp(BaseModel):
    phrases: List[str]


class SerpReq(BaseModel):
    queries: List[str] = Field(min_length=1, max_length=50)
    geo: str
    company_name: str
    website: Optional[str] = None


class SerpCitation(BaseModel):
    title: str
    url: str
    snippet: Optional[str] = None


class SerpResp(BaseModel):
    main_answer: str
    citations: List[SerpCitation] = []
    ordered_display: List[str] = ["main_answer", "citations"]
    ten_suggested_with_relevance: List[dict] = []


class OverviewReq(BaseModel):
    company_name: str
    website: Optional[str] = None
    geo: str = "us"
    selected_queries: List[str] = []
    added_queries: List[str] = []


class TimeseriesPoint(BaseModel):
    date: str
    value: float


class AiQuery(BaseModel):
    query: str
    ai_visibility_score: float
    position: Optional[int] = None


class OverviewResp(BaseModel):
    period_from: str
    period_to: str
    website: Optional[str]
    company_name: str
    geo: str
    potential_queries_count: int
    weeks_to_top: int
    visibility_value: float
    visibility_delta: float
    visibility_series: List[TimeseriesPoint]
    ai_queries: List[AiQuery]
    avg_position_value: Optional[float]
    avg_position_delta: float
    avg_position_series: List[TimeseriesPoint]
    citations: List[SerpCitation]
    main_answer: str


@router.post("/brand-insight", response_model=BrandInsightResp)
async def brand_insight(req: BrandInsightReq):
    prompt = (
        f"What do you know about {req.brand}? "
        "Can you tell 2–3 sentences to understand what the company does?"
    )
    result = await _run_gpt([prompt], req.country, req.language, _build_target(req.brand, req.website), concurrency=1)

    item = result.results[0]
    answer = (item.response.answer if item.response else "").strip()
    return BrandInsightResp(gpt_answer=answer or "I don't have enough public info yet", understood=bool(answer))


def _parse_phrases(text: str) -> List[str]:
    lines = [re.sub(r"^\s*(?:[-*•]|\d+[.)])\s*", "", ln).strip(" \t\"'") for ln in text.replace("\r", "").split("\n")]
    lines = [ln for ln in lines if ln]
    if len(lines) == 1 and "," in lines[0]:
        lines = [s.strip() for s in lines[0].split(",") if s.strip()]
    phrases = [p for p in lines if 2 <= len(p.split()) <= 8]
    return list(dict.fromkeys(phrases))[:MAX_PHRASES]


@router.post("/collect-phrases", response_model=CollectPhrasesResp)
async def collect_phrases(req: CollectPhrasesReq):
    prompt = (
        "Can you give me a list of short search phrases (2-6 words) "
        f"that can relate to the business of {req.company_name} in {_geo_name(req.geo)} with commercial intent? "
        "Return only a plain list, no numbering."
    )
    result = await _run_gpt([prompt], req.geo, "en", Target(brand=req.company_name), concurrency=1)

    item = result.results[0]
    phrases = _parse_phrases(item.response.answer if item.response else "")
    if not phrases:
        phrases = [f"buy {req.company_name}", f"{req.company_name} price", f"{req.company_name} near me"]
    return CollectPhrasesResp(phrases=phrases)


def _tokens(s: str) -> List[str]:
    return [t for t in "".join(ch.lower() if ch.isalnum() else " " for ch in s or "").split() if len(t) > 2]


def _relevance(query: str, citations: List[SerpCitation]) -> int:
    q_tokens = set(_tokens(query))
    if not q_tokens or not citations:
        return 50

    pages_with_hits = 0
    covered: set[str] = set()
    for c in citations:
        hits = q_tokens & set(_tokens(f"{c.title} {c.snippet or ''} {c.url}"))
        if hits:
            pages_with_hits += 1
            covered |= hits

    coverage = len(covered) / len(q_tokens)
    diversity = pages_with_hits / len(citations)
    return int(round(max(30, min(100, 30 + coverage * 50 + diversity * 20))))


def _collect_citations(result: BatchQueryResponse) -> List[SerpCitation]:
    seen: set[str] = set()
    out: List[SerpCitation] = []
    for item in result.results:
        for c in (item.response.citations if item.response else []):
            if c.url not in seen:
                seen.add(c.url)
                out.append(SerpCitation(title=c.title or c.url, url=c.url))
    return out


def _main_answer(result: BatchQueryResponse) -> str:
    parts = [f"• {item.query}: {item.response.answer}" for item in result.results if item.response and item.response.answer]
    return "\n".join(parts)[:5000]


@router.post("/serp", response_model=SerpResp)
async def serp(req: SerpReq):
    queries = list(dict.fromkeys(q.strip() for q in req.queries if q.strip()))
    if not queries:
        raise HTTPException(status_code=422, detail="No queries provided")

    result = await _run_gpt(queries, req.geo, "en", _build_target(req.company_name, req.website))
    citations = _collect_citations(result)

    return SerpResp(
        main_answer=_main_answer(result),
        citations=citations[:20],
        ten_suggested_with_relevance=[{"query": q, "relevance": _relevance(q, citations)} for q in queries[:10]],
    )


def _query_score(position: Optional[int]) -> float:
    return round(100.0 / position, 1) if position else 0.0


def _weeks_to_top(avg_position: Optional[float]) -> int:
    if avg_position is None:
        return 8
    if avg_position <= 3:
        return 2
    if avg_position <= 5:
        return 4
    return 6


def _save_and_load_series(user_id: int, project_key: str, visibility: float, avg_position: Optional[float]):
    today = date.today()
    start = today - timedelta(days=SERIES_DAYS)
    db: Session = SessionLocal()
    try:
        snap = (
            db.query(VisibilitySnapshot)
            .filter_by(user_id=user_id, project_key=project_key, day=today)
            .first()
        )
        if snap:
            snap.visibility = visibility
            snap.avg_position = avg_position
        else:
            db.add(VisibilitySnapshot(user_id=user_id, project_key=project_key, day=today, visibility=visibility, avg_position=avg_position))
        db.commit()

        rows = (
            db.query(VisibilitySnapshot)
            .filter(
                VisibilitySnapshot.user_id == user_id,
                VisibilitySnapshot.project_key == project_key,
                VisibilitySnapshot.day >= start,
            )
            .order_by(VisibilitySnapshot.day.asc())
            .all()
        )
        return [(r.day, r.visibility, r.avg_position) for r in rows]
    finally:
        db.close()


def _delta(values: List[float]) -> float:
    return round(values[-1] - values[-2], 2) if len(values) >= 2 else 0.0


@router.post("/overview", response_model=OverviewResp)
async def overview(req: OverviewReq, user: User = Depends(auth_dep)):
    queries = list(dict.fromkeys(q.strip() for q in [*req.selected_queries, *req.added_queries] if q.strip()))
    today = date.today()
    base = dict(
        period_from=(today - timedelta(days=SERIES_DAYS)).isoformat(),
        period_to=today.isoformat(),
        website=req.website,
        company_name=req.company_name,
        geo=req.geo,
        potential_queries_count=len(queries),
    )

    if not queries:
        return OverviewResp(
            **base,
            weeks_to_top=_weeks_to_top(None),
            visibility_value=0.0,
            visibility_delta=0.0,
            visibility_series=[],
            ai_queries=[],
            avg_position_value=None,
            avg_position_delta=0.0,
            avg_position_series=[],
            citations=[],
            main_answer="",
        )

    result = await _run_gpt(queries, req.geo, "en", _build_target(req.company_name, req.website))

    answered = [item for item in result.results if item.response]
    positions = {item.query: item.response.position for item in answered}
    matched = [p for p in positions.values() if p]

    visibility = round(len(matched) / len(answered) * 100, 1) if answered else 0.0
    avg_position = round(sum(matched) / len(matched), 1) if matched else None

    project_key = f"{req.company_name}|{_extract_domain(req.website) or ''}|{req.geo}".lower()[:512]
    rows = await run_in_threadpool(_save_and_load_series, user.id, project_key, visibility, avg_position)

    visibility_series = [TimeseriesPoint(date=d.isoformat(), value=v) for d, v, _ in rows]
    position_rows = [(d, p) for d, _, p in rows if p is not None]
    avg_position_series = [TimeseriesPoint(date=d.isoformat(), value=p) for d, p in position_rows]

    position_values = [p for _, p in position_rows]
    avg_position_delta = round(position_values[-2] - position_values[-1], 2) if len(position_values) >= 2 else 0.0

    ai_queries = [
        AiQuery(query=item.query, ai_visibility_score=_query_score(positions[item.query]), position=positions[item.query])
        for item in answered
    ]

    return OverviewResp(
        **base,
        weeks_to_top=_weeks_to_top(avg_position),
        visibility_value=visibility,
        visibility_delta=_delta([v for _, v, _ in rows]),
        visibility_series=visibility_series,
        ai_queries=ai_queries,
        avg_position_value=avg_position,
        avg_position_delta=avg_position_delta,
        avg_position_series=avg_position_series,
        citations=_collect_citations(result)[:20],
        main_answer=_main_answer(result),
    )
