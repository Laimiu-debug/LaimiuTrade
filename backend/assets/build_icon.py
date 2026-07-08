"""从 icon.png 生成 Windows .ico（多尺寸）。"""

from pathlib import Path

from PIL import Image

ASSETS = Path(__file__).resolve().parent
SRC = ASSETS / "icon.png"
OUT = ASSETS / "icon.ico"

SIZES = [(16, 16), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)]


def main() -> None:
    img = Image.open(SRC).convert("RGBA")
    img.save(OUT, format="ICO", sizes=SIZES)
    print(f"generated {OUT}")


if __name__ == "__main__":
    main()
