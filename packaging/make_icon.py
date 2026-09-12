"""生成 Voice Vibe 应用图标 packaging/icon.ico（麦克风 + 悬浮条底座）。"""
from PIL import Image, ImageDraw


def draw(size: int) -> Image.Image:
    s = size / 64  # 以 64px 为基准坐标系
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)

    # 圆角渐变蓝底
    grad = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    gd = ImageDraw.Draw(grad)
    top, bottom = (72, 145, 255), (34, 80, 200)
    for y in range(size):
        t = y / max(size - 1, 1)
        gd.line([(0, y), (size, y)], fill=tuple(round(a + (b - a) * t) for a, b in zip(top, bottom)))
    mask = Image.new("L", (size, size), 0)
    md = ImageDraw.Draw(mask)
    md.rounded_rectangle([0, 0, size - 1, size - 1], radius=round(13 * s), fill=255)
    img.paste(grad, (0, 0), mask)

    # 麦克风网头
    d.rounded_rectangle([round(24 * s), round(12 * s), round(40 * s), round(32 * s)],
                        radius=round(8 * s), fill=(255, 255, 255, 255))
    # 支架
    d.arc([round(20 * s), round(18 * s), round(44 * s), round(42 * s)], start=0, end=180,
          fill=(255, 255, 255, 255), width=round(4 * s))
    # 麦克风杆 + 底座
    d.line([(32 * s, 40 * s), (32 * s, 46 * s)], fill=(255, 255, 255, 255), width=round(4 * s))
    d.line([(24 * s, 48 * s), (40 * s, 48 * s)], fill=(255, 255, 255, 255), width=round(4 * s))
    return img


if __name__ == "__main__":
    import pathlib

    out = pathlib.Path(__file__).resolve().parent / "icon.ico"
    draw(256).save(out, sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])
    print(f"written: {out}")
