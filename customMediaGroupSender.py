#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import time
import asyncio
import logging
import configparser
import mimetypes
import re
from typing import List, Dict, Tuple, Any, Optional, Callable
from datetime import datetime

from pyrogram import Client
from pyrogram.types import InputMediaPhoto, InputMediaVideo, InputMediaDocument

# 设置日志记录
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger("CustomMediaGroupSender")

class UploadProgressTracker:
    """上传进度跟踪器"""
    def __init__(self, total_files: int, total_size: int):
        self.total_files = total_files
        self.total_size = total_size
        self.uploaded_files = 0
        self.uploaded_size = 0
        self.start_time = time.time()
        self.current_file = ""
        self.current_file_progress = 0
        self.current_file_size = 0
        self.file_start_time = time.time()
        
    def start_file(self, file_name: str, file_size: int):
        """开始上传新文件"""
        self.current_file = file_name
        self.current_file_size = file_size
        self.current_file_progress = 0
        self.file_start_time = time.time()
        logger.info(f"开始上传: {file_name} ({format_size(file_size)})")
        
    def update_progress(self, current: int, total: int):
        """更新当前文件上传进度"""
        self.current_file_progress = current
        
        # 计算当前文件的上传速度
        elapsed = time.time() - self.file_start_time
        speed = current / elapsed if elapsed > 0 else 0
        
        # 计算当前文件的上传百分比
        percentage = (current / total) * 100 if total > 0 else 0
        
        # 计算总体上传进度
        total_progress = ((self.uploaded_size + current) / self.total_size) * 100 if self.total_size > 0 else 0
        
        # 计算预计剩余时间
        remaining_size = self.total_size - (self.uploaded_size + current)
        eta = remaining_size / speed if speed > 0 else 0
        
        # 格式化输出信息
        logger.info(
            f"文件: {self.current_file} - {percentage:.1f}% "
            f"({format_size(current)}/{format_size(total)}) "
            f"速度: {format_size(speed)}/s\n"
            f"总进度: {total_progress:.1f}% "
            f"({self.uploaded_files}/{self.total_files}文件 完成) "
            f"预计剩余时间: {format_time(eta)}"
        )
    
    def complete_file(self):
        """完成当前文件上传"""
        self.uploaded_files += 1
        self.uploaded_size += self.current_file_size
        elapsed = time.time() - self.file_start_time
        speed = self.current_file_size / elapsed if elapsed > 0 else 0
        
        logger.info(
            f"文件上传完成: {self.current_file} "
            f"用时: {elapsed:.2f}秒 "
            f"平均速度: {format_size(speed)}/s"
        )
    
    def complete_all(self):
        """完成所有文件上传"""
        total_elapsed = time.time() - self.start_time
        avg_speed = self.uploaded_size / total_elapsed if total_elapsed > 0 else 0
        
        logger.info(
            f"所有文件上传完成! "
            f"共 {self.uploaded_files} 个文件 ({format_size(self.uploaded_size)}) "
            f"总用时: {total_elapsed:.2f}秒 "
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
    """自定义媒体组发送器"""
    def __init__(self, client: Client, config_path: str = "config.ini"):
        self.client = client
        self.config = self._load_config(config_path)
        self.temp_folder = self.config.get("temp_folder", "temp")
        self.target_channels = self.config.get("target_channels", [])
        self.max_concurrent_uploads = self.config.get("max_concurrent_batches", 3)
        self.semaphore = asyncio.Semaphore(self.max_concurrent_uploads)
        
    def _load_config(self, config_path: str) -> Dict[str, Any]:
        """加载配置文件"""
        config = configparser.ConfigParser()
        if not os.path.exists(config_path):
            logger.error(f"配置文件不存在: {config_path}")
            return {}
            
        config.read(config_path, encoding='utf-8')
        
        result = {}
        
        # 读取目标频道
        if config.has_section("CHANNELS"):
            target_channels_str = config.get("CHANNELS", "target_channels", fallback="")
            # 处理频道标识符，确保格式正确
            result["target_channels"] = [
                parse_channel_identifier(ch.strip()) 
                for ch in target_channels_str.split(",") 
                if ch.strip()
            ]
            logger.info(f"目标频道: {result['target_channels']}")
            
        # 读取临时文件夹
        if config.has_section("DOWNLOAD"):
            result["temp_folder"] = config.get("DOWNLOAD", "temp_folder", fallback="temp")
            
        # 读取上传设置
        if config.has_section("UPLOAD"):
            result["max_concurrent_batches"] = config.getint("UPLOAD", "max_concurrent_batches", fallback=3)
            
        logger.info(f"配置加载完成: 目标频道数 {len(result.get('target_channels', []))}, "
                   f"临时文件夹 {result.get('temp_folder', 'temp')}, "
                   f"最大并发上传数 {result.get('max_concurrent_batches', 3)}")
        
        return result
    
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
    
    async def upload_single_file(self, file_path: str, chat_id: str, tracker: UploadProgressTracker) -> bool:
        """上传单个文件，并跟踪进度"""
        file_name = os.path.basename(file_path)
        file_size = os.path.getsize(file_path)
        mime_type = mimetypes.guess_type(file_path)[0] or ""
        
        tracker.start_file(file_name, file_size)
        
        try:
            if mime_type.startswith('image/'):
                await self.client.send_photo(
                    chat_id=chat_id,
                    photo=file_path,
                    caption=f"[测试] 图片: {file_name}",
                    progress=self.progress_callback,
                    progress_args=(tracker,)
                )
            elif mime_type.startswith('video/'):
                await self.client.send_video(
                    chat_id=chat_id,
                    video=file_path,
                    caption=f"[测试] 视频: {file_name}",
                    progress=self.progress_callback,
                    progress_args=(tracker,)
                )
            else:
                await self.client.send_document(
                    chat_id=chat_id,
                    document=file_path,
                    caption=f"[测试] 文件: {file_name}",
                    progress=self.progress_callback,
                    progress_args=(tracker,)
                )
                
            tracker.complete_file()
            return True
        except Exception as e:
            logger.error(f"上传文件 {file_name} 失败: {str(e)}")
            return False
    
    async def send_media_group_with_progress(self, chat_id: str, file_paths: List[str]) -> bool:
        """发送媒体组，带进度显示"""
        if not file_paths:
            logger.warning("没有提供任何文件路径")
            return False
            
        # 计算总文件大小
        total_size = sum(os.path.getsize(path) for path in file_paths)
        tracker = UploadProgressTracker(len(file_paths), total_size)
        
        # 上传所有文件
        results = []
        for file_path in file_paths:
            async with self.semaphore:  # 控制并发上传数量
                result = await self.upload_single_file(file_path, chat_id, tracker)
                results.append(result)
                
        # 检查结果
        success_count = sum(1 for r in results if r)
        tracker.complete_all()
        
        logger.info(f"媒体组发送完成: {success_count}/{len(file_paths)} 成功")
        return all(results)
    
    async def send_to_all_channels(self, file_paths: List[str]) -> Dict[str, bool]:
        """发送媒体组到所有目标频道"""
        if not self.target_channels:
            logger.error("没有设置目标频道")
            return {}
            
        results = {}
        for channel in self.target_channels:
            logger.info(f"开始向频道 {channel} 发送媒体组")
            success = await self.send_media_group_with_progress(channel, file_paths)
            results[channel] = success
            
        return results
        
async def main():
    """主函数"""
    # 读取API配置
    config = configparser.ConfigParser()
    config.read('config.ini', encoding='utf-8')
    
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
        logger.info(f"使用代理: {proxy_type} {addr}:{port}")
    
    # 初始化Pyrogram客户端
    async with Client(
        "custom_media_sender",
        api_id=api_id,
        api_hash=api_hash,
        proxy=proxy
    ) as client:
        # 初始化自定义媒体发送器
        sender = CustomMediaGroupSender(client)
        
        # 获取测试媒体文件
        media_files = sender.get_media_files(sender.temp_folder)
        
        if not media_files:
            logger.error(f"在 {sender.temp_folder} 文件夹中没有找到媒体文件")
            return
        
        # 发送媒体组
        logger.info(f"准备发送 {len(media_files)} 个文件到 {len(sender.target_channels)} 个频道")
        results = await sender.send_to_all_channels(media_files)
        
        # 打印结果
        for channel, success in results.items():
            logger.info(f"频道 {channel}: {'成功' if success else '失败'}")

if __name__ == "__main__":
    # 运行主函数
    asyncio.run(main()) 