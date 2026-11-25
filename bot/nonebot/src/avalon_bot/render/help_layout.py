from __future__ import annotations

from dataclasses import dataclass
from io import BytesIO

from ..tool.image import (
    draw_hline,
    draw_text,
    get_draw,
    line_height,
    load_font,
    new_canvas,
    to_png_bytes,
    wrap_text,
)

WIDTH = 820
PAD_X = 48
PAD_TOP = 44
PAD_BOTTOM = 48
GAP_TITLE = 18
GAP_META = 8
GAP_BEFORE_SECTION = 32
GAP_AFTER_HEAD = 14
GAP_CMD_DESC = 6
GAP_ITEM = 18
GAP_AFTER_SECTION = 20
DESC_INDENT = 16
BG = (247, 246, 243)
TITLE_COLOR = (28, 25, 23)
MUTED_COLOR = (124, 116, 108)
CMD_COLOR = (41, 37, 36)
DESC_COLOR = (87, 83, 78)
RULE_COLOR = (220, 216, 210)


@dataclass(frozen=True)
class HelpItem:
    usage: str
    desc: str


@dataclass(frozen=True)
class HelpSection:
    title: str
    hint: str
    items: tuple[HelpItem, ...]


@dataclass(frozen=True)
class HelpPage:
    title: str
    prefix_line: str
    legend: str
    sections: tuple[HelpSection, ...]


def render(page: HelpPage) -> BytesIO:
    title_font = load_font(32)
    meta_font = load_font(18)
    section_font = load_font(20)
    cmd_font = load_font(22)
    desc_font = load_font(18)
    max_width = WIDTH - PAD_X * 2

    laid: list[tuple[str, str, list[tuple[list[str], list[str]]]]] = []
    height = PAD_TOP
    height += line_height(title_font) + GAP_TITLE
    height += line_height(meta_font) + GAP_META
    height += line_height(meta_font)

    for section in page.sections:
        height += GAP_BEFORE_SECTION
        height += line_height(section_font) + GAP_AFTER_HEAD
        if section.hint:
            height += line_height(meta_font) + 4
        items: list[tuple[list[str], list[str]]] = []
        for item in section.items:
            cmd_lines = wrap_text(cmd_font, item.usage, max_width)
            desc_lines = (
                wrap_text(desc_font, item.desc, max_width - DESC_INDENT)
                if item.desc
                else []
            )
            items.append((cmd_lines, desc_lines))
            height += line_height(cmd_font) * len(cmd_lines)
            if desc_lines:
                height += GAP_CMD_DESC + line_height(desc_font) * len(desc_lines)
            height += GAP_ITEM
        height -= GAP_ITEM
        height += GAP_AFTER_SECTION
        laid.append((section.title, section.hint, items))

    height += PAD_BOTTOM - GAP_AFTER_SECTION
    image = new_canvas(WIDTH, max(height, 200), BG)
    draw = get_draw(image)
    x = PAD_X
    y = PAD_TOP
    draw_text(draw, (x, y), page.title, title_font, TITLE_COLOR)
    y += line_height(title_font) + GAP_TITLE
    draw_text(draw, (x, y), page.prefix_line, meta_font, MUTED_COLOR)
    y += line_height(meta_font) + GAP_META
    draw_text(draw, (x, y), page.legend, meta_font, MUTED_COLOR)
    y += line_height(meta_font)

    for section_title, hint, items in laid:
        y += GAP_BEFORE_SECTION
        draw_text(draw, (x, y), section_title, section_font, TITLE_COLOR)
        y += line_height(section_font)
        if hint:
            y += 4
            draw_text(draw, (x, y), hint, meta_font, MUTED_COLOR)
            y += line_height(meta_font)
        y += 8
        draw_hline(draw, x, WIDTH - PAD_X, y, RULE_COLOR)
        y += GAP_AFTER_HEAD - 8
        for cmd_lines, desc_lines in items:
            for line in cmd_lines:
                draw_text(draw, (x, y), line, cmd_font, CMD_COLOR)
                y += line_height(cmd_font)
            if desc_lines:
                y += GAP_CMD_DESC
                for line in desc_lines:
                    draw_text(draw, (x + DESC_INDENT, y), line, desc_font, DESC_COLOR)
                    y += line_height(desc_font)
            y += GAP_ITEM
        y -= GAP_ITEM
        y += GAP_AFTER_SECTION

    return to_png_bytes(image)
