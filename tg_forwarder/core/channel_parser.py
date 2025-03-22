"""
频道链接解析模块的核心实现
负责解析各种格式的Telegram频道链接
"""

import re
from typing import Optional, Tuple, Union, List
from urllib.parse import urlparse

from tg_forwarder.interfaces.channel_parser_interface import ChannelParserInterface
from tg_forwarder.utils.exceptions import ChannelParseError
from tg_forwarder.logModule.logger import get_logger

logger = get_logger("core.channel_parser")


class ChannelParser(ChannelParserInterface):
    """
    频道链接解析器核心实现类，实现ChannelParserInterface接口
    提供各种格式Telegram频道链接的解析、格式化和过滤功能
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
        if not channel_identifier:
            raise ChannelParseError("频道标识符不能为空")
            
        original_identifier = channel_identifier
        
        # 处理带@前缀的链接，例如 @https://t.me/+invite_code
        if channel_identifier.startswith('@https://'):
            channel_identifier = channel_identifier[1:]  # 去掉@前缀
        
        # 处理纯+开头的邀请码
        if channel_identifier.startswith('+') and '/' not in channel_identifier:
            # 这是私有频道的邀请码
            return f"https://t.me/{channel_identifier}", None
        
        # 处理@开头的用户名
        if channel_identifier.startswith('@'):
            return channel_identifier[1:], None
        
        # 处理URL
        if channel_identifier.startswith(('https://', 'http://')):
            try:
                parsed_url = urlparse(channel_identifier)
                path_parts = parsed_url.path.strip('/').split('/')
                
                # 检查域名是否为t.me
                if parsed_url.netloc != 't.me':
                    raise ChannelParseError(f"不支持的域名: {parsed_url.netloc}")
                
                # 处理私有频道邀请链接: https://t.me/+invite_code
                if len(path_parts) == 1 and path_parts[0].startswith('+'):
                    return channel_identifier, None
                
                # 处理公有频道链接: https://t.me/channel_name
                if len(path_parts) == 1:
                    return path_parts[0], None
                
                # 处理私有频道链接: https://t.me/c/channel_id/message_id
                if len(path_parts) >= 2 and path_parts[0] == 'c':
                    try:
                        channel_id = int(path_parts[1])
                        message_id = int(path_parts[2]) if len(path_parts) > 2 else None
                        return channel_id, message_id
                    except (ValueError, IndexError):
                        raise ChannelParseError(f"无效的私有频道链接: {channel_identifier}")
                
                # 处理公有频道消息链接: https://t.me/channel_name/message_id
                if len(path_parts) == 2:
                    channel_name = path_parts[0]
                    try:
                        message_id = int(path_parts[1])
                        return channel_name, message_id
                    except ValueError:
                        raise ChannelParseError(f"无效的消息ID: {path_parts[1]}")
                
                raise ChannelParseError(f"无法解析频道链接: {channel_identifier}")
            
            except Exception as e:
                if isinstance(e, ChannelParseError):
                    raise
                raise ChannelParseError(f"解析频道链接时出错: {str(e)}")
        
        # 尝试将输入解析为数字（频道ID）
        try:
            return int(channel_identifier), None
        except ValueError:
            pass
        
        # 如果没有前缀，假设是频道用户名
        if re.match(r'^[a-zA-Z][a-zA-Z0-9_]{3,}$', channel_identifier):
            return channel_identifier, None
        
        raise ChannelParseError(f"无法识别的频道标识符格式: {original_identifier}")
    
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
        if identifier is None:
            return "未知频道"
            
        if isinstance(identifier, int):
            return f"私有频道({identifier})"
        
        # 处理私有频道邀请链接
        if isinstance(identifier, str) and ('t.me/+' in identifier or identifier.startswith('+')):
            return f"私有频道(邀请链接)"
        
        # 处理已经带@前缀的情况
        if isinstance(identifier, str) and identifier.startswith('@'):
            return identifier
            
        return f"@{identifier}"
        
    @staticmethod
    def filter_channels(channels: List[str]) -> List[str]:
        """
        过滤频道列表，移除明显无效的频道标识符
        
        Args:
            channels: 频道标识符列表
            
        Returns:
            List[str]: 过滤后的频道标识符列表，移除空字符串和无效格式
        """
        if not channels:
            return []
            
        filtered_channels = []
        filtered_out = []
        
        for channel in channels:
            if not channel or not isinstance(channel, str):
                filtered_out.append(channel)
                continue
                
            channel = channel.strip()
            if not channel:
                filtered_out.append(channel)
                continue
                
            # 尝试解析频道标识符，验证格式
            try:
                ChannelParser.parse_channel(channel)
                filtered_channels.append(channel)
            except ChannelParseError:
                logger.warning(f"过滤掉无效的频道标识符: {channel}")
                filtered_out.append(channel)
                
        if filtered_out:
            logger.info(f"已过滤 {len(filtered_out)} 个无效的频道标识符")
            
        return filtered_channels 