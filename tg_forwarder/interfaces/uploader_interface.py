"""
上传器接口抽象
定义了媒体上传的必要方法
"""

from abc import ABC, abstractmethod
from typing import Dict, Any, List, Union, Optional


class UploaderInterface(ABC):
    """
    上传器接口，定义了上传媒体的必要方法
    所有上传器实现都应该继承此接口
    """
    
    @abstractmethod
    async def initialize(self) -> bool:
        """
        初始化上传器
        
        Returns:
            bool: 初始化是否成功
        """
        pass
    
    @abstractmethod
    async def shutdown(self) -> None:
        """关闭上传器，释放资源"""
        pass
    
    @abstractmethod
    async def upload_batch(self, batch_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        上传一批媒体文件
        
        Args:
            batch_data: 批次数据，包含媒体组和单条消息
            
        Returns:
            Dict[str, Any]: 上传结果
        """
        pass
    
    @abstractmethod
    async def _forward_to_other_channels(self, source_channel: Union[str, int], 
                                       message_id: int, 
                                       original_id: Union[str, int],
                                       is_media_group: bool = False,
                                       source_channel_id: Optional[Union[str, int]] = None) -> None:
        """
        将消息从第一个频道转发到其他频道
        
        Args:
            source_channel: 源频道ID
            message_id: 消息ID
            original_id: 原始消息ID或媒体组ID
            is_media_group: 是否为媒体组
            source_channel_id: 原始来源频道ID（可选）
        """
        pass
    
    @abstractmethod
    def cleanup_old_records(self, max_age_days: int = 30) -> int:
        """
        清理旧的上传记录
        
        Args:
            max_age_days: 最大保留天数
            
        Returns:
            int: 清理的记录数量
        """
        pass
    
    @abstractmethod
    def cleanup_temp_files(self, max_age_hours: int = 24) -> int:
        """
        清理过期的临时文件
        
        Args:
            max_age_hours: 最大保留小时数
            
        Returns:
            int: 清理的文件数量
        """
        pass 