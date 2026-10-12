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

# Apply CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["Content-Disposition"],
)


@app.get("/")
async def read_root():
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
