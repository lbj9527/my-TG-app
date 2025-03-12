"""
流程管理模块，负责整体流程的协调
"""

import asyncio
from typing import Dict, Any, Optional, List, Union, Tuple
import logging
import sys
import os

from tg_forwarder.config import Config
from tg_forwarder.client import TelegramClient
from tg_forwarder.channel_parser import ChannelParser
from tg_forwarder.media_handler import MediaHandler
from tg_forwarder.forwarder import MessageForwarder
from tg_forwarder.utils.logger import setup_logger, get_logger

# 获取日志记录器
logger = get_logger("manager")

# 导入上传类（在日志设置之后导入）
# 确保uploader.py所在的目录在导入路径中
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from uploader import Uploader

class ForwardManager:
    """转发管理器类，负责协调整个转发流程"""
    
    def __init__(self, config_path: str = "config.ini"):
        """
        初始化转发管理器
        
        Args:
            config_path: 配置文件路径
        """
        self.config = Config(config_path)
        self.config_path = config_path
        self.client = None
        self.media_handler = None
        self.forwarder = None
        self.channel_parser = ChannelParser()
    
    async def setup(self) -> None:
        """设置并初始化所有组件"""
        # 设置日志
        log_config = self.config.get_log_config()
        setup_logger(log_config)
        
        # 创建并连接客户端
        api_config = self.config.get_api_config()
        proxy_config = self.config.get_proxy_config()
        
        self.client = TelegramClient(api_config, proxy_config)
        await self.client.connect()
        
        # 获取媒体处理配置
        media_config = self.config.get_media_config()
        self.media_handler = MediaHandler(self.client, media_config)
        
        # 初始化下载器
        from tg_forwarder.downloader import MediaDownloader
        download_config = self.config.get_download_config()
        self.downloader = MediaDownloader(self.client, download_config)
        
        # 创建转发器
        forward_config = self.config.get_forward_config()
        self.forwarder = MessageForwarder(self.client, forward_config, self.media_handler)
        
        logger.info("所有组件初始化完成")
    
    async def shutdown(self) -> None:
        """关闭所有组件并释放资源"""
        if self.client:
            await self.client.disconnect()
        
        logger.info("已关闭所有组件")
    
    async def run(self) -> Dict[str, Any]:
        """
        运行转发流程
        
        Returns:
            Dict[str, Any]: 处理结果统计
        """
        try:
            # 获取频道配置
            channels_config = self.config.get_channels_config()
            source_channel_str = channels_config['source_channel']
            target_channels_str = channels_config['target_channels']
            
            # 解析源频道
            try:
                source_identifier, _ = self.channel_parser.parse_channel(source_channel_str)
                logger.info(f"源频道: {self.channel_parser.format_channel_identifier(source_identifier)}")
            except Exception as e:
                logger.error(f"解析源频道失败: {str(e)}")
                return {"success": False, "error": f"解析源频道失败: {str(e)}"}
            
            # 解析目标频道
            target_identifiers = []
            for target_str in target_channels_str:
                try:
                    target_identifier, _ = self.channel_parser.parse_channel(target_str)
                    target_identifiers.append(target_identifier)
                    logger.info(f"目标频道: {self.channel_parser.format_channel_identifier(target_identifier)}")
                except Exception as e:
                    logger.warning(f"解析目标频道 '{target_str}' 失败: {str(e)}")
            
            if not target_identifiers:
                logger.error("没有有效的目标频道")
                return {"success": False, "error": "没有有效的目标频道"}
            
            # 获取转发配置
            forward_config = self.config.get_forward_config()
            start_message_id = forward_config['start_message_id']
            end_message_id = forward_config['end_message_id']
            
            # 执行消息处理和转发
            result = await self.forwarder.process_messages(
                source_identifier,
                target_identifiers,
                start_message_id,
                end_message_id
            )
            
            # 检查转发结果中是否有转发的消息
            if result.get("success") and result.get("forwarded_messages"):
                # 检查下载配置
                download_config = self.config.get_download_config()
                if download_config.get("enabled", False):
                    logger.info("开始下载源频道中的媒体文件...")
                    try:
                        # 从源频道直接下载指定范围内的消息
                        download_results = await self.downloader.download_messages_from_source(
                            source_identifier, 
                            start_message_id, 
                            end_message_id
                        )
                        # 将下载结果添加到转发结果中
                        result["download_results"] = download_results
                        logger.info(f"媒体文件下载完成，保存到: {download_config['temp_folder']}")
                    except Exception as e:
                        logger.error(f"下载媒体文件时出错: {repr(e)}")
                        result["download_error"] = str(e)
                else:
                    logger.info("媒体文件下载功能未启用，跳过下载")
                
                # 检查上传配置
                upload_config = self.config.get_upload_config()
                if upload_config.get("enabled", False) and upload_config.get("upload_after_forward", True):
                    logger.info("开始上传本地媒体文件...")
                    try:
                        # 添加更多上传前的日志信息
                        logger.info(f"上传配置: 临时文件夹={upload_config.get('temp_folder', 'temp')}")
                        logger.info(f"目标频道: {', '.join(target_identifiers)}")
                        
                        # 调用Uploader上传媒体文件
                        upload_success = await Uploader.create_and_upload(self.config_path)
                        if upload_success:
                            logger.info("媒体文件上传成功")
                            # 将上传结果添加到转发结果中
                            result["upload_success"] = True
                        else:
                            logger.error("媒体文件上传失败")
                            result["upload_success"] = False
                    except Exception as e:
                        logger.error(f"上传过程中发生错误: {str(e)}")
                        result["upload_success"] = False
                        result["upload_error"] = str(e)
                else:
                    logger.info("媒体文件上传功能未启用或不需要在转发后上传")
            
            return result
        
        except Exception as e:
            logger.error(f"转发过程中发生错误: {str(e)}")
            import traceback
            logger.error(traceback.format_exc())
            return {"success": False, "error": str(e)}
    
    @classmethod
    async def run_from_config(cls, config_path: str = "config.ini") -> Dict[str, Any]:
        """
        从配置文件创建管理器并运行
        
        Args:
            config_path: 配置文件路径
        
        Returns:
            Dict[str, Any]: 处理结果统计
        """
        manager = cls(config_path)
        
        try:
            await manager.setup()
            result = await manager.run()
            return result
        
        finally:
            await manager.shutdown() 