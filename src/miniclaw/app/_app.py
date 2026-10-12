"""FastAPI 应用装配入口。

创建 ``app`` 实例、注册日志与生命周期钩子、挂载全部路由与 CORS 中间件，
并提供根路径、版本与健康检查端点。
"""

import os
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from loguru import logger

from ..__version__ import __version__
from ..utils.logger import install_asyncio_exception_handler, setup_logger
from .routers import ALL_ROUTERS

# Configure logging as soon as _app is imported.
setup_logger()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lifespan context manager for FastAPI application."""
    # 为当前事件循环安装 asyncio 异常处理器，使未处理异常带堆栈落盘
    install_asyncio_exception_handler()
    logger.info("应用正在启动...")
    logger.info("应用启动完成，正在运行...")
    yield
    logger.info("应用正在关闭...")
    logger.info("应用关闭完成。")


app = FastAPI(title="MiniClaw", version=__version__, lifespan=lifespan)

for _router in ALL_ROUTERS:
    app.include_router(_router)

# CORS：仅放行本机来源（浏览器 / Electron 前端）。
# - 桌面端生产环境渲染进程由 file:// 加载，跨源请求的 Origin 为 "null"；
# - 开发环境为 Vite devServer（默认 http://localhost:5173）。
# 如需自定义白名单，可通过环境变量 CORS_ALLOW_ORIGINS（逗号分隔）显式指定。
_cors_origins = [o.strip() for o in os.getenv("CORS_ALLOW_ORIGINS", "").split(",") if o.strip()]
_cors_kwargs = (
    {"allow_origins": _cors_origins}
    if _cors_origins
    else {"allow_origin_regex": r"^(https?://(localhost|127\.0\.0\.1)(:\d+)?|null)$"}
)
app.add_middleware(
    CORSMiddleware,
    # 鉴权走 Authorization: Bearer 头，不使用 Cookie，故关闭 credentials
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["Content-Disposition"],
    **_cors_kwargs,
)


@app.get("/")
async def read_root():
    """根路径：返回 MiniClaw 服务简介。"""
    return {
        "message": (
            "MiniClaw is specialized in agents orchestration and tool management. "
        )
    }


@app.get("/api/version")
async def get_version():
    """Return the current MiniClaw version."""
    return {"version": __version__}


@app.get("/api/health")
async def health():
    """健康检查（供启动方轮询就绪；无需鉴权）。"""
    return {"status": "ok", "version": __version__}
