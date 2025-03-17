"""
日志工具模块，提供日志记录功能
"""

import os
import sys
from enum import Enum
from typing import Dict, Any, Optional, List, Union
from loguru import logger

from tg_forwarder.utils.progress import ProgressBar, ProgressManager
from tg_forwarder.utils.log_filter import LogFilter, CommonFilters

# 定义日志级别
class LogLevel(str, Enum):
    TRACE = "TRACE"
    DEBUG = "DEBUG"
    INFO = "INFO"
    SUCCESS = "SUCCESS"
    WARNING = "WARNING"
    ERROR = "ERROR"
    CRITICAL = "CRITICAL"

class LogConfig:
    """日志配置类，用于存储和管理日志配置"""
    
    def __init__(self, config: Dict[str, Any] = None):
        """
        初始化日志配置
        
        Args:
            config: 日志配置字典
        """
        config = config or {}
        self.level = config.get('level', 'INFO').upper()
        self.file = config.get('file', 'logs/app.log')
        self.format = config.get('format', "default")
        self.filters = config.get('filters', [])
        self.show_progress = config.get('show_progress', True)
        self.console_output = config.get('console_output', True)
        self.file_output = config.get('file_output', True)
        self.rotation = config.get('rotation', "1 day")
        self.retention = config.get('retention', "7 days")
        self.compression = config.get('compression', "zip")
        self.enqueue = config.get('enqueue', True)
        self.colorize = config.get('colorize', True)

class EnhancedLogger:
    """增强型日志记录器，支持进度条和过滤器"""
    
    def __init__(self, name: str, config: LogConfig = None):
        """
        初始化日志记录器
        
        Args:
            name: 日志记录器名称
            config: 日志配置
        """
        self.name = name
        self.config = config or LogConfig()
        self.logger = logger.bind(name=name)
        
        # 初始化过滤器
        self.filter = LogFilter(self.config.filters)
    
    def log(self, level: Union[str, LogLevel], message: str) -> None:
        """
        记录日志
        
        Args:
            level: 日志级别
            message: 日志消息
        """
        # 如果当前有活跃的进度条，需要清空当前行
        active_progress_bar = ProgressManager.get_active_progress_bar()
        if active_progress_bar and active_progress_bar.visible:
            print("\r" + " " * 100 + "\r", end="", file=sys.stdout)
        
        # 记录日志
        if isinstance(level, LogLevel):
            level = level.value
            
        # 使用depth=1确保获取调用者的位置，而不是log函数本身的位置
        log_func = getattr(self.logger.opt(depth=1), level.lower())
        log_func(message)
        
        # 如果当前有活跃的进度条，需要重新显示
        if active_progress_bar and active_progress_bar.visible:
            active_progress_bar.update(0)
    
    def trace(self, message: str) -> None:
        """记录TRACE级别日志"""
        self.logger.opt(depth=1).trace(message)
    
    def debug(self, message: str) -> None:
        """记录DEBUG级别日志"""
        self.logger.opt(depth=1).debug(message)
    
    def info(self, message: str) -> None:
        """记录INFO级别日志"""
        self.logger.opt(depth=1).info(message)
    
    def success(self, message: str) -> None:
        """记录SUCCESS级别日志"""
        self.logger.opt(depth=1).success(message)
    
    def warning(self, message: str) -> None:
        """记录WARNING级别日志"""
        self.logger.opt(depth=1).warning(message)
    
    def error(self, message: str) -> None:
        """记录ERROR级别日志"""
        self.logger.opt(depth=1).error(message)
    
    def critical(self, message: str) -> None:
        """记录CRITICAL级别日志"""
        self.logger.opt(depth=1).critical(message)
    
    def create_progress_bar(self, id: str, total: int, desc: str = "", **kwargs) -> ProgressBar:
        """
        创建进度条
        
        Args:
            id: 进度条ID
            total: 总步骤数
            desc: 进度条描述
            **kwargs: 其他进度条参数
            
        Returns:
            ProgressBar: 进度条实例
        """
        if not self.config.show_progress:
            return None
            
        progress_bar = ProgressManager.create_progress_bar(id, total, desc, **kwargs)
        ProgressManager.set_active_progress_bar(id)
        return progress_bar
    
    def update_progress(self, id: str, step: int = 1) -> None:
        """
        更新指定ID的进度条
        
        Args:
            id: 进度条ID
            step: 步进值
        """
        ProgressManager.update_progress(id, step)
    
    def set_active_progress_bar(self, id: str) -> None:
        """
        设置活跃进度条
        
        Args:
            id: 进度条ID
        """
        ProgressManager.set_active_progress_bar(id)
    
    def close_progress_bar(self, id: str) -> None:
        """
        关闭进度条
        
        Args:
            id: 进度条ID
        """
        ProgressManager.close_progress_bar(id)
    
    def add_filter(self, pattern: str) -> None:
        """
        添加过滤模式
        
        Args:
            pattern: 过滤模式，支持正则表达式
        """
        self.filter.add_pattern(pattern)
    
    def clear_filters(self) -> None:
        """清除所有过滤器"""
        self.filter.clear()
    
    def enable_ffmpeg_filter(self) -> None:
        """启用ffmpeg输出过滤"""
        ffmpeg_filter = CommonFilters.get_ffmpeg_filter()
        for pattern in ffmpeg_filter.patterns:
            self.add_filter(pattern)
    
    def enable_system_filter(self) -> None:
        """启用系统日志过滤"""
        system_filter = CommonFilters.get_system_filter()
        for pattern in system_filter.patterns:
            self.add_filter(pattern)
    
    def enable_telegram_api_filter(self) -> None:
        """启用Telegram API日志过滤"""
        telegram_filter = CommonFilters.get_telegram_api_filter()
        for pattern in telegram_filter.patterns:
            self.add_filter(pattern)

# 全局日志管理器
class LogManager:
    """日志管理器，管理所有日志记录器"""
    
    _instance = None
    _loggers = {}
    _global_config = LogConfig()
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(LogManager, cls).__new__(cls)
        return cls._instance
    
    @classmethod
    def setup(cls, config: Dict[str, Any] = None) -> None:
        """
        设置全局日志配置
        
        Args:
            config: 日志配置字典
        """
        if config:
            cls._global_config = LogConfig(config)
        
        # 确保日志目录存在
        log_dir = os.path.dirname(cls._global_config.file)
        if not os.path.exists(log_dir):
            os.makedirs(log_dir, exist_ok=True)
        
        # 清除默认的handler
        logger.remove()
        
        # 添加控制台输出
        if cls._global_config.console_output:
            logger.add(
                sys.stdout,
                level=cls._global_config.level,
                format="<green>{time:YYYY-MM-DD HH:mm:ss.SSS}</green> | <level>{level: <8}</level> | <cyan>{extra[name]}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> - <level>{message}</level>",
                colorize=cls._global_config.colorize,
                filter=LogFilter(cls._global_config.filters).filter
            )
        
        # 添加文件输出
        if cls._global_config.file_output:
            logger.add(
                cls._global_config.file,
                level=cls._global_config.level,
                format="{time:YYYY-MM-DD HH:mm:ss.SSS} | {level: <8} | {extra[name]}:{function}:{line} - {message}",
                rotation=cls._global_config.rotation,
                retention=cls._global_config.retention,
                compression=cls._global_config.compression,
                enqueue=cls._global_config.enqueue,
                filter=LogFilter(cls._global_config.filters).filter
            )
        
        logger.info(f"日志系统初始化完成，级别：{cls._global_config.level}, 文件：{cls._global_config.file}")
    
    @classmethod
    def get_logger(cls, name: str = None) -> EnhancedLogger:
        """
        获取指定名称的日志记录器
        
        Args:
            name: 日志记录器名称，默认为"main"
            
        Returns:
            EnhancedLogger: 增强型日志记录器实例
        """
        name = name or "main"
        
        if name not in cls._loggers:
            cls._loggers[name] = EnhancedLogger(name, cls._global_config)
        
        return cls._loggers[name]
    
    @classmethod
    def set_global_level(cls, level: Union[str, LogLevel]) -> None:
        """
        设置全局日志级别
        
        Args:
            level: 日志级别
        """
        if isinstance(level, LogLevel):
            level = level.value
            
        cls._global_config.level = level
        # 重新配置所有处理器的日志级别
        for handler_id in logger._core.handlers:
            logger.configure(handlers=[{"id": handler_id, "level": level}])
    
    @classmethod
    def add_global_filter(cls, pattern: str) -> None:
        """
        添加全局过滤模式
        
        Args:
            pattern: 过滤模式，支持正则表达式
        """
        cls._global_config.filters.append(pattern)
        cls.setup()  # 重新配置以应用新过滤器
    
    @classmethod
    def clear_global_filters(cls) -> None:
        """清除所有全局过滤器"""
        cls._global_config.filters = []
        cls.setup()  # 重新配置以应用新过滤器
    
    @classmethod
    def enable_ffmpeg_filter(cls) -> None:
        """在全局范围内启用ffmpeg输出过滤"""
        ffmpeg_filter = CommonFilters.get_ffmpeg_filter()
        for pattern in ffmpeg_filter.patterns:
            cls.add_global_filter(pattern)
    
    @classmethod
    def enable_system_filter(cls) -> None:
        """在全局范围内启用系统日志过滤"""
        system_filter = CommonFilters.get_system_filter()
        for pattern in system_filter.patterns:
            cls.add_global_filter(pattern)
    
    @classmethod
    def enable_telegram_api_filter(cls) -> None:
        """在全局范围内启用Telegram API日志过滤"""
        telegram_filter = CommonFilters.get_telegram_api_filter()
        for pattern in telegram_filter.patterns:
            cls.add_global_filter(pattern)

# 为了向后兼容，保留原来的函数
def setup_logger(config: Dict[str, Any] = None) -> None:
    """
    设置日志记录器（向后兼容函数）
    
    Args:
        config: 日志配置信息
    """
    LogManager.setup(config)

def get_logger(name: Optional[str] = None):
    """
    获取指定名称的日志记录器（向后兼容函数）
    
    Args:
        name: 日志记录器名称
    
    Returns:
        EnhancedLogger: 增强型日志记录器实例或者兼容原始接口的logger
    """
    return LogManager.get_logger(name) 