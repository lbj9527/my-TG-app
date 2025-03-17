"""
媒体上传模块，负责上传媒体文件到目标频道
"""

import os
import asyncio
import logging
import time
import json
from typing import Dict, Any, List, Union, Optional, Set, Tuple
from collections import defaultdict

from pyrogram.types import InputMediaPhoto, InputMediaVideo, InputMediaDocument, InputMediaAudio
from pyrogram.errors import FloodWait, ChatForwardsRestricted, SlowmodeWait, ChannelPrivate

from tg_forwarder.utils.logger import get_logger

# 获取日志记录器
logger = get_logger("media_uploader")

class MediaUploader:
    """媒体上传器，负责上传媒体文件到目标频道"""
    
    def __init__(self, client, target_channels: List[Union[str, int]], temp_folder: str = "temp",
                 wait_time: float = 1.0, retry_count: int = 3, retry_delay: int = 5):
        """
        初始化媒体上传器
        
        Args:
            client: Telegram客户端
            target_channels: 目标频道列表
            temp_folder: 临时文件夹路径
            wait_time: 消息间隔时间（秒）
            retry_count: 重试次数
            retry_delay: 重试延迟时间（秒）
        """
        self.client = client
        self.target_channels = target_channels
        self.temp_folder = temp_folder
        self.wait_time = wait_time
        self.retry_count = retry_count
        self.retry_delay = retry_delay
        
        # 上传记录文件路径
        self.upload_history_path = os.path.join(self.temp_folder, "upload_history.json")
        
        # 上传历史记录
        self.upload_history = self._load_history()
    
    def _load_history(self) -> Dict[str, Dict[str, Any]]:
        """
        加载上传历史记录
        
        Returns:
            Dict[str, Dict[str, Any]]: 上传历史记录
        """
        try:
            if os.path.exists(self.upload_history_path):
                with open(self.upload_history_path, "r", encoding="utf-8") as f:
                    history = json.load(f)
                logger.info(f"加载上传历史记录: {len(history)} 条记录")
                return history
        except Exception as e:
            logger.error(f"加载上传历史记录时出错: {str(e)}")
        
        return {}
    
    def _save_history(self) -> None:
        """保存上传历史记录"""
        try:
            with open(self.upload_history_path, "w", encoding="utf-8") as f:
                json.dump(self.upload_history, f, ensure_ascii=False, indent=2)
            logger.debug("保存上传历史记录成功")
        except Exception as e:
            logger.error(f"保存上传历史记录时出错: {str(e)}")
    
    async def upload_batch(self, batch_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        上传一批媒体文件
        
        Args:
            batch_data: 批次数据，包含媒体组和单条消息
            
        Returns:
            Dict[str, Any]: 上传结果
        """
        start_time = time.time()
        
        # 提取媒体组和单条消息
        media_groups = batch_data.get("media_groups", [])
        single_messages = batch_data.get("single_messages", [])
        
        total_groups = len(media_groups)
        total_singles = len(single_messages)
        
        logger.info(f"开始上传一批数据: {total_groups} 个媒体组, {total_singles} 条单独消息")
        
        # 处理统计
        stats = {
            "total_groups": total_groups,
            "total_singles": total_singles,
            "success_groups": 0,
            "success_singles": 0,
            "failed_groups": 0,
            "failed_singles": 0,
            "start_time": start_time
        }
        
        # 先处理媒体组，因为需要保持消息组的完整性
        for group in media_groups:
            group_id = group.get("media_group_id")
            messages = group.get("messages", [])
            
            if not group_id or not messages:
                continue
            
            # 检查是否已上传
            if self._is_group_uploaded(group_id, self.target_channels[0]):
                logger.info(f"媒体组 {group_id} 已上传到目标频道，跳过")
                stats["success_groups"] += 1
                continue
            
            # 上传到第一个目标频道
            first_channel = self.target_channels[0]
            
            try:
                result = await self._upload_media_group(messages, first_channel)
                
                if result.get("success"):
                    stats["success_groups"] += 1
                    
                    # 记录上传结果
                    self._record_upload(group_id, first_channel, result.get("message_ids", []))
                    
                    # 将消息从第一个频道复制到其他频道
                    if len(self.target_channels) > 1 and result.get("message_ids"):
                        first_message_id = result["message_ids"][0]
                        await self._forward_to_other_channels(first_channel, first_message_id, group_id)
                else:
                    stats["failed_groups"] += 1
                    logger.error(f"上传媒体组 {group_id} 失败: {result.get('error', '未知错误')}")
            
            except Exception as e:
                stats["failed_groups"] += 1
                logger.error(f"上传媒体组 {group_id} 时发生错误: {str(e)}")
            
            # 等待一段时间，避免触发限制
            await asyncio.sleep(self.wait_time)
        
        # 处理单条消息
        for message in single_messages:
            message_id = message.get("message_id")
            
            if not message_id:
                continue
            
            # 检查是否已上传
            if self._is_message_uploaded(message_id, self.target_channels[0]):
                logger.info(f"消息 {message_id} 已上传到目标频道，跳过")
                stats["success_singles"] += 1
                continue
            
            # 上传到第一个目标频道
            first_channel = self.target_channels[0]
            
            try:
                result = await self._upload_single_message(message, first_channel)
                
                if result.get("success"):
                    stats["success_singles"] += 1
                    
                    # 记录上传结果
                    self._record_upload(message_id, first_channel, [result.get("message_id")])
                    
                    # 将消息从第一个频道复制到其他频道
                    if len(self.target_channels) > 1 and result.get("message_id"):
                        await self._forward_to_other_channels(first_channel, result["message_id"], message_id)
                else:
                    stats["failed_singles"] += 1
                    logger.error(f"上传消息 {message_id} 失败: {result.get('error', '未知错误')}")
            
            except Exception as e:
                stats["failed_singles"] += 1
                logger.error(f"上传消息 {message_id} 时发生错误: {str(e)}")
            
            # 等待一段时间，避免触发限制
            await asyncio.sleep(self.wait_time)
        
        # 计算总体统计
        stats["end_time"] = time.time()
        stats["duration"] = stats["end_time"] - stats["start_time"]
        stats["success_total"] = stats["success_groups"] + stats["success_singles"]
        stats["failed_total"] = stats["failed_groups"] + stats["failed_singles"]
        stats["total_messages"] = stats["total_groups"] + stats["total_singles"]
        
        # 计算成功率
        if stats["total_messages"] > 0:
            stats["success_rate"] = stats["success_total"] / stats["total_messages"] * 100
        else:
            stats["success_rate"] = 0
        
        logger.info(
            f"上传批次完成，总计: {stats['total_messages']} 条，成功: {stats['success_total']} 条 "
            f"({stats['success_rate']:.1f}%)，失败: {stats['failed_total']} 条，"
            f"耗时: {stats['duration']:.1f} 秒"
        )
        
        # 保存上传历史
        self._save_history()
        
        return stats
    
    async def _upload_media_group(self, messages: List[Dict[str, Any]], channel_id: Union[str, int]) -> Dict[str, Any]:
        """
        上传媒体组
        
        Args:
            messages: 媒体组消息列表
            channel_id: 目标频道ID
            
        Returns:
            Dict[str, Any]: 上传结果
        """
        if not messages:
            return {"success": False, "error": "没有要上传的消息"}
        
        # 准备媒体组数据
        media_group = []
        caption = None
        caption_entities = None
        
        # 查找第一个有caption的消息
        for msg in messages:
            if msg.get("caption"):
                caption = msg["caption"]
                caption_entities = msg.get("caption_entities")
                break
        
        # 组装媒体组
        for i, msg in enumerate(messages):
            file_path = msg.get("file_path")
            if not file_path or not os.path.exists(file_path):
                logger.warning(f"消息 {msg.get('message_id')} 的文件 {file_path} 不存在")
                continue
            
            # 确定媒体类型
            msg_type = msg.get("message_type")
            
            # 第一个消息使用caption，其他消息不使用
            use_caption = i == 0 and caption
            
            if msg_type == "photo":
                media = InputMediaPhoto(
                    file_path,
                    caption=caption if use_caption else None,
                    caption_entities=caption_entities if use_caption else None
                )
            elif msg_type == "video":
                media = InputMediaVideo(
                    file_path,
                    caption=caption if use_caption else None,
                    caption_entities=caption_entities if use_caption else None,
                    width=msg.get("width"),
                    height=msg.get("height"),
                    duration=msg.get("duration")
                )
            elif msg_type == "document":
                media = InputMediaDocument(
                    file_path,
                    caption=caption if use_caption else None,
                    caption_entities=caption_entities if use_caption else None,
                    thumb=None,
                    file_name=msg.get("file_name")
                )
            elif msg_type == "audio":
                media = InputMediaAudio(
                    file_path,
                    caption=caption if use_caption else None,
                    caption_entities=caption_entities if use_caption else None,
                    duration=msg.get("duration"),
                    performer=msg.get("performer"),
                    title=msg.get("title")
                )
            else:
                logger.warning(f"不支持的媒体类型: {msg_type}")
                continue
            
            media_group.append(media)
        
        if not media_group:
            return {"success": False, "error": "没有有效的媒体文件可上传"}
        
        # 尝试上传媒体组
        for attempt in range(self.retry_count + 1):
            try:
                logger.info(f"上传媒体组到频道 {channel_id} (尝试 {attempt+1}/{self.retry_count+1})")
                
                sent_messages = await self.client.send_media_group(
                    chat_id=channel_id,
                    media=media_group
                )
                
                if sent_messages:
                    # 提取消息ID
                    message_ids = [msg.id for msg in sent_messages]
                    
                    logger.info(f"媒体组上传成功，消息ID: {message_ids}")
                    
                    return {
                        "success": True,
                        "message_ids": message_ids,
                        "channel_id": channel_id
                    }
                else:
                    logger.warning(f"媒体组上传失败，没有收到反馈")
                    
                    if attempt < self.retry_count:
                        retry_wait = self.retry_delay * (attempt + 1)
                        logger.info(f"将在 {retry_wait} 秒后重试...")
                        await asyncio.sleep(retry_wait)
            
            except FloodWait as e:
                wait_time = e.x
                logger.warning(f"触发频率限制，等待 {wait_time} 秒")
                await asyncio.sleep(wait_time)
                
                # 如果等待时间较长，不计入重试次数
                if wait_time < 30:
                    continue
            
            except SlowmodeWait as e:
                wait_time = e.x
                logger.warning(f"触发慢速模式，等待 {wait_time} 秒")
                await asyncio.sleep(wait_time)
                continue
            
            except Exception as e:
                error_msg = str(e)
                logger.error(f"上传媒体组时出错: {error_msg}")
                
                if attempt < self.retry_count:
                    retry_wait = self.retry_delay * (attempt + 1)
                    logger.info(f"将在 {retry_wait} 秒后重试...")
                    await asyncio.sleep(retry_wait)
                else:
                    return {"success": False, "error": error_msg}
        
        return {"success": False, "error": "上传媒体组失败，达到最大重试次数"}
    
    async def _upload_single_message(self, message: Dict[str, Any], channel_id: Union[str, int]) -> Dict[str, Any]:
        """
        上传单条消息
        
        Args:
            message: 消息数据
            channel_id: 目标频道ID
            
        Returns:
            Dict[str, Any]: 上传结果
        """
        message_id = message.get("message_id")
        message_type = message.get("message_type")
        file_path = message.get("file_path")
        caption = message.get("caption")
        caption_entities = message.get("caption_entities")
        
        # 处理纯文本消息
        if message_type == "text":
            text = message.get("text", "")
            entities = message.get("text_entities")
            
            for attempt in range(self.retry_count + 1):
                try:
                    logger.info(f"发送文本消息到频道 {channel_id} (尝试 {attempt+1}/{self.retry_count+1})")
                    
                    sent_message = await self.client.send_message(
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
                    wait_time = e.x
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
        
        # 处理媒体消息
        if not file_path or not os.path.exists(file_path):
            return {"success": False, "error": f"文件 {file_path} 不存在"}
        
        # 根据消息类型发送不同的媒体
        send_func = None
        args = {
            "chat_id": channel_id,
            "caption": caption,
            "caption_entities": caption_entities
        }
        
        if message_type == "photo":
            send_func = self.client.send_photo
            args["photo"] = file_path
        elif message_type == "video":
            send_func = self.client.send_video
            args["video"] = file_path
            args["width"] = message.get("width")
            args["height"] = message.get("height")
            args["duration"] = message.get("duration")
        elif message_type == "document":
            send_func = self.client.send_document
            args["document"] = file_path
            args["file_name"] = message.get("file_name")
        elif message_type == "audio":
            send_func = self.client.send_audio
            args["audio"] = file_path
            args["duration"] = message.get("duration")
            args["performer"] = message.get("performer")
            args["title"] = message.get("title")
        else:
            return {"success": False, "error": f"不支持的媒体类型: {message_type}"}
        
        # 尝试发送媒体
        for attempt in range(self.retry_count + 1):
            try:
                logger.info(f"发送 {message_type} 到频道 {channel_id} (尝试 {attempt+1}/{self.retry_count+1})")
                
                sent_message = await send_func(**args)
                
                if sent_message:
                    logger.info(f"{message_type} 发送成功，消息ID: {sent_message.id}")
                    
                    return {
                        "success": True,
                        "message_id": sent_message.id,
                        "channel_id": channel_id
                    }
            
            except FloodWait as e:
                wait_time = e.x
                logger.warning(f"触发频率限制，等待 {wait_time} 秒")
                await asyncio.sleep(wait_time)
                continue
            
            except SlowmodeWait as e:
                wait_time = e.x
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
    
    async def _forward_to_other_channels(self, source_channel: Union[str, int], 
                                       message_id: int, 
                                       original_id: Union[str, int]) -> None:
        """
        将消息从第一个频道转发到其他频道
        
        Args:
            source_channel: 源频道ID
            message_id: 消息ID
            original_id: 原始消息ID或媒体组ID
        """
        other_channels = self.target_channels[1:]
        
        if not other_channels:
            return
        
        logger.info(f"将消息 {message_id} 从频道 {source_channel} 转发到 {len(other_channels)} 个其他频道")
        
        for channel in other_channels:
            # 检查是否已转发到该频道
            if self._is_message_uploaded(original_id, channel):
                logger.info(f"消息 {original_id} 已转发到频道 {channel}，跳过")
                continue
            
            for attempt in range(self.retry_count + 1):
                try:
                    logger.info(f"转发消息到频道 {channel} (尝试 {attempt+1}/{self.retry_count+1})")
                    
                    # 使用copy方法转发消息
                    sent_message = await self.client.copy_message(
                        chat_id=channel,
                        from_chat_id=source_channel,
                        message_id=message_id
                    )
                    
                    if sent_message:
                        logger.info(f"消息转发成功，目标频道: {channel}, 消息ID: {sent_message.id}")
                        
                        # 记录转发结果
                        self._record_upload(original_id, channel, [sent_message.id])
                        
                        # 跳出重试循环
                        break
                
                except FloodWait as e:
                    wait_time = e.x
                    logger.warning(f"触发频率限制，等待 {wait_time} 秒")
                    await asyncio.sleep(wait_time)
                    # 如果等待时间较短，不计入重试次数
                    if wait_time < 30:
                        continue
                
                except SlowmodeWait as e:
                    wait_time = e.x
                    logger.warning(f"触发慢速模式，等待 {wait_time} 秒")
                    await asyncio.sleep(wait_time)
                    continue
                
                except Exception as e:
                    logger.error(f"转发消息到频道 {channel} 时出错: {str(e)}")
                    
                    if attempt < self.retry_count:
                        retry_wait = self.retry_delay * (attempt + 1)
                        logger.info(f"将在 {retry_wait} 秒后重试...")
                        await asyncio.sleep(retry_wait)
                    else:
                        logger.error(f"转发消息到频道 {channel} 失败，达到最大重试次数")
            
            # 转发后等待一小段时间，避免触发限制
            await asyncio.sleep(self.wait_time)
    
    def _is_message_uploaded(self, message_id: Union[str, int], channel_id: Union[str, int]) -> bool:
        """
        检查消息是否已上传到指定频道
        
        Args:
            message_id: 消息ID
            channel_id: 频道ID
            
        Returns:
            bool: 是否已上传
        """
        message_key = str(message_id)
        channel_key = str(channel_id)
        
        if message_key in self.upload_history and channel_key in self.upload_history[message_key]:
            return True
        
        return False
    
    def _is_group_uploaded(self, group_id: str, channel_id: Union[str, int]) -> bool:
        """
        检查媒体组是否已上传到指定频道
        
        Args:
            group_id: 媒体组ID
            channel_id: 频道ID
            
        Returns:
            bool: 是否已上传
        """
        return self._is_message_uploaded(group_id, channel_id)
    
    def _record_upload(self, original_id: Union[str, int], channel_id: Union[str, int], 
                     message_ids: List[int]) -> None:
        """
        记录上传结果
        
        Args:
            original_id: 原始消息ID或媒体组ID
            channel_id: 频道ID
            message_ids: 上传后的消息ID列表
        """
        original_key = str(original_id)
        channel_key = str(channel_id)
        
        # 初始化原始ID的记录
        if original_key not in self.upload_history:
            self.upload_history[original_key] = {}
        
        # 记录上传结果
        self.upload_history[original_key][channel_key] = {
            "message_ids": message_ids,
            "timestamp": time.time()
        } 