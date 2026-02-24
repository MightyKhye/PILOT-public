"""Create brain icon file for Pilot."""

from pathlib import Path
from PIL import Image, ImageDraw

def create_brain_icon():
    """Create a brain icon and save as .ico file."""
    # Create 256x256 image for high quality
    size = 256
    image = Image.new('RGBA', (size, size), (255, 255, 255, 0))
    dc = ImageDraw.Draw(image)

    # Scale up coordinates
    scale = 4

    # No color - just white fill with black outlines/lines
    fill_color = 'white'

    # Main brain outline (oval)
    dc.ellipse([16*scale, 12*scale, 48*scale, 52*scale],
               fill=fill_color, outline='black', width=6)

    # Central fissure (dividing hemispheres)
    dc.line([32*scale, 14*scale, 32*scale, 50*scale], fill='black', width=4)

    # Left hemisphere folds/gyri (multiple curved lines)
    # Top left folds
    dc.arc([18*scale, 14*scale, 30*scale, 24*scale], start=180, end=360, fill='black', width=3)
    dc.arc([20*scale, 18*scale, 28*scale, 26*scale], start=180, end=360, fill='black', width=2)

    # Middle left folds
    dc.arc([18*scale, 26*scale, 30*scale, 36*scale], start=180, end=360, fill='black', width=3)
    dc.arc([20*scale, 30*scale, 28*scale, 38*scale], start=180, end=360, fill='black', width=2)

    # Bottom left folds
    dc.arc([18*scale, 38*scale, 30*scale, 48*scale], start=180, end=360, fill='black', width=3)

    # Right hemisphere folds/gyri (mirror of left)
    # Top right folds
    dc.arc([34*scale, 14*scale, 46*scale, 24*scale], start=180, end=360, fill='black', width=3)
    dc.arc([36*scale, 18*scale, 44*scale, 26*scale], start=180, end=360, fill='black', width=2)

    # Middle right folds
    dc.arc([34*scale, 26*scale, 46*scale, 36*scale], start=180, end=360, fill='black', width=3)
    dc.arc([36*scale, 30*scale, 44*scale, 38*scale], start=180, end=360, fill='black', width=2)

    # Bottom right folds
    dc.arc([34*scale, 38*scale, 46*scale, 48*scale], start=180, end=360, fill='black', width=3)

    # Additional sulci (grooves) for more detail
    # Diagonal grooves on left
    dc.arc([19*scale, 20*scale, 29*scale, 32*scale], start=200, end=340, fill='black', width=2)
    dc.arc([20*scale, 32*scale, 30*scale, 44*scale], start=200, end=340, fill='black', width=2)

    # Diagonal grooves on right
    dc.arc([35*scale, 20*scale, 45*scale, 32*scale], start=200, end=340, fill='black', width=2)
    dc.arc([34*scale, 32*scale, 44*scale, 44*scale], start=200, end=340, fill='black', width=2)

    # Save as .ico with multiple sizes
    icon_path = str(Path(__file__).parent / "pilot_brain.ico")

    # Create multiple sizes for the icon
    sizes = [(256, 256), (128, 128), (64, 64), (48, 48), (32, 32), (16, 16)]
    images = []
    for size in sizes:
        resized = image.resize(size, Image.Resampling.LANCZOS)
        images.append(resized)

    # Save as .ico
    images[0].save(icon_path, format='ICO', sizes=[(s[0], s[1]) for s in sizes])
    print(f"Icon created: {icon_path}")

if __name__ == '__main__':
    create_brain_icon()
