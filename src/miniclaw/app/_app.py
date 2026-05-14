from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from loguru import logger

from ..__version__ import __version__
from ..utils.logger import setup_logger
from .routers import llm_router

# Configure logging as soon as _app is imported.
setup_logger()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lifespan context manager for FastAPI application."""
    # ── 启动前初始化 ───────────────────────────────────────────────
    # 这里可以放置任何需要在应用启动前执行的代码，例如：
    # - 加载配置文件
    # - 初始化数据库连接
    # - 设置全局状态等

    logger.info("应用正在启动...")
    logger.info("应用启动完成，正在运行...")
    yield  # 这里是应用运行的上下文

    # ── 关闭时清理 ───────────────────────────────────────────────
    # 这里可以放置任何需要在应用关闭时执行的代码，例如：
    # - 关闭数据库连接
    # - 清理临时文件等

    logger.info("应用正在关闭...")
    logger.info("应用关闭完成。")

app = FastAPI(lifespan=lifespan)
app.include_router(llm_router)

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