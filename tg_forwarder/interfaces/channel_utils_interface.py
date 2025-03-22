"""
频道工具接口定义
定义频道验证、状态管理等高级功能接口
"""

from typing import Dict, List, Tuple, Union, Optional, Any


class ChannelUtilsInterface:
    """
    频道工具接口，定义频道验证和状态管理的高级方法
    主要负责频道有效性验证、状态缓存和批量处理
    """
    
    async def validate_channel(self, channel: str) -> Dict[str, Any]:
        """
        验证频道是否有效，并获取频道信息
        
        Args:
            channel: 频道标识符（用户名、ID、链接等）
            
        Returns:
            Dict[str, Any]: 验证结果
                - valid: 频道是否有效
                - channel_id: 频道ID
                - allow_forward: 是否允许转发
                - title: 频道标题
                - error: 错误信息（如果有）
        """
        raise NotImplementedError("接口方法未实现")
    
    async def validate_channels(self, channels: List[str]) -> Dict[str, Any]:
        """
        批量验证频道是否有效
        
        Args:
            channels: 频道标识符列表
            
        Returns:
            Dict[str, Any]: 验证结果
                - valid_channels: 有效频道列表
                - invalid_channels: 无效频道列表及错误原因
                - forward_status: 各频道的转发状态
        """
        raise NotImplementedError("接口方法未实现")
    
    def set_forward_status(self, channel_id: Union[str, int], allow_forward: bool) -> None:
        """
        设置频道转发状态
        
        Args:
            channel_id: 频道ID
            allow_forward: 是否允许转发
        """
        raise NotImplementedError("接口方法未实现")
    
    def get_forward_status(self, channel_id: Union[str, int], default: bool = True) -> bool:
        """
        获取频道转发状态
        
        Args:
            channel_id: 频道ID
            default: 默认状态（如果未缓存）
            
        Returns:
            bool: 是否允许转发
        """
        raise NotImplementedError("接口方法未实现")
    
    def is_cached(self, channel_id: Union[str, int]) -> bool:
        """
        检查频道状态是否已缓存
        
        Args:
            channel_id: 频道ID
            
        Returns:
            bool: 是否已缓存
        """
        raise NotImplementedError("接口方法未实现")
    
    def invalidate_cache(self, channel_id: Optional[Union[str, int]] = None) -> None:
        """
        使缓存失效
        
        Args:
            channel_id: 指定频道ID（如果为None则清除所有缓存）
        """
        raise NotImplementedError("接口方法未实现")
    
    def get_all_statuses(self) -> Dict[str, bool]:
        """
        获取所有频道状态
        
        Returns:
            Dict[str, bool]: 频道状态字典 {channel_id: allow_forward}
        """
        raise NotImplementedError("接口方法未实现")
    
    def sort_channels_by_status(self, channels: List[Union[str, int]]) -> List[Union[str, int]]:
        """
        根据转发状态排序频道列表（优先允许转发的频道）
        
        Args:
            channels: 频道列表
            
        Returns:
            List[Union[str, int]]: 排序后的频道列表
        """
        raise NotImplementedError("接口方法未实现")
        
    def parse_channel(self, channel_identifier: str) -> Tuple[Union[str, int], Optional[int]]:
        """
        解析频道标识符
        
        Args:
            channel_identifier: 频道标识符
            
        Returns:
            Tuple[Union[str, int], Optional[int]]: (频道标识符, 消息ID)
        """
        raise NotImplementedError("接口方法未实现")
    
    def format_channel(self, identifier: Union[str, int]) -> str:
        """
        格式化频道标识符为友好显示格式
        
        Args:
            identifier: 频道标识符
            
        Returns:
            str: 格式化后的频道标识符
        """
        raise NotImplementedError("接口方法未实现")
    
    def filter_channels(self, channels: List[str]) -> List[str]:
        """
        过滤频道列表，移除无效的频道标识符
        
        Args:
            channels: 频道标识符列表
            
        Returns:
            List[str]: 过滤后的频道标识符列表
        """
        raise NotImplementedError("接口方法未实现") 