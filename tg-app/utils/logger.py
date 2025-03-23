"""
日志配置和管理模块。

本模块负责配置和管理应用程序的日志系统，使用loguru库实现。
提供统一的日志记录接口，支持不同级别的日志和日志文件轮转。
"""

import os
import sys
from typing import Dict, Any, Optional

from loguru import logger

# 默认日志配置
DEFAULT_CONFIG = {
    "level": "INFO",
    "file_path": "logs/app.log",
    "rotation": "10 MB",
    "retention": "30 days",
    "compression": "zip",
    "use_console": True,
    "errors_file": "logs/error.log"
}

# 日志级别映射
LOG_LEVELS = {
    "TRACE": 5,
    "DEBUG": 10,
    "INFO": 20,
    "SUCCESS": 25,
    "WARNING": 30,
    "ERROR": 40,
    "CRITICAL": 50
}

# 全局配置
_config = DEFAULT_CONFIG.copy()

def setup_logger(config: Optional[Dict[str, Any]] = None) -> None:
    """
    设置日志配置。
    
    Args:
        config: 日志配置字典，可包含以下字段：
            - level: 日志级别 (TRACE, DEBUG, INFO, SUCCESS, WARNING, ERROR, CRITICAL)
            - file_path: 日志文件路径
            - rotation: 日志轮转策略 (如 "10 MB", "1 day")
            - retention: 日志保留策略 (如 "30 days")
            - compression: 日志压缩格式 (如 "zip")
            - use_console: 是否输出到控制台
            - errors_file: 错误日志文件路径 (只记录ERROR及以上级别的日志)
    """
    global _config
    
    if config:
        _config.update(config)
        
    # 清除已有的处理器
    logger.remove()
    
    # 确保日志目录存在
    os.makedirs(os.path.dirname(os.path.abspath(_config["file_path"])), exist_ok=True)
    if _config["errors_file"]:
        os.makedirs(os.path.dirname(os.path.abspath(_config["errors_file"])), exist_ok=True)
    
    # 设置日志级别
    level = _config["level"].upper() if isinstance(_config["level"], str) else _config["level"]
    level_no = LOG_LEVELS.get(level, level) if isinstance(level, str) else level
    
    # 添加控制台处理器
    if _config["use_console"]:
        logger.add(
            sys.stderr,
            level=level,
            format="<green>{time:YYYY-MM-DD HH:mm:ss.SSS}</green> | <level>{level: <8}</level> | <cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> - <level>{message}</level>"
        )
    
    # 添加文件处理器
    logger.add(
        _config["file_path"],
        level=level,
        format="{time:YYYY-MM-DD HH:mm:ss.SSS} | {level: <8} | {name}:{function}:{line} - {message}",
        rotation=_config["rotation"],
        retention=_config["retention"],
        compression=_config["compression"],
        encoding="utf-8"
    )
    
    # 添加错误日志文件处理器
    if _config["errors_file"]:
        logger.add(
            _config["errors_file"],
            level="ERROR",
            format="{time:YYYY-MM-DD HH:mm:ss.SSS} | {level: <8} | {name}:{function}:{line} - {message}",
            rotation=_config["rotation"],
            retention=_config["retention"],
            compression=_config["compression"],
            encoding="utf-8"
        )
        
    logger.info(f"日志系统已配置，级别: {level}, 文件: {_config['file_path']}")

def get_logger(name: str) -> logger:
    """
    获取指定名称的日志记录器。
    
    Args:
        name: 日志记录器名称，通常为模块或类名
        
    Returns:
        loguru.logger 的绑定实例
    """
    return logger.bind(name=name)


# 初始设置
setup_logger() 