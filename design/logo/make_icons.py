"""Pack design/logo/png/*.png into installer/LACUNA.ico (Windows shortcut) and installer/LACUNA.icns (LACUNA.app)."""
from pathlib import Path
from PIL import Image

png = Path("design/logo/png")
big = Image.open(png / "logo_1024.png").convert("RGBA")
ico_imgs = [Image.open(png / f"logo_{s}.png").convert("RGBA") for s in (16, 24, 32, 48, 64, 128, 256)]
ico_imgs[-1].save("installer/LACUNA.ico", sizes=[i.size for i in ico_imgs], append_images=ico_imgs[:-1])
big.save("installer/LACUNA.icns")
print("ok")
