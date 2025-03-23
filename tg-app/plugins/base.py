"""
插件基类模块。

本模块定义了所有插件的基类，提供插件管理的统一接口和共同功能。
所有具体的插件实现都应该继承自这个基类。
"""

import abc
import uuid
import inspect
from typing import Dict, Any, List, Optional, Set, ClassVar, Type

from core.event_bus import EventBus
from utils.logger import get_logger

# 获取日志记录器
logger = get_logger("plugin_base")


class PluginBase(abc.ABC):
    """
    插件基类，定义所有插件的通用接口和基本功能。
    
    每个具体的插件实现必须继承此类，并实现必要的抽象方法。
    """
    
    # 类级别属性，可被子类覆盖
    id: ClassVar[str] = "base_plugin"
    name: ClassVar[str] = "基础插件"
    version: ClassVar[str] = "0.1.0"
    description: ClassVar[str] = "插件基类，不应直接使用"
    dependencies: ClassVar[List[str]] = []
    
    def __init__(self, event_bus: EventBus):
        """
        初始化插件。
        
        Args:
            event_bus: 事件总线实例
        """
        self._event_bus = event_bus
        self._logger = get_logger(f"plugin.{self.id}")
        
        # 插件是否已初始化
        self._initialized = False
        
        # 存储插件的订阅事件处理器ID {事件类型: 处理器ID}
        self._event_handlers: Dict[str, str] = {}
        
        # 插件配置
        self._config: Dict[str, Any] = {}
        
        self._logger.debug(f"创建插件实例: {self.id} ({self.name})")
    
    @classmethod
    def get_id_from_class(cls) -> str:
        """
        获取类级别的插件ID。
        
        用于在插件发现阶段标识插件。
        
        Returns:
            str: 插件ID
        """
        return cls.id
    
    @property
    def event_bus(self) -> EventBus:
        """获取事件总线实例"""
        return self._event_bus
    
    @abc.abstractmethod
    async def initialize(self) -> None:
        """
        初始化插件。
        
        在这个方法中完成以下工作：
        1. 注册事件处理器
        2. 加载插件配置
        3. 初始化资源
        
        这个方法在插件加载时由插件管理器调用。
        
        Raises:
            Exception: 初始化失败
        """
        if self._initialized:
            return
        
        self._logger.info(f"初始化插件: {self.id} ({self.name} v{self.version})")
        self._initialized = True
    
    @abc.abstractmethod
    async def shutdown(self) -> None:
        """
        关闭插件。
        
        在这个方法中完成以下工作：
        1. 取消注册事件处理器
        2. 保存插件配置
        3. 释放资源
        
        这个方法在插件卸载时由插件管理器调用。
        """
        self._logger.info(f"关闭插件: {self.id} ({self.name})")
        
        # 取消注册所有事件处理器
        for event_type, handler_id in self._event_handlers.items():
            self._event_bus.unsubscribe_by_id(event_type, handler_id)
            
        self._event_handlers.clear()
        self._initialized = False
    
    def get_metadata(self) -> Dict[str, Any]:
        """
        获取插件元数据。
        
        Returns:
            Dict[str, Any]: 包含插件信息的字典
        """
        return {
            "id": self.id,
            "name": self.name,
            "version": self.version,
            "description": self.description,
            "dependencies": self.dependencies,
            "initialized": self._initialized
        }
    
    async def _handle_event(self, event_data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """
        通用事件处理方法，可被子类覆盖或扩展。
        
        Args:
            event_data: 事件数据
            
        Returns:
            Optional[Dict[str, Any]]: 事件响应数据，如果不需要响应则返回None
        """
        event_type = event_data.get("event_type", "unknown")
        self._logger.debug(f"收到事件: {event_type}")
        return None
    
    def register_event_handler(self, event_type: str, handler=None):
        """
        注册事件处理器，支持装饰器模式。
        
        Args:
            event_type: 事件类型
            handler: 事件处理函数，如果为None则用作装饰器
            
        Returns:
            函数装饰器或None
        """
        def decorator(func):
            # 确保处理器是异步函数
            if not inspect.iscoroutinefunction(func):
                self._logger.warning(f"事件处理器不是异步函数: {func.__name__}，将被包装")
                
                # 包装为异步函数
                async def wrapper(event_data):
                    return func(event_data)
                
                wrapper.__name__ = func.__name__
                wrapper.__qualname__ = func.__qualname__
                handler_func = wrapper
            else:
                handler_func = func
            
            # 如果已经订阅了这个事件，先取消订阅
            if event_type in self._event_handlers:
                self._event_bus.unsubscribe_by_id(event_type, self._event_handlers[event_type])
                
            # 订阅事件
            handler_id = self._event_bus.subscribe(event_type, handler_func)
            
            # 记录处理器ID
            self._event_handlers[event_type] = handler_id
            
            self._logger.debug(f"注册事件处理器: {event_type} -> {func.__name__}")
            return func
        
        # 如果直接提供了处理器函数，立即注册
        if handler is not None:
            return decorator(handler)
        
        # 否则返回装饰器
        return decorator
    
    def unregister_event_handler(self, event_type: str) -> bool:
        """
        取消注册事件处理器。
        
        Args:
            event_type: 事件类型
            
        Returns:
            bool: 是否成功取消注册
        """
        if event_type not in self._event_handlers:
            self._logger.warning(f"未注册的事件处理器: {event_type}")
            return False
            
        handler_id = self._event_handlers[event_type]
        success = self._event_bus.unsubscribe_by_id(event_type, handler_id)
        
        if success:
            del self._event_handlers[event_type]
            self._logger.debug(f"已取消注册事件处理器: {event_type}")
            
        return success
    
    async def publish_event(self, event_type: str, data: Optional[Dict[str, Any]] = None) -> int:
        """
        发布事件。
        
        Args:
            event_type: 事件类型
            data: 事件数据
            
        Returns:
            int: 接收事件的处理器数量
        """
        if data is None:
            data = {}
            
        # 添加插件ID到事件数据
        data["source_plugin"] = self.id
        
        return await self._event_bus.publish(event_type, data)
    
    async def publish_and_wait(
        self, 
        event_type: str, 
        data: Optional[Dict[str, Any]] = None,
        timeout: float = 30.0
    ) -> Optional[Dict[str, Any]]:
        """
        发布事件并等待响应。
        
        Args:
            event_type: 事件类型
            data: 事件数据
            timeout: 超时时间（秒）
            
        Returns:
            Optional[Dict[str, Any]]: 事件响应数据，如果超时或没有响应则返回None
        """
        if data is None:
            data = {}
            
        # 添加插件ID到事件数据
        data["source_plugin"] = self.id
        
        return await self._event_bus.publish_and_wait(event_type, data, timeout)
    
    def __str__(self) -> str:
        """返回插件的字符串表示"""
        return f"{self.name} (ID: {self.id}, 版本: {self.version})" 