"""从源 PNG 生成桌面应用图标（icon.ico / icon.png / icons/*.png）。

用法：
    python make_icon.py [源图路径]

- 默认源图：本目录下的 `icon-src.png`。
- 源图须为「方形 PNG（含透明通道）」；建议 >= 256（可满足 Windows 全套尺寸）；
  若要生成 macOS/Linux 的 512，源图需 >= 512（1024 更佳）。
- 生成物：
    icon.ico        Windows 多尺寸图标（16/24/32/48/64/128/256）
    icon.png        256×256，未打包时窗口图标回退使用
    icons/*.png     Linux 打包用 PNG 集合（16…512，超过源图尺寸的会跳过）
    ../src/assets/logo.png   UI 内使用（标题栏 / 加载页）
    ../public/favicon.png   页面 favicon
"""

import sys
from pathlib import Path

from PIL import Image

HERE = Path(__file__).resolve().parent

WINDOWS_SIZES = [16, 24, 32, 48, 64, 128, 256]
PNG_SIZES = [16, 24, 32, 48, 64, 128, 256, 512]


def load_square(src: Path) -> Image.Image:
    """读入源图并保证为方形 RGBA（非方形时居中贴到透明正方形画布）。"""
    im = Image.open(src).convert("RGBA")
    w, h = im.size
    if w != h:
        side = max(w, h)
        canvas = Image.new("RGBA", (side, side), (0, 0, 0, 0))
        canvas.paste(im, ((side - w) // 2, (side - h) // 2), im)
        im = canvas
    return im


def main() -> None:
    src = Path(sys.argv[1]) if len(sys.argv) > 1 else HERE / "icon-src.png"
    if not src.exists():
        print(f"[x] 源图不存在: {src}")
        print("    请把方形 PNG 放到该路径，或作为参数传入。")
        sys.exit(1)

    im = load_square(src)
    print(f"[i] 源图: {src} -> {im.size}")

    # 1) Windows 多尺寸 .ico（Pillow 逐尺寸用 LANCZOS 缩放，32 位）
    ico = HERE / "icon.ico"
    im.save(ico, format="ICO", sizes=[(s, s) for s in WINDOWS_SIZES])
    print(f"[+] {ico}  sizes={WINDOWS_SIZES}")

    # 2) 窗口图标用 PNG（未打包时 electron/main.js 回退使用）
    png256 = HERE / "icon.png"
    im.resize((256, 256), Image.Resampling.LANCZOS).save(png256)
    print(f"[+] {png256}  256x256")

    # 2.1) UI 内使用的小尺寸图标（标题栏 / 加载页）+ 页面 favicon
    frontend = HERE.parent
    logo_target = frontend / "src" / "assets" / "logo.png"
    logo_target.parent.mkdir(parents=True, exist_ok=True)
    im.resize((128, 128), Image.Resampling.LANCZOS).save(logo_target)
    print(f"[+] {logo_target}  128x128")

    fav_target = frontend / "public" / "favicon.png"
    fav_target.parent.mkdir(parents=True, exist_ok=True)
    im.resize((32, 32), Image.Resampling.LANCZOS).save(fav_target)
    print(f"[+] {fav_target}  32x32")

    # 3) Linux 打包用 PNG 集合（超过源图尺寸的跳过）
    icons_dir = HERE / "icons"
    icons_dir.mkdir(exist_ok=True)
    for s in PNG_SIZES:
        if s > max(im.size):
            print(f"[!] 跳过 {s}x{s}（源图过小，需 >= {s}）")
            continue
        im.resize((s, s), Image.Resampling.LANCZOS).save(icons_dir / f"{s}x{s}.png")
    print(f"[+] {icons_dir}/  sizes={PNG_SIZES}")


if __name__ == "__main__":
    main()
