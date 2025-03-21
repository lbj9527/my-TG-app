"""
转发器接口抽象
定义了消息转发的必要方法
"""

from abc import ABC, abstractmethod
from typing import Dict, Any, List, Union, Optional, Tuple
from datetime import datetime


class ForwarderInterface(ABC):
    """
    转发器接口，定义了消息转发的必要方法
    所有转发器实现都应该继承此接口
    """
    
    @abstractmethod
    async def initialize(self) -> bool:
        """
        初始化转发器
        
        Returns:
            bool: 初始化是否成功
        """
        pass
    
    @abstractmethod
    async def shutdown(self) -> None:
        """关闭转发器，释放资源"""
        pass
    
    @abstractmethod
    async def forward_message(self, source_channel: Union[str, int], 
                            message_id: int,
                            target_channels: List[Union[str, int]] = None) -> Dict[str, Any]:
        """
        转发单条消息
        
        Args:
            source_channel: 源频道标识
            message_id: 消息ID
            target_channels: 目标频道列表，为None时使用配置的默认目标
            
        Returns:
            Dict[str, Any]: 转发结果，包含成功和失败的目标频道信息
        """
        pass
    
    @abstractmethod
    async def forward_media_group(self, source_channel: Union[str, int],
                                message_id: int,
                                target_channels: List[Union[str, int]] = None) -> Dict[str, Any]:
        """
        转发媒体组
        
        Args:
            source_channel: 源频道标识
            message_id: 媒体组中任一消息ID
            target_channels: 目标频道列表，为None时使用配置的默认目标
            
        Returns:
            Dict[str, Any]: 转发结果，包含成功和失败的目标频道信息
        """
        pass
        
    @abstractmethod
    async def forward_range(self, source_channel: Union[str, int],
                          start_id: int,
                          end_id: int,
                          target_channels: List[Union[str, int]] = None) -> Dict[str, Any]:
        """
        转发一个范围内的消息
        
        Args:
            source_channel: 源频道标识
            start_id: 起始消息ID
            end_id: 结束消息ID
            target_channels: 目标频道列表，为None时使用配置的默认目标
            
        Returns:
            Dict[str, Any]: 转发结果统计
        """
        pass
    
    @abstractmethod
    async def forward_date_range(self, source_channel: Union[str, int],
                               start_date: datetime,
                               end_date: datetime,
                               target_channels: List[Union[str, int]] = None) -> Dict[str, Any]:
        """
        转发指定日期范围内的消息
        
        Args:
            source_channel: 源频道标识
            start_date: 起始日期
            end_date: 结束日期
            target_channels: 目标频道列表，为None时使用配置的默认目标
            
        Returns:
            Dict[str, Any]: 转发结果统计
        """
        pass
    
    @abstractmethod
    async def schedule_forward(self, source_channel: Union[str, int],
                             message_id: Union[int, Tuple[int, int]],
                             schedule_time: datetime,
                             target_channels: List[Union[str, int]] = None) -> str:
        """
        调度消息转发任务
        
        Args:
            source_channel: 源频道标识
            message_id: 消息ID或范围(起始ID, 结束ID)
            schedule_time: 调度时间
            target_channels: 目标频道列表，为None时使用配置的默认目标
            
        Returns:
            str: 任务ID
        """
        pass
    
    @abstractmethod
    async def cancel_scheduled_forward(self, task_id: str) -> bool:
        """
        取消调度的转发任务
        
        Args:
            task_id: 任务ID
            
        Returns:
            bool: 取消是否成功
        """
        pass
    
    @abstractmethod
    async def get_forward_status(self, task_id: str) -> Dict[str, Any]:
        """
        获取转发任务状态
        
        Args:
            task_id: 任务ID
            
        Returns:
            Dict[str, Any]: 任务状态信息
        """
        pass
    
    @abstractmethod
    async def get_forward_statistics(self, start_date: Optional[datetime] = None,
                                   end_date: Optional[datetime] = None) -> Dict[str, Any]:
        """
        获取转发统计信息
        
        Args:
            start_date: 开始日期，为None表示不限制
            end_date: 结束日期，为None表示不限制
            
        Returns:
            Dict[str, Any]: 统计信息
        """
        pass
    
    @abstractmethod
    async def retry_failed_forward(self, task_id: str = None) -> Dict[str, Any]:
        """
        重试失败的转发任务
        
        Args:
            task_id: 任务ID，为None时重试所有失败任务
            
        Returns:
            Dict[str, Any]: 重试结果
        """
        pass 