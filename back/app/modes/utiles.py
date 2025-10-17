import asyncio
import html
import json
import random
import re
import time
from pathlib import Path
from typing import Any, Dict, List, Optional
from html import unescape
from urllib.parse import urlsplit, urlunsplit, parse_qsl, urlencode, urlparse
import yaml
from playwright.async_api import async_playwright
from app.api.schemas import QueryRequest, QueryResponse, Citation, Render
from app.core.position import match_position as core_match_position
from app.api.schemas import Target

# optional: корректное определение зарегистрированного домена по PSL
try:
    import tldextract  # type: ignore
except Exception:
    tldextract = None

# === Константы ===
TARGET_URL = "https://chat.openai.com/"
STATIC_ROOT = Path("app/data")
ASSISTANT_SEL = "div[data-message-author-role='assistant']"
CONFIG_PATH = Path("app/config/mod_templates.yaml")  # ← путь к конфигу
ALLOWED_TAGS = r"(h[1-6]|p|ul|ol|li|a|code|pre|blockquote|hr)"
SKIP_DOMAINS = ("images.openai.com", "chat.openai.com", ".onion")
COMMON_PSL_3 = {
    # AU
    "com.au", "net.au", "org.au", "gov.au", "edu.au", "asn.au", "id.au",
    # UK / NZ
    "co.uk", "ac.uk", "gov.uk", "org.uk", "co.nz", "org.nz", "gov.nz", "ac.nz",
    # BR / MX
    "com.br", "com.mx",
    # JP
    "co.jp", "ac.jp", "go.jp", "or.jp", "ne.jp",
    # Others common
    "co.in", "co.za", "co.kr", "co.id", "com.sg"
}

# --- Загрузка шаблонов ---

def _load_templates() -> Dict[str, str]:
    """
    Загружает шаблоны модификации запроса из YAML:
      templates.none
      templates.geo_only
      templates.lang_only
      templates.geo_and_lang
    """
    try:
        with open(CONFIG_PATH, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
        t = (data.get("templates") or {})
        return {
            "none": t.get("none", "%Query%"),
            "geo_only": t.get("geo_only", "%Query%"),
            "lang_only": t.get("lang_only", "%Query%"),
            "geo_and_lang": t.get("geo_and_lang", "%Query%"),
        }
    except Exception:
        # На случай отсутствия файла — дефолты из ТЗ
        return {
            "none": "%Query%",
            "geo_only": "%Query%. Answer as if I am in %GEO%, but don't add this info to answer",
            "lang_only": "%Query%. Answer as if my language is %Lang%, but don't add this info to answer",
            "geo_and_lang": "%Query%. Answer as if I am in %GEO% and my language is %Lang%, but don't add this info to answer",
        }

def _apply_template(query: str, geo: Optional[str], lang: Optional[str]) -> str:
    """
    Подставляет query в один из шаблонов, исходя из наличия GEO/языка.
    GEO и язык берём из req.geo / req.geo.language (или близких полей).
    """
    templates = _load_templates()
    geo = (geo or "").strip()
    lang = (lang or "").strip()

    tpl = templates["geo_and_lang"] if (geo and lang) else templates["geo_only"] if geo else templates["lang_only"] if lang else templates["none"]

    # если шаблон содержит точку сразу после %Query%, подменим её на %SEP%
    tpl = tpl.replace("%Query%.", "%Query%%SEP%")

    q = (query or "").strip()
    # если query уже оканчивается на пунктуацию — точку не добавляем
    needs_dot = bool(q) and q[-1] not in ".!?…"
    sep = "." if needs_dot else ""

    return (
        tpl
        .replace("%Query%", q)
        .replace("%GEO%", geo)
        .replace("%Lang%", lang)
        .replace("%SEP%", sep)  # если в шаблоне нет %SEP%, replace ничего не меняет
    )

# === Утилиты ===
def _fs_path_to_static_url(p: str | Path | None) -> str | None:
    """Конвертирует путь в /static/... чтобы его можно было отдавать через Flask."""
    if not p:
        return None
    p = Path(p)
    try:
        rel = p.resolve().relative_to(STATIC_ROOT.resolve())
        return f"/static/{rel.as_posix()}"
    except Exception:
        # если файл вне STATIC_ROOT — вернём имя, чтобы не сломать схему
        return f"/static/{p.name}"


def to_query_response(result: Dict[str, Any], duration_ms: int) -> QueryResponse:
    """Собирает Pydantic-ответ из словаря результата."""
    # 1) citations -> List[Citation]
    citations_pyd: List[Citation] = []
    for c in (result.get("citations") or []):
        if isinstance(c, dict) and c.get("url"):
            citations_pyd.append(
                Citation(
                    url=str(c["url"]),
                    title=(c.get("title") or None),
                )
            )

    # 2) render
    render_src = result.get("render") or {}
    raw_payload = render_src.get("raw_payload") or {}
    if not isinstance(raw_payload, dict):
        raw_payload = {"html": str(raw_payload)}

    screenshot_fs = render_src.get("screenshot_url") or None
    screenshot_url = _fs_path_to_static_url(screenshot_fs)
    
    if isinstance(screenshot_url, str) and screenshot_url:
        full_screenshot_url = f"http://127.0.0.1:8000{screenshot_url}"
    else:
        full_screenshot_url = None

    render = Render(
        screenshot_url=full_screenshot_url,
        raw_payload=raw_payload,
    )

    # 3) position
    pos = result.get("position")
    if not isinstance(pos, (int, type(None))):
        pos = None

    return QueryResponse(
        position=pos,
        answer=str(result.get("answer") or ""),
        citations=citations_pyd,
        render=render,
        timings_ms={"total": int(duration_ms)},
    )

async def find_editor(page):
    candidates = [
        "#prompt-textarea",
        "div#prompt-textarea[contenteditable='true']",
        "div.ProseMirror[contenteditable='true']",
        "div[contenteditable='true'][data-virtualkeyboard='true']",
        "textarea"
    ]
    for sel in candidates:
        el = page.locator(sel).first
        try:
            await el.wait_for(state="visible", timeout=5_000)
            if await el.is_editable():
                return el
        except Exception:
            pass
    raise RuntimeError("Не удалось найти поле ввода промпта.")

def build_prompt(req: Dict[str, Any]) -> str:
    """
    НОВЫЙ билдер: только модификация %Query% через конфиг.
    Никаких инструкций про возврат JSON.
    """
    q = req.get("query", "") or ""
    geo_obj = (req.get("geo") or {})  # может быть строкой/объектом
    # Попробуем разумно вытащить GEO и язык
    geo_str = ""
    lang_str = ""

    if isinstance(geo_obj, dict):
        # варианты названий:
        geo_str = geo_obj.get("country") or geo_obj.get("location") or geo_obj.get("geo") or ""
        lang_str = geo_obj.get("language") or geo_obj.get("lang") or ""
    elif isinstance(geo_obj, str):
        geo_str = geo_obj

    # Дополнительно: иногда язык могут класть отдельно
    lang_str = lang_str or (req.get("language") or req.get("lang") or "")

    return _apply_template(q, geo_str, lang_str)

def _ensure_scheme(u: str) -> str:
    if re.match(r"^https?://", u, re.I):
        return u
    # не добавляем схему к email
    if "@" in u and not u.lower().startswith(("http://", "https://")):
        return u
    return f"https://{u.lstrip('/')}"

def _normalize_url_keep_scheme(u: str) -> str:
    """Убираем utm_* и пустяки, но оставляем схему/хост/путь."""
    try:
        sp = urlsplit(u)
        if not sp.scheme:
            # иногда прилетает без схемы — добавим https для единообразия
            sp = sp._replace(scheme="https")
        # фильтруем трекинг
        q = [(k, v) for (k, v) in parse_qsl(sp.query, keep_blank_values=True)
             if not k.lower().startswith("utm_")]
        new_q = urlencode(q)
        return urlunsplit((sp.scheme, sp.netloc, sp.path, new_q, ""))
    except Exception:
        return u

FULL_URL_RE = re.compile(r"(https?://[^\s<>\]\)\"']+)", re.I)

# домен без схемы + опциональный путь
NAKED_DOMAIN_RE = re.compile(
    r"""(?<!@)                                  # не email
        \b((?:[a-z0-9-]+\.)+[a-z]{2,})          # домен второго уровня и выше
        (/[^\s<>\)]*)?                          # опциональный путь
    """,
    re.I | re.X,
)

_TRAILING = ".,);]»”'"

def _balanced_parens(s: str) -> bool:
    # простенькая проверка на баланс круглых скобок
    cnt = 0
    for ch in s:
        if ch == "(":
            cnt += 1
        elif ch == ")":
            cnt -= 1 if cnt else 0
    return cnt == 0

def _rstrip_punct(u: str) -> str:
    # осторожно убираем явную хвостовую пунктуацию
    while u and u[-1] in _TRAILING:
        # если это закрывающая скобка, не трогаем, когда скобки несбалансированы
        if u[-1] == ")" and not _balanced_parens(u):
            break
        u = u[:-1]
    # не обрезаем финальную точку, если перед ней совсем короткий сегмент пути: /a. или /go.
    if u.endswith("."):
        m = re.search(r"/([A-Za-z0-9]{1,2})\.$", u)
        if not m:
            u = u[:-1]
    return u

def _host_only(url_or_host: str) -> str:
    """Возвращает hostname (без порта/юзер-инфо), в нижнем регистре."""
    if not url_or_host:
        return ""
    s = str(url_or_host).strip()
    try:
        host = urlparse(s).netloc if "://" in s else s
    except Exception:
        host = s
    host = host.split("@")[-1].split("/")[0].split(":")[0].strip().lower()
    return host

def _registered_domain(url_or_host: str | None) -> str | None:
    """Корректный registrable domain: tldextract → фолбэк."""
    host = _host_only(url_or_host or "")
    if not host:
        return None
    if tldextract:
        ext = tldextract.extract(host)  # (subdomain, domain, suffix)
        if ext.domain and ext.suffix:
            return f"{ext.domain}.{ext.suffix}"
        if ext.suffix:
            return ext.suffix
        if ext.domain:
            return ext.domain
        return host
    parts = [p for p in host.split(".") if p]
    if not parts:
        return None
    if len(parts) <= 2:
        return ".".join(parts)
    last2 = ".".join(parts[-2:])
    if last2 in COMMON_PSL_3:
        return ".".join(parts[-3:])
    return last2

def extract_urls(text: str) -> list[str]:
    """
    Достаёт ссылки из обычного текста:
      - https?://...
      - голые домены и домены с путём: example.com, www.site.net/path
    Возвращает нормализованные URL с сохранением порядка и без дублей.
    """
    if not text:
        return []

    urls: list[str] = []

    # 1) полноценные http(s) ссылки
    full_re = re.compile(r"(https?://[^\s<>\]\)\"']+)", re.I)
    for m in full_re.finditer(text):
        raw = m.group(1)
        u = _rstrip_punct(raw)
        u = _normalize_url_keep_scheme(u)
        low = u.lower()
        if low.startswith(("mailto:", "javascript:", "data:", "#")):
            continue
        if _domain(u).endswith(SKIP_DOMAINS):
            continue
        urls.append(u)

    # 2) «голые» домены и домены с путём (без схемы)
    for m in NAKED_DOMAIN_RE.finditer(text):
        dom = m.group(1)
        path = m.group(2) or ""
        candidate = _ensure_scheme(dom + path)  # добавим https://
        candidate = _rstrip_punct(candidate)
        candidate = _normalize_url_keep_scheme(candidate)
        if _domain(candidate).endswith(SKIP_DOMAINS):
            continue
        urls.append(candidate)

    # Уникализация с сохранением порядка
    out, seen = [], set()
    for u in urls:
        if u and u not in seen:
            seen.add(u)
            out.append(u)
    return out

async def handle_after_enter(page, req: Dict[str, Any], screen_path: Path) -> Dict[str, Any]:
    await page.wait_for_selector(ASSISTANT_SEL, timeout=120_000)
    await wait_for_final_message(page)

    assistant_blocks = page.locator(ASSISTANT_SEL)
    count = await assistant_blocks.count()
    last = assistant_blocks.nth(count - 1)

    # Берём именно markdown-контент
    markdown = last.locator(".markdown").first
    if await markdown.count() > 0:
        raw_html = await markdown.inner_html()
        content_html = sanitize_markdown_html(raw_html)  # ← чистим
        content_text = strip_html_to_text(content_html)  # ← читаемый текст без мусора
    else:
        # Fallback
        raw_html = await last.inner_html()
        content_html = sanitize_markdown_html(raw_html)
        content_text = strip_html_to_text(content_html)

    raw_html = await markdown.inner_html() if await markdown.count() > 0 else await last.inner_html()
    content_html = sanitize_markdown_html(raw_html)
    content_text = strip_html_to_text(content_html)
    text_urls = extract_urls(content_text)
    html_urls = extract_urls_from_html(raw_html)
    urls = list(dict.fromkeys([*text_urls, *html_urls]))
    norm_citations = [{"url": u, "title": ""} for u in urls]

    screen_path.parent.mkdir(parents=True, exist_ok=True)
    last = page.locator(ASSISTANT_SEL).last
    await last.scroll_into_view_if_needed()
    await page.screenshot(path=str(screen_path), full_page=True)

    position = resolve_position(norm_citations, req.get("target") or {})

    return {
        "position": position,
        "answer": content_text.strip(),   # чистый человекочитаемый текст
        "citations": norm_citations,
        "render": {
            "screenshot_url": str(screen_path),
            "raw_payload": {"html": content_html},  # уже очищенный HTML markdown-а
        },
    }

def sanitize_markdown_html(html: str) -> str:
    if not html:
        return ""
    s = html
    # 1) Вырезаем явные виджеты/пилюли
    s = re.sub(r'(?is)<div[^>]+data-testid="products-widget"[^>]*>.*?</div>', "", s)
    s = re.sub(r'(?is)<span[^>]+data-testid="webpage-citation-pill"[^>]*>.*?</span>', "", s)
    # 2) Удаляем скрипты/стили
    s = re.sub(r'(?is)<(script|style)[^>]*>.*?</\1>', "", s)
    # 3) Удаляем картинки
    s = re.sub(r'(?is)<img[^>]*>', "", s)
    # 4) Спаны разворачиваем
    s = re.sub(r'(?is)</?span[^>]*>', "", s)
    # 5) div -> переносы
    s = re.sub(r'(?is)</?div[^>]*>', "\n", s)

    # 6) Чистим атрибуты у разрешённых тегов, но у <a> оставляем href
    def _strip_attrs(m):
        tag = m.group(1).lower()
        attrs = m.group(0)
        if tag == "a":
            # забираем только href="..."
            href = re.search(r'href\s*=\s*(".*?"|\'.*?\'|[^\s>]+)', attrs, flags=re.I)
            return f'<a href={href.group(1)}>' if href else '<a>'
        return f'<{tag}>'

    s = re.sub(rf'(?is)<({ALLOWED_TAGS})\s+[^>]*>', _strip_attrs, s)

    # 7) Удаляем теги вне белого списка
    s = re.sub(rf'(?is)</?(?!{ALLOWED_TAGS})\w+[^>]*>', "", s)
    # 8) Схлопываем переносы
    s = re.sub(r'\n{3,}', '\n\n', s)
    return s.strip()

def strip_html_to_text(html: str) -> str:
    if not html:
        return ""

    s = html
    # Блочные — перенос
    s = re.sub(r'(?i)</(p|div|h[1-6]|ul|ol|hr|blockquote)>', '\n', s)
    s = re.sub(r'(?i)<br\s*/?>', '\n', s)

    # Списки
    s = re.sub(r'(?i)<li[^>]*>\s*', '- ', s)
    s = re.sub(r'(?i)</li>', '\n', s)

    # Ссылки: текст + (URL)
    def _a_sub(m):
        href = m.group(1)
        inner = re.sub(r'<[^>]+>', '', m.group(2) or '').strip()
        return f"{inner} ({href})" if href else inner

    s = re.sub(r'(?is)<a[^>]+href="([^"]+)"[^>]*>(.*?)</a>', _a_sub, s)

    # Снять оставшиеся теги
    s = re.sub(r'<[^>]+>', '', s)

    s = unescape(s)
    s = re.sub(r'\n{3,}', '\n\n', s)
    return s.strip()



def clean_links_and_html(text: str) -> str:
    if not text:
        return text
    text = re.sub(r"<br\s*/?>", "\n", text, flags=re.I)
    text = re.sub(r'<a[^>]*href="([^"]+)"[^>]*>.*?</a>', r"\1", text, flags=re.I | re.S)
    text = unescape(text)
    text = re.sub(r'\s*data-[\w-]+="[^"]*"', "", text)
    return text.strip()


def extract_json_from_assistant_text(text: str) -> Dict[str, Any]:
    """Достаёт JSON из текста с возможным ```json ... ``` забором."""
    fenced = re.search(r"```(?:json)?\s*(.+?)\s*```", text, flags=re.S | re.I)
    raw = fenced.group(1) if fenced else text
    raw = clean_links_and_html(raw)
    return json.loads(raw)


async def wait_for_final_message(page):
    import hashlib
    MIN_ELAPSED = 4.0     # было 3.0
    stable_ticks = 0
    target_stable = 10    # было 6
    last_hash = ""
    start = time.time()

    for _ in range(160):  # чуть больше итераций
        blocks = page.locator(ASSISTANT_SEL)
        cnt = await blocks.count()
        last = blocks.nth(cnt - 1)

        # хэш всего HTML
        cur_html = await last.inner_html()
        cur_hash = hashlib.md5(cur_html.encode("utf-8")).hexdigest()

        # дополнительная проверка: считаем кол-во ссылок с href
        a_with_href = await last.locator(".markdown a[href]").count()

        await page.wait_for_timeout(1000)

        # после паузы снова считаем; если растёт количество ссылок — еще рендерится
        a_with_href2 = await last.locator(".markdown a[href]").count()
        links_stable = (a_with_href2 == a_with_href)

        if cur_hash == last_hash and (time.time() - start) >= MIN_ELAPSED and links_stable:
            stable_ticks += 1
            if stable_ticks >= target_stable:
                break
        else:
            stable_ticks = 0
            last_hash = cur_hash


def _normalize_url(u) -> str:
    s = "" if u is None else str(u)
    s = s.strip().lower()
    s = re.sub(r"^https?://", "", s)
    s = re.sub(r"^www\.", "", s)
    s = s.rstrip("/")
    return s


class _SimpleCitation:
    """Простая обёртка с полями-строками для core_match_position."""
    def __init__(self, url: str, title: str = ""):
        self.url = str(url) if url is not None else ""
        self.title = str(title) if title is not None else ""

def _to_simple_citations(citations_list):
    out = []
    for c in citations_list or []:
        if isinstance(c, dict):
            url = c.get("url") or ""
            title = c.get("title") or ""
            if isinstance(url, str) and url:
                out.append(_SimpleCitation(url, title))
    return out

def _normalize_url_simple(url: str) -> str:
    """Нормализация для точного/префиксного сравнения: без схемы и www, без фрагмента, без трейлинга."""
    u = (url or "").strip().lower()
    u = re.sub(r"^https?://", "", u)
    if u.startswith("www."):
        u = u[4:]
    if "#" in u:
        u = u.split("#", 1)[0]
    while u.endswith("/") and len(u) > 1:
        u = u[:-1]
    return u

def _domain(u: str) -> str:
    try:
        return urlsplit(u).netloc.lower()
    except Exception:
        return ""

def _compute_flags_and_position(citations_list, target):
    """
    Возвращает (position:int|None, flags:dict), где flags:
    - matched_exact_url
    - matched_url_prefix
    - matched_registrable_domain
    - matched_brand
    Совпадает по приоритету с _local_position.
    """
    flags = {
        "matched_exact_url": False,
        "matched_url_prefix": False,
        "matched_registrable_domain": False,
        "matched_brand": False,
    }
    if not citations_list:
        return None, flags

    target_url = str(getattr(target, "url", "") or "").strip()
    target_dom = str(getattr(target, "domain", "") or "").strip()
    brand = (str(getattr(target, "brand", "") or "").strip().lower()) or None

    target_url_norm = _normalize_url_simple(target_url) if target_url else None
    target_reg_dom = _registered_domain(target_dom) if target_dom else None

    for idx, c in enumerate(citations_list, start=1):
        url = str(c.get("url", "") or "")
        title = str(c.get("title", "") or "")
        url_norm = _normalize_url_simple(url)
        dom = _registered_domain(url)

        if target_url_norm and url_norm == target_url_norm:
            flags["matched_exact_url"] = True
            return idx, flags
        if target_url_norm and (url_norm.startswith(target_url_norm) or target_url_norm.startswith(url_norm)):
            flags["matched_url_prefix"] = True
            return idx, flags
        if target_reg_dom and dom == target_reg_dom:
            flags["matched_registrable_domain"] = True
            return idx, flags
        if brand:
            title_l = title.lower()
            if re.search(rf"(^|\W){re.escape(brand)}(\W|$)", url_norm) or re.search(rf"(^|\W){re.escape(brand)}(\W|$)", title_l):
                flags["matched_brand"] = True
                return idx, flags

    return None, flags

def _local_position(citations_list, target_any) -> int | None:
    """
    Фолбэк-правила:
      1) точный URL
      2) начинается с target.url (или наоборот)
      3) registered-домен
      4) brand в URL/титле (по слову)
    """
    if not citations_list:
        return None

    # аккуратно достаём поля из dict или Pydantic-модели
    def _get(attr):
        if hasattr(target_any, attr):
            return getattr(target_any, attr)
        if isinstance(target_any, dict):
            return target_any.get(attr)
        return None

    target_url = str(_get("url") or "").strip()
    target_dom = str(_get("domain") or "").strip()
    brand = (str(_get("brand") or "").strip().lower()) or None

    target_url_norm = _normalize_url_simple(target_url) if target_url else None
    target_reg_dom = _registered_domain(target_dom) if target_dom else None

    for idx, c in enumerate(citations_list, start=1):
        url = str(c.get("url", "") or "")
        title = str(c.get("title", "") or "")
        url_norm = _normalize_url_simple(url)
        dom = _registered_domain(url)

        if target_url_norm and url_norm == target_url_norm:
            return idx
        if target_url_norm and (url_norm.startswith(target_url_norm) or target_url_norm.startswith(url_norm)):
            return idx
        if target_reg_dom and dom == target_reg_dom:
            return idx
        if brand:
            title_l = title.lower()
            if re.search(rf"(^|\W){re.escape(brand)}(\W|$)", url_norm) or re.search(rf"(^|\W){re.escape(brand)}(\W|$)", title_l):
                return idx
    return None

def resolve_position(citations: list[dict[str, str]], target: dict | Target) -> int | None:
    """
    Единообразно пытаемся через core.position.match_position.
    Если что-то не так (валидация/исключение/None) — используем локальные правила.
    """
    # 1) основной путь — core
    try:
        simple = _to_simple_citations(citations)
        tgt: Target | None = None
        if isinstance(target, Target):
            tgt = target
        elif isinstance(target, dict):
            # мягкая валидация: пустые поля отсекаем, чтобы не падать на HttpUrl
            payload = {}
            for k in ("url", "domain", "brand"):
                v = target.get(k)
                if v:
                    payload[k] = v
            if payload:
                tgt = Target.model_validate(payload)
        if tgt is not None:
            pos = core_match_position(simple, tgt)
            if isinstance(pos, int):
                return pos
    except Exception:
        pass

    # 2) фолбэк
    return _local_position(citations, target)

def parse_proxy(line: str) -> Optional[Dict[str, Any]]:
    if not line:
        return None
    parts = line.strip().split(":")
    if len(parts) < 2:
        return None
    host, port = parts[0], parts[1]
    if not port.isdigit():
        return None

    server = f"http://{host}:{port}"
    if len(parts) == 4:
        username, password = parts[2], parts[3]
        return {"server": server, "username": username, "password": password}
    elif len(parts) == 2:
        return {"server": server}
    else:
        return None


def choose_proxy(proxy_list: List[str]) -> Optional[Dict[str, Any]]:
    for line in proxy_list or []:
        p = parse_proxy(line)
        if p:
            return p
    return None

def extract_urls_from_html(html: str) -> list[str]:
    if not html:
        return []
    urls = []

    # href="...", href='...', href=bare
    href_re = re.compile(
        r'(?is)<a\b[^>]*\bhref\s*=\s*(?:"([^"]*)"|\'([^\']*)\'|([^\s>]+))'
    )

    for m in href_re.finditer(html):
        raw = (m.group(1) or m.group(2) or m.group(3) or "").strip()
        if not raw:
            continue

        # отбрасываем не-URL схемы
        low = raw.lower()
        if low.startswith(("mailto:", "javascript:", "data:", "#")):
            continue

        u = _rstrip_punct(raw)
        u = _normalize_url_keep_scheme(u)
        if _domain(u).endswith(SKIP_DOMAINS):
            continue

        urls.append(u)

    # уникализация с сохранением порядка
    out, seen = [], set()
    for u in urls:
        if u not in seen:
            seen.add(u)
            out.append(u)
    return out
