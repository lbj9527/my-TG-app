"""
频道工具模块的核心实现
负责频道状态管理、验证和批量处理操作
"""

import asyncio
from typing import Dict, List, Optional, Set, Tuple, Union, Any, Callable
from datetime import datetime, timedelta

from pyrogram.types import Chat
from pyrogram.errors import FloodWait, ChatAdminRequired, ChannelPrivate, PeerIdInvalid, UsernameInvalid, UsernameNotOccupied

from tg_forwarder.interfaces.channel_utils_interface import ChannelUtilsInterface
from tg_forwarder.core.channel_parser import ChannelParser
from tg_forwarder.utils.exceptions import ChannelParseError
from tg_forwarder.logModule.logger import get_logger

logger = get_logger("core.channel_utils")


class ChannelUtils(ChannelUtilsInterface):
    """
    频道工具类核心实现，实现ChannelUtilsInterface接口
    提供频道状态管理、验证和批量处理操作
    """
    
    def __init__(self, client=None):
        """
        初始化频道工具类
        
        Args:
            client: 可选的Pyrogram客户端实例
        """
        self._client = client
        self._parser = ChannelParser()
        
        # 缓存机制
        self._chat_cache: Dict[Union[int, str], Dict[str, Any]] = {}
        self._cache_expiry: Dict[Union[int, str], datetime] = {}
        self._cache_duration = timedelta(minutes=30)  # 缓存有效期30分钟
        
        # 频道转发权限缓存
        self._forwarding_allowed: Set[Union[int, str]] = set()
        self._forwarding_denied: Set[Union[int, str]] = set()
        
    def set_client(self, client):
        """
        设置Pyrogram客户端实例
        
        Args:
            client: Pyrogram客户端实例
        """
        self._client = client
    
    async def is_channel_valid(self, channel_identifier: str) -> Tuple[bool, str]:
        """
        验证频道标识符是否有效
        
        Args:
            channel_identifier: 频道标识符
            
        Returns:
            Tuple[bool, str]: (是否有效, 错误消息)
        """
        try:
            channel_id, _ = self._parser.parse_channel(channel_identifier)
            
            # 如果没有客户端，只能验证格式正确性
            if self._client is None:
                return True, "无法验证频道信息：客户端未设置"
                
            # 尝试获取频道信息
            try:
                chat = await self._get_chat_info(channel_id)
                if chat:
                    return True, "频道有效"
                return False, "无法获取频道信息"
            except Exception as e:
                logger.error(f"验证频道时出错: {str(e)}")
                return False, f"验证频道时出错: {str(e)}"
                
        except ChannelParseError as e:
            return False, str(e)
    
    async def can_forward_from(self, channel_identifier: str) -> Tuple[bool, str]:
        """
        检查是否可以从指定频道转发消息
        
        Args:
            channel_identifier: 频道标识符
            
        Returns:
            Tuple[bool, str]: (是否可以转发, 原因描述)
        """
        try:
            channel_id, _ = self._parser.parse_channel(channel_identifier)
            
            # 检查缓存
            if channel_id in self._forwarding_allowed:
                return True, "允许转发（来自缓存）"
                
            if channel_id in self._forwarding_denied:
                return False, "不允许转发（来自缓存）"
            
            if self._client is None:
                return False, "无法检查转发权限：客户端未设置"
                
            # 获取频道信息
            try:
                chat = await self._get_chat_info(channel_id)
                
                if not chat:
                    self._forwarding_denied.add(channel_id)
                    return False, "无法获取频道信息"
                
                # 检查是否启用了禁止转发
                if hasattr(chat, 'has_protected_content') and chat.has_protected_content:
                    self._forwarding_denied.add(channel_id)
                    return False, "频道已禁止转发内容"
                    
                self._forwarding_allowed.add(channel_id)
                return True, "允许转发"
                
            except FloodWait as e:
                await asyncio.sleep(e.x)
                return await self.can_forward_from(channel_identifier)
                
            except (ChatAdminRequired, ChannelPrivate) as e:
                self._forwarding_denied.add(channel_id)
                return False, f"无法检查转发权限: {str(e)}"
                
            except Exception as e:
                logger.error(f"检查转发权限时出错: {str(e)}")
                return False, f"检查转发权限时出错: {str(e)}"
                
        except ChannelParseError as e:
            return False, str(e)
    
    async def can_forward_to(self, channel_identifier: str) -> Tuple[bool, str]:
        """
        检查是否可以转发消息到指定频道
        
        Args:
            channel_identifier: 频道标识符
            
        Returns:
            Tuple[bool, str]: (是否可以转发, 原因描述)
        """
        try:
            channel_id, _ = self._parser.parse_channel(channel_identifier)
            
            if self._client is None:
                return False, "无法检查转发权限：客户端未设置"
                
            # 获取频道信息
            try:
                chat = await self._get_chat_info(channel_id)
                
                if not chat:
                    return False, "无法获取频道信息"
                
                # 检查是否有发送消息的权限
                if hasattr(chat, 'permissions'):
                    if not chat.permissions.can_send_messages:
                        return False, "您在该频道没有发送消息的权限"
                
                # 检查是否有管理员权限
                try:
                    member = await self._client.get_chat_member(chat.id, "me")
                    if hasattr(member, 'can_post_messages') and not member.can_post_messages:
                        return False, "您在该频道没有发布消息的权限"
                    
                    # 如果可以管理消息，则有权限
                    if hasattr(member, 'can_delete_messages') and member.can_delete_messages:
                        return True, "您有管理员权限，可以转发到该频道"
                        
                    return True, "允许转发到此频道"
                    
                except Exception as e:
                    logger.error(f"检查频道成员权限时出错: {str(e)}")
                    return False, f"检查权限时出错: {str(e)}"
                
            except FloodWait as e:
                await asyncio.sleep(e.x)
                return await self.can_forward_to(channel_identifier)
                
            except Exception as e:
                logger.error(f"检查转发权限时出错: {str(e)}")
                return False, f"检查转发权限时出错: {str(e)}"
                
        except ChannelParseError as e:
            return False, str(e)
            
    async def get_channel_info(self, channel_identifier: str) -> Dict[str, Any]:
        """
        获取频道的详细信息
        
        Args:
            channel_identifier: 频道标识符
            
        Returns:
            Dict[str, Any]: 包含频道详细信息的字典
        """
        try:
            channel_id, _ = self._parser.parse_channel(channel_identifier)
            
            if self._client is None:
                return {"error": "无法获取频道信息：客户端未设置"}
                
            try:
                chat = await self._get_chat_info(channel_id)
                
                if not chat:
                    return {"error": "无法获取频道信息"}
                    
                # 提取有用的频道信息
                result = {
                    "id": chat.id,
                    "type": chat.type,
                    "title": getattr(chat, "title", None),
                    "username": getattr(chat, "username", None),
                    "first_name": getattr(chat, "first_name", None),
                    "last_name": getattr(chat, "last_name", None),
                    "description": getattr(chat, "description", None),
                    "members_count": getattr(chat, "members_count", None),
                    "created_at": getattr(chat, "date", None),
                    "is_verified": getattr(chat, "is_verified", None),
                    "is_restricted": getattr(chat, "is_restricted", None),
                    "is_scam": getattr(chat, "is_scam", None),
                    "is_fake": getattr(chat, "is_fake", None),
                    "has_protected_content": getattr(chat, "has_protected_content", None),
                }
                
                # 添加格式化的标识符
                result["formatted_id"] = self._parser.format_channel_identifier(
                    result["username"] if result["username"] else result["id"]
                )
                
                # 检查转发权限
                can_forward_from, from_reason = await self.can_forward_from(channel_identifier)
                can_forward_to, to_reason = await self.can_forward_to(channel_identifier)
                
                result["can_forward_from"] = can_forward_from
                result["forward_from_reason"] = from_reason
                result["can_forward_to"] = can_forward_to
                result["forward_to_reason"] = to_reason
                
                return result
                
            except Exception as e:
                logger.error(f"获取频道信息时出错: {str(e)}")
                return {"error": f"获取频道信息时出错: {str(e)}"}
                
        except ChannelParseError as e:
            return {"error": str(e)}
            
    async def batch_validate_channels(self, channel_identifiers: List[str],
                                     progress_callback: Optional[Callable[[int, int], None]] = None) -> Dict[str, bool]:
        """
        批量验证频道标识符的有效性
        
        Args:
            channel_identifiers: 频道标识符列表
            progress_callback: 可选的进度回调函数，接收(当前进度, 总数)参数
            
        Returns:
            Dict[str, bool]: 以频道标识符为键，验证结果为值的字典
        """
        if not channel_identifiers:
            return {}
            
        results = {}
        total = len(channel_identifiers)
        
        for i, channel in enumerate(channel_identifiers):
            valid, _ = await self.is_channel_valid(channel)
            results[channel] = valid
            
            if progress_callback:
                progress_callback(i + 1, total)
            
            # 添加短暂延迟，避免API限制
            await asyncio.sleep(0.1)
            
        return results
    
    async def get_actual_chat_id(self, channel_identifier: str) -> Optional[int]:
        """
        获取频道的实际chat_id（数字ID）
        
        Args:
            channel_identifier: 频道标识符
            
        Returns:
            Optional[int]: 频道的数字ID，如果无法获取则返回None
        """
        try:
            channel_id, _ = self._parser.parse_channel(channel_identifier)
            
            # 如果已经是数字ID，直接返回
            if isinstance(channel_id, int):
                return channel_id
                
            if self._client is None:
                return None
                
            # 尝试获取频道详细信息
            try:
                chat = await self._get_chat_info(channel_id)
                if chat:
                    return chat.id
                return None
            except Exception as e:
                logger.error(f"获取频道ID时出错: {str(e)}")
                return None
                
        except ChannelParseError:
            return None
            
    async def _get_chat_info(self, channel_id: Union[int, str]) -> Optional[Chat]:
        """
        获取频道信息，带缓存机制
        
        Args:
            channel_id: 频道ID或用户名
            
        Returns:
            Optional[Chat]: 频道信息对象，如果无法获取则返回None
        """
        if self._client is None:
            return None
            
        # 检查缓存是否有效
        now = datetime.now()
        if channel_id in self._chat_cache and channel_id in self._cache_expiry:
            if now < self._cache_expiry[channel_id]:
                return self._chat_cache[channel_id].get('chat')
                
        # 获取新数据
        try:
            chat = await self._client.get_chat(channel_id)
            
            # 更新缓存
            self._chat_cache[channel_id] = {'chat': chat}
            self._cache_expiry[channel_id] = now + self._cache_duration
            
            return chat
            
        except FloodWait as e:
            logger.warning(f"获取频道信息时遇到限流，等待 {e.x} 秒")
            await asyncio.sleep(e.x)
            return await self._get_chat_info(channel_id)
            
        except (PeerIdInvalid, UsernameInvalid, UsernameNotOccupied):
            logger.warning(f"无效的频道ID或用户名: {channel_id}")
            return None
            
        except Exception as e:
            logger.error(f"获取频道信息时出错: {str(e)}")
            return None
            
    def clear_cache(self):
        """清除所有缓存的频道信息"""
        self._chat_cache.clear()
        self._cache_expiry.clear()
        self._forwarding_allowed.clear()
        self._forwarding_denied.clear()
        logger.info("已清除频道信息缓存") 