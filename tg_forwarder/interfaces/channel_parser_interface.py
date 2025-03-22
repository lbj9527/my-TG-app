"""
频道解析器接口定义
定义频道链接解析的核心功能接口
"""

from typing import Optional, Tuple, Union, List


class ChannelParserInterface:
    """
    频道解析器接口，定义频道链接解析的核心方法
    主要负责解析各种格式的Telegram频道链接或标识符
    """
    
    @staticmethod
    def parse_channel(channel_identifier: str) -> Tuple[Union[str, int], Optional[int]]:
        """
        解析频道标识符，支持多种格式
        
        Args:
            channel_identifier: 频道标识符，支持以下格式：
                - 公有频道/群组链接：https://t.me/channel_name
                - 用户名：@channel_name
                - 纯用户名：channel_name
                - 私有频道/群组链接：https://t.me/c/channel_id/message_id
                - 公有频道消息链接：https://t.me/channel_name/message_id
                - 私有频道邀请链接：https://t.me/+invite_code
                - 私有频道邀请码: +invite_code
                - 带前缀的私有频道链接: @https://t.me/+invite_code
        
        Returns:
            Tuple[Union[str, int], Optional[int]]: (频道标识符, 消息ID)
                - 对于公有频道，返回频道用户名和可能的消息ID
                - 对于私有频道，返回频道ID(int)和可能的消息ID
                - 对于私有频道邀请链接，返回邀请链接字符串和None
        
        Raises:
            ChannelParseError: 当无法解析频道标识符时抛出
        """
        raise NotImplementedError("接口方法未实现")
    
    @staticmethod
    def format_channel_identifier(identifier: Union[str, int]) -> str:
        """
        格式化频道标识符为友好显示格式
        
        Args:
            identifier: 频道标识符
        
        Returns:
            str: 格式化后的频道标识符
                - 对于公有频道，返回 "@channel_name" 格式
                - 对于私有频道ID，返回 "私有频道(channel_id)" 格式
                - 对于私有频道邀请链接，返回 "私有频道(邀请链接)" 格式
        """
        raise NotImplementedError("接口方法未实现")
        
    @staticmethod
    def filter_channels(channels: List[str]) -> List[str]:
        """
        过滤频道列表，移除明显无效的频道标识符
        
        Args:
            channels: 频道标识符列表
            
        Returns:
            List[str]: 过滤后的频道标识符列表，移除空字符串和无效格式
        """
        raise NotImplementedError("接口方法未实现") 