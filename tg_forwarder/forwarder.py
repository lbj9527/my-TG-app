"""
消息转发模块，负责转发消息到目标频道
"""

import time
import asyncio
from typing import Dict, Any, Optional, List, Union, Tuple
from collections import defaultdict
from pyrogram.types import Message
from pyrogram.errors import FloodWait

from tg_forwarder.utils.logger import get_logger
from tg_forwarder.channel_parser import ChannelParser
from tg_forwarder.media_handler import MediaHandler

logger = get_logger("forwarder")

class MessageForwarder:
    """消息转发类，负责消息转发的主要逻辑"""
    
    def __init__(self, client, config: Dict[str, Any], media_handler: MediaHandler):
        """
        初始化消息转发器
        
        Args:
            client: Telegram客户端实例
            config: 转发配置信息
            media_handler: 媒体处理器实例
        """
        self.client = client
        self.config = config
        self.media_handler = media_handler
        
        self.start_message_id = config.get('start_message_id', 0)
        self.end_message_id = config.get('end_message_id', 0)
        self.hide_author = config.get('hide_author', False)
        self.delay = config.get('delay', 1)
        self.batch_size = config.get('batch_size', 100)
    
    async def forward_message(self, source_message: Message, target_channels: List[Union[str, int]]) -> Dict[str, List[Optional[Message]]]:
        """
        转发单条消息到多个目标频道
        
        Args:
            source_message: 源消息对象
            target_channels: 目标频道ID列表（应该已经是真实的chat ID）
        
        Returns:
            Dict[str, List[Optional[Message]]]: 转发结果，格式为 {target_channel: [forwarded_message, ...]}
        """
        results = defaultdict(list)
        
        for target_id in target_channels:
            logger.info(f"正在转发消息 {source_message.id} 到目标频道 (ID: {target_id})")
            
            # 根据是否隐藏作者选择转发方式
            if self.hide_author:
                # 使用copy_message复制消息而不显示来源
                forwarded = await source_message.copy(target_id)
            else:
                # 直接转发保留原始格式和作者
                forwarded = await source_message.forward(target_id)
            
            if forwarded:
                results[str(target_id)].append(forwarded)
                logger.info(f"成功转发消息 {source_message.id} 到目标频道 (ID: {target_id})")
            
        return results
    
    async def forward_media_group(self, media_group: List[Message], target_channels: List[Union[str, int]]) -> Dict[str, List[Optional[Message]]]:
        """
        转发媒体组到多个目标频道
        
        Args:
            media_group: 媒体组消息列表
            target_channels: 目标频道ID列表（应该已经是真实的chat ID）
        
        Returns:
            Dict[str, List[Optional[Message]]]: 转发结果
        """
        results = defaultdict(list)
        
        for target_id in target_channels:
            logger.info(f"正在转发媒体组 {media_group[0].media_group_id} 到目标频道 (ID: {target_id})")
            
            # 使用copy_media_group直接复制媒体组
            client_to_use = self.get_client_instance()
            
            # 使用copy_media_group方法复制媒体组
            copied = await client_to_use.copy_media_group(
                chat_id=target_id,
                from_chat_id=media_group[0].chat.id,
                message_id=media_group[0].id
            )
            
            results[str(target_id)].extend(copied)
            logger.info(f"成功转发媒体组 {media_group[0].media_group_id} 到目标频道 (ID: {target_id}) (共{len(copied)}条)")
                
        return results
    
    async def process_messages(self, source_channel: Union[str, int], target_channels: List[Union[str, int]], 
                             start_id: Optional[int] = None, end_id: Optional[int] = None) -> Dict[str, Any]:
        """
        处理并转发消息
        
        Args:
            source_channel: 源频道ID或用户名
            target_channels: 目标频道ID或用户名列表
            start_id: 起始消息ID
            end_id: 结束消息ID
        
        Returns:
            Dict[str, Any]: 处理结果统计
        """
        # 设置默认的起始/结束消息ID
        if not end_id or end_id <= 0:
            # 获取最新消息ID
            latest_id = await self.client.get_latest_message_id(source_channel)
            if not latest_id:
                logger.error(f"无法获取源频道的最新消息ID: {source_channel}")
                return {"success": False, "error": "无法获取源频道的最新消息ID"}
            
            end_id = latest_id
            logger.info(f"已获取最新消息ID: {end_id}")
        
        if not start_id or start_id <= 0:
            # 如果没有指定起始ID，使用默认值（最新消息ID - 8）
            start_id = max(1, end_id - 8)
            logger.info(f"未指定起始消息ID，将从ID={start_id}开始")
        
        logger.info(f"开始处理消息: 从 {start_id} 到 {end_id}")
        
        # 检查频道是否存在
        source_entity = await self.client.get_entity(source_channel)
        if not source_entity:
            logger.error(f"源频道不存在或无法访问: {source_channel}")
            return {"success": False, "error": f"源频道不存在或无法访问: {source_channel}"}
        
        # 获取真实的源频道ID
        source_chat_id = source_entity.id
        
        # 检查目标频道是否存在并获取真实ID
        valid_targets = []
        for target in target_channels:
            target_entity = await self.client.get_entity(target)
            if target_entity:
                # 保存真实的chat ID而不是原始标识符
                valid_targets.append(target_entity.id)
                logger.info(f"已找到目标频道: {getattr(target_entity, 'title', target)} (ID: {target_entity.id})")
            else:
                logger.warning(f"目标频道不存在或无法访问: {target}")
        
        if not valid_targets:
            logger.error("没有有效的目标频道")
            return {"success": False, "error": "没有有效的目标频道"}
        
        # 开始批量获取和转发消息
        stats = {
            "total": end_id - start_id + 1,
            "processed": 0,
            "success": 0,
            "failed": 0,
            "media_groups": 0,
            "text_messages": 0,
            "media_messages": 0,
            "skipped": 0,
            "start_time": time.time()
        }
        
        # 获取消息
        messages = await self.client.get_messages_range(
            source_channel, start_id, end_id, self.batch_size
        )
        
        # 先对消息进行分组，将媒体组消息放在一起
        grouped_messages = []
        current_media_group = None
        
        for msg in messages:
            if msg is None:
                stats["skipped"] += 1
                continue
            
            if msg.media_group_id:
                if current_media_group and current_media_group[0].media_group_id == msg.media_group_id:
                    # 添加到当前媒体组
                    current_media_group.append(msg)
                else:
                    # 开始新的媒体组
                    if current_media_group:
                        grouped_messages.append(("media_group", current_media_group))
                    current_media_group = [msg]
            else:
                # 如果有未完成的媒体组，先添加它
                if current_media_group:
                    grouped_messages.append(("media_group", current_media_group))
                    current_media_group = None
                
                # 添加普通消息
                grouped_messages.append(("message", msg))
        
        # 添加最后一个媒体组（如果有）
        if current_media_group:
            grouped_messages.append(("media_group", current_media_group))
        
        # 存储所有转发的消息
        forwarded_messages = defaultdict(list)
        
        # 处理分组后的消息
        for msg_type, msg_data in grouped_messages:
            try:
                if msg_type == "media_group":
                    # 转发媒体组
                    media_group = msg_data
                    result = await self.forward_media_group(media_group, valid_targets)
                    
                    # 将转发结果添加到forwarded_messages
                    for target, messages in result.items():
                        forwarded_messages[target].extend(messages)
                    
                    success = any(bool(msgs) for msgs in result.values())
                    stats["processed"] += len(media_group)
                    if success:
                        stats["success"] += len(media_group)
                        stats["media_groups"] += 1
                    else:
                        stats["failed"] += len(media_group)
                    
                    # 更新媒体消息计数
                    stats["media_messages"] += len(media_group)
                
                else:
                    # 转发单条消息
                    message = msg_data
                    result = await self.forward_message(message, valid_targets)
                    
                    # 将转发结果添加到forwarded_messages
                    for target, messages in result.items():
                        forwarded_messages[target].extend(messages)
                    
                    success = any(bool(msgs) for msgs in result.values())
                    stats["processed"] += 1
                    if success:
                        stats["success"] += 1
                    else:
                        stats["failed"] += 1
                    
                    # 更新消息类型计数
                    if message.media:
                        stats["media_messages"] += 1
                    else:
                        stats["text_messages"] += 1
                
                # 防止处理太快触发限流
                await asyncio.sleep(self.delay)
            
            except Exception as e:
                logger.error(f"处理消息时出错: {str(e)}")
                if msg_type == "media_group":
                    stats["failed"] += len(msg_data)
                    stats["processed"] += len(msg_data)
                else:
                    stats["failed"] += 1
                    stats["processed"] += 1
        
        # 计算总耗时
        stats["end_time"] = time.time()
        stats["duration"] = stats["end_time"] - stats["start_time"]
        stats["success"] = True
        
        # 添加转发消息列表到结果中
        stats["forwarded_messages"] = dict(forwarded_messages)
        
        logger.info(f"消息处理完成: 总数 {stats['total']}, 处理 {stats['processed']}, 成功 {stats['success']}, 失败 {stats['failed']}, 跳过 {stats['skipped']}")
        logger.info(f"耗时: {stats['duration']:.2f}秒")
        
        return stats

    def get_client_instance(self):
        """
        获取有效的客户端实例
        
        Returns:
            有效的Pyrogram客户端实例
        
        Raises:
            ValueError: 如果找不到有效的客户端实例
        """
        # 首先检查self.client.client (常见情况)
        if hasattr(self.client, 'client') and self.client.client is not None:
            return self.client.client
            
        # 如果没有.client属性，检查self.client本身
        if self.client is not None:
            return self.client
            
        # 如果都不可用，抛出错误
        raise ValueError("无法获取有效的客户端实例")