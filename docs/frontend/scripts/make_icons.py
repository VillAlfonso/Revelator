"""
Generate the PWA / home-screen PNG icons from the Revelator mark.

The mark is the same design as frontend/public/favicon.svg (crosshair ring +
triangle + fingerprint ridges) redrawn with Pillow, because the manifest needs
real raster icons: Android's install criteria want a >=192px PNG, and a
"maskable" variant so the launcher's circle/squircle crop does not clip the ring.

Run from the repo root (or anywhere) with:
    python frontend/scripts/make_icons.py

Writes into frontend/public/:
    icon-192.png            purpose "any"
    icon-512.png            purpose "any"
    icon-maskable-512.png   purpose "maskable" (mark shrunk into the safe zone)
    apple-touch-icon.png    180px, iOS "Add to Home Screen"
"""

from pathlib import Path

from PIL import Image, ImageDraw

OUT_DIR = Path(__file__).resolve().parent.parent / "public"

GREEN = (0, 255, 102)
BG_EDGE = (0, 0, 0)
BG_CORE = (10, 18, 12)

SS = 4  # supersample factor, downscaled at the end for antialiasing


def _lerp(a, b, t):
    return tuple(round(x + (y - x) * t) for x, y in zip(a, b))


def _q_bezier(p0, p1, p2, steps=48):
    """Quadratic bezier -> polyline, so Pillow can stroke the SVG 'Q' paths."""
    pts = []
    for i in range(steps + 1):
        t = i / steps
        u = 1 - t
        pts.append((
            u * u * p0[0] + 2 * u * t * p1[0] + t * t * p2[0],
            u * u * p0[1] + 2 * u * t * p1[1] + t * t * p2[1],
        ))
    return pts


def draw_mark(size, inset_ratio=1.0):
    """
    Render the mark on an opaque black square of `size` px.

    inset_ratio shrinks the 100x100 artboard inside the square: 1.0 fills the
    icon edge to edge, ~0.62 pulls it into the maskable safe zone.
    """
    S = size * SS
    img = Image.new("RGB", (S, S), BG_EDGE)
    d = ImageDraw.Draw(img)

    art = S * inset_ratio          # artboard side in device px
    off = (S - art) / 2            # top-left of the artboard
    u = art / 100.0                # one SVG user-unit in device px

    def P(x, y):
        return (off + x * u, off + y * u)

    def circle(cx, cy, r, **kw):
        d.ellipse([P(cx - r, cy - r), P(cx + r, cy + r)], **kw)

    # Radial background inside the ring: #0a120c core -> #000 edge, faked with
    # concentric fills (Pillow has no gradient primitive).
    steps = 90
    for i in range(steps, 0, -1):
        t = i / steps
        circle(50, 50, 46 * t, fill=_lerp(BG_CORE, BG_EDGE, 1 - t))

    # Outer ring
    circle(50, 50, 46, outline=GREEN, width=max(1, round(2 * u)))

    # Inner dashed ring (dasharray 2 3 on r=42) at 50% opacity
    dash = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    dd = ImageDraw.Draw(dash)
    seg, gap = 2.0, 3.0
    circumference = 2 * 3.141592653589793 * 42
    step_deg = 360.0 * seg / circumference
    gap_deg = 360.0 * gap / circumference
    a = 0.0
    while a < 360:
        dd.arc(
            [P(50 - 42, 50 - 42), P(50 + 42, 50 + 42)],
            start=a, end=a + step_deg,
            fill=GREEN + (128,), width=max(1, round(0.6 * u)),
        )
        a += step_deg + gap_deg
    img.paste(Image.alpha_composite(img.convert("RGBA"), dash).convert("RGB"), (0, 0))
    d = ImageDraw.Draw(img)

    # Crosshair ticks
    tick = max(1, round(1.6 * u))
    for x1, y1, x2, y2 in [
        (50, 2, 50, 9), (50, 91, 50, 98), (2, 50, 9, 50), (91, 50, 98, 50),
    ]:
        d.line([P(x1, y1), P(x2, y2)], fill=GREEN, width=tick)

    # Fingerprint ridges, clipped to the triangle
    tri = [(50, 18), (82, 72), (18, 72)]
    ridges = Image.new("RGB", (S, S), BG_EDGE)
    rd = ImageDraw.Draw(ridges)
    for x0, y0, cx, cy, x1, y1 in [
        (28, 62, 50, 42, 72, 62),
        (32, 62, 50, 46, 68, 62),
        (36, 62, 50, 50, 64, 62),
        (40, 62, 50, 54, 60, 62),
        (44, 62, 50, 58, 56, 62),
    ]:
        pts = [P(x, y) for x, y in _q_bezier((x0, y0), (cx, cy), (x1, y1))]
        rd.line(pts, fill=GREEN, width=max(1, round(1.0 * u)), joint="curve")

    mask = Image.new("L", (S, S), 0)
    ImageDraw.Draw(mask).polygon([P(x, y) for x, y in tri], fill=255)
    img.paste(ridges, (0, 0), mask)
    d = ImageDraw.Draw(img)

    # Triangle outline + centre dot
    d.polygon([P(x, y) for x, y in tri], outline=GREEN, width=max(1, round(1.8 * u)))
    circle(50, 60, 1.6, fill=GREEN)

    return img.resize((size, size), Image.LANCZOS)


def main():
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    targets = [
        ("icon-192.png", 192, 0.98),
        ("icon-512.png", 512, 0.98),
        # Maskable: launchers crop to a circle/squircle, keeping only the middle
        # ~80%. Shrink the mark so the ring survives the crop.
        ("icon-maskable-512.png", 512, 0.62),
        ("apple-touch-icon.png", 180, 0.88),
    ]
    for name, size, inset in targets:
        img = draw_mark(size, inset)
        img.save(OUT_DIR / name, "PNG", optimize=True)
        print(f"  wrote {name} ({size}x{size})")


if __name__ == "__main__":
    main()
