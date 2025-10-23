# Патч для gpt_chat_parse.py — дружелюбные сообщения про прокси/туннель
# Вставь изменения ниже в свой файл gpt_chat_parse.py

import random
import time
from pathlib import Path
from typing import Any, Dict

from playwright.async_api import async_playwright, TimeoutError as PlaywrightTimeoutError, Error as PlaywrightError
from app.api.schemas import BatchQueryRequest, BatchQueryResponse, ItemResult, QueryRequest, QueryResponse

from app.core.position import match_position
from app.core.utiles import *
from app.core.utiles import _compute_flags_and_position

# === Константы ===
TARGET_URL = "https://chat.openai.com/"
STATIC_ROOT = Path("app/data")
SESSIONS_DIR = Path("app/data/sessions")
ASSISTANT_SEL = "div[data-message-author-role='assistant']"

# --- НОВОЕ: аккуратная нормализация сетевых ошибок ---
def _nice_net_error(err: Exception) -> RuntimeError:
    s = str(err)
    if "Browser needs to be launched with the global proxy" in s:
        return RuntimeError("Нужно запускать браузер с глобальным прокси: launch(proxy={server:'http://per-context'}), а реальные прокси задавать в new_context().")
    if "ERR_TUNNEL_CONNECTION_FAILED" in s:
        return RuntimeError("Ошибка подключения к прокси (ERR_TUNNEL_CONNECTION_FAILED). Проверьте доступность прокси/аутентификацию.")
    if "ERR_PROXY_CONNECTION_FAILED" in s or "ECONNRESET" in s or "ECONNREFUSED" in s:
        return RuntimeError("Ошибка сети/прокси при открытии ChatGPT. Проверьте настройки прокси или доступ в сеть.")
    if "ERR_NAME_NOT_RESOLVED" in s:
        return RuntimeError("DNS не разрешил хост chat.openai.com — проверьте резолвер.")
    return RuntimeError(f"Сетевая ошибка: {s}")


def _pick_random_session() -> Path | None:
    try:
        files = [p for p in SESSIONS_DIR.glob("*.json") if p.is_file()]
        return random.choice(files) if files else None
    except Exception:
        return None


def _invalidate_session(session_path: Path | None):
    if not session_path:
        return
    try:
        session_path.unlink(missing_ok=True)
    except Exception:
        pass


async def _ensure_no_auth_modal_or_raise(page, session_path: Path | None):
    modal = page.locator("[data-testid='modal-no-auth-welcome-back']").first
    try:
        if await modal.count() > 0 and await modal.is_visible():
            _invalidate_session(session_path)
            raise RuntimeError(f"Ошибка сессии: {session_path.name if session_path else 'unknown'}. Попробуйте ещё раз.")
    except Exception:
        pass


# === Основная логика ===
async def handle_gpt_chat_parse(req: QueryRequest) -> QueryResponse:
    start = time.time()

    session_path = _pick_random_session()

    from uuid import uuid4
    screen_path = STATIC_ROOT / f"chatgpt_answer_{int(time.time()*1000)}_{uuid4().hex[:6]}.png"

    if isinstance(req, dict):
        req_dict = req
    elif hasattr(req, "model_dump"):
        req_dict = req.model_dump(mode="json")
    elif hasattr(req, "dict"):
        req_dict = req.dict()
    else:
        req_dict = {}

    proxy_list = None
    if hasattr(req, "options") and getattr(req.options, "proxy_list", None):
        proxy_list = req.options.proxy_list
    else:
        proxy_list = (req_dict.get("options", {}) or {}).get("proxy_list")

    proxy = choose_proxy(proxy_list) if proxy_list else None

    async with async_playwright() as p:
        # ВАЖНО: убрали proxy из launch ("per-context" ломал соединение)
        try:
            browser = await p.chromium.launch(
                headless=False,
                args=[
                    "--disable-blink-features=AutomationControlled",
                    "--disable-features=IsolateOrigins,site-per-process",
                ],
                proxy={"server": "http://per-context"},  # требование Playwright для per-context proxy
                slow_mo=50,
            )
        except PlaywrightError as e:
            raise _nice_net_error(e)

        context_kwargs: Dict[str, Any] = {}
        if session_path:
            context_kwargs["storage_state"] = str(session_path)

        # Прокси теперь только на уровне контекста
        if proxy:
            context_kwargs["proxy"] = proxy
        else:
            context_kwargs["proxy"] = {"server": "direct"}

        try:
            context = await browser.new_context(**context_kwargs)
        except PlaywrightError as e:
            await browser.close()
            raise _nice_net_error(e)

        page = await context.new_page()

        try:
            await page.goto(TARGET_URL)
            await page.wait_for_load_state("domcontentloaded")
        except PlaywrightError as e:
            await browser.close()
            raise _nice_net_error(e)
        except PlaywrightError as e:
            await browser.close()
            raise _nice_net_error(e)

        # Проверка на модал "welcome back"
        await _ensure_no_auth_modal_or_raise(page, session_path)
        editor = await find_editor(page)

        try:
            await editor.scroll_into_view_if_needed()
            await editor.click(timeout=10_000)
        except PlaywrightTimeoutError:
            await _ensure_no_auth_modal_or_raise(page, session_path)
            raise

        prompt = build_prompt(req_dict)
        await page.keyboard.insert_text(prompt)
        await page.keyboard.press("Enter")

        try:
            result: Dict[str, Any] = await handle_after_enter(page, req_dict, screen_path)
            citations_list = result.get("citations") or []
            pos, flags = _compute_flags_and_position(citations_list, req.target)
            if pos is not None:
                result["position"] = pos
            render = result.get("render") or {}
            raw_payload = (render.get("raw_payload") or {})
            raw_payload["flags"] = flags
            render["raw_payload"] = raw_payload
            result["render"] = render
        except PlaywrightTimeoutError:
            await _ensure_no_auth_modal_or_raise(page, session_path)
            raise
        except PlaywrightError as e:
            raise _nice_net_error(e)
        finally:
            await browser.close()

    duration_ms = int((time.time() - start) * 1000)
    return to_query_response(result, duration_ms)


async def handle_gpt_chat_parse_batch(req: BatchQueryRequest) -> BatchQueryResponse:
    if req.source != "gpt_chat_parse":
        raise ValueError("handle_gpt_chat_parse_batch ожидает source='gpt_chat_parse'")

    start = time.time()
    sem = asyncio.Semaphore(max(1, req.concurrency or 5))
    results: List[ItemResult] = []

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
                r: QueryResponse = await handle_gpt_chat_parse(single)
                if r.position is None:
                    try:
                        r.position = match_position(r.citations, req.target)
                    except Exception:
                        pass
                return ItemResult(query=q, response=r)
            except Exception as e:
                # Здесь теперь прилетят наши дружелюбные RuntimeError с коротким текстом
                return ItemResult(query=q, error=str(e))

    tasks = [asyncio.create_task(_one(q)) for q in req.queries]
    results = await asyncio.gather(*tasks)

    total = int((time.time() - start) * 1000)
    return BatchQueryResponse(results=results, timings_ms={"total": total})
