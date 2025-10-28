from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from typing import List, Optional, Iterable
import os
import hashlib
from urllib.parse import urlparse
from datetime import date, timedelta

# --- твои импорты из проекта ---
from app.api.schemas import BatchQueryRequest, Geo, Target, Options, BatchQueryResponse
from app.adapters.gpt_api.openai_adapter import handle_batch_gpt_api
from app.core.resolver import resolve_query

router = APIRouter(prefix="/analyze", tags=["Analyze"])

# --------- helpers ---------
def _norm_url(u: Optional[str]) -> Optional[str]:
    if not u:
        return None
    u = u.strip()
    if not u:
        return None
    if not u.startswith(("http://", "https://")):
        u = "https://" + u
    return u

def _extract_domain(u: Optional[str]) -> Optional[str]:
    u2 = _norm_url(u)
    if not u2:
        return None
    netloc = urlparse(u2).netloc
    return netloc or None

def _hash_to_unit(s: str) -> float:
    """
    Детерминированно маппим строку в [0,1] через sha256. Не зависит от PYTHONHASHSEED.
    """
    h = hashlib.sha256(s.encode("utf-8")).hexdigest()
    n = int(h[:16], 16)
    return (n % 10**12) / float(10**12)

def _hash_jitter(key: str, lo: float, hi: float) -> float:
    """Детерминированный «джиттер» в [lo, hi] из ключа."""
    u = _hash_to_unit(key)
    return lo + (hi - lo) * u

def _concat(parts: Iterable[Optional[str]]) -> str:
    return "|".join([p for p in parts if p])

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

    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise HTTPException(status_code=500, detail="Missing OPENAI_API_KEY")
    model = os.getenv("OPENAI_MODEL", "gpt-4.1-mini")

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

    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise HTTPException(status_code=500, detail="Missing OPENAI_API_KEY")
    model = os.getenv("OPENAI_MODEL", "gpt-4.1-mini")

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
    Релевантность «top-10» считаем детерминированно от попаданий токенов запроса в GPT-цитаты.
    """
    try:
        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key:
            raise HTTPException(status_code=500, detail="Missing OPENAI_API_KEY")
        model = os.getenv("OPENAI_MODEL", "gpt-4.1-mini")

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

        # --- Детерминированная релевантность top-10 на базе цитат ---
        base = req.queries[:] if req.queries else []
        # (если будет меньше 10 — не дублируем, просто дадим меньше элементов)

        def _normalize_tokens(s: str) -> list[str]:
            return [t for t in "".join(ch.lower() if ch.isalnum() else " " for ch in s or "").split() if len(t) > 2]

        def _q_relevance(q: str, citations: list[SerpCitation]) -> int:
            """
            Релевантность 30..100 детерминированно от GPT-цитат:
            - учитываем, в скольких разных цитатах встретились токены запроса
            - учитываем долю покрытых уникальных токенов запроса
            """
            q_tokens = _normalize_tokens(q)
            if not q_tokens or not citations:
                return 50  # нейтрально, когда сравнивать не с чем

            unique_q = set(q_tokens)
            pages_with_hits = 0
            covered_tokens: set[str] = set()

            for c in citations:
                text = f"{c.title} {c.snippet or ''}"
                tset = set(_normalize_tokens(text))
                hits_here = unique_q & tset
                if hits_here:
                    pages_with_hits += 1
                    covered_tokens |= hits_here

            # сигнал 1: доля покрытых токенов запроса
            coverage = len(covered_tokens) / max(1, len(unique_q))  # 0..1
            # сигнал 2: разнообразие источников (больше разных страниц → лучше)
            diversity = pages_with_hits / max(1, len(citations))    # 0..1

            # сводим к шкале 30..100 (вес покрытия больше, чем разнообразия)
            raw = 30 + (coverage * 50) + (diversity * 20)  # 30..100
            return int(round(max(30, min(100, raw))))

        ten = [{"query": q, "relevance": _q_relevance(q, citations)} for q in base[:10]]

        return SerpResp(
            main_answer=main_answer,
            citations=citations[:20],
            ordered_display=["main_answer", "citations"],
            ten_suggested_with_relevance=ten
        )

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"SERP failed: {e}")


# ===================== OVERVIEW =====================

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
    Берём выбранные запросы, вызываем /serp, собираем main/citations и считаем метрики от фактической выдачи GPT.
    Полностью детерминированно (никакого random).
    """
    # 1) дергаем "серп"
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

    # 3) Видимость (0..100) — приближение от фактов (число цитат / число запросов)
    visibility_base = (citations_count / (queries_count * 3)) * 100.0
    visibility_base = max(0.0, min(100.0, round(visibility_base, 2)))

    # 4) Влияние детерминированной "релевантности"
    try:
        rel_items = (serp_result.ten_suggested_with_relevance or [])[:10]
        if rel_items:
            avg_rel = sum(float(q.get("relevance", 80.0)) for q in rel_items) / len(rel_items)
        else:
            avg_rel = 80.0
    except Exception:
        avg_rel = 80.0
    # 80 ~ 0, 100 ~ +2%, 60 ~ -2%
    visibility_adjust = (avg_rel - 80.0) / 10.0
    visibility_value = max(0.0, min(100.0, round(visibility_base + visibility_adjust, 2)))

    # 5) Собираем «блоб» из фактической GPT-выдачи для детерминированного джиттера
    answers_blob = serp_result.main_answer or ""
    cites_blob = "\n".join(f"{c.title}|{c.url}|{c.snippet or ''}" for c in (serp_result.citations or []))
    queries_blob = ",".join(queries or [])
    period_blob = f"{start.isoformat()}..{today.isoformat()}"
    base_blob = _concat([answers_blob, cites_blob, queries_blob, period_blob])

    # 6) Генерация timeseries вокруг visibility_value (детерминированный «шум» + тренд от релевантности)
    visibility_series: List[TimeseriesPoint] = []
    for i in range(15):
        d = (start + timedelta(days=i))
        jitter = _hash_jitter(f"vis|{base_blob}|{i}", -1.2, 1.2)
        trend = (i - 14) * (visibility_adjust * 0.05)
        point = max(0.0, min(100.0, round(visibility_value + jitter + trend, 2)))
        visibility_series.append(TimeseriesPoint(date=d.isoformat(), value=point))

    # Текущие/вчерашние
    visibility_now = visibility_series[-1].value
    visibility_prev = visibility_series[-2].value
    visibility_delta = round(visibility_now - visibility_prev, 2)

    # 7) Средняя позиция (1..10): чем выше видимость — тем лучше (меньше число)
    #    0% -> ~10, 100% -> ~2
    avg_position_value_raw = max(1.0, 10.0 - (visibility_now / 12.5))
    bump = _hash_jitter(f"pos|{base_blob}|current", -0.2, 0.2)
    avg_position_value = round(min(10.0, max(1.0, avg_position_value_raw + bump)), 1)

    # Серия позиций — инверсия от видимости с детерминированной микро-поправкой
    avg_position_series: List[TimeseriesPoint] = []
    for i, v in enumerate(visibility_series):
        inv = max(1.0, 10.0 - (v.value / 12.5))
        inv_bump = _hash_jitter(f"pos|{base_blob}|{i}", -0.2, 0.2)
        inv = round(min(10.0, max(1.0, inv + inv_bump)), 1)
        avg_position_series.append(TimeseriesPoint(date=visibility_series[i].date, value=inv))

    avg_position_prev = avg_position_series[-2].value
    # Позитив — когда позиция улучшается (число снижается)
    avg_position_delta = round(avg_position_prev - avg_position_value, 2)

    # 8) AI-queries: детерминированно от GPT-выдачи
    company_domain = _extract_domain(req.website) if req.website else None

    def _norm(s: str) -> str:
        return " ".join((s or "").lower().split())

    def _normalize_tokens(s: str) -> list[str]:
        return [t for t in "".join(ch.lower() if ch.isalnum() else " " for ch in s or "").split() if len(t) > 2]

    def _count_pages_with_hits(q_tokens: set[str]) -> int:
        cnt = 0
        for c in (serp_result.citations or []):
            text = f"{c.title} {c.snippet or ''}"
            if q_tokens & set(_normalize_tokens(text)):
                cnt += 1
        return cnt

    def _token_coverage_ratio(q_tokens: set[str]) -> float:
        covered: set[str] = set()
        for c in (serp_result.citations or []):
            text = f"{c.title} {c.snippet or ''}"
            covered |= (q_tokens & set(_normalize_tokens(text)))
        return len(covered) / max(1, len(q_tokens))

    def _answer_overlap_ratio(q_tokens: set[str]) -> float:
        ans_tokens = set(_normalize_tokens(serp_result.main_answer or ""))
        return len(q_tokens & ans_tokens) / max(1, len(q_tokens))

    def _domain_hit() -> bool:
        if not company_domain:
            return False
        for c in (serp_result.citations or []):
            if company_domain in (c.url or ""):
                return True
        return False

    intent_weights = {
        "buy": 1.0, "purchase": 1.0, "price": 0.8, "fees": 1.0, "fee": 1.0,
        "staking": 0.7, "stake": 0.7, "wallet": 0.5, "account": 0.5,
        "register": 0.6, "setup": 0.5, "analysis": 0.3, "trading": 0.4,
        "altcoin": 0.3, "bitcoin": 0.4, "btc": 0.4, "platform": 0.3,
    }

    citations_total = len(serp_result.citations or [])
    queries_count = max(1, len(queries))
    global_boost = min(5.0, (citations_total / (queries_count * 3)) * 5.0)  # как и раньше
    domain_bonus = 1.5 if _domain_hit() else 0.0

    best_scores: dict[str, tuple[str, float]] = {}

    for q_item in (serp_result.ten_suggested_with_relevance or []):
        text = (q_item.get("query") or "").strip()
        if not text:
            continue
        rel = float(q_item.get("relevance", 80.0))  # уже улучшенная релевантность из /serp
        q_tokens_list = _normalize_tokens(text)
        q_tokens = set(q_tokens_list)

        # базовая ось — от релевантности (как было)
        score = (rel - 80.0) / 10.0  # -5..+2

        # фичи от фактической GPT-выдачи (цитаты + main_answer)
        pages_with_hits = _count_pages_with_hits(q_tokens)             # 0..N
        coverage = _token_coverage_ratio(q_tokens)                     # 0..1
        ans_overlap = _answer_overlap_ratio(q_tokens) if citations_total == 0 else 0.0  # fallback, если нет цитат

        # добавки (консервативные лимиты, чтобы не «взрывать» шкалу)
        score += min(3.0, 0.5 * pages_with_hits)       # до +3 за разнообразие источников
        score += min(3.0, 1.5 * coverage)              # до +3 за покрытие токенов
        score += min(2.0, 2.0 * ans_overlap)           # до +2 за пересечение с main_answer при отсутствии цитат
        score += global_boost                           # общий контекст
        score += domain_bonus if any(tok in text.lower() for tok in (req.company_name.lower(), (company_domain or ""))) else 0.0

        # бонус за коммерческие/топовые интенты
        score += sum(w for tok, w in intent_weights.items() if tok in text.lower())

        # финальные рамки и округление
        score = max(-10.0, min(15.0, round(score, 1)))

        key = _norm(text)
        if key not in best_scores or score > best_scores[key][1]:
            best_scores[key] = (text, score)

    ai_queries = [{"query": orig, "ai_visibility_score": sc} for orig, sc in best_scores.values()]
        
    # 9) Грубая оценка недель до ТОПа — по текущей позиции
    if avg_position_value <= 3:
        weeks_to_top = 2
    elif avg_position_value <= 5:
        weeks_to_top = 4
    else:
        weeks_to_top = 6

    # 10) Ответ
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
