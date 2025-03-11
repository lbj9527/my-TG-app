"""
媒体下载模块，负责下载消息中的媒体文件到本地
"""

import os
import asyncio
import time
from typing import Dict, Any, Optional, List, Union, Tuple
from pyrogram.types import Message
from pyrogram.errors import FloodWait

from tg_forwarder.utils.logger import get_logger

logger = get_logger("downloader")

class MediaDownloader:
    """媒体下载器类，负责下载消息中的媒体文件"""
    
    def __init__(self, client, config: Dict[str, Any]):
        """
        初始化媒体下载器
        
        参数:
            client: Pyrogram客户端实例
            config: 下载配置信息
        """
        self.client = client
        self.temp_folder = config.get('temp_folder', './temp')
        self.timeout = config.get('timeout', 300)
        
        # 确保临时文件夹存在
        os.makedirs(self.temp_folder, exist_ok=True)
        
        logger.info(f"媒体下载器初始化完成，临时文件夹: {self.temp_folder}")
    
    async def _download_media_with_retry(self, message: Message, folder: str) -> Optional[str]:
        """
        带重试的媒体下载
        
        参数:
            message: 消息对象
            folder: 保存文件夹路径
            
        返回:
            Optional[str]: 下载文件的路径，如果下载失败则返回None
        """
        max_retries = 3
        retry_count = 0
        
        while retry_count < max_retries:
            try:
                # 获取原始文件名（如果有）
                original_filename = None
                if message.photo:
                    original_filename = f"{message.photo.file_unique_id}"
                elif message.video and message.video.file_name:
                    original_filename = message.video.file_name
                elif message.audio and message.audio.file_name:
                    original_filename = message.audio.file_name
                elif message.voice and message.voice.file_name:
                    original_filename = message.voice.file_name
                elif message.document and message.document.file_name:
                    original_filename = message.document.file_name
                
                # 获取扩展名
                extension = self._get_extension_for_media(message)
                
                # 创建文件名格式: 聊天ID_消息ID_原文件名
                chat_id = str(message.chat.id).replace('-100', '')
                if original_filename:
                    # 如果有原始文件名，使用原始文件名
                    unique_filename = f"{chat_id}_{message.id}_{original_filename}"
                    # 确保文件名不包含非法字符
                    unique_filename = "".join(c for c in unique_filename if c.isalnum() or c in "._-")
                    # 确保文件名有正确的扩展名
                    if extension and not unique_filename.lower().endswith(extension.lower()):
                        unique_filename += extension
                else:
                    # 如果没有原始文件名，使用ID和扩展名
                    unique_filename = f"{chat_id}_{message.id}{extension or '.bin'}"
                
                # 下载媒体文件
                file_path = await message.download(
                    file_name=os.path.join(folder, unique_filename),
                    block=True,
                    progress=self._progress_callback
                )
                
                if file_path:
                    logger.info(f"成功下载媒体文件: {file_path}")
                    return file_path
                else:
                    logger.warning(f"下载媒体文件失败，返回了空路径")
                    retry_count += 1
            
            except FloodWait as e:
                logger.warning(f"触发Telegram限流，等待{e.value}秒...")
                await asyncio.sleep(e.value)
                # 不计入重试次数，因为这是Telegram的限制
            
            except Exception as e:
                logger.error(f"下载媒体文件时出错: {str(e)}")
                retry_count += 1
                await asyncio.sleep(2)  # 等待2秒后重试
        
        logger.error(f"媒体文件下载失败，已重试{max_retries}次")
        return None
    
    async def _progress_callback(self, current, total):
        """下载进度回调函数"""
        # 每10%更新一次进度
        if total > 0 and current % (total // 10) < 100000:
            progress = current / total * 100
            logger.info(f"下载进度: {progress:.1f}%")
    
    def _get_extension_for_media(self, message: Message) -> str:
        """
        根据媒体类型获取适当的文件扩展名
        
        参数:
            message: 消息对象
            
        返回:
            str: 文件扩展名（包括点号）
        """
        if message.photo:
            return ".jpg"
        elif message.video:
            # 尝试获取原始文件扩展名
            if message.video.file_name:
                _, ext = os.path.splitext(message.video.file_name)
                if ext:
                    return ext
            return ".mp4"
        elif message.audio:
            if message.audio.file_name:
                _, ext = os.path.splitext(message.audio.file_name)
                if ext:
                    return ext
            return ".mp3"
        elif message.voice:
            return ".ogg"
        elif message.document:
            if message.document.file_name:
                _, ext = os.path.splitext(message.document.file_name)
                if ext:
                    return ext
        elif message.animation:
            return ".mp4"
        elif message.video_note:
            return ".mp4"
        
        # 默认返回空，将在下载时使用.bin
        return ""
    
    async def download_media_from_message(self, message: Message) -> Optional[str]:
        """
        从消息中下载媒体文件
        
        参数:
            message: 消息对象
            
        返回:
            Optional[str]: 下载文件的路径，如果消息不包含媒体或下载失败则返回None
        """
        if not message.media:
            return None
        
        # 直接下载到临时文件夹
        return await self._download_media_with_retry(message, self.temp_folder)
    
    async def download_media_from_messages(self, messages: List[Message]) -> Dict[int, Optional[str]]:
        """
        从多个消息中下载媒体文件
        
        参数:
            messages: 消息对象列表
            
        返回:
            Dict[int, Optional[str]]: 下载结果，格式为 {消息ID: 文件路径}
        """
        results = {}
        
        for message in messages:
            file_path = await self.download_media_from_message(message)
            results[message.id] = file_path
        
        # 输出统计结果
        success_count = sum(1 for path in results.values() if path is not None)
        logger.info(f"媒体下载统计: 总共 {len(messages)} 个文件, 成功 {success_count} 个")
        
        return results
    
    def _get_media_type(self, message: Message) -> Optional[str]:
        """
        获取消息中媒体的类型
        
        参数:
            message: 消息对象
            
        返回:
            Optional[str]: 媒体类型，如果没有媒体则返回None
        """
        if message.photo:
            return "photo"
        elif message.video:
            return "video"
        elif message.audio:
            return "audio"
        elif message.document:
            return "document"
        elif message.animation:
            return "animation"
        elif message.voice:
            return "audio"  # 语音也保存在audio文件夹
        elif message.video_note:
            return "video"  # 视频笔记也保存在video文件夹
        
        return None
    
    async def download_media_group(self, media_group: List[Message]) -> Dict[int, Optional[str]]:
        """
        下载媒体组中的所有媒体文件
        
        参数:
            media_group: 媒体组消息列表
            
        返回:
            Dict[int, Optional[str]]: 下载结果，格式为 {消息ID: 文件路径}
        """
        if not media_group:
            return {}
        
        logger.info(f"开始下载媒体组 (组ID: {media_group[0].media_group_id}), 共 {len(media_group)} 个文件")
        return await self.download_media_from_messages(media_group)
    
    async def download_forwarded_messages(self, forward_results: Dict[str, List[Message]]) -> Dict[str, Dict[int, Optional[str]]]:
        """
        下载转发结果中的所有媒体文件
        
        参数:
            forward_results: 转发结果，格式为 {目标频道: [转发的消息]}
            
        返回:
            Dict[str, Dict[int, Optional[str]]]: 下载结果，格式为 {目标频道: {消息ID: 文件路径}}
        """
        # 去重：创建一个字典来跟踪已处理的文件
        # 键是文件的唯一标识符，值是下载的路径
        downloaded_files = {}
        
        # 收集所有唯一的媒体消息
        all_messages = []
        seen_file_ids = set()  # 使用set来跟踪已处理的文件ID
        
        # 首先，收集每个转发目标中第一个目标频道的所有消息
        # 只处理第一个目标频道的消息，避免重复下载
        if forward_results:
            first_target = next(iter(forward_results.keys()))
            messages = forward_results[first_target]
            
            logger.info(f"只从第一个目标频道 {first_target} 收集媒体文件，共 {len(messages)} 条消息")
            
            for msg in messages:
                # 跳过非媒体消息
                if not msg.media:
                    continue
                
                # 获取文件的唯一ID
                file_unique_id = None
                if msg.photo:
                    file_unique_id = msg.photo.file_unique_id
                elif msg.video:
                    file_unique_id = msg.video.file_unique_id
                elif msg.document:
                    file_unique_id = msg.document.file_unique_id
                elif msg.audio:
                    file_unique_id = msg.audio.file_unique_id
                elif msg.voice:
                    file_unique_id = msg.voice.file_unique_id
                
                # 如果无法获取文件ID或已处理过，跳过
                if not file_unique_id or file_unique_id in seen_file_ids:
                    continue
                
                seen_file_ids.add(file_unique_id)
                all_messages.append(msg)
        
        # 如果没有媒体消息，直接返回
        if not all_messages:
            logger.info("没有发现需要下载的媒体文件")
            return {target: {} for target in forward_results.keys()}
            
        logger.info(f"开始下载所有唯一媒体文件，共 {len(all_messages)} 个")
        
        # 下载所有唯一的媒体文件
        download_results = {}
        
        # 将消息分组，媒体组放在一起处理
        grouped_messages = {}  # {media_group_id: [messages]}
        individual_messages = []
        
        for msg in all_messages:
            if msg.media_group_id:
                if msg.media_group_id not in grouped_messages:
                    grouped_messages[msg.media_group_id] = []
                grouped_messages[msg.media_group_id].append(msg)
            else:
                individual_messages.append(msg)
        
        # 下载媒体组
        for group_id, group_messages in grouped_messages.items():
            group_results = await self.download_media_group(group_messages)
            for msg_id, file_path in group_results.items():
                if file_path:
                    # 记录下载的文件路径
                    downloaded_files[msg_id] = file_path
        
        # 下载单个消息
        for msg in individual_messages:
            file_path = await self.download_media_from_message(msg)
            if file_path:
                downloaded_files[msg.id] = file_path
        
        # 将下载结果与每个目标频道关联
        for target in forward_results.keys():
            download_results[target] = {}
            for msg in forward_results[target]:
                if msg.media and msg.id in downloaded_files:
                    download_results[target][msg.id] = downloaded_files[msg.id]
                elif msg.media and msg.media_group_id and any(m.id in downloaded_files for m in forward_results[target] if m.media_group_id == msg.media_group_id):
                    # 对于媒体组，找一个已下载的成员
                    for m in forward_results[target]:
                        if m.media_group_id == msg.media_group_id and m.id in downloaded_files:
                            download_results[target][msg.id] = downloaded_files[m.id]
                            break
        
        # 统计下载结果
        total_unique_files = len(all_messages)
        total_success = len([f for f in downloaded_files.values() if f is not None])
        
        logger.info(f"媒体下载完成: 共 {total_unique_files} 个唯一文件, 成功下载 {total_success} 个")
        
        return download_results 