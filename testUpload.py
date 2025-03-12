#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
测试脚本：测试send_media_group功能是否能将媒体组上传到Telegram频道
"""

import os
import asyncio
import configparser
from pyrogram import Client
from pyrogram.types import InputMediaPhoto, InputMediaVideo, InputMediaDocument
import logging

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

logger = logging.getLogger("TestUpload")

async def upload_media_group():
    """测试上传媒体组到Telegram频道"""
    
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
    
    # 获取目标频道
    target_channels = [ch.strip() for ch in config.get('CHANNELS', 'target_channels').split(',')]
    target_channel = target_channels[0]  # 使用第一个目标频道进行测试
    if target_channel.startswith('https://t.me/'):
        # 从URL中提取频道用户名
        target_channel = target_channel.split('/')[-1]
    
    logger.info(f"目标测试频道: {target_channel}")
    
    # 设置媒体文件夹
    temp_folder = config.get('DOWNLOAD', 'temp_folder')
    if temp_folder.startswith('./'):
        temp_folder = temp_folder[2:]  # 移除开头的'./'
    
    # 创建pyrogram客户端
    async with Client("test_session", api_id, api_hash, proxy=proxy) as app:
        try:
            # 列出temp文件夹中的所有文件
            media_files = [f for f in os.listdir(temp_folder) if os.path.isfile(os.path.join(temp_folder, f))]
            logger.info(f"找到 {len(media_files)} 个媒体文件")
            
            # 准备媒体列表
            media_list = []
            for filename in media_files:
                filepath = os.path.join(temp_folder, filename)
                
                # 根据文件类型创建不同的InputMedia对象
                if filename.endswith(('.jpg', '.jpeg', '.png')):
                    with open(filepath, 'rb') as f:
                        media_list.append(InputMediaPhoto(
                            media=f.read(),
                            caption=f"测试照片: {filename}" if filename == media_files[0] else None
                        ))
                        logger.info(f"添加照片: {filename}")
                
                elif filename.endswith(('.mp4', '.mov', '.avi')):
                    media_list.append(InputMediaVideo(
                        media=filepath,
                        caption=f"测试视频: {filename}" if filename == media_files[0] else None
                    ))
                    logger.info(f"添加视频: {filename}")
                
                # 限制为最多10个媒体项目
                if len(media_list) >= 10:
                    break
            
            # 如果媒体列表为空，发送错误
            if not media_list:
                logger.error("没有找到支持的媒体文件")
                return
            
            # 为了避免send_media_group的限制，我们最多一次发送10个媒体项目
            if len(media_list) > 10:
                media_list = media_list[:10]
                logger.warning("媒体文件超过10个，仅使用前10个")
            
            # 测试方法1：使用文件路径
            logger.info("============== 测试方法1：使用文件路径 ==============")
            media_list_paths = []
            for i, filename in enumerate(media_files[:4]):  # 只使用前4个文件
                filepath = os.path.join(temp_folder, filename)
                if filename.endswith(('.jpg', '.jpeg', '.png')):
                    media_list_paths.append(InputMediaPhoto(
                        media=filepath,
                        caption=f"测试方法1: {filename}" if i == 0 else None
                    ))
                elif filename.endswith(('.mp4', '.mov', '.avi')):
                    media_list_paths.append(InputMediaVideo(
                        media=filepath,
                        caption=f"测试方法1: {filename}" if i == 0 else None
                    ))
            
            if media_list_paths:
                try:
                    logger.info("开始发送媒体组（使用文件路径）...")
                    result = await app.send_media_group(
                        chat_id=target_channel,
                        media=media_list_paths
                    )
                    logger.info(f"成功！发送了 {len(result)} 个媒体项目")
                except Exception as e:
                    # 使用repr()确保完整错误信息被记录，避免截断
                    logger.error(f"发送失败: {repr(e)}")
            
            # 测试方法2：使用文件对象
            logger.info("============== 测试方法2：使用文件对象 ==============")
            media_file_objects = []
            file_objects = []  # 保存文件对象的引用，以便后续关闭
            
            try:
                for i, filename in enumerate(media_files[5:10]):  # 使用后5个文件
                    filepath = os.path.join(temp_folder, filename)
                    file_obj = open(filepath, "rb")
                    file_objects.append(file_obj)
                    
                    if filename.endswith(('.jpg', '.jpeg', '.png')):
                        media_file_objects.append(InputMediaPhoto(
                            media=file_obj,
                            caption=f"测试方法2: {filename}" if i == 0 else None
                        ))
                    elif filename.endswith(('.mp4', '.mov', '.avi')):
                        media_file_objects.append(InputMediaVideo(
                            media=file_obj,
                            caption=f"测试方法2: {filename}" if i == 0 else None
                        ))
                
                if media_file_objects:
                    try:
                        logger.info("开始发送媒体组（使用文件对象）...")
                        result = await app.send_media_group(
                            chat_id=target_channel,
                            media=media_file_objects
                        )
                        logger.info(f"成功！发送了 {len(result)} 个媒体项目")
                    except Exception as e:
                        # 使用repr()确保完整错误信息被记录，避免截断
                        logger.error(f"发送失败: {repr(e)}")
            finally:
                # 关闭所有文件对象
                for file_obj in file_objects:
                    try:
                        file_obj.close()
                    except:
                        pass
            
            # 测试方法3：单独处理视频文件，提供更多参数选项
            logger.info("============== 测试方法3：处理视频文件 ==============")
            video_files = [f for f in media_files if f.endswith(('.mp4', '.mov', '.avi'))]
            
            if video_files:
                # 首先单独发送一个视频来获取file_id
                try:
                    video_path = os.path.join(temp_folder, video_files[0])
                    logger.info(f"发送单个视频文件: {video_files[0]}")
                    
                    # 先发送一个视频以获取file_id
                    sent_video = await app.send_video(
                        chat_id=target_channel,
                        video=video_path,
                        caption="测试视频以获取file_id",
                        width=1280,
                        height=720,
                        supports_streaming=True,
                        disable_notification=False
                    )
                    
                    if sent_video and hasattr(sent_video, 'video') and hasattr(sent_video.video, 'file_id'):
                        video_file_id = sent_video.video.file_id
                        logger.info(f"获取到视频file_id: {video_file_id}")
                        
                        # 使用file_id构建媒体组
                        photo_files = [f for f in media_files if f.endswith(('.jpg', '.jpeg', '.png'))][:4]  # 最多4张照片
                        
                        if photo_files:
                            file_id_media_group = []
                            # 添加视频
                            file_id_media_group.append(InputMediaVideo(
                                media=video_file_id,
                                caption="使用file_id的视频"
                            ))
                            
                            # 添加照片
                            for photo_file in photo_files:
                                photo_path = os.path.join(temp_folder, photo_file)
                                file_id_media_group.append(InputMediaPhoto(
                                    media=photo_path
                                ))
                            
                            # 发送媒体组
                            logger.info("使用file_id发送媒体组...")
                            try:
                                result = await app.send_media_group(
                                    chat_id=target_channel,
                                    media=file_id_media_group
                                )
                                logger.info(f"成功！使用file_id发送了 {len(result)} 个媒体项目")
                            except Exception as e:
                                # 使用repr()确保完整错误信息被记录，避免截断
                                logger.error(f"使用file_id发送失败: {repr(e)}")
                    else:
                        logger.error("无法获取视频file_id")
                
                except Exception as e:
                    # 使用repr()确保完整错误信息被记录，避免截断
                    logger.error(f"处理视频文件时出错: {repr(e)}")
            else:
                logger.warning("没有找到视频文件，跳过测试方法3")
            
            # 测试方法4：使用更安全的参数配置，避免is_premium错误
            logger.info("============== 测试方法4：使用安全参数配置 ==============")
            
            # 只使用照片文件，通常更容易成功
            photo_files = [f for f in media_files if f.endswith(('.jpg', '.jpeg', '.png'))][:5]  # 最多5张照片
            
            if photo_files:
                try:
                    # 创建修改后的媒体列表，添加所有可能避免is_premium错误的参数
                    safe_media_list = []
                    
                    for i, photo_file in enumerate(photo_files):
                        photo_path = os.path.join(temp_folder, photo_file)
                        
                        # 直接使用文件路径，添加所有可能有帮助的参数
                        safe_media_list.append(InputMediaPhoto(
                            media=photo_path,
                            caption=f"安全测试: {photo_file}" if i == 0 else None,
                            parse_mode=None,  # 明确设置为None，避免解析模式问题
                            has_spoiler=False
                        ))
                    
                    logger.info("使用安全参数配置发送媒体组...")
                    
                    # 使用明确的参数配置发送
                    result = await app.send_media_group(
                        chat_id=target_channel,
                        media=safe_media_list,
                        disable_notification=False,  # 明确设置通知参数
                        message_thread_id=None,      # 明确设置为None
                        protect_content=False        # 明确设置内容保护
                    )
                    
                    logger.info(f"成功！使用安全参数发送了 {len(result)} 个媒体项目")
                    
                except Exception as e:
                    # 使用repr()确保完整错误信息被记录，避免截断
                    logger.error(f"使用安全参数发送失败: {repr(e)}")
            else:
                logger.warning("没有找到照片文件，跳过测试方法4")
            
            logger.info("测试完成")
            
        except Exception as e:
            # 使用repr()确保完整错误信息被记录，避免截断
            logger.error(f"发生错误: {repr(e)}")

if __name__ == "__main__":
    asyncio.run(upload_media_group()) 