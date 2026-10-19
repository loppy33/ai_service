import asyncio
import random
import time
from pathlib import Path
from typing import Any, Dict, Optional
from uuid import uuid4

from playwright.async_api import Error as PlaywrightError
from playwright.async_api import TimeoutError as PlaywrightTimeoutError
from playwright.async_api import async_playwright

from app.api.schemas import BatchQueryRequest, BatchQueryResponse, ItemResult, QueryRequest, QueryResponse
from app.core.config import CHATGPT_HEADLESS, SCREENSHOTS_DIR, SESSIONS_DIR
from app.core.utiles import build_prompt, choose_proxy, find_editor, handle_after_enter, to_query_response

TARGET_URL = "https://chatgpt.com/"
AUTH_MODAL_SEL = "[data-testid='modal-no-auth-welcome-back']"


def _nice_net_error(err: Exception) -> RuntimeError:
    s = str(err)
    if "Browser needs to be launched with the global proxy" in s:
        return RuntimeError("Нужно запускать браузер с глобальным прокси: launch(proxy={server:'http://per-context'}), а реальные прокси задавать в new_context().")
    if "ERR_TUNNEL_CONNECTION_FAILED" in s:
        return RuntimeError("Ошибка подключения к прокси (ERR_TUNNEL_CONNECTION_FAILED). Проверьте доступность прокси/аутентификацию.")
    if "ERR_PROXY_CONNECTION_FAILED" in s or "ECONNRESET" in s or "ECONNREFUSED" in s:
        return RuntimeError("Ошибка сети/прокси при открытии ChatGPT. Проверьте настройки прокси или доступ в сеть.")
    if "ERR_NAME_NOT_RESOLVED" in s:
        return RuntimeError("DNS не разрешил хост chatgpt.com — проверьте резолвер.")
    return RuntimeError(f"Сетевая ошибка: {s}")


def _pick_random_session() -> Optional[Path]:
    files = [p for p in SESSIONS_DIR.glob("*.json") if p.is_file()]
    return random.choice(files) if files else None


def _invalidate_session(session_path: Optional[Path]) -> None:
    if session_path:
        session_path.unlink(missing_ok=True)


async def _ensure_no_auth_modal_or_raise(page, session_path: Optional[Path]) -> None:
    modal = page.locator(AUTH_MODAL_SEL).first
    try:
        visible = await modal.count() > 0 and await modal.is_visible()
    except PlaywrightError:
        return
    if visible:
        _invalidate_session(session_path)
        raise RuntimeError(f"Ошибка сессии: {session_path.name if session_path else 'unknown'}. Попробуйте ещё раз.")


async def handle_gpt_chat_parse(req: QueryRequest) -> QueryResponse:
    start = time.time()
    session_path = _pick_random_session()
    screen_path = SCREENSHOTS_DIR / f"chatgpt_answer_{int(time.time() * 1000)}_{uuid4().hex[:6]}.png"

    req_dict = req.model_dump(mode="json")
    proxy_list = req.options.proxy_list if req.options else None
    proxy = choose_proxy(proxy_list) if proxy_list else None

    async with async_playwright() as p:
        try:
            browser = await p.chromium.launch(
                headless=CHATGPT_HEADLESS,
                args=[
                    "--disable-blink-features=AutomationControlled",
                    "--disable-features=IsolateOrigins,site-per-process",
                ],
                proxy={"server": "http://per-context"},
                slow_mo=50,
            )
        except PlaywrightError as e:
            raise _nice_net_error(e)

        try:
            context_kwargs: Dict[str, Any] = {"proxy": proxy or {"server": "direct"}}
            if session_path:
                context_kwargs["storage_state"] = str(session_path)

            try:
                context = await browser.new_context(**context_kwargs)
                page = await context.new_page()
                await page.goto(TARGET_URL)
                await page.wait_for_load_state("domcontentloaded")
            except PlaywrightError as e:
                raise _nice_net_error(e)

            await _ensure_no_auth_modal_or_raise(page, session_path)
            editor = await find_editor(page)

            try:
                await editor.scroll_into_view_if_needed()
                await editor.click(timeout=10_000)
                await page.keyboard.insert_text(build_prompt(req_dict))
                await page.keyboard.press("Enter")
                result = await handle_after_enter(page, req_dict, screen_path)
            except PlaywrightTimeoutError:
                await _ensure_no_auth_modal_or_raise(page, session_path)
                raise
            except PlaywrightError as e:
                raise _nice_net_error(e)
        finally:
            await browser.close()

    return to_query_response(result, int((time.time() - start) * 1000))


async def handle_gpt_chat_parse_batch(req: BatchQueryRequest) -> BatchQueryResponse:
    if req.source != "gpt_chat_parse":
        raise ValueError("handle_gpt_chat_parse_batch ожидает source='gpt_chat_parse'")

    start = time.time()
    sem = asyncio.Semaphore(req.concurrency)

    async def _one(q: str) -> ItemResult:
        async with sem:
            try:
                single = QueryRequest(query=q, geo=req.geo, target=req.target, source=req.source, options=req.options)
                return ItemResult(query=q, response=await handle_gpt_chat_parse(single))
            except Exception as e:
                return ItemResult(query=q, error=str(e) or e.__class__.__name__)

    results = await asyncio.gather(*(_one(q) for q in req.queries))
    return BatchQueryResponse(results=list(results), timings_ms={"total": int((time.time() - start) * 1000)})
