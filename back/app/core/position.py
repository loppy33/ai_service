import re
from typing import Any, Dict, Iterable, Optional, Tuple
from urllib.parse import urlparse

import tldextract

FLAG_NAMES = (
    "matched_exact_url",
    "matched_url_prefix",
    "matched_registrable_domain",
    "matched_brand",
)


def normalize_url(u: Any) -> str:
    s = "" if u is None else str(u).strip().lower()
    s = re.sub(r"^https?://", "", s)
    if s.startswith("www."):
        s = s[4:]
    s = s.split("#", 1)[0]
    return s.rstrip("/")


def host_only(url_or_host: Any) -> str:
    s = "" if url_or_host is None else str(url_or_host).strip()
    if not s:
        return ""
    try:
        host = urlparse(s).netloc if "://" in s else s
    except ValueError:
        host = s
    return host.split("@")[-1].split("/")[0].split(":")[0].strip().lower()


def registered_domain(url_or_host: Any) -> Optional[str]:
    host = host_only(url_or_host)
    if not host:
        return None
    if host.startswith("www."):
        host = host[4:]
    ext = tldextract.extract(host)
    if ext.domain and ext.suffix:
        return f"{ext.domain}.{ext.suffix}"
    return ext.domain or ext.suffix or host


def _target_field(target: Any, name: str) -> str:
    value = target.get(name) if isinstance(target, dict) else getattr(target, name, None)
    return str(value or "").strip()


def _brand_matches(brand: str, haystack: str) -> bool:
    return bool(re.search(rf"(^|\W){re.escape(brand)}(\W|$)", haystack))


def _is_path_prefix(prefix: str, value: str) -> bool:
    return value == prefix or value.startswith(prefix + "/") or value.startswith(prefix + "?")


def compute_flags_and_position(citations: Iterable[Dict[str, Any]], target: Any) -> Tuple[Optional[int], Dict[str, bool]]:
    flags = {name: False for name in FLAG_NAMES}

    target_url = _target_field(target, "url")
    target_domain = _target_field(target, "domain")
    brand = _target_field(target, "brand").lower()

    target_url_norm = normalize_url(target_url) if target_url else None
    target_reg = registered_domain(target_domain) if target_domain else None
    if not target_reg and target_url:
        target_reg = registered_domain(target_url)

    for idx, c in enumerate(citations, start=1):
        url = str(c.get("url") or "")
        title = str(c.get("title") or "")
        url_norm = normalize_url(url)

        if target_url_norm and url_norm == target_url_norm:
            flags["matched_exact_url"] = True
            return idx, flags
        if target_url_norm and _is_path_prefix(target_url_norm, url_norm):
            flags["matched_url_prefix"] = True
            return idx, flags
        if target_reg and registered_domain(url) == target_reg:
            flags["matched_registrable_domain"] = True
            return idx, flags
        if brand and (_brand_matches(brand, url_norm) or _brand_matches(brand, title.lower())):
            flags["matched_brand"] = True
            return idx, flags

    return None, flags
