"""Create ultra-simple brain icon - just outline and minimal detail."""

from pathlib import Path
from PIL import Image, ImageDraw

def create_brain_icon():
    """Create a very simple brain outline."""
    size = 256
    image = Image.new('RGBA', (size, size), (255, 255, 255, 0))
    dc = ImageDraw.Draw(image)

    scale = 4

    # Main brain outline - white fill, black border
    dc.ellipse([16*scale, 16*scale, 48*scale, 48*scale],
               fill='white', outline='black', width=6)

    # Central vertical line dividing hemispheres
    dc.line([32*scale, 18*scale, 32*scale, 46*scale], fill='black', width=4)

    # Just TWO simple curves per hemisphere for brain folds
    # Left hemisphere
    dc.arc([20*scale, 22*scale, 30*scale, 32*scale], start=200, end=340, fill='black', width=4)
    dc.arc([20*scale, 34*scale, 30*scale, 44*scale], start=200, end=340, fill='black', width=4)

    # Right hemisphere
    dc.arc([34*scale, 22*scale, 44*scale, 32*scale], start=200, end=340, fill='black', width=4)
    dc.arc([34*scale, 34*scale, 44*scale, 44*scale], start=200, end=340, fill='black', width=4)

    # Save
    icon_path = str(Path(__file__).parent / "pilot_icon_new.ico")

    sizes = [(256, 256), (128, 128), (64, 64), (48, 48), (32, 32), (16, 16)]
    images = []
    for s in sizes:
        resized = image.resize(s, Image.Resampling.LANCZOS)
        images.append(resized)

    images[0].save(icon_path, format='ICO', sizes=[(s[0], s[1]) for s in sizes])
    print(f"Simple brain icon created: {icon_path}")

if __name__ == '__main__':
    create_brain_icon()
