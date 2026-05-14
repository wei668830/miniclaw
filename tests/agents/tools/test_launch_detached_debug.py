# -*- coding: utf-8 -*-
"""独立测试 launch_detached 功能"""

import asyncio
import os
import subprocess
import sys
import time


async def test_simple_command():
    """测试1: 最简单的命令 - 查看目录"""
    print("\n=== 测试1: 执行 dir 命令 ===")

    log_file = "D:\\logs\\test_dir.log"
    os.makedirs(os.path.dirname(log_file), exist_ok=True)

    # 直接执行，不后台
    process = subprocess.Popen(
        'dir',
        shell=True,
        cwd="D:\\wormsleep\\workspace\\rpa-platform\\rpa-platform-3.2.3\\rpa-xyz-idea",
        stdout=open(log_file, 'w'),
        stderr=subprocess.STDOUT,
        text=True
    )

    process.wait(timeout=5)

    print(f"进程退出码: {process.returncode}")
    print(f"日志文件: {log_file}")

    with open(log_file, 'r', encoding='utf-8') as f:
        print(f"日志内容:\n{f.read()}")

    return process.returncode == 0


async def test_maven_command_direct():
    """测试2: 直接执行 Maven 命令（前台运行5秒后终止）"""
    print("\n=== 测试2: 直接执行 Maven 命令 ===")

    log_file = "D:\\logs\\test_maven_direct.log"
    os.makedirs(os.path.dirname(log_file), exist_ok=True)

    cmd = 'mvn spring-boot:run -Dspring-boot.run.jvmArguments="-Dfile.encoding=UTF-8"'
    cwd = "D:\\wormsleep\\workspace\\rpa-platform\\rpa-platform-3.2.3\\rpa-xyz-idea"

    print(f"执行命令: {cmd}")
    print(f"工作目录: {cwd}")

    try:
        process = subprocess.Popen(
            cmd,
            shell=True,
            cwd=cwd,
            stdout=open(log_file, 'w'),
            stderr=subprocess.STDOUT,
            text=True
        )

        print(f"进程 PID: {process.pid}")

        # 等待5秒看进程是否启动
        for i in range(5):
            time.sleep(1)
            if process.poll() is not None:
                print(f"进程已退出，退出码: {process.returncode}")
                break
            else:
                print(f"进程运行中... ({i + 1}/5)")

        # 查看 Java 进程
        print("\n当前 Java/Maven 进程:")
        result = subprocess.run('tasklist | findstr /i "java mvn"', shell=True, capture_output=True, text=True)
        print(result.stdout if result.stdout else "未找到 Java/Maven 进程")

        # 终止进程
        if process.poll() is None:
            print("\n终止测试进程...")
            process.terminate()
            time.sleep(2)
            if process.poll() is None:
                process.kill()

        # 显示日志前几行
        print(f"\n日志文件前20行 ({log_file}):")
        with open(log_file, 'r', encoding='utf-8') as f:
            lines = f.readlines()[:20]
            print(''.join(lines))

        return True

    except Exception as e:
        print(f"错误: {e}")
        return False


async def test_background_with_output():
    """测试3: 后台运行并检查进程"""
    print("\n=== 测试3: 后台运行并追踪进程 ===")

    log_file = "D:\\logs\\test_background.log"
    os.makedirs(os.path.dirname(log_file), exist_ok=True)

    # 创建一个测试脚本
    test_script = f"""@echo off
echo Starting process... > "{log_file}"
echo PID: %$ > "{log_file}"
timeout /t 30
echo Process completed >> "{log_file}"
"""

    # 执行后台命令
    if sys.platform == 'win32':
        cmd = f'start /b cmd /c "echo Test && timeout /t 10"'
    else:
        cmd = f'nohup sh -c "echo Test && sleep 10" > {log_file} 2>&1 &'

    print(f"执行命令: {cmd}")

    process = subprocess.Popen(
        cmd,
        shell=True,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        creationflags=subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.DETACHED_PROCESS if sys.platform == 'win32' else 0
    )

    print(f"Shell PID: {process.pid}")

    # 等待进程启动
    time.sleep(2)

    # 查找子进程
    print(f"\n查找 PID {process.pid} 的子进程:")
    result = subprocess.run(f'wmic process where "parentprocessid={process.pid}" get processid,name',
                            shell=True, capture_output=True, text=True)
    print(result.stdout if result.stdout else "没有子进程")

    return True


async def test_check_maven_environment():
    """测试4: 检查 Maven 环境"""
    print("\n=== 测试4: 检查 Maven 环境 ===")

    # 检查 mvn 是否可用
    result = subprocess.run('where mvn', shell=True, capture_output=True, text=True)
    if result.returncode == 0:
        print(f"Maven 路径: {result.stdout}")
    else:
        print("未找到 Maven，请检查环境变量")
        return False

    # 检查 Java 版本
    result = subprocess.run('java -version', shell=True, capture_output=True, text=True)
    print(f"Java 版本: {result.stderr if result.stderr else result.stdout}")

    # 检查项目目录
    cwd = "D:\\wormsleep\\workspace\\rpa-platform\\rpa-platform-3.2.3\\rpa-xyz-idea"
    if os.path.exists(cwd):
        print(f"项目目录存在: {cwd}")

        # 检查 pom.xml
        pom_path = os.path.join(cwd, "pom.xml")
        if os.path.exists(pom_path):
            print(f"pom.xml 存在")
        else:
            print(f"警告: pom.xml 不存在")
    else:
        print(f"错误: 项目目录不存在 {cwd}")
        return False

    return True


async def main():
    """运行所有测试"""
    print("=" * 60)
    print("开始测试 launch_detached 功能")
    print("=" * 60)

    # 测试4: 检查环境
    await test_check_maven_environment()

    # 测试1: 简单命令
    await test_simple_command()

    # 测试3: 后台运行
    await test_background_with_output()

    # 测试2: Maven 命令（会实际启动）
    print("\n" + "=" * 60)
    print("即将启动 Maven 命令（会运行5秒后自动终止）")
    print("=" * 60)
    await test_maven_command_direct()

    print("\n" + "=" * 60)
    print("测试完成")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())