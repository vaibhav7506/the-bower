from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw, ImageFont, ImageOps


PROJECT_ROOT = Path(__file__).resolve().parents[1]
IMAGE_ROOT = PROJECT_ROOT / "static" / "img"
WEBP_QUALITY = 82

RESPONSIVE_IMAGES = {
    "hero-graded.png": (480, 960, 1600),
    "texture-pendant.png": (480, 960, 1600),
    "texture-carpet.png": (480, 960, 1600),
    "menu/garden-pea-veloute.png": (320, 500),
    "menu/ember-roasted-beetroot.png": (320, 500),
    "menu/ricotta-gnudi.png": (320, 500),
    "menu/charred-cauliflower.png": (320, 500),
    "menu/market-fish.png": (320, 500),
    "menu/lamb-shoulder.png": (320, 500),
    "menu/dark-chocolate-cremeux.png": (320, 500),
    "menu/poached-pear.png": (320, 500),
}


def display_font(size: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    font_path = PROJECT_ROOT / "static" / "fonts" / "fraunces-latin.woff2"
    try:
        return ImageFont.truetype(str(font_path), size=size)
    except OSError:
        return ImageFont.load_default(size=size)


def body_font(size: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    font_path = PROJECT_ROOT / "static" / "fonts" / "inter-latin.woff2"
    try:
        return ImageFont.truetype(str(font_path), size=size)
    except OSError:
        return ImageFont.load_default(size=size)


def build_responsive_images() -> None:
    for relative_path, widths in RESPONSIVE_IMAGES.items():
        source_path = IMAGE_ROOT / relative_path
        with Image.open(source_path) as source:
            source = source.convert("RGB")
            for width in widths:
                output_width = min(width, source.width)
                output_height = round(source.height * output_width / source.width)
                resized = source.resize((output_width, output_height), Image.Resampling.LANCZOS)
                output_path = source_path.with_name(f"{source_path.stem}-{width}.webp")
                resized.save(output_path, "WEBP", quality=WEBP_QUALITY, method=6)


def build_open_graph_image() -> None:
    with Image.open(IMAGE_ROOT / "hero-graded.png") as source:
        canvas = ImageOps.fit(
            source.convert("RGB"),
            (1200, 630),
            method=Image.Resampling.LANCZOS,
            centering=(0.58, 0.5),
        ).convert("RGBA")

    overlay = Image.new("RGBA", canvas.size, (0, 0, 0, 0))
    overlay_draw = ImageDraw.Draw(overlay)
    for x in range(760):
        alpha = round(220 * (1 - x / 760) ** 1.7)
        overlay_draw.line((x, 0, x, 630), fill=(20, 38, 27, alpha))
    canvas = Image.alpha_composite(canvas, overlay)

    draw = ImageDraw.Draw(canvas)
    brass = "#d4ad70"
    cream = "#f4ede0"
    draw.text((76, 92), "B", font=display_font(124), fill=brass)
    draw.ellipse((150, 82, 173, 100), outline=brass, width=3)
    draw.line((151, 101, 177, 76), fill=brass, width=3)
    draw.text((78, 258), "THE BOWER", font=display_font(70), fill=cream)
    draw.line((80, 352, 360, 352), fill=brass, width=3)
    draw.text(
        (80, 385),
        "A quiet table, made memorable.",
        font=body_font(30),
        fill=cream,
    )

    output_path = IMAGE_ROOT / "og-bower.jpg"
    canvas.convert("RGB").save(output_path, "JPEG", quality=88, optimize=True, progressive=True)


if __name__ == "__main__":
    build_responsive_images()
    build_open_graph_image()
    print("Responsive WebP variants and the Open Graph image are ready.")
