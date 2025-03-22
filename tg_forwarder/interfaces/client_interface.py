"""
Telegram客户端接口抽象
定义与Telegram API交互的必要方法
"""

from abc import ABC, abstractmethod
from typing import Dict, Any, Optional, List, Union, Tuple
from pyrogram.types import Message


class TelegramClientInterface(ABC):
    """
    Telegram客户端接口，定义了与Telegram API交互的必要方法
    所有客户端实现都应该继承此接口
    """
    
    @abstractmethod
    async def connect(self) -> None:
        """
        连接到Telegram API
        
        Raises:
            Exception: 连接失败时抛出
        """
        pass
    
    @abstractmethod
    async def disconnect(self) -> None:
        """断开与Telegram API的连接"""
        pass
    
    @abstractmethod
    async def get_entity(self, channel_identifier: Union[str, int]) -> Optional[Any]:
        """
        获取频道/聊天/用户的实体信息
        
        Args:
            channel_identifier: 频道标识符
        
        Returns:
            Any: 实体信息，如果获取失败则返回None
        """
        pass
    
    @abstractmethod
    async def get_message(self, channel: Union[str, int], message_id: int) -> Optional[Message]:
        """
        获取指定频道的指定消息
        
        Args:
            channel: 频道标识符
            message_id: 消息ID
        
        Returns:
            Optional[Message]: 消息对象，如果消息不存在则返回None
        """
        pass
    
    @abstractmethod
    async def get_messages_range(self, channel: Union[str, int], start_id: int, end_id: int, batch_size: int = 100) -> List[Message]:
        """
        获取指定范围内的消息
        
        Args:
            channel: 频道标识符
            start_id: 起始消息ID
            end_id: 结束消息ID
            batch_size: 每批次获取的消息数量
        
        Returns:
            List[Message]: 消息列表
        """
        pass
    
    @abstractmethod
    async def get_chat_history(self, channel: Union[str, int], limit: int = 100) -> List[Message]:
        """
        获取频道历史消息
        
        Args:
            channel: 频道标识符
            limit: 最大获取消息数量
        
        Returns:
            List[Message]: 消息列表
        """
        pass
    
    @abstractmethod
    async def get_latest_message_id(self, channel: Union[str, int]) -> Optional[int]:
        """
        获取频道最新消息ID
        
        Args:
            channel: 频道标识符
        
        Returns:
            Optional[int]: 最新消息ID，如果获取失败则返回None
        """
        pass
    
    @abstractmethod
    async def get_media_group(self, chat_id: Union[str, int], message_id: int) -> List[Message]:
        """
        获取媒体组消息
        
        Args:
            chat_id: 聊天ID或用户名
            message_id: 媒体组中任一消息ID
        
        Returns:
            List[Message]: 媒体组中的所有消息
        """
        pass
    
    @abstractmethod
    async def get_chat_member(self, chat_id: Union[str, int], user_id: Union[str, int]) -> Optional[Any]:
        """
        获取指定聊天中的成员信息
        
        Args:
            chat_id: 聊天或频道的ID
            user_id: 用户ID或用户名
            
        Returns:
            Any: 成员信息，如果获取失败则返回None
        """
        pass 