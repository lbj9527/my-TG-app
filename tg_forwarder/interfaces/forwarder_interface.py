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
    
    @abstractmethod
    async def start_forwarding(
        self,
        forward_config: Dict[str, Any] = None,
        monitor_mode: bool = False
    ) -> Dict[str, Any]:
        """
        启动转发服务
        
        Args:
            forward_config: 转发配置，为None时使用默认配置
            monitor_mode: 是否为监听模式，为True时使用monitor配置
            
        Returns:
            Dict[str, Any]: 启动结果
        """
        pass
    
    @abstractmethod
    async def stop_forwarding(self) -> Dict[str, Any]:
        """
        停止转发服务
        
        Returns:
            Dict[str, Any]: 停止结果
        """
        pass
    
    @abstractmethod
    def get_forwarding_status(self) -> Dict[str, Any]:
        """
        获取转发服务状态
        
        Returns:
            Dict[str, Any]: 转发服务状态信息
        """
        pass
        
    @abstractmethod
    async def start_monitor(
        self,
        monitor_config: Dict[str, Any] = None
    ) -> Dict[str, Any]:
        """
        启动监听服务，实时监听源频道的新消息并转发到目标频道
        
        Args:
            monitor_config: 监听配置，为None时使用默认配置。配置应包含：
                - channel_pairs: 源频道与目标频道的映射关系
                - duration: 监听时长，格式为"年-月-日-时"，如"2025-3-28-1"
                - remove_captions: 是否移除原始字幕
                - media_types: 要转发的媒体类型列表
                - forward_delay: 转发延迟（秒）
                - max_retries: 失败后最大重试次数
                - message_filter: 消息过滤器表达式
            
        Returns:
            Dict[str, Any]: 启动结果，包含以下字段：
                - success: 是否成功启动
                - error: 如果失败，包含错误信息
                - monitor_id: 监听任务ID
                - start_time: 开始时间
                - end_time: 预计结束时间（根据duration计算）
        """
        pass
    
    @abstractmethod
    async def stop_monitor(self) -> Dict[str, Any]:
        """
        停止监听服务
        
        Returns:
            Dict[str, Any]: 停止结果，包含以下字段：
                - success: 是否成功停止
                - error: 如果失败，包含错误信息
                - monitor_id: 监听任务ID
                - duration: 实际监听时长（秒）
                - messages_forwarded: 已转发的消息数量
        """
        pass
    
    @abstractmethod
    def get_monitor_status(self) -> Dict[str, Any]:
        """
        获取监听服务状态
        
        Returns:
            Dict[str, Any]: 监听服务状态信息，包含以下字段：
                - running: 是否正在运行
                - start_time: 开始时间
                - end_time: 预计结束时间
                - remaining_time: 剩余时间（秒）
                - messages_forwarded: 已转发的消息数量
                - channel_pairs: 监听的频道对
                - errors: 错误统计
        """
        pass 