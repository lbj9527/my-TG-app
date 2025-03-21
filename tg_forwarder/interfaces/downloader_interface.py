"""
下载器接口抽象
定义了消息和媒体下载的必要方法
"""

from abc import ABC, abstractmethod
from typing import Dict, Any, List, Union, Optional
from pyrogram.types import Message


class DownloaderInterface(ABC):
    """
    下载器接口，定义了下载消息和媒体的必要方法
    所有下载器实现都应该继承此接口
    """
    
    @abstractmethod
    async def initialize(self) -> bool:
        """
        初始化下载器
        
        Returns:
            bool: 初始化是否成功
        """
        pass
    
    @abstractmethod
    async def shutdown(self) -> None:
        """关闭下载器，释放资源"""
        pass
        
    @abstractmethod
    async def download_media_batch(self, batch: Dict[str, Any]) -> Dict[str, Any]:
        """
        下载批量媒体文件
        
        Args:
            batch: 包含消息信息的批次数据
            
        Returns:
            Dict[str, Any]: 下载结果，包含成功和失败的媒体信息
        """
        pass
    
    @abstractmethod
    def _has_downloadable_media(self, message: Message) -> bool:
        """
        检查消息是否包含可下载的媒体
        
        Args:
            message: 消息对象
            
        Returns:
            bool: 如果包含可下载媒体则返回True，否则返回False
        """
        pass
    
    @abstractmethod
    def _generate_file_name(self, message: Message, chat_id: int, message_id: int, group_id: str = None) -> str:
        """
        生成媒体文件的保存路径
        
        Args:
            message: 消息对象
            chat_id: 聊天ID
            message_id: 消息ID
            group_id: 媒体组ID（可选）
            
        Returns:
            str: 生成的文件名
        """
        pass
    
    @abstractmethod
    def _is_message_downloaded(self, chat_id, message_id) -> bool:
        """
        检查消息是否已下载
        
        Args:
            chat_id: 聊天ID
            message_id: 消息ID
            
        Returns:
            bool: 如果已下载则返回True，否则返回False
        """
        pass
    
    @abstractmethod
    def _store_message_metadata(self, message: Message, group_id: str = None) -> None:
        """
        存储消息元数据
        
        Args:
            message: 消息对象
            group_id: 媒体组ID（可选）
        """
        pass 