"""
日志工具模块，提供日志记录功能
"""

import os
import sys
from loguru import logger
from typing import Dict, Any, Optional

def setup_logger(config: Dict[str, Any]) -> None:
    """
    设置日志记录器
    
    Args:
        config: 日志配置信息
    """
    # 获取日志级别
    log_level = config.get('level', 'INFO').upper()
    log_file = config.get('file', 'logs/app.log')
    
    # 确保日志目录存在
    log_dir = os.path.dirname(log_file)
    if not os.path.exists(log_dir):
        os.makedirs(log_dir, exist_ok=True)
    
    # 清除默认的handler
    logger.remove()
    
    # 添加控制台输出
    logger.add(
        sys.stdout,
        level=log_level,
        format="<green>{time:YYYY-MM-DD HH:mm:ss}</green> | <level>{level: <8}</level> | <cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> - <level>{message}</level>",
        colorize=True
    )
    
    # 添加文件输出
    logger.add(
        log_file,
        level=log_level,
        format="{time:YYYY-MM-DD HH:mm:ss} | {level: <8} | {name}:{function}:{line} - {message}",
        rotation="1 day",
        retention="7 days",
        compression="zip",
        enqueue=True
    )
    
    logger.info(f"日志系统初始化完成，级别：{log_level}, 文件：{log_file}")

def get_logger(name: Optional[str] = None):
    """
    获取指定名称的日志记录器
    
    Args:
        name: 日志记录器名称
    
    Returns:
        Logger: 日志记录器实例
    """
    return logger.bind(name=name or "main") 