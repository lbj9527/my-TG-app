"""
频道工具插件 (ChannelPlugin)
提供频道解析、验证和信息获取功能

支持解析的频道/群组链接格式:
1. 纯数字ID格式: 
   - 例如: -1001234567890, 1234567890

2. 私有频道链接格式 (t.me/c/数字ID): 
   - 例如: https://t.me/c/1234567890
   - 例如: https://t.me/c/1234567890/123 (带消息ID)
   - 注意: 私有频道ID会自动添加 -100 前缀

3. 公开邀请链接格式 (t.me/+邀请码): 
   - 例如: https://t.me/+abcdefghijk
   - 例如: t.me/+abcdefghijk

4. 旧式私有链接格式 (t.me/joinchat/邀请哈希): 
   - 例如: https://t.me/joinchat/abcdefghijk
   - 例如: t.me/joinchat/abcdefghijk

5. 用户名格式: 
   - 例如: @username
   - 例如: username

6. 公开链接格式 (t.me/用户名): 
   - 例如: https://t.me/username
   - 例如: t.me/username
"""

import re
from typing import Dict, Any, List, Optional, Union, Tuple

from pyrogram import Client
from pyrogram.types import Chat
from pyrogram.errors import FloodWait, ChannelInvalid, ChannelPrivate, UsernameInvalid, UsernameNotOccupied

from plugins.base import PluginBase
from events import event_types as events
from utils.logger import get_logger

# 获取日志记录器
logger = get_logger("channel_plugin")

class ChannelPlugin(PluginBase):
    """
    频道工具插件，负责频道解析、验证和信息获取
    """
    
    def __init__(self, event_bus):
        """
        初始化频道工具插件
        
        Args:
            event_bus: 事件总线
        """
        super().__init__(event_bus)
        
        self.client = None
        
        # 定义插件元数据
        self.id = "channel"
        self.name = "频道工具插件"
        self.version = "1.0.0"
        self.description = "提供频道解析、验证和信息获取功能"
        self.dependencies = ["client"]  # 依赖客户端插件
    
    async def initialize(self) -> None:
        """初始化插件"""
        logger.info("正在初始化频道工具插件...")
        
        # 注册事件处理器
        self.event_bus.subscribe(events.CHANNEL_PARSE, self._handle_channel_parse)
        self.event_bus.subscribe(events.CHANNEL_GET_INFO, self._handle_channel_get_info)
        self.event_bus.subscribe(events.CHANNEL_CHECK_ACCESS, self._handle_channel_check_access)
        self.event_bus.subscribe(events.MESSAGE_GET_FROM_CHANNEL, self._handle_message_get_from_channel)
        
        # 获取客户端实例
        response = await self.event_bus.publish_and_wait(
            events.CLIENT_GET_INSTANCE,
            timeout=5.0
        )
        
        if not response or not response.get("success", False) or not response.get("client"):
            logger.error("获取客户端实例失败")
            return
            
        self.client = response.get("client")
        logger.info("频道工具插件初始化完成")
    
    async def _handle_channel_parse(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """
        处理频道解析事件
        
        Args:
            data: 事件数据，包含 "channel" 字段
            
        Returns:
            Dict[str, Any]: 解析结果
        """
        channel = data.get("channel")
        if not channel:
            return {"success": False, "error": "未提供频道参数"}
            
        try:
            entity = await self._parse_channel(channel)
            if entity:
                return {"success": True, "entity": entity}
            else:
                return {"success": False, "error": f"无法解析频道: {channel}"}
        except Exception as e:
            error_msg = f"解析频道 {channel} 时出错: {str(e)}"
            logger.exception(error_msg)
            return {"success": False, "error": error_msg}
    
    async def _handle_channel_get_info(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """
        处理获取频道信息事件
        
        Args:
            data: 事件数据，包含 "channel" 字段
            
        Returns:
            Dict[str, Any]: 频道信息
        """
        channel = data.get("channel")
        if not channel:
            return {"success": False, "error": "未提供频道参数"}
            
        try:
            entity = await self._parse_channel(channel)
            if not entity:
                return {"success": False, "error": f"无法解析频道: {channel}"}
                
            # 获取更详细的信息
            chat = await self.client.get_chat(entity.id)
            
            # 格式化返回信息
            info = {
                "id": chat.id,
                "type": chat.type,
                "title": chat.title,
                "username": chat.username,
                "description": chat.description,
                "members_count": chat.members_count if hasattr(chat, "members_count") else None,
                "linked_chat": chat.linked_chat.id if hasattr(chat, "linked_chat") and chat.linked_chat else None,
                "is_verified": chat.is_verified if hasattr(chat, "is_verified") else False,
                "is_restricted": chat.is_restricted if hasattr(chat, "is_restricted") else False,
                "is_scam": chat.is_scam if hasattr(chat, "is_scam") else False,
                "is_fake": chat.is_fake if hasattr(chat, "is_fake") else False
            }
            
            return {"success": True, "info": info}
            
        except Exception as e:
            error_msg = f"获取频道 {channel} 信息时出错: {str(e)}"
            logger.exception(error_msg)
            return {"success": False, "error": error_msg}
    
    async def _handle_channel_check_access(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """
        处理检查频道访问权限事件
        
        Args:
            data: 事件数据，包含 "channel" 字段
            
        Returns:
            Dict[str, Any]: 访问权限检查结果
        """
        channel = data.get("channel")
        if not channel:
            return {"success": False, "error": "未提供频道参数"}
            
        try:
            entity = await self._parse_channel(channel)
            if not entity:
                return {"success": False, "error": f"无法解析频道: {channel}", "has_access": False}
                
            # 尝试获取最新消息来验证访问权限
            try:
                # 需要使用async for收集消息，因为get_chat_history返回异步生成器
                messages = []
                async for message in self.client.get_chat_history(entity.id, limit=1):
                    messages.append(message)
                has_read_access = len(messages) > 0
            except (ChannelPrivate, ChannelInvalid):
                has_read_access = False
                
            # 尝试发送一条消息然后立即删除来验证写入权限
            has_write_access = False
            try:
                # 如果是频道，则需要管理员权限才能发送消息
                if entity.type == "channel":
                    # 获取自己在频道中的角色
                    member = await self.client.get_chat_member(entity.id, "me")
                    has_write_access = member.status in ("creator", "administrator")
                else:
                    # 对于群组，尝试发送一条消息
                    message = await self.client.send_message(entity.id, "测试消息，将立即删除")
                    await message.delete()
                    has_write_access = True
            except Exception:
                has_write_access = False
                
            return {
                "success": True, 
                "has_access": has_read_access,
                "has_read_access": has_read_access,
                "has_write_access": has_write_access,
                "entity": entity
            }
            
        except Exception as e:
            error_msg = f"检查频道 {channel} 访问权限时出错: {str(e)}"
            logger.exception(error_msg)
            return {"success": False, "error": error_msg, "has_access": False}
    
    async def _handle_message_get_from_channel(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """
        处理从频道获取消息事件
        
        Args:
            data: 事件数据，包含 "chat_id" 和 "limit" 字段
            
        Returns:
            Dict[str, Any]: 消息获取结果
        """
        chat_id = data.get("chat_id")
        if not chat_id:
            return {"success": False, "error": "未提供聊天ID"}
            
        limit = data.get("limit", 100)
        offset_id = data.get("offset_id", 0)  # 起始消息ID
        
        try:
            messages = []
            async for message in self.client.get_chat_history(
                chat_id=chat_id,
                limit=limit,
                offset_id=offset_id
            ):
                messages.append(message)
                
            return {"success": True, "messages": messages, "count": len(messages)}
            
        except Exception as e:
            error_msg = f"从频道 {chat_id} 获取消息时出错: {str(e)}"
            logger.exception(error_msg)
            return {"success": False, "error": error_msg}
    
    async def _parse_channel(self, channel_str: str) -> Optional[Chat]:
        """
        解析频道字符串为Chat对象
        
        Args:
            channel_str: 频道字符串，可以是用户名、邀请链接、ID等
            
        Returns:
            Optional[Chat]: 解析后的Chat对象
        """
        if not self.client:
            logger.error("客户端未初始化")
            return None
            
        try:
            # 清理字符串
            channel_str = channel_str.strip()
            
            # 尝试解析不同格式
            
            # 1. 检查是否是纯数字ID
            if channel_str.lstrip('-').isdigit():
                chat_id = int(channel_str)
                try:
                    return await self.client.get_chat(chat_id)
                except Exception:
                    logger.warning(f"无法通过ID {chat_id} 获取频道")
                    return None
            
            # 2. 检查是否是私有频道链接 (t.me/c/ID 格式)
            private_channel_match = re.match(r'(?:https?://)?t\.me/c/(\d+)(?:/(\d+))?', channel_str)
            if private_channel_match:
                chat_id = int(private_channel_match.group(1))
                # 私有频道ID需要添加 -100 前缀
                full_chat_id = int(f"-100{chat_id}")  # 正确的Telegram私有频道格式
                try:
                    return await self.client.get_chat(full_chat_id)
                except Exception as e:
                    logger.warning(f"无法通过私有频道ID {full_chat_id} 获取频道: {str(e)}")
                    return None
            
            # 3. 检查是否是邀请链接 (t.me/+xxx 格式)
            invite_link_match = re.match(r'(?:https?://)?t\.me/\+([a-zA-Z0-9_-]+)', channel_str)
            if invite_link_match:
                invite_code = invite_link_match.group(1)
                try:
                    full_link = f"https://t.me/+{invite_code}"
                    return await self.client.get_chat(full_link)
                except Exception:
                    logger.warning(f"无法通过邀请链接获取频道: {channel_str}")
                    return None
            
            # 4. 检查是否是旧式私有链接 (t.me/joinchat/xxx 格式)
            joinchat_match = re.match(r'(?:https?://)?t\.me/joinchat/([a-zA-Z0-9_-]+)', channel_str)
            if joinchat_match:
                invite_hash = joinchat_match.group(1)
                try:
                    full_link = f"https://t.me/joinchat/{invite_hash}"
                    return await self.client.get_chat(full_link)
                except Exception:
                    logger.warning(f"无法通过joinchat链接获取频道: {channel_str}")
                    return None
                
            # 5. 检查是否是用户名 (@username 格式)
            username_match = re.match(r'^@?([a-zA-Z]\w{3,30}[a-zA-Z0-9])$', channel_str)
            if username_match:
                username = username_match.group(1)
                try:
                    return await self.client.get_chat(username)
                except (UsernameInvalid, UsernameNotOccupied):
                    logger.warning(f"无效的用户名: {username}")
                    return None
            
            # 6. 检查是否是公开链接 (t.me/username 格式)
            public_match = re.match(r'(?:https?://)?t\.me/(?!c/)(?!joinchat/)([a-zA-Z]\w{3,30}[a-zA-Z0-9])', channel_str) 
            if public_match:
                username = public_match.group(1)
                try:
                    return await self.client.get_chat(username)
                except Exception:
                    logger.warning(f"无法通过公开链接获取频道: {channel_str}")
                    return None
            
            # 7. 尝试直接获取（可能是其他格式的链接等）
            try:
                return await self.client.get_chat(channel_str)
            except Exception:
                logger.warning(f"无法解析频道: {channel_str}")
                return None
                
        except Exception as e:
            logger.exception(f"解析频道 {channel_str} 时出错: {str(e)}")
            return None
    
    async def shutdown(self) -> None:
        """关闭插件"""
        logger.info("正在关闭频道工具插件...")
        
        # 取消事件订阅
        self.event_bus.unsubscribe(events.CHANNEL_PARSE, self._handle_channel_parse)
        self.event_bus.unsubscribe(events.CHANNEL_GET_INFO, self._handle_channel_get_info)
        self.event_bus.unsubscribe(events.CHANNEL_CHECK_ACCESS, self._handle_channel_check_access)
        self.event_bus.unsubscribe(events.MESSAGE_GET_FROM_CHANNEL, self._handle_message_get_from_channel)
        
        self.client = None
        logger.info("频道工具插件已关闭") 