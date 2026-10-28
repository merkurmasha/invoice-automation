"""Turns a handful of the generated invoice PDFs into "phone photo" JPEGs.

Pipeline: pymupdf renders the PDF's first page to a bitmap (this is why
pymupdf is a dependency - reportlab can only write PDFs, not images).
Pillow then degrades that bitmap to look like a quick phone snapshot:
a slight rotation, an uneven shadow from one corner, lower contrast, a
touch of blur, and JPEG compression artifacts.
"""
from __future__ import annotations

import random
from pathlib import Path

import pymupdf
from PIL import Image, ImageChops, ImageEnhance, ImageFilter

PHOTO_SEED_OFFSET = 9001
RENDER_DPI = 200


def _shadow_mask(width: int, height: int, rng: random.Random) -> Image.Image:
    """Builds a low-res radial darkening mask (darker near one random
    corner) and scales it up, so the gradient looks smooth and cheap to
    compute instead of looping over every full-resolution pixel."""
    small = 24
    corner = rng.choice([(0, 0), (small - 1, 0), (0, small - 1), (small - 1, small - 1)])
    cx, cy = corner
    max_dist = ((small - 1) ** 2 + (small - 1) ** 2) ** 0.5
    darkness = rng.uniform(55, 90)

    base = Image.new("L", (small, small), 255)
    pixels = base.load()
    for y in range(small):
        for x in range(small):
            dist = ((x - cx) ** 2 + (y - cy) ** 2) ** 0.5
            falloff = 1 - (dist / max_dist)
            pixels[x, y] = int(255 - darkness * falloff)
    return base.resize((width, height), Image.BICUBIC).convert("RGB")


def pdf_to_phone_photo(pdf_path: Path, output_path: Path, seed: int) -> None:
    rng = random.Random(seed)
    doc = pymupdf.open(str(pdf_path))
    page = doc[0]
    pix = page.get_pixmap(dpi=RENDER_DPI)
    img = Image.frombytes("RGB", (pix.width, pix.height), pix.samples)
    doc.close()

    angle = rng.uniform(-4.0, 4.0)
    img = img.rotate(angle, expand=True, fillcolor=(238, 236, 230), resample=Image.BICUBIC)

    shadow = _shadow_mask(img.width, img.height, rng)
    img = ImageChops.multiply(img, shadow)

    img = ImageEnhance.Contrast(img).enhance(rng.uniform(0.65, 0.8))
    img = ImageEnhance.Brightness(img).enhance(rng.uniform(0.92, 1.0))
    img = img.filter(ImageFilter.GaussianBlur(radius=rng.uniform(0.6, 1.3)))

    output_path.parent.mkdir(parents=True, exist_ok=True)
    img.convert("RGB").save(str(output_path), "JPEG", quality=rng.randint(35, 55))
