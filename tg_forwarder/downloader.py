"""
媒体下载模块，负责下载Telegram消息中的媒体文件
"""

import os
import asyncio
import time
import re
import sys
from typing import Dict, Any, Optional, List, Union, Tuple
from pyrogram.types import Message
from pyrogram.errors import FloodWait

# 引入colorama库支持彩色终端输出
try:
    from colorama import init, Fore, Back, Style
    init(autoreset=True)  # 初始化colorama，自动重置颜色
    COLORAMA_AVAILABLE = True
except ImportError:
    print("提示: 未安装colorama库，将不会显示彩色输出。可运行 'pip install colorama' 安装。")
    COLORAMA_AVAILABLE = False
    # 创建空的颜色类，避免报错
    class DummyFore:
        def __getattr__(self, name):
            return ""
    class DummyBack:
        def __getattr__(self, name):
            return ""
    class DummyStyle:
        def __getattr__(self, name):
            return ""
    Fore = DummyFore()
    Back = DummyBack()
    Style = DummyStyle()

# 引入tqdm库支持更专业的终端进度条
try:
    from tqdm import tqdm
    from tqdm.asyncio import tqdm as atqdm
    TQDM_AVAILABLE = True
except ImportError:
    print("提示: 未安装tqdm库，将不会显示进度条。可运行 'pip install tqdm' 安装。")
    TQDM_AVAILABLE = False

# 定义彩色进度条格式
if TQDM_AVAILABLE and COLORAMA_AVAILABLE:
    # 文件总进度条格式
    TOTAL_BAR_FORMAT = (f"{Fore.CYAN}{{desc}}{Style.RESET_ALL}: "
                        f"{Fore.BLUE}{{percentage:3.1f}}%{Style.RESET_ALL}|"
                        f"{Fore.GREEN}{{bar}}{Style.RESET_ALL}| "
                        f"{Fore.YELLOW}{{n_fmt}}{Style.RESET_ALL}/{Fore.YELLOW}{{total_fmt}}{Style.RESET_ALL} "
                        f"[{Fore.MAGENTA}{{elapsed}}{Style.RESET_ALL}<{Fore.MAGENTA}{{remaining}}{Style.RESET_ALL}, "
                        f"{Fore.CYAN}{{rate_fmt}}{Style.RESET_ALL}]")
    
    # 当前文件进度条格式
    FILE_BAR_FORMAT = (f"{Fore.GREEN}{{desc}}{Style.RESET_ALL}: "
                      f"{Fore.YELLOW}{{percentage:3.1f}}%{Style.RESET_ALL}|"
                      f"{Fore.BLUE}{{bar}}{Style.RESET_ALL}| "
                      f"{Fore.CYAN}{{n_fmt}}{Style.RESET_ALL}/{Fore.CYAN}{{total_fmt}}{Style.RESET_ALL} "
                      f"[{Fore.MAGENTA}{{elapsed}}{Style.RESET_ALL}<{Fore.MAGENTA}{{remaining}}{Style.RESET_ALL}, "
                      f"{Fore.GREEN}{{rate_fmt}}{Style.RESET_ALL}]")
    
    # 批次进度条格式
    BATCH_BAR_FORMAT = (f"{Fore.YELLOW}{{desc}}{Style.RESET_ALL}: "
                       f"{Fore.CYAN}{{percentage:3.1f}}%{Style.RESET_ALL}|"
                       f"{Fore.MAGENTA}{{bar}}{Style.RESET_ALL}| "
                       f"{Fore.GREEN}{{n_fmt}}{Style.RESET_ALL}/{Fore.GREEN}{{total_fmt}}{Style.RESET_ALL} "
                       f"[{Fore.BLUE}{{elapsed}}{Style.RESET_ALL}<{Fore.BLUE}{{remaining}}{Style.RESET_ALL}]")
    
    # 等待进度条格式                  
    WAIT_BAR_FORMAT = (f"{Fore.RED}{{desc}}{Style.RESET_ALL}: "
                      f"{Fore.YELLOW}{{remaining}}s{Style.RESET_ALL}")
else:
    TOTAL_BAR_FORMAT = '{desc}: {percentage:3.1f}%|{bar}| {n_fmt}/{total_fmt} [{elapsed}<{remaining}, {rate_fmt}]'
    FILE_BAR_FORMAT = '{desc}: {percentage:3.1f}%|{bar}| {n_fmt}/{total_fmt} [{elapsed}<{remaining}, {rate_fmt}]'
    BATCH_BAR_FORMAT = '{desc}: {percentage:3.1f}%|{bar}| {n_fmt}/{total_fmt} [{elapsed}<{remaining}]'
    WAIT_BAR_FORMAT = '{desc}: {remaining}s'

from tg_forwarder.utils.logger import get_logger
from tg_forwarder.utils.common import format_size, format_time, get_client_instance

# 自定义彩色日志格式
class ColoredFormatter:
    """自定义彩色日志格式器"""
    
    def __init__(self, logger):
        self.logger = logger
    
    def info(self, message):
        if COLORAMA_AVAILABLE:
            if "下载进度" in message:
                self.logger.info(f"{Fore.CYAN}📥 {message}{Style.RESET_ALL}")
            elif "成功下载" in message:
                self.logger.info(f"{Fore.GREEN}✅ {message}{Style.RESET_ALL}")
            elif "媒体下载统计" in message:
                self.logger.info(f"{Fore.GREEN}{Style.BRIGHT}🎉 {message}{Style.RESET_ALL}")
            elif "开始下载" in message:
                self.logger.info(f"{Fore.YELLOW}📥 {message}{Style.RESET_ALL}")
            elif "找到" in message or "获取" in message:
                self.logger.info(f"{Fore.CYAN}🔍 {message}{Style.RESET_ALL}")
            elif "准备下载" in message:
                self.logger.info(f"{Fore.YELLOW}📋 {message}{Style.RESET_ALL}")
            else:
                self.logger.info(f"{Fore.WHITE}ℹ️ {message}{Style.RESET_ALL}")
        else:
            self.logger.info(message)
    
    def warning(self, message):
        if COLORAMA_AVAILABLE:
            self.logger.warning(f"{Fore.YELLOW}{Style.BRIGHT}⚠️ {message}{Style.RESET_ALL}")
        else:
            self.logger.warning(message)
    
    def error(self, message):
        if COLORAMA_AVAILABLE:
            self.logger.error(f"{Fore.RED}{Style.BRIGHT}❌ {message}{Style.RESET_ALL}")
        else:
            self.logger.error(message)
    
    def critical(self, message):
        if COLORAMA_AVAILABLE:
            self.logger.critical(f"{Back.RED}{Fore.WHITE}{Style.BRIGHT}🚨 {message}{Style.RESET_ALL}")
        else:
            self.logger.critical(message)

# 获取原始日志记录器
_logger = get_logger("downloader")
# 创建彩色日志包装器
logger = ColoredFormatter(_logger)

class DownloadProgressTracker:
    """下载进度跟踪器，使用tqdm实现专业的终端进度条"""
    
    def __init__(self, file_name: str, file_size: int):
        self.file_name = file_name
        self.file_size = file_size
        self.start_time = time.time()
        self.pbar = None
        
        # 简化文件名显示
        self.short_name = file_name
        if len(self.short_name) > 20:
            self.short_name = self.short_name[:17] + "..."
        
        # 初始化进度条
        if TQDM_AVAILABLE:
            # 彩色文件名前缀
            if COLORAMA_AVAILABLE:
                file_desc = f"{Fore.GREEN}下载: {self.short_name}{Style.RESET_ALL}"
            else:
                file_desc = f"下载: {self.short_name}"
                
            self.pbar = tqdm(
                total=file_size,
                unit='B',
                unit_scale=True,
                desc=file_desc,
                position=0,
                leave=True,
                bar_format=FILE_BAR_FORMAT,
                colour='blue' if not COLORAMA_AVAILABLE else None
            )
    
    def update(self, current: int):
        """更新当前文件下载进度"""
        if TQDM_AVAILABLE and self.pbar:
            # 获取当前位置
            last_n = self.pbar.n
            # 更新进度条(设置增量)
            self.pbar.update(current - last_n)
    
    def close(self, success: bool = True):
        """关闭进度条并显示完成信息"""
        if TQDM_AVAILABLE and self.pbar:
            self.pbar.close()
            
        elapsed = time.time() - self.start_time
        speed = self.file_size / elapsed if elapsed > 0 and self.file_size > 0 else 0
        
        if success:
            # 输出完成信息
            if COLORAMA_AVAILABLE:
                logger.info(
                    f"{Fore.GREEN}文件下载完成: {self.short_name} | "
                    f"大小: {format_size(self.file_size)} | "
                    f"用时: {Fore.CYAN}{elapsed:.2f}秒{Style.RESET_ALL} | "
                    f"平均速度: {Fore.YELLOW}{format_size(speed)}/s{Style.RESET_ALL}"
                )
            else:
                logger.info(
                    f"文件下载完成: {self.short_name} | "
                    f"大小: {format_size(self.file_size)} | "
                    f"用时: {elapsed:.2f}秒 | "
                    f"平均速度: {format_size(speed)}/s"
                )

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
        self.active_trackers = {}
        
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
        
        # 获取原始文件名（如果有）
        original_filename = None
        file_size = 0
        
        if message.photo:
            original_filename = f"{message.photo.file_unique_id}"
            file_size = message.photo.file_size or 0
        elif message.video:
            original_filename = message.video.file_name
            file_size = message.video.file_size or 0
        elif message.audio:
            original_filename = message.audio.file_name
            file_size = message.audio.file_size or 0
        elif message.voice:
            original_filename = message.voice.file_name
            file_size = message.voice.file_size or 0
        elif message.document:
            original_filename = message.document.file_name
            file_size = message.document.file_size or 0
        
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
            
        # 创建唯一的消息标识
        msg_id = f"{message.chat.id}_{message.id}"
        
        # 如果已有正在下载的同一个文件，返回None防止重复下载
        if msg_id in self.active_trackers:
            logger.warning(f"文件 {unique_filename} 已在下载队列中，跳过")
            return None
            
        # 创建进度跟踪器
        tracker = DownloadProgressTracker(unique_filename, file_size)
        self.active_trackers[msg_id] = tracker
        
        if COLORAMA_AVAILABLE:
            logger.info(f"{Fore.CYAN}开始下载: {unique_filename} ({format_size(file_size)}){Style.RESET_ALL}")
        else:
            logger.info(f"开始下载: {unique_filename} ({format_size(file_size)})")
        
        try:
            while retry_count < max_retries:
                try:
                    try:
                        # 下载媒体文件
                        file_path = await message.download(
                            file_name=os.path.join(folder, unique_filename),
                            block=True,
                            progress=self._progress_callback
                        )
                        
                        if file_path:
                            logger.info(f"成功下载媒体文件: {file_path}")
                            # 关闭进度跟踪器
                            if msg_id in self.active_trackers:
                                self.active_trackers[msg_id].close(True)
                                del self.active_trackers[msg_id]
                            return file_path
                        else:
                            logger.warning(f"下载媒体文件失败，返回了空路径")
                            retry_count += 1
                    except ValueError as e:
                        if "Peer id invalid" in str(e):
                            # 这是与其他线程中的Pyrogram库错误相关
                            peer_id = re.search(r"Peer id invalid: (.*)", str(e))
                            peer_info = peer_id.group(1) if peer_id else "未知ID"
                            
                            if COLORAMA_AVAILABLE:
                                logger.warning(f"下载时遇到无效的Peer ID: {Fore.CYAN}{peer_info}{Style.RESET_ALL}，尝试忽略并继续")
                            else:
                                logger.warning(f"下载时遇到无效的Peer ID: {peer_info}，尝试忽略并继续")
                            continue
                        else:
                            raise e
                
                except FloodWait as e:
                    # 遇到Telegram限流
                    logger.warning(f"触发Telegram限流，等待{e.value}秒...")
                    
                    # 使用tqdm显示等待倒计时
                    if TQDM_AVAILABLE:
                        wait_desc = "等待限制解除" if not COLORAMA_AVAILABLE else f"{Fore.RED}等待限制解除{Style.RESET_ALL}"
                        with tqdm(total=e.value, desc=wait_desc, unit="秒", 
                                bar_format=WAIT_BAR_FORMAT,
                                colour='red' if not COLORAMA_AVAILABLE else None) as wait_pbar:
                            for _ in range(e.value):
                                await asyncio.sleep(1)
                                wait_pbar.update(1)
                    else:
                        await asyncio.sleep(e.value)
                    
                    # 不计入重试次数，因为这是Telegram的限制
                
                except Exception as e:
                    logger.error(f"下载媒体文件时出错: {str(e)}")
                    retry_count += 1
                    await asyncio.sleep(2)  # 等待2秒后重试
        
        finally:
            # 确保关闭进度跟踪器
            if msg_id in self.active_trackers:
                self.active_trackers[msg_id].close(False)
                del self.active_trackers[msg_id]
                
        if retry_count >= max_retries:
            logger.error(f"媒体文件下载失败，已重试{max_retries}次")
            
        return None
    
    async def _progress_callback(self, current, total):
        """下载进度回调函数"""
        if total <= 0:
            return
            
        # 获取当前正在下载的消息ID
        active_downloads = list(self.active_trackers.keys())
        if not active_downloads:
            return
            
        msg_id = active_downloads[0]
        tracker = self.active_trackers.get(msg_id)
        
        if tracker:
            tracker.update(current)
    
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
        
        # 显示文件总数和大小
        total_size = sum(self._get_media_size(msg) for msg in messages if msg.media)
        
        if COLORAMA_AVAILABLE:
            logger.info(
                f"{Fore.YELLOW}准备下载 {len(messages)} 个文件 "
                f"(总大小: {Fore.CYAN}{format_size(total_size)}{Style.RESET_ALL}{Fore.YELLOW})"
            )
        else:
            logger.info(f"准备下载 {len(messages)} 个文件 (总大小: {format_size(total_size)})")
        
        # 创建总进度条
        total_pbar = None
        if TQDM_AVAILABLE and len(messages) > 1:
            total_desc = f"总进度" if not COLORAMA_AVAILABLE else f"{Fore.CYAN}总进度{Style.RESET_ALL}"
            total_pbar = tqdm(
                total=len(messages),
                unit='个',
                desc=total_desc,
                position=1,
                leave=True,
                bar_format=TOTAL_BAR_FORMAT,
                colour='green' if not COLORAMA_AVAILABLE else None
            )
        
        try:
            for i, message in enumerate(messages):
                file_path = await self.download_media_from_message(message)
                results[message.id] = file_path
                
                # 更新总进度条
                if total_pbar:
                    total_pbar.update(1)
                    
                # 每下载5个文件或最后一个文件时显示进度信息
                if (i + 1) % 5 == 0 or i == len(messages) - 1:
                    success_count = sum(1 for path in results.values() if path is not None)
                    if COLORAMA_AVAILABLE:
                        logger.info(
                            f"{Fore.CYAN}下载进度: {success_count}/{len(messages)} 文件完成 "
                            f"({Fore.YELLOW}{success_count/len(messages)*100:.1f}%{Style.RESET_ALL})"
                        )
                    else:
                        logger.info(f"下载进度: {success_count}/{len(messages)} 文件完成 ({success_count/len(messages)*100:.1f}%)")
        
        finally:
            # 关闭总进度条
            if total_pbar:
                total_pbar.close()
        
        # 输出统计结果
        success_count = sum(1 for path in results.values() if path is not None)
        
        if COLORAMA_AVAILABLE:
            logger.info(
                f"{Fore.GREEN}{Style.BRIGHT}媒体下载统计: 总共 {Fore.YELLOW}{len(messages)}{Style.RESET_ALL}"
                f"{Fore.GREEN}{Style.BRIGHT} 个文件, 成功 {Fore.CYAN}{success_count}{Style.RESET_ALL}"
                f"{Fore.GREEN}{Style.BRIGHT} 个 ({Fore.YELLOW}{success_count/len(messages)*100:.1f}%{Style.RESET_ALL}"
                f"{Fore.GREEN}{Style.BRIGHT} 完成率){Style.RESET_ALL}"
            )
        else:
            logger.info(f"媒体下载统计: 总共 {len(messages)} 个文件, 成功 {success_count} 个 ({success_count/len(messages)*100:.1f}% 完成率)")
        
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
    
    def _get_media_size(self, message: Message) -> int:
        """获取媒体文件大小"""
        if message.photo:
            return message.photo.file_size or 0
        elif message.video:
            return message.video.file_size or 0
        elif message.audio:
            return message.audio.file_size or 0
        elif message.voice:
            return message.voice.file_size or 0
        elif message.document:
            return message.document.file_size or 0
        elif message.animation:
            return message.animation.file_size or 0
        elif message.video_note:
            return message.video_note.file_size or 0
        return 0
    
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
        
        if COLORAMA_AVAILABLE:
            logger.info(f"{Fore.CYAN}{Style.BRIGHT}开始下载媒体组 (组ID: {media_group[0].media_group_id}), 共 {len(media_group)} 个文件{Style.RESET_ALL}")
        else:
            logger.info(f"开始下载媒体组 (组ID: {media_group[0].media_group_id}), 共 {len(media_group)} 个文件")
            
        return await self.download_media_from_messages(media_group)
    
    async def download_forwarded_messages(self, forward_results: Dict[str, List[Message]]) -> Dict[str, Dict[int, Optional[str]]]:
        """
        下载已转发的消息中的媒体文件
        
        Args:
            forward_results: 转发结果字典，键为目标聊天ID，值为消息列表
            
        Returns:
            Dict[str, Dict[int, Optional[str]]]: 下载结果
        """
        result = {}
        
        # 计算所有文件的总数和总大小
        total_messages = sum(len(messages) for messages in forward_results.values())
        total_size = 0
        for chat_id, messages in forward_results.items():
            for msg in messages:
                total_size += self._get_media_size(msg)
        
        if COLORAMA_AVAILABLE:
            logger.info(
                f"{Fore.YELLOW}准备下载 {total_messages} 个文件 "
                f"(总大小: {Fore.CYAN}{format_size(total_size)}{Style.RESET_ALL}{Fore.YELLOW})"
            )
        else:
            logger.info(f"准备下载 {total_messages} 个文件 (总大小: {format_size(total_size)})")
        
        for chat_id, messages in forward_results.items():
            chat_result = {}
            if COLORAMA_AVAILABLE:
                logger.info(f"{Fore.CYAN}准备下载聊天 {chat_id} 中的 {len(messages)} 条消息的媒体...{Style.RESET_ALL}")
            else:
                logger.info(f"准备下载聊天 {chat_id} 中的 {len(messages)} 条消息的媒体...")
            
            # 按媒体组分组
            media_groups = {}
            single_messages = []
            
            for msg in messages:
                if msg.media_group_id:
                    if msg.media_group_id not in media_groups:
                        media_groups[msg.media_group_id] = []
                    media_groups[msg.media_group_id].append(msg)
                else:
                    single_messages.append(msg)
            
            # 下载媒体组消息
            for group_id, group_messages in media_groups.items():
                group_results = await self.download_media_group(group_messages)
                chat_result.update(group_results)
            
            # 下载单独消息
            for msg in single_messages:
                file_path = await self.download_media_from_message(msg)
                chat_result[msg.id] = file_path
            
            result[chat_id] = chat_result
        
        return result
    
    async def download_messages_from_source(self, source_chat_id, start_message_id, end_message_id) -> Dict[int, Optional[str]]:
        """
        直接从源频道下载指定范围内的媒体消息
        
        Args:
            source_chat_id: 源聊天/频道的ID
            start_message_id: 起始消息ID
            end_message_id: 结束消息ID
            
        Returns:
            Dict[int, Optional[str]]: 消息ID到下载文件路径的映射
        """
        result = {}
        
        try:
            if COLORAMA_AVAILABLE:
                logger.info(f"{Fore.CYAN}准备从源频道 {source_chat_id} 下载消息范围 {start_message_id} 到 {end_message_id} 的媒体...{Style.RESET_ALL}")
            else:
                logger.info(f"准备从源频道 {source_chat_id} 下载消息范围 {start_message_id} 到 {end_message_id} 的媒体...")
            
            # 设置默认的结束消息ID
            if not end_message_id or end_message_id <= 0:
                # 获取最新消息ID
                latest_id = await self.client.get_latest_message_id(source_chat_id)
                if not latest_id:
                    logger.error(f"无法获取源频道的最新消息ID: {source_chat_id}")
                    return result
                
                end_message_id = latest_id
                logger.info(f"已获取最新消息ID作为结束ID: {end_message_id}")
            
            # 设置默认的起始消息ID
            if not start_message_id or start_message_id <= 0:
                # 如果没有指定起始ID，使用默认值（最新消息ID - 8）
                start_message_id = max(1, end_message_id - 8)
                logger.info(f"未指定起始消息ID，将从ID={start_message_id}开始")
            
            # 消息ID列表
            message_ids = list(range(start_message_id, end_message_id + 1))
            total_messages = len(message_ids)
            
            # 媒体组消息的缓存，避免重复处理
            processed_media_groups = set()
            
            # 使用get_messages_range方法获取消息
            try:
                logger.info(f"获取消息范围: {start_message_id}-{end_message_id}")
                messages = await self.client.get_messages_range(source_chat_id, start_message_id, end_message_id)
                
                # 按媒体组分组
                media_groups = {}
                single_messages = []
                
                for msg in messages:
                    # 跳过非媒体消息
                    if not msg or not self._get_media_type(msg):
                        continue
                        
                    # 处理媒体组消息
                    if msg.media_group_id:
                        if msg.media_group_id not in processed_media_groups:
                            if msg.media_group_id not in media_groups:
                                media_groups[msg.media_group_id] = []
                            media_groups[msg.media_group_id].append(msg)
                    else:
                        single_messages.append(msg)
                
                # 处理媒体组
                for group_id, group_messages in media_groups.items():
                    try:
                        if COLORAMA_AVAILABLE:
                            logger.info(f"{Fore.YELLOW}下载媒体组 {group_id} 中的 {len(group_messages)} 个媒体文件{Style.RESET_ALL}")
                        else:
                            logger.info(f"下载媒体组 {group_id} 中的 {len(group_messages)} 个媒体文件")
                            
                        # 直接使用已获取的媒体组消息
                        group_results = await self.download_media_group(group_messages)
                        result.update(group_results)
                        processed_media_groups.add(group_id)
                    except Exception as e:
                        logger.error(f"下载媒体组 {group_id} 时出错: {str(e)}")
                
                # 下载单独消息
                for msg in single_messages:
                    try:
                        file_path = await self.download_media_from_message(msg)
                        if file_path:
                            result[msg.id] = file_path
                    except Exception as e:
                        logger.error(f"下载消息 {msg.id} 时出错: {str(e)}")
            
            except Exception as e:
                logger.error(f"获取消息范围时出错: {str(e)}")
        
        except Exception as e:
            logger.error(f"从源频道下载消息时出错: {str(e)}")
        
        # 统计下载结果
        success_count = sum(1 for path in result.values() if path)
        
        if COLORAMA_AVAILABLE:
            logger.info(
                f"{Fore.GREEN}{Style.BRIGHT}从源频道下载完成。总消息数: {Fore.YELLOW}{total_messages}{Style.RESET_ALL}"
                f"{Fore.GREEN}{Style.BRIGHT}，成功下载媒体: {Fore.CYAN}{success_count}{Style.RESET_ALL}"
            )
        else:
            logger.info(f"从源频道下载完成。总消息数: {total_messages}，成功下载媒体: {success_count}")
        
        return result 