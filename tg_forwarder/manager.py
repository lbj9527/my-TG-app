"""
流程管理模块，负责整体流程的协调
"""

import asyncio
from typing import Dict, Any, Optional, List, Union, Tuple
import logging
import sys
import os
import configparser

from tg_forwarder.config import Config
from tg_forwarder.client import TelegramClient
from tg_forwarder.channel_parser import ChannelParser
from tg_forwarder.media_handler import MediaHandler
from tg_forwarder.forwarder import MessageForwarder
from tg_forwarder.utils.logger import setup_logger, get_logger
from tg_forwarder.customUploader import CustomMediaGroupSender
from tg_forwarder.client import Client

# 获取日志记录器
logger = get_logger("manager")

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
        # 添加频道转发状态缓存
        self.channel_forward_status = {}
    
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
    
    async def check_channel_forward_status(self, channels: List[Union[str, int]]) -> Dict[str, bool]:
        """
        检查频道是否禁止转发，并缓存结果
        
        Args:
            channels: 频道ID或用户名列表
            
        Returns:
            Dict[str, bool]: 频道转发状态字典，键为频道ID，值为是否允许转发(True表示允许)
        """
        results = {}
        
        for channel_id in channels:
            if str(channel_id) in self.channel_forward_status:
                # 使用缓存结果
                results[str(channel_id)] = self.channel_forward_status[str(channel_id)]
                continue
                
            try:
                # 获取频道完整信息
                chat_info = await self.client.get_entity(channel_id)
                
                # 检查是否设置了禁止转发
                if hasattr(chat_info, 'has_protected_content') and chat_info.has_protected_content:
                    # 禁止转发
                    allow_forward = False
                    logger.info(f"频道 {channel_id} 状态预检: ⚠️ 禁止转发 (has_protected_content=True)")
                else:
                    # 允许转发
                    allow_forward = True
                    logger.info(f"频道 {channel_id} 状态预检: ✓ 允许转发 (has_protected_content=False)")
                
                # 缓存结果
                self.channel_forward_status[str(channel_id)] = allow_forward
                results[str(channel_id)] = allow_forward
                
            except Exception as e:
                logger.warning(f"获取频道 {channel_id} 的保护内容状态失败: {str(e)[:100]}")
                # 默认为允许转发
                results[str(channel_id)] = True
                self.channel_forward_status[str(channel_id)] = True
        
        return results
    
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
            
            # 预检查所有频道的转发状态
            all_channels = [source_identifier] + target_identifiers
            logger.info("开始预检查所有频道的转发状态...")
            channel_status = await self.check_channel_forward_status(all_channels)
            
            # 根据预检查结果排序目标频道，优先使用允许转发的频道
            logger.info("根据转发状态对目标频道进行排序...")
            # 将禁止转发的频道移到列表末尾
            target_identifiers.sort(key=lambda x: 0 if channel_status.get(str(x), True) else 1)
            
            # 记录排序后的频道状态
            for channel in target_identifiers:
                status = "允许转发" if channel_status.get(str(channel), True) else "禁止转发"
                logger.info(f"目标频道 {channel} 状态: {status}")
            
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
                            
                            # 根据频道状态重新排序目标频道，优先使用可转发的频道
                            sorted_target_channels = sorted(
                                target_channels_str, 
                                key=lambda x: 0 if self.channel_forward_status.get(str(x), True) else 1
                            )
                            
                            logger.info(f"已对上传目标频道进行排序，优先使用允许转发的频道")
                            
                            # 读取配置
                            config_parser = configparser.ConfigParser()
                            config_parser.read(self.config_path, encoding='utf-8')
                            
                            api_id = config_parser.getint('API', 'api_id')
                            api_hash = config_parser.get('API', 'api_hash')
                            
                            # 获取正确的代理配置
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
                                    "port": port
                                }
                                
                                if username:
                                    proxy["username"] = username
                                    
                                if password:
                                    proxy["password"] = password
                            
                            # 使用新的参数调用upload_from_source
                            async with Client(
                                "forwarder_upload_client",
                                api_id=api_id,
                                api_hash=api_hash,
                                proxy=proxy
                            ) as client:
                                media_sender = CustomMediaGroupSender(
                                    client=client,
                                    config_parser=config_parser,
                                    target_channels=sorted_target_channels,
                                    temp_folder=download_config['temp_folder'],
                                    channel_forward_status=self.channel_forward_status
                                )
                                
                                # 使用对象实例方法而非类方法
                                upload_result = await media_sender.upload_from_source(
                                    source_dir=download_config['temp_folder'],
                                    filter_pattern="*",
                                    batch_size=10,
                                    max_workers=2,
                                    delete_after_upload=True
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