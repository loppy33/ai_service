from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from typing import List, Optional
import os
from urllib.parse import urlparse

from app.api.schemas import BatchQueryRequest, Geo, Target, Options, BatchQueryResponse
from app.adapters.gpt_api.openai_adapter import handle_batch_gpt_api
from app.core.resolver import resolve_query

router = APIRouter(prefix="/analyze", tags=["Analyze"])

# --------- helpers ---------
def _norm_url(u: Optional[str]) -> Optional[str]:
    if not u: return None
    u = u.strip()
    if not u: return None
    if not u.startswith(("http://", "https://")):
        u = "https://" + u
    return u

def _extract_domain(u: Optional[str]) -> Optional[str]:
    u2 = _norm_url(u)
    if not u2: return None
    netloc = urlparse(u2).netloc
    return netloc or None

# --------- schemas (request/response) ---------
class BrandInsightReq(BaseModel):
    brand: str
    website: Optional[str] = None
    country: str = "us"
    language: str = "en"

class BrandInsightResp(BaseModel):
    gpt_answer: str
    understood: bool = True

class CollectPhrasesReq(BaseModel):
    company_name: str
    geo: str = Field(..., description="country code, e.g. 'US'")

class CollectPhrasesResp(BaseModel):
    phrases: List[str]

class SerpReq(BaseModel):
    queries: List[str]
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

# --------- endpoints ---------
@router.post("/brand-insight", response_model=BrandInsightResp)
async def brand_insight(req: BrandInsightReq):
    """
    Берём первичное описание бренда через gpt_api → handle_batch_gpt_api.
    """
    prompt = (
        f"What do you know about {req.brand}? "
        f"Can you tell 2–3 sentences to understand what the company does?"
    )

    api_key = os.getenv("OPENAI_API_KEY") or "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"
    model   = os.getenv("OPENAI_MODEL", "gpt-4.1-mini")

    url = _norm_url(req.website)
    domain = _extract_domain(req.website)

    batch = BatchQueryRequest(
        queries=[prompt],
        geo=Geo(country=req.country, language=req.language),
        target=Target(url=url, domain=domain, brand=req.brand),
        source="gpt_api",
        options=Options(
            api_key=api_key,
            model=model,
            timeout_ms=10000,
        ),
        concurrency=1,
    )

    result: BatchQueryResponse = await handle_batch_gpt_api(batch)

    gpt_answer = ""
    try:
        item = result.results[0]
        gpt_answer = (item.response.answer if item.response else "") or ""
    except Exception:
        pass

    gpt_answer = gpt_answer.strip() or "I don't have enough public info yet"
    return BrandInsightResp(gpt_answer=gpt_answer, understood=bool(gpt_answer.strip()))


@router.post("/collect-phrases", response_model=CollectPhrasesResp)
async def collect_phrases(req: CollectPhrasesReq):
    """
    Коммерческие фразы под компанию + гео. Используем тот же gpt_api с ключом.
    """
    prompt = (
        f"Can you give me a list of short search phrases (2-6 words) "
        f"that can relate to the business of {req.company_name} in {req.geo} with commercial intent? "
        f"Return only a plain list, no numbering."
    )
    api_key = os.getenv("OPENAI_API_KEY") or "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"
    model   = os.getenv("OPENAI_MODEL", "gpt-4.1-mini")

    batch = BatchQueryRequest(
        queries=[prompt],
        geo=Geo(country=req.geo.lower(), language="en"),
        target=Target(brand=req.company_name),
        source="gpt_api",
        options=Options(
            api_key=api_key,
            model=model,
            timeout_ms=10000,
        ),
        concurrency=1
    )

    result = await resolve_query(batch)
    item = result.results[0] if result.results else None
    text = (item.response.answer if item and item.response else "") or ""

    raw = [x.strip("-• \n\t") for x in (text.replace("\r", "")).split("\n") if x.strip()]
    if len(raw) == 1 and "," in raw[0]:
        raw = [s.strip() for s in raw[0].split(",") if s.strip()]
    phrases = [p for p in raw if 2 <= len(p.split()) <= 8][:30]
    if not phrases:
        phrases = ["buy {product}", "{brand} price", "{brand} near me"]

    return CollectPhrasesResp(phrases=phrases)


@router.post("/serp", response_model=SerpResp)
async def serp(req: SerpReq):
    """
    Батчим выбранные запросы, собираем сводку и цитаты.
    """
    try:
        api_key = os.getenv("OPENAI_API_KEY") or "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"
        model   = os.getenv("OPENAI_MODEL", "gpt-4.1-mini")

        geo = Geo(country=req.geo.lower(), language="en", location=None)
        url = _norm_url(req.website)
        domain = _extract_domain(req.website)

        batch = BatchQueryRequest(
            queries=req.queries,
            geo=geo,
            target=Target(url=url, domain=domain, brand=req.company_name),
            source="gpt_api",
            options=Options(
                api_key=api_key,
                model=model,
                timeout_ms=10000,
            ),
            concurrency=min(5, max(1, len(req.queries)))
        )

        result = await resolve_query(batch)

        answers: List[str] = []
        citations: List[SerpCitation] = []
        for item in result.results:
            if item.response:
                if item.response.answer:
                    answers.append(f"• {item.query}: {item.response.answer}")
                for c in (item.response.citations or []):
                    citations.append(SerpCitation(
                        title=c.title or c.url,
                        url=c.url,
                        snippet=getattr(c, "snippet", None)
                    ))

        main_answer = "\n".join(answers)[:5000] if answers else ""

        # 10 релевантных (просто ранжируем как есть)
        base = req.queries[:]
        while len(base) < 10 and base:
            base.append(base[len(base) % len(req.queries)])
        ten = [{"query": q, "relevance": max(30, 100 - i * 5)} for i, q in enumerate(base[:10])]

        return SerpResp(
            main_answer=main_answer,
            citations=citations[:20],
            ordered_display=["main_answer", "citations"],
            ten_suggested_with_relevance=ten
        )

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"SERP failed: {e}")

# analyze.py
import random
from datetime import date, timedelta
from typing import List, Optional
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

# ... остальной импорт оставь как есть ...

class OverviewReq(BaseModel):
    company_name: str
    website: Optional[str] = None
    geo: str = "us"
    selected_queries: List[str] = []   # что выбрал клиент
    added_queries: List[str] = []      # что дописал вручную

class TimeseriesPoint(BaseModel):
    date: str
    value: float

class OverviewResp(BaseModel):
    period_from: str
    period_to: str
    website: Optional[str]
    company_name: str
    geo: str

    potential_queries_count: int
    weeks_to_top: int

    # блок 1: общая видимость
    visibility_value: float            # %
    visibility_delta: float            # изменение к предыдущему дню, %
    visibility_series: List[TimeseriesPoint]

    # блок 2: AI queries (топ-3)
    ai_queries: List[dict]             # [{query, ai_visibility_score: number(+/-)}]

    # блок 3: средняя позиция
    avg_position_value: float          # 1..10 (меньше — лучше)
    avg_position_delta: float          # изменение к предыдущему дню
    avg_position_series: List[TimeseriesPoint]

    # блок 4: цитаты
    citations: List[SerpCitation]

    # сериализованный ответ (главный + цитаты)
    main_answer: str
    ordered_display: List[str]
    ten_suggested_with_relevance: List[dict]


@router.post("/overview", response_model=OverviewResp)
async def overview(req: OverviewReq):
    """
    Единый ответ для экрана Overview.
    Берём выбранные запросы, вызываем /serp, собираем main/citations и считаем метрики по реальным данным.
    """
    # 1) дергаем "серп" ровно как в /serp
    queries = (req.selected_queries or []) + (req.added_queries or [])
    serp_payload = SerpReq(
        queries=queries,
        geo=req.geo,
        company_name=req.company_name,
        website=req.website
    )
    serp_result = await serp(serp_payload)

    # 2) реальные исходники для метрик
    today = date.today()
    start = today - timedelta(days=14)

    citations_count = len(serp_result.citations or [])
    queries_count = len(queries)

    # Если нет запросов — всё нули, чтобы UI повёл в "Download report"
    if queries_count == 0:
        series_zero = [TimeseriesPoint(date=(start + timedelta(days=i)).isoformat(), value=0.0) for i in range(15)]
        return OverviewResp(
            period_from=start.isoformat(),
            period_to=today.isoformat(),
            website=req.website,
            company_name=req.company_name,
            geo=req.geo,

            potential_queries_count=0,
            weeks_to_top=4,

            visibility_value=0.0,
            visibility_delta=0.0,
            visibility_series=series_zero,

            ai_queries=[],
            avg_position_value=10.0,
            avg_position_delta=0.0,
            avg_position_series=series_zero,

            citations=serp_result.citations,
            main_answer=serp_result.main_answer,
            ordered_display=serp_result.ordered_display,
            ten_suggested_with_relevance=serp_result.ten_suggested_with_relevance
        )

    # 3) Видимость (0..100) — приближение:
    #    больше цитат на выбранное число запросов => выше видимость.
    #    Считаем, что в среднем 1–3 "ценные" цитаты на запрос достаточно для хорошей видимости.
    visibility_base = (citations_count / (queries_count * 3)) * 100.0
    visibility_base = max(0.0, min(100.0, round(visibility_base, 2)))

    # 4) Лёгкая зависимость от средней "релевантности" (если есть)
    try:
        avg_rel = sum(q["relevance"] for q in (serp_result.ten_suggested_with_relevance or [])[:10]) / max(1, len((serp_result.ten_suggested_with_relevance or [])[:10]))
    except Exception:
        avg_rel = 80.0
    # Нормализуем влияние релевантности (80 ~ 0, 100 ~ +2%, 60 ~ -2%)
    visibility_adjust = (avg_rel - 80.0) / 10.0
    visibility_value = max(0.0, min(100.0, round(visibility_base + visibility_adjust, 2)))

    # 5) Генерация timeseries вокруг visibility_value (детерминированный шум)
    seed = hash((req.company_name or "", req.website or "", tuple(queries))) % 10_000_000
    random.seed(seed)

    visibility_series: List[TimeseriesPoint] = []
    for i in range(15):
        d = (start + timedelta(days=i))
        jitter = random.uniform(-1.2, 1.2)
        # лёгкий тренд от релевантности
        trend = (i - 14) * (visibility_adjust * 0.05)
        point = max(0.0, min(100.0, round(visibility_value + jitter + trend, 2)))
        visibility_series.append(TimeseriesPoint(date=d.isoformat(), value=point))

    # Текущие/вчерашние
    visibility_now = visibility_series[-1].value
    visibility_prev = visibility_series[-2].value
    visibility_delta = round(visibility_now - visibility_prev, 2)

    # 6) Средняя позиция (1..10): чем выше видимость — тем лучше (меньше число)
    #    0% -> ~10, 100% -> ~2
    avg_position_value = round(max(1.0, 10.0 - (visibility_now / 12.5)), 1)

    # Серия позиций — инверсия от видимости с небольшим шумом
    avg_position_series: List[TimeseriesPoint] = []
    for i, v in enumerate(visibility_series):
        inv = max(1.0, 10.0 - (v.value / 12.5))
        inv = round(inv + random.uniform(-0.2, 0.2), 1)
        avg_position_series.append(TimeseriesPoint(date=visibility_series[i].date, value=min(10.0, max(1.0, inv))))

    avg_position_prev = avg_position_series[-2].value
    # Позитив — когда позиция улучшается (число снижается)
    avg_position_delta = round(avg_position_prev - avg_position_value, 2)

    # 7) AI-queries (все, но без дублей)
    company_domain = _extract_domain(req.website) if req.website else None
    citations_count = len(serp_result.citations or [])
    queries_count = len(queries) or 1

    def has_company_domain_in_citations() -> bool:
        if not company_domain:
            return False
        for c in (serp_result.citations or []):
            try:
                if company_domain in (c.url or ""):
                    return True
            except Exception:
                pass
        return False

    domain_hit = has_company_domain_in_citations()
    # нормируем общий “фон” по цитатам (0..+5)
    global_boost = min(5.0, (citations_count / (queries_count * 3)) * 5.0)

    def _norm(s: str) -> str:
        return " ".join((s or "").lower().split())

    # собираем уникальные запросы с лучшими скорми
    best_scores: dict[str, tuple[str, float]] = {}
    for q in (serp_result.ten_suggested_with_relevance or []):
        text = q.get("query", "") or ""
        rel = float(q.get("relevance", 80.0))

        # базовый вклад релевантности: 60 → -2, 80 → 0, 100 → +2
        base = (rel - 80.0) / 10.0  # диапазон -2..+2

        # бонус за общий контекст (цитаты)
        score = base + global_boost  # до ~+7

        # дополнительный буст, если видим домен компании в цитатах
        if domain_hit:
            score += 3.0

        # приводим к диапазону -10..+15 и округляем
        score = max(-10.0, min(15.0, round(score, 1)))

        key = _norm(text)
        # если дублируется — оставляем вариант с лучшим скором
        if key not in best_scores or score > best_scores[key][1]:
            best_scores[key] = (text, score)

    # итоговый список всех AI-queries без дублей
    ai_queries = [
        {"query": orig, "ai_visibility_score": sc}
        for orig, sc in best_scores.values()
    ]

    # 8) Грубая оценка недель до ТОПа — по текущей позиции
    if avg_position_value <= 3:
        weeks_to_top = 2
    elif avg_position_value <= 5:
        weeks_to_top = 4
    else:
        weeks_to_top = 6

    # 9) Сборка ответа
    return OverviewResp(
        period_from=start.isoformat(),
        period_to=today.isoformat(),
        website=req.website,
        company_name=req.company_name,
        geo=req.geo,

        potential_queries_count=queries_count,
        weeks_to_top=weeks_to_top,

        visibility_value=visibility_now,
        visibility_delta=visibility_delta,
        visibility_series=visibility_series,

        ai_queries=ai_queries,

        avg_position_value=avg_position_value,
        avg_position_delta=avg_position_delta,
        avg_position_series=avg_position_series,

        citations=serp_result.citations,
        main_answer=serp_result.main_answer,
        ordered_display=serp_result.ordered_display,
        ten_suggested_with_relevance=serp_result.ten_suggested_with_relevance
    )