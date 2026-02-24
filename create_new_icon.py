"""Create clean simplified brain icon - black and white only."""

from pathlib import Path
from PIL import Image, ImageDraw

def create_brain_icon():
    """Create a clean, simplified black/white brain icon."""
    size = 256
    image = Image.new('RGBA', (size, size), (255, 255, 255, 0))
    dc = ImageDraw.Draw(image)

    scale = 4

    # Main brain outline - white fill, thick black border
    dc.ellipse([16*scale, 12*scale, 48*scale, 52*scale],
               fill='white', outline='black', width=8)

    # Central fissure (vertical line dividing hemispheres)
    dc.line([32*scale, 14*scale, 32*scale, 50*scale], fill='black', width=6)

    # LEFT HEMISPHERE - simplified clean curves (fewer, thicker lines)
    # Top curve
    dc.arc([18*scale, 16*scale, 30*scale, 26*scale], start=200, end=340, fill='black', width=5)

    # Middle curve
    dc.arc([18*scale, 28*scale, 30*scale, 38*scale], start=200, end=340, fill='black', width=5)

    # Bottom curve
    dc.arc([18*scale, 40*scale, 30*scale, 50*scale], start=200, end=340, fill='black', width=5)

    # RIGHT HEMISPHERE - mirror curves
    # Top curve
    dc.arc([34*scale, 16*scale, 46*scale, 26*scale], start=200, end=340, fill='black', width=5)

    # Middle curve
    dc.arc([34*scale, 28*scale, 46*scale, 38*scale], start=200, end=340, fill='black', width=5)

    # Bottom curve
    dc.arc([34*scale, 40*scale, 46*scale, 50*scale], start=200, end=340, fill='black', width=5)

    # Save as NEW filename to bypass cache
    icon_path = str(Path(__file__).parent / "pilot_icon_new.ico")

    sizes = [(256, 256), (128, 128), (64, 64), (48, 48), (32, 32), (16, 16)]
    images = []
    for s in sizes:
        resized = image.resize(s, Image.Resampling.LANCZOS)
        images.append(resized)

    images[0].save(icon_path, format='ICO', sizes=[(s[0], s[1]) for s in sizes])
    print(f"NEW icon created: {icon_path}")

if __name__ == '__main__':
    create_brain_icon()
