"""
日志记录器实现类
提供统一的日志记录功能
"""

import os
import sys
from typing import Dict, Any, Optional, List
from pathlib import Path

from loguru import logger

from tg_forwarder.interfaces.logger_interface import LoggerInterface


class Logger(LoggerInterface):
    """
    日志记录器，实现LoggerInterface接口
    提供统一的日志记录功能，基于loguru库
    """
    
    def __init__(self):
        """初始化日志记录器"""
        self._logger = logger
        self._handlers_ids = []
        self._default_format = "<green>{time:YYYY-MM-DD HH:mm:ss.SSS}</green> | <level>{level: <8}</level> | <cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> | <level>{message}</level>"
        self._initialized = False
    
    def initialize(self, log_file: Optional[str] = None, 
                  log_level: str = "INFO", 
                  rotation: str = "10 MB") -> bool:
        """
        初始化日志系统
        
        Args:
            log_file: 日志文件路径，None为控制台输出
            log_level: 日志级别
            rotation: 日志轮换策略
            
        Returns:
            bool: 初始化是否成功
        """
        try:
            # 移除所有现有的处理器
            self._remove_all_handlers()
            
            # 添加控制台处理器
            self._add_console_handler(log_level)
            
            # 如果指定了日志文件，添加文件处理器
            if log_file:
                self._add_file_handler(log_file, log_level, rotation)
            
            self._initialized = True
            self.info("日志系统初始化完成", system="日志")
            return True
        except Exception as e:
            # 初始化失败时打印到控制台
            print(f"日志系统初始化失败: {str(e)}")
            self._initialized = False
            return False
    
    def shutdown(self) -> None:
        """关闭日志系统"""
        self._remove_all_handlers()
        self._initialized = False
    
    def debug(self, message: str, **kwargs) -> None:
        """
        记录调试日志
        
        Args:
            message: 日志消息
            **kwargs: 额外参数
        """
        self._logger.debug(message, **kwargs)
    
    def info(self, message: str, **kwargs) -> None:
        """
        记录信息日志
        
        Args:
            message: 日志消息
            **kwargs: 额外参数
        """
        self._logger.info(message, **kwargs)
    
    def warning(self, message: str, **kwargs) -> None:
        """
        记录警告日志
        
        Args:
            message: 日志消息
            **kwargs: 额外参数
        """
        self._logger.warning(message, **kwargs)
    
    def error(self, message: str, exc_info: bool = False, **kwargs) -> None:
        """
        记录错误日志
        
        Args:
            message: 日志消息
            exc_info: 是否包含异常信息
            **kwargs: 额外参数
        """
        self._logger.opt(exception=exc_info).error(message, **kwargs)
    
    def critical(self, message: str, exc_info: bool = True, **kwargs) -> None:
        """
        记录严重错误日志
        
        Args:
            message: 日志消息
            exc_info: 是否包含异常信息
            **kwargs: 额外参数
        """
        self._logger.opt(exception=exc_info).critical(message, **kwargs)
    
    def exception(self, message: str, **kwargs) -> None:
        """
        记录异常日志
        
        Args:
            message: 日志消息
            **kwargs: 额外参数
        """
        self._logger.exception(message, **kwargs)
    
    def set_level(self, level: str) -> None:
        """
        设置日志级别
        
        Args:
            level: 日志级别
        """
        for handler_id in self._handlers_ids:
            self._logger.level(handler_id, level.upper())
    
    def add_handler(self, handler: Any) -> None:
        """
        添加日志处理器
        
        Args:
            handler: 日志处理器配置，字典格式，包含：
                - sink: 日志输出目标
                - level: 日志级别
                - format: 日志格式
                - 其他loguru支持的参数
        """
        if not isinstance(handler, dict) or 'sink' not in handler:
            raise ValueError("处理器必须是包含'sink'的字典")
        
        handler_format = handler.get('format', self._default_format)
        handler_level = handler.get('level', "INFO").upper()
        
        handler_id = self._logger.add(
            handler['sink'],
            format=handler_format,
            level=handler_level,
            **{k: v for k, v in handler.items() if k not in ('sink', 'format', 'level')}
        )
        
        self._handlers_ids.append(handler_id)
    
    def remove_handler(self, handler: Any) -> None:
        """
        移除日志处理器
        
        Args:
            handler: 处理器ID或处理器对象
        """
        if handler in self._handlers_ids:
            self._logger.remove(handler)
            self._handlers_ids.remove(handler)
    
    def get_logger(self, name: str) -> Any:
        """
        获取命名日志器
        
        Args:
            name: 日志器名称
            
        Returns:
            Any: 日志器实例
        """
        return self._logger.bind(name=name)
    
    def _remove_all_handlers(self) -> None:
        """移除所有处理器"""
        # 先记录所有处理器ID
        self._handlers_ids = []
        # 清除所有处理器
        self._logger.remove()
    
    def _add_console_handler(self, level: str) -> None:
        """
        添加控制台处理器
        
        Args:
            level: 日志级别
        """
        handler_id = self._logger.add(
            sys.stderr,
            format=self._default_format,
            level=level.upper(),
            colorize=True
        )
        self._handlers_ids.append(handler_id)
    
    def _add_file_handler(self, log_file: str, level: str, rotation: str) -> None:
        """
        添加文件处理器
        
        Args:
            log_file: 日志文件路径
            level: 日志级别
            rotation: 日志轮换策略
        """
        # 确保日志目录存在
        log_path = Path(log_file)
        log_path.parent.mkdir(parents=True, exist_ok=True)
        
        # 添加常规日志文件处理器
        handler_id = self._logger.add(
            log_file,
            format=self._default_format,
            level=level.upper(),
            rotation=rotation,
            retention="30 days",
            compression="zip",
            backtrace=True,
            diagnose=True
        )
        self._handlers_ids.append(handler_id)
        
        # 添加错误日志文件处理器
        error_log_file = str(log_path.parent / f"error_{log_path.name}")
        handler_id = self._logger.add(
            error_log_file,
            format=self._default_format,
            level="ERROR",
            rotation=rotation,
            retention="30 days",
            compression="zip",
            backtrace=True,
            diagnose=True
        )
        self._handlers_ids.append(handler_id) 