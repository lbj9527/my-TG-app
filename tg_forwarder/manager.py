"""
流程管理模块，负责整体流程的协调
"""

import asyncio
from typing import Dict, Any, Optional, List, Union, Tuple
import logging
import sys
import os
import configparser
import time

from tg_forwarder.config import Config
from tg_forwarder.client import TelegramClient
from tg_forwarder.channel_parser import ChannelParser, ChannelValidator
from tg_forwarder.media_handler import MediaHandler
from tg_forwarder.forwarder import MessageForwarder
from tg_forwarder.utils.logger import setup_logger, get_logger
from tg_forwarder.customUploader import CustomMediaGroupSender
from tg_forwarder.client import Client
from tg_forwarder.downloader import MediaDownloader

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
        self.config_path = config_path
        self.config = Config(config_path)
        self.client = None
        self.forwarder = None
        self.media_handler = None
        self.downloader = None
        self.channel_validator = None
        self.channel_forward_status = {}
    
    async def setup(self) -> None:
        """初始化组件"""
        try:
            # 创建Pyrogram客户端
            self.client = TelegramClient(
                api_config=self.config.get_api_config(),
                proxy_config=self.config.get_proxy_config()
            )
            
            # 连接到Telegram
            await self.client.connect()
            
            # 创建频道验证器
            self.channel_validator = ChannelValidator(self.client)
            
            # 创建媒体下载器
            download_config = self.config.get_download_config()
            self.downloader = MediaDownloader(self.client, download_config)
            
            # 创建媒体处理器
            media_config = self.config.get_media_config()
            self.media_handler = MediaHandler(self.client, media_config)
            
            # 创建消息转发器
            forward_config = self.config.get_forward_config()
            self.forwarder = MessageForwarder(self.client, forward_config, self.media_handler)
            
            logger.info("所有组件初始化完成")
        except Exception as e:
            logger.error(f"初始化组件时出错: {str(e)}")
            raise
    
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
                source_identifier, _ = ChannelParser.parse_channel(source_channel_str)
                logger.info(f"源频道: {ChannelParser.format_channel_identifier(source_identifier)}")
            except Exception as e:
                logger.error(f"解析源频道失败: {str(e)}")
                return {"success": False, "error": f"解析源频道失败: {str(e)}"}
            
            # 解析目标频道
            target_identifiers = []
            for target_str in target_channels_str:
                try:
                    target_identifier, _ = ChannelParser.parse_channel(target_str)
                    target_identifiers.append(target_identifier)
                    logger.info(f"目标频道: {ChannelParser.format_channel_identifier(target_identifier)}")
                except Exception as e:
                    logger.warning(f"解析目标频道 '{target_str}' 失败: {str(e)}")
            
            if not target_identifiers:
                logger.error("没有有效的目标频道")
                return {"success": False, "error": "没有有效的目标频道"}
            
            # 预检查所有频道的转发状态
            all_channels = [source_identifier] + target_identifiers
            logger.info("开始预检查所有频道的转发状态...")
            channel_status = await self.check_channel_forward_status(all_channels)
            
            # 检查源频道是否允许转发
            source_allow_forward = channel_status.get(str(source_identifier), True)
            
            # 根据预检查结果排序目标频道，优先使用允许转发的频道
            logger.info("根据转发状态对目标频道进行排序...")
            # 将禁止转发的频道移到列表末尾
            target_identifiers.sort(key=lambda x: 0 if channel_status.get(str(x), True) else 1)
            
            # 记录排序后的频道状态
            logger.info(f"源频道 {source_identifier} 状态: {'允许转发' if source_allow_forward else '禁止转发'}")
            for channel in target_identifiers:
                status = "允许转发" if channel_status.get(str(channel), True) else "禁止转发"
                logger.info(f"目标频道 {channel} 状态: {status}")
            
            # 获取转发配置
            forward_config = self.config.get_forward_config()
            start_message_id = forward_config['start_message_id']
            end_message_id = forward_config['end_message_id']
            
            # 获取下载配置
            download_config = self.config.get_download_config()
            
            # 根据源频道转发状态选择处理方式
            if source_allow_forward:
                # 源频道允许转发，使用正常转发流程
                logger.info("源频道允许转发，使用正常转发流程...")
                result = await self.forwarder.process_messages(
                    source_identifier,
                    target_identifiers,
                    start_message_id,
                    end_message_id
                )
                
                # 处理普通转发中的错误（非禁止转发导致的失败）
                if result.get("failed", 0) > 0 and "failed_messages" in result:
                    failed_count = result.get("failed", 0)
                    failed_message_ids = result["failed_messages"]
                    logger.warning(f"检测到 {failed_count} 条消息转发失败，将直接跳过这些消息")
                    
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
                    logger.info("所有消息转发成功")
                
            else:
                # 源频道禁止转发，直接使用备用方式
                logger.warning("源频道禁止转发消息，将使用备用方式: 下载文件后上传")
                try:
                    # 初始化结果字典
                    result = {
                        "forwards_restricted": True,
                        "total": end_message_id - start_message_id + 1 if end_message_id and start_message_id else 0,
                        "processed": 0,
                        "success": 0,
                        "failed": 0,
                        "start_time": time.time()
                    }
                    
                    # 读取配置文件以获取并行设置
                    config_parser = configparser.ConfigParser()
                    config_parser.read(self.config_path, encoding='utf-8')
                    
                    # 获取并行下载数量
                    parallel_downloads = 1
                    if config_parser.has_section('DOWNLOAD'):
                        parallel_downloads = config_parser.getint('DOWNLOAD', 'parallel_downloads', fallback=5)
                    logger.info(f"并行下载数量设置为: {parallel_downloads}")
                    
                    # 获取并行上传数量
                    parallel_uploads = 1
                    max_workers = 1
                    if config_parser.has_section('UPLOAD'):
                        parallel_uploads = config_parser.getint('UPLOAD', 'parallel_uploads', fallback=3)
                        max_workers = config_parser.getint('UPLOAD', 'max_workers', fallback=2)
                    logger.info(f"并行上传数量设置为: {parallel_uploads}, 最大工作线程: {max_workers}")
                    
                    # 下载源频道消息到本地
                    logger.info(f"开始并行下载源频道消息...")
                    
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
                            
                            # 从已有的Config实例获取配置信息，避免重复读取配置文件
                            api_config = self.config.get_api_config()
                            api_id = api_config['api_id']
                            api_hash = api_config['api_hash']
                            
                            # 获取正确的代理配置
                            proxy = None
                            proxy_config = self.config.get_proxy_config()
                            if proxy_config:
                                proxy = {
                                    "scheme": proxy_config['proxy_type'].lower(),
                                    "hostname": proxy_config['addr'],
                                    "port": proxy_config['port']
                                }
                                
                                if 'username' in proxy_config and proxy_config['username']:
                                    proxy["username"] = proxy_config['username']
                                    
                                if 'password' in proxy_config and proxy_config['password']:
                                    proxy["password"] = proxy_config['password']
                            
                            # 使用新的参数调用upload_from_source
                            async with Client(
                                "forwarder_upload_client",
                                api_id=api_id,
                                api_hash=api_hash,
                                proxy=proxy
                            ) as client:
                                media_sender = CustomMediaGroupSender(
                                    client=client,
                                    config_parser=config_parser,  # 使用已读取的配置
                                    target_channels=sorted_target_channels,
                                    temp_folder=download_config['temp_folder'],
                                    channel_forward_status=self.channel_forward_status
                                )
                                
                                # 使用对象实例方法而非类方法
                                upload_result = await media_sender.upload_from_source_instance(
                                    source_dir=download_config['temp_folder'],
                                    filter_pattern="*",
                                    batch_size=10,
                                    max_workers=max_workers,  # 使用配置的工作线程数
                                    delete_after_upload=True
                                )
                                
                                # 如果需要直接上传，修改send_to_all_channels方法的参数
                                media_sender.config["parallel_uploads"] = parallel_uploads
                            
                            # 合并上传结果到总结果
                            result["upload_results"] = upload_result
                            
                            if upload_result.get("success", False) or upload_result.get("success_flag", False) or upload_result:
                                # 如果能找到文件上传数或成功频道数，就认为上传成功
                                uploaded_files = upload_result.get("uploaded_files", 0)
                                if not uploaded_files:
                                    # 尝试从success字段计算上传文件数
                                    success_count = upload_result.get("success", 0)
                                    # 尝试获取总批次或消息数
                                    total_batches = len(upload_result.get("messages_by_channel", {}))
                                    uploaded_files = success_count or total_batches or 0
                                
                                success_channels = upload_result.get("success_channels", 0)
                                if not success_channels:
                                    # 尝试从success字段获取成功频道数
                                    success_channels = upload_result.get("success", 0)
                                
                                logger.info(f"备用上传成功: {uploaded_files} 个文件上传到 {success_channels} 个频道")
                                # 更新统计信息，将上传的文件数设为成功数
                                result["success"] = uploaded_files
                                result["failed"] = 0  # 既然备用上传成功，失败数应为0
                                result["success_flag"] = True  # 设置整体操作成功标志
                            else:
                                logger.error(f"备用上传失败: {upload_result.get('error', '未知错误')}")
                        else:
                            logger.warning("没有成功下载的媒体文件，无法进行备用上传")
                    else:
                        logger.warning("没有下载结果，无法进行备用上传")
                
                except Exception as e:
                    logger.error(f"备用方式处理时出错: {repr(e)}")
                    result["backup_error"] = str(e)
            
            # 计算总耗时
            result["end_time"] = time.time()
            result["duration"] = result.get("end_time", 0) - result.get("start_time", 0)
            logger.info(f"总耗时: {result.get('duration', 0):.2f}秒")
            
            return result
        
        except Exception as e:
            logger.error(f"转发过程中发生错误: {str(e)}")
            import traceback
            logger.error(traceback.format_exc())
            return {"success_flag": False, "error": str(e)}
    
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