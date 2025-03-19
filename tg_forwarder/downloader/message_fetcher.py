"""
消息获取模块，负责从频道获取消息并按媒体组分组
"""

import asyncio
from typing import Dict, Any, List, Optional, Union, AsyncGenerator, Tuple, Set
import time
from collections import defaultdict

from pyrogram.types import Message
from pyrogram.errors import FloodWait

from tg_forwarder.logModule.logger import get_logger

# 获取日志记录器
logger = get_logger("message_fetcher")

class MessageFetcher:
    """消息获取器，负责获取消息并处理"""
    
    def __init__(self, client, batch_size: int = 10):
        """
        初始化消息获取器
        
        Args:
            client: Telegram客户端
            batch_size: 每批获取的消息数量
        """
        self.client = client
        self.batch_size = batch_size
        self.processed_media_groups: Set[str] = set()
        self.processed_message_ids: Set[int] = set()
        self.message_metadata = defaultdict(dict)
    
    async def get_messages(self, 
                         source_chat_id: Union[str, int], 
                         start_message_id: int, 
                         end_message_id: int = 0) -> AsyncGenerator[Dict[str, Any], None]:
        """
        获取频道消息，按批次分组
        
        Args:
            source_chat_id: 源频道ID
            start_message_id: 起始消息ID
            end_message_id: 结束消息ID (0表示获取到最新消息)
            
        Yields:
            Dict[str, Any]: 消息分组信息
        """
        current_id = start_message_id
        
        # 如果end_message_id为0，获取最新消息ID
        if end_message_id == 0:
            try:
                latest_messages = await self.client.get_chat_history(source_chat_id, 1)
                if latest_messages and len(latest_messages) > 0:
                    end_message_id = latest_messages[0].id
                    logger.info(f"获取到最新消息ID: {end_message_id}")
                else:
                    logger.warning(f"无法获取最新消息ID，使用起始ID")
                    end_message_id = start_message_id
            except Exception as e:
                logger.error(f"获取最新消息ID时出错: {str(e)}")
                logger.exception("错误详情:")
                end_message_id = start_message_id
        
        # 确保end_message_id大于start_message_id
        if end_message_id < start_message_id:
            end_message_id, start_message_id = start_message_id, end_message_id
        
        total_messages = end_message_id - start_message_id + 1
        processed_count = 0
        
        logger.info(f"开始获取消息，从ID {start_message_id} 到 {end_message_id}，共 {total_messages} 条")
        
        # 批量获取消息
        while current_id <= end_message_id:
            batch_end = min(current_id + self.batch_size - 1, end_message_id)
            
            try:
                logger.debug(f"获取消息批次: {current_id} 到 {batch_end}")
                messages = await self.client.get_messages_range(source_chat_id, start_message_id, end_message_id, self.batch_size)
                
                # 处理获取到的消息
                grouped_messages = await self._process_messages(messages, source_chat_id)
                
                # 更新进度
                processed_count += len(messages)
                progress = processed_count / total_messages * 100
                logger.info(f"已处理 {processed_count}/{total_messages} 条消息 ({progress:.2f}%)")
                
                # 如果有分组后的消息，按媒体组生成任务
                if grouped_messages["media_groups"] or grouped_messages["single_messages"]:
                    yield {
                        "id": f"batch_{current_id}_{batch_end}",
                        "media_groups": grouped_messages["media_groups"],
                        "single_messages": grouped_messages["single_messages"],
                        "progress": progress
                    }
                
                # 更新当前处理的消息ID
                current_id = batch_end + 1
                
                # 短暂延迟，避免触发限制
                await asyncio.sleep(0.5)
                
            except FloodWait as e:
                wait_time = e.x
                logger.warning(f"触发频率限制，等待 {wait_time} 秒")
                await asyncio.sleep(wait_time)
            except Exception as e:
                logger.error(f"获取消息 {current_id} 到 {batch_end} 时出错: {str(e)}")
                logger.exception("错误详情:")
                current_id = batch_end + 1  # 跳过错误的批次
    
    async def _process_messages(self, messages: List[Message], chat_id: Union[str, int]) -> Dict[str, List]:
        """
        处理消息列表，按媒体组分组
        
        Args:
            messages: 消息列表
            chat_id: 频道ID
            
        Returns:
            Dict[str, List]: 按媒体组分组的消息列表
        """
        result = {
            "media_groups": [],
            "single_messages": []
        }
        
        # 第一次遍历，识别媒体组
        pending_groups = defaultdict(list)
        
        for message in messages:
            # 过滤掉None消息或已处理的消息
            if message is None or message.id in self.processed_message_ids:
                continue
            
            # 记录消息ID，防止重复处理
            self.processed_message_ids.add(message.id)
            
            # 检查是否属于媒体组
            if hasattr(message, "media_group_id") and message.media_group_id:
                media_group_id = message.media_group_id
                
                # 生成唯一的媒体组标识符
                group_key = f"{chat_id}_{media_group_id}"
                
                # 如果媒体组已处理，则跳过
                if group_key in self.processed_media_groups:
                    continue
                
                # 将消息添加到待处理媒体组
                pending_groups[group_key].append(message)
            else:
                # 如果不属于媒体组，视为单条消息
                result["single_messages"].append(message)
                
                # 存储消息元数据
                self._store_message_metadata(message)
        
        # 第二次处理，获取完整媒体组
        for group_key, messages in pending_groups.items():
            # 至少有一条消息
            if not messages:
                continue
            
            # 如果媒体组中有多条消息，获取完整媒体组
            try:
                # 使用第一条消息获取完整媒体组
                complete_group = await self.client.get_media_group(chat_id, messages[0].id)
                
                if complete_group:
                    # 标记媒体组为已处理
                    self.processed_media_groups.add(group_key)
                    
                    # 添加到结果中
                    result["media_groups"].append(complete_group)
                    
                    # 存储每条消息的元数据
                    for msg in complete_group:
                        self._store_message_metadata(msg, media_group_id=messages[0].media_group_id)
                        
                    logger.info(f"获取到完整媒体组 {group_key}，包含 {len(complete_group)} 条消息")
                else:
                    # 如果无法获取完整组，将各消息添加为单条消息
                    for msg in messages:
                        result["single_messages"].append(msg)
                        self._store_message_metadata(msg)
                    
                    logger.warning(f"无法获取完整媒体组 {group_key}，将 {len(messages)} 条消息作为单独消息处理")
            except Exception as e:
                logger.error(f"获取媒体组 {group_key} 时出错: {str(e)}")
                logger.exception("错误详情:")
                
                # 如果出错，将各消息添加为单条消息
                for msg in messages:
                    result["single_messages"].append(msg)
                    self._store_message_metadata(msg)
        
        return result
    
    def _store_message_metadata(self, message: Message, media_group_id: str = None) -> None:
        """
        存储消息元数据
        
        Args:
            message: 消息对象
            media_group_id: 媒体组ID，如果消息不属于媒体组则为None
        """
        # 确保消息ID存在
        if not message or not hasattr(message, "id"):
            return
        
        # 提取基本信息
        msg_id = message.id
        chat_id = message.chat.id if hasattr(message, "chat") and message.chat else None
        
        metadata = {
            "message_id": msg_id,
            "chat_id": chat_id,
            "date": message.date if hasattr(message, "date") else None,
            "media_group_id": media_group_id or (message.media_group_id if hasattr(message, "media_group_id") else None),
            "message_type": self._get_message_type(message),
            "caption": message.caption if hasattr(message, "caption") else None,
            "caption_entities": message.caption_entities if hasattr(message, "caption_entities") else None,
            "file_name": getattr(getattr(message, "document", None), "file_name", None),
            "file_size": getattr(getattr(message, "document", None), "file_size", None),
            "mime_type": getattr(getattr(message, "document", None), "mime_type", None),
            "duration": getattr(getattr(message, "video", None), "duration", None) or 
                       getattr(getattr(message, "audio", None), "duration", None),
            "width": getattr(getattr(message, "photo", None), "width", None) or 
                    getattr(getattr(message, "video", None), "width", None),
            "height": getattr(getattr(message, "photo", None), "height", None) or 
                     getattr(getattr(message, "video", None), "height", None),
            "performer": getattr(getattr(message, "audio", None), "performer", None),
            "title": getattr(getattr(message, "audio", None), "title", None)
        }
        
        # 存储元数据
        self.message_metadata[msg_id] = metadata
    
    def _get_message_type(self, message: Message) -> str:
        """
        获取消息类型
        
        Args:
            message: 消息对象
            
        Returns:
            str: 消息类型
        """
        if hasattr(message, "text") and message.text:
            return "text"
        elif hasattr(message, "photo") and message.photo:
            return "photo"
        elif hasattr(message, "video") and message.video:
            return "video"
        elif hasattr(message, "document") and message.document:
            return "document"
        elif hasattr(message, "audio") and message.audio:
            return "audio"
        elif hasattr(message, "voice") and message.voice:
            return "voice"
        elif hasattr(message, "sticker") and message.sticker:
            return "sticker"
        elif hasattr(message, "animation") and message.animation:
            return "animation"
        elif hasattr(message, "contact") and message.contact:
            return "contact"
        elif hasattr(message, "location") and message.location:
            return "location"
        elif hasattr(message, "poll") and message.poll:
            return "poll"
        else:
            return "unknown" 