"""
错误处理模块，负责处理各类错误情况
"""

import asyncio
import re
from typing import Dict, Any, Callable, Optional, Union, List

from tg_forwarder.logModule.logger import get_logger

# 获取日志记录器
logger = get_logger("error_handler")

class ErrorHandler:
    """错误处理器，负责处理各类错误情况"""
    
    def __init__(self, retry_count: int = 3, retry_delay: int = 5):
        """
        初始化错误处理器
        
        Args:
            retry_count: 最大重试次数
            retry_delay: 基础重试延迟（秒）
        """
        self.retry_count = retry_count
        self.retry_delay = retry_delay
    
    async def handle_error(self, error: Exception, error_type: str = "general") -> Dict[str, Any]:
        """
        处理错误，返回处理结果
        
        Args:
            error: 错误对象
            error_type: 错误类型
            
        Returns:
            Dict[str, Any]: 处理结果
        """
        error_msg = str(error)
        
        # FloodWait错误
        if "FloodWait" in error_type or "FLOOD_WAIT" in error_msg:
            return await self._handle_flood_wait(error, error_msg)
        
        # 转发限制错误
        elif "ChatForwardsRestricted" in error_type or "CHAT_FORWARDS_RESTRICTED" in error_msg:
            return self._handle_forward_restricted(error_msg)
        
        # 慢速模式错误
        elif "SlowmodeWait" in error_type or "SLOWMODE" in error_msg:
            return await self._handle_slowmode_wait(error, error_msg)
        
        # 权限错误
        elif "CHAT_WRITE_FORBIDDEN" in error_msg:
            return self._handle_permission_error(error_msg)
        
        # 无效ID错误
        elif "PEER_ID_INVALID" in error_msg:
            return self._handle_invalid_id(error_msg)
        
        # 通用错误
        else:
            return self._handle_general_error(error_msg)
    
    async def _handle_flood_wait(self, error: Exception, error_msg: str) -> Dict[str, Any]:
        """
        处理FloodWait错误
        
        Args:
            error: 错误对象
            error_msg: 错误消息
            
        Returns:
            Dict[str, Any]: 处理结果
        """
        # 提取等待时间
        wait_time_match = re.search(r"([0-9]+)", error_msg)
        wait_time = int(wait_time_match.group(1)) if wait_time_match else 30
        
        # 记录日志
        logger.warning(f"触发频率限制，等待 {wait_time} 秒")
        
        # 等待指定时间
        await asyncio.sleep(wait_time)
        
        return {
            "handled": True,
            "retry": True,
            "error_type": "flood_wait",
            "wait_time": wait_time,
            "message": f"触发频率限制，已等待 {wait_time} 秒"
        }
    
    async def _handle_slowmode_wait(self, error: Exception, error_msg: str) -> Dict[str, Any]:
        """
        处理SlowmodeWait错误
        
        Args:
            error: 错误对象
            error_msg: 错误消息
            
        Returns:
            Dict[str, Any]: 处理结果
        """
        # 提取等待时间
        wait_time_match = re.search(r"([0-9]+)", error_msg)
        wait_time = int(wait_time_match.group(1)) if wait_time_match else 10
        
        # 记录日志
        logger.warning(f"触发慢速模式，等待 {wait_time} 秒")
        
        # 等待指定时间
        await asyncio.sleep(wait_time)
        
        return {
            "handled": True,
            "retry": True,
            "error_type": "slowmode_wait",
            "wait_time": wait_time,
            "message": f"触发慢速模式，已等待 {wait_time} 秒"
        }
    
    def _handle_forward_restricted(self, error_msg: str) -> Dict[str, Any]:
        """
        处理转发限制错误
        
        Args:
            error_msg: 错误消息
            
        Returns:
            Dict[str, Any]: 处理结果
        """
        logger.warning(f"频道禁止转发消息: {error_msg}")
        
        return {
            "handled": True,
            "retry": False,
            "error_type": "forwards_restricted",
            "message": "频道禁止转发消息，需要使用下载上传方式"
        }
    
    def _handle_permission_error(self, error_msg: str) -> Dict[str, Any]:
        """
        处理权限错误
        
        Args:
            error_msg: 错误消息
            
        Returns:
            Dict[str, Any]: 处理结果
        """
        logger.error(f"无权在目标频道发送消息: {error_msg}")
        
        return {
            "handled": True,
            "retry": False,
            "error_type": "permission_error",
            "message": "无权在目标频道发送消息"
        }
    
    def _handle_invalid_id(self, error_msg: str) -> Dict[str, Any]:
        """
        处理无效ID错误
        
        Args:
            error_msg: 错误消息
            
        Returns:
            Dict[str, Any]: 处理结果
        """
        logger.error(f"无效的频道ID: {error_msg}")
        
        return {
            "handled": True,
            "retry": False,
            "error_type": "invalid_id",
            "message": "无效的频道ID"
        }
    
    def _handle_general_error(self, error_msg: str) -> Dict[str, Any]:
        """
        处理通用错误
        
        Args:
            error_msg: 错误消息
            
        Returns:
            Dict[str, Any]: 处理结果
        """
        logger.error(f"发生错误: {error_msg}")
        
        return {
            "handled": False,
            "retry": False,
            "error_type": "general",
            "message": f"发生错误: {error_msg}"
        }
    
    async def retry_operation(self, operation: Callable, *args, **kwargs) -> Any:
        """
        使用重试机制执行操作
        
        Args:
            operation: 要执行的操作函数
            args: 传递给操作函数的位置参数
            kwargs: 传递给操作函数的关键字参数
            
        Returns:
            Any: 操作结果
        """
        last_error = None
        
        for attempt in range(self.retry_count + 1):
            try:
                # 执行操作
                return await operation(*args, **kwargs)
            
            except Exception as e:
                last_error = e
                error_result = await self.handle_error(e)
                
                # 如果错误已处理且可以重试
                if error_result.get("handled") and error_result.get("retry"):
                    if "wait_time" not in error_result:
                        # 使用退避策略计算等待时间
                        wait_time = self.retry_delay * (2 ** attempt)
                        logger.info(f"将在 {wait_time} 秒后重试 (尝试 {attempt+1}/{self.retry_count+1})...")
                        await asyncio.sleep(wait_time)
                else:
                    # 不可重试的错误
                    logger.error(f"操作失败，不再重试: {error_result.get('message')}")
                    break
        
        # 如果所有重试都失败
        if last_error:
            raise last_error
        
        return None 