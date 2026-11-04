"""
验证码API模块

提供验证码的生成和验证功能。
"""
from fastapi import APIRouter, Request
from fastapi.responses import PlainTextResponse, StreamingResponse
from PIL import Image, ImageDraw, ImageFont
import io
import secrets
import threading
import time
from collections import defaultdict, deque
from pathlib import Path

from ..core.admin_security import get_client_ip

router = APIRouter()

# 验证码专用字体：仅包含 CAPTCHA_CHAR_SET 字符的思源黑体子集（约 12KB），
# 由 scripts/build_captcha_font.py 生成；字符集调整后需重新生成。
# 使用绝对路径，避免服务进程工作目录变化时回退到不含中文字形的默认字体，
# 导致验证码显示成方块（移动端尤其明显）。
FONT_PATH = str(Path(__file__).resolve().parents[1] / "static" / "fonts" / "captcha-sourcehansans.otf")

# 融合了玄学、易经、二次元风格的自定义字符集
CAPTCHA_CHAR_SET = (
    # --- 玄学 & 易经系列 ---
    # 八卦 + 天干地支 + 五行
    "乾坤震巽坎离艮兑甲乙丙丁子丑寅卯金木水火土"
    # --- 概念 & 精神系列 ---
    # 道家思想 + ACG常见精神内核
    "道气阴阳魂魄神魔鬼妖仙缘劫命"
    # --- 二次元 & 幻想系列 ---
    # 经典概念 + 游戏黑话 + 常见元素
    "萌燃絆契傲娇詠唱圣剑姬翼梦幻欧非氪肝"
)

# 验证码图片按 IP 限流，避免被高频请求拖垮图片渲染 CPU。
_CAPTCHA_RATE_LIMIT_PER_MIN = 40
_CAPTCHA_RATE_BUCKETS = defaultdict(deque)
_CAPTCHA_RATE_LOCK = threading.Lock()
_CAPTCHA_RATE_LAST_PRUNE = 0.0


def _is_captcha_rate_limited(ip_address: str) -> bool:
    global _CAPTCHA_RATE_LAST_PRUNE
    now_ts = time.time()
    with _CAPTCHA_RATE_LOCK:
        # 定期清理长时间无访问的 IP 桶，避免伪造来源撑大内存（512MB 机器需控制常驻开销）
        if now_ts - _CAPTCHA_RATE_LAST_PRUNE >= 60:
            stale_keys = [
                key for key, bucket in _CAPTCHA_RATE_BUCKETS.items()
                if not bucket or now_ts - bucket[-1] >= 120
            ]
            for key in stale_keys:
                _CAPTCHA_RATE_BUCKETS.pop(key, None)
            _CAPTCHA_RATE_LAST_PRUNE = now_ts

        bucket = _CAPTCHA_RATE_BUCKETS[ip_address]
        while bucket and now_ts - bucket[0] >= 60:
            bucket.popleft()
        if len(bucket) >= _CAPTCHA_RATE_LIMIT_PER_MIN:
            return True
        bucket.append(now_ts)
        return False


def get_random_color():
    """获取一个随机颜色 (R, G, B)"""
    return (secrets.randbelow(151), secrets.randbelow(151), secrets.randbelow(151))


def generate_captcha_image_upgraded(text):
    """生成一个更安全的验证码图片"""
    width, height = 150, 60
    # 使用随机背景色，避免纯白背景
    image = Image.new(
        'RGB',
        (width, height),
        color=(
            secrets.randbelow(56) + 200,
            secrets.randbelow(56) + 200,
            secrets.randbelow(56) + 200,
        ),
    )

    font = None
    try:
        font = ImageFont.truetype(FONT_PATH, 36)
    except OSError:
        # 字体缺失时回退默认字体，仅用于保证接口可用；生产环境应保证字体文件存在。
        print(f"错误：字体文件未在 '{FONT_PATH}' 找到。")
        font = ImageFont.load_default()

    d = ImageDraw.Draw(image)

    # 逐个绘制字符，并添加随机变换
    char_width = width / len(text)
    for i, char in enumerate(text):
        # 为每个字符应用随机的位置抖动
        x = int(char_width * i + secrets.randbelow(11))
        y = secrets.randbelow(11) - 5

        # 创建一个单独的透明图层来旋转字符
        char_image = Image.new('RGBA', (50, 50))
        char_draw = ImageDraw.Draw(char_image)
        char_draw.text((0, 0), char, font=font, fill=get_random_color())

        # 随机旋转
        char_image = char_image.rotate(secrets.randbelow(41) - 20, expand=1, resample=Image.BICUBIC)

        # 将旋转后的字符粘贴回主图片
        image.paste(char_image, (x, y), char_image)

    # 添加更复杂的干扰：噪点
    for _ in range(100):
        d.point(
            (secrets.randbelow(width + 1), secrets.randbelow(height + 1)),
            fill=get_random_color(),
        )

    # 添加干扰线
    for _ in range(3):
        d.line(
            [
                (secrets.randbelow(width + 1), secrets.randbelow(height + 1)),
                (secrets.randbelow(width + 1), secrets.randbelow(height + 1)),
            ],
            fill=get_random_color(),
            width=1,
        )

    img_byte_arr = io.BytesIO()
    image.save(img_byte_arr, format='PNG')
    return img_byte_arr.getvalue()


@router.get("/api/v1/captcha")
def get_captcha(request: Request):
    """生成并返回验证码图片。"""
    if _is_captcha_rate_limited(get_client_ip(request)):
        return PlainTextResponse(
            "验证码请求过于频繁，请稍后再试",
            status_code=429,
            headers={"Retry-After": "60", "Cache-Control": "no-store"},
        )

    captcha_text = "".join(secrets.choice(CAPTCHA_CHAR_SET) for _ in range(4))

    # 只保留最新一次验证码，避免旧验证码长期留在会话里被复用。
    request.session['captcha'] = captcha_text

    image_bytes = generate_captcha_image_upgraded(captcha_text)

    return StreamingResponse(
        io.BytesIO(image_bytes),
        media_type="image/png",
        headers={
            "Cache-Control": "no-store, no-cache, must-revalidate",
            "Pragma": "no-cache",
            "Expires": "0",
        },
    )
