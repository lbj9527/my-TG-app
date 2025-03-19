"""
媒体上传模块，负责上传媒体文件到目标频道
"""

import os
import asyncio
import time
from typing import Dict, Any, List, Union, Optional

from tg_forwarder.logModule.logger import get_logger
from tg_forwarder.uploader.utils import (
    UploaderConfigValidator,
    UploadHistoryManager,
    TelegramClientManager,
    MediaUtils
)
from tg_forwarder.uploader.message_sender import MessageSender

# 获取日志记录器
logger = get_logger("media_uploader")


class MediaUploader:
    """媒体上传器，负责上传媒体文件到目标频道"""
    
    def __init__(self, client, target_channels: List[Union[str, int]], temp_folder: str = "temp",
                 wait_time: float = 1.0, retry_count: int = 3, retry_delay: int = 5):
        """
        初始化媒体上传器
        
        Args:
            client: Telegram客户端
            target_channels: 目标频道列表
            temp_folder: 临时文件夹路径
            wait_time: 消息间隔时间（秒）
            retry_count: 重试次数
            retry_delay: 重试延迟时间（秒）
        """
        # 验证配置
        config = {
            'temp_folder': temp_folder,
            'wait_time': wait_time,
            'retry_count': retry_count,
            'retry_delay': retry_delay
        }
        self.config = UploaderConfigValidator.validate_upload_config(config)
        self.target_channels = UploaderConfigValidator.validate_channels(target_channels)
        
        # 创建历史记录管理器
        history_path = os.path.join(self.config['temp_folder'], "upload_history.json")
        self.history_manager = UploadHistoryManager(history_path)
        
        # 创建客户端管理器
        client_config = UploaderConfigValidator.validate_client_config(client)
        self.client_manager = TelegramClientManager(
            api_id=client_config['api_config']['api_id'],
            api_hash=client_config['api_config']['api_hash'],
            proxy_config=client_config['proxy_config'],
            session_name="media_uploader_fixed"  # 使用固定的会话名称
        )
        
        # 创建消息发送器
        self.message_sender = MessageSender(
            client_manager=self.client_manager,
            wait_time=self.config['wait_time'],
            retry_count=self.config['retry_count'],
            retry_delay=self.config['retry_delay']
        )
        
        # 当前是否已初始化
        self._initialized = False
    
    async def initialize(self):
        """
        初始化上传器，创建临时客户端
        应在开始使用上传器之前调用此方法
        
        Returns:
            bool: 初始化是否成功
        """
        if self._initialized:
            logger.info("上传器已经初始化")
            return True
        
        # 初始化客户端
        client_initialized = await self.client_manager.initialize()
        
        if client_initialized:
            # 启动历史记录自动保存
            self.history_manager.start_auto_save()
            self._initialized = True
            logger.info("上传器初始化成功")
            return True
        else:
            logger.error("上传器初始化失败：客户端初始化失败")
            return False
    
    async def shutdown(self):
        """
        关闭上传器，释放资源
        应在完成所有上传任务后调用此方法
        """
        # 停止历史记录自动保存
        self.history_manager.stop_auto_save()
        
        # 确保保存上传历史
        await self.history_manager.save_if_dirty()
        
        # 关闭客户端
        await self.client_manager.shutdown()
        
        self._initialized = False
        logger.info("上传器已关闭")
    
    async def upload_batch(self, batch_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        上传一批媒体文件
        
        Args:
            batch_data: 批次数据，包含媒体组和单条消息
            
        Returns:
            Dict[str, Any]: 上传结果
        """
        start_time = time.time()
        
        # 确保已初始化
        if not self._initialized:
            success = await self.initialize()
            if not success:
                return {
                    "success": False,
                    "error": "上传器初始化失败",
                    "total_groups": 0,
                    "total_singles": 0,
                    "success_groups": 0,
                    "success_singles": 0,
                    "failed_groups": 0,
                    "failed_singles": 0
                }
        
        try:
            # 提取媒体组和单条消息
            media_groups = batch_data.get("media_groups", [])
            single_messages = batch_data.get("single_messages", [])
            source_channel_id = batch_data.get("source_channel_id")
            
            total_groups = len(media_groups)
            total_singles = len(single_messages)
            
            logger.info(f"开始上传一批数据: {total_groups} 个媒体组, {total_singles} 条单独消息")
            
            # 处理统计
            stats = {
                "total_groups": total_groups,
                "total_singles": total_singles,
                "success_groups": 0,
                "success_singles": 0,
                "failed_groups": 0,
                "failed_singles": 0,
                "start_time": start_time
            }
            
            # 先处理媒体组，因为需要保持消息组的完整性
            for group in media_groups:
                group_id = group.get("media_group_id")
                messages = group.get("messages", [])
                
                if not group_id or not messages:
                    continue
                
                # 检查是否已上传
                if self.history_manager.is_group_uploaded(group_id, self.target_channels[0], source_channel_id):
                    logger.info(f"媒体组 {group_id} 已上传到目标频道，跳过")
                    stats["success_groups"] += 1
                    continue
                
                # 上传到第一个目标频道
                first_channel = self.target_channels[0]
                
                try:
                    result = await self.message_sender.send_media_group(messages, first_channel)
                    
                    if result.get("success"):
                        stats["success_groups"] += 1
                        
                        # 记录上传结果
                        await self.history_manager.record_upload(
                            group_id, 
                            first_channel, 
                            result.get("message_ids", []), 
                            source_channel_id
                        )
                        
                        # 将消息从第一个频道复制到其他频道
                        if len(self.target_channels) > 1 and result.get("message_ids"):
                            first_message_id = result["message_ids"][0]
                            await self._forward_to_other_channels(first_channel, first_message_id, group_id, True, source_channel_id)
                    else:
                        stats["failed_groups"] += 1
                        logger.error(f"上传媒体组 {group_id} 失败: {result.get('error', '未知错误')}")
                
                except Exception as e:
                    stats["failed_groups"] += 1
                    logger.error(f"上传媒体组 {group_id} 时发生错误: {str(e)}")
                
                # 等待一段时间，避免触发限制
                await asyncio.sleep(self.config['wait_time'])
            
            # 处理单条消息
            for message in single_messages:
                message_id = message.get("message_id")
                
                if not message_id:
                    continue
                
                # 检查是否已上传
                if self.history_manager.is_message_uploaded(message_id, self.target_channels[0], source_channel_id):
                    logger.info(f"消息 {message_id} 已上传到目标频道，跳过")
                    stats["success_singles"] += 1
                    continue
                
                # 上传到第一个目标频道
                first_channel = self.target_channels[0]
                
                try:
                    result = await self.message_sender.send_single_message(message, first_channel)
                    
                    if result.get("success"):
                        stats["success_singles"] += 1
                        
                        # 记录上传结果
                        await self.history_manager.record_upload(
                            message_id, 
                            first_channel, 
                            [result.get("message_id")], 
                            source_channel_id
                        )
                        
                        # 将消息从第一个频道复制到其他频道
                        if len(self.target_channels) > 1 and result.get("message_id"):
                            await self._forward_to_other_channels(first_channel, result["message_id"], message_id, False, source_channel_id)
                    else:
                        stats["failed_singles"] += 1
                        logger.error(f"上传消息 {message_id} 失败: {result.get('error', '未知错误')}")
                
                except Exception as e:
                    stats["failed_singles"] += 1
                    logger.error(f"上传消息 {message_id} 时发生错误: {str(e)}")
                
                # 等待一段时间，避免触发限制
                await asyncio.sleep(self.config['wait_time'])
            
            # 计算总体统计
            stats["end_time"] = time.time()
            stats["duration"] = stats["end_time"] - stats["start_time"]
            stats["success_total"] = stats["success_groups"] + stats["success_singles"]
            stats["failed_total"] = stats["failed_groups"] + stats["failed_singles"]
            stats["total_messages"] = stats["total_groups"] + stats["total_singles"]
            
            # 计算成功率
            if stats["total_messages"] > 0:
                stats["success_rate"] = stats["success_total"] / stats["total_messages"] * 100
            else:
                stats["success_rate"] = 0
            
            logger.info(
                f"上传批次完成，总计: {stats['total_messages']} 条，成功: {stats['success_total']} 条 "
                f"({stats['success_rate']:.1f}%)，失败: {stats['failed_total']} 条，"
                f"耗时: {stats['duration']:.1f} 秒"
            )
            
            return stats
                
        except Exception as e:
            logger.error(f"上传批次时发生异常: {str(e)}")
            import traceback
            logger.error(f"异常详情: {traceback.format_exc()}")
            return {
                "success": False,
                "error": str(e),
                "total_groups": total_groups if 'total_groups' in locals() else 0,
                "total_singles": total_singles if 'total_singles' in locals() else 0,
                "success_groups": stats.get("success_groups", 0) if 'stats' in locals() else 0,
                "success_singles": stats.get("success_singles", 0) if 'stats' in locals() else 0,
                "failed_groups": stats.get("failed_groups", 0) if 'stats' in locals() else 0,
                "failed_singles": stats.get("failed_singles", 0) if 'stats' in locals() else 0
            }
    
    async def _forward_to_other_channels(self, source_channel: Union[str, int], 
                                       message_id: int, 
                                        original_id: Union[str, int],
                                        is_media_group: bool = False,
                                        source_channel_id: Optional[Union[str, int]] = None) -> None:
        """
        将消息从第一个频道转发到其他频道
        
        Args:
            source_channel: 源频道ID
            message_id: 消息ID
            original_id: 原始消息ID或媒体组ID
            is_media_group: 是否为媒体组，默认为False
            source_channel_id: 原始来源频道ID（可选）
        """
        # 确保已初始化
        if not self._initialized:
            success = await self.initialize()
            if not success:
                logger.error("上传器初始化失败，转发失败")
                return
        
        other_channels = self.target_channels[1:]
        
        if not other_channels:
            return
        
        if is_media_group:
            logger.info(f"将媒体组 (消息ID: {message_id}) 从频道 {source_channel} 转发到 {len(other_channels)} 个其他频道")
        else:
            logger.info(f"将消息 {message_id} 从频道 {source_channel} 转发到 {len(other_channels)} 个其他频道")
        
        for channel_id in other_channels:
            # 检查是否已转发到该频道
            if self.history_manager.is_message_uploaded(original_id, channel_id, source_channel_id):
                logger.info(f"消息 {original_id} 已转发到频道 {channel_id}，跳过")
                continue
            
            # 根据消息类型使用不同的转发方法
            try:
                if is_media_group:
                    result = await self.message_sender.copy_media_group(source_channel, message_id, channel_id)
                    
                    if result.get("success"):
                        # 记录转发结果
                        await self.history_manager.record_upload(
                            original_id, 
                            channel_id, 
                            result.get("message_ids", []), 
                            source_channel_id
                        )
                        logger.info(f"媒体组转发成功，目标频道: {channel_id}, 共 {len(result.get('message_ids', []))} 条消息")
                    else:
                        logger.error(f"媒体组转发失败，目标频道: {channel_id}, 错误: {result.get('error', '未知错误')}")
                
                else:
                    result = await self.message_sender.copy_message(source_channel, message_id, channel_id)
                    
                    if result.get("success"):
                        # 记录转发结果
                        await self.history_manager.record_upload(
                            original_id, 
                            channel_id, 
                            [result.get("message_id")], 
                            source_channel_id
                        )
                        logger.info(f"消息转发成功，目标频道: {channel_id}, 消息ID: {result.get('message_id')}")
                    else:
                        logger.error(f"消息转发失败，目标频道: {channel_id}, 错误: {result.get('error', '未知错误')}")
            
            except Exception as e:
                logger.error(f"转发消息到频道 {channel_id} 时出错: {str(e)}")
            
            # 转发后等待一小段时间，避免触发限制
            await asyncio.sleep(self.config['wait_time'])
    
    def cleanup_old_records(self, max_age_days: int = 30) -> int:
        """
        清理旧的上传记录
        
        Args:
            max_age_days: 最大保留天数
            
        Returns:
            int: 清理的记录数量
        """
        return self.history_manager.cleanup_old_records(max_age_days)
    
    def cleanup_temp_files(self, max_age_hours: int = 24) -> int:
        """
        清理过期的临时文件
        
        Args:
            max_age_hours: 最大保留小时数
            
        Returns:
            int: 清理的文件数量
        """
        current_time = time.time()
        cleanup_threshold = current_time - (max_age_hours * 3600)
        count = 0
        
        for root, _, files in os.walk(self.config['temp_folder']):
            for file in files:
                # 跳过历史记录文件
                if file == "upload_history.json":
                    continue
                
                # 跳过会话文件
                if file.endswith(".session"):
                    continue
                    
                file_path = os.path.join(root, file)
                # 获取文件修改时间
                try:
                    mod_time = os.path.getmtime(file_path)
                    if mod_time < cleanup_threshold:
                        os.remove(file_path)
                        count += 1
                except Exception as e:
                    logger.error(f"清理文件 {file_path} 时出错: {str(e)}")
        
        logger.info(f"已清理 {count} 个过期临时文件")
        return count 