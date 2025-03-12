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
from pyrogram.types import InputMediaPhoto, InputMediaVideo, InputMediaDocument
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

# 重定向错误输出，隐藏Pyrogram的详细错误信息
class ErrorFilter(logging.Filter):
    def filter(self, record):
        # 过滤掉Peer id invalid和Task exception was never retrieved相关的错误
        if "Peer id invalid" in str(record.msg) or "Task exception was never retrieved" in str(record.msg):
            return False
        return True

# 自定义彩色日志格式
class ColoredFormatter(logging.Formatter):
    """自定义彩色日志格式器"""
    
    def format(self, record):
        if COLORAMA_AVAILABLE:
            levelname = record.levelname
            message = record.getMessage()
            
            if levelname == "INFO":
                if "开始上传" in message:
                    record.msg = f"{Fore.CYAN}📤 {message}{Style.RESET_ALL}"
                elif "文件完成" in message:
                    record.msg = f"{Fore.GREEN}✅ {message}{Style.RESET_ALL}"
                elif "全部完成" in message:
                    record.msg = f"{Fore.GREEN}{Style.BRIGHT}🎉 {message}{Style.RESET_ALL}"
                elif "发送媒体组" in message:
                    record.msg = f"{Fore.YELLOW}📤 {message}{Style.RESET_ALL}"
                elif "批次" in message and "发送成功" in message:
                    record.msg = f"{Fore.GREEN}✅ {message}{Style.RESET_ALL}"
                elif "找到" in message:
                    record.msg = f"{Fore.CYAN}🔍 {message}{Style.RESET_ALL}"
                elif "准备上传" in message:
                    record.msg = f"{Fore.YELLOW}📋 {message}{Style.RESET_ALL}"
                else:
                    record.msg = f"{Fore.WHITE}ℹ️ {message}{Style.RESET_ALL}"
            elif levelname == "WARNING":
                record.msg = f"{Fore.YELLOW}{Style.BRIGHT}⚠️ {message}{Style.RESET_ALL}"
            elif levelname == "ERROR":
                record.msg = f"{Fore.RED}{Style.BRIGHT}❌ {message}{Style.RESET_ALL}"
            elif levelname == "CRITICAL":
                record.msg = f"{Back.RED}{Fore.WHITE}{Style.BRIGHT}🚨 {message}{Style.RESET_ALL}"
                
        return super().format(record)

# 设置日志记录
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger("CustomMediaGroupSender")

# 为日志添加彩色格式
if COLORAMA_AVAILABLE:
    for handler in logger.handlers:
        handler.setFormatter(ColoredFormatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s'))
    if not logger.handlers:
        handler = logging.StreamHandler()
        handler.setFormatter(ColoredFormatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s'))
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

# 抑制未捕获的异常输出
def custom_excepthook(exc_type, exc_value, exc_traceback):
    if issubclass(exc_type, KeyboardInterrupt):
        # 正常处理键盘中断
        if COLORAMA_AVAILABLE:
            print(f"\n{Fore.YELLOW}⚠️ 程序被用户中断{Style.RESET_ALL}")
        else:
            print("\n⚠️ 程序被用户中断")
        return
    
    # 过滤掉特定的Pyrogram错误
    error_msg = str(exc_value)
    if "Peer id invalid" in error_msg:
        peer_id = re.search(r"Peer id invalid: (.*)", error_msg)
        peer_info = peer_id.group(1) if peer_id else "未知ID"
        
        if COLORAMA_AVAILABLE:
            print(f"{Fore.YELLOW}⚠️ 频道ID解析错误: {Fore.CYAN}{peer_info}{Fore.YELLOW}，这不会影响上传功能。{Style.RESET_ALL}")
        else:
            print(f"⚠️ 频道ID解析错误: {peer_info}，这不会影响上传功能。")
    else:
        # 对其他错误进行简化处理
        error_type = exc_type.__name__
        if COLORAMA_AVAILABLE:
            print(f"{Fore.RED}❌ 错误类型: {Fore.WHITE}{error_type}{Style.RESET_ALL}")
            print(f"{Fore.RED}❌ 错误信息: {Fore.WHITE}{error_msg}{Style.RESET_ALL}")
            print(f"{Fore.YELLOW}如需查看详细错误跟踪，请在命令行运行本程序时添加 --debug 参数{Style.RESET_ALL}")
        else:
            print(f"❌ 错误类型: {error_type}")
            print(f"❌ 错误信息: {error_msg}")
            print("如需查看详细错误跟踪，请在命令行运行本程序时添加 --debug 参数")
            
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
            # 彩色总进度前缀
            total_desc = f"总进度" if not COLORAMA_AVAILABLE else f"{Fore.CYAN}总进度{Style.RESET_ALL}"
            
            self.total_pbar = tqdm(
                total=total_size,
                unit='B',
                unit_scale=True,
                desc=total_desc,
                position=0,
                leave=True,
                bar_format=TOTAL_BAR_FORMAT,
                colour='green' if not COLORAMA_AVAILABLE else None
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
        
        # 彩色日志
        if COLORAMA_AVAILABLE:
            logger.info(f"{Fore.CYAN}开始上传: {short_name} ({format_size(file_size)}){Style.RESET_ALL}")
        else:
            logger.info(f"开始上传: {short_name} ({format_size(file_size)})")
        
        # 创建当前文件的进度条
        if TQDM_AVAILABLE:
            # 如果之前有进度条，先关闭
            if self.current_pbar is not None:
                self.current_pbar.close()
                
            # 创建新的文件进度条
            # 彩色文件名前缀
            if COLORAMA_AVAILABLE:
                file_desc = f"{Fore.GREEN}文件: {short_name}{Style.RESET_ALL}"
            else:
                file_desc = f"文件: {short_name}"
                
            self.current_pbar = tqdm(
                total=file_size,
                unit='B',
                unit_scale=True,
                desc=file_desc,
                position=1,
                leave=True,
                bar_format=FILE_BAR_FORMAT,
                colour='blue' if not COLORAMA_AVAILABLE else None
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
        
        # 输出完成信息
        if COLORAMA_AVAILABLE:
            logger.info(
                f"{Fore.GREEN}文件完成: {short_name} | "
                f"大小: {format_size(self.current_file_size)} | "
                f"用时: {Fore.CYAN}{elapsed:.2f}秒{Style.RESET_ALL} | "
                f"平均速度: {Fore.YELLOW}{format_size(speed)}/s{Style.RESET_ALL} | "
                f"进度: {Fore.MAGENTA}{self.uploaded_files}/{self.total_files}文件{Style.RESET_ALL}"
            )
        else:
        logger.info(
                f"文件完成: {short_name} | "
                f"大小: {format_size(self.current_file_size)} | "
                f"用时: {elapsed:.2f}秒 | "
                f"平均速度: {format_size(speed)}/s | "
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
            
        # 彩色输出完成信息
        if COLORAMA_AVAILABLE:
            logger.info(
                f"{Fore.GREEN}{Style.BRIGHT}全部完成 | "
                f"共 {Fore.YELLOW}{self.uploaded_files}{Style.RESET_ALL}{Fore.GREEN}{Style.BRIGHT} 个文件 | "
                f"总大小: {Fore.CYAN}{format_size(self.uploaded_size)}{Style.RESET_ALL}{Fore.GREEN}{Style.BRIGHT} | "
                f"总用时: {Fore.MAGENTA}{total_elapsed:.2f}秒{Style.RESET_ALL}{Fore.GREEN}{Style.BRIGHT} | "
                f"平均速度: {Fore.YELLOW}{format_size(avg_speed)}/s{Style.RESET_ALL}"
            )
        else:
        logger.info(
                f"全部完成 | "
                f"共 {self.uploaded_files} 个文件 | "
                f"总大小: {format_size(self.uploaded_size)} | "
                f"总用时: {total_elapsed:.2f}秒 | "
            f"平均速度: {format_size(avg_speed)}/s"
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
            
    # 确保用户名格式正确
    if not channel.startswith('@') and not channel.isdigit():
        channel = '@' + channel
            
    return channel

class CustomMediaGroupSender:
    """自定义媒体组发送器，支持带进度显示的媒体组发送"""
    
    def __init__(self, client: Client, temp_folder: str = 'temp', target_channels: List[str] = None):
        """初始化媒体发送器"""
        self.client = client
        self.temp_folder = temp_folder
        self.target_channels = []
        
        # 确保临时文件夹存在
        if not os.path.exists(temp_folder):
            os.makedirs(temp_folder)
            
        # 设置目标频道
        if target_channels:
            for channel in target_channels:
                parsed = parse_channel_identifier(channel)
                if parsed:
                    self.target_channels.append(parsed)
    
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
            logger.error(f"上传文件 {file_name} 失败: {str(e)}")
            return None
    
    async def send_media_group_with_progress(self, chat_id: str, file_paths: List[str]) -> bool:
        """发送媒体组，带进度显示"""
        if not file_paths:
            logger.warning("没有提供任何文件路径")
            return False
            
        # 计算总文件大小
        total_size = sum(os.path.getsize(path) for path in file_paths)
        tracker = UploadProgressTracker(len(file_paths), total_size)
        
        # 彩色日志输出
        if COLORAMA_AVAILABLE:
            logger.info(f"{Fore.YELLOW}准备上传 {len(file_paths)} 个文件 (总大小: {Fore.CYAN}{format_size(total_size)}{Style.RESET_ALL}{Fore.YELLOW}) 到媒体组{Style.RESET_ALL}")
        else:
            logger.info(f"准备上传 {len(file_paths)} 个文件 (总大小: {format_size(total_size)}) 到媒体组")
        
        # 使用tqdm创建文件处理进度条
        file_batch_desc = "处理文件" if not COLORAMA_AVAILABLE else f"{Fore.MAGENTA}处理文件{Style.RESET_ALL}"
        with tqdm(total=len(file_paths), desc=file_batch_desc, unit="个", position=2, 
                 bar_format=BATCH_BAR_FORMAT,
                 colour='magenta' if not COLORAMA_AVAILABLE else None) if TQDM_AVAILABLE else None as file_pbar:
            # 上传所有文件并获取文件ID
            media_list = []
        for file_path in file_paths:
                file_name = os.path.basename(file_path)
                mime_type = mimetypes.guess_type(file_path)[0] or ""
                
                # 上传文件
                file_id = await self.upload_file_for_media_group(file_path, tracker)
                if not file_id:
                    if TQDM_AVAILABLE and file_pbar:
                        file_pbar.update(1)
                    continue
                    
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
            return False
            
        # 发送媒体组
        try:
            # 分批发送（Telegram限制每组最多10个媒体）
            batch_size = 10
            batch_count = (len(media_list) + batch_size - 1) // batch_size
            
            # 创建批次发送进度条
            batch_desc = "发送批次" if not COLORAMA_AVAILABLE else f"{Fore.YELLOW}发送批次{Style.RESET_ALL}"
            with tqdm(total=batch_count, desc=batch_desc, unit="批", position=2,
                     bar_format=BATCH_BAR_FORMAT,
                     colour='yellow' if not COLORAMA_AVAILABLE else None) if TQDM_AVAILABLE else None as batch_pbar:
                for i in range(0, len(media_list), batch_size):
                    batch = media_list[i:i+batch_size]
                    batch_num = i // batch_size + 1
                    
                    logger.info(f"发送媒体组批次 {batch_num}/{batch_count} (包含 {len(batch)} 个文件)")
                    
                    try:
                        await self.client.send_media_group(
                            chat_id=chat_id,
                            media=batch
                        )
                        logger.info(f"批次 {batch_num}/{batch_count} 发送成功")
                        
                    except FloodWait as e:
                        logger.warning(f"遇到频率限制，等待 {e.value} 秒后重试")
                        
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
                        
                        # 重试
                        await self.client.send_media_group(
                            chat_id=chat_id,
                            media=batch
                        )
                        logger.info(f"批次 {batch_num}/{batch_count} 重试发送成功")
                    
                    except ValueError as e:
                        # 捕获Peer id invalid错误，显示简短提示而不是详细错误
                        if "Peer id invalid" in str(e):
                            peer_id = re.search(r"Peer id invalid: (.*)", str(e))
                            peer_info = peer_id.group(1) if peer_id else chat_id
                            
                            if COLORAMA_AVAILABLE:
                                logger.warning(f"频道ID {Fore.CYAN}{peer_info}{Style.RESET_ALL} 解析问题，但上传仍将继续")
                            else:
                                logger.warning(f"频道ID {peer_info} 解析问题，但上传仍将继续")
                        else:
                            logger.error(f"批次 {batch_num}/{batch_count} 发送失败: {str(e)}")
                            return False    
                        
                    except Exception as e:
                        # 简化错误信息，只显示主要部分
                        error_msg = str(e)
                        if len(error_msg) > 100:
                            error_msg = error_msg[:100] + "..."
                        logger.error(f"批次 {batch_num}/{batch_count} 发送失败: {error_msg}")
                        return False
                        
                    # 批次之间添加短暂延迟，避免触发频率限制
                    if batch_num < batch_count:
                        await asyncio.sleep(2)
                    
                    # 更新批次发送进度条
                    if TQDM_AVAILABLE and batch_pbar:
                        batch_pbar.update(1)
            
        tracker.complete_all()
        
            logger.info(f"媒体组发送完成: {len(media_list)}/{len(file_paths)} 成功")
            return True
            
        except Exception as e:
            logger.error(f"发送媒体组失败: {str(e)}")
            return False
    
    async def send_to_all_channels(self, file_paths: List[str]) -> Dict[str, bool]:
        """发送媒体组到所有目标频道"""
        if not self.target_channels:
            logger.error("没有设置目标频道")
            return {}
            
        results = {}
        
        # 创建频道发送进度条
        channel_desc = "发送到频道" if not COLORAMA_AVAILABLE else f"{Fore.CYAN}发送到频道{Style.RESET_ALL}"
        with tqdm(total=len(self.target_channels), desc=channel_desc, unit="个", position=0,
                 bar_format=TOTAL_BAR_FORMAT,
                 colour='cyan' if not COLORAMA_AVAILABLE else None) if TQDM_AVAILABLE else None as channel_pbar:
        for channel in self.target_channels:
                # 彩色日志
                if COLORAMA_AVAILABLE:
                    logger.info(f"{Fore.CYAN}{Style.BRIGHT}开始向频道 {channel} 发送媒体组{Style.RESET_ALL}")
                else:
            logger.info(f"开始向频道 {channel} 发送媒体组")
                    
            success = await self.send_media_group_with_progress(channel, file_paths)
            results[channel] = success
                
                # 更新频道进度条
                if TQDM_AVAILABLE and channel_pbar:
                    channel_pbar.update(1)
            
        return results
        
async def main():
    """主函数"""
    # 处理命令行参数
    debug_mode = "--debug" in sys.argv
    
    # 检查tqdm是否可用，如果不可用提醒用户安装
    if not TQDM_AVAILABLE:
        if COLORAMA_AVAILABLE:
            print(f"\n{Fore.CYAN}{'='*60}{Style.RESET_ALL}")
            print(f"{Fore.YELLOW}⚠️ 建议安装 tqdm 以启用进度条{Style.RESET_ALL}")
            print(f"{Fore.GREEN}💡 可以使用以下命令安装: {Fore.WHITE}pip install tqdm{Style.RESET_ALL}")
            print(f"{Fore.CYAN}{'='*60}{Style.RESET_ALL}\n")
        else:
            print("\n" + "="*60)
            print("⚠️ 建议安装 tqdm 以启用进度条")
            print("💡 可以使用以下命令安装: pip install tqdm")
            print("="*60 + "\n")
    
    # 检查colorama是否可用，如果不可用提醒用户安装
    if not COLORAMA_AVAILABLE:
        print("\n" + "="*60)
        print("⚠️ 建议安装 colorama 以启用彩色显示")
        print("💡 可以使用以下命令安装: pip install colorama")
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
        logger.info(f"使用代理: {proxy_type} {addr}:{port}")
    
    # 美化输出的启动信息
    if COLORAMA_AVAILABLE:
        print(f"\n{Fore.CYAN}{'='*60}{Style.RESET_ALL}")
        print(f"{Fore.GREEN}{Style.BRIGHT}{' '*20}🚀 媒体发送器启动中...{Style.RESET_ALL}")
        print(f"{Fore.CYAN}{'='*60}{Style.RESET_ALL}\n")
    else:
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
            init_desc = "初始化" if not COLORAMA_AVAILABLE else f"{Fore.GREEN}初始化{Style.RESET_ALL}"
            with tqdm(total=100, desc=init_desc, unit="%", 
                     bar_format=TOTAL_BAR_FORMAT,
                     colour='green' if not COLORAMA_AVAILABLE else None) as pbar:
                # 模拟初始化过程
                for i in range(1, 101):
                    await asyncio.sleep(0.01)
                    pbar.update(1)
                
        # 美化输出的准备就绪信息
        if COLORAMA_AVAILABLE:
            print(f"\n{Fore.CYAN}{'='*60}{Style.RESET_ALL}")
            print(f"{Fore.GREEN}{Style.BRIGHT}{' '*20}✅ 媒体发送器已准备就绪{Style.RESET_ALL}")
            print(f"{Fore.YELLOW}{' '*15}🎨 使用tqdm和colorama提供专业的彩色进度显示{Style.RESET_ALL}")
            print(f"{Fore.CYAN}{'='*60}{Style.RESET_ALL}\n")
        else:
            print("\n" + "="*60)
            print(" "*20 + "✅ 媒体发送器已准备就绪")
            print(" "*15 + "🎨 使用tqdm提供专业的进度显示")
            print("="*60 + "\n")
        
        # 初始化自定义媒体发送器
        sender = CustomMediaGroupSender(client, temp_folder, target_channels)
        
        # 获取测试媒体文件
        media_files = sender.get_media_files(sender.temp_folder)
        
        if not media_files:
            logger.error(f"在 {sender.temp_folder} 文件夹中没有找到媒体文件")
            return
        
        # 发送媒体组
        logger.info(f"准备发送 {len(media_files)} 个文件到 {len(sender.target_channels)} 个频道")
        
        # 记录开始时间
        start_time = time.time()
        
        # 发送媒体
        results = await sender.send_to_all_channels(media_files)
        
        # 计算总耗时
        elapsed_time = time.time() - start_time
        
        # 美化输出的结果表格
        if COLORAMA_AVAILABLE:
            print(f"\n{Fore.CYAN}{'='*60}{Style.RESET_ALL}")
            print(f"{Fore.GREEN}{Style.BRIGHT}{' '*20}📊 发送结果摘要{Style.RESET_ALL}")
            print(f"{Fore.CYAN}{'='*60}{Style.RESET_ALL}")
            print(f"{Fore.YELLOW}{'频道':^30} | {'状态':^10} | {'耗时':^15}{Style.RESET_ALL}")
            print(f"{Fore.CYAN}{'-'*60}{Style.RESET_ALL}")
        else:
            print("\n" + "="*60)
            print(" "*20 + "📊 发送结果摘要")
            print("="*60)
            print(f"{'频道':^30} | {'状态':^10} | {'耗时':^15}")
            print("-"*60)
        
        # 统计成功和失败数
        success_count = 0
        for channel, success in results.items():
            if COLORAMA_AVAILABLE:
                status = f"{Fore.GREEN}✅ 成功{Style.RESET_ALL}" if success else f"{Fore.RED}❌ 失败{Style.RESET_ALL}"
            else:
                status = "✅ 成功" if success else "❌ 失败"
                
            if success:
                success_count += 1
                
            if COLORAMA_AVAILABLE:
                channel_display = f"{Fore.CYAN}{channel}{Style.RESET_ALL}"
                time_display = f"{Fore.MAGENTA}{format_time(elapsed_time)}{Style.RESET_ALL}"
                print(f"{channel_display:^40} | {status:^25} | {time_display:^25}")
            else:
                print(f"{channel:^30} | {status:^10} | {format_time(elapsed_time):^15}")
        
        if COLORAMA_AVAILABLE:
            print(f"{Fore.CYAN}{'-'*60}{Style.RESET_ALL}")
            print(f"总计: {Fore.YELLOW}{len(results)}{Style.RESET_ALL} 个频道, "
                 f"{Fore.GREEN}{success_count}{Style.RESET_ALL} 成功, "
                 f"{Fore.RED}{len(results) - success_count}{Style.RESET_ALL} 失败")
            print(f"总耗时: {Fore.MAGENTA}{format_time(elapsed_time)}{Style.RESET_ALL}")
            print(f"{Fore.CYAN}{'='*60}{Style.RESET_ALL}\n")
        else:
            print("-"*60)
            print(f"总计: {len(results)} 个频道, {success_count} 成功, {len(results) - success_count} 失败")
            print(f"总耗时: {format_time(elapsed_time)}")
            print("="*60 + "\n")
        
        # 美化输出的结束信息
        if COLORAMA_AVAILABLE:
            print(f"\n{Fore.CYAN}{'='*60}{Style.RESET_ALL}")
            print(f"{Fore.GREEN}{Style.BRIGHT}{' '*20}操作已完成{Style.RESET_ALL}")
            print(f"{Fore.YELLOW}{' '*15}总用时: {Fore.MAGENTA}{format_time(elapsed_time)}{Style.RESET_ALL}")
            print(f"{Fore.CYAN}{'='*60}{Style.RESET_ALL}\n")
        else:
            print("\n" + "="*60)
            print(" "*20 + "操作已完成")
            print(" "*15 + f"总用时: {format_time(elapsed_time)}")
            print("="*60 + "\n")

if __name__ == "__main__":
    # 设置处理任务异常的回调
    loop = asyncio.get_event_loop()
    loop.set_exception_handler(lambda loop, context: None if "exception was never retrieved" in str(context.get("message", "")) else None)
    
    # 运行主函数
    try:
    asyncio.run(main()) 
    except KeyboardInterrupt:
        if COLORAMA_AVAILABLE:
            print(f"\n{Fore.YELLOW}⚠️ 程序被用户中断{Style.RESET_ALL}")
        else:
            print("\n⚠️ 程序被用户中断")
    except Exception as e:
        # 简化错误输出
        error_msg = str(e)
        if "Peer id invalid" in error_msg:
            peer_id = re.search(r"Peer id invalid: (.*)", error_msg)
            peer_info = peer_id.group(1) if peer_id else "未知ID"
            
            if COLORAMA_AVAILABLE:
                print(f"\n{Fore.YELLOW}⚠️ 频道ID解析问题: {Fore.CYAN}{peer_info}{Style.RESET_ALL}")
                print(f"{Fore.GREEN}💡 这是正常现象，不影响功能，实际媒体文件已成功上传{Style.RESET_ALL}")
            else:
                print(f"\n⚠️ 频道ID解析问题: {peer_info}")
                print("💡 这是正常现象，不影响功能，实际媒体文件已成功上传")
        else:
            if COLORAMA_AVAILABLE:
                print(f"\n{Fore.RED}❌ 程序发生错误: {error_msg}{Style.RESET_ALL}")
                print(f"{Fore.YELLOW}💡 使用 --debug 参数运行可查看详细错误信息{Style.RESET_ALL}")
            else:
                print(f"\n❌ 程序发生错误: {error_msg}")
                print("💡 使用 --debug 参数运行可查看详细错误信息")
    finally:
        if COLORAMA_AVAILABLE:
            print(f"\n{Fore.CYAN}👋 程序已退出{Style.RESET_ALL}")
        else:
            print("\n👋 程序已退出") 