"""
消息发送模块，负责发送消息到目标频道
"""

import os
import asyncio
import time
from typing import Dict, Any, List, Union, Optional, Tuple

from pyrogram.errors import FloodWait, SlowmodeWait, ChannelPrivate, ChatForwardsRestricted

from tg_forwarder.logModule.logger import get_logger
from tg_forwarder.uploader.utils import TelegramClientManager, MediaUtils
from tg_forwarder.channel_utils import ChannelUtils, get_channel_utils

# 获取日志记录器
logger = get_logger("message_sender")


class MessageSender:
    """消息发送器，负责发送消息到目标频道"""
    
    def __init__(self, client_manager: TelegramClientManager, wait_time: float = 1.0, 
                 retry_count: int = 3, retry_delay: int = 5):
        """
        初始化消息发送器
        
        Args:
            client_manager: Telegram客户端管理器
            wait_time: 消息间隔时间（秒）
            retry_count: 重试次数
            retry_delay: 重试延迟时间（秒）
        """
        self.client_manager = client_manager
        self.wait_time = wait_time
        self.retry_count = retry_count
        self.retry_delay = retry_delay
        self.channel_utils = ChannelUtils(client_manager.client)
    
    @property
    def client(self):
        """获取客户端实例"""
        if self.client_manager and self.client_manager.client:
            return self.client_manager.client
        return None
    
    async def send_media_group(self, messages: List[Dict[str, Any]], channel_id: Union[str, int]) -> Dict[str, Any]:
        """
        发送媒体组
        
        Args:
            messages: 消息列表
            channel_id: 目标频道ID
            
        Returns:
            Dict[str, Any]: 发送结果
        """
        if not messages:
            return {"success": False, "error": "没有要发送的消息"}
        
        # 确保客户端已初始化
        if not self.client:
            return {"success": False, "error": "客户端未初始化"}
        
        # 处理私密频道链接
        target_chat_id = channel_id
        if isinstance(channel_id, str) and (channel_id.startswith('+') or 't.me/+' in channel_id):
            # 如果是纯邀请码格式，转换为完整链接
            if channel_id.startswith('+') and '/' not in channel_id:
                channel_id = f"https://t.me/{channel_id}"
            
            logger.info(f"处理媒体组发送的私密频道链接: {channel_id}")
            
            # 尝试获取实际chat实体和ID
            try:
                chat_entity = await self.client_manager.client.get_chat(channel_id)
                if chat_entity:
                    target_chat_id = chat_entity.id
                    logger.info(f"成功获取私密频道ID: {target_chat_id}")
                else:
                    return {"success": False, "error": f"无法获取私密频道实体: {channel_id}"}
            except Exception as e:
                logger.error(f"获取私密频道实体时出错: {str(e)}")
                return {"success": False, "error": f"无法处理私密频道链接: {str(e)}"}
        
        # 创建媒体组
        media_group = MediaUtils.create_media_group(messages)
        
        if not media_group:
            return {"success": False, "error": "没有有效的媒体文件可发送"}
        
        # 尝试发送媒体组
        for attempt in range(self.retry_count + 1):
            try:
                logger.info(f"正在发送媒体组到 {target_chat_id} (尝试 {attempt+1}/{self.retry_count+1})...")
                start_time = time.time()
                
                # 使用客户端管理器的错误处理包装器
                result = await self.client_manager.with_error_handling(
                    self.client.send_media_group,
                    chat_id=target_chat_id,
                    media=media_group
                )
                
                duration = time.time() - start_time
                logger.info(f"成功发送媒体组 ({len(result)} 条消息, 耗时 {duration:.1f}秒)")
                
                # 提取消息ID
                message_ids = [msg.id for msg in result]
                
                return {
                    "success": True,
                    "message_ids": message_ids,
                    "duration": duration
                }
                
            except FloodWait as e:
                wait_time = e.value
                logger.warning(f"触发频率限制，等待 {wait_time} 秒...")
                await asyncio.sleep(wait_time)
                # 不增加attempt计数，这不算作一次失败
                attempt -= 1
                
            except SlowmodeWait as e:
                wait_time = e.value
                logger.warning(f"触发慢速模式，等待 {wait_time} 秒...")
                await asyncio.sleep(wait_time)
                # 不增加attempt计数，这不算作一次失败
                attempt -= 1
                
            except ChatForwardsRestricted as e:
                logger.error(f"频道禁止转发: {str(e)}")
                return {"success": False, "error": f"频道禁止转发: {str(e)}"}
                
            except ChannelPrivate as e:
                logger.error(f"无法访问私有频道: {str(e)}")
                return {"success": False, "error": f"无法访问私有频道: {str(e)}"}
            
            except Exception as e:
                error_msg = str(e)
                logger.error(f"发送媒体组时出错: {error_msg}")
                
                if attempt < self.retry_count:
                    retry_wait = self.retry_delay * (attempt + 1)
                    logger.info(f"将在 {retry_wait} 秒后重试...")
                    await asyncio.sleep(retry_wait)
                else:
                    return {"success": False, "error": error_msg}
        
        return {"success": False, "error": "发送媒体组失败，达到最大重试次数"}
    
    async def send_single_message(self, message: Dict[str, Any], channel_id: Union[str, int]) -> Dict[str, Any]:
        """
        发送单条消息
        
        Args:
            message: 消息数据
            channel_id: 目标频道ID
            
        Returns:
            Dict[str, Any]: 发送结果
        """
        # 确保客户端已初始化
        if not self.client:
            return {"success": False, "error": "客户端未初始化"}
        
        # 处理私密频道链接
        target_chat_id = channel_id
        if isinstance(channel_id, str) and (channel_id.startswith('+') or 't.me/+' in channel_id):
            # 如果是纯邀请码格式，转换为完整链接
            if channel_id.startswith('+') and '/' not in channel_id:
                channel_id = f"https://t.me/{channel_id}"
            
            logger.info(f"处理单条消息发送的私密频道链接: {channel_id}")
            
            # 尝试获取实际chat实体和ID
            try:
                chat_entity = await self.client_manager.client.get_chat(channel_id)
                if chat_entity:
                    target_chat_id = chat_entity.id
                    logger.info(f"成功获取私密频道ID: {target_chat_id}")
                else:
                    return {"success": False, "error": f"无法获取私密频道实体: {channel_id}"}
            except Exception as e:
                logger.error(f"获取私密频道实体时出错: {str(e)}")
                return {"success": False, "error": f"无法处理私密频道链接: {str(e)}"}
        
        message_id = message.get("message_id")
        message_type = message.get("message_type")
        file_path = message.get("file_path")
        
        # 处理纯文本消息
        if message_type == "text":
            return await self._send_text_message(message, target_chat_id)
        
        # 处理媒体消息
        if not file_path or not os.path.exists(file_path):
            return {"success": False, "error": f"文件 {file_path} 不存在"}
        
        # 准备发送参数
        args = MediaUtils.prepare_single_message_args(message, target_chat_id)
        
        # 根据消息类型选择发送方法
        if message_type == "photo":
            send_func = self.client.send_photo
        elif message_type == "video":
            send_func = self.client.send_video
        elif message_type == "document":
            send_func = self.client.send_document
        elif message_type == "audio":
            send_func = self.client.send_audio
        else:
            return {"success": False, "error": f"不支持的媒体类型: {message_type}"}
        
        # 尝试发送媒体
        for attempt in range(self.retry_count + 1):
            try:
                logger.info(f"发送 {message_type} 到频道 {target_chat_id} (尝试 {attempt+1}/{self.retry_count+1})")
                
                # 使用客户端管理器的错误处理包装器
                sent_message = await self.client_manager.with_error_handling(
                    send_func,
                    **args
                )
                
                if sent_message:
                    logger.info(f"{message_type} 发送成功，消息ID: {sent_message.id}")
                    
                    return {
                        "success": True,
                        "message_id": sent_message.id,
                        "channel_id": channel_id
                    }
            
            except FloodWait as e:
                wait_time = e.value
                logger.warning(f"触发频率限制，等待 {wait_time} 秒")
                await asyncio.sleep(wait_time)
                continue
            
            except SlowmodeWait as e:
                wait_time = e.value
                logger.warning(f"触发慢速模式，等待 {wait_time} 秒")
                await asyncio.sleep(wait_time)
                continue
            
            except Exception as e:
                logger.error(f"发送 {message_type} 时出错: {str(e)}")
                
                if attempt < self.retry_count:
                    retry_wait = self.retry_delay * (attempt + 1)
                    logger.info(f"将在 {retry_wait} 秒后重试...")
                    await asyncio.sleep(retry_wait)
                else:
                    return {"success": False, "error": str(e)}
        
        return {"success": False, "error": f"发送 {message_type} 失败，达到最大重试次数"}
    
    async def _send_text_message(self, message: Dict[str, Any], channel_id: Union[str, int]) -> Dict[str, Any]:
        """
        发送文本消息
        
        Args:
            message: 消息数据
            channel_id: 目标频道ID
            
        Returns:
            Dict[str, Any]: 发送结果
        """
        text = message.get("text", "")
        entities = message.get("text_entities")
        
        for attempt in range(self.retry_count + 1):
            try:
                logger.info(f"发送文本消息到频道 {channel_id} (尝试 {attempt+1}/{self.retry_count+1})")
                
                # 使用客户端管理器的错误处理包装器
                sent_message = await self.client_manager.with_error_handling(
                    self.client.send_message,
                    chat_id=channel_id,
                    text=text,
                    entities=entities
                )
                
                if sent_message:
                    logger.info(f"文本消息发送成功，消息ID: {sent_message.id}")
                    
                    return {
                        "success": True,
                        "message_id": sent_message.id,
                        "channel_id": channel_id
                    }
            
            except FloodWait as e:
                wait_time = e.value
                logger.warning(f"触发频率限制，等待 {wait_time} 秒")
                await asyncio.sleep(wait_time)
                continue
            
            except Exception as e:
                logger.error(f"发送文本消息时出错: {str(e)}")
                
                if attempt < self.retry_count:
                    retry_wait = self.retry_delay * (attempt + 1)
                    await asyncio.sleep(retry_wait)
                else:
                    return {"success": False, "error": str(e)}
        
        return {"success": False, "error": "发送文本消息失败，达到最大重试次数"}
    
    async def copy_message(self, source_channel: Union[str, int], message_id: int, 
                         target_channel: Union[str, int]) -> Dict[str, Any]:
        """
        从一个频道复制消息到另一个频道
        
        Args:
            source_channel: 源频道ID
            message_id: 消息ID
            target_channel: 目标频道ID
            
        Returns:
            Dict[str, Any]: 复制结果
        """
        # 确保客户端已初始化
        if not self.client:
            return {"success": False, "error": "客户端未初始化"}
        
        # 使用channel_utils获取实际聊天ID
        target_chat_id = self.channel_utils.get_actual_chat_id(target_channel)
        source_chat_id = self.channel_utils.get_actual_chat_id(source_channel)
        
        for attempt in range(self.retry_count + 1):
            try:
                logger.info(f"复制消息从频道 {source_chat_id} 到 {target_chat_id} (尝试 {attempt+1}/{self.retry_count+1})")
                
                # 使用客户端管理器的错误处理包装器
                copied_message = await self.client_manager.with_error_handling(
                    self.client.copy_message,
                    chat_id=target_chat_id,
                    from_chat_id=source_chat_id,
                    message_id=message_id
                )
                
                if copied_message:
                    logger.info(f"消息复制成功，新消息ID: {copied_message.id}")
                    
                    return {
                        "success": True,
                        "message_id": copied_message.id,
                        "channel_id": target_channel
                    }
            
            except FloodWait as e:
                wait_time = e.value
                logger.warning(f"触发频率限制，等待 {wait_time} 秒")
                await asyncio.sleep(wait_time)
                continue
            
            except Exception as e:
                logger.error(f"复制消息时出错: {str(e)}")
                
                if attempt < self.retry_count:
                    retry_wait = self.retry_delay * (attempt + 1)
                    logger.info(f"将在 {retry_wait} 秒后重试...")
                    await asyncio.sleep(retry_wait)
                else:
                    return {"success": False, "error": str(e)}
        
        return {"success": False, "error": "复制消息失败，达到最大重试次数"}
    
    async def copy_media_group(self, source_channel: Union[str, int], message_id: int, 
                             target_channel: Union[str, int]) -> Dict[str, Any]:
        """
        从一个频道复制媒体组到另一个频道
        
        Args:
            source_channel: 源频道ID
            message_id: 媒体组中第一条消息的ID
            target_channel: 目标频道ID
            
        Returns:
            Dict[str, Any]: 复制结果
        """
        # 确保客户端已初始化
        if not self.client:
            return {"success": False, "error": "客户端未初始化"}
        
        # 使用channel_utils获取实际聊天ID
        target_chat_id = self.channel_utils.get_actual_chat_id(target_channel)
        source_chat_id = self.channel_utils.get_actual_chat_id(source_channel)
        
        for attempt in range(self.retry_count + 1):
            try:
                logger.info(f"复制媒体组从频道 {source_chat_id} 到 {target_chat_id} (尝试 {attempt+1}/{self.retry_count+1})")
                
                # 使用客户端管理器的错误处理包装器
                copied_messages = await self.client_manager.with_error_handling(
                    self.client.copy_media_group,
                    chat_id=target_chat_id,
                    from_chat_id=source_chat_id,
                    message_id=message_id
                )
                
                if copied_messages:
                    message_ids = [msg.id for msg in copied_messages]
                    logger.info(f"媒体组复制成功，共 {len(message_ids)} 条消息")
                    
                    return {
                        "success": True,
                        "message_ids": message_ids,
                        "channel_id": target_channel
                    }
            
            except FloodWait as e:
                wait_time = e.value
                logger.warning(f"触发频率限制，等待 {wait_time} 秒")
                await asyncio.sleep(wait_time)
                continue
            
            except Exception as e:
                logger.error(f"复制媒体组时出错: {str(e)}")
                
                if attempt < self.retry_count:
                    retry_wait = self.retry_delay * (attempt + 1)
                    logger.info(f"将在 {retry_wait} 秒后重试...")
                    await asyncio.sleep(retry_wait)
                else:
                    return {"success": False, "error": str(e)}
        
        return {"success": False, "error": "复制媒体组失败，达到最大重试次数"} 