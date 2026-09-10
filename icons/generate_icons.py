"""
Generate extension icons (16x16, 48x48, 128x128) from the source JPG.
Run once after setup: python generate_icons.py
Requires: pip install Pillow
"""
import os
from PIL import Image

SRC = os.path.join(os.path.dirname(__file__), "icon_source.jpg")
OUT_DIR = os.path.join(os.path.dirname(__file__), "..", "extension", "icons")

os.makedirs(OUT_DIR, exist_ok=True)

sizes = [16, 48, 128]

img = Image.open(SRC).convert("RGBA")

for size in sizes:
    resized = img.resize((size, size), Image.LANCZOS)
    out_path = os.path.join(OUT_DIR, f"icon{size}.png")
    resized.save(out_path, "PNG")
    print(f"✅ Saved {out_path}")

print("Done! Icons ready.")
