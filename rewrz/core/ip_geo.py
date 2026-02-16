import ipaddress
import json
import threading
import time
from typing import Dict, List, Optional
from urllib import error, parse, request


_CACHE_LOCK = threading.Lock()
_IP_GEO_CACHE: Dict[str, tuple[float, str]] = {}
_CACHE_TTL_SECONDS = 24 * 60 * 60

_ZH_TOKEN_MAP = {
    "China": "中国",
    "United States": "美国",
    "United Kingdom": "英国",
    "Japan": "日本",
    "Korea, Republic of": "韩国",
    "South Korea": "韩国",
    "North Korea": "朝鲜",
    "Singapore": "新加坡",
    "Hong Kong": "中国香港",
    "Taiwan": "中国台湾",
    "Macao": "中国澳门",
    "Germany": "德国",
    "France": "法国",
    "Italy": "意大利",
    "Spain": "西班牙",
    "Russia": "俄罗斯",
    "Canada": "加拿大",
    "Australia": "澳大利亚",
    "New Zealand": "新西兰",
    "India": "印度",
    "Brazil": "巴西",
    "Mexico": "墨西哥",
    "Netherlands": "荷兰",
    "Sweden": "瑞典",
    "Norway": "挪威",
    "Finland": "芬兰",
    "Denmark": "丹麦",
    "Switzerland": "瑞士",
    "Austria": "奥地利",
    "Ireland": "爱尔兰",
    "Belgium": "比利时",
    "Poland": "波兰",
    "Ukraine": "乌克兰",
    "Turkey": "土耳其",
    "Indonesia": "印度尼西亚",
    "Thailand": "泰国",
    "Vietnam": "越南",
    "Malaysia": "马来西亚",
    "Philippines": "菲律宾",
    "澳大利亞": "澳大利亚",
    "紐西蘭": "新西兰",
    "韓國": "韩国",
    "中國": "中国",
    "臺灣": "中国台湾",
    "香港": "中国香港",
    "澳門": "中国澳门",
    "Queensland": "昆士兰州",
    "New South Wales": "新南威尔士州",
    "Victoria": "维多利亚州",
    "California": "加利福尼亚州",
    "Virginia": "弗吉尼亚州",
    "Tokyo": "东京都",
    "Ashburn": "阿什本",
    "South Brisbane": "南布里斯班",
    "Los Angeles": "洛杉矶",
    "San Francisco": "旧金山",
    "New York": "纽约",
}


def _normalize_ip(raw_ip: str) -> str:
    text = (raw_ip or "").strip()
    if not text:
        return ""
    if "," in text:
        text = text.split(",")[0].strip()
    return text


def _is_non_public_ip(ip_text: str) -> tuple[bool, str]:
    try:
        ip_obj = ipaddress.ip_address(ip_text)
    except ValueError:
        return True, "IP格式异常"

    if ip_obj.is_loopback:
        return True, "本地回环地址"
    if ip_obj.is_private:
        return True, "内网地址"
    if ip_obj.is_multicast:
        return True, "组播地址"
    if ip_obj.is_reserved:
        return True, "保留地址"
    if ip_obj.is_unspecified:
        return True, "未指定地址"
    return False, ""


def _safe_join(parts: List[str]) -> str:
    return "-".join([part for part in parts if part and part.strip()])


def _to_zh_token(token: str) -> str:
    text = (token or "").strip()
    if not text:
        return ""
    return _ZH_TOKEN_MAP.get(text, text)


def _fetch_json(url: str, timeout: float = 2.5) -> Optional[dict]:
    req = request.Request(url, headers={"User-Agent": "RewrZ-IPGeo/1.0"})
    try:
        with request.urlopen(req, timeout=timeout) as resp:
            data = resp.read().decode("utf-8", errors="ignore")
            return json.loads(data)
    except (error.URLError, error.HTTPError, TimeoutError, ValueError, json.JSONDecodeError):
        return None


def _lookup_ipwhois(ip_text: str) -> Optional[str]:
    url = f"https://ipwho.is/{parse.quote(ip_text)}?lang=zh"
    payload = _fetch_json(url)
    if not payload or payload.get("success") is False:
        return None

    location = _safe_join([
        _to_zh_token(str(payload.get("country") or "")),
        _to_zh_token(str(payload.get("region") or "")),
        _to_zh_token(str(payload.get("city") or "")),
    ])
    isp = str(payload.get("connection", {}).get("isp") or "").strip()
    if location and isp:
        return f"{location} ({isp})"
    return location or None


def _lookup_ip_api(ip_text: str) -> Optional[str]:
    # ip-api 免费接口仅支持 HTTP，作为回退来源使用
    fields = "status,country,regionName,city,district,isp,message"
    url = f"http://ip-api.com/json/{parse.quote(ip_text)}?lang=zh-CN&fields={fields}"
    payload = _fetch_json(url)
    if not payload or payload.get("status") != "success":
        return None

    location = _safe_join([
        _to_zh_token(str(payload.get("country") or "")),
        _to_zh_token(str(payload.get("regionName") or "")),
        _to_zh_token(str(payload.get("city") or "")),
        _to_zh_token(str(payload.get("district") or "")),
    ])
    isp = str(payload.get("isp") or "").strip()
    if location and isp:
        return f"{location} ({isp})"
    return location or None


def lookup_ip_location(raw_ip: str) -> str:
    ip_text = _normalize_ip(raw_ip)
    if not ip_text:
        return ""

    non_public, reason = _is_non_public_ip(ip_text)
    if non_public:
        return reason

    now = time.time()
    with _CACHE_LOCK:
        cached = _IP_GEO_CACHE.get(ip_text)
        if cached and now - cached[0] < _CACHE_TTL_SECONDS:
            return cached[1]

    # 优先使用支持中文的来源
    location = _lookup_ip_api(ip_text) or _lookup_ipwhois(ip_text) or "位置未知"
    with _CACHE_LOCK:
        _IP_GEO_CACHE[ip_text] = (now, location)
    return location


def lookup_ip_locations(raw_ips: List[str]) -> Dict[str, str]:
    result: Dict[str, str] = {}
    unique_ips = []
    seen = set()
    for item in raw_ips:
        normalized = _normalize_ip(item)
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        unique_ips.append(normalized)

    # 避免一次请求过多IP导致等待过长
    for ip_text in unique_ips[:80]:
        result[ip_text] = lookup_ip_location(ip_text)
    return result
