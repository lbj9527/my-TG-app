"""
日志模块，提供统一的日志记录功能
"""

import os
import sys
import datetime
from enum import Enum
from typing import Dict, Any, Optional
from pathlib import Path

from loguru import logger

# 日志级别枚举
class LogLevel(str, Enum):
    """日志级别"""
    TRACE = "TRACE"
    DEBUG = "DEBUG"
    INFO = "INFO"
    SUCCESS = "SUCCESS"
    WARNING = "WARNING"
    ERROR = "ERROR"
    CRITICAL = "CRITICAL"

class LogManager:
    """日志管理器，单例模式管理所有日志配置"""
    
    _instance = None
    _initialized = False
    _logger = logger
    _default_format = "<green>{time:YYYY-MM-DD HH:mm:ss.SSS}</green> | <level>{level: <8}</level> | <cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> | <level>{message}</level>"
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(LogManager, cls).__new__(cls)
        return cls._instance
    
    def __init__(self):
        if not LogManager._initialized:
            self._setup_default_logger()
            LogManager._initialized = True
    
    def _setup_default_logger(self):
        """设置默认日志配置"""
        # 清除所有默认处理器
        self._logger.remove()
        
        # 添加控制台处理器
        self._logger.add(
            sys.stderr,
            format=self._default_format,
            level="INFO",
            colorize=True
        )
    
    def setup(self, config: Dict[str, Any] = None):
        """
        配置日志系统
        
        Args:
            config: 日志配置字典，包含以下可选参数：
                - level: 日志级别，默认为 "INFO"
                - file: 日志文件路径，默认为 "logs/app.log"
                - rotation: 日志轮转策略，默认为 "10 MB"
                - retention: 日志保留策略，默认为 "30 days"
                - format: 日志格式，默认使用内置格式
                - use_console: 是否输出到控制台，默认为 True
        """
        # 使用默认配置
        if config is None:
            config = {}
        
        # 获取配置参数
        level = config.get('level', "INFO").upper()
        log_file = config.get('file', "logs/app.log")
        rotation = config.get('rotation', "10 MB")
        retention = config.get('retention', "30 days")
        compression = config.get('compression', "zip")
        log_format = config.get('format', self._default_format)
        use_console = config.get('use_console', True)
        
        # 清除所有处理器
        self._logger.remove()
        
        # 添加控制台处理器
        if use_console:
            self._logger.add(
                sys.stderr,
                format=log_format,
                level=level,
                colorize=True
            )
        
        # 确保日志目录存在
        log_path = Path(log_file)
        log_path.parent.mkdir(parents=True, exist_ok=True)
        
        # 添加文件处理器
        self._logger.add(
            log_file,
            format=log_format,
            level=level,
            rotation=rotation,
            retention=retention,
            compression=compression,
            backtrace=True,
            diagnose=True
        )
        
        # 添加错误日志文件
        error_log_file = str(log_path.parent / f"error_{log_path.name}")
        self._logger.add(
            error_log_file,
            format=log_format,
            level="ERROR",
            rotation=rotation,
            retention=retention,
            compression=compression,
            backtrace=True,
            diagnose=True
        )
        
        # 记录日志配置完成
        self._logger.success(f"日志系统初始化完成 - 级别: {level}, 文件: {log_file}")
    
    def get_logger(self, name: Optional[str] = None) -> logger.__class__:
        """
        获取日志记录器
        
        Args:
            name: 日志记录器名称，用于识别日志来源
            
        Returns:
            logger.__class__: 日志记录器实例
        """
        if name:
            return self._logger.bind(name=name)
        return self._logger

# 全局日志管理器实例
_log_manager = LogManager()

def setup_logger(config: Dict[str, Any] = None) -> None:
    """
    配置日志系统的快捷方法
    
    Args:
        config: 日志配置字典
    """
    _log_manager.setup(config)

def get_logger(name: Optional[str] = None) -> logger.__class__:
    """
    获取日志记录器的快捷方法
    
    Args:
        name: 日志记录器名称
        
    Returns:
        logger.__class__: 日志记录器实例
    """
    return _log_manager.get_logger(name) 