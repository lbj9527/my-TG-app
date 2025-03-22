"""
频道相关组件的工厂模块
提供获取ChannelParser和ChannelUtils实例的工厂函数
"""

from typing import Optional

from tg_forwarder.core.channel_parser import ChannelParser
from tg_forwarder.core.channel_utils import ChannelUtils
from tg_forwarder.logModule.logger import get_logger

logger = get_logger("core.channel_factory")

# 全局单例实例
_global_channel_parser: Optional[ChannelParser] = None
_global_channel_utils: Optional[ChannelUtils] = None


def get_channel_parser() -> ChannelParser:
    """
    获取全局ChannelParser实例
    
    Returns:
        ChannelParser: 全局ChannelParser实例
    """
    global _global_channel_parser
    
    if _global_channel_parser is None:
        logger.info("创建新的ChannelParser实例")
        _global_channel_parser = ChannelParser()
    
    return _global_channel_parser


def get_channel_utils(client=None) -> ChannelUtils:
    """
    获取全局ChannelUtils实例
    
    Args:
        client: 可选的Telegram客户端实例，如果提供，将更新ChannelUtils使用的客户端
        
    Returns:
        ChannelUtils: 全局ChannelUtils实例
    """
    global _global_channel_utils
    
    if _global_channel_utils is None:
        logger.info("创建新的ChannelUtils实例")
        _global_channel_utils = ChannelUtils(client)
    elif client is not None:
        logger.info("更新ChannelUtils实例的客户端")
        _global_channel_utils.set_client(client)
    
    return _global_channel_utils


# 常用函数的快捷方式
async def get_actual_chat_id(channel_identifier: str):
    """
    获取频道的实际chat_id（数字ID）
    
    Args:
        channel_identifier: 频道标识符
        
    Returns:
        频道的数字ID，如果无法获取则返回None
    """
    utils = get_channel_utils()
    return await utils.get_actual_chat_id(channel_identifier)


def parse_channel(channel_identifier: str):
    """
    解析频道标识符
    
    Args:
        channel_identifier: 频道标识符
        
    Returns:
        (频道标识符, 消息ID)元组
    """
    parser = get_channel_parser()
    return parser.parse_channel(channel_identifier)


def format_channel(identifier):
    """
    格式化频道标识符为友好显示格式
    
    Args:
        identifier: 频道标识符
        
    Returns:
        格式化后的频道标识符字符串
    """
    parser = get_channel_parser()
    return parser.format_channel_identifier(identifier)


async def is_channel_valid(channel_identifier: str):
    """
    验证频道标识符是否有效
    
    Args:
        channel_identifier: 频道标识符
        
    Returns:
        (是否有效, 错误消息)元组
    """
    utils = get_channel_utils()
    return await utils.is_channel_valid(channel_identifier)


async def can_forward_from(channel_identifier: str):
    """
    检查是否可以从指定频道转发消息
    
    Args:
        channel_identifier: 频道标识符
        
    Returns:
        (是否可以转发, 原因描述)元组
    """
    utils = get_channel_utils()
    return await utils.can_forward_from(channel_identifier)


async def can_forward_to(channel_identifier: str):
    """
    检查是否可以转发消息到指定频道
    
    Args:
        channel_identifier: 频道标识符
        
    Returns:
        (是否可以转发, 原因描述)元组
    """
    utils = get_channel_utils()
    return await utils.can_forward_to(channel_identifier)


def filter_channels(channels):
    """
    过滤频道列表，移除明显无效的频道标识符
    
    Args:
        channels: 频道标识符列表
        
    Returns:
        过滤后的频道标识符列表
    """
    parser = get_channel_parser()
    return parser.filter_channels(channels) 