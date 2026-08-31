"""验证码字体构建脚本：从完整版思源黑体生成验证码专用子集。

验证码字符集固定为 rewrz/api/captcha.py 中的 CAPTCHA_CHAR_SET（约 55 个汉字），
仅子集化这些字符输出 CFF 格式 OTF（PIL/FreeType 可直接加载），体积约 12KB。

维护约定：
- 调整 captcha.py 的 CAPTCHA_CHAR_SET 后必须重新执行本脚本；
- 完整版字体不随仓库分发，如需重建请先从上游获取思源黑体 Medium OTF，
  或从 git 历史（font-subset 引入前的提交）找回 rewrz/static/fonts/SourceHanSansCN-Medium.otf。

用法：.venv\\Scripts\\python.exe scripts\\build_captcha_font.py
"""

from pathlib import Path

from fontTools import subset

ROOT = Path(__file__).resolve().parents[1]
CAPTCHA_CHARS = (
    "乾坤震巽坎离艮兑甲乙丙丁子丑寅卯金木水火土"
    "道气阴阳魂魄神魔鬼妖仙缘劫命"
    "萌燃絆契傲娇詠唱圣剑姬翼梦幻欧非氪肝"
)

options = subset.Options()
options.layout_features = ["*"]
options.hinting = False
options.desubroutinize = True


def main() -> None:
    source = ROOT / "rewrz" / "static" / "fonts" / "SourceHanSansCN-Medium.otf"
    if not source.is_file():
        raise SystemExit(
            f"未找到完整版字体 {source}；请按本文件顶部说明获取后再执行"
        )
    font = subset.load_font(source, options)
    subsetter = subset.Subsetter(options)
    subsetter.populate(text=CAPTCHA_CHARS)
    subsetter.subset(font)
    subset.save_font(
        font,
        ROOT / "rewrz" / "static" / "fonts" / "captcha-sourcehansans.otf",
        options,
    )
    print("验证码字体生成完成，字符数:", len(set(CAPTCHA_CHARS)))


if __name__ == "__main__":
    main()
