from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter


ROOT_DIR = Path(__file__).resolve().parents[1]
ASSETS_DIR = ROOT_DIR / "assets"
PNG_PATH = ASSETS_DIR / "emulation-work.png"
ICO_PATH = ASSETS_DIR / "emulation-work.ico"


def create_gradient(size: int) -> Image.Image:
    image = Image.new("RGBA", (size, size))
    pixels = image.load()
    for y in range(size):
        blend = y / max(1, size - 1)
        top = (16, 71, 99)
        bottom = (7, 25, 40)
        r = int(top[0] * (1 - blend) + bottom[0] * blend)
        g = int(top[1] * (1 - blend) + bottom[1] * blend)
        b = int(top[2] * (1 - blend) + bottom[2] * blend)
        for x in range(size):
            pixels[x, y] = (r, g, b, 255)
    return image


def rounded_panel(draw: ImageDraw.ImageDraw, size: int) -> None:
    margin = int(size * 0.09)
    draw.rounded_rectangle(
        (margin, margin, size - margin, size - margin),
        radius=int(size * 0.18),
        fill=(242, 248, 251, 255),
    )


def monitor(draw: ImageDraw.ImageDraw, size: int) -> None:
    screen = (
        int(size * 0.19),
        int(size * 0.20),
        int(size * 0.81),
        int(size * 0.61),
    )
    draw.rounded_rectangle(screen, radius=int(size * 0.05), fill=(22, 44, 60, 255))
    draw.rounded_rectangle(
        (screen[0] + int(size * 0.025), screen[1] + int(size * 0.025), screen[2] - int(size * 0.025), screen[3] - int(size * 0.025)),
        radius=int(size * 0.04),
        fill=(29, 120, 167, 255),
    )
    draw.rectangle((int(size * 0.44), int(size * 0.61), int(size * 0.56), int(size * 0.72)), fill=(22, 44, 60, 255))
    draw.rounded_rectangle(
        (int(size * 0.34), int(size * 0.71), int(size * 0.66), int(size * 0.77)),
        radius=int(size * 0.03),
        fill=(22, 44, 60, 255),
    )


def cursor(draw: ImageDraw.ImageDraw, size: int) -> None:
    points = [
        (int(size * 0.56), int(size * 0.34)),
        (int(size * 0.40), int(size * 0.76)),
        (int(size * 0.52), int(size * 0.70)),
        (int(size * 0.59), int(size * 0.84)),
        (int(size * 0.68), int(size * 0.80)),
        (int(size * 0.61), int(size * 0.67)),
        (int(size * 0.73), int(size * 0.64)),
    ]
    draw.polygon(points, fill=(255, 255, 255, 255))
    draw.line(points + [points[0]], fill=(13, 31, 44, 255), width=max(2, size // 48))


def accent_spark(draw: ImageDraw.ImageDraw, size: int) -> None:
    x = int(size * 0.71)
    y = int(size * 0.27)
    color = (255, 213, 79, 255)
    arm = int(size * 0.05)
    draw.line((x - arm, y, x + arm, y), fill=color, width=max(2, size // 64))
    draw.line((x, y - arm, x, y + arm), fill=color, width=max(2, size // 64))


def add_glow(image: Image.Image, size: int) -> Image.Image:
    glow = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(glow)
    draw.ellipse(
        (int(size * 0.10), int(size * 0.08), int(size * 0.90), int(size * 0.88)),
        fill=(88, 189, 255, 70),
    )
    glow = glow.filter(ImageFilter.GaussianBlur(radius=size // 18))
    return Image.alpha_composite(image, glow)


def build_master_icon(size: int = 512) -> Image.Image:
    image = create_gradient(size)
    image = add_glow(image, size)
    draw = ImageDraw.Draw(image)
    rounded_panel(draw, size)
    monitor(draw, size)
    cursor(draw, size)
    accent_spark(draw, size)
    return image


def main() -> None:
    ASSETS_DIR.mkdir(parents=True, exist_ok=True)
    master = build_master_icon()
    master.save(PNG_PATH)
    master.save(ICO_PATH, sizes=[(256, 256), (128, 128), (64, 64), (48, 48), (32, 32), (16, 16)])
    print(f"Saved {PNG_PATH}")
    print(f"Saved {ICO_PATH}")


if __name__ == "__main__":
    main()
