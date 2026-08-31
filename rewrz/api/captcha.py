"""
验证码API模块

提供验证码的生成和验证功能。
"""
from fastapi import APIRouter, Request, Response
from fastapi.responses import StreamingResponse
from PIL import Image, ImageDraw, ImageFont
import random
import io

router = APIRouter()

# 验证码专用字体：仅包含 CAPTCHA_CHAR_SET 字符的思源黑体子集（约 12KB），
# 由 scripts/build_captcha_font.py 生成；字符集调整后需重新生成
FONT_PATH = 'rewrz/static/fonts/captcha-sourcehansans.otf'

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

def get_random_color():
    """获取一个随机颜色 (R, G, B)"""
    return (random.randint(0, 150), random.randint(0, 150), random.randint(0, 150))

def generate_captcha_image_upgraded(text):
    """生成一个更安全的验证码图片"""
    width, height = 150, 60
    # 使用随机背景色，避免纯白背景
    image = Image.new('RGB', (width, height), color=(random.randint(200, 255), random.randint(200, 255), random.randint(200, 255)))
    
    try:
        font = ImageFont.truetype(FONT_PATH, 36)
    except IOError:
        # 如果字体文件不存在，提供一个备用方案或清晰的错误
        print(f"错误：字体文件未在 '{FONT_PATH}' 找到。")
        # 在实际应用中，这里应该有更健壮的错误处理
        # 为演示目的，我们创建一个不带文字的图像
        font = ImageFont.load_default()

    d = ImageDraw.Draw(image)

    # 逐个绘制字符，并添加随机变换
    char_width = width / len(text)
    for i, char in enumerate(text):
        # 为每个字符应用随机的位置抖动
        x = int(char_width * i + random.randint(0, 10))
        y = random.randint(-5, 5)
        
        # 创建一个单独的透明图层来旋转字符
        char_image = Image.new('RGBA', (50, 50))
        char_draw = ImageDraw.Draw(char_image)
        char_draw.text((0, 0), char, font=font, fill=get_random_color())
        
        # 随机旋转
        char_image = char_image.rotate(random.randint(-20, 20), expand=1, resample=Image.BICUBIC)
        
        # 将旋转后的字符粘贴回主图片
        image.paste(char_image, (x, y), char_image)

    # 添加更复杂的干扰：噪点
    for _ in range(100):
        d.point((random.randint(0, width), random.randint(0, height)), fill=get_random_color())
        
    # 添加干扰线
    for _ in range(3):
        d.line([(random.randint(0, width), random.randint(0, height)),
                (random.randint(0, width), random.randint(0, height))], fill=get_random_color(), width=1)

    img_byte_arr = io.BytesIO()
    image.save(img_byte_arr, format='PNG')
    img_byte_arr = img_byte_arr.getvalue()
    return img_byte_arr

# --- 在你的FastAPI路由中这样使用 ---
@router.get("/api/v1/captcha")
async def get_captcha(request: Request):
    """生成并返回验证码图片"""
    # 使用一个大的、安全的字符集
    captcha_text = ''.join(random.sample(CAPTCHA_CHAR_SET, k=4))
    
    request.session['captcha'] = captcha_text
    
    # 调用升级版的生成函数
    image_bytes = generate_captcha_image_upgraded(captcha_text)
    
    return StreamingResponse(io.BytesIO(image_bytes), media_type="image/png")