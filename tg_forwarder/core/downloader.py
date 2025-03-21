"""
下载器实现类
负责下载消息和媒体文件
"""

import os
import time
import asyncio
from typing import Dict, Any, List, Union, Optional, Tuple
from datetime import datetime
import hashlib
import json

from pyrogram.types import Message
from pyrogram.errors import FloodWait

from tg_forwarder.interfaces.downloader_interface import DownloaderInterface
from tg_forwarder.interfaces.client_interface import TelegramClientInterface
from tg_forwarder.interfaces.config_interface import ConfigInterface
from tg_forwarder.interfaces.logger_interface import LoggerInterface
from tg_forwarder.interfaces.storage_interface import StorageInterface
from tg_forwarder.interfaces.status_tracker_interface import StatusTrackerInterface


class Downloader(DownloaderInterface):
    """
    下载器类，实现DownloaderInterface接口
    负责下载Telegram消息中的媒体内容
    """
    
    def __init__(self, client: TelegramClientInterface, config: ConfigInterface, 
                 logger: LoggerInterface, storage: StorageInterface,
                 status_tracker: StatusTrackerInterface):
        """
        初始化下载器
        
        Args:
            client: Telegram客户端接口实例
            config: 配置接口实例
            logger: 日志接口实例
            storage: 存储接口实例
            status_tracker: 状态追踪器接口实例
        """
        self._client = client
        self._config = config
        self._logger = logger.get_logger("Downloader")
        self._storage = storage
        self._status_tracker = status_tracker
        
        self._download_path = None
        self._initialized = False
        self._media_types = ["photo", "video", "document", "audio", "animation", "voice", "sticker"]
        
        # 用于存储已下载消息的集合
        self._downloaded_cache = set()
        
    async def initialize(self) -> bool:
        """
        初始化下载器
        
        Returns:
            bool: 初始化是否成功
        """
        try:
            self._download_path = self._config.get_download_path()
            if not self._download_path:
                self._download_path = os.path.join(os.getcwd(), "downloads")
            
            # 确保下载目录存在
            os.makedirs(self._download_path, exist_ok=True)
            
            # 从存储中加载已下载消息记录
            await self._load_downloaded_cache()
            
            self._initialized = True
            self._logger.info(f"下载器初始化完成，下载路径: {self._download_path}")
            return True
        except Exception as e:
            self._logger.error(f"初始化下载器失败: {str(e)}", exc_info=True)
            self._initialized = False
            return False
    
    async def shutdown(self) -> None:
        """关闭下载器，释放资源"""
        if not self._initialized:
            return
        
        try:
            # 保存下载缓存
            await self._save_downloaded_cache()
            
            self._initialized = False
            self._logger.info("下载器已关闭")
        except Exception as e:
            self._logger.error(f"关闭下载器时发生错误: {str(e)}", exc_info=True)
    
    async def download_media_batch(self, batch: Dict[str, Any]) -> Dict[str, Any]:
        """
        下载批量媒体文件
        
        Args:
            batch: 包含消息信息的批次数据，格式：
                {
                    "chat_id": int,
                    "messages": [message_id1, message_id2, ...],
                    "media_groups": {group_id: [message_id1, message_id2, ...], ...}
                }
            
        Returns:
            Dict[str, Any]: 下载结果，包含成功和失败的媒体信息
        """
        if not self._initialized:
            await self.initialize()
        
        chat_id = batch.get("chat_id")
        message_ids = batch.get("messages", [])
        media_groups = batch.get("media_groups", {})
        
        result = {
            "success": [],
            "failed": [],
            "skipped": []
        }
        
        # 下载单个消息
        for message_id in message_ids:
            if self._is_message_downloaded(chat_id, message_id):
                result["skipped"].append({"chat_id": chat_id, "message_id": message_id})
                continue
            
            download_result = await self._download_single_message(chat_id, message_id)
            if download_result["success"]:
                result["success"].append(download_result["data"])
            else:
                result["failed"].append(download_result["error"])
        
        # 下载媒体组
        for group_id, group_message_ids in media_groups.items():
            group_result = await self._download_media_group(chat_id, group_id, group_message_ids)
            result["success"].extend(group_result["success"])
            result["failed"].extend(group_result["failed"])
            result["skipped"].extend(group_result["skipped"])
        
        return result
    
    async def _download_single_message(self, chat_id: Union[int, str], message_id: int) -> Dict[str, Any]:
        """
        下载单个消息的媒体
        
        Args:
            chat_id: 聊天ID
            message_id: 消息ID
            
        Returns:
            Dict[str, Any]: 下载结果
        """
        try:
            # 获取消息
            message = await self._client.get_message(chat_id, message_id)
            if not message:
                return {
                    "success": False,
                    "error": {"chat_id": chat_id, "message_id": message_id, "reason": "消息不存在"}
                }
            
            # 检查是否有可下载的媒体
            if not self._has_downloadable_media(message):
                return {
                    "success": False,
                    "error": {"chat_id": chat_id, "message_id": message_id, "reason": "消息不包含可下载媒体"}
                }
            
            # 生成保存路径
            file_path = self._generate_file_name(message, chat_id, message_id)
            
            # 记录下载开始
            task_id = await self._status_tracker.record_download_start(chat_id, message_id, None)
            
            # 下载媒体
            download_path = await self._client.download_media(message, file_path)
            if not download_path:
                await self._status_tracker.record_download_failed(task_id, "下载失败")
                return {
                    "success": False,
                    "error": {"chat_id": chat_id, "message_id": message_id, "reason": "下载失败"}
                }
            
            # 保存元数据
            self._store_message_metadata(message)
            
            # 添加到已下载缓存
            self._add_to_downloaded_cache(chat_id, message_id)
            
            # 记录下载完成
            await self._status_tracker.record_download_complete(task_id, download_path)
            
            return {
                "success": True,
                "data": {
                    "task_id": task_id,
                    "chat_id": chat_id,
                    "message_id": message_id,
                    "file_path": download_path,
                    "media_type": self._get_media_type(message),
                    "caption": message.caption,
                    "date": message.date
                }
            }
            
        except Exception as e:
            self._logger.error(f"下载消息 {chat_id}:{message_id} 失败: {str(e)}", exc_info=True)
            return {
                "success": False,
                "error": {"chat_id": chat_id, "message_id": message_id, "reason": str(e)}
            }
    
    async def _download_media_group(self, chat_id: Union[int, str], group_id: str, message_ids: List[int]) -> Dict[str, Any]:
        """
        下载媒体组
        
        Args:
            chat_id: 聊天ID
            group_id: 媒体组ID
            message_ids: 媒体组中的消息ID列表
            
        Returns:
            Dict[str, Any]: 下载结果
        """
        result = {
            "success": [],
            "failed": [],
            "skipped": []
        }
        
        try:
            # 获取媒体组中的第一个消息，用于获取完整的媒体组
            if not message_ids:
                return result
            
            # 如果所有消息都已下载，则跳过
            all_downloaded = all(self._is_message_downloaded(chat_id, msg_id) for msg_id in message_ids)
            if all_downloaded:
                for msg_id in message_ids:
                    result["skipped"].append({"chat_id": chat_id, "message_id": msg_id, "group_id": group_id})
                return result
            
            # 获取完整的媒体组
            media_group = await self._client.get_media_group(chat_id, message_ids[0])
            if not media_group:
                for msg_id in message_ids:
                    result["failed"].append({
                        "chat_id": chat_id, 
                        "message_id": msg_id, 
                        "group_id": group_id,
                        "reason": "无法获取媒体组"
                    })
                return result
            
            # 为媒体组中的每个消息创建一个任务ID
            task_ids = {}
            for message in media_group:
                if not self._is_message_downloaded(chat_id, message.id):
                    task_id = await self._status_tracker.record_download_start(chat_id, message.id, group_id)
                    task_ids[message.id] = task_id
            
            # 下载媒体组中的每个消息
            for message in media_group:
                # 如果已经下载过，则跳过
                if self._is_message_downloaded(chat_id, message.id):
                    result["skipped"].append({
                        "chat_id": chat_id, 
                        "message_id": message.id, 
                        "group_id": group_id
                    })
                    continue
                
                # 检查是否有可下载的媒体
                if not self._has_downloadable_media(message):
                    continue
                
                # 生成保存路径
                file_path = self._generate_file_name(message, chat_id, message.id, group_id)
                
                # 下载媒体
                download_path = await self._client.download_media(message, file_path)
                if not download_path:
                    await self._status_tracker.record_download_failed(task_ids[message.id], "下载失败")
                    result["failed"].append({
                        "chat_id": chat_id, 
                        "message_id": message.id, 
                        "group_id": group_id,
                        "reason": "下载失败"
                    })
                    continue
                
                # 保存元数据
                self._store_message_metadata(message, group_id)
                
                # 添加到已下载缓存
                self._add_to_downloaded_cache(chat_id, message.id)
                
                # 记录下载完成
                await self._status_tracker.record_download_complete(task_ids[message.id], download_path)
                
                result["success"].append({
                    "task_id": task_ids[message.id],
                    "chat_id": chat_id,
                    "message_id": message.id,
                    "group_id": group_id,
                    "file_path": download_path,
                    "media_type": self._get_media_type(message),
                    "caption": message.caption,
                    "date": message.date
                })
            
            return result
            
        except Exception as e:
            self._logger.error(f"下载媒体组 {chat_id}:{group_id} 失败: {str(e)}", exc_info=True)
            for msg_id in message_ids:
                if msg_id in task_ids:
                    await self._status_tracker.record_download_failed(task_ids[msg_id], str(e))
                result["failed"].append({
                    "chat_id": chat_id, 
                    "message_id": msg_id, 
                    "group_id": group_id,
                    "reason": str(e)
                })
            return result
    
    def _has_downloadable_media(self, message: Message) -> bool:
        """
        检查消息是否包含可下载的媒体
        
        Args:
            message: 消息对象
            
        Returns:
            bool: 如果包含可下载媒体则返回True，否则返回False
        """
        return bool(message.photo or message.video or message.document or 
                   message.audio or message.animation or message.voice or 
                   message.sticker)
    
    def _get_media_type(self, message: Message) -> str:
        """
        获取消息的媒体类型
        
        Args:
            message: 消息对象
            
        Returns:
            str: 媒体类型
        """
        if message.photo:
            return "photo"
        elif message.video:
            return "video"
        elif message.document:
            return "document"
        elif message.audio:
            return "audio"
        elif message.animation:
            return "animation"
        elif message.voice:
            return "voice"
        elif message.sticker:
            return "sticker"
        else:
            return "unknown"
    
    def _generate_file_name(self, message: Message, chat_id: int, message_id: int, group_id: str = None) -> str:
        """
        生成媒体文件的保存路径
        
        Args:
            message: 消息对象
            chat_id: 聊天ID
            message_id: 消息ID
            group_id: 媒体组ID（可选）
            
        Returns:
            str: 生成的文件名
        """
        # 创建目录结构：downloads/chat_id/media_type/date
        media_type = self._get_media_type(message)
        date_folder = datetime.fromtimestamp(message.date).strftime("%Y-%m-%d")
        
        # 为每个聊天创建单独的目录
        chat_folder = f"chat_{chat_id}"
        
        # 构建目录路径
        directory = os.path.join(self._download_path, chat_folder, media_type, date_folder)
        os.makedirs(directory, exist_ok=True)
        
        # 为文件名生成一个唯一标识，包括消息ID和媒体组ID（如果有）
        file_id_part = f"{message_id}"
        if group_id:
            file_id_part = f"{file_id_part}_group_{group_id[-8:]}"  # 使用媒体组ID的一部分来避免文件名过长
        
        # 获取原始文件名或生成一个文件名
        original_filename = None
        
        if media_type == "photo":
            # 照片没有原始文件名，使用默认的jpg扩展名
            original_filename = f"{file_id_part}.jpg"
        elif media_type == "video":
            # 尝试从视频对象中获取文件名
            file_name = getattr(message.video, "file_name", None)
            if file_name:
                name, ext = os.path.splitext(file_name)
                original_filename = f"{file_id_part}{ext}"
            else:
                original_filename = f"{file_id_part}.mp4"
        elif media_type == "document":
            # 从文档对象中获取文件名
            file_name = getattr(message.document, "file_name", None)
            if file_name:
                name, ext = os.path.splitext(file_name)
                original_filename = f"{file_id_part}{ext}"
            else:
                original_filename = f"{file_id_part}.bin"
        elif media_type == "audio":
            # 从音频对象中获取文件名
            file_name = getattr(message.audio, "file_name", None)
            if file_name:
                name, ext = os.path.splitext(file_name)
                original_filename = f"{file_id_part}{ext}"
            else:
                original_filename = f"{file_id_part}.mp3"
        elif media_type == "animation":
            # 从动画对象中获取文件名
            file_name = getattr(message.animation, "file_name", None)
            if file_name:
                name, ext = os.path.splitext(file_name)
                original_filename = f"{file_id_part}{ext}"
            else:
                original_filename = f"{file_id_part}.gif"
        elif media_type == "voice":
            # 语音消息一般没有文件名，使用默认的ogg扩展名
            original_filename = f"{file_id_part}.ogg"
        elif media_type == "sticker":
            # 贴纸消息一般没有文件名，保存为webp或tgs
            if getattr(message.sticker, "is_animated", False):
                original_filename = f"{file_id_part}.tgs"
            else:
                original_filename = f"{file_id_part}.webp"
        else:
            # 未知类型，使用默认的bin扩展名
            original_filename = f"{file_id_part}.bin"
        
        # 完整的文件路径
        file_path = os.path.join(directory, original_filename)
        
        return file_path
    
    def _is_message_downloaded(self, chat_id, message_id) -> bool:
        """
        检查消息是否已下载
        
        Args:
            chat_id: 聊天ID
            message_id: 消息ID
            
        Returns:
            bool: 如果已下载则返回True，否则返回False
        """
        # 首先检查内存缓存
        cache_key = f"{chat_id}:{message_id}"
        if cache_key in self._downloaded_cache:
            return True
        
        # 然后检查存储
        try:
            key = f"downloaded:{chat_id}:{message_id}"
            data = self._storage.get_data("downloads", key)
            if data:
                # 添加到内存缓存
                self._add_to_downloaded_cache(chat_id, message_id)
                return True
            return False
        except Exception as e:
            self._logger.warning(f"检查消息下载状态失败: {str(e)}")
            return False
    
    def _add_to_downloaded_cache(self, chat_id, message_id) -> None:
        """
        将消息添加到已下载缓存
        
        Args:
            chat_id: 聊天ID
            message_id: 消息ID
        """
        cache_key = f"{chat_id}:{message_id}"
        self._downloaded_cache.add(cache_key)
    
    async def _load_downloaded_cache(self) -> None:
        """从存储加载已下载消息缓存"""
        try:
            # 从存储中查询所有已下载的消息
            records = self._storage.query_data("downloads", {"key": {"$regex": "^downloaded:"}})
            
            # 清空缓存
            self._downloaded_cache.clear()
            
            # 添加到缓存
            for record in records:
                key = record.get("key", "")
                if key.startswith("downloaded:"):
                    parts = key.split(":", 2)
                    if len(parts) == 3:
                        _, chat_id, message_id = parts
                        cache_key = f"{chat_id}:{message_id}"
                        self._downloaded_cache.add(cache_key)
            
            self._logger.debug(f"已加载 {len(self._downloaded_cache)} 条已下载消息记录")
        except Exception as e:
            self._logger.error(f"加载已下载消息缓存失败: {str(e)}", exc_info=True)
    
    async def _save_downloaded_cache(self) -> None:
        """保存已下载消息缓存到存储"""
        try:
            # 将内存缓存保存到存储
            for cache_key in self._downloaded_cache:
                chat_id, message_id = cache_key.split(":", 1)
                key = f"downloaded:{chat_id}:{message_id}"
                
                # 检查是否已存在
                if not self._storage.get_data("downloads", key):
                    self._storage.store_data("downloads", key, {
                        "chat_id": chat_id,
                        "message_id": message_id,
                        "downloaded_at": datetime.now().isoformat()
                    })
            
            self._logger.debug(f"已保存 {len(self._downloaded_cache)} 条已下载消息记录")
        except Exception as e:
            self._logger.error(f"保存已下载消息缓存失败: {str(e)}", exc_info=True)
    
    def _store_message_metadata(self, message: Message, group_id: str = None) -> None:
        """
        存储消息元数据
        
        Args:
            message: 消息对象
            group_id: 媒体组ID（可选）
        """
        try:
            # 提取需要存储的消息元数据
            metadata = {
                "message_id": message.id,
                "chat_id": message.chat.id,
                "date": message.date,
                "media_type": self._get_media_type(message),
                "caption": message.caption,
                "downloaded_at": datetime.now().isoformat()
            }
            
            # 添加媒体组ID（如果有）
            if group_id:
                metadata["media_group_id"] = group_id
            elif message.media_group_id:
                metadata["media_group_id"] = message.media_group_id
            
            # 添加媒体信息
            if message.photo:
                metadata["photo_info"] = {
                    "file_id": message.photo.file_id,
                    "width": message.photo.width,
                    "height": message.photo.height,
                    "file_size": message.photo.file_size
                }
            elif message.video:
                metadata["video_info"] = {
                    "file_id": message.video.file_id,
                    "width": message.video.width,
                    "height": message.video.height,
                    "duration": message.video.duration,
                    "file_size": message.video.file_size,
                    "mime_type": message.video.mime_type
                }
            # 其他媒体类型类似处理...
            
            # 存储元数据
            key = f"metadata:{message.chat.id}:{message.id}"
            self._storage.store_data("downloads", key, metadata)
        except Exception as e:
            self._logger.error(f"存储消息元数据失败: {str(e)}", exc_info=True) 