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
from tg_forwarder.utils.channel_utils import ChannelUtils, get_channel_utils, parse_channel
from tg_forwarder.forward.forwarder import MessageForwarder
from tg_forwarder.logModule.logger import setup_logger, get_logger
from tg_forwarder.client import Client

# 添加新导入的模块
from tg_forwarder.taskQueue import TaskQueue
from tg_forwarder.downloader.message_fetcher import MessageFetcher
from tg_forwarder.downloader.media_downloader import MediaDownloader
from tg_forwarder.uploader.assember import MessageAssembler
from tg_forwarder.uploader.media_uploader import MediaUploader

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
        # 使用ChannelUtils替代原来的channel_validator和channel_state_manager
        self.channel_utils = None
    
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
            
            # 初始化ChannelUtils
            self.channel_utils = ChannelUtils(self.client)
            
            # 创建消息转发器
            forward_config = self.config.get_forward_config()
            self.forwarder = MessageForwarder(self.client, forward_config)
            
            logger.info("所有组件初始化完成")
        except Exception as e:
            logger.error(f"初始化组件时出错: {str(e)}")
            raise
        
    async def shutdown(self) -> None:
        """关闭所有组件并释放资源"""
        if self.client:
            await self.client.disconnect()
        
        logger.info("已关闭所有组件")
    
    async def validate_channels(self) -> Tuple[List[str], List[str]]:
        """
        验证频道列表
        
        Returns:
            Tuple[List[str], List[str]]: (有效频道列表, 无效频道列表)
        """
        # 获取目标频道列表
        target_channels = self.config.get_target_channels()
        
        # 使用channel_utils验证频道
        result = await self.channel_utils.validate_channels(target_channels)
        
        # 从结果提取有效和无效频道
        valid_channels = result["valid_channels"]
        invalid_channels = result["invalid_channels"]
        
        return valid_channels, invalid_channels
    
    async def select_source_channel(self, valid_channels: List[str]) -> Optional[str]:
        """
        选择源频道
        
        Args:
            valid_channels: 有效频道列表
            
        Returns:
            Optional[str]: 选择的源频道，如果没有找到合适的源频道则返回None
        """
        if not valid_channels:
            logger.error("没有有效的频道可选择")
            return None
            
        # 使用channel_utils获取频道状态并排序
        # 优先考虑允许转发的频道作为源
        sorted_channels = self.channel_utils.sort_channels_by_status(valid_channels)
        
        for channel in sorted_channels:
            # 检查频道是否允许转发
            if self.channel_utils.get_forward_status(channel):
                logger.info(f"已选择频道 {channel} 作为转发源")
                return channel
        
        # 如果没有找到允许转发的频道，使用第一个频道作为源
        # 但发出警告
        logger.warning("没有找到允许转发的频道，将使用第一个频道作为源")
        logger.warning("注意: 这可能无法正常工作，因为该频道禁止转发内容")
        return valid_channels[0]
    
    async def update_channel_status(self, channel: str) -> bool:
        """
        更新频道状态信息
        
        Args:
            channel: 频道标识符
            
        Returns:
            bool: 是否允许转发
        """
        # 使用channel_utils获取或更新频道状态
        if not self.channel_utils.is_cached(channel):
            logger.info(f"更新频道 {channel} 的状态信息")
            result = await self.channel_utils.validate_channel(channel)
            return result["allow_forward"]
        return self.channel_utils.get_forward_status(channel)
    
    async def parse_channels(self) -> Tuple[Optional[Union[str, int]], List[Union[str, int]], Dict[str, Any]]:
        """
        解析配置中的频道设置
        
        Returns:
            Tuple[Optional[Union[str, int]], List[Union[str, int]], Dict[str, Any]]:
                (源频道标识符, 目标频道标识符列表, 额外配置)
        """
        logger.info("开始解析频道配置...")
        
        # 获取频道配置
        channels_config = self.config.get_channels_config()
        
        # 获取目标频道列表
        target_channels = channels_config['target_channels']
        if not target_channels:
            logger.error("未设置目标频道")
            return None, [], {}
            
        # 获取源频道设置
        source_channel = channels_config['source_channel']
        
        # 先验证所有的目标频道
        logger.info(f"验证目标频道: {', '.join(target_channels)}")
        result = await self.channel_utils.validate_channels(target_channels)
        
        valid_channels = result["valid_channels"]
        invalid_channels = result["invalid_channels"]
        
        if not valid_channels:
            logger.error("没有有效的目标频道，终止程序")
            return None, [], {}
            
        # 如果源频道为空或设为auto，则自动选择第一个允许转发的频道作为源
        auto_select = False
        if not source_channel or source_channel.lower() == 'auto':
            auto_select = True
            logger.info("使用自动选择模式选择源频道")
        
        # 源频道和目标频道分开处理，确保正确的转发方向
        if auto_select:
            # 按照转发状态排序频道
            source_identifier = await self.select_source_channel(valid_channels)
            if not source_identifier:
                logger.error("没有找到合适的源频道")
                return None, [], {}
                
            # 从目标列表中移除源频道
            if source_identifier in valid_channels:
                valid_channels.remove(source_identifier)
                
            # 如果没有有效目标频道，终止程序
            if not valid_channels:
                logger.error("没有有效的目标频道（源频道已从目标列表中移除）")
                return None, [], {}
                
            logger.info(f"自动选择 {source_identifier} 作为源频道")
            logger.info(f"有效目标频道: {', '.join(map(str, valid_channels))}")
            
            # 使用从验证结果获取的channel_id，确保标识符有效
            source_identifiers_map = {}
            for channel in valid_channels:
                channel_result = result["details"].get(channel, {})
                if channel_result.get("valid") and channel_result.get("channel_id"):
                    source_identifiers_map[channel] = channel_result["channel_id"]
            
            # 更新target_identifiers使用验证过的channel_id
            target_identifiers = [source_identifiers_map.get(ch, ch) for ch in valid_channels]
            
        else:
            # 验证源频道
            logger.info(f"验证源频道: {source_channel}")
            source_result = await self.channel_utils.validate_channel(source_channel)
            
            # 增加更详细的日志输出
            logger.debug(f"源频道验证结果: {source_result}")
            
            if not source_result["valid"]:
                error_msg = source_result["error"] or "未知错误"
                logger.error(f"源频道 {source_channel} 无效: {error_msg}")
                return None, [], {"error": f"源频道无效: {error_msg}", "success_flag": False}
            
            # 再次检查channel_id是否有效
            if not source_result.get("channel_id"):
                logger.error(f"源频道 {source_channel} 虽然被标记为有效，但没有获取到有效的channel_id")
                return None, [], {"error": "未能获取有效的源频道ID", "success_flag": False}
                
            logger.info(f"源频道 {source_channel} 有效，ID: {source_result['channel_id']}, 标题: {source_result.get('title', '未知')}")
            
            # 使用从验证结果获取的channel_id，而不是再次解析
            source_identifier = source_result["channel_id"]
            
            # 从目标列表中移除源频道
            target_identifiers = []
            for channel in valid_channels:
                if channel != source_channel:
                    channel_id, _ = parse_channel(channel)
                    target_identifiers.append(channel_id)
            
            if not target_identifiers:
                logger.error("没有有效的目标频道（源频道已从目标列表中移除）")
                return None, [], {}
                
            logger.info(f"使用用户指定的源频道: {source_channel}")
            logger.info(f"有效目标频道: {', '.join(map(str, valid_channels))}")
        
        # 检查源频道是否允许转发
        source_allow_forward = self.channel_utils.get_forward_status(source_identifier)
        
        # 根据预检查结果排序目标频道，使用管理器的排序方法
        logger.info("根据转发状态对目标频道进行排序...")
        sorted_targets = self.channel_utils.sort_channels_by_status(target_identifiers)
        
        # 记录排序后的频道状态
        logger.info(f"源频道 {source_identifier} 状态: {'允许转发' if source_allow_forward else '禁止转发'}")
        for channel in sorted_targets:
            status = "允许转发" if self.channel_utils.get_forward_status(channel) else "禁止转发"
            logger.info(f"目标频道 {channel} 状态: {status}")
        
        # 返回额外配置
        extra_configs = {
            "batch_size": self.config.get_forward_config().get('batch_size', 10),
            "delay_between_messages": self.config.get_forward_config().get('delay', 10),
            "delay_between_batches": 60,  # 使用默认值
            "captions": {},  # 使用空字典替代 get_captions() 方法的结果
            "stop_on_error": False,  # 使用默认值
            "copy_voice_note": True,  # 使用默认值
            "auto_select_source": auto_select,
            "source_allow_forward": source_allow_forward
        }
        
        return source_identifier, sorted_targets, extra_configs
    
    async def prepare_channels(self, source_identifier: Union[str, int], target_identifiers: List[Union[str, int]]) -> Tuple[bool, List[Union[str, int]]]:
        """
        预检查频道状态并对目标频道进行排序
        
        Args:
            source_identifier: 源频道标识符
            target_identifiers: 目标频道标识符列表
            
        Returns:
            Tuple[bool, List[Union[str, int]]]: 返回(源频道是否允许转发, 排序后的目标频道列表)
        """
        # 预检查所有频道的转发状态
        all_channels = [source_identifier] + target_identifiers
        logger.info("开始预检查所有频道的转发状态...")
        channel_status = await self.check_channel_forward_status(all_channels)
        
        # 检查源频道是否允许转发
        source_allow_forward = self.channel_utils.get_forward_status(source_identifier)
        
        # 根据预检查结果排序目标频道，使用管理器的排序方法
        logger.info("根据转发状态对目标频道进行排序...")
        sorted_targets = self.channel_utils.sort_channels_by_status(target_identifiers)
        
        # 记录排序后的频道状态
        logger.info(f"源频道 {source_identifier} 状态: {'允许转发' if source_allow_forward else '禁止转发'}")
        for channel in sorted_targets:
            status = "允许转发" if self.channel_utils.get_forward_status(channel) else "禁止转发"
            logger.info(f"目标频道 {channel} 状态: {status}")
        
        return source_allow_forward, sorted_targets
    
    async def process_normal_forward(self, source_identifier: Union[str, int], target_identifiers: List[Union[str, int]], 
                                   start_message_id: int, end_message_id: int) -> Dict[str, Any]:
        """
        处理正常转发流程
        
        Args:
            source_identifier: 源频道标识符
            target_identifiers: 目标频道标识符列表
            start_message_id: 起始消息ID
            end_message_id: 结束消息ID
            
        Returns:
            Dict[str, Any]: 处理结果统计
        """
        logger.info("源频道允许转发，使用正常转发流程...")
        result = await self.forwarder.process_messages(
            source_identifier,
            target_identifiers,
            start_message_id,
            end_message_id
        )
        
        # 处理普通转发中的错误（非禁止转发导致的失败）
        if result.get("failed", 0) > 0 and "failed_messages" in result:
            await self.handle_forward_errors(result)
        else:
            logger.info("所有消息转发成功")
        
        # 添加成功标志
        result["success_flag"] = True
        
        return result
    
    async def handle_forward_errors(self, result: Dict[str, Any]) -> None:
        """
        处理转发过程中的错误
        
        Args:
            result: 转发结果字典
        """
        failed_count = result.get("failed", 0)
        failed_message_ids = result.get("failed_messages", [])
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
    
    async def _get_real_channel_ids(self, source_identifier, sorted_targets):
        """
        获取源频道和目标频道的真实ID
        
        Args:
            source_identifier: 源频道标识符
            sorted_targets: 排序后的目标频道标识符列表
            
        Returns:
            Dict[str, Any]: 包含真实ID和可能的错误信息
        """
        try:
            # 获取源频道真实ID
            real_source_id, error = await self.channel_utils.get_real_chat_id(source_identifier)
            if error:
                return {"success": False, "error": error}
            
            # 获取目标频道真实ID列表
            real_target_ids = []
            for target in sorted_targets:
                real_target_id, error = await self.channel_utils.get_real_chat_id(target)
                if real_target_id:
                    real_target_ids.append(real_target_id)
                else:
                    logger.warning(f"无法获取目标频道 {target} 的真实ID: {error}")
            
            if not real_target_ids:
                logger.error("没有有效的目标频道")
                return {"success": False, "error": "没有有效的目标频道"}
            
            return {
                "success": True, 
                "source_id": real_source_id, 
                "target_ids": real_target_ids
            }
            
        except Exception as e:
            logger.error(f"获取频道真实ID时出错: {str(e)}")
            return {"success": False, "error": f"获取频道真实ID时出错: {str(e)}"}

    async def _setup_media_components(self, target_channels=None):
        """
        设置媒体处理相关组件
        
        Args:
            target_channels: 目标频道ID列表，默认为None
            
        Returns:
            Dict[str, Any]: 包含创建的组件和配置
        """
        # 创建下载配置
        download_config = self.config.get_download_config()
        
        # 创建上传配置
        upload_config = self.config.get_upload_config()
        
        # 获取转发配置
        forward_config = self.config.get_forward_config()
        
        # 创建消息获取器
        message_fetcher = MessageFetcher(
            client=self.client,
            batch_size=forward_config.get('batch_size', 30)
        )
        
        # 创建媒体下载器
        media_downloader = MediaDownloader(
            client=self.client,
            concurrent_downloads=download_config["concurrent_downloads"],
            temp_folder=download_config["temp_folder"],
            retry_count=download_config["retry_count"],
            retry_delay=download_config["retry_delay"]
        )
        
        # 创建消息重组器
        message_assembler = MessageAssembler(
            metadata_path=os.path.join(download_config["temp_folder"], "message_metadata.json"),
            download_mapping_path=os.path.join(download_config["temp_folder"], "download_mapping.json")
        )
        
        # 如果没有提供target_channels，使用一个占位值以通过验证
        if target_channels is None or len(target_channels) == 0:
            # 使用一个占位的目标频道ID，这将在实际使用前被替换
            placeholder_target = [-1]  # 使用一个不可能是真实频道ID的值
            logger.debug("使用占位目标频道ID初始化上传器")
        else:
            placeholder_target = target_channels
            logger.debug(f"使用提供的 {len(placeholder_target)} 个目标频道初始化上传器")
        
        # 创建媒体上传器
        media_uploader = MediaUploader(
            client=self.client,
            target_channels=placeholder_target,
            temp_folder=download_config["temp_folder"],
            wait_time=upload_config["wait_between_messages"],
            retry_count=upload_config.get("retry_count", download_config["retry_count"]),
            retry_delay=upload_config.get("retry_delay", download_config["retry_delay"])
        )
        
        # 初始化媒体上传器的临时客户端
        logger.info("初始化媒体上传器临时客户端...")
        await media_uploader.initialize()
        
        return {
            "message_fetcher": message_fetcher,
            "media_downloader": media_downloader,
            "message_assembler": message_assembler,
            "media_uploader": media_uploader,
            "download_config": download_config,
            "upload_config": upload_config
        }

    async def _download_producer(self, message_fetcher, media_downloader, real_source_id, 
                               start_message_id, end_message_id, download_upload_queue, pipeline_control):
        """
        下载生产者任务，处理消息的获取和媒体下载
        
        Args:
            message_fetcher: 消息获取器实例
            media_downloader: 媒体下载器实例
            real_source_id: 源频道的真实ID
            start_message_id: 起始消息ID
            end_message_id: 结束消息ID
            download_upload_queue: 下载和上传之间的队列
            pipeline_control: 流水线控制字典
        """
        try:
            # 获取消息批次
            async for batch in message_fetcher.get_messages(
                real_source_id,
                start_message_id,
                end_message_id
            ):
                logger.info(f"获取到批次 {batch['id']}, 开始下载处理")
                
                # 按媒体组处理，而不是整个批次
                media_groups = batch.get("media_groups", [])
                single_messages = batch.get("single_messages", [])
                
                # 处理媒体组
                for group_index, group_messages in enumerate(media_groups):
                    # 从第一个消息获取媒体组ID
                    if group_messages and len(group_messages) > 0:
                        first_message = group_messages[0]
                        group_id = first_message.media_group_id if hasattr(first_message, "media_group_id") else f"group_{group_index}"
                        logger.info(f"开始下载媒体组 {group_id}，包含 {len(group_messages)} 个文件")
                        
                        # 为该媒体组创建一个小批次
                        group_batch = {
                            "id": f"group_{group_id}",
                            "parent_batch_id": batch.get("id"),
                            "media_groups": [group_messages],  # 使用列表包装
                            "messages": [],
                            "progress": batch.get("progress", 0)
                        }
                        
                        # 下载这个媒体组的所有文件
                        download_result = await media_downloader.download_media_batch(group_batch)
                        
                        # 如果下载成功，立即添加到上传队列
                        if download_result.get("success", 0) > 0:
                            download_task = {
                                "batch_id": group_batch.get("id"),
                                "batch": group_batch,
                                "download_result": download_result,
                                "progress": group_batch.get("progress", 0)
                            }
                            
                            await download_upload_queue.put(download_task)
                            pipeline_control["download_count"] += 1
                            logger.info(f"媒体组 {group_id} 下载完成并进入上传流水线，共 {download_result.get('success', 0)} 个文件")
                        else:
                            logger.warning(f"媒体组 {group_id} 下载失败或无内容，跳过上传")
                
                # 处理单条消息（每条消息作为一个任务）
                for message in single_messages:
                    # 使用直接属性访问而不是get方法
                    message_id = message.id if hasattr(message, "id") else "unknown"
                    logger.info(f"开始下载单条消息 {message_id}")
                    
                    # 为单条消息创建一个小批次
                    message_batch = {
                        "id": f"message_{message_id}",
                        "parent_batch_id": batch.get("id"),
                        "media_groups": {},
                        "messages": [message],
                        "progress": batch.get("progress", 0)
                    }
                    
                    # 下载这条消息
                    download_result = await media_downloader.download_media_batch(message_batch)
                    
                    # 如果下载成功，立即添加到上传队列
                    if download_result.get("success", 0) > 0:
                        download_task = {
                            "batch_id": message_batch.get("id"),
                            "batch": message_batch,
                            "download_result": download_result,
                            "progress": message_batch.get("progress", 0)
                        }
                        
                        await download_upload_queue.put(download_task)
                        pipeline_control["download_count"] += 1
                        logger.info(f"消息 {message_id} 下载完成并进入上传流水线")
                    else:
                        logger.warning(f"消息 {message_id} 下载失败或无内容，跳过上传")
                    
                logger.info(f"批次 {batch['id']} 所有媒体组和单条消息处理完成")
                
        except Exception as e:
            logger.error(f"下载生产者任务出错: {str(e)}")
            import traceback
            logger.error(f"错误详情: {traceback.format_exc()}")
        finally:
            # 标记下载完成
            pipeline_control["downloading_complete"] = True
            logger.info(f"所有下载任务完成，总计下载 {pipeline_control['download_count']} 个项目")

    async def _upload_producer(self, upload_queue, download_upload_queue, pipeline_control):
        """
        上传生产者任务，负责从下载队列获取任务并放入上传队列
        
        Args:
            upload_queue: 上传任务队列
            download_upload_queue: 下载上传中间队列
            pipeline_control: 流水线控制字典
        """
        try:
            while not (pipeline_control["downloading_complete"] and download_upload_queue.empty()):
                try:
                    # 使用超时获取，允许检查循环终止条件
                    download_task = await asyncio.wait_for(download_upload_queue.get(), timeout=1.0)
                    
                    # 将下载任务放入上传队列
                    await upload_queue.put(download_task)
                    
                    # 标记队列任务完成
                    download_upload_queue.task_done()
                    
                except asyncio.TimeoutError:
                    # 超时只是为了检查条件，继续循环
                    continue
                except Exception as e:
                    logger.error(f"上传生产者处理任务时出错: {str(e)}")
        except Exception as e:
            logger.error(f"上传生产者任务出错: {str(e)}")
            import traceback
            logger.error(f"错误详情: {traceback.format_exc()}")

    async def _upload_consumer(self, download_task, message_assembler, media_uploader, 
                             pipeline_control, result):
        """
        上传消费者任务，负责处理单个下载任务的上传
        
        Args:
            download_task: 下载任务信息
            message_assembler: 消息重组器实例
            media_uploader: 媒体上传器实例
            pipeline_control: 流水线控制字典
            result: 结果统计字典
            
        Returns:
            Dict or bool: 处理结果或状态
        """
        try:
            batch_id = download_task.get("batch_id")
            download_result = download_task.get("download_result")
            
            # 检查是否已处理过该批次，避免重复转发
            if batch_id in pipeline_control["processed_items"]:
                logger.info(f"批次 {batch_id} 已处理过，跳过")
                return True
            
            logger.info(f"开始处理批次 {batch_id} 的上传任务")
            
            # 获取下载文件列表
            files = download_result.get("files", [])
            if not files:
                logger.warning(f"批次 {batch_id} 没有可用文件，跳过上传")
                return True
                
            # 记录下载的文件信息，用于调试
            logger.debug(f"准备组装批次 {batch_id} 的 {len(files)} 个文件")
            if files:
                for i, file in enumerate(files[:3]):
                    logger.debug(f"文件 {i+1}: message_id={file.get('message_id')}, " +
                               f"media_group_id={file.get('media_group_id')}, " + 
                               f"file_path={file.get('file_path', '')[-30:]}")
                if len(files) > 3:
                    logger.debug(f"... 等共 {len(files)} 个文件")
            
            # 重组消息
            assembled_data = message_assembler.assemble_batch(files)
            
            # 记录重组结果
            media_groups = assembled_data.get("media_groups", [])
            single_messages = assembled_data.get("single_messages", [])
            logger.info(f"重组结果: {len(media_groups)} 个媒体组, {len(single_messages)} 条单独消息")
            
            # 上传重组后的消息
            upload_result = await media_uploader.upload_batch(assembled_data)
            
            # 更新统计信息
            result["processed"] += upload_result.get("total_messages", 0)
            result["success"] += upload_result.get("success_total", 0)
            result["failed"] += upload_result.get("failed_total", 0)
            
            # 标记该批次已处理
            pipeline_control["processed_items"].add(batch_id)
            pipeline_control["upload_count"] += 1
            
            logger.info(f"批次 {batch_id} 上传完成，成功: {upload_result.get('success_total', 0)}，" +
                      f"失败: {upload_result.get('failed_total', 0)}，" +
                      f"已完成: {pipeline_control['upload_count']}/{pipeline_control['download_count']}")
            
            return {
                "batch_id": batch_id,
                "download": download_result,
                "upload": upload_result
            }
        except Exception as e:
            logger.error(f"上传消费者任务出错: {str(e)}")
            import traceback
            logger.error(f"错误详情: {traceback.format_exc()}")
            return False

    async def _process_download_upload(self, real_source_id, real_target_ids, 
                                     start_message_id, end_message_id):
        """
        处理下载上传流程（当源频道禁止转发时使用）
        
        Args:
            real_source_id: 源频道真实ID
            real_target_ids: 目标频道真实ID列表
            start_message_id: 起始消息ID
            end_message_id: 结束消息ID
            
        Returns:
            Dict[str, Any]: 处理结果统计
        """
        # 初始化结果字典
        result = {
            "forwards_restricted": True,
            "total": end_message_id - start_message_id + 1 if end_message_id and start_message_id else 0,
            "processed": 0,
            "success": 0,
            "failed": 0,
            "start_time": time.time(),
        }
        
        components = None
        try:
            # 检查目标频道列表是否为空
            if not real_target_ids:
                logger.error("目标频道列表为空，无法进行下载上传")
                result["error"] = "目标频道列表为空"
                result["success_flag"] = False
                return result
            
            # 设置媒体处理组件，直接传入目标频道列表
            components = await self._setup_media_components(target_channels=real_target_ids)
            
            # 提取组件
            message_fetcher = components["message_fetcher"]
            media_downloader = components["media_downloader"]
            message_assembler = components["message_assembler"]
            media_uploader = components["media_uploader"]
            upload_config = components["upload_config"]
            
            # 确认上传器已使用正确的目标频道
            logger.info(f"上传器将发送消息到 {len(media_uploader.target_channels)} 个目标频道")
            
            # 创建共享队列，用于连接下载和上传流程
            download_upload_queue = asyncio.Queue(maxsize=10)
            
            # 创建媒体处理流水线的控制标志
            pipeline_control = {
                "downloading_complete": False,
                "processed_items": set(),  # 用于跟踪已处理项目，避免重复转发
                "download_count": 0,
                "upload_count": 0
            }
            
            logger.info("开始下载和上传并行处理流水线...")
            
            # 创建下载任务
            download_task = asyncio.create_task(
                self._download_producer(
                    message_fetcher, media_downloader, real_source_id,
                    start_message_id, end_message_id, download_upload_queue, pipeline_control
                )
            )
            
            # 创建上传任务队列
            upload_queue = TaskQueue(
                max_queue_size=upload_config.get("concurrent_uploads", 3), 
                max_workers=upload_config.get("concurrent_uploads", 3)
            )
            
            # 启动上传任务队列
            upload_task = asyncio.create_task(
                upload_queue.run(
                    lambda queue=upload_queue: self._upload_producer(queue, download_upload_queue, pipeline_control),
                    lambda task: self._upload_consumer(task, message_assembler, media_uploader, pipeline_control, result)
                )
            )
            
            # 等待下载任务和上传任务完成
            try:
                # 增加超时保护，避免无限等待
                download_future = asyncio.ensure_future(download_task)
                upload_future = asyncio.ensure_future(upload_task)
                
                # 设置最大等待时间（根据任务量可调整）
                max_wait_time = 3600  # 1小时
                
                # 等待所有任务完成或超时
                await asyncio.wait(
                    [download_future, upload_future],
                    timeout=max_wait_time,
                    return_when=asyncio.ALL_COMPLETED
                )
                
                # 检查是否有任务因超时未完成
                if not download_future.done():
                    logger.warning("下载任务执行超时，强制结束")
                    download_future.cancel()
                
                if not upload_future.done():
                    logger.warning("上传任务执行超时，强制结束")
                    upload_future.cancel()
                    
                # 检查任务是否有异常
                for future, name in [(download_future, "下载"), (upload_future, "上传")]:
                    if future.done() and not future.cancelled():
                        try:
                            future.result()
                        except Exception as e:
                            logger.error(f"{name}任务执行出错: {str(e)}")
                
                # 确保下载完成标志已设置，防止上传队列死锁
                pipeline_control["downloading_complete"] = True
                
            except asyncio.TimeoutError:
                logger.error("等待下载和上传任务完成超时")
                pipeline_control["downloading_complete"] = True
            except Exception as e:
                logger.error(f"等待任务完成时出错: {str(e)}")
                pipeline_control["downloading_complete"] = True
            
            # 更新结果统计
            result.update({
                "download_count": pipeline_control["download_count"],
                "upload_count": pipeline_control["upload_count"],
                "error": None,
                "success_flag": True  # 添加成功标志
            })
            
            logger.info(f"下载上传流水线任务完成，总计下载: {result.get('download_count')} 批次，"
                       f"总计上传: {result.get('upload_count')} 批次，"
                       f"成功: {result.get('success')} 条，失败: {result.get('failed')} 条")
        
        except Exception as e:
            logger.error(f"下载上传过程中发生错误: {str(e)}")
            import traceback
            logger.error(traceback.format_exc())
            result["error"] = f"下载上传过程中发生错误: {str(e)}"
            result["success_flag"] = False  # 失败标志
        
        finally:
            # 关闭媒体上传器临时客户端
            if components and 'media_uploader' in components:
                logger.info("关闭媒体上传器临时客户端...")
                await components["media_uploader"].shutdown()
        
        return result

    def _create_error_result(self, error_message):
        """
        创建标准错误结果字典
        
        Args:
            error_message: 错误信息
            
        Returns:
            Dict[str, Any]: 错误结果字典
        """
        return {
            "success_flag": False,
            "error": error_message
        }

    async def run(self) -> Dict[str, Any]:
        """
        运行转发流程
        
        Returns:
            Dict[str, Any]: 处理结果统计
        """
        try:
            # 1. 解析频道信息
            source_identifier, target_identifiers, extra_configs = await self.parse_channels()
            
            # 检查是否有错误结果返回
            if isinstance(extra_configs, dict) and "error" in extra_configs:
                logger.error(f"频道解析失败: {extra_configs.get('error')}")
                return {
                    "success_flag": False, 
                    "error": extra_configs.get('error', "频道解析失败")
                }
            
            if not source_identifier:
                return self._create_error_result("无法找到有效的源频道")
            
            if not target_identifiers:
                return self._create_error_result("无法找到有效的目标频道")
            
            # 2. 预检查频道状态并排序目标频道
            source_allow_forward, sorted_targets = await self.prepare_channels(source_identifier, target_identifiers)
            
            # 3. 获取源频道和目标频道的真实ID
            logger.info("获取源频道和目标频道的真实ID...")
            channel_id_result = await self._get_real_channel_ids(source_identifier, sorted_targets)
            
            if not channel_id_result["success"]:
                return self._create_error_result(channel_id_result["error"])
            
            real_source_id = channel_id_result["source_id"]
            real_target_ids = channel_id_result["target_ids"]
            
            # 4. 获取转发配置
            forward_config = self.config.get_forward_config()
            start_message_id = forward_config['start_message_id']
            end_message_id = forward_config['end_message_id']
            
            # 5. 根据源频道转发状态选择处理方式
            if source_allow_forward:
                # 源频道允许转发，使用正常转发流程
                result = await self.process_normal_forward(
                    real_source_id,
                    real_target_ids,
                    start_message_id,
                    end_message_id
                )
            else:
                # 源频道禁止转发，使用下载上传流程
                logger.warning("源频道禁止转发消息，启动下载上传流程")
                result = await self._process_download_upload(
                    real_source_id,
                    real_target_ids,
                    start_message_id,
                    end_message_id
                )
            
            # 6. 计算总耗时
            result["end_time"] = time.time()
            result["duration"] = result.get("end_time", 0) - result.get("start_time", 0)
            logger.info(f"总耗时: {result.get('duration', 0):.2f}秒")
            
            # 7. 添加成功标志（如果尚未设置）
            if "success_flag" not in result:
                result["success_flag"] = True
            
            return result
        
        except Exception as e:
            logger.error(f"转发过程中发生错误: {str(e)}")
            import traceback
            logger.error(traceback.format_exc())
            return self._create_error_result(str(e))
    
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

    async def check_channel_forward_status(self, channels: List[Union[str, int]]) -> Dict[Union[str, int], bool]:
        """
        检查多个频道的转发状态
        
        Args:
            channels: 频道标识符列表
            
        Returns:
            Dict[Union[str, int], bool]: 频道ID到转发状态的映射
        """
        channel_status = {}
        for channel in channels:
            logger.info(f"检查频道 {channel} 的转发状态...")
            if self.channel_utils.is_cached(channel):
                status = self.channel_utils.get_forward_status(channel)
                channel_status[channel] = status
                logger.info(f"频道 {channel} 状态 (缓存): {'允许转发' if status else '禁止转发'}")
            else:
                # 验证频道并获取状态
                result = await self.channel_utils.validate_channel(channel)
                status = result.get("allow_forward", False)
                channel_status[channel] = status
                logger.info(f"频道 {channel} 状态 (新查询): {'允许转发' if status else '禁止转发'}")
                
        return channel_status 