"""
事件总线模块。

本模块实现了事件总线，用于事件的发布和订阅，支持异步操作。
事件总线是整个应用的消息中心，负责组件间的通信。
"""

import asyncio
import uuid
import time
import inspect
from typing import Dict, Any, List, Callable, Optional, Set, Tuple, Coroutine
from functools import wraps

# 修改导入语句
from utils.logger import get_logger

# 获取日志记录器
logger = get_logger("event_bus")

# 事件处理器类型
EventHandler = Callable[[Dict[str, Any]], Coroutine[Any, Any, Dict[str, Any]]]


class EventBus:
    """
    事件总线，负责事件的发布和订阅。
    
    支持异步事件处理，可以等待事件处理结果。
    """
    
    def __init__(self):
        """初始化事件总线"""
        # 事件处理器映射 {事件类型: {处理器ID: 处理器函数}}
        self._handlers: Dict[str, Dict[str, EventHandler]] = {}
        
        # 等待中的事件响应 {响应ID: 响应Future}
        self._waiting_responses: Dict[str, asyncio.Future] = {}
        
        # 事件统计信息
        self._stats = {
            "published": 0,  # 已发布事件总数
            "handled": 0,  # 已处理事件总数
            "subscribers": 0,  # 订阅者总数
            "start_time": time.time()  # 启动时间
        }
        
        logger.info("事件总线已初始化")
    
    def subscribe(self, event_type: str, handler: EventHandler) -> str:
        """
        订阅事件。
        
        Args:
            event_type: 事件类型
            handler: 事件处理函数，必须是一个接受事件数据(dict)的异步函数
            
        Returns:
            str: 处理器ID，可用于取消订阅
        """
        # 验证处理器是否是异步函数
        if not inspect.iscoroutinefunction(handler):
            logger.warning(f"事件处理器不是异步函数: {handler.__qualname__}")
            
        # 初始化事件类型的处理器字典
        if event_type not in self._handlers:
            self._handlers[event_type] = {}
            
        # 生成处理器ID
        handler_id = str(uuid.uuid4())
        
        # 注册处理器
        self._handlers[event_type][handler_id] = handler
        
        # 更新统计信息
        self._stats["subscribers"] += 1
        
        logger.debug(f"已订阅事件 {event_type}，处理器 {handler.__qualname__}，ID {handler_id}")
        return handler_id
    
    def unsubscribe(self, event_type: str, handler: EventHandler) -> bool:
        """
        取消订阅事件。
        
        Args:
            event_type: 事件类型
            handler: 事件处理函数
            
        Returns:
            bool: 是否成功取消订阅
        """
        if event_type not in self._handlers:
            logger.warning(f"取消订阅失败，事件类型不存在: {event_type}")
            return False
            
        # 查找处理器ID
        handler_id = None
        for h_id, h in self._handlers[event_type].items():
            if h == handler:
                handler_id = h_id
                break
                
        if handler_id is None:
            logger.warning(f"取消订阅失败，处理器未注册: {handler.__qualname__}")
            return False
            
        # 移除处理器
        del self._handlers[event_type][handler_id]
        
        # 如果事件类型没有处理器了，删除该类型
        if not self._handlers[event_type]:
            del self._handlers[event_type]
            
        # 更新统计信息
        self._stats["subscribers"] -= 1
        
        logger.debug(f"已取消订阅事件 {event_type}，处理器 {handler.__qualname__}")
        return True
    
    def unsubscribe_by_id(self, event_type: str, handler_id: str) -> bool:
        """
        通过处理器ID取消订阅事件。
        
        Args:
            event_type: 事件类型
            handler_id: 处理器ID
            
        Returns:
            bool: 是否成功取消订阅
        """
        if event_type not in self._handlers:
            logger.warning(f"取消订阅失败，事件类型不存在: {event_type}")
            return False
            
        if handler_id not in self._handlers[event_type]:
            logger.warning(f"取消订阅失败，处理器ID不存在: {handler_id}")
            return False
            
        # 移除处理器
        del self._handlers[event_type][handler_id]
        
        # 如果事件类型没有处理器了，删除该类型
        if not self._handlers[event_type]:
            del self._handlers[event_type]
            
        # 更新统计信息
        self._stats["subscribers"] -= 1
        
        logger.debug(f"已通过ID取消订阅事件 {event_type}，ID {handler_id}")
        return True
    
    def unsubscribe_all(self, event_type: str) -> int:
        """
        取消订阅指定事件类型的所有处理器。
        
        Args:
            event_type: 事件类型
            
        Returns:
            int: 被取消的处理器数量
        """
        if event_type not in self._handlers:
            logger.warning(f"取消订阅失败，事件类型不存在: {event_type}")
            return 0
            
        # 获取处理器数量
        count = len(self._handlers[event_type])
        
        # 删除所有处理器
        del self._handlers[event_type]
        
        # 更新统计信息
        self._stats["subscribers"] -= count
        
        logger.debug(f"已取消订阅事件 {event_type} 的所有处理器，共 {count} 个")
        return count
    
    async def publish(self, event_type: str, data: Optional[Dict[str, Any]] = None) -> int:
        """
        发布事件。
        
        Args:
            event_type: 事件类型
            data: 事件数据，默认为空字典
            
        Returns:
            int: 接收到事件的处理器数量
        """
        if data is None:
            data = {}
            
        if event_type not in self._handlers:
            logger.debug(f"没有处理器订阅事件: {event_type}")
            return 0
            
        # 复制处理器字典，防止遍历过程中修改
        handlers = self._handlers[event_type].copy()
        
        # 更新统计信息
        self._stats["published"] += 1
        
        # 记录日志
        if handlers:
            logger.debug(f"发布事件 {event_type}，数据: {data}，处理器数量: {len(handlers)}")
        
        # 调用所有处理器
        tasks = []
        for handler_id, handler in handlers.items():
            try:
                task = asyncio.create_task(handler(data))
                tasks.append(task)
            except Exception as e:
                logger.error(f"创建事件处理任务时出错: {str(e)}")
                
        # 等待所有处理器执行完成
        if tasks:
            try:
                await asyncio.gather(*tasks)
                
                # 更新统计信息
                self._stats["handled"] += len(tasks)
                
            except Exception as e:
                logger.error(f"等待事件处理器执行时出错: {str(e)}")
        
        return len(handlers)
    
    async def publish_and_wait(
        self, 
        event_type: str, 
        data: Optional[Dict[str, Any]] = None,
        timeout: float = 30.0
    ) -> Optional[Dict[str, Any]]:
        """
        发布事件并等待第一个处理器的响应。
        
        Args:
            event_type: 事件类型
            data: 事件数据，默认为空字典
            timeout: 超时时间（秒），默认为30秒
            
        Returns:
            Optional[Dict[str, Any]]: 第一个处理器的响应，如果超时或无处理器则返回None
        """
        if data is None:
            data = {}
            
        if event_type not in self._handlers:
            logger.debug(f"没有处理器订阅事件: {event_type}")
            return None
            
        # 复制处理器字典，防止遍历过程中修改
        handlers = self._handlers[event_type].copy()
        
        # 更新统计信息
        self._stats["published"] += 1
        
        # 记录日志
        if handlers:
            logger.debug(f"发布事件 {event_type} 并等待响应，数据: {data}，处理器数量: {len(handlers)}")
            
        # 创建响应Future
        response_id = str(uuid.uuid4())
        response_future = asyncio.Future()
        
        # 存储响应Future
        self._waiting_responses[response_id] = response_future
        
        # 添加响应ID到事件数据
        data["_response_id"] = response_id
        
        # 调用所有处理器
        tasks = []
        for handler_id, handler in handlers.items():
            try:
                task = asyncio.create_task(self._call_handler_with_response(handler, data, response_id))
                tasks.append(task)
            except Exception as e:
                logger.error(f"创建事件处理任务时出错: {str(e)}")
                
        try:
            # 等待响应，带超时
            response = await asyncio.wait_for(response_future, timeout=timeout)
            
            # 更新统计信息
            self._stats["handled"] += 1
            
            return response
            
        except asyncio.TimeoutError:
            logger.warning(f"等待事件 {event_type} 响应超时")
            return None
            
        except Exception as e:
            logger.error(f"等待事件 {event_type} 响应时出错: {str(e)}")
            return None
            
        finally:
            # 清理响应Future
            if response_id in self._waiting_responses:
                del self._waiting_responses[response_id]
                
            # 取消所有任务
            for task in tasks:
                if not task.done():
                    task.cancel()
    
    async def _call_handler_with_response(
        self, 
        handler: EventHandler, 
        data: Dict[str, Any], 
        response_id: str
    ) -> None:
        """
        调用处理器并处理响应。
        
        Args:
            handler: 事件处理函数
            data: 事件数据
            response_id: 响应ID
        """
        try:
            # 调用处理器
            response = await handler(data)
            
            # 如果响应是字典，且Future仍在等待中，设置结果
            if (
                isinstance(response, dict) and 
                response_id in self._waiting_responses and 
                not self._waiting_responses[response_id].done()
            ):
                self._waiting_responses[response_id].set_result(response)
                
        except Exception as e:
            logger.error(f"事件处理器 {handler.__qualname__} 执行时出错: {str(e)}")
    
    def get_stats(self) -> Dict[str, Any]:
        """
        获取事件总线统计信息。
        
        Returns:
            Dict[str, Any]: 包含统计信息的字典
        """
        # 复制统计信息并添加当前事件类型和处理器数量
        stats = self._stats.copy()
        stats["event_types"] = len(self._handlers)
        
        # 计算每个事件类型的处理器数量
        event_stats = {}
        for event_type, handlers in self._handlers.items():
            event_stats[event_type] = len(handlers)
            
        stats["events"] = event_stats
        stats["uptime"] = time.time() - stats["start_time"]
        
        return stats 