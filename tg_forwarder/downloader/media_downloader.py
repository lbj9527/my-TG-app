"""
媒体下载模块，负责下载消息中的媒体文件
"""

import os
import asyncio
import logging
import time
from typing import Dict, Any, List, Union, Optional, Set, Tuple
from collections import defaultdict
import json

from pyrogram.types import Message, MessageEntity
from pyrogram.errors import FloodWait

from tg_forwarder.utils.logger import get_logger

# 获取日志记录器
logger = get_logger("media_downloader")

def entity_to_dict(entity: MessageEntity) -> Dict[str, Any]:
    """
    将MessageEntity对象转换为字典
    
    Args:
        entity: MessageEntity对象
        
    Returns:
        Dict[str, Any]: 实体字典
    """
    result = {
        "type": str(entity.type) if hasattr(entity.type, "value") else entity.type,
        "offset": entity.offset,
        "length": entity.length
    }
    
    # 添加可选属性
    if hasattr(entity, "url") and entity.url:
        result["url"] = entity.url
    
    if hasattr(entity, "user") and entity.user:
        result["user"] = {
            "id": entity.user.id,
            "is_bot": entity.user.is_bot,
            "first_name": entity.user.first_name,
            "username": getattr(entity.user, "username", None)
        }
    
    if hasattr(entity, "language") and entity.language:
        result["language"] = entity.language
        
    if hasattr(entity, "custom_emoji_id") and entity.custom_emoji_id:
        result["custom_emoji_id"] = entity.custom_emoji_id
    
    return result

class MediaDownloader:
    """媒体下载器，负责下载消息中的媒体文件"""
    
    def __init__(self, client, concurrent_downloads: int = 10, temp_folder: str = "temp", 
                 retry_count: int = 3, retry_delay: int = 5):
        """
        初始化媒体下载器
        
        Args:
            client: Telegram客户端
            concurrent_downloads: 并发下载数量
            temp_folder: 临时文件夹路径
            retry_count: 重试次数
            retry_delay: 重试延迟时间（秒）
        """
        self.client = client
        self.concurrent_downloads = concurrent_downloads
        self.temp_folder = temp_folder
        self.retry_count = retry_count
        self.retry_delay = retry_delay
        self.semaphore = asyncio.Semaphore(concurrent_downloads)
        self.processed_files: Set[str] = set()  # 已处理文件集合
        
        # 确保临时文件夹存在
        os.makedirs(self.temp_folder, exist_ok=True)
        
        # 创建存储文件路径
        self.metadata_path = os.path.join(self.temp_folder, "message_metadata.json")
        self.download_mapping_path = os.path.join(self.temp_folder, "download_mapping.json")
        
        # 消息元数据映射
        self.message_metadata = {}
        
        # 下载映射（消息ID → 文件路径）
        self.download_mapping = {}
        
        # 加载现有元数据
        self._load_metadata()
        
        # 初始化已下载消息集合
        self.downloaded_messages = set()
        
        # 加载已下载消息记录
        self._load_downloaded_messages()
    
    def _load_metadata(self) -> None:
        """加载现有元数据"""
        try:
            if os.path.exists(self.metadata_path):
                with open(self.metadata_path, "r", encoding="utf-8") as f:
                    self.message_metadata = json.load(f)
                logger.info(f"加载消息元数据: {len(self.message_metadata)} 条记录")
            
            if os.path.exists(self.download_mapping_path):
                with open(self.download_mapping_path, "r", encoding="utf-8") as f:
                    self.download_mapping = json.load(f)
                logger.info(f"加载下载映射: {len(self.download_mapping)} 条记录")
                # 标记已下载文件为已处理
                for file_path in self.download_mapping.values():
                    if isinstance(file_path, str) and os.path.exists(file_path):
                        self.processed_files.add(file_path)
        except Exception as e:
            logger.error(f"加载元数据时出错: {str(e)}")
    
    def _save_metadata(self) -> None:
        """保存元数据"""
        try:
            # 在保存前递归处理所有可能的枚举类型
            def prepare_for_json(obj):
                if isinstance(obj, dict):
                    return {k: prepare_for_json(v) for k, v in obj.items()}
                elif isinstance(obj, list):
                    return [prepare_for_json(item) for item in obj]
                elif hasattr(obj, "value") and not callable(obj.value):  # 处理枚举类型
                    return str(obj.value)
                elif hasattr(obj, "__dict__"):  # 处理其他复杂对象
                    try:
                        return str(obj)
                    except:
                        return f"<Object of type {type(obj).__name__}>"
                else:
                    return obj
            
            # 处理元数据和下载映射
            processed_metadata = prepare_for_json(self.message_metadata)
            processed_mapping = prepare_for_json(self.download_mapping)
            
            # 保存处理后的数据
            with open(self.metadata_path, "w", encoding="utf-8") as f:
                json.dump(processed_metadata, f, ensure_ascii=False, indent=2)
            
            with open(self.download_mapping_path, "w", encoding="utf-8") as f:
                json.dump(processed_mapping, f, ensure_ascii=False, indent=2)
            
            logger.debug("保存元数据成功")
        except Exception as e:
            logger.error(f"保存元数据时出错: {str(e)}")
            # 记录更详细的错误信息以帮助调试
            import traceback
            logger.debug(f"错误详情: {traceback.format_exc()}")
    
    async def download_media_batch(self, batch: Dict[str, Any]) -> Dict[str, Any]:
        """
        下载一个批次中的所有媒体文件

        Args:
            batch: 包含媒体信息的批次

        Returns:
            Dict[str, Any]: 下载结果统计
        """
        # 提取所有需要下载的消息
        all_messages = []
        
        # 从媒体组中提取消息 (media_groups是列表结构)
        media_groups = batch.get("media_groups", [])
        if media_groups:
            for group in media_groups:
                if isinstance(group, list):
                    all_messages.extend(group)
        
        # 添加单条消息
        all_messages.extend(batch.get("single_messages", []) or batch.get("messages", []))
        
        # 如果没有消息需要下载，直接返回
        if not all_messages:
            return {"success": 0, "failed": 0, "files": []}
        
        logger.info(f"开始并行下载 {len(all_messages)} 个文件...")
        
        # 准备下载任务
        download_tasks = []
        for message in all_messages:
            # 检查消息是否已下载过 (通过获取属性而不是get方法)
            message_id = message.id if hasattr(message, "id") else 0
            chat_id = message.chat.id if hasattr(message, "chat") else 0
            
            if self._is_message_downloaded(chat_id, message_id):
                logger.debug(f"消息已下载过: {chat_id}_{message_id}")
                continue
            
            # 添加下载任务
            download_tasks.append(self._process_message_media(message))
        
        # 使用信号量控制并发数量
        semaphore = asyncio.Semaphore(self.concurrent_downloads)
        
        # 定义包装函数，应用信号量控制
        async def download_with_semaphore(task):
            async with semaphore:
                return await task
        
        # 并行执行所有下载任务
        results = []
        if download_tasks:
            # 将所有任务包装在信号量中
            bounded_tasks = [download_with_semaphore(task) for task in download_tasks]
            
            # 使用as_completed同时获取完成的任务结果
            for future in asyncio.as_completed(bounded_tasks):
                try:
                    result = await future
                    if result:
                        results.append(result)
                except Exception as e:
                    logger.error(f"下载任务执行异常: {str(e)}")
        
        # 分类统计下载结果
        success_files = [item for item in results if item and "error" not in item]
        failed_files = [item for item in results if item and "error" in item]
        
        # 保存下载记录
        for item in success_files:
            self._mark_message_downloaded(item.get("chat_id"), item.get("message_id"))
        
        logger.info(f"批次下载完成: 成功 {len(success_files)}, 失败 {len(failed_files)}")
        
        return {
            "success": len(success_files),
            "failed": len(failed_files),
            "files": success_files
        }
    
    async def _download_media_file(self, message: Message, group_id: str = None) -> Dict[str, Any]:
        """
        下载单个媒体文件
        
        Args:
            message: 消息对象
            group_id: 媒体组ID
            
        Returns:
            Dict[str, Any]: 下载结果
        """
        # 使用信号量限制并发下载数量
        async with self.semaphore:
            start_time = time.time()
            
            # 消息ID作为索引
            message_id = message.id
            chat_id = message.chat.id
            
            # 生成唯一文件名
            file_name = self._generate_file_name(message, chat_id, message_id, group_id)
            file_path = os.path.join(self.temp_folder, file_name)
            
            # 如果文件已存在且已处理，跳过
            if file_path in self.processed_files:
                logger.debug(f"文件已存在，跳过下载: {file_path}")
                return {
                    "message_id": message_id,
                    "chat_id": chat_id,
                    "media_group_id": group_id or (message.media_group_id if hasattr(message, "media_group_id") else None),
                    "file_path": file_path,
                    "file_name": file_name,
                    "success": True,
                    "duration": 0,
                    "file_size": os.path.getsize(file_path) if os.path.exists(file_path) else 0,
                    "already_existed": True
                }
            
            # 尝试下载文件
            for attempt in range(self.retry_count + 1):
                try:
                    logger.debug(f"下载文件: {file_name} (尝试 {attempt+1}/{self.retry_count+1})")
                    
                    # 下载文件
                    downloaded_file = await message.download(file_name=file_path)
                    
                    if downloaded_file:
                        # 下载成功
                        duration = time.time() - start_time
                        file_size = os.path.getsize(file_path) if os.path.exists(file_path) else 0
                        
                        # 确保message_id是字符串
                        str_message_id = str(message_id)
                        
                        # 更新下载映射
                        self.download_mapping[str_message_id] = file_path
                        self.processed_files.add(file_path)
                        
                        # 保存更新的映射
                        self._save_metadata()
                        
                        logger.info(f"下载成功: {file_name} ({file_size/1024:.1f} KB, {duration:.1f}秒)")
                        
                        # 返回包含媒体组ID的结果
                        media_group_id = group_id or (message.media_group_id if hasattr(message, "media_group_id") else None)
                        
                        return {
                            "message_id": message_id,
                            "chat_id": chat_id,
                            "media_group_id": media_group_id,
                            "file_path": file_path,
                            "file_name": file_name,
                            "success": True,
                            "duration": duration,
                            "file_size": file_size
                        }
                    else:
                        logger.warning(f"下载失败: {file_name} (无内容)")
                except FloodWait as e:
                    wait_time = e.x
                    logger.warning(f"触发频率限制，等待 {wait_time} 秒")
                    await asyncio.sleep(wait_time)
                except Exception as e:
                    logger.error(f"下载文件出错: {file_name}, 错误: {str(e)}")
                    if attempt < self.retry_count:
                        retry_wait = self.retry_delay * (attempt + 1)
                        logger.info(f"将在 {retry_wait} 秒后重试...")
                        await asyncio.sleep(retry_wait)
                    else:
                        break
            
            # 所有重试都失败
            return {
                "message_id": message_id,
                "file_name": file_name,
                "success": False,
                "error": "下载失败，达到最大重试次数"
            }
    
    def _generate_file_name(self, message: Message, chat_id: int, message_id: int, group_id: str = None) -> str:
        """
        生成唯一文件名
        
        Args:
            message: 消息对象
            chat_id: 聊天ID
            message_id: 消息ID
            group_id: 媒体组ID
            
        Returns:
            str: 文件名
        """
        # 确定文件后缀和原始文件名
        original_name = ""
        ext = ""
        
        if hasattr(message, "document") and message.document:
            original_name = message.document.file_name or ""
            if original_name:
                ext = os.path.splitext(original_name)[1] or ""
                original_name = os.path.splitext(original_name)[0]
        elif hasattr(message, "photo") and message.photo:
            ext = ".jpg"
        elif hasattr(message, "video") and message.video:
            ext = ".mp4"
            original_name = message.video.file_name or ""
            if original_name:
                original_name = os.path.splitext(original_name)[0]
        elif hasattr(message, "audio") and message.audio:
            ext = ".mp3"
            original_name = message.audio.file_name or ""
            if original_name:
                original_name = os.path.splitext(original_name)[0]
        elif hasattr(message, "voice") and message.voice:
            ext = ".ogg"
        elif hasattr(message, "animation") and message.animation:
            ext = ".mp4"
        
        # 生成基本文件名
        base_name = f"{chat_id}_{message_id}"
        
        # 添加媒体组ID
        if group_id:
            base_name = f"{base_name}_group_{group_id}"
        
        # 添加原始文件名
        if original_name:
            # 移除不安全字符
            safe_original_name = "".join(c for c in original_name if c.isalnum() or c in "._- ")
            # 限制长度
            safe_original_name = safe_original_name[:50]
            base_name = f"{base_name}_{safe_original_name}"
        
        # 添加后缀
        return f"{base_name}{ext}"
    
    def _has_downloadable_media(self, message: Message) -> bool:
        """
        检查消息是否包含可下载的媒体
        
        Args:
            message: 消息对象
            
        Returns:
            bool: 是否包含可下载媒体
        """
        return (
            (hasattr(message, "photo") and message.photo) or
            (hasattr(message, "video") and message.video) or
            (hasattr(message, "document") and message.document) or
            (hasattr(message, "audio") and message.audio) or
            (hasattr(message, "voice") and message.voice) or
            (hasattr(message, "animation") and message.animation)
        )
    
    def _store_message_metadata(self, message: Message, group_id: str = None) -> None:
        """
        存储消息元数据
        
        Args:
            message: 消息对象
            group_id: 媒体组ID
        """
        # 确保消息ID存在
        if not message or not hasattr(message, "id"):
            return
        
        # 提取基本信息
        msg_id = message.id
        chat_id = message.chat.id if hasattr(message, "chat") and message.chat else None
        
        # 确定媒体组ID - 优先使用传入的group_id，其次使用消息自带的media_group_id
        media_group_id = None
        if group_id:
            media_group_id = group_id
            logger.debug(f"使用传入的媒体组ID: {group_id} (消息ID: {msg_id})")
        elif hasattr(message, "media_group_id") and message.media_group_id:
            media_group_id = message.media_group_id
            logger.debug(f"使用消息自带的媒体组ID: {media_group_id} (消息ID: {msg_id})")
        
        metadata = {
            "message_id": msg_id,
            "chat_id": chat_id,
            "date": message.date.timestamp() if hasattr(message, "date") and message.date else time.time(),
            "media_group_id": media_group_id,
            "message_type": self._get_message_type(message),
            "caption": message.caption if hasattr(message, "caption") else None,
            "caption_entities": [entity_to_dict(entity) for entity in message.caption_entities] if hasattr(message, "caption_entities") and message.caption_entities else None,
            "text": message.text if hasattr(message, "text") else None,
            "text_entities": [entity_to_dict(entity) for entity in message.entities] if hasattr(message, "entities") and message.entities else None,
        }
        
        # 添加文件特有的元数据
        if hasattr(message, "document") and message.document:
            metadata.update({
                "file_name": message.document.file_name,
                "file_size": message.document.file_size,
                "mime_type": message.document.mime_type
            })
        elif hasattr(message, "video") and message.video:
            metadata.update({
                "duration": message.video.duration,
                "width": message.video.width,
                "height": message.video.height,
                "file_name": message.video.file_name,
                "file_size": message.video.file_size,
                "mime_type": message.video.mime_type
            })
        elif hasattr(message, "audio") and message.audio:
            metadata.update({
                "duration": message.audio.duration,
                "performer": message.audio.performer,
                "title": message.audio.title,
                "file_name": message.audio.file_name,
                "file_size": message.audio.file_size,
                "mime_type": message.audio.mime_type
            })
        elif hasattr(message, "photo") and message.photo:
            # 对于照片，选择最大尺寸
            metadata.update({
                "width": message.photo.width,
                "height": message.photo.height,
                "file_size": message.photo.file_size
            })
        
        # 将消息ID转为字符串作为键
        str_msg_id = str(msg_id)
        
        # 存储元数据
        self.message_metadata[str_msg_id] = metadata
        
        # 记录添加的元数据
        logger.debug(f"已存储消息 {msg_id} 的元数据，媒体组ID: {media_group_id}, 类型: {metadata['message_type']}")
        
        # 保存元数据到文件
        self._save_metadata()
    
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
    
    async def _process_message_media(self, message) -> Dict[str, Any]:
        """
        处理单个消息的媒体文件下载
        
        Args:
            message: 消息数据（Pyrogram Message对象）
            
        Returns:
            Dict[str, Any]: 下载结果
        """
        try:
            # 获取消息基本信息（直接访问属性而不是使用get方法）
            message_id = message.id if hasattr(message, "id") else 0
            chat_id = message.chat.id if hasattr(message, "chat") else 0
            group_id = message.media_group_id if hasattr(message, "media_group_id") else None
            
            # 存储消息元数据
            self._store_message_metadata(message, group_id)
            
            # 检查消息是否包含可下载媒体
            if not self._has_downloadable_media(message):
                logger.debug(f"消息 {chat_id}_{message_id} 不包含可下载媒体")
                return None
            
            # 下载媒体文件
            result = await self._download_media_file(message, group_id)
            return result
            
        except Exception as e:
            logger.error(f"处理消息媒体出错: {str(e)}")
            import traceback
            logger.error(f"错误详情: {traceback.format_exc()}")
            message_id = message.id if hasattr(message, "id") else "unknown"
            chat_id = message.chat.id if hasattr(message, "chat") else "unknown"
            return {"error": str(e), "message_id": message_id, "chat_id": chat_id}
    
    def _is_message_downloaded(self, chat_id, message_id) -> bool:
        """
        检查消息是否已经下载过
        
        Args:
            chat_id: 聊天ID
            message_id: 消息ID
            
        Returns:
            bool: 是否已下载
        """
        key = f"{chat_id}_{message_id}"
        return key in self.downloaded_messages
        
    def _mark_message_downloaded(self, chat_id, message_id) -> None:
        """
        标记消息已下载
        
        Args:
            chat_id: 聊天ID
            message_id: 消息ID
        """
        key = f"{chat_id}_{message_id}"
        self.downloaded_messages.add(key)
        
        # 定期保存下载状态
        if len(self.downloaded_messages) % 10 == 0:
            self._save_downloaded_messages()
    
    def _save_downloaded_messages(self) -> None:
        """
        保存已下载消息记录到文件
        """
        try:
            download_record_path = os.path.join(self.temp_folder, "downloaded_messages.json")
            with open(download_record_path, 'w', encoding='utf-8') as f:
                json.dump(list(self.downloaded_messages), f)
            logger.debug(f"已保存下载记录，共 {len(self.downloaded_messages)} 条消息")
        except Exception as e:
            logger.error(f"保存下载记录失败: {str(e)}")
    
    def _load_downloaded_messages(self) -> None:
        """
        从文件加载已下载消息记录
        """
        try:
            download_record_path = os.path.join(self.temp_folder, "downloaded_messages.json")
            if os.path.exists(download_record_path):
                with open(download_record_path, 'r', encoding='utf-8') as f:
                    records = json.load(f)
                    self.downloaded_messages = set(records)
                logger.info(f"已加载下载记录，共 {len(self.downloaded_messages)} 条消息")
            else:
                logger.info("下载记录文件不存在，创建新记录")
                self.downloaded_messages = set()
        except Exception as e:
            logger.error(f"加载下载记录失败: {str(e)}")
            self.downloaded_messages = set() 