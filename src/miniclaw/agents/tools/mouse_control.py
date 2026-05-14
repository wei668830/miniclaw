"""
鼠标控制工具 - 适用于大模型调用
支持移动、单击、双击、拖拽等操作
依赖: pyautogui, pynput
安装: pip install pyautogui pynput
"""

import pyautogui
import time
from typing import Tuple, Optional, Literal

# 安全设置：让PyAutoGUI操作之间有短暂延迟，防止操作过快
pyautogui.PAUSE = 0.1
# 启用失败保护：将鼠标移到左上角会触发异常
pyautogui.FAILSAFE = True


# ========== 基础鼠标操作函数 ==========

def get_screen_size() -> Tuple[int, int]:
    """获取屏幕尺寸"""
    return pyautogui.size()


def get_current_position() -> Tuple[int, int]:
    """获取当前鼠标位置"""
    return pyautogui.position()


def move_to(x: int, y: int, duration: float = 0.2, absolute: bool = True):
    """
    移动鼠标到指定位置

    Args:
        x: X坐标或相对移动量
        y: Y坐标或相对移动量
        duration: 移动持续时间(秒)
        absolute: True为绝对坐标，False为相对当前坐标移动
    """
    if absolute:
        pyautogui.moveTo(x, y, duration=duration)
    else:
        pyautogui.moveRel(x, y, duration=duration)

    return {
        "success": True,
        "position": get_current_position(),
        "message": f"鼠标已移动到 ({x}, {y})"
    }


def click(button: Literal['left', 'right', 'middle'] = 'left',
          clicks: int = 1,
          interval: float = 0.1):
    """
    鼠标单击或双击

    Args:
        button: 按钮类型 'left', 'right', 'middle'
        clicks: 点击次数 (1=单击, 2=双击)
        interval: 点击间隔(秒)
    """
    pyautogui.click(button=button, clicks=clicks, interval=interval)

    return {
        "success": True,
        "button": button,
        "clicks": clicks,
        "message": f"鼠标{button}键{'双击' if clicks == 2 else '单击'}完成"
    }


def double_click(button: Literal['left', 'right', 'middle'] = 'left'):
    """双击鼠标"""
    return click(button=button, clicks=2)


def right_click():
    """右键单击"""
    return click(button='right', clicks=1)


def middle_click():
    """中键单击"""
    return click(button='middle', clicks=1)


def press_down(button: Literal['left', 'right', 'middle'] = 'left'):
    """按下鼠标按钮（不释放）"""
    pyautogui.mouseDown(button=button)

    return {
        "success": True,
        "button": button,
        "message": f"鼠标{button}键已按下"
    }


def release(button: Literal['left', 'right', 'middle'] = 'left'):
    """释放鼠标按钮"""
    pyautogui.mouseUp(button=button)

    return {
        "success": True,
        "button": button,
        "message": f"鼠标{button}键已释放"
    }


def drag(start_x: int, start_y: int,
         end_x: int, end_y: int,
         button: Literal['left', 'right', 'middle'] = 'left',
         duration: float = 0.5):
    """
    拖拽鼠标（从起点到终点）

    Args:
        start_x, start_y: 起始坐标
        end_x, end_y: 结束坐标
        button: 使用的按钮
        duration: 拖拽持续时间(秒)
    """
    # 移动到起点
    move_to(start_x, start_y, duration=0.1)
    # 按下按钮
    pyautogui.mouseDown(button=button)
    # 拖拽到终点
    pyautogui.moveTo(end_x, end_y, duration=duration)
    # 释放按钮
    pyautogui.mouseUp(button=button)

    return {
        "success": True,
        "start": (start_x, start_y),
        "end": (end_x, end_y),
        "button": button,
        "message": f"从 ({start_x}, {start_y}) 拖拽到 ({end_x}, {end_y})"
    }


def drag_relative(dx: int, dy: int,
                  button: Literal['left', 'right', 'middle'] = 'left',
                  duration: float = 0.5):
    """
    相对拖拽（从当前位置开始）

    Args:
        dx, dy: 相对移动距离
        button: 使用的按钮
        duration: 拖拽持续时间(秒)
    """
    pyautogui.drag(dx, dy, duration=duration, button=button)

    return {
        "success": True,
        "delta": (dx, dy),
        "button": button,
        "message": f"相对拖拽 ({dx}, {dy})"
    }


def scroll(amount: int, x: Optional[int] = None, y: Optional[int] = None):
    """
    滚动鼠标滚轮

    Args:
        amount: 滚动量（正数向上，负数向下）
        x, y: 滚动位置的坐标（可选，默认为当前位置）
    """
    if x is not None and y is not None:
        move_to(x, y, duration=0.1)

    pyautogui.scroll(amount)

    return {
        "success": True,
        "amount": amount,
        "message": f"滚动 {abs(amount)} 步，方向: {'向上' if amount > 0 else '向下'}"
    }


def smooth_move_to(x: int, y: int, duration: float = 0.5, steps: int = 20):
    """
    平滑移动到指定位置（使用小步长移动）

    Args:
        x, y: 目标坐标
        duration: 移动持续时间
        steps: 移动步数
    """
    current_x, current_y = get_current_position()
    step_x = (x - current_x) / steps
    step_y = (y - current_y) / steps
    step_duration = duration / steps

    for i in range(steps):
        new_x = current_x + step_x * (i + 1)
        new_y = current_y + step_y * (i + 1)
        pyautogui.moveTo(new_x, new_y, duration=step_duration)
        time.sleep(0.01)

    return {
        "success": True,
        "position": (x, y),
        "message": f"平滑移动到 ({x}, {y})"
    }


def click_at(x: int, y: int,
             button: Literal['left', 'right', 'middle'] = 'left',
             clicks: int = 1):
    """
    移动到指定位置并点击

    Args:
        x, y: 点击位置坐标
        button: 按钮类型
        clicks: 点击次数
    """
    move_to(x, y, duration=0.1)
    time.sleep(0.05)
    return click(button=button, clicks=clicks)


# ========== 大模型工具函数（符合OpenAI Function Calling格式） ==========

def get_mouse_tools():
    """获取鼠标控制工具的定义（用于大模型）"""
    return [
        {
            "type": "function",
            "function": {
                "name": "mouse_move_to",
                "description": "移动鼠标到屏幕的指定位置（绝对坐标）",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "x": {
                            "type": "integer",
                            "description": "目标位置的X坐标（像素）"
                        },
                        "y": {
                            "type": "integer",
                            "description": "目标位置的Y坐标（像素）"
                        },
                        "duration": {
                            "type": "number",
                            "description": "移动的持续时间（秒），默认0.2",
                            "default": 0.2
                        }
                    },
                    "required": ["x", "y"]
                }
            }
        },
        {
            "type": "function",
            "function": {
                "name": "mouse_click",
                "description": "在当前位置单击鼠标",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "button": {
                            "type": "string",
                            "enum": ["left", "right", "middle"],
                            "description": "要点击的鼠标按钮，默认为左键",
                            "default": "left"
                        }
                    },
                    "required": []
                }
            }
        },
        {
            "type": "function",
            "function": {
                "name": "mouse_double_click",
                "description": "在当前位置双击鼠标",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "button": {
                            "type": "string",
                            "enum": ["left", "right", "middle"],
                            "description": "要双击的鼠标按钮，默认为左键",
                            "default": "left"
                        }
                    },
                    "required": []
                }
            }
        },
        {
            "type": "function",
            "function": {
                "name": "mouse_right_click",
                "description": "在当前位置右键单击",
                "parameters": {
                    "type": "object",
                    "properties": {},
                    "required": []
                }
            }
        },
        {
            "type": "function",
            "function": {
                "name": "mouse_drag",
                "description": "从起点拖拽鼠标到终点（按下并移动后释放）",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "start_x": {
                            "type": "integer",
                            "description": "拖拽起点的X坐标"
                        },
                        "start_y": {
                            "type": "integer",
                            "description": "拖拽起点的Y坐标"
                        },
                        "end_x": {
                            "type": "integer",
                            "description": "拖拽终点的X坐标"
                        },
                        "end_y": {
                            "type": "integer",
                            "description": "拖拽终点的Y坐标"
                        },
                        "button": {
                            "type": "string",
                            "enum": ["left", "right", "middle"],
                            "description": "拖拽时使用的按钮",
                            "default": "left"
                        },
                        "duration": {
                            "type": "number",
                            "description": "拖拽过程的持续时间（秒）",
                            "default": 0.5
                        }
                    },
                    "required": ["start_x", "start_y", "end_x", "end_y"]
                }
            }
        },
        {
            "type": "function",
            "function": {
                "name": "mouse_click_at",
                "description": "移动到指定位置并单击",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "x": {
                            "type": "integer",
                            "description": "目标位置的X坐标"
                        },
                        "y": {
                            "type": "integer",
                            "description": "目标位置的Y坐标"
                        },
                        "button": {
                            "type": "string",
                            "enum": ["left", "right", "middle"],
                            "description": "要点击的按钮",
                            "default": "left"
                        },
                        "clicks": {
                            "type": "integer",
                            "description": "点击次数（1或2）",
                            "enum": [1, 2],
                            "default": 1
                        }
                    },
                    "required": ["x", "y"]
                }
            }
        },
        {
            "type": "function",
            "function": {
                "name": "mouse_scroll",
                "description": "滚动鼠标滚轮",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "amount": {
                            "type": "integer",
                            "description": "滚动量，正数向上滚动，负数向下滚动"
                        },
                        "x": {
                            "type": "integer",
                            "description": "滚动位置的X坐标（可选，不指定则在当前位置滚动）"
                        },
                        "y": {
                            "type": "integer",
                            "description": "滚动位置的Y坐标（可选）"
                        }
                    },
                    "required": ["amount"]
                }
            }
        },
        {
            "type": "function",
            "function": {
                "name": "mouse_get_position",
                "description": "获取当前鼠标位置",
                "parameters": {
                    "type": "object",
                    "properties": {},
                    "required": []
                }
            }
        },
        {
            "type": "function",
            "function": {
                "name": "mouse_get_screen_size",
                "description": "获取屏幕尺寸",
                "parameters": {
                    "type": "object",
                    "properties": {},
                    "required": []
                }
            }
        }
    ]


def execute_mouse_tool(tool_name: str, arguments: dict):
    """执行鼠标控制工具"""
    try:
        if tool_name == "mouse_move_to":
            return move_to(
                arguments["x"],
                arguments["y"],
                arguments.get("duration", 0.2)
            )

        elif tool_name == "mouse_click":
            return click(arguments.get("button", "left"))

        elif tool_name == "mouse_double_click":
            return double_click(arguments.get("button", "left"))

        elif tool_name == "mouse_right_click":
            return right_click()

        elif tool_name == "mouse_drag":
            return drag(
                arguments["start_x"],
                arguments["start_y"],
                arguments["end_x"],
                arguments["end_y"],
                arguments.get("button", "left"),
                arguments.get("duration", 0.5)
            )

        elif tool_name == "mouse_click_at":
            return click_at(
                arguments["x"],
                arguments["y"],
                arguments.get("button", "left"),
                arguments.get("clicks", 1)
            )

        elif tool_name == "mouse_scroll":
            return scroll(
                arguments["amount"],
                arguments.get("x"),
                arguments.get("y")
            )

        elif tool_name == "mouse_get_position":
            pos = get_current_position()
            return {
                "success": True,
                "x": pos[0],
                "y": pos[1],
                "message": f"当前鼠标位置: ({pos[0]}, {pos[1]})"
            }

        elif tool_name == "mouse_get_screen_size":
            size = get_screen_size()
            return {
                "success": True,
                "width": size[0],
                "height": size[1],
                "message": f"屏幕尺寸: {size[0]} x {size[1]}"
            }

        else:
            return {
                "success": False,
                "error": f"未知的工具名称: {tool_name}"
            }

    except Exception as e:
        return {
            "success": False,
            "error": str(e),
            "message": f"执行工具 {tool_name} 时出错"
        }


# ========== 使用示例 ==========

if __name__ == "__main__":
    # 示例1：直接使用函数
    print("=== 鼠标控制工具演示 ===")

    # 获取屏幕信息
    print(f"屏幕尺寸: {get_screen_size()}")
    print(f"当前鼠标位置: {get_current_position()}")

    # 移动鼠标到屏幕中央
    screen = get_screen_size()
    center_x, center_y = screen[0] // 2, screen[1] // 2
    move_to(center_x, center_y)
    print(f"鼠标已移动到屏幕中央: ({center_x}, {center_y})")

    # 示例2：模拟大模型调用
    print("\n=== 模拟大模型调用 ===")

    # 获取工具定义
    tools = get_mouse_tools()
    print(f"已加载 {len(tools)} 个鼠标控制工具")

    # 模拟大模型返回的工具调用
    mock_calls = [
        ("mouse_get_screen_size", {}),
        ("mouse_move_to", {"x": 100, "y": 100, "duration": 0.3}),
        ("mouse_get_position", {}),
        ("mouse_click_at", {"x": 500, "y": 500, "button": "left"}),
        ("mouse_scroll", {"amount": 3}),
    ]

    for tool_name, args in mock_calls:
        print(f"\n调用工具: {tool_name}({args})")
        result = execute_mouse_tool(tool_name, args)
        print(f"结果: {result}")
        time.sleep(0.5)