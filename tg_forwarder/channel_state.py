"""
频道状态管理模块，负责集中管理频道状态信息
"""

import logging
from typing import Dict, Union, Optional, List
import time

from tg_forwarder.utils.logger import get_logger

logger = get_logger("channel_state")

class ChannelStateManager:
    """频道状态管理器，集中管理频道的各种状态信息"""
    
    def __init__(self):
        """初始化频道状态管理器"""
        # 频道转发状态缓存 {channel_id: allow_forward}
        self._forward_status = {}
        # 频道验证时间缓存 {channel_id: last_verified_time}
        self._verification_time = {}
        # 缓存过期时间（秒）
        self.cache_expiry = 3600  # 默认1小时
    
    def set_forward_status(self, channel_id: Union[str, int], allow_forward: bool) -> None:
        """
        设置频道转发状态
        
        Args:
            channel_id: 频道ID
            allow_forward: 是否允许转发
        """
        channel_id_str = str(channel_id)
        self._forward_status[channel_id_str] = allow_forward
        self._verification_time[channel_id_str] = time.time()
        logger.info(f"频道 {channel_id} 状态已更新: {'允许转发' if allow_forward else '禁止转发'}")
    
    def get_forward_status(self, channel_id: Union[str, int], default: bool = True) -> bool:
        """
        获取频道转发状态
        
        Args:
            channel_id: 频道ID
            default: 默认状态（如果未缓存）
            
        Returns:
            bool: 是否允许转发
        """
        channel_id_str = str(channel_id)
        
        # 检查缓存是否过期
        if channel_id_str in self._verification_time:
            cache_age = time.time() - self._verification_time[channel_id_str]
            if cache_age > self.cache_expiry:
                logger.info(f"频道 {channel_id} 状态缓存已过期，需要重新验证")
                del self._forward_status[channel_id_str]
                del self._verification_time[channel_id_str]
        
        return self._forward_status.get(channel_id_str, default)
    
    def is_cached(self, channel_id: Union[str, int]) -> bool:
        """
        检查频道状态是否已缓存
        
        Args:
            channel_id: 频道ID
            
        Returns:
            bool: 是否已缓存
        """
        channel_id_str = str(channel_id)
        return channel_id_str in self._forward_status
    
    def invalidate_cache(self, channel_id: Optional[Union[str, int]] = None) -> None:
        """
        使缓存失效
        
        Args:
            channel_id: 指定频道ID（如果为None则清除所有缓存）
        """
        if channel_id is None:
            # 清除所有缓存
            self._forward_status.clear()
            self._verification_time.clear()
            logger.info("所有频道状态缓存已清除")
        else:
            # 清除指定频道的缓存
            channel_id_str = str(channel_id)
            if channel_id_str in self._forward_status:
                del self._forward_status[channel_id_str]
            if channel_id_str in self._verification_time:
                del self._verification_time[channel_id_str]
            logger.info(f"频道 {channel_id} 状态缓存已清除")
    
    def get_all_statuses(self) -> Dict[str, bool]:
        """
        获取所有频道状态
        
        Returns:
            Dict[str, bool]: 频道状态字典
        """
        return self._forward_status.copy()
    
    def sort_channels_by_status(self, channels: List[Union[str, int]]) -> List[Union[str, int]]:
        """
        根据转发状态排序频道列表（优先允许转发的频道）
        
        Args:
            channels: 频道列表
            
        Returns:
            List[Union[str, int]]: 排序后的频道列表
        """
        return sorted(channels, key=lambda channel: 0 if self.get_forward_status(channel) else 1) 