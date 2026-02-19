import hashlib
from typing import Optional, Union


ANIME_GIRL_NAME_POOL = [
    "绫波丽",
    "明日香",
    "初音未来",
    "雷姆",
    "蕾姆",
    "五更琉璃",
    "时崎狂三",
    "立华奏",
    "亚丝娜",
    "御坂美琴",
    "中野三玖",
    "中野二乃",
    "雪之下雪乃",
    "千反田爱瑠",
    "椎名真白",
    "约尔",
    "四宫辉夜",
    "可可萝",
    "七海千秋",
    "洛天依",
]


def _stable_index(seed_value: Union[str, int], total: int) -> int:
    digest = hashlib.sha256(str(seed_value).encode("utf-8")).hexdigest()
    return int(digest[:8], 16) % max(1, total)


def resolve_public_display_name(
    display_name: Optional[str],
    *,
    seed_value: Optional[Union[str, int]] = None,
    fallback: str = "博主",
) -> str:
    clean_name = str(display_name or "").strip()
    if clean_name:
        return clean_name

    if seed_value is None:
        return fallback

    return ANIME_GIRL_NAME_POOL[_stable_index(seed_value, len(ANIME_GIRL_NAME_POOL))]
