#!/usr/bin/env python3
"""
应用入口点。

本文件是应用的主入口点，负责启动整个应用程序。
"""

import sys
import os
import argparse
import asyncio
import signal
from pathlib import Path

# 添加当前目录到Python路径
current_dir = Path(__file__).resolve().parent
if str(current_dir) not in sys.path:
    sys.path.insert(0, str(current_dir))

from utils.logger import setup_logger, get_logger

# 获取日志记录器
logger = get_logger("main")


def parse_arguments():
    """
    解析命令行参数。
    
    Returns:
        argparse.Namespace: 解析后的参数
    """
    parser = argparse.ArgumentParser(description='Telegram功能增强工具')
    parser.add_argument('-c', '--config', help='配置文件路径')
    parser.add_argument('-l', '--log-level', choices=['DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL'],
                      default='INFO', help='日志级别')
    parser.add_argument('-v', '--version', action='store_true', help='显示版本信息')
    
    return parser.parse_args()


def show_version():
    """显示版本信息"""
    print("my-TG-app v0.1.0")
    print("基于插件架构的Telegram功能增强工具")
    print("Copyright © 2023")


def main():
    """应用主函数"""
    # 解析命令行参数
    args = parse_arguments()
    
    # 显示版本信息并退出
    if args.version:
        show_version()
        return 0
    
    # 设置日志级别
    setup_logger(log_level=args.log_level)
    
    logger.info("启动 my-TG-app")
    
    # 动态导入应用程序模块
    try:
        from core.application import run_application
        return run_application()
    except ImportError as e:
        logger.critical(f"导入错误: {str(e)}")
        return 1
    except Exception as e:
        logger.critical(f"应用运行时出现未捕获的异常: {str(e)}", exc_info=True)
        return 1


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        print("\n程序被用户中断")
        sys.exit(130) 