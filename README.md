# Mini Claw
小搔！人工智能脚本手架工具！

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
**Windows 系统**
将 `miniclaw.bat` 中的 `python.exe` 路径替换为本机路径
```cmd
@echo off
"C:\Users\zhaowei\miniconda3\envs\miniclaw311\python.exe" -m miniclaw %*
```

**Linux 系统**
同上

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