"""
媒体处理模块，负责下载和上传媒体文件
"""

import os
import asyncio
import time
from typing import Dict, Any, Optional, List, Union, Tuple, BinaryIO
import aiofiles
from pyrogram.types import Message
from pyrogram.errors import FloodWait

from tg_forwarder.utils.logger import get_logger

logger = get_logger("media")

class MediaHandler:
    """媒体处理类，负责下载和上传媒体文件"""
    
    def __init__(self, client, config: Dict[str, Any]):
        """
        初始化媒体处理器
        
        Args:
            client: Telegram客户端实例
            config: 媒体配置信息
        """
        self.client = client
        self.temp_folder = config.get('temp_folder', './temp')
        self.timeout = config.get('timeout', 300)
        self.chunk_size = config.get('chunk_size', 4096)
        
        # 确保临时文件夹存在
        os.makedirs(self.temp_folder, exist_ok=True)
    
    async def download_media(self, message: Message, progress_callback=None) -> Optional[str]:
        """
        下载消息中的媒体文件
        
        Args:
            message: 消息对象
            progress_callback: 进度回调函数
        
        Returns:
            Optional[str]: 下载后的文件路径，如果没有媒体则返回None
        """
        if not message.media:
            return None
        
        message_id = message.id
        chat_id = message.chat.id
        
        # 确定媒体类型
        media_type = self._get_media_type(message)
        
        # 获取文件扩展名和原始文件名
        original_file_name = None
        file_extension = ""
        
        if media_type == "photo":
            file_extension = ".jpg"
        elif media_type == "video":
            file_extension = ".mp4"
            if message.video.file_name:
                original_file_name = message.video.file_name
        elif media_type == "audio":
            file_extension = ".mp3"
            if message.audio.file_name:
                original_file_name = message.audio.file_name
        elif media_type == "document":
            if message.document.file_name:
                original_file_name = message.document.file_name
                # 从原文件名获取扩展名
                file_extension = os.path.splitext(original_file_name)[1] or ".doc"
        elif media_type == "animation":
            file_extension = ".gif" if not message.animation.file_name else os.path.splitext(message.animation.file_name)[1]
        elif media_type == "voice":
            file_extension = ".ogg"
        elif media_type == "video_note":
            file_extension = ".mp4"
        elif media_type == "sticker":
            file_extension = ".webp"
        
        # 确定最终文件名
        if original_file_name:
            # 保留原始文件名但添加唯一标识符前缀
            file_name = f"msg{message_id}_{original_file_name}"
        else:
            # 使用唯一标识符和媒体类型命名
            file_name = f"msg{message_id}_{media_type}{file_extension}"
        
        # 确保文件名合法
        file_name = "".join(c for c in file_name if c.isalnum() or c in "._- ")
        
        # 如果文件名太长就截断
        if len(file_name) > 100:
            base, ext = os.path.splitext(file_name)
            file_name = base[:100-len(ext)] + ext
            
        file_path = os.path.join(self.temp_folder, file_name)
        
        try:
            # 使用Pyrogram的下载功能，支持多种媒体类型
            start_time = time.time()
            downloaded_file = await message.download(
                file_name=file_path,
                progress=progress_callback
            )
            
            download_time = time.time() - start_time
            file_size = os.path.getsize(downloaded_file)
            logger.info(f"媒体下载完成: {downloaded_file} ({file_size/1024/1024:.2f} MB, 耗时: {download_time:.2f}秒)")
            
            return downloaded_file
        
        except FloodWait as e:
            logger.warning(f"下载媒体时触发Telegram限流，等待{e.value}秒...")
            await asyncio.sleep(e.value)
            return await self.download_media(message, progress_callback)
        
        except Exception as e:
            logger.error(f"下载媒体时出错: {str(e)}")
            return None
    
    def _get_media_type(self, message: Message) -> Optional[str]:
        """
        获取消息中媒体的类型
        
        Args:
            message: 消息对象
        
        Returns:
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
        elif message.sticker:
            return "sticker"
        elif message.animation:
            return "animation"
        elif message.voice:
            return "voice"
        elif message.video_note:
            return "video_note"
        return None
    
    async def send_media(self, chat_id: Union[str, int], message: Message, file_path: str = None, 
                         progress_callback=None, caption: str = None, hide_author: bool = False) -> Optional[Message]:
        """
        发送媒体文件到目标频道
        
        Args:
            chat_id: 目标频道ID
            message: 原始消息对象
            file_path: 文件路径（如果已下载）
            progress_callback: 进度回调函数
            caption: 消息说明文字
            hide_author: 是否隐藏原作者
        
        Returns:
            Optional[Message]: 发送后的消息对象，发送失败则返回None
        """
        # 如果没有提供文件路径，需要下载媒体
        if not file_path and message.media:
            file_path = await self.download_media(message, progress_callback)
            if not file_path:
                logger.error(f"无法下载媒体文件，消息ID: {message.id}")
                return None
        
        # 如果没有媒体，直接返回None
        if not message.media:
            return None
        
        # 提取说明文字
        if caption is None and message.caption:
            caption = message.caption
        
        # 发送媒体
        media_type = self._get_media_type(message)
        try:
            start_time = time.time()
            
            # 确保使用正确的参数，避免NoneType错误
            common_params = {
                'chat_id': chat_id,
                'caption': caption,
                'parse_mode': 'html'  # 使用HTML解析模式，Telegram默认支持
            }
            
            # 如果提供了进度回调，添加到参数中
            if progress_callback:
                common_params['progress'] = progress_callback
            
            if media_type == "photo":
                new_message = await self.client.client.send_photo(
                    photo=file_path,
                    **common_params
                )
            elif media_type == "video":
                video_params = {}
                if message.video:
                    if hasattr(message.video, 'duration'):
                        video_params['duration'] = message.video.duration
                    if hasattr(message.video, 'width'):
                        video_params['width'] = message.video.width
                    if hasattr(message.video, 'height'):
                        video_params['height'] = message.video.height
                
                new_message = await self.client.client.send_video(
                    video=file_path,
                    **common_params,
                    **video_params
                )
            elif media_type == "audio":
                audio_params = {}
                if message.audio:
                    if hasattr(message.audio, 'duration'):
                        audio_params['duration'] = message.audio.duration
                    if hasattr(message.audio, 'performer'):
                        audio_params['performer'] = message.audio.performer
                    if hasattr(message.audio, 'title'):
                        audio_params['title'] = message.audio.title
                
                new_message = await self.client.client.send_audio(
                    audio=file_path,
                    **common_params,
                    **audio_params
                )
            elif media_type == "document":
                new_message = await self.client.client.send_document(
                    document=file_path,
                    **common_params
                )
            elif media_type == "animation":
                new_message = await self.client.client.send_animation(
                    animation=file_path,
                    **common_params
                )
            elif media_type == "voice":
                new_message = await self.client.client.send_voice(
                    voice=file_path,
                    **common_params
                )
            elif media_type == "video_note":
                new_message = await self.client.client.send_video_note(
                    video_note=file_path,
                    **common_params
                )
            elif media_type == "sticker":
                new_message = await self.client.client.send_sticker(
                    sticker=file_path,
                    **common_params
                )
            else:
                logger.error(f"未知的媒体类型: {media_type}, 消息ID: {message.id}")
                return None
            
            upload_time = time.time() - start_time
            logger.info(f"媒体上传完成，类型: {media_type}, 耗时: {upload_time:.2f}秒")
            
            return new_message
        
        except FloodWait as e:
            logger.warning(f"发送媒体时触发Telegram限流，等待{e.value}秒...")
            await asyncio.sleep(e.value)
            return await self.send_media(chat_id, message, file_path, progress_callback, caption, hide_author)
        
        except Exception as e:
            logger.error(f"发送媒体时出错: {str(e)}")
            return None
        
        finally:
            # 清理临时文件
            if file_path and os.path.exists(file_path):
                try:
                    os.remove(file_path)
                    logger.debug(f"已清理临时文件: {file_path}")
                except Exception as e:
                    logger.warning(f"清理临时文件时出错: {str(e)}")
    
    async def handle_media_group(self, chat_id: Union[str, int], messages: List[Message], 
                                progress_callback=None, hide_author: bool = False) -> List[Optional[Message]]:
        """
        处理媒体组消息
        
        Args:
            chat_id: 目标频道ID
            messages: 原始媒体组消息列表
            progress_callback: 进度回调函数
            hide_author: 是否隐藏原作者
        
        Returns:
            List[Optional[Message]]: 发送后的消息对象列表
        """
        if not messages:
            return []
        
        # 下载所有媒体文件
        downloaded_files = []
        for message in messages:
            file_path = await self.download_media(message, progress_callback)
            if file_path:
                downloaded_files.append((message, file_path))
            else:
                logger.warning(f"媒体组中的消息下载失败，ID: {message.id}")
        
        # 准备发送媒体组
        result_messages = []
        media_types = {self._get_media_type(msg) for msg, _ in downloaded_files}
        
        # 判断是否为混合媒体组
        is_mixed_group = len(media_types) > 1 or None in media_types
        
        try:
            if not is_mixed_group and len(downloaded_files) > 1 and list(media_types)[0] in ["photo", "video", "document"]:
                # 支持同类型媒体组发送
                media_list = []
                for message, file_path in downloaded_files:
                    media_type = self._get_media_type(message)
                    caption = message.caption if message == messages[0] else None
                    
                    if media_type == "photo":
                        media_list.append({"type": "photo", "media": file_path, "caption": caption})
                    elif media_type == "video":
                        media_list.append({"type": "video", "media": file_path, "caption": caption})
                    elif media_type == "document":
                        media_list.append({"type": "document", "media": file_path, "caption": caption})
                
                # 发送媒体组
                sent_messages = await self.client.client.send_media_group(chat_id, media_list)
                result_messages.extend(sent_messages)
            else:
                # 逐个发送媒体
                for message, file_path in downloaded_files:
                    sent_message = await self.send_media(chat_id, message, file_path, progress_callback, message.caption, hide_author)
                    if sent_message:
                        result_messages.append(sent_message)
                    # 添加短暂延迟，防止触发限流
                    await asyncio.sleep(0.5)
            
            return result_messages
        
        except FloodWait as e:
            logger.warning(f"发送媒体组时触发Telegram限流，等待{e.value}秒...")
            await asyncio.sleep(e.value)
            # 递归重试，但需要重新下载文件，因为之前的临时文件可能已被清理
            return await self.handle_media_group(chat_id, messages, progress_callback, hide_author)
        
        except Exception as e:
            logger.error(f"发送媒体组时出错: {str(e)}")
            return result_messages
        
        finally:
            # 清理临时文件
            for _, file_path in downloaded_files:
                if file_path and os.path.exists(file_path):
                    try:
                        os.remove(file_path)
                        logger.debug(f"已清理临时文件: {file_path}")
                    except Exception as e:
                        logger.warning(f"清理临时文件时出错: {str(e)}")
    
    async def forward_media_message(self, source_message: Message, target_chat_id: Union[str, int], 
                                   hide_author: bool = False) -> Optional[Message]:
        """
        转发带媒体的消息到目标频道
        
        Args:
            source_message: 源消息对象
            target_chat_id: 目标频道ID
            hide_author: 是否隐藏原作者
        
        Returns:
            Optional[Message]: 转发后的消息对象，转发失败则返回None
        """
        # 如果消息没有媒体，直接返回None
        if not source_message.media:
            return None
        
        try:
            # 先尝试直接转发
            if not hide_author:
                try:
                    forwarded = await source_message.forward(target_chat_id)
                    logger.info(f"成功直接转发媒体消息 (ID: {source_message.id}) 到 {target_chat_id}")
                    return forwarded
                except Exception as e:
                    logger.warning(f"直接转发媒体消息失败，将尝试下载后重新发送: {str(e)}")
            
            # 如果直接转发失败或需要隐藏作者，则下载后重新发送
            return await self.send_media(
                chat_id=target_chat_id,
                message=source_message,
                file_path=None,  # 将会触发下载
                caption=source_message.caption,
                hide_author=hide_author
            )
        
        except FloodWait as e:
            logger.warning(f"转发媒体消息时触发Telegram限流，等待{e.value}秒...")
            await asyncio.sleep(e.value)
            return await self.forward_media_message(source_message, target_chat_id, hide_author)
        
        except Exception as e:
            logger.error(f"转发媒体消息时出错: {str(e)}")
            return None 