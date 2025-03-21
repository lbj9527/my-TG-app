"""
日志接口抽象
定义了日志记录和管理的必要方法
"""

from abc import ABC, abstractmethod
from typing import Dict, Any, Optional, Union, Callable


class LoggerInterface(ABC):
    """
    日志接口，定义了日志记录和管理的必要方法
    所有日志实现都应该继承此接口
    """
    
    @abstractmethod
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
        pass
    
    @abstractmethod
    def shutdown(self) -> None:
        """关闭日志系统"""
        pass
    
    @abstractmethod
    def debug(self, message: str, **kwargs) -> None:
        """
        记录调试日志
        
        Args:
            message: 日志消息
            **kwargs: 额外参数
        """
        pass
    
    @abstractmethod
    def info(self, message: str, **kwargs) -> None:
        """
        记录信息日志
        
        Args:
            message: 日志消息
            **kwargs: 额外参数
        """
        pass
    
    @abstractmethod
    def warning(self, message: str, **kwargs) -> None:
        """
        记录警告日志
        
        Args:
            message: 日志消息
            **kwargs: 额外参数
        """
        pass
    
    @abstractmethod
    def error(self, message: str, exc_info: bool = False, **kwargs) -> None:
        """
        记录错误日志
        
        Args:
            message: 日志消息
            exc_info: 是否包含异常信息
            **kwargs: 额外参数
        """
        pass
    
    @abstractmethod
    def critical(self, message: str, exc_info: bool = True, **kwargs) -> None:
        """
        记录严重错误日志
        
        Args:
            message: 日志消息
            exc_info: 是否包含异常信息
            **kwargs: 额外参数
        """
        pass
    
    @abstractmethod
    def exception(self, message: str, **kwargs) -> None:
        """
        记录异常日志
        
        Args:
            message: 日志消息
            **kwargs: 额外参数
        """
        pass
    
    @abstractmethod
    def set_level(self, level: str) -> None:
        """
        设置日志级别
        
        Args:
            level: 日志级别
        """
        pass
    
    @abstractmethod
    def add_handler(self, handler: Any) -> None:
        """
        添加日志处理器
        
        Args:
            handler: 日志处理器
        """
        pass
    
    @abstractmethod
    def remove_handler(self, handler: Any) -> None:
        """
        移除日志处理器
        
        Args:
            handler: 日志处理器
        """
        pass
    
    @abstractmethod
    def get_logger(self, name: str) -> Any:
        """
        获取命名日志器
        
        Args:
            name: 日志器名称
            
        Returns:
            Any: 日志器实例
        """
        pass 