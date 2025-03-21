"""
上传器实现类
负责上传和转发媒体文件
"""

import os
import time
import asyncio
import shutil
from typing import Dict, Any, List, Union, Optional, Tuple
from datetime import datetime, timedelta

from pyrogram.types import Message
from pyrogram.errors import FloodWait, MessageIdInvalid, MessageNotModified

from tg_forwarder.interfaces.uploader_interface import UploaderInterface
from tg_forwarder.interfaces.client_interface import TelegramClientInterface
from tg_forwarder.interfaces.config_interface import ConfigInterface
from tg_forwarder.interfaces.logger_interface import LoggerInterface
from tg_forwarder.interfaces.storage_interface import StorageInterface
from tg_forwarder.interfaces.status_tracker_interface import StatusTrackerInterface


class Uploader(UploaderInterface):
    """
    上传器类，实现UploaderInterface接口
    负责上传下载的媒体到目标频道
    """
    
    def __init__(self, client: TelegramClientInterface, config: ConfigInterface, 
                 logger: LoggerInterface, storage: StorageInterface,
                 status_tracker: StatusTrackerInterface):
        """
        初始化上传器
        
        Args:
            client: Telegram客户端接口实例
            config: 配置接口实例
            logger: 日志接口实例
            storage: 存储接口实例
            status_tracker: 状态追踪器接口实例
        """
        self._client = client
        self._config = config
        self._logger = logger.get_logger("Uploader")
        self._storage = storage
        self._status_tracker = status_tracker
        
        self._initialized = False
        self._upload_semaphore = None  # 上传信号量，用于限制并发上传数
        self._temp_dir = None  # 临时文件目录
        
        # 上传状态追踪
        self._upload_status = {}  # task_id -> status
        self._media_groups = {}  # group_id -> [task_ids]
        
    async def initialize(self) -> bool:
        """
        初始化上传器
        
        Returns:
            bool: 初始化是否成功
        """
        try:
            # 创建上传信号量
            max_concurrent_uploads = self._config.get_max_concurrent_uploads(5)
            self._upload_semaphore = asyncio.Semaphore(max_concurrent_uploads)
            
            # 创建临时目录
            self._temp_dir = self._config.get_temp_dir()
            if not self._temp_dir:
                self._temp_dir = os.path.join(os.getcwd(), "temp")
            
            os.makedirs(self._temp_dir, exist_ok=True)
            
            # 清理过期临时文件
            self.cleanup_temp_files()
            
            self._initialized = True
            self._logger.info(f"上传器初始化完成，最大并发上传数: {max_concurrent_uploads}")
            return True
        except Exception as e:
            self._logger.error(f"初始化上传器失败: {str(e)}", exc_info=True)
            self._initialized = False
            return False
    
    async def shutdown(self) -> None:
        """关闭上传器，释放资源"""
        if not self._initialized:
            return
        
        try:
            # 清理临时文件
            self.cleanup_temp_files(0)  # 清理所有临时文件
            
            self._initialized = False
            self._logger.info("上传器已关闭")
        except Exception as e:
            self._logger.error(f"关闭上传器时发生错误: {str(e)}", exc_info=True)
    
    async def upload_batch(self, batch_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        上传一批媒体文件
        
        Args:
            batch_data: 批次数据，格式如下:
            {
                "target_chat_id": chat_id,
                "files": [
                    {
                        "task_id": "...",
                        "chat_id": original_chat_id,
                        "message_id": original_message_id,
                        "file_path": "path/to/file",
                        "media_type": "photo|video|document|...",
                        "caption": "...",
                        "date": timestamp,
                        "group_id": "..." # 可选，媒体组ID
                    },
                    ...
                ],
                "options": {
                    "forward_to_channels": [chat_id1, chat_id2, ...], # 可选，要转发到的其他频道
                    "add_source_info": True, # 可选，是否添加来源信息
                    "remove_caption": False, # 可选，是否移除原始标题
                    "caption_template": "..." # 可选，标题模板
                }
            }
            
        Returns:
            Dict[str, Any]: 上传结果，格式如下:
            {
                "success": [
                    {
                        "task_id": "...",
                        "original_chat_id": chat_id,
                        "original_message_id": message_id,
                        "target_chat_id": target_chat_id,
                        "target_message_id": target_message_id
                    },
                    ...
                ],
                "failed": [
                    {
                        "task_id": "...",
                        "original_chat_id": chat_id,
                        "original_message_id": message_id,
                        "error": "错误信息"
                    },
                    ...
                ]
            }
        """
        if not self._initialized:
            await self.initialize()
        
        target_chat_id = batch_data.get("target_chat_id")
        files = batch_data.get("files", [])
        options = batch_data.get("options", {})
        
        # 结果
        result = {
            "success": [],
            "failed": []
        }
        
        # 重置状态追踪
        self._upload_status = {}
        self._media_groups = {}
        
        # 首先按媒体组分组
        media_groups = {}
        single_files = []
        
        for file_info in files:
            group_id = file_info.get("group_id")
            if group_id:
                if group_id not in media_groups:
                    media_groups[group_id] = []
                media_groups[group_id].append(file_info)
            else:
                single_files.append(file_info)
        
        # 处理单个文件
        for file_info in single_files:
            upload_result = await self._upload_single_file(target_chat_id, file_info, options)
            if upload_result.get("success"):
                result["success"].append(upload_result["data"])
                
                # 检查是否需要转发到其他频道
                if options.get("forward_to_channels"):
                    await self._forward_to_other_channels(
                        target_chat_id,
                        upload_result["data"]["target_message_id"],
                        file_info["message_id"],
                        False,
                        file_info["chat_id"]
                    )
            else:
                result["failed"].append({
                    "task_id": file_info.get("task_id"),
                    "original_chat_id": file_info.get("chat_id"),
                    "original_message_id": file_info.get("message_id"),
                    "error": upload_result.get("error", "未知错误")
                })
        
        # 处理媒体组
        for group_id, group_files in media_groups.items():
            group_result = await self._upload_media_group(target_chat_id, group_id, group_files, options)
            result["success"].extend(group_result["success"])
            result["failed"].extend(group_result["failed"])
            
            # 检查是否需要转发到其他频道，只有在至少有一个成功时才转发
            if group_result["success"] and options.get("forward_to_channels"):
                first_success = group_result["success"][0]
                await self._forward_to_other_channels(
                    target_chat_id,
                    first_success["target_message_id"],
                    group_id,
                    True,
                    group_files[0]["chat_id"]
                )
        
        return result
    
    async def _upload_single_file(self, target_chat_id: Union[str, int], file_info: Dict[str, Any], options: Dict[str, Any]) -> Dict[str, Any]:
        """
        上传单个文件
        
        Args:
            target_chat_id: 目标聊天ID
            file_info: 文件信息
            options: 上传选项
            
        Returns:
            Dict[str, Any]: 上传结果
        """
        task_id = file_info.get("task_id")
        chat_id = file_info.get("chat_id")
        message_id = file_info.get("message_id")
        file_path = file_info.get("file_path")
        media_type = file_info.get("media_type", "")
        caption = file_info.get("caption", "")
        
        # 更新上传状态
        self._upload_status[task_id] = "uploading"
        
        try:
            # 记录上传开始
            await self._status_tracker.record_upload_start(task_id, target_chat_id)
            
            # 检查文件是否存在
            if not os.path.exists(file_path):
                error_msg = f"文件不存在: {file_path}"
                await self._status_tracker.record_upload_failed(task_id, target_chat_id, error_msg)
                self._upload_status[task_id] = "failed"
                return {"success": False, "error": error_msg}
            
            # 处理标题
            if options.get("remove_caption"):
                caption = ""
            elif options.get("caption_template") and caption:
                caption_template = options.get("caption_template")
                caption = caption_template.format(
                    original_caption=caption,
                    date=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                    source_chat_id=chat_id,
                    source_message_id=message_id
                )
            
            # 添加来源信息
            if options.get("add_source_info") and caption:
                # 获取源频道信息
                source_chat = await self._client.get_entity(chat_id)
                source_chat_title = getattr(source_chat, "title", str(chat_id))
                
                # 添加来源信息到标题
                source_info = f"\n\n📢 来源: {source_chat_title}"
                if len(caption + source_info) <= 1024:  # Telegram标题最大长度
                    caption += source_info
            
            # 限制并发上传
            async with self._upload_semaphore:
                # 根据媒体类型上传
                if media_type == "photo":
                    message = await self._client.send_media(target_chat_id, "photo", file_path, caption=caption)
                elif media_type == "video":
                    message = await self._client.send_media(target_chat_id, "video", file_path, caption=caption)
                elif media_type == "document":
                    message = await self._client.send_media(target_chat_id, "document", file_path, caption=caption)
                elif media_type == "audio":
                    message = await self._client.send_media(target_chat_id, "audio", file_path, caption=caption)
                elif media_type == "animation":
                    message = await self._client.send_media(target_chat_id, "animation", file_path, caption=caption)
                elif media_type == "voice":
                    message = await self._client.send_media(target_chat_id, "voice", file_path, caption=caption)
                elif media_type == "sticker":
                    # 贴纸一般不需要标题
                    message = await self._client.send_media(target_chat_id, "sticker", file_path)
                else:
                    # 未知类型，作为文档发送
                    message = await self._client.send_media(target_chat_id, "document", file_path, caption=caption)
                
            if not message:
                error_msg = "发送消息失败"
                await self._status_tracker.record_upload_failed(task_id, target_chat_id, error_msg)
                self._upload_status[task_id] = "failed"
                return {"success": False, "error": error_msg}
            
            # 记录上传成功
            await self._status_tracker.record_upload_complete(task_id, target_chat_id, message.id)
            self._upload_status[task_id] = "completed"
            
            # 保存上传记录
            self._save_upload_record(task_id, chat_id, message_id, target_chat_id, message.id, media_type)
            
            return {
                "success": True,
                "data": {
                    "task_id": task_id,
                    "original_chat_id": chat_id,
                    "original_message_id": message_id,
                    "target_chat_id": target_chat_id,
                    "target_message_id": message.id
                }
            }
            
        except Exception as e:
            error_msg = f"上传文件失败: {str(e)}"
            self._logger.error(error_msg, exc_info=True)
            
            # 记录上传失败
            await self._status_tracker.record_upload_failed(task_id, target_chat_id, error_msg)
            self._upload_status[task_id] = "failed"
            
            return {"success": False, "error": error_msg}
    
    async def _upload_media_group(self, target_chat_id: Union[str, int], group_id: str, 
                                 files: List[Dict[str, Any]], options: Dict[str, Any]) -> Dict[str, Any]:
        """
        上传媒体组
        
        Args:
            target_chat_id: 目标聊天ID
            group_id: 媒体组ID
            files: 文件信息列表
            options: 上传选项
            
        Returns:
            Dict[str, Any]: 上传结果
        """
        result = {
            "success": [],
            "failed": []
        }
        
        # 排序文件，确保按照媒体组的顺序上传
        files = sorted(files, key=lambda x: x.get("message_id", 0))
        
        # 初始化媒体组跟踪
        self._media_groups[group_id] = [file_info.get("task_id") for file_info in files]
        first_success = None
        
        try:
            # 准备媒体数组
            media_array = []
            task_ids = []
            
            for file_info in files:
                task_id = file_info.get("task_id")
                chat_id = file_info.get("chat_id")
                message_id = file_info.get("message_id")
                file_path = file_info.get("file_path")
                media_type = file_info.get("media_type", "")
                caption = file_info.get("caption", "")
                
                # 更新上传状态
                self._upload_status[task_id] = "uploading"
                
                # 记录上传开始
                await self._status_tracker.record_upload_start(task_id, target_chat_id)
                
                # 检查文件是否存在
                if not os.path.exists(file_path):
                    await self._status_tracker.record_upload_failed(
                        task_id, target_chat_id, f"文件不存在: {file_path}")
                    self._upload_status[task_id] = "failed"
                    
                    result["failed"].append({
                        "task_id": task_id,
                        "original_chat_id": chat_id,
                        "original_message_id": message_id,
                        "error": f"文件不存在: {file_path}"
                    })
                    continue
                
                # 处理标题（仅第一个文件有标题）
                if len(media_array) > 0:
                    # 媒体组中只有第一个媒体可以有标题
                    caption = ""
                elif options.get("remove_caption"):
                    caption = ""
                elif options.get("caption_template") and caption:
                    caption_template = options.get("caption_template")
                    caption = caption_template.format(
                        original_caption=caption,
                        date=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                        source_chat_id=chat_id,
                        source_message_id=message_id,
                        source_group_id=group_id
                    )
                    
                    # 添加来源信息
                    if options.get("add_source_info") and caption:
                        # 获取源频道信息
                        source_chat = await self._client.get_entity(chat_id)
                        source_chat_title = getattr(source_chat, "title", str(chat_id))
                        
                        # 添加来源信息到标题
                        source_info = f"\n\n📢 来源: {source_chat_title}"
                        if len(caption + source_info) <= 1024:  # Telegram标题最大长度
                            caption += source_info
                
                # 添加到媒体数组
                media_array.append({
                    "file_path": file_path,
                    "media_type": media_type,
                    "caption": caption
                })
                
                task_ids.append(task_id)
            
            # 如果没有有效媒体，返回
            if not media_array:
                return result
            
            # 上传媒体组
            async with self._upload_semaphore:
                # 分批上传媒体组（Telegram限制最多10个媒体）
                for i in range(0, len(media_array), 10):
                    batch = media_array[i:i+10]
                    batch_task_ids = task_ids[i:i+10]
                    batch_files = files[i:i+10]
                    
                    # 准备发送媒体组
                    input_media = []
                    for media in batch:
                        media_type = media["media_type"]
                        file_path = media["file_path"]
                        caption = media["caption"]
                        
                        if media_type == "photo":
                            input_media.append({
                                "type": "photo",
                                "media": file_path,
                                "caption": caption
                            })
                        elif media_type == "video":
                            input_media.append({
                                "type": "video",
                                "media": file_path,
                                "caption": caption
                            })
                        elif media_type == "audio":
                            input_media.append({
                                "type": "audio",
                                "media": file_path,
                                "caption": caption
                            })
                        else:
                            # 其他类型作为文档发送
                            input_media.append({
                                "type": "document",
                                "media": file_path,
                                "caption": caption
                            })
                    
                    # 发送媒体组
                    messages = await self._client.send_media_group(target_chat_id, input_media)
                    
                    if not messages:
                        # 记录所有任务失败
                        for idx, task_id in enumerate(batch_task_ids):
                            file_info = batch_files[idx]
                            await self._status_tracker.record_upload_failed(
                                task_id, target_chat_id, "发送媒体组失败")
                            self._upload_status[task_id] = "failed"
                            
                            result["failed"].append({
                                "task_id": task_id,
                                "original_chat_id": file_info.get("chat_id"),
                                "original_message_id": file_info.get("message_id"),
                                "error": "发送媒体组失败"
                            })
                        continue
                    
                    # 记录成功
                    for idx, message in enumerate(messages):
                        if idx >= len(batch_task_ids):
                            break  # 安全检查
                            
                        task_id = batch_task_ids[idx]
                        file_info = batch_files[idx]
                        
                        await self._status_tracker.record_upload_complete(
                            task_id, target_chat_id, message.id)
                        self._upload_status[task_id] = "completed"
                        
                        # 保存上传记录
                        self._save_upload_record(
                            task_id, 
                            file_info.get("chat_id"), 
                            file_info.get("message_id"), 
                            target_chat_id, 
                            message.id, 
                            file_info.get("media_type"),
                            group_id
                        )
                        
                        success_info = {
                            "task_id": task_id,
                            "original_chat_id": file_info.get("chat_id"),
                            "original_message_id": file_info.get("message_id"),
                            "target_chat_id": target_chat_id,
                            "target_message_id": message.id
                        }
                        
                        result["success"].append(success_info)
                        
                        # 记录第一个成功的消息，用于转发
                        if first_success is None:
                            first_success = success_info
            
            return result
            
        except Exception as e:
            error_msg = f"上传媒体组失败: {str(e)}"
            self._logger.error(error_msg, exc_info=True)
            
            # 记录所有未完成任务失败
            for file_info in files:
                task_id = file_info.get("task_id")
                if self._upload_status.get(task_id) != "completed":
                    await self._status_tracker.record_upload_failed(
                        task_id, target_chat_id, error_msg)
                    self._upload_status[task_id] = "failed"
                    
                    result["failed"].append({
                        "task_id": task_id,
                        "original_chat_id": file_info.get("chat_id"),
                        "original_message_id": file_info.get("message_id"),
                        "error": error_msg
                    })
            
            return result
    
    async def _forward_to_other_channels(self, source_channel: Union[str, int], 
                                       message_id: int, 
                                       original_id: Union[str, int],
                                       is_media_group: bool = False,
                                       source_channel_id: Optional[Union[str, int]] = None) -> None:
        """
        将消息从第一个频道转发到其他频道
        
        Args:
            source_channel: 源频道ID（已上传的频道）
            message_id: 消息ID（已上传的消息）
            original_id: 原始消息ID或媒体组ID
            is_media_group: 是否为媒体组
            source_channel_id: 原始来源频道ID（可选）
        """
        try:
            # 获取转发配置
            forward_channels = self._config.get_forward_channels()
            if not forward_channels:
                return
            
            # 获取失败重试次数和间隔
            max_retries = self._config.get_forward_retries(3)
            retry_delay = self._config.get_forward_retry_delay(5)
            
            for channel_id in forward_channels:
                # 跳过源频道
                if str(channel_id) == str(source_channel):
                    continue
                
                retries = 0
                success = False
                
                while retries < max_retries and not success:
                    try:
                        # 转发消息
                        message = await self._client.forward_message(channel_id, source_channel, message_id)
                        if message:
                            success = True
                            
                            # 保存转发记录
                            self._save_forward_record(
                                source_channel, message_id,
                                channel_id, message.id,
                                original_id, is_media_group, source_channel_id
                            )
                        else:
                            retries += 1
                            await asyncio.sleep(retry_delay)
                            
                    except FloodWait as e:
                        self._logger.warning(f"转发到频道 {channel_id} 时触发FloodWait: {e.value}秒")
                        await asyncio.sleep(e.value)
                    
                    except Exception as e:
                        self._logger.error(f"转发到频道 {channel_id} 失败: {str(e)}", exc_info=True)
                        retries += 1
                        await asyncio.sleep(retry_delay)
                
                if not success:
                    self._logger.warning(f"转发消息 {message_id} 到频道 {channel_id} 失败，已重试 {max_retries} 次")
            
        except Exception as e:
            self._logger.error(f"转发消息过程中发生错误: {str(e)}", exc_info=True)
    
    def _save_upload_record(self, task_id: str, original_chat_id: Union[str, int], 
                          original_message_id: int, target_chat_id: Union[str, int], 
                          target_message_id: int, media_type: str, group_id: str = None) -> None:
        """
        保存上传记录
        
        Args:
            task_id: 任务ID
            original_chat_id: 原始聊天ID
            original_message_id: 原始消息ID
            target_chat_id: 目标聊天ID
            target_message_id: 目标消息ID
            media_type: 媒体类型
            group_id: 媒体组ID（可选）
        """
        try:
            record = {
                "task_id": task_id,
                "original_chat_id": str(original_chat_id),
                "original_message_id": original_message_id,
                "target_chat_id": str(target_chat_id),
                "target_message_id": target_message_id,
                "media_type": media_type,
                "uploaded_at": datetime.now().isoformat()
            }
            
            if group_id:
                record["group_id"] = group_id
            
            key = f"upload:{original_chat_id}:{original_message_id}"
            self._storage.store_data("uploads", key, record)
            
        except Exception as e:
            self._logger.error(f"保存上传记录失败: {str(e)}", exc_info=True)
    
    def _save_forward_record(self, source_chat_id: Union[str, int], source_message_id: int,
                           target_chat_id: Union[str, int], target_message_id: int,
                           original_id: Union[str, int], is_media_group: bool,
                           original_chat_id: Optional[Union[str, int]] = None) -> None:
        """
        保存转发记录
        
        Args:
            source_chat_id: 源聊天ID（已上传的频道）
            source_message_id: 源消息ID（已上传的消息）
            target_chat_id: 目标聊天ID
            target_message_id: 目标消息ID
            original_id: 原始消息ID或媒体组ID
            is_media_group: 是否为媒体组
            original_chat_id: 原始来源频道ID（可选）
        """
        try:
            record = {
                "source_chat_id": str(source_chat_id),
                "source_message_id": source_message_id,
                "target_chat_id": str(target_chat_id),
                "target_message_id": target_message_id,
                "original_id": original_id,
                "is_media_group": is_media_group,
                "forwarded_at": datetime.now().isoformat()
            }
            
            if original_chat_id:
                record["original_chat_id"] = str(original_chat_id)
            
            key = f"forward:{source_chat_id}:{source_message_id}:{target_chat_id}"
            self._storage.store_data("forwards", key, record)
            
        except Exception as e:
            self._logger.error(f"保存转发记录失败: {str(e)}", exc_info=True)
    
    def cleanup_old_records(self, max_age_days: int = 30) -> int:
        """
        清理旧的上传记录
        
        Args:
            max_age_days: 最大保留天数
            
        Returns:
            int: 清理的记录数量
        """
        try:
            cutoff_date = datetime.now() - timedelta(days=max_age_days)
            cutoff_str = cutoff_date.isoformat()
            
            # 查询旧记录
            old_uploads = self._storage.query_data(
                "uploads", 
                {"value.uploaded_at": {"$lt": cutoff_str}}
            )
            
            old_forwards = self._storage.query_data(
                "forwards", 
                {"value.forwarded_at": {"$lt": cutoff_str}}
            )
            
            # 删除旧记录
            deleted_count = 0
            for record in old_uploads:
                key = record.get("key")
                if key:
                    self._storage.delete_data("uploads", key)
                    deleted_count += 1
            
            for record in old_forwards:
                key = record.get("key")
                if key:
                    self._storage.delete_data("forwards", key)
                    deleted_count += 1
            
            self._logger.info(f"已清理 {deleted_count} 条旧记录")
            return deleted_count
            
        except Exception as e:
            self._logger.error(f"清理旧记录失败: {str(e)}", exc_info=True)
            return 0
    
    def cleanup_temp_files(self, max_age_hours: int = 24) -> int:
        """
        清理过期的临时文件
        
        Args:
            max_age_hours: 最大保留小时数，0表示清理所有文件
            
        Returns:
            int: 清理的文件数量
        """
        if not self._temp_dir or not os.path.exists(self._temp_dir):
            return 0
        
        deleted_count = 0
        current_time = time.time()
        
        try:
            for root, dirs, files in os.walk(self._temp_dir):
                for file in files:
                    file_path = os.path.join(root, file)
                    
                    # 检查文件修改时间
                    if max_age_hours == 0 or os.path.getmtime(file_path) < current_time - (max_age_hours * 3600):
                        try:
                            os.remove(file_path)
                            deleted_count += 1
                        except OSError as e:
                            self._logger.warning(f"删除文件 {file_path} 失败: {str(e)}")
            
            # 清理空目录
            for root, dirs, files in os.walk(self._temp_dir, topdown=False):
                for dir in dirs:
                    dir_path = os.path.join(root, dir)
                    if not os.listdir(dir_path):
                        try:
                            os.rmdir(dir_path)
                        except OSError as e:
                            self._logger.warning(f"删除目录 {dir_path} 失败: {str(e)}")
            
            self._logger.info(f"已清理 {deleted_count} 个临时文件")
            return deleted_count
            
        except Exception as e:
            self._logger.error(f"清理临时文件失败: {str(e)}", exc_info=True)
            return deleted_count 