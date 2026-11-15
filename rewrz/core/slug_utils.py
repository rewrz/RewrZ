"""slug 生成工具：在保留点号的同时复用项目现有的拼音与规范化规则。"""

from slugify import slugify


def slugify_with_dots(value: str) -> str:
    """生成允许点号的 slug。

    python-slugify 默认会把 ``.`` 替换成 ``-``，但版本号（v1.2）、
    域名式标题（Node.js）需要保留点号。这里按点号分段分别规范化，
    再重新拼接，并折叠空段与连续点。
    """
    raw_value = str(value or "").strip()
    if not raw_value:
        return ""

    parts = [slugify(part) for part in raw_value.split(".")]
    normalized = ".".join(part for part in parts if part).strip(".")
    while ".." in normalized:
        normalized = normalized.replace("..", ".")
    return normalized or slugify(raw_value)
