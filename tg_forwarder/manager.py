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
            
            # 获取下载配置
            download_config = self.config.get_download_config()
            
            # 检查源频道是否禁止转发
            if result.get("forwards_restricted", False):
                logger.warning("检测到源频道禁止转发消息，将使用备用方式: 下载文件后上传")
                try:
                    # 下载源频道消息到本地
                    logger.info(f"开始下载源频道消息...")
                    
                    # 从源频道直接下载指定范围内的消息
                    download_results = await self.downloader.download_messages_from_source(
                        source_identifier, 
                        start_message_id, 
                        end_message_id
                    )
                    
                    # 将下载结果添加到转发结果中
                    result["download_results"] = download_results
                    logger.info(f"媒体文件下载完成，保存到: {download_config['temp_folder']}")
                    
                    # 如果有下载的文件，使用CustomMediaGroupSender进行上传
                    if download_results:
                        logger.info("开始使用备用方式上传媒体文件...")
                        
                        # 获取下载的文件路径列表
                        downloaded_files = [path for path in download_results.values() if path]
                        
                        if downloaded_files:
                            # 导入CustomMediaGroupSender
                            from tg_forwarder.customUploader import CustomMediaGroupSender
                            
                            # 调用上传方法
                            upload_result = await CustomMediaGroupSender.upload_from_source(
                                config_path=self.config_path,
                                downloaded_files=downloaded_files,
                                target_channels=target_channels_str,
                                delete_after_upload=True  # 上传后删除文件
                            )
                            
                            # 合并上传结果到总结果
                            result["upload_results"] = upload_result
                            
                            if upload_result.get("success", False):
                                logger.info(f"备用上传成功: {upload_result.get('uploaded_files', 0)} 个文件上传到 {upload_result.get('success_channels', 0)} 个频道")
                            else:
                                logger.error(f"备用上传失败: {upload_result.get('error', '未知错误')}")
                        else:
                            logger.warning("没有成功下载的媒体文件，无法进行备用上传")
                    else:
                        logger.warning("没有下载结果，无法进行备用上传")
                
                except Exception as e:
                    logger.error(f"备用方式处理时出错: {repr(e)}")
                    result["backup_error"] = str(e)
            
            # 如果有转发失败的消息(但源频道不是禁止转发的)，直接跳过而不下载
            elif result.get("failed", 0) > 0 and "failed_messages" in result:
                failed_count = result.get("failed", 0)
                failed_message_ids = result["failed_messages"]
                logger.warning(f"检测到 {failed_count} 条消息转发失败，但不是因为源频道禁止转发，将直接跳过这些消息")
                
                # 仅记录失败的消息ID，不下载
                if failed_message_ids:
                    logger.info(f"转发失败的消息ID: {', '.join(map(str, failed_message_ids[:10]))}" + 
                               (f"... 等共 {len(failed_message_ids)} 条" if len(failed_message_ids) > 10 else ""))
                
                # 显示详细错误信息
                if "error_messages" in result and result["error_messages"]:
                    error_messages = result["error_messages"]
                    # 如果错误消息很多，只显示前几条和统计信息
                    if len(error_messages) > 5:
                        logger.warning(f"转发失败的主要错误信息 (共 {len(error_messages)} 条):")
                        for i, msg in enumerate(error_messages[:5], 1):
                            logger.warning(f"  {i}. {msg}")
                        logger.warning(f"  ... 以及其他 {len(error_messages) - 5} 条错误")
                    else:
                        logger.warning("转发失败的错误信息:")
                        for i, msg in enumerate(error_messages, 1):
                            logger.warning(f"  {i}. {msg}")
                
                # 记录总体转发结果
                total_messages = result.get("total", 0)
                success_count = result.get("success", 0)
                success_percentage = (success_count / total_messages * 100) if total_messages > 0 else 0
                
                logger.info(f"转发总结: 总计 {total_messages} 条消息，成功 {success_count} 条 ({success_percentage:.1f}%)，"
                           f"失败 {failed_count} 条 ({100 - success_percentage:.1f}%)")
            else:
                logger.info("所有消息转发成功，无需下载源频道消息")
            
            # 检查上传配置 - 由于禁止转发的情况已经处理了上传，这里只处理普通转发后上传的情况
            upload_config = self.config.get_upload_config()
            if not result.get("forwards_restricted", False) and upload_config.get("enabled", False) and upload_config.get("upload_after_forward", True):
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
                if not result.get("forwards_restricted", False):
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