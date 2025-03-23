"""
转发器接口抽象
定义了消息转发的必要方法，包括历史消息转发和实时监听转发
"""

from abc import ABC, abstractmethod
from typing import Dict, Any, List, Optional, Union, Set, Tuple
from pyrogram.types import Message


class ForwarderInterface(ABC):
    """
    转发器接口，定义了消息转发的必要方法     
    所有转发器实现都应该继承此接口
    """

    @abstractmethod
    async def initialize(self) -> bool:
        """
        初始化转发器（异步方法）

        Returns:
            bool: 初始化是否成功
        """
        pass

    @abstractmethod
    def close(self) -> None:
        """关闭转发器，释放资源"""
        pass

    @abstractmethod
    async def start_forwarding(self, forward_config: Dict[str, Any]) -> Dict[str, Any]:
        """
        开始历史消息转发流程

        Args:
            forward_config: 转发配置，包含以下字段:
                - forward_channel_pairs: 源频道与目标频道的映射关系
                - remove_captions: 是否移除原始消息的标题
                - media_types: 需转发的媒体类型列表
                - forward_delay: 转发延迟（秒）
                - timeout: 转发操作超时时间（秒）
                - max_retries: 转发失败后的最大重试次数
                - message_filter: 消息过滤器（预留接口）
                - add_watermark: 是否添加水印（预留接口）
                - watermark_text: 水印文本（预留接口）
                - start_id: 起始消息ID
                - end_id: 结束消息ID
                - limit: 转发消息数量上限
                - pause_time: A到达限制后的暂停时间（秒）

        Returns:
            Dict[str, Any]: 转发结果统计
        """
        pass

    @abstractmethod
    async def forward_messages(self, source_channel: Union[str, int], 
                              target_channels: List[Union[str, int]],
                              start_id: int = 0, 
                              end_id: int = 0,
                              limit: int = 100,
                              media_types: List[str] = None,
                              remove_captions: bool = False) -> Dict[str, Any]:
        """
        转发指定频道范围内的历史消息

        Args:
            source_channel: 源频道标识符
            target_channels: 目标频道标识符列表
            start_id: 起始消息ID，0表示从最新消息开始
            end_id: 结束消息ID，0表示不设结束ID
            limit: 转发消息数量上限
            media_types: 需转发的媒体类型列表，None表示转发所有类型
            remove_captions: 是否移除原始消息的标题

        Returns:
            Dict[str, Any]: 转发结果统计
        """
        pass

    @abstractmethod
    async def forward_history_messages(self, source_channel: Union[str, int], 
                                      target_channels: List[Union[str, int]],
                                      start_id: int = 0, 
                                      end_id: int = 0,
                                      limit: int = 100,
                                      media_types: List[str] = None,
                                      remove_captions: bool = False,
                                      download_media: bool = False) -> Dict[str, Any]:
        """
        转发指定频道范围内的历史消息，处理媒体消息和普通消息

        Args:
            source_channel: 源频道标识符
            target_channels: 目标频道标识符列表
            start_id: 起始消息ID，0表示从最新消息开始
            end_id: 结束消息ID，0表示不设结束ID
            limit: 转发消息数量上限
            media_types: 需转发的媒体类型列表，None表示转发所有类型
            remove_captions: 是否移除原始消息的标题
            download_media: 对于禁止转发的频道，是否下载媒体后重新上传

        Returns:
            Dict[str, Any]: 转发结果统计
        """
        pass

    @abstractmethod
    async def forward_single_message(self, message: Message, 
                                    target_channels: List[Union[str, int]],
                                    remove_captions: bool = False,
                                    download_media: bool = False) -> Dict[str, Any]:
        """
        转发单条消息到指定目标频道

        Args:
            message: 要转发的消息
            target_channels: 目标频道标识符列表
            remove_captions: 是否移除原始消息的标题
            download_media: 对于禁止转发的频道，是否下载媒体后重新上传

        Returns:
            Dict[str, Any]: 转发结果
        """
        pass

    @abstractmethod
    async def check_message_forwarded(self, source_channel: Union[str, int], 
                                     message_id: int, 
                                     target_channel: Union[str, int]) -> bool:
        """
        检查消息是否已转发到指定目标频道

        Args:
            source_channel: 源频道标识符
            message_id: 消息ID
            target_channel: 目标频道标识符

        Returns:
            bool: 消息是否已转发到指定目标频道
        """
        pass

    @abstractmethod
    async def start_monitor(self, monitor_config: Dict[str, Any] = None) -> Dict[str, Any]:
        """
        开始监听源频道，实时转发新消息

        Args:
            monitor_config: 监听配置，包含以下字段:
                - monitor_channel_pairs: 源频道与目标频道的映射关系
                - remove_captions: 是否移除原始消息的标题
                - media_types: 需转发的媒体类型列表
                - duration: 监听时长，格式为"年-月-日-时"，如"2025-3-28-1"
                - forward_delay: 转发延迟（秒）
                - max_retries: 失败后最大重试次数
                - message_filter: 消息过滤器表达式（预留接口）
                - add_watermark: 是否添加水印（预留接口）
                - watermark_text: 水印文本（预留接口）
                
        Returns:
            Dict[str, Any]: 启动结果
        """
        pass

    @abstractmethod
    async def handle_new_message(self, message: Message) -> Dict[str, Any]:
        """
        处理监听到的新消息

        Args:
            message: 新消息

        Returns:
            Dict[str, Any]: 处理结果
        """
        pass

    @abstractmethod
    def is_message_type_allowed(self, message: Message, allowed_types: List[str]) -> bool:
        """
        检查消息类型是否在允许的类型列表中

        Args:
            message: 消息
            allowed_types: 允许的类型列表

        Returns:
            bool: 消息类型是否允许
        """
        pass

    @abstractmethod
    async def is_channel_restricted(self, channel_id: Union[str, int]) -> bool:
        """
        检查频道是否禁止转发

        Args:
            channel_id: 频道ID或用户名

        Returns:
            bool: 频道是否禁止转发
        """
        pass

    @abstractmethod
    async def get_forwarding_stats(self) -> Dict[str, Any]:
        """
        获取转发统计信息

        Returns:
            Dict[str, Any]: 转发统计信息
        """
        pass 