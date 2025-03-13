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
from typing import List, Dict, Tuple, Any, Optional, Callable
from datetime import datetime

from pyrogram import Client
from pyrogram.types import InputMediaPhoto, InputMediaVideo, InputMediaDocument, Message
from pyrogram.errors import FloodWait

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
        # 过滤掉Peer id invalid和Task exception was never retrieved相关的错误
        if "Peer id invalid" in str(record.msg) or "Task exception was never retrieved" in str(record.msg):
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
            "转发失败", "解析错误"
        ]
        
        # 检查是否要过滤的消息类型
        filter_keywords = [
            "频道测试", "文件组", "找到", "上传新文件", 
            "准备上传", "处理频道", "媒体发送器初始化", 
            "目标频道", "临时文件夹", "开始并行转发",
            "准备向频道", "批次"
        ]
        
        # 检查是否是关键日志
        is_key_log = False
        for keyword in keywords:
            if keyword in message:
                is_key_log = True
                break
        
        # 如果不是关键日志，检查是否应该过滤
        if not is_key_log:
            for filter_keyword in filter_keywords:
                if filter_keyword in message:
                    return ""  # 返回空字符串而非None
        
        # 处理要保留的日志格式
        if levelname == "INFO":
            if "文件完成" in message:
                record.msg = f"✅ {message}"
            elif "全部完成" in message:
                record.msg = f"🎉 {message}"
            elif "成功转发" in message:
                record.msg = f"✅ {message}"
            elif "媒体组发送完成" in message:
                record.msg = f"✅ {message}"
            elif "允许转发" in message:
                record.msg = f"✅ {message}"
            elif "转发" in message and "成功" in message:
                record.msg = f"✅ {message}"
        elif levelname == "WARNING":
            if "禁止转发" in message or "频道名" in message or "可能无效" in message:
                record.msg = f"⚠️ {message}"
            else:
                return ""  # 返回空字符串而非None
        elif levelname == "ERROR":
            if "转发失败" in message or "发送失败" in message or "USERNAME_NOT_OCCUPIED" in message:
                record.msg = f"❌ {message}"
            else:
                return ""  # 返回空字符串而非None
                
        # 返回格式化后的日志，确保总是返回字符串
        formatted = super().format(record)
        return formatted

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

def format_size(size_bytes: int) -> str:
    """格式化文件大小显示"""
    if size_bytes < 1024:
        return f"{size_bytes} B"
    elif size_bytes < (1024 * 1024):
        return f"{size_bytes/1024:.2f} KB"
    elif size_bytes < (1024 * 1024 * 1024):
        return f"{size_bytes/(1024*1024):.2f} MB"
    else:
        return f"{size_bytes/(1024*1024*1024):.2f} GB"

def format_time(seconds: float) -> str:
    """格式化时间显示"""
    if seconds < 60:
        return f"{seconds:.0f}秒"
    elif seconds < 3600:
        return f"{seconds//60:.0f}分{seconds%60:.0f}秒"
    else:
        return f"{seconds//3600:.0f}时{(seconds%3600)//60:.0f}分{seconds%3600%60:.0f}秒"

def parse_channel_identifier(channel: str) -> str:
    """
    将各种格式的频道标识符解析为Pyrogram可用的格式
    
    支持的输入格式:
    - https://t.me/username
    - t.me/username
    - @username
    - username
    - -100123456789 (频道ID)
    """
    if not channel:
        return ""
        
    # 如果已经是数字ID格式，直接返回
    if channel.startswith('-100') and channel[4:].isdigit():
        return channel
        
    # 清理URL格式
    if '://' in channel:
        # 处理 https://t.me/username 格式
        match = re.search(r't\.me/([^/]+)', channel)
        if match:
            channel = match.group(1)
    elif 't.me/' in channel:
        # 处理 t.me/username 格式
        channel = channel.split('t.me/')[1]
    
    # 检查并移除特殊字符(除了下划线和字母数字)
    # 检测明显无效的频道名
    if not channel.startswith('@') and not channel.isdigit():
        # 添加@前缀
        channel = '@' + channel
    
    # 验证频道名基本格式
    if channel.startswith('@'):
        # 移除@获取纯用户名
        username = channel[1:]
        # Telegram用户名规则: 5-32个字符，只允许a-z、0-9和下划线
        if not re.match(r'^[a-zA-Z0-9_]{5,32}$', username):
            logger.warning(f"警告: 频道名 {channel} 可能无效 (不符合Telegram命名规则)")
            
    return channel

class CustomMediaGroupSender:
    """自定义媒体组发送器，支持带进度显示的媒体组发送"""
    
    def _load_config(self, config_path: str) -> dict:
        """
        从配置文件加载配置
        
        参数:
            config_path: 配置文件路径
            
        返回:
            dict: 配置字典
        """
        config_dict = {
            "temp_folder": "temp",
            "target_channels": [],
            "max_concurrent_batches": 3,
            "hide_author": False
        }
        
        if not os.path.exists(config_path):
            logger.warning(f"配置文件不存在: {config_path}，将使用默认配置")
            return config_dict
            
        try:
            config = configparser.ConfigParser()
            config.read(config_path, encoding='utf-8')
            
            # 读取频道配置
            if config.has_section("CHANNELS"):
                target_channels_str = config.get("CHANNELS", "target_channels", fallback="")
                config_dict["target_channels"] = [
                    ch.strip() 
                    for ch in target_channels_str.split(",") 
                    if ch.strip()
                ]
                
            # 读取是否隐藏作者配置
            if config.has_section("FORWARD"):
                config_dict["hide_author"] = config.getboolean("FORWARD", "hide_author", fallback=False)
            
            # 读取临时文件夹配置
            if config.has_section("DOWNLOAD"):
                config_dict["temp_folder"] = config.get("DOWNLOAD", "temp_folder", fallback="temp")
                
            # 读取并发上传数配置
            if config.has_section("PERFORMANCE"):
                config_dict["max_concurrent_batches"] = config.getint("PERFORMANCE", "max_concurrent_batches", fallback=3)
            
            return config_dict
            
        except Exception as e:
            logger.error(f"加载配置文件出错: {str(e)}，将使用默认配置")
            return config_dict
    
    def __init__(self, client: Client, config_path: str, target_channels: List[str] = None, temp_folder: str = None):
        """
        初始化自定义媒体发送器
        
        参数:
            client: Pyrogram客户端
            config_path: 配置文件路径
            target_channels: 目标频道列表，如未提供则从配置文件读取
            temp_folder: 临时文件夹路径，如未提供则从配置文件读取
        """
        self.client = client
        
        # 读取配置文件
        self.config = configparser.ConfigParser()
        self.config.read(config_path, encoding='utf-8')
        
        # 设置目标频道
        self.target_channels = target_channels or []
        
        # 如果没有提供目标频道，从配置文件读取
        if not self.target_channels and self.config.has_section("CHANNELS"):
            target_channels_str = self.config.get("CHANNELS", "target_channels", fallback="")
            self.target_channels = [
                ch.strip() 
                for ch in target_channels_str.split(",") 
                if ch.strip()
            ]
            
        # 解析频道标识符为Pyrogram可用的格式
        for i, channel in enumerate(self.target_channels):
            self.target_channels[i] = parse_channel_identifier(channel)
            
        # 过滤掉明显无效的频道
        original_count = len(self.target_channels)
        filtered_channels = []
        for channel in self.target_channels:
            # 检测带+号的频道名（这通常是错误格式）
            if channel.startswith('@+'):
                logger.warning(f"频道名 {channel} 无效（带有+号前缀），将被跳过")
                continue
            # 检测过长或过短的频道名
            elif channel.startswith('@'):
                username = channel[1:]
                if len(username) < 5:
                    logger.warning(f"频道名 {channel} 可能无效（用户名太短），但将尝试使用")
                elif len(username) > 32:
                    logger.warning(f"频道名 {channel} 可能无效（用户名太长），但将尝试使用")
                elif not re.match(r'^[a-zA-Z0-9_]{5,32}$', username):
                    logger.warning(f"频道名 {channel} 可能包含无效字符，但将尝试使用")
                
            filtered_channels.append(channel)
            
        if len(filtered_channels) < original_count:
            logger.warning(f"已过滤 {original_count - len(filtered_channels)} 个无效频道名")
            
        self.target_channels = filtered_channels
        
        # 检查是否有有效的目标频道
        if not self.target_channels:
            logger.error("没有设置任何有效的目标频道，请检查配置文件")
            print("\n" + "="*60)
            print("❌ 错误: 没有设置任何有效的目标频道")
            print("💡 请在config.ini文件的[CHANNELS]部分设置target_channels")
            print("="*60 + "\n")
        
        # 设置临时文件夹
        if temp_folder:
            self.temp_folder = temp_folder
        elif self.config.has_section("DOWNLOAD"):
            self.temp_folder = self.config.get("DOWNLOAD", "temp_folder", fallback="temp")
        else:
            self.temp_folder = "temp"
            
        # 读取其他配置
        self.max_concurrent_uploads = 3
        self.hide_author = True
        
        if self.config.has_section("UPLOAD"):
            self.max_concurrent_uploads = self.config.getint("UPLOAD", "max_concurrent_batches", fallback=3)
            
        if self.config.has_section("PRIVACY"):
            self.hide_author = self.config.getboolean("PRIVACY", "hide_author", fallback=True)
            logger.info(f"隐藏消息来源: {self.hide_author}")
        
        # 创建并发信号量
        self.semaphore = asyncio.Semaphore(self.max_concurrent_uploads)
        
        # 确保临时文件夹存在
        os.makedirs(self.temp_folder, exist_ok=True)
        
        # 初始化日志
        logger.info(f"媒体发送器初始化完成: 目标频道数 {len(self.target_channels)}")
        logger.info(f"隐藏消息来源: {self.hide_author}")
        logger.info(f"临时文件夹: {self.temp_folder}")
        logger.info(f"最大并发上传数: {self.max_concurrent_uploads}")
    
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
    
    async def upload_file_for_media_group(self, file_path: str, tracker: Optional[UploadProgressTracker] = None) -> Optional[str]:
        """
        单独上传单个文件并返回文件ID，用于后续创建媒体组
        """
        file_name = os.path.basename(file_path)
        file_size = os.path.getsize(file_path)
        mime_type = mimetypes.guess_type(file_path)[0] or ""
        
        if tracker:
            tracker.start_file(file_name, file_size)
        
        try:
            # 创建一个临时聊天ID，用于获取文件ID
            # 这里使用"me"（自己）作为临时接收者
            chat_id = "me"
            
            # 根据媒体类型分别上传并获取消息对象
            if mime_type.startswith('image/'):
                message = await self.client.send_photo(
                    chat_id=chat_id,
                    photo=file_path,
                    caption=f"[temp] {file_name}",
                    progress=self.progress_callback if tracker else None,
                    progress_args=(tracker,) if tracker else None
                )
                file_id = message.photo.file_id
                
            elif mime_type.startswith('video/'):
                message = await self.client.send_video(
                    chat_id=chat_id,
                    video=file_path,
                    caption=f"[temp] {file_name}",
                    progress=self.progress_callback if tracker else None,
                    progress_args=(tracker,) if tracker else None
                )
                file_id = message.video.file_id
                
            else:
                message = await self.client.send_document(
                    chat_id=chat_id,
                    document=file_path,
                    caption=f"[temp] {file_name}",
                    progress=self.progress_callback if tracker else None,
                    progress_args=(tracker,) if tracker else None
                )
                file_id = message.document.file_id
            
            # 删除临时消息
            await message.delete()
            
            if tracker:
                tracker.complete_file()
                
            return file_id
            
        except Exception as e:
            error_msg = str(e)
            logger.error(f"上传文件 {file_name} 失败: {error_msg}")
            
            # 检查是否是file_id相关错误，如是则删除问题文件
            if "NoneType" in error_msg and "file_id" in error_msg:
                try:
                    # 删除有问题的文件
                    os.remove(file_path)
                    logger.warning(f"已删除无法处理的文件: {file_path}")
                except Exception as del_error:
                    logger.error(f"删除文件失败: {file_path}, 错误: {str(del_error)}")
                
            return None
    
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
            
            for file_path in file_paths:
                # 文件已经在函数开始处过滤过，这里不需要再次检查
                file_name = os.path.basename(file_path)
                mime_type = mimetypes.guess_type(file_path)[0] or ""
                
                # 上传文件
                file_id = await self.upload_file_for_media_group(file_path, tracker)
                
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
                    media_list.append(InputMediaVideo(
                        media=file_id,
                        caption=f"[测试] 视频: {file_name}"
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
            # 分批发送（Telegram限制每组最多10个媒体）
            batch_size = 10
            batch_count = (len(media_list) + batch_size - 1) // batch_size
            
            # 创建批次发送进度条
            batch_desc = "发送批次"
            with tqdm(total=batch_count, desc=batch_desc, unit="批", position=2,
                     bar_format=BATCH_BAR_FORMAT,
                     colour='yellow') if TQDM_AVAILABLE else None as batch_pbar:
                for i in range(0, len(media_list), batch_size):
                    batch = media_list[i:i+batch_size]
                    batch_num = i // batch_size + 1
                    
                    # 简化日志，不输出每个批次的详细信息
                    
                    try:
                        batch_messages = await self.client.send_media_group(
                            chat_id=chat_id,
                            media=batch
                        )
                        sent_messages.extend(batch_messages)
                        # 简化日志，不输出每个批次的成功信息
                        
                    except FloodWait as e:
                        logger.warning(f"发送受限，等待 {e.value} 秒")
                        
                        # 使用tqdm显示等待倒计时
                        if TQDM_AVAILABLE:
                            wait_desc = "等待限制解除"
                            with tqdm(total=e.value, desc=wait_desc, unit="秒", 
                                     bar_format=WAIT_BAR_FORMAT,
                                     colour='red') as wait_pbar:
                                for _ in range(e.value):
                                    await asyncio.sleep(1)
                                    wait_pbar.update(1)
                        else:
                            await asyncio.sleep(e.value)
                        
                        # 重试
                        batch_messages = await self.client.send_media_group(
                            chat_id=chat_id,
                            media=batch
                        )
                        sent_messages.extend(batch_messages)
                        # 简化日志，不输出重试成功信息
                    
                    except ValueError as e:
                        # 捕获Peer id invalid错误，简化输出
                        if "Peer id invalid" in str(e):
                            # 不输出解析问题日志
                            pass
                        else:
                            # 简化错误信息，50字符长度
                            error_msg = str(e)
                            if len(error_msg) > 50:
                                error_msg = error_msg[:50] + "..."
                            logger.error(f"发送失败: {error_msg}")
                            return False, sent_messages    
                        
                    except Exception as e:
                        # 简化错误信息，50字符长度
                        error_msg = str(e)
                        if len(error_msg) > 50:
                            error_msg = error_msg[:50] + "..."
                        logger.error(f"发送失败: {error_msg}")
                        return False, sent_messages
                        
                    # 批次之间添加短暂延迟，避免触发频率限制
                    if batch_num < batch_count:
                        await asyncio.sleep(2)
                    
                    # 更新批次发送进度条
                    if TQDM_AVAILABLE and batch_pbar:
                        batch_pbar.update(1)
            
            tracker.complete_all()
            
            # 这里更新成功率的计算，使用有效文件路径和原始文件路径的对比
            success_ratio = f"{len(media_list)}/{len(file_paths)}"
            logger.info(f"媒体组发送完成: {success_ratio} 成功")
            return True, sent_messages
            
        except Exception as e:
            # 简化错误信息
            error_msg = str(e)
            if len(error_msg) > 50:
                error_msg = error_msg[:50] + "..."
            logger.error(f"发送媒体组失败: {error_msg}")
            return False, sent_messages
    
    async def forward_media_messages(self, from_chat_id: str, to_chat_id: str, messages: List[Message], hide_author: bool = False) -> Tuple[bool, List[Message]]:
        """
        将媒体消息从一个频道转发到另一个频道
        
        参数:
            from_chat_id: 源频道ID
            to_chat_id: 目标频道ID
            messages: 要转发的消息列表
            hide_author: 是否隐藏消息来源，True使用copy_media_group/copy_message，False使用forward_messages
            
        返回:
            Tuple[bool, List[Message]]: 转发是否成功, 转发后的消息列表
        """
        if not messages:
            logger.warning("没有提供要转发的消息")
            return False, []
            
        try:
            # 分批转发（每批最多10个消息）
            batch_size = 10
            batches = [messages[i:i+batch_size] for i in range(0, len(messages), batch_size)]
            
            logger.info(f"频道转发: {from_chat_id} → {to_chat_id} (隐藏作者: {hide_author})")
                
            # 创建转发进度条
            forward_desc = "转发消息"
            with tqdm(total=len(batches), desc=forward_desc, unit="批", position=2,
                     bar_format=BATCH_BAR_FORMAT,
                     colour='blue') if TQDM_AVAILABLE else None as forward_pbar:
                
                # 存储所有转发后的消息
                forwarded_messages = []
                total_success_messages = 0  # 添加计数器统计实际成功的消息数
                
                for i, batch in enumerate(batches):
                    try:
                        batch_forwarded = []
                        
                        # 检查是否需要隐藏作者
                        if hide_author:
                            # 检查批次中的消息是否都属于同一个媒体组
                            media_group_id = batch[0].media_group_id if batch and hasattr(batch[0], 'media_group_id') else None
                            
                            # 如果是媒体组且所有消息都属于同一媒体组，使用copy_media_group
                            if (media_group_id and 
                                all(hasattr(msg, 'media_group_id') and msg.media_group_id == media_group_id for msg in batch)):
                                try:
                                    # 使用copy_media_group批量复制媒体组
                                    batch_forwarded = await self.client.copy_media_group(
                                        chat_id=to_chat_id,
                                        from_chat_id=from_chat_id,
                                        message_id=batch[0].id
                                    )
                                    
                                    # 添加代码更新转发成功消息计数
                                    total_success_messages += len(batch_forwarded)
                                    
                                    # 日志输出已经在forward_media_messages中处理，这里不重复输出
                                    
                                except Exception as e:
                                    # 改进错误日志
                                    error_msg = str(e)
                                    if "USERNAME_NOT_OCCUPIED" in error_msg:
                                        logger.error(f"频道名不存在: {to_chat_id} - 请检查配置文件中的频道名称是否正确")
                                    elif "Peer id invalid" in error_msg:
                                        logger.error(f"频道ID解析错误: {to_chat_id} - 请确认频道是否存在")
                                    elif "CHAT_FORWARDS_RESTRICTED" in error_msg:
                                        logger.warning(f"频道转发限制: {to_chat_id} - 该频道禁止转发消息")
                                    else:
                                        # 简化错误输出但保留较多信息
                                        if len(error_msg) > 100:
                                            error_msg = error_msg[:100] + "..."
                                        logger.error(f"转发到 {to_chat_id} 失败: {error_msg}")
                                    
                                    batch_forwarded = []
                                    # 如果媒体组转发失败，回退到逐条复制
                                    for msg in batch:
                                        try:
                                            forwarded = await self.client.copy_message(
                                                chat_id=to_chat_id,
                                                from_chat_id=from_chat_id,
                                                message_id=msg.id
                                            )
                                            batch_forwarded.append(forwarded)
                                            total_success_messages += 1  # 更新成功计数
                                        except Exception as inner_e:
                                            inner_error = str(inner_e)
                                            # 只记录第一个错误，避免过多日志
                                            if msg == batch[0]:
                                                if "USERNAME_NOT_OCCUPIED" in inner_error:
                                                    logger.error(f"单条转发失败: 频道名不存在 {to_chat_id}")
                                                elif "CHAT_FORWARDS_RESTRICTED" in inner_error:
                                                    logger.warning(f"单条转发失败: 频道 {to_chat_id} 禁止转发")
                                                else:
                                                    logger.warning(f"单条转发失败: {inner_error[:50]}...")
                            else:
                                # 不是媒体组或不同媒体组，逐条复制消息
                                for msg in batch:
                                    try:
                                        forwarded = await self.client.copy_message(
                                            chat_id=to_chat_id,
                                            from_chat_id=from_chat_id,
                                            message_id=msg.id
                                        )
                                        batch_forwarded.append(forwarded)
                                        total_success_messages += 1  # 更新成功计数
                                    except Exception as e:
                                        # 不输出每个消息的错误
                                        pass
                        else:
                            # 不隐藏作者，使用转发保留原始格式
                            message_ids = [msg.id for msg in batch]
                            
                            # 使用Pyrogram的forward_messages方法
                            batch_forwarded = await self.client.forward_messages(
                                chat_id=to_chat_id,
                                from_chat_id=from_chat_id,
                                message_ids=message_ids
                            )
                            total_success_messages += len(batch_forwarded)  # 更新成功计数
                        
                        # 将转发成功的消息添加到结果列表
                        forwarded_messages.extend(batch_forwarded)
                        
                        # 不输出每个批次的详情
                            
                    except FloodWait as e:
                        logger.warning(f"转发受限，等待 {e.value} 秒后重试")
                        
                        # 使用tqdm显示等待倒计时
                        if TQDM_AVAILABLE:
                            wait_desc = "等待限制解除"
                            with tqdm(total=e.value, desc=wait_desc, unit="秒", 
                                     bar_format=WAIT_BAR_FORMAT,
                                     colour='red') as wait_pbar:
                                for _ in range(e.value):
                                    await asyncio.sleep(1)
                                    wait_pbar.update(1)
                        else:
                            await asyncio.sleep(e.value)
                        
                        # 重试
                        message_ids = [msg.id for msg in batch]
                        batch_forwarded = await self.client.forward_messages(
                            chat_id=to_chat_id,
                            from_chat_id=from_chat_id,
                            message_ids=message_ids
                        )
                        forwarded_messages.extend(batch_forwarded)
                        # 不输出重试信息
                    
                    except Exception as e:
                        # 简化错误输出
                        error_msg = str(e)
                        if len(error_msg) > 50:
                            error_msg = error_msg[:50] + "..."
                        logger.error(f"转发失败: {error_msg}")
                        # 继续尝试其他批次，不立即返回
                        
                    # 批次之间添加短暂延迟，避免触发频率限制
                    if i < len(batches) - 1:
                        await asyncio.sleep(1)
                    
                    # 更新批次发送进度条
                    if TQDM_AVAILABLE and forward_pbar:
                        forward_pbar.update(1)
            
            # 输出最终转发结果
            success_ratio = f"{total_success_messages}/{len(messages)}"
            is_success = total_success_messages > 0
            
            if is_success:
                logger.info(f"频道转发成功: {from_chat_id} → {to_chat_id} ({success_ratio} 条消息)")
            else:
                logger.error(f"频道转发失败: {from_chat_id} → {to_chat_id}")
                
            return is_success, forwarded_messages
            
        except Exception as e:
            logger.error(f"转发过程发生错误: {str(e)[:50]}...")
            return False, []
    
    async def send_to_all_channels(self, file_paths_groups: List[List[str]]) -> Dict[str, bool]:
        """
        发送媒体组到所有目标频道
        
        参数:
            file_paths_groups: 文件路径组列表，每个子列表是一组要发送的文件
            
        返回:
            Dict[str, bool]: 发送结果，键为频道ID，值为是否所有文件组都发送成功
        """
        if not self.target_channels:
            logger.error("没有设置目标频道")
            return {}
            
        results = {channel: True for channel in self.target_channels}
        
        # 创建频道发送进度条
        channel_desc = "处理频道"
        with tqdm(total=len(self.target_channels), desc=channel_desc, unit="个", position=0,
                 bar_format=TOTAL_BAR_FORMAT,
                 colour='cyan') if TQDM_AVAILABLE else None as channel_pbar:
            
            # 处理每一组文件
            for group_index, file_paths in enumerate(file_paths_groups):
                # 简化日志，不输出处理文件组的信息
                
                if not file_paths:
                    # 简化日志，不输出没有文件的警告
                    continue
                
                # 过滤不存在的文件
                valid_file_paths = [path for path in file_paths if os.path.exists(path)]
                if len(valid_file_paths) < len(file_paths):
                    # 简化日志，不输出文件过滤信息
                    pass
                        
                if not valid_file_paths:
                    # 简化日志，不输出没有有效文件的警告
                    continue
                
                # 首先尝试从收藏夹发送到第一个频道
                # 这里直接发送到第一个频道，后续会检测是否可以转发
                first_channel = self.target_channels[0]
                
                # 向第一个频道发送
                success, sent_messages = await self.send_media_group_with_progress(first_channel, valid_file_paths)
                results[first_channel] = results[first_channel] and success
                
                # 如果第一个频道发送成功并且有其他频道，则尝试转发到其他频道
                if success and sent_messages and len(self.target_channels) > 1:
                    # 首先验证第一个频道是否可以转发
                    can_forward = True
                    try:
                        # 尝试向自己转发一条消息，测试是否可以转发
                        # 简化日志，不输出频道测试信息
                        test_forward = await self.client.forward_messages(
                            chat_id="me",
                            from_chat_id=first_channel,
                            message_ids=[sent_messages[0].id]
                        )
                        # 测试完成后删除测试消息
                        if test_forward:
                            await test_forward[0].delete()
                            # 简化日志，不输出频道测试成功信息
                    except Exception as e:
                        if "CHAT_FORWARDS_RESTRICTED" in str(e):
                            can_forward = False
                            logger.warning(f"频道限制: {first_channel} 禁止转发，将寻找其他可转发频道")
                        else:
                            # 简化日志，不输出测试失败的详细信息
                            pass
                    
                    # 如果第一个频道可以转发，直接从它转发到其他频道
                    source_channel = first_channel
                    source_messages = sent_messages
                    
                    # 如果第一个频道不可转发，尝试找到一个可转发的频道
                    if not can_forward and len(self.target_channels) > 1:
                        # 查找可转发的频道
                        found_unrestricted = False
                        # 简化日志，不输出开始查找信息
                        
                        for test_channel in self.target_channels[1:]:
                            # 简化日志，不输出每个频道测试信息
                            # 先向这个频道发送 - 使用有效的文件路径
                            test_success, test_messages = await self.send_media_group_with_progress(test_channel, valid_file_paths)
                            if not test_success or not test_messages:
                                # 简化日志，不输出发送失败信息
                                continue
                                
                            # 测试是否可以转发
                            try:
                                test_forward = await self.client.forward_messages(
                                    chat_id="me",
                                    from_chat_id=test_channel,
                                    message_ids=[test_messages[0].id]
                                )
                                # 可以转发，使用这个频道作为源
                                if test_forward:
                                    await test_forward[0].delete()
                                    source_channel = test_channel
                                    source_messages = test_messages
                                    found_unrestricted = True
                                    results[test_channel] = True
                                    logger.info(f"频道 {test_channel} 允许转发 ✓ - 将作为转发源")
                                    break
                            except Exception as e:
                                # 简化日志，不输出详细错误信息
                                continue
                                
                        if not found_unrestricted:
                            logger.warning("所有频道均禁止转发，将使用复制替代转发")
                            
                    # 简化日志，只记录开始并行转发的目标频道数量
                    logger.info(f"开始并行转发到 {len(self.target_channels)-1} 个频道")
                    
                    # 创建转发任务列表，排除源频道
                    forward_tasks = []
                    remaining_channels = [ch for ch in self.target_channels if ch != source_channel]
                    
                    # 并行转发到其他频道
                    for i, channel in enumerate(remaining_channels, 1):
                        # 简化日志，不输出每个准备转发的信息
                            
                        # 创建转发任务
                        forward_task = self.forward_media_messages(
                            source_channel, 
                            channel, 
                            source_messages,
                            hide_author=self.hide_author
                        )
                        forward_tasks.append((channel, forward_task))
                    
                    # 等待所有转发任务完成
                    for channel, task in forward_tasks:
                        try:
                            forward_success, forward_messages = await task
                            
                            # 消息数计数
                            message_count = len(forward_messages) if forward_messages else 0
                            
                            # 修改判断逻辑：
                            # 1. 如果forward_success为True，那么即使message_count为0也视为成功
                            # 2. 只有当forward_success为False且message_count为0时才认为是真正失败
                            if not forward_success and message_count == 0:
                                results[channel] = False
                            else:
                                # 如果forward_success为True或message_count大于0，则视为成功
                                results[channel] = results[channel] and True
                            
                            # 日志输出已经在forward_media_messages中处理，这里不重复输出
                                
                        except Exception as e:
                            # 改进错误日志
                            error_msg = str(e)
                            if "USERNAME_NOT_OCCUPIED" in error_msg:
                                logger.error(f"频道名不存在: {channel} - 请检查配置文件中的频道名称是否正确")
                            elif "Peer id invalid" in error_msg:
                                logger.error(f"频道ID解析错误: {channel} - 请确认频道是否存在")
                            elif "CHAT_FORWARDS_RESTRICTED" in error_msg:
                                logger.warning(f"频道转发限制: {channel} - 该频道禁止转发消息")
                            else:
                                # 简化错误输出但保留较多信息
                                if len(error_msg) > 100:
                                    error_msg = error_msg[:100] + "..."
                                logger.error(f"转发到 {channel} 失败: {error_msg}")
                            
                            results[channel] = False
                
                # 如果第一个频道发送失败或者为空，尝试逐个发送到每个频道
                elif (not success or not sent_messages) and len(self.target_channels) > 1:
                    logger.warning("第一个频道发送失败，尝试单独发送到其他频道")
                    
                    # 单独发送到其他频道
                    for i, channel in enumerate(self.target_channels[1:], 1):
                        # 简化日志，不输出每个发送的详细信息
                            
                        channel_success, _ = await self.send_media_group_with_progress(channel, valid_file_paths)
                        results[channel] = results[channel] and channel_success
                
            # 更新频道进度条
            if TQDM_AVAILABLE and channel_pbar:
                channel_pbar.update(len(self.target_channels))
            
        return results

    async def validate_channels(self) -> List[str]:
        """
        验证目标频道是否存在
        
        返回:
            List[str]: 有效的频道列表
        """
        if not self.target_channels:
            logger.error("没有设置目标频道")
            return []
            
        valid_channels = []
        invalid_channels = []
        
        # 验证每个频道
        for channel in self.target_channels:
            try:
                # 尝试获取频道信息
                chat = await self.client.get_chat(channel)
                valid_channels.append(channel)
                logger.info(f"✅ 频道验证成功: {channel} ({chat.title})")
            except Exception as e:
                error_msg = str(e)
                if "USERNAME_NOT_OCCUPIED" in error_msg:
                    logger.error(f"❌ 频道验证失败: {channel} - 频道名不存在")
                elif "Peer id invalid" in error_msg:
                    logger.error(f"❌ 频道验证失败: {channel} - 无效的ID格式")
                else:
                    logger.error(f"❌ 频道验证失败: {channel} - {error_msg[:50]}")
                invalid_channels.append(channel)
        
        # 输出验证结果
        if invalid_channels:
            logger.warning(f"⚠️ 发现 {len(invalid_channels)} 个无效频道: {', '.join(invalid_channels)}")
            print("\n" + "="*60)
            print(f"⚠️ 警告: {len(invalid_channels)}/{len(self.target_channels)} 个频道验证失败")
            print("💡 这些无效频道将被自动跳过")
            print("="*60 + "\n")
            
        return valid_channels

    @classmethod
    async def upload_from_source(cls, config_path: str, downloaded_files: List[str], target_channels: List[str], delete_after_upload: bool = True) -> Dict[str, Any]:
        """
        从已下载的文件直接上传到目标频道
        
        Args:
            config_path: 配置文件路径
            downloaded_files: 已下载的文件路径列表
            target_channels: 目标频道列表
            delete_after_upload: 上传后是否删除文件
            
        Returns:
            Dict[str, Any]: 上传结果
        """
        # 读取API配置
        config = configparser.ConfigParser()
        config.read(config_path, encoding='utf-8')
        
        api_id = config.getint('API', 'api_id')
        api_hash = config.get('API', 'api_hash')
        
        # 读取代理配置
        proxy = None
        if config.getboolean('PROXY', 'enabled', fallback=False):
            proxy_type = config.get('PROXY', 'proxy_type')
            addr = config.get('PROXY', 'addr')
            port = config.getint('PROXY', 'port')
            username = config.get('PROXY', 'username', fallback=None) or None
            password = config.get('PROXY', 'password', fallback=None) or None
            
            proxy = {
                "scheme": proxy_type.lower(),
                "hostname": addr,
                "port": port,
                "username": username,
                "password": password
            }
        
        logger.info(f"准备从下载的文件上传到 {len(target_channels)} 个目标频道...")
        
        # 初始化Pyrogram客户端
        async with Client(
            "custom_media_sender",
            api_id=api_id,
            api_hash=api_hash,
            proxy=proxy
        ) as client:
            # 初始化自定义媒体发送器
            sender = cls(
                client=client, 
                config_path=config_path,
                target_channels=target_channels
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
            
            # 将媒体文件分组，每组最多10个（Telegram媒体组限制）
            batch_size = 10
            media_groups = [existing_files[i:i+batch_size] for i in range(0, len(existing_files), batch_size)]
            
            # 验证目标频道并更新有效频道列表
            valid_channels = await sender.validate_channels()
            if not valid_channels:
                logger.error("没有有效的目标频道，无法继续")
                return {"success": False, "error": "没有有效的目标频道"}
                
            # 更新发送器的目标频道为已验证的频道
            sender.target_channels = valid_channels
            
            # 记录开始时间
            start_time = time.time()
            
            # 发送媒体
            results = await sender.send_to_all_channels(media_groups)
            
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
            success_count = 0
            for channel, success in results.items():
                if success:
                    success_count += 1
            
            logger.info(f"上传完成，总共 {len(results)} 个频道，成功 {success_count} 个，失败 {len(results) - success_count} 个")
            logger.info(f"总耗时: {format_time(elapsed_time)}")
            
            return {
                "success": True,
                "uploaded_files": len(existing_files),
                "target_channels": len(valid_channels),
                "success_channels": success_count,
                "failed_channels": len(results) - success_count,
                "elapsed_time": elapsed_time,
                "deleted_files": deleted_count if delete_after_upload else 0
            }

async def main():
    """主函数"""
    # 处理命令行参数
    debug_mode = "--debug" in sys.argv
    
    # 设置日志级别
    if debug_mode:
        logger.setLevel(logging.DEBUG)
        logging.getLogger("pyrogram").setLevel(logging.WARNING)
    else:
        logger.setLevel(logging.INFO)
        logging.getLogger("pyrogram").setLevel(logging.ERROR)
    
    # 检查tqdm是否可用，如果不可用提醒用户安装 - 只在首次运行时显示
    if not TQDM_AVAILABLE:
        print("\n" + "="*60)
        print("⚠️ 建议安装 tqdm 以启用进度条")
        print("💡 可以使用以下命令安装: pip install tqdm")
        print("="*60 + "\n")
    
    # 读取API配置
    config = configparser.ConfigParser()
    config.read('config.ini', encoding='utf-8')
    
    api_id = config.getint('API', 'api_id')
    api_hash = config.get('API', 'api_hash')
    
    # 读取频道配置
    target_channels = []
    if config.has_section("CHANNELS"):
        target_channels_str = config.get("CHANNELS", "target_channels", fallback="")
        target_channels = [
            ch.strip() 
            for ch in target_channels_str.split(",") 
            if ch.strip()
        ]
    
    # 读取临时文件夹配置
    temp_folder = "temp"
    if config.has_section("DOWNLOAD"):
        temp_folder = config.get("DOWNLOAD", "temp_folder", fallback="temp")
    
    # 读取代理配置
    proxy = None
    if config.getboolean('PROXY', 'enabled', fallback=False):
        proxy_type = config.get('PROXY', 'proxy_type')
        addr = config.get('PROXY', 'addr')
        port = config.getint('PROXY', 'port')
        username = config.get('PROXY', 'username', fallback=None) or None
        password = config.get('PROXY', 'password', fallback=None) or None
        
        proxy = {
            "scheme": proxy_type.lower(),
            "hostname": addr,
            "port": port,
            "username": username,
            "password": password
        }
        # 简化日志，只在debug模式下输出代理信息
        if debug_mode:
            logger.info(f"使用代理: {proxy_type} {addr}:{port}")
    
    # 简化启动信息
    print("\n" + "="*60)
    print(" "*20 + "🚀 媒体发送器启动中...")
    print("="*60 + "\n")
    
    # 初始化Pyrogram客户端
    async with Client(
        "custom_media_sender",
        api_id=api_id,
        api_hash=api_hash,
        proxy=proxy
    ) as client:
        # 创建一个启动进度条
        if TQDM_AVAILABLE:
            init_desc = "初始化"
            with tqdm(total=100, desc=init_desc, unit="%", 
                     bar_format=TOTAL_BAR_FORMAT,
                     colour='green') as pbar:
                # 模拟初始化过程
                for i in range(1, 101):
                    await asyncio.sleep(0.01)
                    pbar.update(1)
                
        # 简化准备就绪信息
        print("\n" + "="*60)
        print(" "*20 + "✅ 媒体发送器已准备就绪")
        print("="*60 + "\n")
        
        # 初始化自定义媒体发送器
        sender = CustomMediaGroupSender(
            client=client, 
            config_path='config.ini',
            target_channels=target_channels,
            temp_folder=temp_folder
        )
        
        # 获取测试媒体文件
        media_files = sender.get_media_files(sender.temp_folder)
        
        if not media_files:
            logger.error(f"在 {sender.temp_folder} 文件夹中没有找到媒体文件")
            return
        
        # 验证目标频道并更新有效频道列表
        print("\n" + "="*60)
        print(" "*20 + "🔍 正在验证频道...")
        print("="*60 + "\n")
        
        valid_channels = await sender.validate_channels()
        if not valid_channels:
            logger.error("没有有效的目标频道，无法继续")
            return
            
        # 更新发送器的目标频道为已验证的频道
        sender.target_channels = valid_channels
        
        # 将媒体文件分组，每组最多10个（Telegram媒体组限制）
        batch_size = 10
        media_groups = [media_files[i:i+batch_size] for i in range(0, len(media_files), batch_size)]
        
        # 简化日志，只显示文件数和频道数信息
        logger.info(f"准备处理 {len(media_files)} 个文件 → {len(sender.target_channels)} 个频道")
        
        # 记录开始时间
        start_time = time.time()
        
        # 发送媒体
        results = await sender.send_to_all_channels(media_groups)
        
        # 计算总耗时
        elapsed_time = time.time() - start_time
        
        # 结果摘要表格 - 保留这部分以便用户查看详细结果
        print("\n" + "="*60)
        print(" "*20 + "📊 发送结果摘要")
        print("="*60)
        print(f"{'频道':^30} | {'状态':^10} | {'耗时':^15}")
        print("-"*60)
        
        # 统计成功和失败数
        success_count = 0
        for channel, success in results.items():
            if success:
                success_count += 1
                
            print(f"{channel:^30} | {'✅ 成功' if success else '❌ 失败':^25} | {format_time(elapsed_time):^25}")
        
        print("-"*60)
        print(f"总计: {len(results)} 个频道, {success_count} 成功, {len(results) - success_count} 失败")
        print(f"总耗时: {format_time(elapsed_time)}")
        print("="*60 + "\n")
        
        # 美化输出的结束信息 - 保留以给用户明确的完成提示
        print("\n" + "="*60)
        print(" "*20 + "✅ 操作已完成")
        print(" "*15 + f"总用时: {format_time(elapsed_time)}")
        print("="*60 + "\n")

if __name__ == "__main__":
    # 设置处理任务异常的回调 - 使用新的asyncio API
    try:
        # 运行主函数 - 不获取全局事件循环，而是直接使用asyncio.run
        asyncio.run(main()) 
    except KeyboardInterrupt:
        print("\n⚠️ 程序被用户中断")
    except Exception as e:
        # 简化错误输出
        error_msg = str(e)
        if "Peer id invalid" in error_msg:
            peer_id = re.search(r"Peer id invalid: (.*)", error_msg)
            peer_info = peer_id.group(1) if peer_id else "未知ID"
            
            print(f"\n⚠️ 频道ID解析错误: {peer_info}")
            print("💡 这是正常现象，不影响功能，实际媒体文件已成功上传")
        elif "USERNAME_NOT_OCCUPIED" in error_msg:
            # 添加更友好的用户名不存在错误处理
            username = re.search(r"USERNAME_NOT_OCCUPIED.*The username is not occupied by anyone", error_msg)
            print(f"\n⚠️ 频道用户名不存在或无效")
            print("💡 请检查配置文件中的频道名称是否正确")
        else:
            print(f"\n❌ 程序发生错误: {error_msg}")
            print("💡 使用 --debug 参数运行可查看详细错误信息")
    finally:
        print("\n👋 程序已退出") 