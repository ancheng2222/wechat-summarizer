"""
调度模块 —— 定时触发 + 守护进程
"""
import os
import sys
import subprocess
import time
from datetime import datetime
from loguru import logger

PROJECT_DIR = os.path.dirname(os.path.dirname(__file__))


def create_windows_task(task_name: str, schedule_time: str, python_path: str) -> bool:
    """
    创建 Windows 计划任务，每日定时运行。
    - task_name: 任务名称
    - schedule_time: "HH:MM" 格式
    - python_path: Python 解释器路径
    """
    main_script = os.path.join(PROJECT_DIR, "main.py")
    h, m = schedule_time.split(":")

    cmd = [
        "schtasks", "/Create", "/SC", "DAILY",
        "/TN", task_name,
        "/TR", f'"{python_path}" "{main_script}" --once',
        "/ST", f"{h}:{m}",
        "/F",  # 强制覆盖同名任务
    ]

    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        if result.returncode == 0:
            logger.info(f"已创建计划任务 '{task_name}'，每日 {schedule_time} 运行")
            return True
        else:
            logger.error(f"创建计划任务失败: {result.stderr}")
            return False
    except Exception as e:
        logger.error(f"创建计划任务异常: {e}")
        return False


def remove_windows_task(task_name: str) -> bool:
    """删除 Windows 计划任务"""
    try:
        result = subprocess.run(
            ["schtasks", "/Delete", "/TN", task_name, "/F"],
            capture_output=True, text=True, timeout=10,
        )
        return result.returncode == 0
    except Exception:
        return False


def check_task_exists(task_name: str) -> bool:
    """检查计划任务是否存在"""
    try:
        result = subprocess.run(
            ["schtasks", "/Query", "/TN", task_name],
            capture_output=True, text=True, timeout=10,
        )
        return result.returncode == 0
    except Exception:
        return False


def run_daemon(config: dict):
    """
    守护进程模式 —— 使用 schedule 库在进程内循环等待。
    适合调试场景。
    """
    try:
        import schedule
    except ImportError:
        logger.error("请安装 schedule: pip install schedule")
        return

    from main import run_once

    schedule_time = config.get("schedule_time", "22:00")
    task_name = config.get("task_name", "微信群聊摘要")
    logger.info(f"守护进程启动，将在每日 {schedule_time} 运行 —— {task_name}")

    schedule.every().day.at(schedule_time).do(
        lambda: run_once(config)
    )

    while True:
        schedule.run_pending()
        time.sleep(60)  # 每分钟检查一次


def get_python_path() -> str:
    """获取当前 Python 解释器路径"""
    return sys.executable
