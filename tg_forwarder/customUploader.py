#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import time
import asyncio
import logging
import configparser
import mimetypes
import re
import sys
import tempfile
import contextlib
from typing import List, Dict, Tuple, Any, Optional, Callable
from datetime import datetime

from pyrogram import Client
from pyrogram.types import InputMediaPhoto, InputMediaVideo, InputMediaDocument, Message
from pyrogram.errors import FloodWait

# 添加moviepy导入
try:
    # 告诉IDE忽略这个导入错误
    # type: ignore
    from moviepy import VideoFileClip
    MOVIEPY_AVAILABLE = True
except ImportError:
    print("提示: 未安装moviepy库，将无法生成视频缩略图。可运行 'pip install moviepy' 安装。")
    MOVIEPY_AVAILABLE = False

# 从公共模块导入工具函数
from tg_forwarder.utils.common import format_size, format_time, get_client_instance
# 导入频道解析工具
from tg_forwarder.channel_parser import ChannelParser, ChannelValidator

# 删除colorama导入，只保留tqdm
try:
    from tqdm import tqdm
    from tqdm.asyncio import tqdm as atqdm
    TQDM_AVAILABLE = True
except ImportError:
    print("提示: 未安装tqdm库，将不会显示进度条。可运行 'pip install tqdm' 安装。")
    TQDM_AVAILABLE = False

# 定义进度条格式 - 统一使用非彩色格式
TOTAL_BAR_FORMAT = '{desc}: {percentage:3.1f}%|{bar}| {n_fmt}/{total_fmt} [{elapsed}<{remaining}, {rate_fmt}]'
FILE_BAR_FORMAT = '{desc}: {percentage:3.1f}%|{bar}| {n_fmt}/{total_fmt} [{elapsed}<{remaining}, {rate_fmt}]'
BATCH_BAR_FORMAT = '{desc}: {percentage:3.1f}%|{bar}| {n_fmt}/{total_fmt} [{elapsed}<{remaining}]'
WAIT_BAR_FORMAT = '{desc}: {remaining}s'

# 重定向错误输出，隐藏Pyrogram的详细错误信息
class ErrorFilter(logging.Filter):
    def filter(self, record):
        # 过滤掉常见的非关键性日志
        if isinstance(record.msg, str):
            msg_lower = record.msg.lower()
            
            # 过滤常见错误
            if ("peer id invalid" in msg_lower or 
                "task exception was never retrieved" in msg_lower):
                return False
                
            # 过滤媒体处理的非错误日志
            if record.levelno < logging.WARNING:
                if ("开始为视频生成缩略图" in record.msg or
                    "缩略图已存在" in record.msg or
                    "成功使用ffmpeg" in msg_lower or
                    "尝试使用moviepy" in msg_lower or
                    "生成视频缩略图" in msg_lower or
                    "使用缩略图" in record.msg or
                    "文件下载完成" in record.msg or
                    "开始下载" in record.msg and not "失败" in record.msg or
                    "上传图片" in record.msg or
                    "上传文档" in record.msg or
                    "开始上传视频" in record.msg or
                    "视频作为文档上传成功" in record.msg or
                    "视频上传成功" in record.msg):
                    return False
        
        return True

# 过滤媒体处理的非关键输出
class MediaFilter(logging.Filter):
    """过滤掉FFmpeg、MoviePy等媒体处理的详细输出"""
    
    def filter(self, record):
        if not isinstance(record.msg, str):
            return True
            
        msg_lower = str(record.msg).lower()
        
        # 只过滤非警告/错误日志
        if record.levelno < logging.WARNING:
            # 过滤媒体工具输出
            media_patterns = [
                'ffmpeg', 'avcodec', 'libav', 'moviepy', 'imageio',
                'duration=', 'video:', 'audio:', 'stream mapping',
                'frame=', 'fps=', 'bitrate=', 'time=', 'size=',
                'converting', 'processed', 'image sequence',
                '开始处理文件', '处理批次', '媒体上传', '视频转码'
            ]
            
            # 过滤进度相关输出
            progress_patterns = [
                '进度:', '进度条', '总进度', '文件进度', 
                '处理进度', '下载进度', '上传进度',
                '正在上传', '正在下载', '正在处理'
            ]
            
            # 过滤文件操作详情
            file_patterns = [
                '生成缩略图', '成功下载', '开始下载', '文件已存在',
                '文件大小', '上传文件', '统计信息', '文件下载完成'
            ]
            
            # 检查是否包含任何需要过滤的模式
            for pattern_list in [media_patterns, progress_patterns, file_patterns]:
                for pattern in pattern_list:
                    if pattern in msg_lower and '失败' not in msg_lower and '错误' not in msg_lower:
                        return False
        
        return True

# 替换彩色日志格式为简单格式，并添加日志过滤功能
class SimpleFormatter(logging.Formatter):
    """简化的日志格式器，只显示关键信息"""
    
    def format(self, record):
        levelname = record.levelname
        message = record.getMessage()
        
        # 关键字过滤，只保留与上传、转发、速度和进度相关的日志
        # 检查是否包含关键字
        keywords = [
            "文件完成", "全部完成", "速度", "进度", 
            "成功转发", "媒体组发送完成", "频道转发", 
            "允许转发", "禁止转发", "USERNAME_NOT_OCCUPIED",
            "CHAT_FORWARDS_RESTRICTED", "频道名", "频道ID",
            "验证成功", "验证失败", "有效频道", "无效频道",
            "上传完成", "转发消息", "转发失败", "发送失败",
            "下载完成", "上传媒体", "上传视频"
        ]
        
        # 如果是警告或错误，始终显示
        if record.levelno >= logging.WARNING:
            pass  # 不做过滤，保留所有警告和错误日志
        else:
            # 对于INFO级别日志，过滤掉非关键信息
            has_keyword = any(keyword in message for keyword in keywords)
            if not has_keyword:
                # 对非关键INFO日志，简化显示
                if len(message) > 60:
                    message = message[:57] + "..."
        
        # 删除ANSI颜色代码
        import re
        ansi_escape = re.compile(r'\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])')
        message = ansi_escape.sub('', message)
        
        # 创建最终日志消息
        formatted_message = f"{message}"
        
        return formatted_message

# 设置日志记录
# 在创建日志之前，先重置根日志配置
for handler in logging.root.handlers[:]:
    logging.root.removeHandler(handler)

# 创建日志记录器
logger = logging.getLogger("CustomMediaGroupSender")
logger.setLevel(logging.INFO)
# 防止日志传播到根日志记录器
logger.propagate = False

# 清除所有已有处理器
for handler in logger.handlers[:]:
    logger.removeHandler(handler)

# 添加处理器 - 简化日志格式，去掉logger名称
handler = logging.StreamHandler()
handler.setFormatter(SimpleFormatter('%(asctime)s - %(levelname)s - %(message)s'))
logger.addHandler(handler)

# 添加媒体过滤器，减少非关键输出
media_filter = MediaFilter()
logger.addFilter(media_filter)
logging.getLogger().addFilter(media_filter)  # 添加到根日志记录器

# 设置 pyrogram 的日志级别为 ERROR，减少连接和错误信息输出
logging.getLogger("pyrogram").setLevel(logging.ERROR)
logging.getLogger("pyrogram.session").setLevel(logging.ERROR)
logging.getLogger("pyrogram.connection").setLevel(logging.ERROR)
logging.getLogger("pyrogram.dispatcher").setLevel(logging.ERROR)

# 为asyncio添加过滤器，隐藏未处理的任务异常
asyncio_logger = logging.getLogger("asyncio")
asyncio_logger.setLevel(logging.ERROR)
asyncio_logger.addFilter(ErrorFilter())

# 为pyrogram添加过滤器
pyrogram_logger = logging.getLogger("pyrogram")
pyrogram_logger.addFilter(ErrorFilter())

# 改进异常处理函数
def custom_excepthook(exc_type, exc_value, exc_traceback):
    if issubclass(exc_type, KeyboardInterrupt):
        # 正常处理键盘中断
        print("\n⚠️ 程序被用户中断")
        return
    
    # 过滤掉特定的Pyrogram错误
    error_msg = str(exc_value)
    if "Peer id invalid" in error_msg:
        # 不显示频道ID解析错误
        return
    elif "CHAT_FORWARDS_RESTRICTED" in error_msg:
        print(f"⚠️ 频道限制转发: {error_msg}")
        print(f"💡 程序将尝试使用copy_message/copy_media_group替代转发")
    else:
        # 对其他错误进行简化处理
        error_type = exc_type.__name__
        print(f"❌ 错误类型: {error_type}")
        print(f"❌ 错误信息: {error_msg}")
        print(f"💡 使用 --debug 参数运行可查看详细错误跟踪")
            
        # 只有在debug模式下才显示完整堆栈信息
        if "--debug" in sys.argv:
            sys.__excepthook__(exc_type, exc_value, exc_traceback)

# 设置自定义异常处理器
sys.excepthook = custom_excepthook

class UploadProgressTracker:
    """上传进度跟踪器，使用tqdm实现专业的终端进度条"""
    def __init__(self, total_files: int, total_size: int):
        self.total_files = total_files
        self.total_size = total_size
        self.uploaded_files = 0
        self.uploaded_size = 0
        self.start_time = time.time()
        self.current_file = ""
        self.current_file_size = 0
        self.file_start_time = time.time()
        
        # 总进度条
        self.total_pbar = None
        # 当前文件进度条
        self.current_pbar = None
        
        # 初始化总进度条
        if TQDM_AVAILABLE:
            # 简化总进度前缀
            total_desc = "总进度"
            
            self.total_pbar = tqdm(
                total=total_size,
                unit='B',
                unit_scale=True,
                desc=total_desc,
                position=0,
                leave=True,
                bar_format=TOTAL_BAR_FORMAT,
                colour='green'
            )
        
    def start_file(self, file_name: str, file_size: int):
        """开始上传新文件"""
        self.current_file = file_name
        self.current_file_size = file_size
        self.file_start_time = time.time()
        
        # 简化文件名显示
        short_name = file_name
        if len(short_name) > 20:
            short_name = short_name[:17] + "..."
        
        # 不输出开始上传日志，减少日志输出
        
        # 创建当前文件的进度条
        if TQDM_AVAILABLE:
            # 如果之前有进度条，先关闭
            if self.current_pbar is not None:
                self.current_pbar.close()
                
            # 创建新的文件进度条
            file_desc = f"文件: {short_name}"
                
            self.current_pbar = tqdm(
                total=file_size,
                unit='B',
                unit_scale=True,
                desc=file_desc,
                position=1,
                leave=True,
                bar_format=FILE_BAR_FORMAT,
                colour='blue'
            )
        
    def update_progress(self, current: int, total: int):
        """更新当前文件上传进度"""
        if TQDM_AVAILABLE:
            # 计算增量进度
            if self.current_pbar is not None:
                # 获取当前位置
                last_n = self.current_pbar.n
                # 更新当前文件进度条(设置绝对值)
                self.current_pbar.update(current - last_n)
                
            # 更新总进度条
            if self.total_pbar is not None:
                last_total_n = self.total_pbar.n
                # 计算总进度，上传完成的文件大小+当前文件进度
                current_total = self.uploaded_size + current
                # 更新总进度条(设置增量)
                self.total_pbar.update(current_total - last_total_n)
    
    def complete_file(self):
        """完成当前文件上传"""
        self.uploaded_files += 1
        self.uploaded_size += self.current_file_size
        elapsed = time.time() - self.file_start_time
        speed = self.current_file_size / elapsed if elapsed > 0 else 0
        
        # 关闭当前文件的进度条
        if TQDM_AVAILABLE and self.current_pbar is not None:
            self.current_pbar.close()
            self.current_pbar = None
        
        # 简化文件名显示
        short_name = self.current_file
        if len(short_name) > 20:
            short_name = short_name[:17] + "..."
        
        # 只输出速度和进度信息
        logger.info(
            f"文件完成: {short_name} | "
            f"速度: {format_size(speed)}/s | "
            f"进度: {self.uploaded_files}/{self.total_files}文件"
        )
    
    def complete_all(self):
        """完成所有文件上传"""
        total_elapsed = time.time() - self.start_time
        avg_speed = self.uploaded_size / total_elapsed if total_elapsed > 0 else 0
        
        # 关闭总进度条
        if TQDM_AVAILABLE and self.total_pbar is not None:
            self.total_pbar.close()
            self.total_pbar = None
            
        # 只输出总体速度信息
        logger.info(
            f"全部完成 | "
            f"共 {self.uploaded_files} 个文件 | "
            f"总速度: {format_size(avg_speed)}/s"
        )

class CustomMediaGroupSender:
    """自定义媒体组发送器，支持带进度显示的媒体组发送"""
    
    def __init__(self, client: Client, config_parser=None, target_channels: List[str] = None, temp_folder: str = None, 
                channel_forward_status: Dict[str, bool] = None):
        """
        初始化自定义媒体组发送器
        
        参数:
            client: Pyrogram客户端实例
            config_parser: 配置解析器或None
            target_channels: 目标频道列表
            temp_folder: 临时文件夹
            channel_forward_status: 频道转发状态缓存
        """
        # 基础属性设置
        self.client = client
        self.config_parser = config_parser
        self.target_channels = target_channels or []
        self.temp_folder = temp_folder or './temp'
        self.channel_forward_status = channel_forward_status or {}
        
        # 初始化频道验证器
        self.channel_validator = ChannelValidator(client)
        
        # 存储实际的聊天ID映射表
        self.actual_chat_ids = {}
        
        # 读取配置并设置默认值
        self._init_config()
        
        # 创建并发信号量
        self.semaphore = asyncio.Semaphore(self.max_concurrent_uploads)
        
        # 日志记录
        logger.info(f"媒体发送器初始化完成: 目标频道数 {len(self.target_channels)}, "
                    f"隐藏消息来源: {self.hide_author}, 最大并发上传数: {self.max_concurrent_uploads}")
    
    def _init_config(self):
        """初始化配置，从config_parser读取设置或使用默认值"""
        # 设置默认值
        self.hide_author = False
        self.max_concurrent_batches = 3
        self.max_concurrent_uploads = 3
        
        # 从config_parser读取配置
        if self.config_parser and isinstance(self.config_parser, configparser.ConfigParser):
            if self.config_parser.has_section("FORWARD"):
                self.hide_author = self.config_parser.getboolean("FORWARD", "hide_author", fallback=False)
                self.max_concurrent_batches = self.config_parser.getint("FORWARD", "max_concurrent_batches", fallback=3)
            
            if self.config_parser.has_section("UPLOAD"):
                self.max_concurrent_uploads = self.config_parser.getint("UPLOAD", "max_concurrent_batches", fallback=3)
        
        # 创建配置字典，便于内部使用
        self.config = {
            "temp_folder": self.temp_folder,
            "target_channels": self.target_channels,
            "max_concurrent_batches": self.max_concurrent_batches,
            "hide_author": self.hide_author,
            "max_concurrent_uploads": self.max_concurrent_uploads,
        }
    
    def get_media_files(self, folder: str, limit: int = 10) -> List[str]:
        """获取指定文件夹下的媒体文件"""
        if not os.path.exists(folder):
            logger.error(f"文件夹不存在: {folder}")
            return []
            
        media_files = []
        allowed_extensions = ('.jpg', '.jpeg', '.png', '.mp4', '.mov', '.avi', '.gif')
        
        for filename in os.listdir(folder):
            if filename.lower().endswith(allowed_extensions):
                file_path = os.path.join(folder, filename)
                if os.path.isfile(file_path):
                    media_files.append(file_path)
                    if len(media_files) >= limit:
                        break
        
        logger.info(f"找到 {len(media_files)} 个媒体文件用于测试")
        return media_files
    
    async def progress_callback(self, current: int, total: int, tracker: UploadProgressTracker):
        """进度回调函数"""
        tracker.update_progress(current, total)
    
    async def upload_file_for_media_group(self, file_path: str, tracker: Optional[UploadProgressTracker] = None) -> Tuple[Optional[str], Optional[Message]]:
        """
        上传单个文件，用于媒体组发送
        
        参数:
            file_path: 文件路径
            tracker: 上传进度跟踪器
            
        返回:
            Tuple[Optional[str], Optional[Message]]: (上传成功的文件ID, 消息对象) 或 (None, None)
        """
        if not os.path.exists(file_path):
            logger.error(f"文件不存在: {file_path}")
            return None, None
            
        file_name = os.path.basename(file_path)
        file_size = os.path.getsize(file_path)
        mime_type = mimetypes.guess_type(file_path)[0] or "application/octet-stream"
        
        # 开始跟踪当前文件上传
        if tracker:
            tracker.start_file(file_name, file_size)
        
        # 创建用于接收消息的聊天ID
        chat_id = "me"  # 使用自己的账号作为中转
        
        # 获取客户端实例
        client_to_use = self.client
        
        thumb_path = None
        
        try:
            # 根据文件类型选择不同的上传方法
            try:
                if mime_type.startswith('image/'):
                    logger.info(f"正在上传图片: {file_name}")
                    message = await client_to_use.send_photo(
                        chat_id=chat_id,
                        photo=file_path,
                        caption=f"[temp] {file_name}",
                        progress=self.progress_callback if tracker else None,
                        progress_args=(tracker,) if tracker else None
                    )
                    file_id = message.photo.file_id
                    
                elif mime_type.startswith('video/'):
                    # 为视频生成缩略图
                    try:
                        if MOVIEPY_AVAILABLE:
                            thumb_path = self.generate_thumbnail(file_path)
                    except Exception as e:
                        logger.warning(f"生成缩略图失败: {str(e)}")
                        thumb_path = None

                    logger.info(f"正在上传视频: {file_name}")
                    message = await client_to_use.send_video(
                        chat_id=chat_id,
                        video=file_path,
                        caption=f"[temp] {file_name}",
                        thumb=thumb_path,  # 添加缩略图参数
                        supports_streaming=True,  # 启用流媒体支持
                        progress=self.progress_callback if tracker else None,
                        progress_args=(tracker,) if tracker else None
                    )
                    file_id = message.video.file_id
                
                else:
                    logger.info(f"正在上传文档: {file_name}")
                    message = await client_to_use.send_document(
                        chat_id=chat_id,
                        document=file_path,
                        caption=f"[temp] {file_name}",
                        progress=self.progress_callback if tracker else None,
                        progress_args=(tracker,) if tracker else None
                    )
                    file_id = message.document.file_id
                
                # 完成进度跟踪
                if tracker:
                    tracker.complete_file()
                
                logger.info(f"成功上传文件 {file_name}，获取到file_id")
                return file_id, message
                
            except AttributeError as e:
                if "is_premium" in str(e):
                    logger.warning(f"客户端实例缺少premium属性，尝试使用替代方法上传: {str(e)}")
                    # 告知用户但不引发错误，上传继续
                    return None, None
                else:
                    # 其他属性错误
                    logger.error(f"上传文件 {file_name} 时出现属性错误: {str(e)}")
                    return None, None
        except Exception as e:
            # 简化错误信息
            error_msg = str(e)
            if len(error_msg) > 50:
                error_msg = error_msg[:50] + "..."
            logger.error(f"上传文件 {file_name} 失败: {error_msg}")
            return None, None
        finally:
            # 清理缩略图文件
            if thumb_path and os.path.exists(thumb_path):
                try:
                    os.unlink(thumb_path)
                    logger.debug(f"已清理临时缩略图: {thumb_path}")
                except Exception as e:
                    logger.warning(f"清理临时缩略图失败: {str(e)}")
    
    def generate_thumbnail(self, video_path: str) -> Optional[str]:
        """
        使用moviepy为视频生成缩略图
        
        参数:
            video_path: 视频文件路径
            
        返回:
            str: 缩略图文件路径，如果生成失败则返回None
        """
        if not MOVIEPY_AVAILABLE:
            return None
            
        thumb_path = None
        video = None
        
        try:
            # 创建一个临时文件用于保存缩略图
            with tempfile.NamedTemporaryFile(suffix='.jpg', delete=False) as thumb_file:
                thumb_path = thumb_file.name
            
            # 使用moviepy加载视频并截取帧作为缩略图
            video = VideoFileClip(video_path)
            
            # 获取视频时长的25%位置的帧
            frame_time = max(0.1, min(video.duration * 0.25, video.duration - 0.1))
                
            # 获取视频的帧
            video_frame = video.get_frame(frame_time)
                
            # 创建临时图像并保存为JPEG
            from PIL import Image
            import numpy as np
            image = Image.fromarray(np.uint8(video_frame))
                
            # 调整图像大小以适应Telegram缩略图要求(不超过320px)
            width, height = image.size
            max_size = 320
                
            if width > height:
                new_width = min(width, max_size)
                new_height = int(height * (new_width / width))
            else:
                new_height = min(height, max_size)
                new_width = int(width * (new_height / height))
                
            image = image.resize((new_width, new_height), Image.LANCZOS)
                
            # 保存缩略图，质量设为90%以确保文件小于200KB
            image.save(thumb_path, 'JPEG', quality=90, optimize=True)
                
            # 检查文件大小是否超过200KB，如果超过则压缩
            if os.path.getsize(thumb_path) > 200 * 1024:
                # 递减质量直到文件小于200KB
                quality = 85
                while os.path.getsize(thumb_path) > 200 * 1024 and quality > 10:
                    image.save(thumb_path, 'JPEG', quality=quality, optimize=True)
                    quality -= 10
                
            logger.info(f"已生成视频缩略图: {os.path.basename(video_path)}")
            return thumb_path
                
        except Exception as e:
            logger.warning(f"生成视频缩略图失败: {str(e)}")
            # 如果生成失败但临时文件已创建，则删除它
            if thumb_path and os.path.exists(thumb_path):
                try:
                    os.unlink(thumb_path)
                except Exception as e:
                    logger.warning(f"删除临时缩略图文件失败: {str(e)}")
            return None
        finally:
            # 确保VideoFileClip对象被正确关闭
            if video is not None:
                try:
                    video.close()
                except Exception as e:
                    logger.warning(f"关闭VideoFileClip对象失败: {str(e)}")
    
    async def send_media_group_with_progress(self, chat_id: str, file_paths: List[str]) -> Tuple[bool, List[Message]]:
        """
        发送媒体组，带进度显示
        
        返回值:
            Tuple[bool, List[Message]]: 发送是否成功, 及发送成功的消息列表
        """
        if not file_paths:
            logger.warning("没有提供任何文件路径")
            return False, []
        
        # 首先过滤出存在的文件，确保后续所有操作都是安全的
        file_paths = [path for path in file_paths if os.path.exists(path)]
        if not file_paths:
            logger.warning("所有提供的文件路径都不存在，无法继续")
            return False, []
            
        # 计算总文件大小 - 仅使用存在的文件
        total_size = sum(os.path.getsize(path) for path in file_paths)
        tracker = UploadProgressTracker(len(file_paths), total_size)
        
        # 简化日志输出，不输出准备上传信息
        
        # 使用tqdm创建文件处理进度条
        file_batch_desc = "处理文件"
        with tqdm(total=len(file_paths), desc=file_batch_desc, unit="个", position=2, 
                 bar_format=BATCH_BAR_FORMAT,
                 colour='magenta') if TQDM_AVAILABLE else None as file_pbar:
            # 上传所有文件并获取文件ID
            media_list = []
            valid_file_paths = []  # 创建一个有效文件路径列表
            thumbnail_paths = []  # 存储生成的缩略图路径，以便后续清理
            
            for file_path in file_paths:
                # 文件已经在函数开始处过滤过，这里不需要再次检查
                file_name = os.path.basename(file_path)
                mime_type = mimetypes.guess_type(file_path)[0] or ""
                
                # 上传文件
                file_id, message = await self.upload_file_for_media_group(file_path, tracker)
                
                if not file_id:
                    if TQDM_AVAILABLE and file_pbar:
                        file_pbar.update(1)
                    continue
                
                # 如果上传成功，添加到有效文件列表
                valid_file_paths.append(file_path)
                    
                # 根据媒体类型创建不同的媒体对象
                if mime_type.startswith('image/'):
                    media_list.append(InputMediaPhoto(
                        media=file_id,
                        caption=f"[测试] 图片: {file_name}"
                    ))
                elif mime_type.startswith('video/'):
                    # 为视频生成缩略图
                    thumb_path = None
                    if MOVIEPY_AVAILABLE:
                        thumb_path = self.generate_thumbnail(file_path)
                        if thumb_path:
                            thumbnail_paths.append(thumb_path)
                    
                    media_list.append(InputMediaVideo(
                        media=file_id,
                        caption=f"[测试] 视频: {file_name}",
                        thumb=thumb_path,  # 添加缩略图参数
                        width=None,  # 可以在这里添加视频宽度
                        height=None,  # 可以在这里添加视频高度
                        duration=None,  # 可以在这里添加视频时长
                        supports_streaming=True  # 启用流媒体支持
                    ))
                else:
                    media_list.append(InputMediaDocument(
                        media=file_id,
                        caption=f"[测试] 文件: {file_name}"
                    ))
                
                # 更新文件处理进度条
                if TQDM_AVAILABLE and file_pbar:
                    file_pbar.update(1)
            
        # 检查是否有成功上传的媒体
        if not media_list:
            logger.error("没有成功上传任何媒体文件，无法发送媒体组")
            return False, []
            
        # 发送媒体组
        sent_messages = []
        try:
            # 创建媒体组发送批次
            batch_desc = f"发送媒体组"
            
            # 使用当前客户端实例
            client_to_use = self.client
            
            # 发送媒体组
            media_batch_chunks = [media_list[i:i+10] for i in range(0, len(media_list), 10)]
            
            # 创建批次进度条
            with tqdm(total=len(media_batch_chunks), desc=batch_desc, unit="批", position=3, 
                      bar_format=BATCH_BAR_FORMAT,
                      colour='yellow') if TQDM_AVAILABLE else None as batch_pbar:
                
                for batch in media_batch_chunks:
                    result = await client_to_use.send_media_group(chat_id, batch)
                    sent_messages.extend(result)
                    
                    # 更新批次进度条
                    if TQDM_AVAILABLE and batch_pbar:
                        batch_pbar.update(1)
            
            # 清理生成的缩略图临时文件
            for thumb_path in thumbnail_paths:
                try:
                    if os.path.exists(thumb_path):
                        os.unlink(thumb_path)
                except Exception as e:
                    logger.warning(f"删除缩略图临时文件失败: {str(e)}")
            
            tracker.complete_all()
            
            logger.info(f"已成功将 {len(valid_file_paths)} 个文件发送到 {chat_id}")
            return True, sent_messages
            
        except Exception as e:
            # 简化错误信息
            error_msg = str(e)
            if len(error_msg) > 50:
                error_msg = error_msg[:50] + "..."
            logger.error(f"发送媒体组失败: {error_msg}")
            
            # 清理生成的缩略图临时文件
            for thumb_path in thumbnail_paths:
                try:
                    if os.path.exists(thumb_path):
                        os.unlink(thumb_path)
                except:
                    pass
                
            return False, sent_messages
    
    async def forward_media_messages(self, from_chat_id: str, to_chat_id: str, messages: List[Message], hide_author: bool = False) -> Tuple[bool, List[Message]]:
        """
        转发媒体消息
        
        参数:
            from_chat_id: 源频道ID
            to_chat_id: 目标频道ID
            messages: 消息列表
            hide_author: 是否隐藏作者
            
        返回:
            Tuple[bool, List[Message]]: (成功标志, 转发后的消息列表)
        """
        # 检查参数
        if not messages:
            logger.warning("没有提供要转发的消息")
            return False, []
            
        # 获取实际的频道ID
        from_chat_actual = self.get_actual_chat_id(from_chat_id)
        to_chat_actual = self.get_actual_chat_id(to_chat_id)
        
        # 验证ID格式
        if not self._is_valid_chat_id_format(from_chat_actual):
            logger.error(f"❌ 源频道ID格式不正确: {from_chat_id} -> {from_chat_actual}")
            return False, []
            
        if not self._is_valid_chat_id_format(to_chat_actual):
            logger.error(f"❌ 目标频道ID格式不正确: {to_chat_id} -> {to_chat_actual}")
            return False, []
        
        # 检查源频道是否禁止转发
        try:
            source_chat = await self.client.get_chat(from_chat_actual)
            if hasattr(source_chat, 'has_protected_content') and source_chat.has_protected_content:
                logger.warning(f"源频道 {from_chat_id} 禁止转发消息")
                return False, []
        except Exception as e:
            logger.warning(f"检查源频道 {from_chat_id} 状态失败: {str(e)[:50]}")
        
        try:
            forwarded_messages = []
            total_success = 0
            
            # 分批处理，每批最多10条消息
            batch_size = 10
            batches = [messages[i:i+batch_size] for i in range(0, len(messages), batch_size)]
            logger.info(f"转发 {from_chat_id} → {to_chat_id} ({len(messages)}条消息，分{len(batches)}批)")
            
            for batch_idx, batch in enumerate(batches):
                try:
                    # 根据hide_author参数决定使用何种方式
                    if hide_author:
                        # 检查是否是媒体组
                        msg = batch[0]
                        media_group_id = getattr(msg, 'media_group_id', None)
                        
                        if media_group_id and all(getattr(m, 'media_group_id', None) == media_group_id for m in batch):
                            # 整体复制媒体组
                            batch_result = await self._copy_media_group(from_chat_actual, to_chat_actual, batch[0].id)
                        else:
                            # 逐条复制消息
                            batch_result = await self._copy_messages(from_chat_actual, to_chat_actual, batch)
                    else:
                        # 使用直接转发
                        message_ids = [msg.id for msg in batch]
                        batch_result = await self.client.forward_messages(
                            chat_id=to_chat_actual,
                            from_chat_id=from_chat_actual,
                            message_ids=message_ids
                        )
                    
                    # 处理结果
                    if batch_result:
                        forwarded_messages.extend(batch_result if isinstance(batch_result, list) else [batch_result])
                        total_success += len(batch_result) if isinstance(batch_result, list) else 1
                        
                    # 批次间添加短暂延迟，避免频率限制
                    if batch_idx < len(batches) - 1:
                        await asyncio.sleep(0.5)
                        
                except FloodWait as e:
                    logger.warning(f"转发受限，等待 {e.value} 秒后重试")
                    await asyncio.sleep(e.value)
                    
                    # 重试
                    message_ids = [msg.id for msg in batch]
                    retry_result = await self.client.forward_messages(
                        chat_id=to_chat_actual,
                        from_chat_id=from_chat_actual,
                        message_ids=message_ids
                    )
                    
                    if retry_result:
                        forwarded_messages.extend(retry_result if isinstance(retry_result, list) else [retry_result])
                        total_success += len(retry_result) if isinstance(retry_result, list) else 1
                except Exception as e:
                    logger.error(f"转发批次 {batch_idx+1}/{len(batches)} 失败: {str(e)[:50]}")
            
            # 返回结果
            is_success = total_success > 0
            if is_success:
                logger.info(f"转发成功: {from_chat_id} → {to_chat_id} ({total_success}/{len(messages)}条消息)")
            else:
                logger.error(f"转发失败: {from_chat_id} → {to_chat_id}")
                
            return is_success, forwarded_messages
            
        except Exception as e:
            logger.error(f"转发过程出错: {str(e)[:50]}")
            return False, []
            
    async def _copy_media_group(self, from_chat_id: str, to_chat_id: str, message_id: int) -> List[Message]:
        """复制媒体组"""
        try:
            return await self.client.copy_media_group(
                chat_id=to_chat_id,
                from_chat_id=from_chat_id,
                message_id=message_id
            )
        except Exception as e:
            error_msg = str(e)
            if "USERNAME_NOT_OCCUPIED" in error_msg:
                logger.error(f"频道名不存在: {to_chat_id}")
            elif "CHAT_FORWARDS_RESTRICTED" in error_msg:
                logger.warning(f"频道转发限制: {to_chat_id}")
            else:
                logger.error(f"复制媒体组失败: {error_msg[:50]}")
            return []
            
    async def _copy_messages(self, from_chat_id: str, to_chat_id: str, messages: List[Message]) -> List[Message]:
        """逐条复制消息"""
        results = []
        for msg in messages:
            try:
                copied = await self.client.copy_message(
                    chat_id=to_chat_id,
                    from_chat_id=from_chat_id,
                    message_id=msg.id
                )
                if copied:
                    results.append(copied)
            except Exception:
                # 单条失败继续处理下一条
                pass
        return results
    
    async def send_to_all_channels(self, file_paths: List[str], preserve_format: bool = False, 
                                 metadata_files: List[str] = None, parallel_channels: int = None) -> Dict[str, Any]:
        """
        按照优化流程发送媒体文件到所有目标频道:
        1. 先上传到me获取file_id
        2. 找到第一个允许转发的频道并发送
        3. 从该频道转发到其他频道
        
        参数:
            file_paths: 媒体文件路径列表
            preserve_format: 是否保持原始消息格式
            metadata_files: 元数据文件路径列表
            parallel_channels: 并行处理的频道数量
            
        返回:
            Dict: 包含成功/失败统计和每个频道的消息列表
        """
        # 初始化结果和检查参数
        start_time = time.time()
        results = {
            "success": 0,          # 成功发送的频道数
            "fail": 0,             # 失败发送的频道数
            "messages_by_channel": {}  # 每个频道的消息列表
        }
        
        # 检查文件路径
        if not file_paths:
            logger.error("❌ 没有提供任何文件路径")
            return results
            
        # 设置并行数量
        if parallel_channels is None:
            if isinstance(self.config_parser, configparser.ConfigParser):
                if self.config_parser.has_section('UPLOAD'):
                    parallel_channels = self.config_parser.getint('UPLOAD', 'parallel_uploads', fallback=3)
                else:
                    parallel_channels = 3
            else:
                parallel_channels = 3  # 默认值
        
        logger.info(f"并行上传频道数量: {parallel_channels}")
        
        # 验证频道
        valid_channels, invalid_channels, forward_status = await self.channel_validator.validate_channels(self.target_channels)
        # 更新转发状态缓存
        if forward_status:
            self.channel_forward_status.update(forward_status)
            
        # 确保已经预加载了频道ID
        if not self.actual_chat_ids:
            logger.info("预加载频道ID...")
            await self.preload_channel_ids(valid_channels)
                
        if not valid_channels:
            logger.error("❌ 没有有效的目标频道，上传被终止")
            results["fail"] = len(self.target_channels)
            return results
            
        logger.info(f"🚀 开始处理 {len(file_paths)} 个文件到 {len(valid_channels)} 个频道")
        
        # 第1步: 上传到me获取file_id并组装媒体组件
        logger.info("📤 步骤1：上传文件到'me'获取file_id")
        media_components = await self.first_upload_to_me(file_paths)
        if not media_components:
            logger.error("❌ 没有成功上传任何媒体文件，流程终止")
            results["fail"] = len(valid_channels)
            return results
            
        # 第2步: 找到适合的第一个频道作为转发源
        logger.info("🔍 步骤2：查找合适的第一个频道作为转发源")
        first_channel = None
        
        # 优先使用允许转发的频道，但要确保能获取到实际ID
        if self.channel_forward_status:
            # 按照转发状态对频道进行排序
            sorted_channels = sorted(
                valid_channels,
                key=lambda x: 0 if self.channel_forward_status.get(str(x), True) else 1
            )
            
            # 找到第一个允许转发的频道，且确保该频道的ID可用
            for channel in sorted_channels:
                if self.channel_forward_status.get(str(channel), True):
                    # 检查是否有该频道的实际ID
                    channel_str = str(channel)
                    if channel_str in self.actual_chat_ids:
                        actual_id = self.actual_chat_ids[channel_str]
                        # 验证ID格式是否正确
                        if self._is_valid_chat_id_format(actual_id):
                            first_channel = channel
                            logger.info(f"✅ 找到允许转发的频道: {first_channel} (实际ID: {actual_id})")
                            break
                        else:
                            logger.warning(f"⚠️ 跳过频道 {channel}，ID格式不正确: {actual_id}")
                    else:
                        logger.warning(f"⚠️ 跳过频道 {channel}，无法获取实际ID")
        
        # 如果没有找到允许转发的频道，使用第一个有效频道（但要确保ID可用）
        if not first_channel and valid_channels:
            for channel in valid_channels:
                channel_str = str(channel)
                if channel_str in self.actual_chat_ids:
                    actual_id = self.actual_chat_ids[channel_str]
                    if self._is_valid_chat_id_format(actual_id):
                        first_channel = channel
                        logger.warning(f"⚠️ 没有找到允许转发的频道，将使用: {first_channel} (实际ID: {actual_id})")
                        break
        
        if not first_channel:
            logger.error("❌ 无法确定第一个目标频道，流程终止")
            results["fail"] = len(valid_channels)
            return results
            
        # 获取第一个频道的实际ID
        first_channel_actual = self.get_actual_chat_id(first_channel)
        
        # 额外验证ID格式
        if not self._is_valid_chat_id_format(first_channel_actual):
            logger.error(f"❌ 第一个频道 {first_channel} 的ID格式不正确: {first_channel_actual}，流程终止")
            results["fail"] = len(valid_channels)
            return results
                
        logger.info(f"📤 正在发送媒体组到第一个频道: {first_channel} (ID: {first_channel_actual})")
        try:
            # 发送媒体组
            messages = await self.client.send_media_group(
                chat_id=first_channel_actual,
                media=media_components
            )
            
            if not messages:
                logger.error(f"❌ 发送到第一个频道 {first_channel} 失败: 未返回消息")
                results["fail"] = len(valid_channels)
                return results
                
            logger.info(f"✅ 成功发送到第一个频道 {first_channel}，共 {len(messages)} 条消息")
            results["success"] += 1
            results["messages_by_channel"][str(first_channel)] = messages
            
            # 第3步: 从第一个频道转发到其他频道
            if len(valid_channels) > 1:
                logger.info("↪️ 步骤3：从第一个频道转发到其他频道")
                remaining_channels = [ch for ch in valid_channels if ch != first_channel]
                
                # 使用缓存的转发状态判断是否可以转发
                can_forward = self.channel_validator.get_forward_status(first_channel, True)
                
                if can_forward:
                    # 可以使用转发，创建信号量控制并发数
                    semaphore = asyncio.Semaphore(parallel_channels)
                    tasks = []
                    
                    # 定义并发转发函数
                    async def forward_to_channel(channel):
                        async with semaphore:
                            target_id = self.get_actual_chat_id(channel)
                            if not self._is_valid_chat_id_format(target_id):
                                logger.error(f"❌ 目标频道 {channel} ID格式不正确: {target_id}")
                                return False, None
                                
                            logger.info(f"↪️ 转发到 {channel}")
                            try:
                                success, forwarded = await self.forward_media_messages(
                                    from_chat_id=first_channel_actual,
                                    to_chat_id=target_id,
                                    messages=messages,
                                    hide_author=self.hide_author
                                )
                                return success, forwarded
                            except Exception as e:
                                logger.error(f"❌ 转发到 {channel} 失败: {str(e)}")
                                return False, None
                    
                    # 为每个剩余频道创建任务
                    for channel in remaining_channels:
                        tasks.append(asyncio.create_task(forward_to_channel(channel)))
                    
                    # 等待所有任务完成并处理结果
                    remaining_results = await asyncio.gather(*tasks, return_exceptions=True)
                    
                    # 处理转发结果
                    for i, (channel, result) in enumerate(zip(remaining_channels, remaining_results)):
                        if isinstance(result, Exception):
                            logger.error(f"❌ 转发到 {channel} 时出错: {str(result)}")
                            results["fail"] += 1
                        elif isinstance(result, tuple) and len(result) == 2:
                            success, forwarded = result
                            if success:
                                logger.info(f"✅ 成功转发到 {channel}")
                                results["success"] += 1
                                results["messages_by_channel"][str(channel)] = forwarded
                            else:
                                logger.error(f"❌ 转发到 {channel} 失败")
                                results["fail"] += 1
                        else:
                            logger.error(f"❌ 转发到 {channel} 返回了意外结果")
                            results["fail"] += 1
                else:
                    # 无法转发，需要发送副本
                    logger.warning(f"⚠️ 源频道 {first_channel} 禁止转发，将使用复制消息方式")
                    
                    # 同样使用并发处理
                    semaphore = asyncio.Semaphore(parallel_channels)
                    tasks = []
                    
                    # 定义发送副本的函数
                    async def copy_to_channel(channel):
                        async with semaphore:
                            target_id = self.get_actual_chat_id(channel)
                            if not self._is_valid_chat_id_format(target_id):
                                logger.error(f"❌ 目标频道 {channel} ID格式不正确: {target_id}")
                                return False, None
                                
                            logger.info(f"📋 复制到 {channel}")
                            try:
                                # 检查是否是媒体组
                                if hasattr(messages[0], 'media_group_id') and messages[0].media_group_id:
                                    copied = await self.client.copy_media_group(
                                        chat_id=target_id,
                                        from_chat_id=first_channel_actual,
                                        message_id=messages[0].id
                                    )
                                    return True, copied
                                else:
                                    # 逐条复制普通消息
                                    copied_msgs = []
                                    for msg in messages:
                                        copied = await self.client.copy_message(
                                            chat_id=target_id,
                                            from_chat_id=first_channel_actual,
                                            message_id=msg.id
                                        )
                                        copied_msgs.append(copied)
                                    return True, copied_msgs
                            except Exception as e:
                                logger.error(f"❌ 复制到 {channel} 失败: {str(e)}")
                                return False, None
                    
                    # 为每个剩余频道创建任务
                    for channel in remaining_channels:
                        tasks.append(asyncio.create_task(copy_to_channel(channel)))
                    
                    # 等待所有任务完成并处理结果
                    copy_results = await asyncio.gather(*tasks, return_exceptions=True)
                    
                    # 处理复制结果
                    for channel, result in zip(remaining_channels, copy_results):
                        if isinstance(result, Exception):
                            logger.error(f"❌ 复制到 {channel} 时出错: {str(result)}")
                            results["fail"] += 1
                        elif isinstance(result, tuple) and len(result) == 2:
                            success, copied = result
                            if success:
                                logger.info(f"✅ 成功复制到 {channel}")
                                results["success"] += 1
                                results["messages_by_channel"][str(channel)] = copied
                            else:
                                logger.error(f"❌ 复制到 {channel} 失败")
                                results["fail"] += 1
                        else:
                            logger.error(f"❌ 复制到 {channel} 返回了意外结果")
                            results["fail"] += 1
        except Exception as e:
            logger.error(f"❌ 发送到第一个频道 {first_channel} 失败: {str(e)}")
            results["fail"] = len(valid_channels)
            
        # 计算总耗时
        elapsed_time = time.time() - start_time        
        logger.info(f"✅ 全部完成! 成功: {results['success']}/{len(valid_channels)}，耗时: {elapsed_time:.2f}秒")
            
        return results

    async def validate_channels(self) -> List[str]:
        """
        验证目标频道是否存在且有权限
        
        返回:
            List[str]: 有效的目标频道列表
        """
        # 验证频道并更新状态
        valid_channels, invalid_channels, forward_status = await self.channel_validator.validate_channels(self.target_channels)
        
        # 更新转发状态缓存
        if forward_status:
            self.channel_forward_status.update(forward_status)
            
        # 预加载频道ID
        if valid_channels:
            await self.preload_channel_ids(valid_channels)
        else:
            logger.warning("没有有效的目标频道")
                
        return valid_channels
        
    async def preload_channel_ids(self, channels: List[str]) -> None:
        """
        预加载频道的实际ID
        
        参数:
            channels: 频道标识符列表
        """
        if not channels:
            logger.info("没有频道需要预加载")
            return
            
        logger.info(f"预加载 {len(channels)} 个频道的ID信息...")
        
        # 检查已缓存ID数量
        cached_count = sum(1 for ch in channels if str(ch) in self.actual_chat_ids)
        if cached_count > 0:
            logger.info(f"✓ 已有 {cached_count}/{len(channels)} 个频道ID在缓存中")
        
        # 处理数字格式ID
        numeric_channels = []
        non_numeric_channels = []
        
        for channel in channels:
            channel_str = str(channel)
            # 如果channel本身就是数字ID，直接使用
            if channel_str.startswith('-100') or (channel_str.isdigit() and len(channel_str) > 6):
                self.actual_chat_ids[channel_str] = channel
                numeric_channels.append(channel)
            else:
                non_numeric_channels.append(channel)
        
        if numeric_channels:
            logger.info(f"✓ 识别到 {len(numeric_channels)} 个数字格式的频道ID")
            
        # 处理私有频道链接，尝试从已有缓存匹配
        private_channels = []
        remaining_channels = []
        
        for channel in non_numeric_channels:
            channel_str = str(channel)
            # 检查是否是私有频道链接
            if isinstance(channel, str) and ('t.me/+' in channel or channel.startswith('+')):
                # 尝试从channel_forward_status中的键匹配
                match_found = False
                for stored_key in self.channel_forward_status.keys():
                    stored_key_str = str(stored_key)
                    # 如果存储的键是数字ID，且有对应的私有链接缓存
                    if stored_key_str.startswith('-100'):
                        for cached_key, cached_id in self.actual_chat_ids.items():
                            if str(cached_id) == stored_key_str and isinstance(cached_key, str) and '+' in cached_key:
                                # 比较链接部分
                                link_part1 = channel_str.split('+')[-1].split('/')[0]
                                link_part2 = cached_key.split('+')[-1].split('/')[0]
                                if link_part1 == link_part2:
                                    self.actual_chat_ids[channel_str] = stored_key
                                    logger.info(f"✓ 为私有链接 {channel_str} 匹配到ID: {stored_key}")
                                    match_found = True
                                    break
                if match_found:
                    private_channels.append(channel)
                else:
                    remaining_channels.append(channel)
            else:
                remaining_channels.append(channel)
                
        if private_channels:
            logger.info(f"✓ 处理了 {len(private_channels)} 个私有频道链接")
        
        # 对剩余频道使用API加载
        if remaining_channels:
            logger.info(f"⏳ 正在通过API获取 {len(remaining_channels)} 个频道的ID...")
            
            for channel in remaining_channels:
                try:
                    await self._resolve_channel_id_with_validator_async(channel)
                except KeyboardInterrupt:
                    logger.warning("⚠️ 用户中断操作")
                    raise
                except Exception as e:
                    logger.warning(f"⚠️ 获取频道 {channel} ID失败: {str(e)}")
                    # 失败时使用原始值
                    self.actual_chat_ids[str(channel)] = channel
        
        logger.info(f"✅ 完成 {len(self.actual_chat_ids)} 个频道ID的预加载")
    
    async def _resolve_channel_id_with_validator_async(self, channel) -> str:
        """
        使用验证器异步解析频道ID
        
        参数:
            channel: 频道标识符
            
        返回:
            str: 实际的频道ID
        """
        channel_str = str(channel)
        
        try:
            # 方法1: 直接使用get_chat
            chat = await self.client.get_chat(channel)
            
            if chat and hasattr(chat, 'id'):
                actual_id = chat.id
                self.actual_chat_ids[channel_str] = actual_id
                logger.info(f"✅ 已获取频道 {channel_str} 的实际ID: {actual_id}")
                
                # 如果是私有频道链接，同时保存链接形式的键
                if isinstance(channel, str) and ('t.me/+' in channel or channel.startswith('+')):
                    self.actual_chat_ids[channel] = actual_id
                
                return actual_id
        except Exception as e1:
            # 尝试备用方法
            try:
                # 方法2: 对于公开频道，尝试解析用户名
                if isinstance(channel, str) and 't.me/' in channel and '+' not in channel:
                    username = channel.split('t.me/')[1].split('/')[0]
                    chat = await self.client.get_chat(f"@{username}")
                    if chat and hasattr(chat, 'id'):
                        actual_id = chat.id
                        self.actual_chat_ids[channel_str] = actual_id
                        logger.info(f"✅ 已通过用户名 @{username} 获取频道ID: {actual_id}")
                        return actual_id
            except Exception:
                # 尝试最后一种方法
                try:
                    # 方法3: 获取消息历史
                    messages = await self.client.get_chat_history(channel, limit=1)
                    if messages:
                        chat_id = messages[0].chat.id
                        self.actual_chat_ids[channel_str] = chat_id
                        logger.info(f"✅ 通过历史消息获取频道ID: {chat_id}")
                        return chat_id
                except Exception as e3:
                    logger.warning(f"⚠️ 所有方法获取频道 {channel} ID都失败")
                    raise e3
        
        # 如果所有方法都失败，使用原始值
        return channel

    def get_actual_chat_id(self, channel: str) -> str:
        """
        获取频道的实际聊天ID，优先使用缓存
        
        参数:
            channel: 频道标识符
            
        返回:
            str: 实际的聊天ID
        """
        # 处理空值或None
        if not channel:
            return channel
            
        # 统一转为字符串处理
        channel_str = str(channel)
        
        # 检查缓存
        if channel_str in self.actual_chat_ids:
            chat_id = self.actual_chat_ids[channel_str]
            # 验证缓存的ID格式
            if self._is_valid_chat_id_format(chat_id):
                return chat_id
        
        # 如果是数字ID格式，直接返回
        if self._is_valid_chat_id_format(channel_str):
            self.actual_chat_ids[channel_str] = channel_str  # 缓存起来
            return channel_str
            
        # 如果是私有频道链接，尝试匹配
        if isinstance(channel, str) and ('t.me/+' in channel or channel.startswith('+')):
            matched_id = self._find_matched_private_channel_id(channel)
            if matched_id:
                return matched_id
        
        # 使用验证器获取实际ID
        try:
            actual_id = self.channel_validator.get_actual_chat_id(channel)
            actual_id_str = str(actual_id)
            
            # 验证ID格式
            if self._is_valid_chat_id_format(actual_id_str):
                self.actual_chat_ids[channel_str] = actual_id
                return actual_id
            else:
                logger.warning(f"⚠️ 验证器返回的ID格式不正确: {actual_id}")
        except Exception as e:
            logger.warning(f"⚠️ 获取频道ID时出错: {str(e)}")
            
        # 无法获取有效ID，返回原始值
        return channel
    
    def _is_valid_chat_id_format(self, chat_id) -> bool:
        """检查是否是有效的聊天ID格式"""
        chat_id_str = str(chat_id)
        return (chat_id_str.startswith('-100') or 
                (chat_id_str.isdigit() and len(chat_id_str) > 6) or
                (isinstance(chat_id, int) and chat_id < 0))
    
    def _find_matched_private_channel_id(self, channel: str) -> Optional[str]:
        """为私有频道链接寻找匹配的ID"""
        channel_str = str(channel)
        link_part = channel_str.split('+')[-1].split('/')[0]
        
        # 遍历channel_forward_status寻找匹配项
        for stored_key, _ in self.channel_forward_status.items():
            stored_key_str = str(stored_key)
            
            # 如果存储的键是数字ID
            if stored_key_str.startswith('-100'):
                # 检查该ID是否与某个私有链接关联
                for cached_key, cached_id in self.actual_chat_ids.items():
                    if (str(cached_id) == stored_key_str and 
                        isinstance(cached_key, str) and 
                        '+' in cached_key):
                        
                        cached_link_part = cached_key.split('+')[-1].split('/')[0]
                        if link_part == cached_link_part:
                            # 找到匹配，缓存并返回
                            self.actual_chat_ids[channel_str] = stored_key
                            logger.info(f"✓ 匹配到私有频道: {channel_str} -> {stored_key}")
                            return stored_key
                            
        return None

    @classmethod
    async def upload_from_source_class(cls, config_path: str, downloaded_files: List[str], target_channels: List[str], 
                                delete_after_upload: bool = True, channel_forward_status: Dict[str, bool] = None) -> Dict[str, Any]:
        """
        从已下载的文件直接上传到目标频道（类方法版本）
        
        参数:
            config_path: 配置文件路径
            downloaded_files: 已下载的文件列表
            target_channels: 目标频道列表
            delete_after_upload: 上传后是否删除源文件
            channel_forward_status: 频道转发状态缓存
            
        返回:
            上传结果统计
        """
        # 读取API配置
        config_parser = configparser.ConfigParser()
        config_parser.read(config_path, encoding='utf-8')
        
        api_id = config_parser.getint('API', 'api_id')
        api_hash = config_parser.get('API', 'api_hash')
        
        # 读取代理配置
        proxy = None
        if config_parser.has_section('PROXY') and config_parser.getboolean('PROXY', 'enabled', fallback=False):
            proxy_type = config_parser.get('PROXY', 'proxy_type')
            addr = config_parser.get('PROXY', 'addr')
            port = config_parser.getint('PROXY', 'port')
            username = config_parser.get('PROXY', 'username', fallback=None) or None
            password = config_parser.get('PROXY', 'password', fallback=None) or None
            
            proxy = {
                "scheme": proxy_type.lower(),
                "hostname": addr,
                "port": port,
                "username": username,
                "password": password
            }
        
        # 过滤目标频道：移除无效的频道名和邀请链接
        filtered_target_channels = ChannelParser.filter_channels(target_channels)
        
        if len(filtered_target_channels) < len(target_channels):
            logger.info(f"初步过滤: 保留了 {len(filtered_target_channels)}/{len(target_channels)} 个可能有效的频道标识符")
        
        if not filtered_target_channels:
            logger.error("没有有效的目标频道")
            return {"success": False, "error": "没有有效的目标频道"}
        
        logger.info(f"准备从下载的文件上传到 {len(filtered_target_channels)} 个目标频道...")
        
        # 初始化Pyrogram客户端
        async with Client(
            "custom_media_sender",
            api_id=api_id,
            api_hash=api_hash,
            proxy=proxy
        ) as client:
            # 创建自定义发送器实例
            sender = cls(
                client=client, 
                config_parser=config_parser,
                target_channels=filtered_target_channels,
                channel_forward_status=channel_forward_status
            )
            
            if not downloaded_files:
                logger.error("没有找到需要上传的文件")
                return {"success": False, "error": "没有找到需要上传的文件"}
            
            # 确保文件存在
            existing_files = [f for f in downloaded_files if os.path.exists(f)]
            if not existing_files:
                logger.error("所有文件路径都无效")
                return {"success": False, "error": "所有文件路径都无效"}
            
            logger.info(f"准备上传 {len(existing_files)} 个文件")
            
            # 验证目标频道并更新有效频道列表
            valid_channels = await sender.validate_channels()
            if not valid_channels:
                logger.error("没有有效的目标频道，无法继续")
                return {"success": False, "error": "没有有效的目标频道"}
                
            # 更新发送器的目标频道为已验证的频道
            sender.target_channels = valid_channels
            
            # 记录开始时间
            start_time = time.time()
            
            # 使用优化后的send_to_all_channels方法
            result = await sender.send_to_all_channels(existing_files)
            
            # 计算总耗时
            elapsed_time = time.time() - start_time
            
            # 如果设置了删除已上传的文件
            if delete_after_upload:
                logger.info("开始删除已上传的文件...")
                deleted_count = 0
                for file_path in existing_files:
                    try:
                        os.remove(file_path)
                        deleted_count += 1
                    except Exception as e:
                        logger.error(f"删除文件 {file_path} 时出错: {e}")
                
                logger.info(f"已删除 {deleted_count}/{len(existing_files)} 个文件")
            
            # 统计成功和失败数
            success_count = result.get("success", 0)
            failed_count = result.get("fail", 0)
            
            logger.info(f"上传完成，总共 {len(valid_channels)} 个频道，成功 {success_count} 个，失败 {failed_count} 个")
            logger.info(f"总耗时: {format_time(elapsed_time)}")
            
            return {
                "success": True,
                "uploaded_files": len(existing_files),
                "target_channels": len(valid_channels),
                "success_channels": success_count,
                "failed_channels": failed_count,
                "elapsed_time": elapsed_time,
                "deleted_files": deleted_count if delete_after_upload else 0
            }

    async def first_upload_to_me(self, file_paths: List[str]) -> List[Any]:
        """
        将媒体文件首先上传到'me'(saved messages)获取file_id，然后返回准备好的媒体组件
        
        参数:
            file_paths: 文件路径列表
            
        返回:
            List[Any]: 准备好的媒体组件列表，可直接用于发送媒体组
        """
        if not file_paths:
            logger.warning("❌ 没有提供任何文件路径")
            return []
            
        # 计算总文件大小
        total_size = sum(os.path.getsize(path) for path in file_paths if os.path.exists(path))
        valid_paths = [path for path in file_paths if os.path.exists(path)]
        
        if not valid_paths:
            logger.warning("❌ 所有文件路径都无效")
            return []
            
        # 创建进度跟踪器
        tracker = UploadProgressTracker(len(valid_paths), total_size)
        
        logger.info(f"🔄 正在上传 {len(valid_paths)} 个文件到'me'以获取file_id (总大小: {format_size(total_size)})")
        
        # 使用tqdm创建上传进度条
        file_batch_desc = "上传到saved messages"
        media_components = []
        
        # 保存上传到me的消息ID，用于后续删除
        me_messages = []
        
        # 上传并获取file_id
        with tqdm(total=len(valid_paths), desc=file_batch_desc, unit="个", position=1, 
                 bar_format=FILE_BAR_FORMAT,
                 colour='blue') if TQDM_AVAILABLE else None as file_pbar:
            for file_path in valid_paths:
                file_name = os.path.basename(file_path)
                mime_type = mimetypes.guess_type(file_path)[0] or ""
                
                # 上传文件并获取file_id和消息对象
                file_id, message = await self.upload_file_for_media_group(file_path, tracker)
                
                if not file_id:
                    logger.error(f"❌ 上传文件失败: {file_name}")
                    if file_pbar:
                        file_pbar.update(1)
                    continue
                
                # 添加消息ID到列表，用于后续删除
                if message:
                    me_messages.append(message)
                    
                # 根据媒体类型创建不同的媒体组件
                if mime_type.startswith('image/'):
                    # 创建图片媒体组件
                    media_components.append(InputMediaPhoto(
                        media=file_id,
                        caption=file_name
                    ))
                elif mime_type.startswith('video/'):
                    # 为视频生成缩略图并上传
                    thumb_path = None
                    try:
                        if MOVIEPY_AVAILABLE:
                            # 避免使用with silence_output上下文，改为直接调用
                            thumb_path = self.generate_thumbnail(file_path)
                    except Exception as e:
                        logger.warning(f"⚠️ 生成缩略图失败: {str(e)}")
                        thumb_path = None
                    
                    # 将视频添加到媒体组件
                    media_components.append(InputMediaVideo(
                        media=file_id,
                        caption=file_name,
                        thumb=thumb_path,
                        supports_streaming=True
                    ))
                    
                    # 清理缩略图文件
                    if thumb_path and os.path.exists(thumb_path):
                        try:
                            os.unlink(thumb_path)
                        except Exception as e:
                            logger.warning(f"⚠️ 删除临时缩略图失败: {str(e)}")
                else:
                    # 创建文档媒体组件
                    media_components.append(InputMediaDocument(
                        media=file_id,
                        caption=file_name
                    ))
                
                # 更新进度条
                if file_pbar:
                    file_pbar.update(1)
        
        # 完成上传
        tracker.complete_all()
        
        # 删除上传到me的消息
        if me_messages:
            logger.info(f"🗑️ 正在删除上传到'me'的 {len(me_messages)} 条临时消息...")
            try:
                # 使用delete_messages批量删除消息
                await self.client.delete_messages("me", [msg.id for msg in me_messages])
                logger.info(f"✅ 已成功删除上传到'me'的 {len(me_messages)} 条临时消息")
            except Exception as e:
                logger.warning(f"⚠️ 删除'me'中的临时消息时出错: {str(e)}")
        
        if media_components:
            logger.info(f"✅ 成功准备 {len(media_components)} 个媒体组件，使用file_id模式")
        else:
            logger.error("❌ 没有成功准备任何媒体组件")
            
        return media_components

    async def upload_from_source_instance(self, source_dir=None, filter_pattern=None, 
                           batch_size=None, max_workers=None, delete_after_upload=True):
        """
        从源目录上传文件（实例方法版本）
        
        参数:
            source_dir: 源目录路径
            filter_pattern: 文件筛选模式，例如 "*.jpg"
            batch_size: 每批次处理的文件数量
            max_workers: 最大并行工作批次
            delete_after_upload: 上传后是否删除源文件
        
        返回:
            上传结果统计
        """
        start_time = time.time()
        
        # 获取参数或使用默认值
        source_dir = source_dir or self.config.get("source_dir", self.temp_folder)
        filter_pattern = filter_pattern or self.config.get("filter_pattern", "*")
        batch_size = batch_size or self.config.get("batch_size", 10)
        max_workers = max_workers or self.config.get("max_concurrent_batches", 1)
        
        # 参数校验
        if not os.path.exists(source_dir):
            logger.error(f"❌ 源目录不存在: {source_dir}")
            return {"success_flag": False, "error": f"源目录不存在: {source_dir}"}
            
        # 预加载频道ID信息
        logger.info("开始预加载频道ID信息...")
        await self.preload_channel_ids(self.target_channels)
            
        # 获取要上传的文件
        all_files = self.get_files_to_upload(source_dir, filter_pattern)
        if not all_files:
            logger.warning(f"⚠️ 在目录 {source_dir} 中没有找到匹配的文件")
            return {"success_flag": True, "message": "没有找到匹配的文件", "uploaded_files": 0}
            
        # 验证频道
        valid_channels = await self.validate_channels()
        if not valid_channels:
            logger.error("❌ 没有有效的目标频道")
            return {"success_flag": False, "error": "没有有效的目标频道"}
            
        # 按批次分组文件
        batches = self.group_files_by_batch(all_files, batch_size)
        
        logger.info(f"🚀 开始上传 {len(all_files)} 个文件 (分为 {len(batches)} 批次，最大并发: {max_workers})")
        print("\n" + "="*60)
        print(f"📂 源目录: {source_dir}")
        print(f"🔍 过滤模式: {filter_pattern}")
        print(f"📦 文件批次: {len(batches)} 批 (每批次 {batch_size} 个文件)")
        print(f"⚙️ 并发上传: {max_workers} 个批次")
        print(f"📡 目标频道: {len(self.target_channels)} 个频道")
        print(f"🗑️ 上传后删除文件: {'是' if delete_after_upload else '否'}")
        print("="*60 + "\n")
        
        # 创建批次上传进度条
        batch_desc = "上传批次"
        
        # 创建信号量控制并发
        semaphore = asyncio.Semaphore(max_workers)
        upload_tasks = []
        
        # 跟踪上传结果
        total_success = 0
        total_failures = 0
        results_by_batch = []
        
        # 创建并发上传任务
        async def process_batch(batch_index, files):
            async with semaphore:
                try:
                    logger.info(f"开始处理批次 {batch_index+1}/{len(batches)} (包含 {len(files)} 个文件)")
                    
                    # 调用优化后的send_to_all_channels方法
                    result = await self.send_to_all_channels(files)
                    
                    # 统计结果
                    batch_success = result.get("success", 0)
                    batch_failure = result.get("fail", 0)
                    
                    logger.info(f"批次 {batch_index+1} 完成，成功: {batch_success}, 失败: {batch_failure}")
                    
                    if batch_pbar:
                        batch_pbar.update(1)
                        
                    return {
                        "batch_index": batch_index,
                        "success": batch_success,
                        "fail": batch_failure,
                        "files": files
                    }
                except Exception as e:
                    logger.error(f"处理批次 {batch_index+1} 时出错: {str(e)}")
                    if batch_pbar:
                        batch_pbar.update(1)
                    return {
                        "batch_index": batch_index,
                        "success": 0,
                        "fail": len(self.target_channels),
                        "files": files,
                        "error": str(e)
                    }
                    
        # 创建进度条和上传任务
        with tqdm(total=len(batches), desc=batch_desc, unit="批",
                position=0, bar_format=TOTAL_BAR_FORMAT,
                colour='yellow') if TQDM_AVAILABLE else None as batch_pbar:
            
            # 创建所有上传任务
            for i, batch_files in enumerate(batches):
                task = asyncio.create_task(process_batch(i, batch_files))
                upload_tasks.append(task)
                
            # 等待所有任务完成并收集结果
            for future in asyncio.as_completed(upload_tasks):
                result = await future
                results_by_batch.append(result)
                
                # 累计成功和失败次数
                total_success += result.get("success", 0)
                total_failures += result.get("fail", 0)
                
        # 计算统计信息
        elapsed_time = time.time() - start_time
        total_channels = len(self.target_channels)
        expected_uploads = len(batches) * total_channels
        upload_rate = (total_success / expected_uploads) * 100 if expected_uploads > 0 else 0
        
        # 上传完成后，如果需要删除文件（即使部分失败也删除）
        deleted_files = 0
        
        # 定义成功标志 - 只要有一个上传成功就算成功
        is_success = total_success > 0
        
        if delete_after_upload and is_success:
            logger.info("🗑️ 正在删除本地文件...")
            
            for batch_result in results_by_batch:
                batch_files = batch_result.get("files", [])
                for file_path in batch_files:
                    try:
                        if os.path.exists(file_path):
                            os.remove(file_path)
                            deleted_files += 1
                            logger.debug(f"已删除文件: {os.path.basename(file_path)}")
                    except Exception as e:
                        logger.error(f"删除文件失败: {file_path}, 错误: {str(e)}")
            
            logger.info(f"✅ 已成功删除 {deleted_files}/{len(all_files)} 个本地文件")
        elif delete_after_upload:
            logger.warning("⚠️ 上传完全失败，本地文件未被删除")
        
        # 输出上传结果摘要
        print("\n" + "="*60)
        print(f"📊 上传统计")
        print(f"⏱️ 总耗时: {elapsed_time:.2f} 秒")
        print(f"📦 批次数: {len(batches)}")
        print(f"📁 文件数: {len(all_files)}")
        print(f"📡 频道数: {total_channels}")
        print(f"✅ 成功: {total_success}/{expected_uploads} ({upload_rate:.1f}%)")
        if total_failures > 0:
            print(f"❌ 失败: {total_failures}")
        if delete_after_upload:
            print(f"🗑️ 删除文件: {deleted_files}/{len(all_files)}")
        print("="*60 + "\n")
        
        return {
            "success_flag": is_success,
            "success": total_success,  # 保留数值型的success，表示成功的消息数量
            "uploaded_files": len(all_files),
            "target_channels": total_channels,
            "success_channels": len(self.target_channels) - total_failures // len(batches) if len(batches) > 0 else 0,
            "failed_channels": total_failures // len(batches) if len(batches) > 0 else 0,
            "elapsed_time": elapsed_time,
            "deleted_files": deleted_files if delete_after_upload else 0
        }

    def get_files_to_upload(self, source_dir: str, filter_pattern: str = "*") -> List[str]:
        """
        获取需要上传的文件列表
        
        参数:
            source_dir: 源目录
            filter_pattern: 文件过滤模式
            
        返回:
            List[str]: 文件路径列表
        """
        import glob
        
        if not os.path.exists(source_dir):
            logger.error(f"❌ 源目录不存在: {source_dir}")
            return []
            
        # 获取符合条件的所有文件
        file_pattern = os.path.join(source_dir, filter_pattern)
        all_files = glob.glob(file_pattern)
        
        # 仅保留媒体文件
        media_extensions = ('.jpg', '.jpeg', '.png', '.mp4', '.mov', '.avi', '.gif')
        media_files = [f for f in all_files if os.path.isfile(f) and 
                       os.path.splitext(f.lower())[1] in media_extensions]
        
        # 按文件名排序
        media_files.sort()
        
        logger.info(f"🔍 在 {source_dir} 中找到 {len(media_files)} 个媒体文件")
        return media_files
        
    def group_files_by_batch(self, files: List[str], batch_size: int) -> List[List[str]]:
        """
        将文件按批次分组
        
        参数:
            files: 文件路径列表
            batch_size: 每批文件数量
            
        返回:
            List[List[str]]: 分组后的文件列表
        """
        if not files:
            return []
            
        # 分批处理文件
        batches = []
        for i in range(0, len(files), batch_size):
            batch = files[i:i+batch_size]
            batches.append(batch)
            
        logger.info(f"📦 将 {len(files)} 个文件分为 {len(batches)} 个批次，每批 {batch_size} 个文件")
        return batches

    async def prepare_media_with_original_format(self, file_paths: List[str], metadata_dict: Dict[str, Any]) -> List[Any]:
        """
        根据原始消息格式准备媒体组件
        
        参数:
            file_paths: 媒体文件路径列表
            metadata_dict: 消息元数据字典 {消息ID: 元数据}
            
        返回:
            List: 媒体组件列表
        """
        from pyrogram.types import (
            InputMediaPhoto, 
            InputMediaVideo, 
            InputMediaAudio,
            InputMediaDocument,
            MessageEntity
        )
        
        media_components = []
        
        # 记录消息ID到文件路径的映射
        msg_id_to_file = {}
        for file_path in file_paths:
            filename = os.path.basename(file_path)
            # 从文件名中提取消息ID
            parts = filename.split("_")
            if len(parts) >= 2 and parts[1].isdigit():
                msg_id = parts[1]
                msg_id_to_file[msg_id] = file_path
                
        logger.info(f"📄 正在准备 {len(file_paths)} 个文件的媒体组件，保持原始格式")
        
        # 处理每个文件
        for msg_id, file_path in msg_id_to_file.items():
            # 查找对应的元数据
            metadata = metadata_dict.get(msg_id)
            
            if not metadata:
                logger.warning(f"⚠️ 未找到消息 {msg_id} 的元数据，将使用默认格式")
                # 使用默认上传方式，直接获取file_id
                file_id = await self.upload_file_for_media_group(file_path)
                if file_id:
                    # 根据文件扩展名判断类型
                    ext = os.path.splitext(file_path)[1].lower()
                    if ext in ('.jpg', '.jpeg', '.png', '.webp'):
                        media_components.append(InputMediaPhoto(media=file_id))
                    elif ext in ('.mp4', '.mov', '.avi'):
                        media_components.append(InputMediaVideo(media=file_id))
                    else:
                        media_components.append(InputMediaDocument(media=file_id))
                continue
                
            # 上传文件获取file_id
            file_id = await self.upload_file_for_media_group(file_path)
            if not file_id:
                continue
                
            # 获取消息文本和实体
            caption = metadata.get("text", "")
            entities_data = metadata.get("entities", [])
            
            # 将元数据中的实体转换为MessageEntity对象
            entities = []
            for entity_data in entities_data:
                try:
                    entity_type = entity_data.get("type")
                    if not entity_type:
                        continue
                        
                    entity = MessageEntity(
                        type=entity_type,
                        offset=entity_data.get("offset", 0),
                        length=entity_data.get("length", 0)
                    )
                    
                    # 设置可选属性
                    if "url" in entity_data and entity_data["url"]:
                        entity.url = entity_data["url"]
                        
                    if "user" in entity_data and entity_data["user"]:
                        # user属性需要特殊处理，这里简化处理
                        pass
                        
                    entities.append(entity)
                except Exception as e:
                    logger.warning(f"⚠️ 解析消息实体失败: {str(e)}")
            
            # 根据媒体类型创建媒体组件
            media_type = metadata.get("media_type")
            
            try:
                if media_type == "photo":
                    media_components.append(InputMediaPhoto(
                        media=file_id,
                        caption=caption,
                        caption_entities=entities
                    ))
                elif media_type == "video":
                    # 为视频生成缩略图
                    thumbnail = None
                    if os.path.exists(file_path):
                        thumbnail_path = self.generate_thumbnail(file_path)
                        if thumbnail_path:
                            thumbnail = thumbnail_path
                            
                    media_components.append(InputMediaVideo(
                        media=file_id,
                        caption=caption,
                        caption_entities=entities,
                        thumbnail=thumbnail,
                        supports_streaming=True
                    ))
                elif media_type == "audio":
                    media_components.append(InputMediaAudio(
                        media=file_id,
                        caption=caption,
                        caption_entities=entities
                    ))
                else:
                    # 默认作为文档处理
                    media_components.append(InputMediaDocument(
                        media=file_id,
                        caption=caption,
                        caption_entities=entities
                    ))
                    
                logger.info(f"✅ 成功准备消息 {msg_id} 的媒体组件，使用原始格式")
            except Exception as e:
                logger.error(f"❌ 准备媒体组件时出错: {str(e)}")
                # 使用默认文档格式作为备选
                media_components.append(InputMediaDocument(media=file_id))
                
        logger.info(f"✅ 已成功准备 {len(media_components)}/{len(file_paths)} 个媒体组件")
        return media_components

# 修改黑洞输出函数，完全屏蔽FFmpeg和MoviePy的输出
def silence_output():
    """创建一个上下文管理器来完全屏蔽标准输出和错误输出，特别适用于媒体处理工具"""
    import os
    import sys
    import io
    from contextlib import redirect_stdout, redirect_stderr
    
    # 创建黑洞文件对象
    null_io = io.StringIO()
    
    # 设置FFmpeg环境变量来静默输出
    old_ffmpeg_loglevel = os.environ.get("FFMPEG_LOGLEVEL", "")
    old_ffmpeg_silent = os.environ.get("FFMPEG_SILENT", "")
    old_imageio_ffmpeg = os.environ.get("IMAGEIO_FFMPEG_EXE", "")
    
    os.environ["FFMPEG_LOGLEVEL"] = "quiet"
    os.environ["FFMPEG_SILENT"] = "true"
    os.environ["IMAGEIO_FFMPEG_EXE"] = "ffmpeg"  # 确保使用系统FFmpeg
    
    # 创建重定向器
    stdout_redirect = redirect_stdout(null_io)
    stderr_redirect = redirect_stderr(null_io)
    
    class SilenceManager:
        def __enter__(self):
            # 进入上下文时应用重定向
            self.stdout_ctx = stdout_redirect.__enter__()
            self.stderr_ctx = stderr_redirect.__enter__()
            return self
            
        def __exit__(self, exc_type, exc_val, exc_tb):
            # 退出上下文时恢复原始输出
            self.stderr_ctx.__exit__(exc_type, exc_val, exc_tb)
            self.stdout_ctx.__exit__(exc_type, exc_val, exc_tb)
            
            # 恢复环境变量
            if old_ffmpeg_loglevel:
                os.environ["FFMPEG_LOGLEVEL"] = old_ffmpeg_loglevel
            if old_ffmpeg_silent:
                os.environ["FFMPEG_SILENT"] = old_ffmpeg_silent
            if old_imageio_ffmpeg:
                os.environ["IMAGEIO_FFMPEG_EXE"] = old_imageio_ffmpeg
    
    return SilenceManager() 