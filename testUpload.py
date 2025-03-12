#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
测试脚本：测试send_media_group功能是否能将媒体组上传到Telegram频道
"""

import os
import asyncio
import configparser
from pyrogram import Client
from pyrogram.types import InputMediaPhoto, InputMediaVideo
import logging
import subprocess
import json

# 设置日志系统
# 创建一个过滤器来过滤掉不需要的pyrogram日志
class PyrogramFilter(logging.Filter):
    def filter(self, record):
        # 过滤掉大部分pyrogram的连接和会话信息
        if record.name.startswith('pyrogram') and any(msg in record.getMessage() for msg in 
                                                     ['Session', 'NetworkTask', 'PingTask', 'Connected', 'Connecting']):
            return False
        return True

# 设置日志格式和级别
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        # 文件处理器确保完整日志被保存
        logging.FileHandler("upload_test.log", encoding="utf-8"),
        # 控制台处理器过滤掉不必要的pyrogram日志
        logging.StreamHandler()
    ]
)

# 应用过滤器到根日志记录器的控制台处理器
for handler in logging.getLogger().handlers:
    if isinstance(handler, logging.StreamHandler) and not isinstance(handler, logging.FileHandler):
        handler.addFilter(PyrogramFilter())

# 降低pyrogram日志级别
logging.getLogger("pyrogram").setLevel(logging.WARNING)

logger = logging.getLogger("MediaUploader")

def check_file(filepath, file_type="媒体", quiet=False):
    """检查文件是否存在、可读、大小是否合适"""
    if not os.path.exists(filepath):
        if not quiet:
            logger.error(f"{file_type}文件不存在: {filepath}")
        return False
    
    if not os.path.isfile(filepath):
        if not quiet:
            logger.error(f"{filepath} 不是一个文件")
        return False
    
    if not os.access(filepath, os.R_OK):
        if not quiet:
            logger.error(f"{file_type}文件无法读取: {filepath}")
        return False
    
    file_size = os.path.getsize(filepath)
    if file_size == 0:
        if not quiet:
            logger.error(f"{file_type}文件大小为0: {filepath}")
        return False
    
    if not quiet:
        logger.info(f"{file_type}文件检查通过: {filepath} (大小: {file_size/1024:.2f} KB)")
    return True

def check_video_format(filepath):
    """
    检验视频格式是否满足要求：
    1. 视频格式为mp4或mov
    2. 音频编码为aac
    3. 必须包含音频
    4. 文件大小不超过2G
    """
    try:
        # 检查文件大小
        file_size_bytes = os.path.getsize(filepath)
        file_size_gb = file_size_bytes / (1024 * 1024 * 1024)
        if file_size_gb > 2:
            logger.warning(f"视频文件过大: {file_size_gb:.2f}GB，超过2GB限制")
            return False, f"文件过大: {file_size_gb:.2f}GB > 2GB"
        
        # 使用ffprobe分析视频
        cmd = [
            'ffprobe', 
            '-v', 'quiet', 
            '-print_format', 'json', 
            '-show_format', 
            '-show_streams', 
            filepath
        ]
        
        result = subprocess.run(cmd, capture_output=True, text=True)
        
        if result.returncode != 0:
            logger.error(f"分析视频失败: {filepath}")
            return False, "分析视频失败"
        
        video_info = json.loads(result.stdout)
        
        # 检查容器格式
        format_name = video_info.get('format', {}).get('format_name', '').lower()
        if 'mp4' not in format_name and 'mov' not in format_name:
            logger.warning(f"视频格式不符合要求: {format_name}")
            return False, f"视频格式不是mp4或mov: {format_name}"
        
        # 检查是否有视频流
        has_video = False
        for stream in video_info.get('streams', []):
            if stream.get('codec_type') == 'video':
                has_video = True
                break
        
        if not has_video:
            logger.warning(f"视频中没有视频流: {filepath}")
            return False, "没有视频流"
        
        # 检查是否有音频流，以及音频编码是否为AAC
        has_audio = False
        is_aac = False
        
        for stream in video_info.get('streams', []):
            if stream.get('codec_type') == 'audio':
                has_audio = True
                codec_name = stream.get('codec_name', '').lower()
                if 'aac' in codec_name:
                    is_aac = True
                break
        
        if not has_audio:
            logger.warning(f"视频没有音频流: {filepath}")
            return False, "没有音频流"
        
        if not is_aac:
            logger.warning(f"音频编码不是AAC: {filepath}")
            return False, "音频编码不是AAC"
        
        logger.info(f"视频格式检查通过: {filepath}")
        return True, None
    
    except Exception as e:
        logger.error(f"检查视频格式时出错: {repr(e)}")
        return False, f"检查出错: {repr(e)}"

async def classify_media_files(files, temp_folder):
    """
    对媒体文件进行分类，区分满足和不满足要求的文件
    视频文件需要检查格式，其他类型文件不需要
    """
    compatible_files = []
    incompatible_files = []
    compatibility_issues = {}
    
    for filename in files:
        filepath = os.path.join(temp_folder, filename)
        
        if not check_file(filepath):
            incompatible_files.append(filename)
            compatibility_issues[filename] = "文件不存在或不可读"
            continue
        
        # 对于图片文件，直接认为兼容
        if filename.endswith(('.jpg', '.jpeg', '.png')):
            logger.info(f"图片文件无需额外检查: {filename}")
            compatible_files.append(filename)
            continue
        
        # 检查视频格式
        if filename.endswith(('.mp4', '.mov', '.avi')):
            try:
                is_compatible, reason = check_video_format(filepath)
                if is_compatible:
                    compatible_files.append(filename)
                    logger.info(f"视频格式符合要求: {filename}")
                else:
                    incompatible_files.append(filename)
                    compatibility_issues[filename] = reason
                    logger.warning(f"视频格式不符合要求: {filename}, 原因: {reason}")
            except Exception as e:
                logger.error(f"检查视频格式失败: {repr(e)}")
                incompatible_files.append(filename)
                compatibility_issues[filename] = f"分析失败: {repr(e)}"
    
    # 输出分类结果
    logger.info(f"格式符合要求的文件({len(compatible_files)}): {compatible_files}")
    if incompatible_files:
        logger.info(f"格式不符合要求的文件({len(incompatible_files)}): {incompatible_files}")
        for file, reason in compatibility_issues.items():
            logger.info(f"不符合要求原因({file}): {reason}")
    
    return compatible_files, incompatible_files

async def send_files_to_all_channels(app, channels, files, temp_folder, is_group=True):
    """
    发送一组文件到所有目标频道
    is_group=True表示使用媒体组发送，False表示单独发送
    """
    all_results = {}
    
    for channel in channels:
        channel_results = []
        
        if is_group:
            # 使用媒体组发送
            media_group = []
            valid_files = []
            
            for i, filename in enumerate(files):
                filepath = os.path.join(temp_folder, filename)
                if not check_file(filepath, quiet=True):
                    continue
                
                valid_files.append(filename)
                caption = f"媒体组: {filename}" if i == 0 else None
                
                if filename.endswith(('.jpg', '.jpeg', '.png')):
                    media_group.append(InputMediaPhoto(
                        media=filepath,
                        caption=caption
                    ))
                elif filename.endswith(('.mp4', '.mov', '.avi')):
                    media_group.append(InputMediaVideo(
                        media=filepath,
                        caption=caption,
                        supports_streaming=True
                    ))
            
            if len(media_group) >= 2:
                try:
                    logger.info(f"向频道{channel}发送媒体组({len(media_group)}个项目)")
                    result = await app.send_media_group(
                        chat_id=channel,
                        media=media_group
                    )
                    logger.info(f"向频道{channel}成功发送媒体组，共{len(result)}个项目")
                    channel_results.extend(valid_files)
                except Exception as e:
                    logger.error(f"向频道{channel}发送媒体组失败: {repr(e)}")
        else:
            # 单独发送每个文件
            for filename in files:
                filepath = os.path.join(temp_folder, filename)
                if not check_file(filepath, quiet=True):
                    continue
                
                try:
                    if filename.endswith(('.jpg', '.jpeg', '.png')):
                        logger.info(f"向频道{channel}单独发送照片: {filename}")
                        await app.send_photo(
                            chat_id=channel,
                            photo=filepath,
                            caption=f"单独发送: {filename}"
                        )
                        logger.info(f"向频道{channel}单独发送照片成功: {filename}")
                        channel_results.append(filename)
                    
                    elif filename.endswith(('.mp4', '.mov', '.avi')):
                        logger.info(f"向频道{channel}单独发送视频: {filename}")
                        await app.send_video(
                            chat_id=channel,
                            video=filepath,
                            caption=f"单独发送: {filename}",
                            supports_streaming=True
                        )
                        logger.info(f"向频道{channel}单独发送视频成功: {filename}")
                        channel_results.append(filename)
                
                except Exception as e:
                    logger.error(f"向频道{channel}单独发送文件{filename}失败: {repr(e)}")
        
        all_results[channel] = channel_results
    
    # 返回每个频道成功发送的文件列表
    return all_results

async def upload_media_group():
    """
    上传媒体组到Telegram频道的主函数
    新的流程：
    1. 分类媒体文件，区分符合和不符合媒体组要求的文件
    2. 将符合要求的文件分批（每批不超过10个）发送到所有目标频道
    3. 将不符合要求的文件单独发送到所有目标频道
    """
    
    # 读取配置文件
    config = configparser.ConfigParser()
    config.read('config.ini')
    
    # API设置
    api_id = config.get('API', 'api_id')
    api_hash = config.get('API', 'api_hash')
    
    # 代理设置
    proxy = None
    if config.getboolean('PROXY', 'enabled'):
        proxy_type = config.get('PROXY', 'proxy_type')
        addr = config.get('PROXY', 'addr')
        port = config.getint('PROXY', 'port')
        username = config.get('PROXY', 'username') or None
        password = config.get('PROXY', 'password') or None
        
        proxy = {
            "scheme": proxy_type.lower(),
            "hostname": addr,
            "port": port,
            "username": username,
            "password": password
        }
        logger.info(f"使用代理：{proxy_type} {addr}:{port}")
    
    # 获取所有目标频道
    target_channels = [ch.strip() for ch in config.get('CHANNELS', 'target_channels').split(',')]
    
    # 处理频道格式，从URL中提取频道用户名
    processed_channels = []
    for channel in target_channels:
        if channel.startswith('https://t.me/'):
            channel = channel.split('/')[-1]
        processed_channels.append(channel)
    
    logger.info(f"目标频道列表: {processed_channels}")
    
    # 设置媒体文件夹
    temp_folder = config.get('DOWNLOAD', 'temp_folder')
    if temp_folder.startswith('./'):
        temp_folder = temp_folder[2:]  # 移除开头的'./'
    
    # 确保临时文件夹路径正确
    if not os.path.exists(temp_folder):
        logger.error(f"临时文件夹不存在: {temp_folder}")
        logger.info(f"当前工作目录: {os.getcwd()}")
        try:
            os.makedirs(temp_folder, exist_ok=True)
            logger.info(f"成功创建临时文件夹: {temp_folder}")
        except Exception as e:
            logger.error(f"创建临时文件夹失败: {repr(e)}")
            return
    
    # 创建pyrogram客户端
    async with Client("upload_session", api_id, api_hash, proxy=proxy) as app:
        try:
            # 列出并过滤支持的媒体文件
            media_files = [f for f in os.listdir(temp_folder) if os.path.isfile(os.path.join(temp_folder, f))]
            
            if not media_files:
                logger.error(f"临时文件夹中没有文件: {temp_folder}")
                return
            
            # 过滤出支持的媒体文件类型
            supported_files = []
            for filename in media_files:
                if filename.endswith(('.jpg', '.jpeg', '.png', '.mp4', '.mov', '.avi')):
                    supported_files.append(filename)
            
            if not supported_files:
                logger.error(f"未找到支持的媒体文件类型，只支持jpg、jpeg、png、mp4、mov、avi")
                return
            
            logger.info(f"找到 {len(supported_files)} 个支持的媒体文件")
            
            # 第1步：分类媒体文件
            logger.info("=== 第1步：分类媒体文件 ===")
            compatible_files, incompatible_files = await classify_media_files(supported_files, temp_folder)
            
            # 第2步：将符合要求的文件分批发送（媒体组）
            if compatible_files:
                logger.info("=== 第2步：以媒体组方式发送符合要求的文件 ===")
                # 将文件分批，每批最多10个
                batches = []
                for i in range(0, len(compatible_files), 10):
                    batch = compatible_files[i:i+10]
                    if len(batch) >= 2:  # 媒体组至少需要2个文件
                        batches.append(batch)
                    else:
                        # 不足2个的放入不兼容列表单独发送
                        incompatible_files.extend(batch)
                
                # 逐批发送
                for i, batch in enumerate(batches):
                    logger.info(f"=== 发送第{i+1}/{len(batches)}批媒体组 ===")
                    results = await send_files_to_all_channels(
                        app, processed_channels, batch, temp_folder, is_group=True
                    )
                    
                    # 输出每个频道的发送结果
                    for channel, sent_files in results.items():
                        logger.info(f"第{i+1}批媒体组，频道{channel}成功发送: {sent_files}")
                    
                    # 等待一下再发送下一批
                    if i < len(batches) - 1:
                        await asyncio.sleep(3)
            
            # 第3步：单独发送不符合要求的文件
            if incompatible_files:
                logger.info("=== 第3步：单独发送不符合要求的文件 ===")
                results = await send_files_to_all_channels(
                    app, processed_channels, incompatible_files, temp_folder, is_group=False
                )
                
                # 输出每个频道的发送结果
                for channel, sent_files in results.items():
                    logger.info(f"单独发送，频道{channel}成功发送: {sent_files}")
            
            logger.info("所有媒体文件上传完成")
            
        except Exception as e:
            logger.error(f"发生错误: {repr(e)}")

if __name__ == "__main__":
    asyncio.run(upload_media_group()) 