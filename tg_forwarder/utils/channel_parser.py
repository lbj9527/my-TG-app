"""
频道链接解析模块，负责解析各种格式的Telegram频道链接
"""

# =====================================
# 使用示例
# =====================================
"""
# 示例1: 解析不同格式的频道链接
from tg_forwarder.utils.channel_parser import ChannelParser

# 1.1 解析公开频道用户名
channel_id, message_id = ChannelParser.parse_channel("@telegram")
# 返回: ('telegram', None)

# 1.2 解析不带@的公开频道用户名
channel_id, message_id = ChannelParser.parse_channel("telegram")
# 返回: ('telegram', None)

# 1.3 解析公开频道链接
channel_id, message_id = ChannelParser.parse_channel("https://t.me/telegram")
# 返回: ('telegram', None)

# 1.4 解析带消息ID的公开频道链接
channel_id, message_id = ChannelParser.parse_channel("https://t.me/telegram/10")
# 返回: ('telegram', 10)

# 1.5 解析私有频道链接
channel_id, message_id = ChannelParser.parse_channel("https://t.me/c/1234567890/42")
# 返回: (1234567890, 42)

# 1.6 解析私有频道ID
channel_id, message_id = ChannelParser.parse_channel("1234567890")
# 返回: (1234567890, None)

# 1.7 解析私有频道邀请链接
channel_id, message_id = ChannelParser.parse_channel("https://t.me/+abcdefghijk")
# 返回: ('https://t.me/+abcdefghijk', None)

# 1.8 解析纯邀请码
channel_id, message_id = ChannelParser.parse_channel("+abcdefghijk")
# 返回: ('https://t.me/+abcdefghijk', None)

# 示例2: 格式化频道标识符为友好显示格式
from tg_forwarder.utils.channel_parser import ChannelParser

# 2.1 格式化公开频道用户名
friendly_name = ChannelParser.format_channel_identifier("telegram")
# 返回: '@telegram'

# 2.2 格式化私有频道ID
friendly_name = ChannelParser.format_channel_identifier(1234567890)
# 返回: '私有频道(1234567890)'

# 2.3 格式化私有频道邀请链接
friendly_name = ChannelParser.format_channel_identifier("https://t.me/+abcdefghijk")
# 返回: '私有频道(邀请链接)'

# 示例3: 过滤频道列表，移除无效的频道标识符
from tg_forwarder.utils.channel_parser import ChannelParser

channels = ["@telegram", "", "invalid#channel", "1234567890", "+abcdefgh"]
filtered = ChannelParser.filter_channels(channels)
# 返回: ['@telegram', '1234567890', '+abcdefgh'] (移除了空字符串和无效格式)

# 示例4: 验证频道是否存在并检查转发权限 (需要客户端实例)
import asyncio
from tg_forwarder.client import TelegramClient
from tg_forwarder.utils.channel_utils import ChannelUtils

async def validate_example():
    # 初始化客户端
    client = TelegramClient(api_config={...}, proxy_config={...})
    await client.connect()
    
    # 创建工具类
    channel_utils = ChannelUtils(client)
    
    # 4.1 验证单个频道
    result = await channel_utils.validate_channel("@telegram")
    if result["valid"]:
        print(f"频道有效: {result['title']}")
        print(f"是否允许转发: {result['allow_forward']}")
    else:
        print(f"频道无效: {result['error']}")
    
    # 4.2 批量验证多个频道
    channels = ["@telegram", "@durov", "invalid_channel"]
    result = await channel_utils.validate_channels(channels)
    print(f"有效频道: {result['valid_channels']}")
    print(f"无效频道: {result['invalid_channels']}")
    
    # 4.3 获取频道的转发状态
    allow_forward = channel_utils.get_forward_status("@telegram")
    print(f"频道是否允许转发: {allow_forward}")
    
    await client.disconnect()

# 运行异步示例
# asyncio.run(validate_example())
"""

import re
from typing import Optional, Tuple, Union, List
from urllib.parse import urlparse
import logging

# 获取日志记录器
from tg_forwarder.logModule.logger import get_logger

logger = get_logger("channel_parser")

class ChannelParseError(Exception):
    """频道解析错误异常"""
    pass

class ChannelParser:
    """频道链接解析器"""
    
    @staticmethod
    def parse_channel(channel_identifier: str) -> Tuple[Union[str, int], Optional[int]]:
        """
        解析频道标识符，支持多种格式
        
        Args:
            channel_identifier: 频道标识符，支持以下格式：
                - 公有频道/群组链接：https://t.me/channel_name
                - 用户名：@channel_name
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
        """
        if isinstance(identifier, int):
            return f"私有频道({identifier})"
        
        # 处理私有频道邀请链接
        if isinstance(identifier, str) and ('t.me/+' in identifier or identifier.startswith('+')):
            return f"私有频道(邀请链接)"
            
        return f"@{identifier}"
        
    @staticmethod
    def filter_channels(channels: List[str]) -> List[str]:
        """
        过滤频道列表，移除明显无效的频道标识符
        
        Args:
            channels: 频道标识符列表
            
        Returns:
            List[str]: 过滤后的频道标识符列表
        """
        if not channels:
            return []
            
        filtered_channels = []
        filtered_out = []
        
        for channel in channels:
            # 如果为空，跳过
            if not channel or not channel.strip():
                filtered_out.append(channel)
                continue
                
            # 标准化频道
            channel = channel.strip()
            
            # 去除@前缀便于判断
            channel_name = channel[1:] if channel.startswith('@') else channel
            
            # 如果是私有频道邀请链接，直接保留
            if channel.startswith('https://t.me/+') or channel.startswith('https://t.me/joinchat/'):
                filtered_channels.append(channel)
                continue
                
            # 如果是完整的公开频道链接，保留
            if channel.startswith('https://t.me/') and not '+' in channel.replace('https://t.me/', ''):
                filtered_channels.append(channel)
                continue
                
            # 如果是纯+开头的邀请码，保留
            if channel.startswith('+') and len(channel) > 1:
                filtered_channels.append(channel)
                continue
                
            # 如果是普通公开频道用户名（包括@前缀的形式）
            if channel.startswith('@'):
                if len(channel) > 4 and re.match(r'^@[a-zA-Z][a-zA-Z0-9_]{3,}$', channel):
                    filtered_channels.append(channel)
                    continue
                else:
                    logger.warning(f"频道名 {channel} 不符合Telegram命名规则，将被跳过")
                    filtered_out.append(channel)
                    continue
                    
            # 如果是不带@的用户名
            if re.match(r'^[a-zA-Z][a-zA-Z0-9_]{3,}$', channel):
                filtered_channels.append(channel)
                continue
                
            # 检查是否是数字ID（私有频道ID）
            try:
                int(channel)
                filtered_channels.append(channel)
                continue
            except ValueError:
                pass
                
            # 其他格式，视为无效
            logger.warning(f"频道标识符 {channel} 格式无效，将被跳过")
            filtered_out.append(channel)
            
        # 输出过滤结果
        if filtered_out:
            logger.info(f"已过滤 {len(filtered_out)} 个无效频道标识符")
            
        return filtered_channels 