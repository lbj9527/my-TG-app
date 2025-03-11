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
        
        # 初始化下载进度跟踪
        self.download_start_time = {}
        self.download_previous = {}
        self.download_speed = {}
        
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
        
        # 初始化此下载的进度跟踪数据
        msg_id = f"{message.chat.id}_{message.id}"
        self.download_start_time[msg_id] = time.time()
        self.download_previous[msg_id] = (0, time.time())
        self.download_speed[msg_id] = 0
        
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
                
                try:
                    # 下载媒体文件
                    file_path = await message.download(
                        file_name=os.path.join(folder, unique_filename),
                        block=True,
                        progress=self._progress_callback
                    )
                    
                    if file_path:
                        logger.info(f"成功下载媒体文件: {file_path}")
                        # 清理进度跟踪数据
                        if msg_id in self.download_start_time:
                            del self.download_start_time[msg_id]
                        if msg_id in self.download_previous:
                            del self.download_previous[msg_id]
                        if msg_id in self.download_speed:
                            del self.download_speed[msg_id]
                        return file_path
                    else:
                        logger.warning(f"下载媒体文件失败，返回了空路径")
                        retry_count += 1
                except ValueError as e:
                    if "Peer id invalid" in str(e):
                        logger.warning(f"下载时遇到无效的Peer ID错误: {str(e)}，尝试忽略并继续")
                        # 这是与其他线程中的Pyrogram库错误相关，不影响当前下载
                        continue
                    else:
                        raise e
            
            except FloodWait as e:
                logger.warning(f"触发Telegram限流，等待{e.value}秒...")
                await asyncio.sleep(e.value)
                # 不计入重试次数，因为这是Telegram的限制
            
            except Exception as e:
                logger.error(f"下载媒体文件时出错: {str(e)}")
                retry_count += 1
                await asyncio.sleep(2)  # 等待2秒后重试
        
        # 清理进度跟踪数据
        if msg_id in self.download_start_time:
            del self.download_start_time[msg_id]
        if msg_id in self.download_previous:
            del self.download_previous[msg_id]
        if msg_id in self.download_speed:
            del self.download_speed[msg_id]
            
        logger.error(f"媒体文件下载失败，已重试{max_retries}次")
        return None
    
    def _format_size(self, size_bytes: int) -> str:
        """将字节大小转换为人类可读格式"""
        if size_bytes < 1024:
            return f"{size_bytes} B"
        elif size_bytes < 1024 * 1024:
            return f"{size_bytes/1024:.1f} KB"
        elif size_bytes < 1024 * 1024 * 1024:
            return f"{size_bytes/(1024*1024):.1f} MB"
        else:
            return f"{size_bytes/(1024*1024*1024):.1f} GB"
    
    async def _progress_callback(self, current, total):
        """下载进度回调函数"""
        if total <= 0:
            return
            
        # 获取当前正在下载的消息ID
        active_downloads = list(self.download_start_time.keys())
        if not active_downloads:
            return
            
        msg_id = active_downloads[0]
        now = time.time()
        
        # 计算下载速度 (每秒字节数)
        prev_bytes, prev_time = self.download_previous.get(msg_id, (0, now))
        time_diff = now - prev_time
        
        # 保证时间差不为零，避免除零错误
        if time_diff <= 0:
            time_diff = 0.1
        
        try:
            # 每秒更新一次或下载完成时
            if time_diff >= 1.0 or current == total or current % (total // 10) < 100000:
                # 计算下载速度 (字节/秒)
                speed = (current - prev_bytes) / time_diff
                # 避免速度波动太大
                old_speed = self.download_speed.get(msg_id, 0)
                if old_speed > 0:
                    # 平滑处理速度变化
                    speed = old_speed * 0.7 + speed * 0.3
                self.download_speed[msg_id] = speed
                    
                # 更新上一次记录的值
                self.download_previous[msg_id] = (current, now)
                
                # 计算进度百分比
                progress = current / total * 100
                
                # 计算预计剩余时间
                if speed > 0:
                    eta = (total - current) / speed
                    if eta > 3600:
                        eta_str = f"{int(eta // 3600)}时{int((eta % 3600) // 60)}分"
                    elif eta > 60:
                        eta_str = f"{int(eta // 60)}分{int(eta % 60)}秒"
                    else:
                        eta_str = f"{int(eta)}秒"
                else:
                    eta_str = "计算中..."
                
                # 计算已用时间
                elapsed = now - self.download_start_time.get(msg_id, now)
                if elapsed > 3600:
                    elapsed_str = f"{int(elapsed // 3600)}时{int((elapsed % 3600) // 60)}分"
                elif elapsed > 60:
                    elapsed_str = f"{int(elapsed // 60)}分{int(elapsed % 60)}秒"
                else:
                    elapsed_str = f"{int(elapsed)}秒"
                
                # 格式化大小显示
                current_size = self._format_size(current)
                total_size = self._format_size(total)
                speed_str = self._format_size(int(speed)) + "/s"
                
                # 提取文件名
                file_name = msg_id.split('_')[-1] if '_' in msg_id else f"文件{msg_id}"
                file_name_short = file_name[:15] + '...' if len(file_name) > 15 else file_name
                
                # 构建进度信息
                progress_info = (
                    f"下载进度: {progress:.1f}% | "
                    f"{current_size}/{total_size} | "
                    f"速度: {speed_str} | "
                    f"已用: {elapsed_str} | "
                    f"剩余: {eta_str}"
                )
                
                logger.info(progress_info)
        except Exception as e:
            # 确保进度显示错误不会中断下载过程
            logger.error(f"显示下载进度时出错: {str(e)}")
    
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
                try:
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
                except ValueError as e:
                    if "Peer id invalid" in str(e):
                        logger.warning(f"获取文件ID时遇到无效的Peer ID错误，跳过此消息: {msg.id}")
                        continue
                    raise
                
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
            try:
                if msg.media_group_id:
                    if msg.media_group_id not in grouped_messages:
                        grouped_messages[msg.media_group_id] = []
                    grouped_messages[msg.media_group_id].append(msg)
                else:
                    individual_messages.append(msg)
            except ValueError as e:
                if "Peer id invalid" in str(e):
                    logger.warning(f"处理消息分组时遇到无效的Peer ID错误，跳过此消息: {msg.id}")
                    continue
                raise
        
        # 下载媒体组
        for group_id, group_messages in grouped_messages.items():
            try:
                group_results = await self.download_media_group(group_messages)
                for msg_id, file_path in group_results.items():
                    if file_path:
                        # 记录下载的文件路径
                        downloaded_files[msg_id] = file_path
            except ValueError as e:
                if "Peer id invalid" in str(e):
                    logger.warning(f"下载媒体组时遇到无效的Peer ID错误，跳过此组: {group_id}")
                    continue
                raise
            except Exception as e:
                logger.error(f"下载媒体组时出错: {str(e)}")
                continue
        
        # 下载单个消息
        for msg in individual_messages:
            try:
                file_path = await self.download_media_from_message(msg)
                if file_path:
                    downloaded_files[msg.id] = file_path
            except ValueError as e:
                if "Peer id invalid" in str(e):
                    logger.warning(f"下载单个消息时遇到无效的Peer ID错误，跳过此消息: {msg.id}")
                    continue
                raise
            except Exception as e:
                logger.error(f"下载单个消息时出错: {str(e)}")
                continue
        
        # 将下载结果与每个目标频道关联
        for target in forward_results.keys():
            download_results[target] = {}
            for msg in forward_results[target]:
                try:
                    if msg.media and msg.id in downloaded_files:
                        download_results[target][msg.id] = downloaded_files[msg.id]
                    elif msg.media and hasattr(msg, 'media_group_id') and msg.media_group_id and any(m.id in downloaded_files for m in forward_results[target] if hasattr(m, 'media_group_id') and m.media_group_id == msg.media_group_id):
                        # 对于媒体组，找一个已下载的成员
                        for m in forward_results[target]:
                            if hasattr(m, 'media_group_id') and m.media_group_id == msg.media_group_id and m.id in downloaded_files:
                                download_results[target][msg.id] = downloaded_files[m.id]
                                break
                except ValueError as e:
                    if "Peer id invalid" in str(e):
                        logger.warning(f"关联下载结果时遇到无效的Peer ID错误，跳过此消息: {msg.id}")
                        continue
                    raise
                except Exception as e:
                    logger.error(f"关联下载结果时出错: {str(e)}, 消息ID: {msg.id}")
                    continue
        
        # 统计下载结果
        total_unique_files = len(all_messages)
        total_success = len([f for f in downloaded_files.values() if f is not None])
        
        logger.info(f"媒体下载完成: 共 {total_unique_files} 个唯一文件, 成功下载 {total_success} 个")
        
        return download_results 