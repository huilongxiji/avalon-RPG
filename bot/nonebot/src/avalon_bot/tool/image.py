from __future__ import annotations

from functools import lru_cache
from io import BytesIO
from pathlib import Path

from nonebot import get_plugin_config
from PIL import Image, ImageDraw, ImageFont

from .config import Config

_FONT_CANDIDATES = (
    # 仓库自带字体优先，保证任何部署环境都能出图
    Path(__file__).resolve().parent / "fonts" / "simhei.ttf",
    Path("/System/Library/Fonts/PingFang.ttc"),
    Path("/System/Library/Fonts/Hiragino Sans GB.ttc"),
    Path("/System/Library/Fonts/STHeiti Light.ttc"),
    Path("/System/Library/Fonts/Supplemental/Songti.ttc"),
    Path("/Library/Fonts/Arial Unicode.ttf"),
    Path("/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc"),
    Path("/usr/share/fonts/noto-cjk/NotoSansCJK-Regular.ttc"),
    Path("/usr/share/fonts/truetype/noto/NotoSansCJK-Regular.ttc"),
    Path("/usr/share/fonts/truetype/wqy/wqy-microhei.ttc"),
    Path("C:/Windows/Fonts/msyh.ttc"),
    Path("C:/Windows/Fonts/msyh.ttf"),
)


class FontNotFoundError(RuntimeError):
    pass


def _font_path() -> Path | None:
    configured = get_plugin_config(Config).game_layout_font.strip()
    if configured:
        path = Path(configured).expanduser()
        if path.is_file():
            return path
    for path in _FONT_CANDIDATES:
        if path.is_file():
            return path
    return None


def _try_truetype(path: Path, size: int) -> ImageFont.FreeTypeFont | None:
    for index in (0, 1, 2):
        try:
            return ImageFont.truetype(str(path), size=size, index=index)
        except OSError:
            continue
    return None


@lru_cache(maxsize=16)
def load_font(size: int) -> ImageFont.FreeTypeFont:
    path = _font_path()
    if path is None:
        raise FontNotFoundError("未找到可用的中文字体")
    font = _try_truetype(path, size)
    if font is None:
        raise FontNotFoundError(f"无法加载字体: {path}")
    return font


def new_canvas(width: int, height: int, background: tuple[int, int, int]) -> Image.Image:
    return Image.new("RGB", (width, height), background)


def get_draw(image: Image.Image) -> ImageDraw.ImageDraw:
    return ImageDraw.Draw(image)


def line_height(font: ImageFont.FreeTypeFont) -> int:
    ascent, descent = font.getmetrics()
    return ascent + descent


def text_width(font: ImageFont.FreeTypeFont, text: str) -> int:
    if not text:
        return 0
    left, _top, right, _bottom = font.getbbox(text)
    return round(right - left)


def wrap_text(font: ImageFont.FreeTypeFont, text: str, max_width: int) -> list[str]:
    if text_width(font, text) <= max_width:
        return [text] if text else [""]
    lines: list[str] = []
    current = ""
    for char in text:
        trial = current + char
        if text_width(font, trial) <= max_width:
            current = trial
            continue
        if current:
            lines.append(current)
        current = char
    if current:
        lines.append(current)
    return lines or [""]


def draw_text(
    draw: ImageDraw.ImageDraw,
    xy: tuple[int, int],
    text: str,
    font: ImageFont.FreeTypeFont,
    fill: tuple[int, int, int],
) -> None:
    x, y = xy
    ascent, _descent = font.getmetrics()
    draw.text((x, y + ascent), text, font=font, fill=fill, anchor="ls")


def draw_hline(
    draw: ImageDraw.ImageDraw,
    x1: int,
    x2: int,
    y: int,
    fill: tuple[int, int, int],
) -> None:
    draw.line((x1, y, x2, y), fill=fill, width=1)


def to_png_bytes(image: Image.Image) -> BytesIO:
    buf = BytesIO()
    image.save(buf, format="PNG")
    buf.seek(0)
    return buf
