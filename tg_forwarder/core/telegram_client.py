"""
Telegram客户端实现类
负责与Telegram API交互
"""

import os
import asyncio
import logging
from typing import Dict, Any, Optional, List, Union, Tuple
from datetime import datetime

from pyrogram import Client
from pyrogram.errors import FloodWait, ChatAdminRequired, ChannelPrivate, UserNotParticipant
from pyrogram.types import Message

from tg_forwarder.interfaces.client_interface import TelegramClientInterface
from tg_forwarder.interfaces.config_interface import ConfigInterface
from tg_forwarder.interfaces.logger_interface import LoggerInterface


class TelegramClient(TelegramClientInterface):
    """
    Telegram客户端，实现TelegramClientInterface接口
    负责与Telegram API交互，基于pyrogram库
    """
    
    def __init__(self, config: ConfigInterface, logger: LoggerInterface):
        """
        初始化Telegram客户端
        
        Args:
            config: 配置接口实例
            logger: 日志接口实例
        """
        self._config = config
        self._logger = logger.get_logger("TelegramClient")
        self._client = None
        self._connected = False
        self._flood_wait_retries = 0
        self._max_flood_wait_retries = 3
    
    async def connect(self) -> None:
        """
        连接到Telegram API
        
        Raises:
            Exception: 连接失败时抛出
        """
        if self._connected:
            self._logger.info("客户端已连接")
            return
        
        try:
            self._logger.info("正在连接到Telegram...")
            
            # 禁用pyrogram日志
            pyrogram_logger = logging.getLogger("pyrogram")
            pyrogram_logger.setLevel(logging.WARNING)
            
            # 创建客户端实例
            api_id = self._config.get_telegram_api_id()
            api_hash = self._config.get_telegram_api_hash()
            session_name = self._config.get_session_name()
            
            # 确保会话目录存在
            session_dir = os.path.dirname(session_name)
            if session_dir and not os.path.exists(session_dir):
                os.makedirs(session_dir)
            
            # 创建并连接客户端
            self._client = Client(
                name=session_name,
                api_id=api_id,
                api_hash=api_hash,
                no_updates=True  # 不接收更新，减少资源消耗
            )
            
            await self._client.start()
            self._connected = True
            me = await self._client.get_me()
            
            self._logger.info(f"已连接到Telegram，账号: {me.first_name} (@{me.username})")
        
        except Exception as e:
            self._logger.error(f"连接Telegram失败: {str(e)}", exc_info=True)
            if self._client:
                await self._client.stop()
                self._client = None
            self._connected = False
            raise
    
    async def disconnect(self) -> None:
        """断开与Telegram API的连接"""
        if not self._connected:
            return
        
        try:
            self._logger.info("正在断开Telegram连接...")
            if self._client:
                await self._client.stop()
            self._connected = False
            self._client = None
            self._logger.info("已断开Telegram连接")
        except Exception as e:
            self._logger.error(f"断开连接时出错: {str(e)}", exc_info=True)
    
    async def get_entity(self, channel_identifier: Union[str, int]) -> Optional[Any]:
        """
        获取频道/聊天/用户的实体信息
        
        Args:
            channel_identifier: 频道标识符
        
        Returns:
            Any: 实体信息，如果获取失败则返回None
        """
        if not self._connected:
            await self.connect()
        
        try:
            chat = await self._client.get_chat(channel_identifier)
            return chat
        except FloodWait as e:
            self._logger.warning(f"获取实体时触发FloodWait: {e.value}秒")
            if self._flood_wait_retries < self._max_flood_wait_retries:
                self._flood_wait_retries += 1
                self._logger.info(f"等待 {e.value} 秒后重试 (重试 {self._flood_wait_retries}/{self._max_flood_wait_retries})...")
                await asyncio.sleep(e.value)
                return await self.get_entity(channel_identifier)
            else:
                self._logger.error(f"获取实体失败: 超过最大重试次数")
                self._flood_wait_retries = 0
                return None
        except Exception as e:
            self._logger.error(f"获取实体信息失败: {str(e)}")
            return None
    
    async def get_message(self, channel: Union[str, int], message_id: int) -> Optional[Message]:
        """
        获取指定频道的指定消息
        
        Args:
            channel: 频道标识符
            message_id: 消息ID
        
        Returns:
            Optional[Message]: 消息对象，如果消息不存在则返回None
        """
        if not self._connected:
            await self.connect()
        
        try:
            message = await self._client.get_messages(channel, message_id)
            return message
        except FloodWait as e:
            self._logger.warning(f"获取消息时触发FloodWait: {e.value}秒")
            if self._flood_wait_retries < self._max_flood_wait_retries:
                self._flood_wait_retries += 1
                self._logger.info(f"等待 {e.value} 秒后重试 (重试 {self._flood_wait_retries}/{self._max_flood_wait_retries})...")
                await asyncio.sleep(e.value)
                return await self.get_message(channel, message_id)
            else:
                self._logger.error(f"获取消息失败: 超过最大重试次数")
                self._flood_wait_retries = 0
                return None
        except ChannelPrivate:
            self._logger.error(f"获取消息失败: 频道 {channel} 是私有的或不可访问")
            return None
        except Exception as e:
            self._logger.error(f"获取消息失败: {str(e)}")
            return None
    
    async def get_messages_range(self, channel: Union[str, int], start_id: int, end_id: int, batch_size: int = 100) -> List[Message]:
        """
        获取指定范围内的消息
        
        Args:
            channel: 频道标识符
            start_id: 起始消息ID
            end_id: 结束消息ID
            batch_size: 每批次获取的消息数量
        
        Returns:
            List[Message]: 消息列表
        """
        if not self._connected:
            await self.connect()
        
        result = []
        
        # 确保开始ID小于结束ID
        if start_id > end_id:
            start_id, end_id = end_id, start_id
        
        try:
            # 计算需要获取的消息总数
            total_messages = end_id - start_id + 1
            
            # 如果总数小于批次大小，直接获取
            if total_messages <= batch_size:
                messages = await self._client.get_messages(channel, list(range(start_id, end_id + 1)))
                return [msg for msg in messages if msg is not None]
            
            # 否则分批获取
            current_id = start_id
            while current_id <= end_id:
                # 计算当前批次的结束ID
                batch_end_id = min(current_id + batch_size - 1, end_id)
                
                self._logger.debug(f"获取消息范围: {current_id} 到 {batch_end_id}")
                
                try:
                    # 获取当前批次的消息
                    message_ids = list(range(current_id, batch_end_id + 1))
                    messages = await self._client.get_messages(channel, message_ids)
                    
                    # 过滤掉不存在的消息并添加到结果
                    valid_messages = [msg for msg in messages if msg is not None]
                    result.extend(valid_messages)
                    
                    self._logger.debug(f"获取到 {len(valid_messages)}/{len(message_ids)} 条消息")
                
                except FloodWait as e:
                    self._logger.warning(f"获取消息范围时触发FloodWait: {e.value}秒")
                    await asyncio.sleep(e.value)
                    # 不更新current_id，重试当前批次
                    continue
                
                # 更新下一批次的起始ID
                current_id = batch_end_id + 1
                
                # 每批次获取后暂停一下，避免触发限制
                await asyncio.sleep(0.5)
        
        except Exception as e:
            self._logger.error(f"获取消息范围失败: {str(e)}")
        
        return result
    
    async def get_chat_history(self, channel: Union[str, int], limit: int = 100) -> List[Message]:
        """
        获取频道历史消息
        
        Args:
            channel: 频道标识符
            limit: 最大获取消息数量
        
        Returns:
            List[Message]: 消息列表
        """
        if not self._connected:
            await self.connect()
        
        result = []
        
        try:
            async for message in self._client.get_chat_history(channel, limit=limit):
                result.append(message)
        except FloodWait as e:
            self._logger.warning(f"获取聊天历史时触发FloodWait: {e.value}秒")
            await asyncio.sleep(e.value)
            # 递归调用，重试
            remaining = limit - len(result)
            if remaining > 0:
                additional_messages = await self.get_chat_history(channel, limit=remaining)
                result.extend(additional_messages)
        except Exception as e:
            self._logger.error(f"获取聊天历史失败: {str(e)}")
        
        return result
    
    async def get_latest_message_id(self, channel: Union[str, int]) -> Optional[int]:
        """
        获取频道最新消息ID
        
        Args:
            channel: 频道标识符
        
        Returns:
            Optional[int]: 最新消息ID，如果获取失败则返回None
        """
        if not self._connected:
            await self.connect()
        
        try:
            # 获取最新消息
            messages = await self.get_chat_history(channel, limit=1)
            if messages:
                return messages[0].id
            return None
        except Exception as e:
            self._logger.error(f"获取最新消息ID失败: {str(e)}")
            return None
    
    async def get_media_group(self, chat_id: Union[str, int], message_id: int) -> List[Message]:
        """
        获取媒体组消息
        
        Args:
            chat_id: 聊天ID或用户名
            message_id: 媒体组中任一消息ID
        
        Returns:
            List[Message]: 媒体组中的所有消息
        """
        if not self._connected:
            await self.connect()
        
        try:
            # 先获取指定消息
            message = await self.get_message(chat_id, message_id)
            if not message:
                return []
            
            # 如果消息不属于媒体组，直接返回该消息
            if not message.media_group_id:
                return [message]
            
            # 获取媒体组中的所有消息
            media_group_messages = await self._client.get_media_group(chat_id, message_id)
            return media_group_messages
        
        except Exception as e:
            self._logger.error(f"获取媒体组失败: {str(e)}")
            return []
    
    async def send_message(self, chat_id: Union[str, int], text: str, **kwargs) -> Optional[Message]:
        """
        发送文本消息
        
        Args:
            chat_id: 聊天ID或用户名
            text: 消息文本
            **kwargs: 其他发送参数
        
        Returns:
            Optional[Message]: 发送的消息对象，如果发送失败则返回None
        """
        if not self._connected:
            await self.connect()
        
        try:
            return await self._client.send_message(chat_id, text, **kwargs)
        except FloodWait as e:
            self._logger.warning(f"发送消息时触发FloodWait: {e.value}秒")
            if self._flood_wait_retries < self._max_flood_wait_retries:
                self._flood_wait_retries += 1
                self._logger.info(f"等待 {e.value} 秒后重试 (重试 {self._flood_wait_retries}/{self._max_flood_wait_retries})...")
                await asyncio.sleep(e.value)
                return await self.send_message(chat_id, text, **kwargs)
            else:
                self._logger.error("发送消息失败: 超过最大重试次数")
                self._flood_wait_retries = 0
                return None
        except Exception as e:
            self._logger.error(f"发送消息失败: {str(e)}")
            return None
    
    async def send_media(self, chat_id: Union[str, int], media_type: str, media: Union[str, bytes], **kwargs) -> Optional[Message]:
        """
        发送媒体消息
        
        Args:
            chat_id: 聊天ID或用户名
            media_type: 媒体类型 (photo, video, document, audio, animation)
            media: 媒体文件路径或二进制数据
            **kwargs: 其他发送参数
        
        Returns:
            Optional[Message]: 发送的消息对象，如果发送失败则返回None
        """
        if not self._connected:
            await self.connect()
        
        try:
            method_map = {
                "photo": self._client.send_photo,
                "video": self._client.send_video,
                "document": self._client.send_document,
                "audio": self._client.send_audio,
                "animation": self._client.send_animation,
                "voice": self._client.send_voice,
                "sticker": self._client.send_sticker
            }
            
            if media_type not in method_map:
                self._logger.error(f"不支持的媒体类型: {media_type}")
                return None
            
            send_method = method_map[media_type]
            return await send_method(chat_id, media, **kwargs)
        
        except FloodWait as e:
            self._logger.warning(f"发送媒体时触发FloodWait: {e.value}秒")
            if self._flood_wait_retries < self._max_flood_wait_retries:
                self._flood_wait_retries += 1
                self._logger.info(f"等待 {e.value} 秒后重试 (重试 {self._flood_wait_retries}/{self._max_flood_wait_retries})...")
                await asyncio.sleep(e.value)
                return await self.send_media(chat_id, media_type, media, **kwargs)
            else:
                self._logger.error("发送媒体失败: 超过最大重试次数")
                self._flood_wait_retries = 0
                return None
        except Exception as e:
            self._logger.error(f"发送媒体失败: {str(e)}")
            return None
    
    async def download_media(self, message: Message, file_path: str) -> Optional[str]:
        """
        下载媒体文件
        
        Args:
            message: 消息对象
            file_path: 文件保存路径
        
        Returns:
            Optional[str]: 下载文件的完整路径，如果下载失败则返回None
        """
        if not self._connected:
            await self.connect()
        
        try:
            # 确保目录存在
            file_dir = os.path.dirname(file_path)
            if file_dir and not os.path.exists(file_dir):
                os.makedirs(file_dir)
            
            # 下载媒体
            result = await self._client.download_media(message, file_name=file_path)
            return result
        
        except FloodWait as e:
            self._logger.warning(f"下载媒体时触发FloodWait: {e.value}秒")
            if self._flood_wait_retries < self._max_flood_wait_retries:
                self._flood_wait_retries += 1
                self._logger.info(f"等待 {e.value} 秒后重试 (重试 {self._flood_wait_retries}/{self._max_flood_wait_retries})...")
                await asyncio.sleep(e.value)
                return await self.download_media(message, file_path)
            else:
                self._logger.error("下载媒体失败: 超过最大重试次数")
                self._flood_wait_retries = 0
                return None
        except Exception as e:
            self._logger.error(f"下载媒体失败: {str(e)}")
            return None
    
    async def forward_message(self, chat_id: Union[str, int], from_chat_id: Union[str, int], message_id: int) -> Optional[Message]:
        """
        转发消息
        
        Args:
            chat_id: 目标聊天ID或用户名
            from_chat_id: 源聊天ID或用户名
            message_id: 消息ID
        
        Returns:
            Optional[Message]: 转发的消息对象，如果转发失败则返回None
        """
        if not self._connected:
            await self.connect()
        
        try:
            return await self._client.forward_messages(chat_id, from_chat_id, message_id)
        
        except FloodWait as e:
            self._logger.warning(f"转发消息时触发FloodWait: {e.value}秒")
            if self._flood_wait_retries < self._max_flood_wait_retries:
                self._flood_wait_retries += 1
                self._logger.info(f"等待 {e.value} 秒后重试 (重试 {self._flood_wait_retries}/{self._max_flood_wait_retries})...")
                await asyncio.sleep(e.value)
                return await self.forward_message(chat_id, from_chat_id, message_id)
            else:
                self._logger.error("转发消息失败: 超过最大重试次数")
                self._flood_wait_retries = 0
                return None
        except ChatAdminRequired:
            self._logger.error(f"转发消息失败: 需要管理员权限")
            return None
        except ChannelPrivate:
            self._logger.error(f"转发消息失败: 频道是私有的或不可访问")
            return None
        except UserNotParticipant:
            self._logger.error(f"转发消息失败: 用户未加入频道")
            return None
        except Exception as e:
            self._logger.error(f"转发消息失败: {str(e)}")
            return None 