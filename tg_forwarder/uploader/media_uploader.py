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

from pyrogram import Client
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
        
        # 临时客户端
        self.temp_client = None
    
    async def _create_temp_client(self):
        """创建临时客户端"""
        if self.temp_client is None:
            logger.info("创建临时客户端用于媒体上传")
            # 从原始客户端复制配置信息
            if hasattr(self.client, 'api_id') and hasattr(self.client, 'api_hash'):
                api_id = self.client.api_id
                api_hash = self.client.api_hash
                
                # 创建临时客户端
                self.temp_client = Client(
                    "media_uploader_temp",
                    api_id=api_id,
                    api_hash=api_hash,
                    in_memory=False,
                    app_version="TG Forwarder Temp Client v1.0",
                    device_model="PC",
                    system_version="Windows"
                )
                
                # 如果原始客户端有代理设置，也应用到临时客户端
                if hasattr(self.client, 'proxy_config') and self.client.proxy_config:
                    proxy_type = self.client.proxy_config.get('proxy_type', '').upper()
                    proxy = {
                        'scheme': proxy_type,
                        'hostname': self.client.proxy_config.get('addr'),
                        'port': self.client.proxy_config.get('port')
                    }
                    
                    if 'username' in self.client.proxy_config and self.client.proxy_config['username']:
                        proxy['username'] = self.client.proxy_config['username']
                    
                    if 'password' in self.client.proxy_config and self.client.proxy_config['password']:
                        proxy['password'] = self.client.proxy_config['password']
                    
                    self.temp_client.proxy = proxy
                
                # 连接临时客户端
                await self.temp_client.start()
                
                # 验证临时客户端状态
                try:
                    me = await self.temp_client.get_me()
                    if me:
                        logger.info(f"临时客户端成功连接到账号: {me.first_name} {me.last_name or ''}")
                    else:
                        logger.warning("临时客户端创建成功但无法获取用户信息")
                except Exception as e:
                    logger.error(f"验证临时客户端状态出错: {str(e)}")
            else:
                # 尝试从已有客户端获取会话字符串
                try:
                    if hasattr(self.client, 'client'):
                        # 有些实现中客户端可能是包装在一个属性中的
                        actual_client = self.client.client
                        api_id = actual_client.api_id
                        api_hash = actual_client.api_hash
                        
                        # 创建临时客户端
                        self.temp_client = Client(
                            "media_uploader_temp",
                            api_id=api_id,
                            api_hash=api_hash,
                            in_memory=True
                        )
                        
                        # 连接临时客户端
                        await self.temp_client.start()
                        
                        # 验证临时客户端状态
                        me = await self.temp_client.get_me()
                        if me:
                            logger.info(f"临时客户端成功连接到账号: {me.first_name} {me.last_name or ''}")
                        else:
                            logger.warning("临时客户端创建成功但无法获取用户信息")
                    else:
                        logger.error("无法创建临时客户端：无法获取原始客户端的API信息")
                except Exception as e:
                    logger.error(f"创建临时客户端时出错: {str(e)}")
                    import traceback
                    logger.debug(f"错误详情: {traceback.format_exc()}")

    async def _close_temp_client(self):
        """关闭临时客户端"""
        if self.temp_client:
            try:
                await self.temp_client.stop()
                logger.info("临时客户端已关闭")
                self.temp_client = None
            except Exception as e:
                logger.error(f"关闭临时客户端时出错: {str(e)}")
    
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
        
        # 创建临时客户端
        await self._create_temp_client()
        
        try:
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
                        self._record_upload(group_id, first_channel, result.get("message_ids", []), batch_data.get("source_channel_id"))
                        
                        # 将消息从第一个频道复制到其他频道
                        if len(self.target_channels) > 1 and result.get("message_ids"):
                            first_message_id = result["message_ids"][0]
                            await self._forward_to_other_channels(first_channel, first_message_id, group_id, True)
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
                if self._is_message_uploaded(message_id, self.target_channels[0], batch_data.get("source_channel_id")):
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
                        self._record_upload(message_id, first_channel, [result.get("message_id")], batch_data.get("source_channel_id"))
                        
                        # 将消息从第一个频道复制到其他频道
                        if len(self.target_channels) > 1 and result.get("message_id"):
                            await self._forward_to_other_channels(first_channel, result["message_id"], message_id, False)
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
            
        finally:
            # 无论结果如何，都关闭临时客户端
            await self._close_temp_client()
    
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
        
        # 确保临时客户端存在
        if not self.temp_client:
            await self._create_temp_client()
            if not self.temp_client:
                return {"success": False, "error": "无法创建临时客户端"}
                
        # 检查消息结构
        for i, msg in enumerate(messages[:3]):  # 只检查前三条消息
            logger.debug(f"媒体组消息 {i+1} 结构: {list(msg.keys())}")
        
        # 准备媒体组数据
        media_group = []
        caption = None
        caption_entities = None
        
        # 查找第一个有caption的消息
        for msg in messages:
            msg_caption = msg.get("caption")
            if msg_caption:
                caption = msg_caption
                caption_entities = msg.get("caption_entities")
                logger.debug(f"找到媒体组标题: {caption[:30] if caption else 'None'}...")
                break
            
            # 兼容可能的嵌套metadata结构
            metadata = msg.get("metadata", {})
            if isinstance(metadata, dict) and metadata.get("caption"):
                caption = metadata.get("caption")
                caption_entities = metadata.get("caption_entities")
                logger.debug(f"从metadata中找到媒体组标题: {caption[:30] if caption else 'None'}...")
                break
        
        # 组装媒体组
        for i, msg in enumerate(messages):
            # 获取文件路径，支持两种可能的格式
            file_path = msg.get("file_path")
            if not file_path and isinstance(msg.get("metadata"), dict):
                file_path = msg.get("metadata", {}).get("file_path")
            
            if not file_path or not os.path.exists(file_path):
                logger.warning(f"消息 {msg.get('message_id')} 的文件 {file_path} 不存在")
                continue
            
            # 确定媒体类型，支持两种可能的结构
            msg_type = msg.get("type") or msg.get("message_type")
            if not msg_type and isinstance(msg.get("metadata"), dict):
                msg_type = msg.get("metadata", {}).get("message_type")
            
            if not msg_type:
                logger.warning(f"消息 {msg.get('message_id')} 没有指定媒体类型")
                # 尝试根据文件扩展名猜测类型
                ext = os.path.splitext(file_path)[1].lower()
                if ext in ['.jpg', '.jpeg', '.png', '.webp']:
                    msg_type = "photo"
                    logger.info(f"根据扩展名将消息 {msg.get('message_id')} 类型设为 photo")
                elif ext in ['.mp4', '.avi', '.mov', '.mkv']:
                    msg_type = "video"
                    logger.info(f"根据扩展名将消息 {msg.get('message_id')} 类型设为 video")
                elif ext in ['.mp3', '.ogg', '.m4a', '.wav']:
                    msg_type = "audio"
                    logger.info(f"根据扩展名将消息 {msg.get('message_id')} 类型设为 audio")
                else:
                    msg_type = "document"
                    logger.info(f"根据扩展名将消息 {msg.get('message_id')} 类型设为 document")
            
            # 第一个消息使用caption，其他消息不使用
            use_caption = i == 0 and caption is not None
            
            # 获取附加属性的辅助函数
            def get_prop(prop_name, default=None):
                # 直接在消息中查找
                value = msg.get(prop_name)
                if value is not None:
                    return value
                
                # 在metadata中查找
                if isinstance(msg.get("metadata"), dict):
                    value = msg.get("metadata", {}).get(prop_name)
                    if value is not None:
                        return value
                
                return default
            
            # 根据媒体类型创建对应的InputMedia对象
            try:
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
                        width=get_prop("width"),
                        height=get_prop("height"),
                        duration=get_prop("duration")
                    )
                elif msg_type == "document":
                    media = InputMediaDocument(
                        file_path,
                        caption=caption if use_caption else None,
                        caption_entities=caption_entities if use_caption else None,
                        thumb=None,
                        file_name=get_prop("file_name")
                    )
                elif msg_type == "audio":
                    media = InputMediaAudio(
                        file_path,
                        caption=caption if use_caption else None,
                        caption_entities=caption_entities if use_caption else None,
                        duration=get_prop("duration"),
                        performer=get_prop("performer"),
                        title=get_prop("title")
                    )
                else:
                    logger.warning(f"不支持的媒体类型: {msg_type}，尝试作为文档发送")
                    media = InputMediaDocument(
                        file_path,
                        caption=caption if use_caption else None,
                        caption_entities=caption_entities if use_caption else None
                    )
                
                media_group.append(media)
                logger.debug(f"已添加媒体项: 类型={msg_type}, 文件={os.path.basename(file_path)}")
                
            except Exception as e:
                logger.error(f"创建媒体项时出错: {str(e)}")
                import traceback
                logger.debug(f"错误详情: {traceback.format_exc()}")
        
        if not media_group:
            return {"success": False, "error": "没有有效的媒体文件可上传"}
        
        # 尝试上传媒体组
        for attempt in range(self.retry_count + 1):
            try:
                logger.info(f"正在上传媒体组 (尝试 {attempt+1}/{self.retry_count+1})...")
                start_time = time.time()
                
                try:
                    # 使用临时客户端而不是原始客户端
                    result = await self.temp_client.send_media_group(
                        chat_id=channel_id,
                        media=media_group
                    )
                    
                    duration = time.time() - start_time
                    logger.info(f"成功上传媒体组 ({len(result)} 条消息, 耗时 {duration:.1f}秒)")
                    
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
        # 确保临时客户端存在
        if not self.temp_client:
            await self._create_temp_client()
            if not self.temp_client:
                return {"success": False, "error": "无法创建临时客户端"}
        
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
                    
                    # 使用临时客户端
                    sent_message = await self.temp_client.send_message(
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
        
        # 处理媒体消息
        if not file_path or not os.path.exists(file_path):
            return {"success": False, "error": f"文件 {file_path} 不存在"}
        
        # 根据消息类型发送不同的媒体
        send_func = None
        args = {
            "chat_id": channel_id,
            "caption": caption,
        }
        
        if message_type == "photo":
            send_func = self.temp_client.send_photo  # 使用临时客户端
            args["photo"] = file_path
        elif message_type == "video":
            send_func = self.temp_client.send_video  # 使用临时客户端
            args["video"] = file_path
            
            # 只添加有效的数值类型参数
            if isinstance(message.get("width"), (int, float)) and message.get("width") > 0:
                args["width"] = message.get("width")
            
            if isinstance(message.get("height"), (int, float)) and message.get("height") > 0:
                args["height"] = message.get("height")
            
            if isinstance(message.get("duration"), (int, float)) and message.get("duration") > 0:
                args["duration"] = message.get("duration")
            
        elif message_type == "document":
            send_func = self.temp_client.send_document  # 使用临时客户端
            args["document"] = file_path
            
            if message.get("file_name"):
                args["file_name"] = message.get("file_name")
            
        elif message_type == "audio":
            send_func = self.temp_client.send_audio  # 使用临时客户端
            args["audio"] = file_path
            
            if isinstance(message.get("duration"), (int, float)) and message.get("duration") > 0:
                args["duration"] = message.get("duration")
            
            if message.get("performer"):
                args["performer"] = message.get("performer")
            
            if message.get("title"):
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
                wait_time = e.value  # 注意：在新版pyrogram中可能是e.value而不是e.x
                logger.warning(f"触发频率限制，等待 {wait_time} 秒")
                await asyncio.sleep(wait_time)
                continue
            
            except SlowmodeWait as e:
                wait_time = e.value  # 注意：在新版pyrogram中可能是e.value而不是e.x
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
                                       original_id: Union[str, int],
                                       is_media_group: bool = False) -> None:
        """
        将消息从第一个频道转发到其他频道
        
        Args:
            source_channel: 源频道ID
            message_id: 消息ID
            original_id: 原始消息ID或媒体组ID
            is_media_group: 是否为媒体组，默认为False
        """
        # 确保临时客户端存在
        if not self.temp_client:
            await self._create_temp_client()
            if not self.temp_client:
                logger.error("无法创建临时客户端，转发失败")
                return
        
        other_channels = self.target_channels[1:]
        
        if not other_channels:
            return
        
        if is_media_group:
            logger.info(f"将媒体组 (消息ID: {message_id}) 从频道 {source_channel} 转发到 {len(other_channels)} 个其他频道")
        else:
            logger.info(f"将消息 {message_id} 从频道 {source_channel} 转发到 {len(other_channels)} 个其他频道")
        
        for channel_id in other_channels:
            # 检查是否为链接格式，获取正确的频道ID
            channel = channel_id
            try:
                # 检查是否是t.me链接格式
                if isinstance(channel_id, str) and ('t.me/' in channel_id or 'https://' in channel_id):
                    logger.debug(f"检测到频道链接格式: {channel_id}，正在解析")
                    
                    # 尝试先获取频道实体
                    chat = None
                    try:
                        # 使用get_chat方法获取频道信息
                        chat = await self.temp_client.get_chat(channel_id)
                        if chat:
                            channel = chat.id
                            logger.info(f"已成功解析频道链接，获取到ID: {channel}")
                    except Exception as e:
                        logger.warning(f"无法直接获取频道 {channel_id} 的信息: {str(e)}")
                        
                        # 如果是私有频道邀请链接，尝试从链接中提取邀请码
                        if '+' in channel_id:
                            # 尝试通过对话列表查找匹配的频道
                            try:
                                dialogs = await self.temp_client.get_dialogs()
                                invite_code = None
                                
                                # 提取邀请码
                                if 't.me/+' in channel_id:
                                    invite_code = channel_id.split('t.me/+')[1].split('/')[0]
                                elif channel_id.startswith('+'):
                                    invite_code = channel_id.lstrip('+')
                                
                                if invite_code:
                                    logger.debug(f"提取到邀请码: {invite_code}")
                                    
                                    # 在对话列表中查找
                                    for dialog in dialogs:
                                        if hasattr(dialog.chat, 'invite_link') and dialog.chat.invite_link:
                                            if invite_code in dialog.chat.invite_link:
                                                channel = dialog.chat.id
                                                logger.info(f"在对话列表中找到匹配的频道: {dialog.chat.title} (ID: {channel})")
                                                break
                                
                                if channel == channel_id:  # 如果没有找到匹配的
                                    # 尝试加入频道
                                    logger.warning(f"无法找到匹配的频道，尝试从链接加入: {channel_id}")
                                    try:
                                        join_result = await self.temp_client.join_chat(channel_id)
                                        if join_result:
                                            channel = join_result.id
                                            logger.info(f"已加入频道: {join_result.title} (ID: {channel})")
                                    except Exception as join_err:
                                        logger.error(f"加入频道失败: {str(join_err)}")
                            except Exception as dialog_err:
                                logger.error(f"获取对话列表时出错: {str(dialog_err)}")
            except Exception as parse_err:
                logger.error(f"解析频道链接时出错: {str(parse_err)}")
                
            # 检查是否已转发到该频道
            if self._is_message_uploaded(original_id, channel):
                logger.info(f"消息 {original_id} 已转发到频道 {channel}，跳过")
                continue
            
            for attempt in range(self.retry_count + 1):
                try:
                    if is_media_group:
                        logger.info(f"转发媒体组到频道 {channel} (尝试 {attempt+1}/{self.retry_count+1})")
                        
                        # 使用copy_media_group方法转发媒体组
                        sent_messages = await self.temp_client.copy_media_group(
                            chat_id=channel,
                            from_chat_id=source_channel,
                            message_id=message_id
                        )
                        
                        if sent_messages:
                            message_ids = [msg.id for msg in sent_messages]
                            logger.info(f"媒体组转发成功，目标频道: {channel}, 共 {len(message_ids)} 条消息")
                            
                            # 记录转发结果
                            self._record_upload(original_id, channel, message_ids, source_channel)
                            
                            # 跳出重试循环
                            break
                    else:
                        logger.info(f"转发消息到频道 {channel} (尝试 {attempt+1}/{self.retry_count+1})")
                        
                        # 使用copy_message方法转发单条消息
                        sent_message = await self.temp_client.copy_message(
                            chat_id=channel,
                            from_chat_id=source_channel,
                            message_id=message_id
                        )
                        
                        if sent_message:
                            logger.info(f"消息转发成功，目标频道: {channel}, 消息ID: {sent_message.id}")
                            
                            # 记录转发结果
                            self._record_upload(original_id, channel, [sent_message.id], source_channel)
                            
                            # 跳出重试循环
                            break
                
                except FloodWait as e:
                    wait_time = e.value  # 在新版pyrogram中是e.value
                    logger.warning(f"触发频率限制，等待 {wait_time} 秒")
                    await asyncio.sleep(wait_time)
                    # 如果等待时间较短，不计入重试次数
                    if wait_time < 30:
                        continue
                
                except SlowmodeWait as e:
                    wait_time = e.value  # 在新版pyrogram中是e.value
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
    
    def _is_message_uploaded(self, message_id: Union[str, int], channel_id: Union[str, int], 
                           source_channel_id: Union[str, int] = None) -> bool:
        """
        检查消息是否已上传到指定频道
        
        Args:
            message_id: 消息ID
            channel_id: 频道ID
            source_channel_id: 源频道ID（可选）
            
        Returns:
            bool: 是否已上传
        """
        if source_channel_id:
            message_key = f"{source_channel_id}_{message_id}"
        else:
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
                     message_ids: List[int], source_channel_id: Union[str, int] = None) -> None:
        """
        记录上传结果
        
        Args:
            original_id: 原始消息ID或媒体组ID
            channel_id: 目标频道ID
            message_ids: 上传后的消息ID列表
            source_channel_id: 源频道ID（可选）
        """
        # 如果提供了源频道ID，将其添加到键中
        if source_channel_id:
            original_key = f"{source_channel_id}_{original_id}"
        else:
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