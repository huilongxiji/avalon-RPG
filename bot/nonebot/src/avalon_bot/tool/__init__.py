"""图片工具按需导入；蓝字等纯排版工具不要求加载 NoneBot。"""

__all__ = [
    "FontNotFoundError",
    "draw_hline",
    "draw_text",
    "get_draw",
    "line_height",
    "load_font",
    "new_canvas",
    "to_png_bytes",
    "wrap_text",
]


def __getattr__(name: str):
    if name in __all__:
        from . import image
        return getattr(image, name)
    raise AttributeError(name)
