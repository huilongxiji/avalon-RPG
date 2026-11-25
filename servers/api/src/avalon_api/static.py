"""托管网站打包后的文件（data/web/dist）。没有打包时什么都不做，开发时由 Vite 开发服务器提供网站。"""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from starlette.exceptions import HTTPException
from starlette.types import Scope

from .config import get_settings


class _WebFiles(StaticFiles):
    """网站的页面地址（例如 /items/138）不是真实文件：找不到时返回首页，由网站自己显示对应页面。
    /api、/ws 开头的地址和带扩展名的文件（例如缺失的 .js）不这样处理，照常返回 404。"""

    async def get_response(self, path: str, scope: Scope):
        try:
            return await super().get_response(path, scope)
        except HTTPException as exc:
            last = path.rsplit("/", 1)[-1]
            if exc.status_code != 404 or path.startswith(("api", "ws")) or "." in last:
                raise
            return await super().get_response("index.html", scope)


def mount_web(app: FastAPI) -> bool:
    dist = get_settings().data_dir / "web" / "dist"
    if not (dist / "index.html").is_file():
        return False
    app.mount("/", _WebFiles(directory=dist, html=True), name="web")
    return True
