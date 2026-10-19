import hashlib
import random
import re
import time
from html import unescape
from pathlib import Path
from typing import Any, Dict, List, Optional
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

import yaml

from app.api.schemas import Citation, QueryResponse, Render
from app.core.config import PUBLIC_BASE_URL, SCREENSHOTS_DIR, TEMPLATES_PATH
from app.core.position import compute_flags_and_position

ASSISTANT_SEL = "div[data-message-author-role='assistant']"
ALLOWED_TAGS = r"(h[1-6]|p|ul|ol|li|a|code|pre|blockquote|hr)"
SKIP_DOMAINS = ("images.openai.com", "chat.openai.com", "chatgpt.com", "oaistatic.com", ".onion")
FILE_EXTENSIONS = {
    "txt", "js", "ts", "py", "json", "md", "png", "jpg", "jpeg", "gif", "svg", "pdf", "css", "html", "htm",
    "xml", "csv", "zip", "exe", "dll", "yaml", "yml", "sh", "php", "jsx", "tsx", "doc", "docx", "xls", "xlsx",
}
TRAILING_PUNCT = ".,);]»”'"
DEFAULT_TEMPLATES = {
    "none": "%Query%",
    "geo_only": "%Query%. Answer as if I am in %GEO%, but don't add this info to answer",
    "lang_only": "%Query%. Answer as if my language is %Lang%, but don't add this info to answer",
    "geo_and_lang": "%Query%. Answer as if I am in %GEO% and my language is %Lang%, but don't add this info to answer",
}

FULL_URL_RE = re.compile(r"https?://[^\s<>\]\)\"']+", re.I)
NAKED_DOMAIN_RE = re.compile(
    r"""(?<![@\w.-])
        ((?:[a-z0-9-]+\.)+[a-z]{2,})
        (/[^\s<>\)]*)?
    """,
    re.I | re.X,
)
HREF_RE = re.compile(r'(?is)<a\b[^>]*\bhref\s*=\s*(?:"([^"]*)"|\'([^\']*)\'|([^\s>]+))')


def _load_templates() -> Dict[str, str]:
    try:
        with open(TEMPLATES_PATH, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
        loaded = data.get("templates") or {}
        return {key: loaded.get(key, default) for key, default in DEFAULT_TEMPLATES.items()}
    except (OSError, yaml.YAMLError):
        return dict(DEFAULT_TEMPLATES)


def _apply_template(query: str, geo: Optional[str], lang: Optional[str]) -> str:
    templates = _load_templates()
    geo = (geo or "").strip()
    lang = (lang or "").strip()

    if geo and lang:
        tpl = templates["geo_and_lang"]
    elif geo:
        tpl = templates["geo_only"]
    elif lang:
        tpl = templates["lang_only"]
    else:
        tpl = templates["none"]

    tpl = tpl.replace("%Query%.", "%Query%%SEP%")
    q = (query or "").strip()
    sep = "." if q and q[-1] not in ".!?…" else ""

    return tpl.replace("%Query%", q).replace("%GEO%", geo).replace("%Lang%", lang).replace("%SEP%", sep)


def build_prompt(req: Dict[str, Any]) -> str:
    geo_obj = req.get("geo") or {}
    geo_str = ""
    lang_str = ""

    if isinstance(geo_obj, dict):
        geo_str = geo_obj.get("country") or geo_obj.get("location") or geo_obj.get("geo") or ""
        lang_str = geo_obj.get("language") or geo_obj.get("lang") or ""
    elif isinstance(geo_obj, str):
        geo_str = geo_obj

    lang_str = lang_str or req.get("language") or req.get("lang") or ""
    return _apply_template(req.get("query", "") or "", geo_str, lang_str)


def _fs_path_to_static_url(p: str | Path | None) -> str | None:
    if not p:
        return None
    path = Path(p)
    try:
        rel = path.resolve().relative_to(SCREENSHOTS_DIR.resolve())
        return f"/static/{rel.as_posix()}"
    except ValueError:
        return f"/static/{path.name}"


def to_query_response(result: Dict[str, Any], duration_ms: int) -> QueryResponse:
    citations: List[Citation] = [
        Citation(url=str(c["url"]), title=(c.get("title") or None))
        for c in (result.get("citations") or [])
        if isinstance(c, dict) and c.get("url")
    ]

    render_src = result.get("render") or {}
    raw_payload = render_src.get("raw_payload") or {}
    if not isinstance(raw_payload, dict):
        raw_payload = {"html": str(raw_payload)}

    static_url = _fs_path_to_static_url(render_src.get("screenshot_url"))
    screenshot_url = f"{PUBLIC_BASE_URL}{static_url}" if static_url else None

    pos = result.get("position")
    if not isinstance(pos, int):
        pos = None

    return QueryResponse(
        position=pos,
        answer=str(result.get("answer") or ""),
        citations=citations,
        render=Render(screenshot_url=screenshot_url, raw_payload=raw_payload),
        timings_ms={"total": int(duration_ms)},
    )


def _domain(u: str) -> str:
    try:
        return urlsplit(u).netloc.lower()
    except ValueError:
        return ""


def _is_skipped(u: str) -> bool:
    return _domain(u).endswith(SKIP_DOMAINS)


def _ensure_scheme(u: str) -> str:
    if re.match(r"^https?://", u, re.I):
        return u
    return f"https://{u.lstrip('/')}"


def _normalize_url_keep_scheme(u: str) -> str:
    try:
        sp = urlsplit(u)
        if not sp.scheme:
            sp = sp._replace(scheme="https")
        query = [(k, v) for k, v in parse_qsl(sp.query, keep_blank_values=True) if not k.lower().startswith("utm_")]
        return urlunsplit((sp.scheme, sp.netloc, sp.path, urlencode(query), ""))
    except ValueError:
        return u


def _balanced_parens(s: str) -> bool:
    depth = 0
    for ch in s:
        if ch == "(":
            depth += 1
        elif ch == ")" and depth:
            depth -= 1
    return depth == 0


def _rstrip_punct(u: str) -> str:
    while u and u[-1] in TRAILING_PUNCT:
        if u[-1] == ")" and not _balanced_parens(u):
            break
        u = u[:-1]
    return u


def _dedupe(items: List[str]) -> List[str]:
    return list(dict.fromkeys(i for i in items if i))


def extract_urls(text: str) -> List[str]:
    if not text:
        return []

    urls: List[str] = []

    for m in FULL_URL_RE.finditer(text):
        u = _normalize_url_keep_scheme(_rstrip_punct(m.group(0)))
        if u.lower().startswith(("mailto:", "javascript:", "data:", "#")) or _is_skipped(u):
            continue
        urls.append(u)

    remainder = FULL_URL_RE.sub(" ", text)
    for m in NAKED_DOMAIN_RE.finditer(remainder):
        host = m.group(1)
        if host.rsplit(".", 1)[-1].lower() in FILE_EXTENSIONS:
            continue
        candidate = _normalize_url_keep_scheme(_rstrip_punct(_ensure_scheme(host + (m.group(2) or ""))))
        if not _is_skipped(candidate):
            urls.append(candidate)

    return _dedupe(urls)


def extract_urls_from_html(html: str) -> List[str]:
    if not html:
        return []

    urls: List[str] = []
    for m in HREF_RE.finditer(html):
        raw = (m.group(1) or m.group(2) or m.group(3) or "").strip()
        if not raw or raw.lower().startswith(("mailto:", "javascript:", "data:", "#")):
            continue
        u = _normalize_url_keep_scheme(_rstrip_punct(raw))
        if not _is_skipped(u):
            urls.append(u)
    return _dedupe(urls)


def sanitize_markdown_html(html: str) -> str:
    if not html:
        return ""
    s = html
    s = re.sub(r'(?is)<div[^>]+data-testid="products-widget"[^>]*>.*?</div>', "", s)
    s = re.sub(r'(?is)<span[^>]+data-testid="webpage-citation-pill"[^>]*>.*?</span>', "", s)
    s = re.sub(r"(?is)<(script|style)[^>]*>.*?</\1>", "", s)
    s = re.sub(r"(?is)<img[^>]*>", "", s)
    s = re.sub(r"(?is)</?span[^>]*>", "", s)
    s = re.sub(r"(?is)</?div[^>]*>", "\n", s)

    def _strip_attrs(m):
        tag = m.group(1).lower()
        if tag == "a":
            href = re.search(r'href\s*=\s*(".*?"|\'.*?\'|[^\s>]+)', m.group(0), flags=re.I)
            return f"<a href={href.group(1)}>" if href else "<a>"
        return f"<{tag}>"

    s = re.sub(rf"(?is)<({ALLOWED_TAGS})\s+[^>]*>", _strip_attrs, s)
    s = re.sub(rf"(?is)</?(?!{ALLOWED_TAGS}\b)[a-z][\w-]*(?:\s[^>]*)?>", "", s)
    s = re.sub(r"\n{3,}", "\n\n", s)
    return s.strip()


def strip_html_to_text(html: str) -> str:
    if not html:
        return ""

    s = re.sub(r"(?i)</(p|div|h[1-6]|ul|ol|hr|blockquote)>", "\n", html)
    s = re.sub(r"(?i)<br\s*/?>", "\n", s)
    s = re.sub(r"(?i)<li[^>]*>\s*", "- ", s)
    s = re.sub(r"(?i)</li>", "\n", s)

    def _a_sub(m):
        href = m.group(1)
        inner = re.sub(r"<[^>]+>", "", m.group(2) or "").strip()
        return f"{inner} ({href})" if href else inner

    s = re.sub(r'(?is)<a[^>]+href="([^"]+)"[^>]*>(.*?)</a>', _a_sub, s)
    s = re.sub(r"<[^>]+>", "", s)
    s = unescape(s)
    s = re.sub(r"\n{3,}", "\n\n", s)
    return s.strip()


async def find_editor(page):
    candidates = [
        "#prompt-textarea",
        "div#prompt-textarea[contenteditable='true']",
        "div.ProseMirror[contenteditable='true']",
        "div[contenteditable='true'][data-virtualkeyboard='true']",
        "textarea",
    ]
    for sel in candidates:
        el = page.locator(sel).first
        try:
            await el.wait_for(state="visible", timeout=5_000)
            if await el.is_editable():
                return el
        except Exception:
            continue
    raise RuntimeError("Не удалось найти поле ввода промпта.")


async def wait_for_final_message(page):
    min_elapsed = 4.0
    target_stable = 10
    stable_ticks = 0
    last_hash = ""
    start = time.time()

    for _ in range(160):
        blocks = page.locator(ASSISTANT_SEL)
        cnt = await blocks.count()
        if cnt == 0:
            await page.wait_for_timeout(1000)
            continue
        last = blocks.nth(cnt - 1)

        cur_hash = hashlib.md5((await last.inner_html()).encode("utf-8")).hexdigest()
        links_before = await last.locator(".markdown a[href]").count()
        await page.wait_for_timeout(1000)
        links_after = await last.locator(".markdown a[href]").count()

        if cur_hash == last_hash and (time.time() - start) >= min_elapsed and links_before == links_after:
            stable_ticks += 1
            if stable_ticks >= target_stable:
                return
        else:
            stable_ticks = 0
            last_hash = cur_hash


async def handle_after_enter(page, req: Dict[str, Any], screen_path: Path) -> Dict[str, Any]:
    await page.wait_for_selector(ASSISTANT_SEL, timeout=120_000)
    await wait_for_final_message(page)

    last = page.locator(ASSISTANT_SEL).last
    markdown = last.locator(".markdown").first
    raw_html = await markdown.inner_html() if await markdown.count() > 0 else await last.inner_html()

    content_html = sanitize_markdown_html(raw_html)
    content_text = strip_html_to_text(content_html)
    urls = _dedupe([*extract_urls(content_text), *extract_urls_from_html(raw_html)])
    citations = [{"url": u, "title": ""} for u in urls]

    screen_path.parent.mkdir(parents=True, exist_ok=True)
    await last.scroll_into_view_if_needed()
    await page.screenshot(path=str(screen_path), full_page=True)

    position, flags = compute_flags_and_position(citations, req.get("target") or {})

    return {
        "position": position,
        "answer": content_text.strip(),
        "citations": citations,
        "render": {
            "screenshot_url": str(screen_path),
            "raw_payload": {"html": content_html, "flags": flags},
        },
    }


def parse_proxy(line: str) -> Optional[Dict[str, Any]]:
    parts = (line or "").strip().split(":")
    if len(parts) not in (2, 4) or not parts[1].isdigit():
        return None
    proxy: Dict[str, Any] = {"server": f"http://{parts[0]}:{parts[1]}"}
    if len(parts) == 4:
        proxy["username"], proxy["password"] = parts[2], parts[3]
    return proxy


def choose_proxy(proxy_list: List[str]) -> Optional[Dict[str, Any]]:
    valid = [p for p in (parse_proxy(line) for line in proxy_list or []) if p]
    return random.choice(valid) if valid else None
