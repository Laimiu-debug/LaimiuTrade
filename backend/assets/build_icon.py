"""从熊 logo 源图生成各处所需图标。

产物：
  frontend/public/logo.png     网页 logo（圆角白底，512）
  frontend/public/favicon.png  浏览器标签（256）
  backend/assets/icon.png      托盘/打包（圆角，512）
  backend/assets/icon.ico      Windows exe 图标（多尺寸）

源图：backend/assets/icon_new.jpg（用户提供）
"""

from pathlib import Path

from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parents[2]
SRC = Path(__file__).resolve().parent / "icon_new.jpg"
PUB = ROOT / "frontend" / "public"
ASSETS = Path(__file__).resolve().parent


def rounded(img: Image.Image, radius: float) -> Image.Image:
    """给图片加圆角遮罩，保留 alpha。"""
    img = img.convert("RGBA")
    mask = Image.new("L", img.size, 0)
    d = ImageDraw.Draw(mask)
    d.rounded_rectangle([0, 0, img.size[0] - 1, img.size[1] - 1], radius=radius, fill=255)
    out = Image.new("RGBA", img.size, (0, 0, 0, 0))
    out.paste(img, (0, 0), mask)
    return out


def fit_on_background(src: Image.Image, size: int, bg) -> Image.Image:
    """源图按 contain 缩放到 size，居中铺在 bg 背景上。"""
    canvas = Image.new("RGBA", (size, size), bg)
    s = src.convert("RGBA")
    ratio = (size * 0.92) / max(s.size)
    new_w, new_h = int(s.size[0] * ratio), int(s.size[1] * ratio)
    s2 = s.resize((new_w, new_h), Image.Resampling.LANCZOS)
    off = ((size - new_w) // 2, (size - new_h) // 2)
    canvas.paste(s2, off, s2)
    return canvas


def main() -> None:
    if not SRC.exists():
        raise SystemExit(f"源图不存在：{SRC}")
    src = Image.open(SRC)
    print(f"source: {src.size} {src.mode}")

    PUB.mkdir(parents=True, exist_ok=True)

    # 网页 logo：圆角白底（在浅色/深色页面上都干净）
    logo = rounded(fit_on_background(src, 512, (255, 255, 255, 255)), radius=96)
    logo.save(PUB / "logo.png", format="PNG")
    print(f"generated {PUB / 'logo.png'}")

    # favicon：圆角白底小图
    fav = rounded(fit_on_background(src, 256, (255, 255, 255, 255)), radius=52)
    fav.save(PUB / "favicon.png", format="PNG")
    print(f"generated {PUB / 'favicon.png'}")

    # 托盘/打包 icon.png：圆角透明底（随系统主题）
    icon = rounded(fit_on_background(src, 512, (245, 240, 230, 255)), radius=96)
    icon.save(ASSETS / "icon.png", format="PNG")
    print(f"generated {ASSETS / 'icon.png'}")

    # Windows .ico：多尺寸
    ico_sizes = [(16, 16), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)]
    icon.save(ASSETS / "icon.ico", format="ICO", sizes=ico_sizes)
    print(f"generated {ASSETS / 'icon.ico'}")


if __name__ == "__main__":
    main()
