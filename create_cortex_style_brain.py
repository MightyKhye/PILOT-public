"""Create brain icon similar to typical brain logos - top-down view with organic curves."""

from pathlib import Path
from PIL import Image, ImageDraw

def create_brain_icon():
    """Create a brain logo showing top-down view with two hemispheres."""
    size = 256
    image = Image.new('RGBA', (size, size), (255, 255, 255, 0))
    dc = ImageDraw.Draw(image)

    scale = 4

    # Overall brain outline (rounded shape)
    brain_outline = [
        (20*scale, 26*scale),  # Top left
        (18*scale, 32*scale),  # Upper left curve
        (20*scale, 38*scale),  # Middle left
        (22*scale, 44*scale),  # Lower left
        (26*scale, 46*scale),  # Bottom left
        (32*scale, 48*scale),  # Bottom center
        (38*scale, 46*scale),  # Bottom right
        (42*scale, 44*scale),  # Lower right
        (44*scale, 38*scale),  # Middle right
        (46*scale, 32*scale),  # Upper right curve
        (44*scale, 26*scale),  # Top right
        (40*scale, 22*scale),  # Upper right top
        (32*scale, 20*scale),  # Top center
        (24*scale, 22*scale),  # Upper left top
    ]
    dc.polygon(brain_outline, fill='white', outline='black', width=4)

    # Central fissure (dividing line between hemispheres) - curved
    fissure_points = [
        (32*scale, 22*scale),
        (31*scale, 28*scale),
        (32*scale, 34*scale),
        (33*scale, 40*scale),
        (32*scale, 46*scale),
    ]
    for i in range(len(fissure_points) - 1):
        dc.line([fissure_points[i], fissure_points[i+1]], fill='black', width=3)

    # LEFT HEMISPHERE organic curves (gyri/folds)
    # Upper left curves
    dc.arc([19*scale, 24*scale, 30*scale, 32*scale], start=160, end=280, fill='black', width=3)
    dc.arc([20*scale, 27*scale, 29*scale, 35*scale], start=170, end=290, fill='black', width=2)

    # Middle left curves
    dc.arc([19*scale, 32*scale, 30*scale, 40*scale], start=160, end=280, fill='black', width=3)
    dc.arc([21*scale, 35*scale, 29*scale, 42*scale], start=170, end=290, fill='black', width=2)

    # Lower left curve
    dc.arc([22*scale, 40*scale, 31*scale, 46*scale], start=160, end=280, fill='black', width=3)

    # RIGHT HEMISPHERE organic curves (mirror)
    # Upper right curves
    dc.arc([34*scale, 24*scale, 45*scale, 32*scale], start=260, end=20, fill='black', width=3)
    dc.arc([35*scale, 27*scale, 44*scale, 35*scale], start=250, end=10, fill='black', width=2)

    # Middle right curves
    dc.arc([34*scale, 32*scale, 45*scale, 40*scale], start=260, end=20, fill='black', width=3)
    dc.arc([35*scale, 35*scale, 43*scale, 42*scale], start=250, end=10, fill='black', width=2)

    # Lower right curve
    dc.arc([33*scale, 40*scale, 42*scale, 46*scale], start=260, end=20, fill='black', width=3)

    # Save
    icon_path = str(Path(__file__).parent / "pilot_brain_v3.ico")

    sizes = [(256, 256), (128, 128), (64, 64), (48, 48), (32, 32), (16, 16)]
    images = []
    for s in sizes:
        resized = image.resize(s, Image.Resampling.LANCZOS)
        images.append(resized)

    images[0].save(icon_path, format='ICO', sizes=[(s[0], s[1]) for s in sizes])
    print(f"Cortex-style brain icon created: {icon_path}")

if __name__ == '__main__':
    create_brain_icon()
