"""Create ReelShift's multi-size Windows icon locally (no Actions required).

Only build dependency: Pillow. Icon is a film-strip + shift arrow; no fonts.
"""
from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw


def create_icon(destination: Path) -> None:
    scale = 4
    canvas = 256
    image = Image.new("RGBA", (canvas * scale, canvas * scale), (0, 0, 0, 0))
    pen = ImageDraw.Draw(image)

    def xy(box: tuple[int, ...]) -> tuple[int, ...]:
        return tuple(value * scale for value in box)

    pen.rounded_rectangle(
        xy((10, 10, 246, 246)), radius=58 * scale,
        fill=(14, 25, 48, 255), outline=(64, 118, 208, 255), width=6 * scale,
    )
    pen.rounded_rectangle(
        xy((40, 65, 215, 190)), radius=24 * scale,
        fill=(31, 66, 116, 255), outline=(108, 174, 245, 255), width=5 * scale,
    )
    pen.rounded_rectangle(xy((56, 81, 199, 173)), radius=15 * scale,
                          fill=(12, 28, 55, 255))
    for x in (58, 93, 128, 163, 198):
        pen.rounded_rectangle(xy((x, 68, x + 14, 78)), radius=3 * scale,
                              fill=(171, 210, 247, 255))
        pen.rounded_rectangle(xy((x, 177, x + 14, 187)), radius=3 * scale,
                              fill=(171, 210, 247, 255))
    pen.line([xy((77, 133)), xy((176, 133))], fill=(67, 163, 255, 255),
             width=15 * scale, joint="curve")
    pen.polygon([xy((165, 106)), xy((200, 133)), xy((165, 160))],
                fill=(67, 163, 255, 255))
    image = image.resize((256, 256), Image.Resampling.LANCZOS)
    destination.parent.mkdir(parents=True, exist_ok=True)
    image.save(destination, format="ICO",
               sizes=[(16, 16), (24, 24), (32, 32),
                      (48, 48), (64, 64), (128, 128), (256, 256)])
    print(f"App-Icon: {destination}")


if __name__ == "__main__":
    create_icon(Path(__file__).resolve().parents[1] / "assets" / "reelshift.ico")
