# Mini Claw
小搔！人工智能脚本手架工具！

> 本工程借鉴 `CoPaw` 项目。

**主要功能：**
* 提供一个交互式的命令行界面，与大模型交互以完成各项工作。
* 对于复杂的任务，可以将其拆分成多个子任务，逐步完成。
* 支持记忆管理，主要是针对超长任务中的上下文压缩以最大限度节省开支。
* 支持办事员模式处理主管交代的任务，并且可以在需要时请求主管提供更多信息。
* 支持无限推进模式，允许大模型自行判断何时需要继续推进任务，直到任务完成。

**支持的工具列表：**
* 文件读写
* 文件查找
* `SHELL`命令（😅支持干掉自己，有时候杀别的 `python` 应用进程处理不了就直接梭哈所有 `python` 进程自己也在名单里！）
* 浏览器操作（基于`playwright`）
* 屏幕截图
* 独立进程运行（在后台启动一个完全独立的进程，脱离当前Python程序独立运行。适用于启动 Spring Boot、Node.js、执行yarn/npm 构建等场景。路径支持~表示用户目录。）
* 办事员（办事员处理各项子任务）
* 任务规划者（对于复杂任务进行规划）

## 环境配置
* `python 3.11+`
  * `Windows` 系统建议安装 `miniconda`
  * `Linux` 系统建议安装 `Conda`
* 需要安装 `poetry` 包管理工具
  * `pip install poetry`
* 安装依赖
  * `poetry install`
  * `poetry install --group dev` (安装开发依赖)
* 运行依赖（额外的）
  * `pip install playwright`
  * `playwright install` (安装浏览器)
  * `pip install uvicorn` (安装服务器)
  * `pip install litellm[proxy]` (安装 LiteLLM 代理)

## 运行配置

### 运行配置
* 需要在项目根目录下创建 `.env` 文件，可以直接将 `.env.example` 文件复制一份并重命名为 `.env`，例如：
  * LLM_MODEL=deepseek/deepseek-v4-flash
  * LLM_API_KEY=<your_api_key>
  * LLM_BASE_URL=https://api.deepseek.com

### 运行方式
**Windows 系统**

将 `miniclaw.bat` 中的 `python.exe` 路径替换为本机路径
```cmd
@echo off
"C:\Users\zhaowei\miniconda3\envs\miniclaw311\python.exe" -m miniclaw %*
```

**Linux 系统**

同上

**运行命令**
```bash
# 在 Commander/Power Shell 或者 Shell 中运行 `miniclaw` 命令，进入交互式命令行界面。

miniclaw.bat
```


## 调试说明
* 若需要在控制台运行时调试，请将下面的语句在待调试的地方拷贝
  * `import pdb; pdb.set_trace()`

## 测试说明

### 异步测试
* 需要安装 `pytest-asyncio` 包
  * `poetry add --group dev pytest-asyncio`
* 在测试文件中引入 `pytest-asyncio`，并使用 `@pytest.mark.asyncio` 装饰器标记异步测试函数
  ```python
    import pytest

    @pytest.mark.asyncio
    async def test_async_function():
        # 测试代码
    ```