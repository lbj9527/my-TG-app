"""
历史记录跟踪接口抽象
定义了历史记录跟踪的必要方法，包括下载历史、上传历史和转发历史
"""

from abc import ABC, abstractmethod
from typing import Dict, Any, List, Optional, Set, Union
from datetime import datetime


class HistoryTrackerInterface(ABC):
    """
    历史记录跟踪接口，定义了历史记录跟踪的必要方法
    所有历史记录跟踪实现都应该继承此接口
    """
    
    @abstractmethod
    async def initialize(self) -> bool:
        """
        初始化历史记录跟踪器（异步方法）
        
        Returns:
            bool: 初始化是否成功
        """
        pass
    
    @abstractmethod
    def close(self) -> None:
        """关闭历史记录跟踪器，释放资源"""
        pass
    
    @abstractmethod
    def is_message_processed(self, history_type: str, channel_id: Union[int, str], message_id: int) -> bool:
        """
        检查消息是否已处理
        
        Args:
            history_type: 历史记录类型（'download', 'upload', 'forward'）
            channel_id: 频道ID或用户名
            message_id: 消息ID
            
        Returns:
            bool: 消息是否已处理
        """
        pass
    
    @abstractmethod
    def mark_message_processed(self, history_type: str, channel_id: Union[int, str], message_id: int) -> bool:
        """
        标记消息为已处理
        
        Args:
            history_type: 历史记录类型（'download', 'upload', 'forward'）
            channel_id: 频道ID或用户名
            message_id: 消息ID
            
        Returns:
            bool: 标记是否成功
        """
        pass
    
    @abstractmethod
    def get_processed_messages(self, history_type: str, channel_id: Union[int, str]) -> Set[int]:
        """
        获取已处理的消息ID集合
        
        Args:
            history_type: 历史记录类型（'download', 'upload', 'forward'）
            channel_id: 频道ID或用户名
            
        Returns:
            Set[int]: 已处理的消息ID集合
        """
        pass
    
    @abstractmethod
    def mark_file_uploaded(self, file_path: str, channel_id: Union[int, str]) -> bool:
        """
        标记文件已上传到指定频道
        
        Args:
            file_path: 文件路径
            channel_id: 已上传的目标频道ID或用户名
            
        Returns:
            bool: 标记是否成功
        """
        pass
    
    @abstractmethod
    def is_file_uploaded(self, file_path: str, channel_id: Union[int, str]) -> bool:
        """
        检查文件是否已上传到指定频道
        
        Args:
            file_path: 文件路径
            channel_id: 目标频道ID或用户名
            
        Returns:
            bool: 文件是否已上传
        """
        pass
    
    @abstractmethod
    def get_uploaded_files(self, channel_id: Union[int, str] = None) -> List[str]:
        """
        获取已上传的文件列表
        
        Args:
            channel_id: 目标频道ID或用户名，为None时返回所有已上传文件
            
        Returns:
            List[str]: 已上传的文件路径列表
        """
        pass
    
    @abstractmethod
    def clear_history(self, history_type: str, channel_id: Union[int, str] = None) -> bool:
        """
        清除历史记录
        
        Args:
            history_type: 历史记录类型（'download', 'upload', 'forward'）
            channel_id: 频道ID或用户名，为None时清除该类型的所有历史记录
            
        Returns:
            bool: 清除是否成功
        """
        pass
    
    @abstractmethod
    def get_history_file_path(self, history_type: str) -> str:
        """
        获取历史记录文件路径
        
        Args:
            history_type: 历史记录类型（'download', 'upload', 'forward'）
            
        Returns:
            str: 历史记录文件路径
        """
        pass
    
    @abstractmethod
    def register_channel_id(self, channel_name: str, channel_id: int) -> bool:
        """
        注册频道ID和用户名的对应关系
        
        Args:
            channel_name: 频道用户名（如"@channel_name"或"https://t.me/channel_name"）
            channel_id: 频道ID（如-100123456789）
            
        Returns:
            bool: 注册是否成功
        """
        pass
    
    @abstractmethod
    def get_channel_id(self, channel_name: str) -> Optional[int]:
        """
        获取频道ID
        
        Args:
            channel_name: 频道用户名
            
        Returns:
            Optional[int]: 频道ID，不存在时返回None
        """
        pass
    
    @abstractmethod
    def mark_message_forwarded(self, source_channel: Union[int, str], message_id: int, target_channels: List[Union[int, str]]) -> bool:
        """
        标记消息已转发到目标频道
        
        Args:
            source_channel: 源频道ID或用户名
            message_id: 消息ID
            target_channels: 目标频道ID或用户名列表
            
        Returns:
            bool: 标记是否成功
        """
        pass
    
    @abstractmethod
    def get_forwarded_targets(self, source_channel: Union[int, str], message_id: int) -> List[Union[int, str]]:
        """
        获取消息已转发到的目标频道列表
        
        Args:
            source_channel: 源频道ID或用户名
            message_id: 消息ID
            
        Returns:
            List[Union[int, str]]: 已转发到的目标频道列表
        """
        pass
    
    @abstractmethod
    def add_file_upload_info(self, file_path: str, target_channel: Union[int, str], file_info: Dict[str, Any]) -> bool:
        """
        添加文件上传信息
        
        Args:
            file_path: 文件路径
            target_channel: 目标频道ID或用户名
            file_info: 文件信息，包括上传时间、文件大小、媒体类型等
            
        Returns:
            bool: 添加是否成功
        """
        pass
    
    @abstractmethod
    def get_file_upload_info(self, file_path: str) -> Dict[str, Any]:
        """
        获取文件上传信息
        
        Args:
            file_path: 文件路径
            
        Returns:
            Dict[str, Any]: 文件上传信息，包括上传目标、上传时间、文件大小、媒体类型等
        """
        pass
    
    @abstractmethod
    def update_last_timestamp(self, history_type: str) -> bool:
        """
        更新历史记录的最后更新时间戳
        
        Args:
            history_type: 历史记录类型（'download', 'upload', 'forward'）
            
        Returns:
            bool: 更新是否成功
        """
        pass
    
    @abstractmethod
    def get_last_timestamp(self, history_type: str) -> Optional[datetime]:
        """
        获取历史记录的最后更新时间戳
        
        Args:
            history_type: 历史记录类型（'download', 'upload', 'forward'）
            
        Returns:
            Optional[datetime]: 最后更新时间戳，不存在时返回None
        """
        pass
    
    @abstractmethod
    def export_history_data(self, history_type: str) -> Dict[str, Any]:
        """
        导出历史记录数据
        
        Args:
            history_type: 历史记录类型（'download', 'upload', 'forward'）
            
        Returns:
            Dict[str, Any]: 导出的历史记录数据，与JSON格式一致
        """
        pass
    
    @abstractmethod
    def import_history_data(self, history_type: str, data: Dict[str, Any]) -> bool:
        """
        导入历史记录数据
        
        Args:
            history_type: 历史记录类型（'download', 'upload', 'forward'）
            data: 要导入的历史记录数据，与JSON格式一致
            
        Returns:
            bool: 导入是否成功
        """
        pass 