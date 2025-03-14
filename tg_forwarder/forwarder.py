"""
消息转发模块，负责转发消息到目标频道
"""

import time
import asyncio
from typing import Dict, Any, Optional, List, Union, Tuple
from collections import defaultdict
from pyrogram.types import Message
from pyrogram.errors import FloodWait
import re

from tg_forwarder.utils.logger import get_logger
from tg_forwarder.channel_parser import ChannelParser
from tg_forwarder.media_handler import MediaHandler
# 导入公共工具函数
from tg_forwarder.utils.common import get_client_instance

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
        self.skip_emoji_messages = config.get('skip_emoji_messages', False)
    
    def has_emoji(self, text: str) -> bool:
        """
        检测文本是否包含Emoji
        
        Args:
            text: 要检测的文本
        
        Returns:
            bool: 如果包含Emoji返回True，否则返回False
        """
        # Emoji表情的Unicode范围
        emoji_pattern = re.compile(
            "["
            "\U0001F600-\U0001F64F"  # 表情符号
            "\U0001F300-\U0001F5FF"  # 符号和象形文字
            "\U0001F680-\U0001F6FF"  # 交通和地图符号
            "\U0001F700-\U0001F77F"  # 字母符号
            "\U0001F780-\U0001F7FF"  # 几何形状
            "\U0001F800-\U0001F8FF"  # 箭头符号
            "\U0001F900-\U0001F9FF"  # 补充符号和象形文字
            "\U0001FA00-\U0001FA6F"  # 扩展符号
            "\U0001FA70-\U0001FAFF"  # 扩展符号和象形文字
            "\U00002702-\U000027B0"  # 装饰符号
            "\U000024C2-\U0001F251" 
            "]+"
        )
        
        return bool(emoji_pattern.search(text if text else ""))
    
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
        forwards_restricted = False
        
        # 首先检查源频道是否设置了保护内容（禁止转发）
        try:
            source_chat = await self.client.get_entity(source_message.chat.id)
            if hasattr(source_chat, 'has_protected_content') and source_chat.has_protected_content:
                logger.warning(f"频道 {source_message.chat.id} 禁止转发消息 (has_protected_content=True)，将使用备用方式")
                forwards_restricted = True
                results["forwards_restricted"] = True
                return results
        except Exception as e:
            # 如果获取频道信息失败，继续尝试转发（将在转发时捕获错误）
            logger.warning(f"检查频道 {source_message.chat.id} 保护内容状态失败: {str(e)[:100]}")
            
        for target_id in target_channels:
            logger.info(f"正在转发消息 {source_message.id} 到目标频道 (ID: {target_id})")
            
            try:
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
            
            except Exception as e:
                error_msg = str(e)
                if "CHAT_FORWARDS_RESTRICTED" in error_msg:
                    logger.warning(f"频道 {source_message.chat.id} 禁止转发消息，将使用备用方式")
                    forwards_restricted = True
                    # 不在这里处理备用转发，而是由调用者处理
                    break
                elif "FLOOD_WAIT" in error_msg:
                    wait_time = re.search(r"FLOOD_WAIT_(\d+)", error_msg)
                    wait_seconds = wait_time.group(1) if wait_time else "未知"
                    logger.error(f"转发消息 {source_message.id} 时触发频率限制，需等待 {wait_seconds} 秒")
                    results["error_messages"] = results.get("error_messages", []) + [f"消息 {source_message.id}: 触发频率限制，需等待 {wait_seconds} 秒"]
                elif "CHAT_WRITE_FORBIDDEN" in error_msg:
                    logger.error(f"转发消息 {source_message.id} 失败: 无权在目标频道 {target_id} 发送消息")
                    results["error_messages"] = results.get("error_messages", []) + [f"消息 {source_message.id}: 无权在目标频道 {target_id} 发送消息"]
                elif "PEER_ID_INVALID" in error_msg:
                    logger.error(f"转发消息 {source_message.id} 失败: 目标频道 {target_id} ID无效")
                    results["error_messages"] = results.get("error_messages", []) + [f"消息 {source_message.id}: 目标频道 {target_id} ID无效"]
                else:
                    logger.error(f"转发消息 {source_message.id} 时出错: {e}")
                    results["error_messages"] = results.get("error_messages", []) + [f"消息 {source_message.id}: {error_msg[:100]}"]
        
        # 如果频道禁止转发，设置一个标记
        if forwards_restricted:
            results["forwards_restricted"] = True
            
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
        forwards_restricted = False
        
        # 检查媒体组中是否有含Emoji的消息
        if self.skip_emoji_messages:
            for msg in media_group:
                if msg.caption and self.has_emoji(msg.caption):
                    logger.info(f"跳过包含Emoji的媒体组消息: {msg.id} (媒体组ID: {msg.media_group_id})")
                    return results

        # 首先检查源频道是否设置了保护内容（禁止转发）
        try:
            source_chat = await self.client.get_entity(media_group[0].chat.id)
            if hasattr(source_chat, 'has_protected_content') and source_chat.has_protected_content:
                logger.warning(f"频道 {media_group[0].chat.id} 禁止转发消息 (has_protected_content=True)，将使用备用方式")
                forwards_restricted = True
                results["forwards_restricted"] = True
                return results
        except Exception as e:
            # 如果获取频道信息失败，继续尝试转发（将在转发时捕获错误）
            logger.warning(f"检查频道 {media_group[0].chat.id} 保护内容状态失败: {str(e)[:100]}")

        for target_id in target_channels:
            logger.info(f"正在转发媒体组 {media_group[0].media_group_id} 到目标频道 (ID: {target_id})")
            
            try:
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
            
            except Exception as e:
                error_msg = str(e)
                if "CHAT_FORWARDS_RESTRICTED" in error_msg:
                    logger.warning(f"频道 {media_group[0].chat.id} 禁止转发消息，将使用备用方式")
                    forwards_restricted = True
                    # 不在这里处理备用转发，而是由调用者处理
                    break
                elif "FLOOD_WAIT" in error_msg:
                    wait_time = re.search(r"FLOOD_WAIT_(\d+)", error_msg)
                    wait_seconds = wait_time.group(1) if wait_time else "未知"
                    logger.error(f"转发媒体组 {media_group[0].media_group_id} 时触发频率限制，需等待 {wait_seconds} 秒")
                    results["error_messages"] = results.get("error_messages", []) + [f"媒体组 {media_group[0].media_group_id}: 触发频率限制，需等待 {wait_seconds} 秒"]
                elif "CHAT_WRITE_FORBIDDEN" in error_msg:
                    logger.error(f"转发媒体组 {media_group[0].media_group_id} 失败: 无权在目标频道 {target_id} 发送消息")
                    results["error_messages"] = results.get("error_messages", []) + [f"媒体组 {media_group[0].media_group_id}: 无权在目标频道 {target_id} 发送消息"]
                elif "PEER_ID_INVALID" in error_msg:
                    logger.error(f"转发媒体组 {media_group[0].media_group_id} 失败: 目标频道 {target_id} ID无效")
                    results["error_messages"] = results.get("error_messages", []) + [f"媒体组 {media_group[0].media_group_id}: 目标频道 {target_id} ID无效"]
                else:
                    logger.error(f"转发媒体组 {media_group[0].media_group_id} 时出错: {e}")
                    results["error_messages"] = results.get("error_messages", []) + [f"媒体组 {media_group[0].media_group_id}: {error_msg[:100]}"]
        
        # 如果频道禁止转发，设置一个标记
        if forwards_restricted:
            results["forwards_restricted"] = True
            
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
            "skipped_emoji": 0,
            "start_time": time.time(),
            "failed_messages": [],  # 记录转发失败的消息ID
            "forwards_restricted": False,  # 标记源频道是否禁止转发
            "error_messages": []  # 记录错误消息
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
            
            # 检查消息是否包含Emoji并根据配置决定是否跳过
            if self.skip_emoji_messages and msg.text and self.has_emoji(msg.text):
                logger.info(f"跳过包含Emoji的消息: {msg.id}")
                stats["skipped"] += 1
                stats["skipped_emoji"] += 1
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
        # 存储所有源消息，以备后续下载使用
        source_messages = []
        
        # 处理分组后的消息
        for msg_type, msg_data in grouped_messages:
            try:
                if msg_type == "media_group":
                    # 转发媒体组
                    media_group = msg_data
                    result = await self.forward_media_group(media_group, valid_targets)
                    
                    # 检查是否因禁止转发而停止
                    if "forwards_restricted" in result:
                        stats["forwards_restricted"] = True
                        # 保存所有源消息以便后续处理
                        source_messages.extend(media_group)
                        # 记录所有媒体组消息ID为失败
                        for msg in media_group:
                            stats["failed_messages"].append(msg.id)
                        stats["failed"] += len(media_group)
                        stats["processed"] += len(media_group)
                        # 停止继续处理
                        break
                    
                    # 收集错误信息
                    if "error_messages" in result:
                        stats["error_messages"].extend(result["error_messages"])
                    
                    # 将转发结果添加到forwarded_messages
                    for target, messages in result.items():
                        if target != "error_messages" and target != "forwards_restricted":
                            forwarded_messages[target].extend(messages)
                    
                    success = any(bool(msgs) for msgs in result.values())
                    stats["processed"] += len(media_group)
                    if success:
                        stats["success"] += len(media_group)
                        stats["media_groups"] += 1
                    else:
                        stats["failed"] += len(media_group)
                        # 记录转发失败的媒体组消息ID
                        for msg in media_group:
                            stats["failed_messages"].append(msg.id)
                    
                    # 更新媒体消息计数
                    stats["media_messages"] += len(media_group)
                    # 保存源消息便于后续可能的处理
                    source_messages.extend(media_group)
                
                else:
                    # 转发单条消息
                    message = msg_data
                    result = await self.forward_message(message, valid_targets)
                    
                    # 检查是否因禁止转发而停止
                    if "forwards_restricted" in result:
                        stats["forwards_restricted"] = True
                        # 保存所有源消息以便后续处理
                        source_messages.append(message)
                        # 记录消息ID为失败
                        stats["failed_messages"].append(message.id)
                        stats["failed"] += 1
                        stats["processed"] += 1
                        # 停止继续处理
                        break
                    
                    # 收集错误信息
                    if "error_messages" in result:
                        stats["error_messages"].extend(result["error_messages"])
                    
                    # 将转发结果添加到forwarded_messages
                    for target, messages in result.items():
                        if target != "error_messages" and target != "forwards_restricted":
                            forwarded_messages[target].extend(messages)
                    
                    success = any(bool(msgs) for msgs in result.values())
                    stats["processed"] += 1
                    if success:
                        stats["success"] += 1
                    else:
                        stats["failed"] += 1
                        # 记录转发失败的消息ID
                        stats["failed_messages"].append(message.id)
                    
                    # 更新消息类型计数
                    if message.media:
                        stats["media_messages"] += 1
                    else:
                        stats["text_messages"] += 1
                    # 保存源消息便于后续可能的处理
                    source_messages.append(message)
                
                # 防止处理太快触发限流
                await asyncio.sleep(self.delay)
            
            except Exception as e:
                logger.error(f"处理消息时出错: {str(e)}")
                if msg_type == "media_group":
                    stats["failed"] += len(msg_data)
                    stats["processed"] += len(msg_data)
                    # 记录转发失败的媒体组消息ID
                    for msg in msg_data:
                        stats["failed_messages"].append(msg.id)
                    # 保存源消息便于后续可能的处理
                    source_messages.extend(msg_data)
                else:
                    stats["failed"] += 1
                    stats["processed"] += 1
                    # 记录转发失败的消息ID
                    stats["failed_messages"].append(msg_data.id)
                    # 保存源消息便于后续可能的处理
                    source_messages.append(msg_data)
        
        # 计算总耗时
        stats["end_time"] = time.time()
        stats["duration"] = stats["end_time"] - stats["start_time"]
        stats["success"] = True
        
        # 添加转发消息列表到结果中
        stats["forwarded_messages"] = dict(forwarded_messages)
        # 添加源消息列表到结果中
        stats["source_messages"] = source_messages
        
        logger.info(f"消息处理完成: 总数 {stats['total']}, 处理 {stats['processed']}, 成功 {stats['success']}, 失败 {stats['failed']}, 跳过 {stats['skipped']}")
        if stats["skipped_emoji"] > 0:
            logger.info(f"跳过的Emoji消息数: {stats['skipped_emoji']}")
        if stats["failed"] > 0:
            logger.info(f"转发失败的消息ID: {stats['failed_messages']}")
            
            # 输出详细的错误信息
            if stats["error_messages"]:
                logger.warning("转发失败的详细错误信息:")
                for i, error_msg in enumerate(stats["error_messages"], 1):
                    logger.warning(f"  {i}. {error_msg}")
                    
                # 如果错误信息超过5条，统计错误类型
                if len(stats["error_messages"]) > 5:
                    error_types = {}
                    for msg in stats["error_messages"]:
                        # 提取错误类型
                        if "触发频率限制" in msg:
                            error_type = "频率限制"
                        elif "无权在目标频道" in msg:
                            error_type = "权限不足"
                        elif "ID无效" in msg:
                            error_type = "频道ID无效"
                        else:
                            error_type = "其他错误"
                        
                        error_types[error_type] = error_types.get(error_type, 0) + 1
                    
                    # 输出错误类型统计
                    logger.warning("错误类型统计:")
                    for error_type, count in error_types.items():
                        percentage = count / len(stats["error_messages"]) * 100
                        logger.warning(f"  - {error_type}: {count}条 ({percentage:.1f}%)")
        
        if stats["forwards_restricted"]:
            logger.warning(f"源频道 {source_chat_id} 禁止转发消息，需要使用备用方式")
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
        # 使用公共模块中的函数
        return get_client_instance(self.client)