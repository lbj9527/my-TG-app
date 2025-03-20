"""
频道工具模块，提供频道解析、验证和状态管理的高级接口
"""

import asyncio
import re
import time
from typing import Dict, List, Tuple, Union, Optional, Any
from urllib.parse import urlparse

from pyrogram import Client
from pyrogram.types import Chat

from tg_forwarder.channel_parser import ChannelParser, ChannelParseError
from tg_forwarder.logModule.logger import get_logger

logger = get_logger("channel_utils")

class ChannelUtils:
    """频道工具类，提供便捷的频道操作功能"""
    
    def __init__(self, client=None):
        """
        初始化频道工具
        
        Args:
            client: Telegram客户端实例，用于验证频道（可选）
        """
        self.client = client
        self.parser = ChannelParser()
        
        # 频道状态管理
        # 频道转发状态缓存 {channel_id: allow_forward}
        self._forward_status = {}
        # 频道验证时间缓存 {channel_id: last_verified_time}
        self._verification_time = {}
        # 缓存过期时间（秒）
        self.cache_expiry = 3600  # 默认1小时
    
    def parse_channel(self, channel_identifier: str) -> Tuple[Union[str, int], Optional[int]]:
        """
        解析频道标识符
        
        Args:
            channel_identifier: 频道标识符
            
        Returns:
            Tuple[Union[str, int], Optional[int]]: (频道标识符, 消息ID)
        """
        try:
            return ChannelParser.parse_channel(channel_identifier)
        except ChannelParseError as e:
            logger.error(f"解析错误: {str(e)}")
            return None, None
    
    def format_channel(self, identifier: Union[str, int]) -> str:
        """
        格式化频道标识符为友好显示格式
        
        Args:
            identifier: 频道标识符
            
        Returns:
            str: 格式化后的频道标识符
        """
        return ChannelParser.format_channel_identifier(identifier)
    
    def filter_channels(self, channels: List[str]) -> List[str]:
        """
        过滤频道列表，移除无效的频道标识符
        
        Args:
            channels: 频道标识符列表
            
        Returns:
            List[str]: 过滤后的频道标识符列表
        """
        return ChannelParser.filter_channels(channels)
    
    # 频道状态管理功能 - 从ChannelStateManager迁移而来
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
    
    # 频道验证功能 - 从ChannelValidator迁移而来
    async def validate_channel(self, channel: str) -> Dict[str, Any]:
        """
        验证频道是否有效，并获取频道信息
        
        Args:
            channel: 频道标识符
            
        Returns:
            Dict[str, Any]: 验证结果
        """
        # 检查是否可以使用缓存
        if self.is_cached(channel):
            logger.info(f"使用缓存的频道信息: {channel}")
            return {
                "valid": True,
                "channel_id": channel,
                "allow_forward": self.get_forward_status(channel),
                "title": str(channel),
                "error": None
            }
        
        if not self.client:
            return {
                "valid": False,
                "channel_id": None,
                "allow_forward": False,
                "title": None,
                "error": "未提供Telegram客户端实例，无法验证频道"
            }
        
        result = {
            "valid": False,
            "channel_id": None,
            "allow_forward": False,
            "title": None,
            "error": None
        }
        
        try:
            # 获取实际标识符
            actual_channel = self.get_actual_chat_id(channel)
            
            # 尝试获取频道信息
            chat = await self.client.get_entity(actual_channel)
            
            # 填充结果
            result["valid"] = True
            result["channel_id"] = chat.id
            result["title"] = chat.title
            
            # 检查是否禁止转发
            if hasattr(chat, 'has_protected_content'):
                result["allow_forward"] = not chat.has_protected_content
            else:
                result["allow_forward"] = True
            
            # 缓存状态
            self.set_forward_status(channel, result["allow_forward"])
            
            logger.info(f"频道验证成功: {channel} ({chat.title}) - {'允许' if result['allow_forward'] else '禁止'}转发")
            
        except Exception as e:
            error_msg = str(e)
            result["error"] = error_msg
            if "USERNAME_INVALID" in error_msg or "USERNAME_NOT_OCCUPIED" in error_msg:
                logger.error(f"频道验证失败: {channel} - {error_msg[:80]}")
            elif "Peer id invalid" in error_msg:
                logger.error(f"频道验证失败: {channel} - 无效的ID格式")
            else:
                logger.error(f"频道验证失败: {channel} - {error_msg[:80]}")
        
        return result
    
    async def validate_channels(self, channels: List[str]) -> Dict[str, Any]:
        """
        批量验证频道是否有效
        
        Args:
            channels: 频道标识符列表
            
        Returns:
            Dict[str, Any]: 验证结果，包含:
                - valid_channels: 有效频道列表
                - invalid_channels: 无效频道列表
                - forward_status: 频道转发状态字典
                - details: 每个频道的详细验证结果
                - protected_channels: 禁止转发的频道列表
        """
        if not self.client:
            return {
                "error": "未提供Telegram客户端实例，无法验证频道",
                "valid_channels": [],
                "invalid_channels": channels,
                "forward_status": {},
                "details": {},
                "protected_channels": []
            }
        
        if not channels:
            logger.error("没有设置目标频道")
            return {
                "valid_channels": [],
                "invalid_channels": [],
                "forward_status": {},
                "details": {},
                "protected_channels": []
            }
        
        result = {
            "valid_channels": [],
            "invalid_channels": [],
            "forward_status": {},
            "details": {},
            "protected_channels": []
        }
        
        for channel in channels:
            channel_result = await self.validate_channel(channel)
            result["details"][channel] = channel_result
            
            if channel_result["valid"]:
                result["valid_channels"].append(channel)
                result["forward_status"][channel] = channel_result["allow_forward"]
                
                if not channel_result["allow_forward"]:
                    result["protected_channels"].append(channel)
            else:
                result["invalid_channels"].append(channel)
        
        # 输出验证结果
        if result["invalid_channels"]:
            logger.warning(f"⚠️ 发现 {len(result['invalid_channels'])} 个无效频道: {', '.join(result['invalid_channels'])}")
            print("\n" + "="*60)
            print(f"⚠️ 警告: {len(result['invalid_channels'])}/{len(channels)} 个频道验证失败")
            print("💡 这些无效频道将被自动跳过")
            print("="*60 + "\n")
            
        # 输出禁止转发的频道
        if result["protected_channels"]:
            logger.warning(f"⚠️ 发现 {len(result['protected_channels'])} 个禁止转发的频道: {', '.join(result['protected_channels'])}")
            print("\n" + "="*60)
            print(f"⚠️ 注意: {len(result['protected_channels'])}/{len(result['valid_channels'])} 个有效频道禁止转发")
            print("💡 这些频道可以上传文件，但不能用作转发源")
            print("="*60 + "\n")
            
            # 如果第一个频道禁止转发，输出更明确的提示
            if channels[0] in result["protected_channels"]:
                logger.warning("⚠️ 第一个目标频道禁止转发，系统将尝试查找其他可转发的频道作为源")
        
        return result
    
    def get_actual_chat_id(self, channel: str) -> str:
        """
        根据频道标识符获取实际的聊天ID
        
        Args:
            channel: 频道标识符
            
        Returns:
            str: 实际的聊天ID
        """
        if isinstance(channel, str) and channel.startswith('https://t.me/'):
            username = channel.replace('https://t.me/', '')
            
            # 处理特殊格式的链接
            if '+' in username or 'joinchat' in username:
                return channel  # 私有频道链接保持原样
            
            # 处理带有消息ID的链接，如 https://t.me/xxzq6/3581
            elif '/' in username:
                username_parts = username.split('/')
                if len(username_parts) >= 1:
                    return '@' + username_parts[0]  # 返回格式化的用户名
            
            # 标准频道用户名
            else:
                return '@' + username
        
        return channel
    
    def get_formatted_info(self, channel: str) -> str:
        """
        获取格式化的频道信息
        
        Args:
            channel: 频道标识符
            
        Returns:
            str: 格式化后的频道信息
        """
        try:
            channel_id, message_id = self.parse_channel(channel)
            formatted = self.format_channel(channel_id)
            
            result = f"标识符: {formatted}"
            if message_id:
                result += f", 消息ID: {message_id}"
                
            if str(channel) in self._forward_status:
                status = "允许转发" if self._forward_status[str(channel)] else "禁止转发"
                result += f", 状态: {status}"
                
            return result
            
        except Exception as e:
            return f"无法获取频道信息: {str(e)}"

# 创建便捷函数
def parse_channel(channel_identifier: str) -> Tuple[Union[str, int], Optional[int]]:
    """解析频道标识符的便捷函数"""
    return ChannelParser.parse_channel(channel_identifier)

def format_channel(identifier: Union[str, int]) -> str:
    """格式化频道标识符的便捷函数"""
    return ChannelParser.format_channel_identifier(identifier)

def filter_channels(channels: List[str]) -> List[str]:
    """过滤频道列表的便捷函数"""
    return ChannelParser.filter_channels(channels)

# 创建默认实例，用于简单操作
_default_utils = ChannelUtils()

def get_channel_utils(client=None) -> ChannelUtils:
    """
    获取频道工具实例
    
    Args:
        client: Telegram客户端实例（可选）
        
    Returns:
        ChannelUtils: 频道工具实例
    """
    global _default_utils
    if client and not _default_utils.client:
        _default_utils = ChannelUtils(client)
    return _default_utils 