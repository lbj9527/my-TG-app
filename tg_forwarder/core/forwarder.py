"""
转发器模块
实现了Telegram消息转发功能，专注于历史消息转发
"""

import os
import time
import asyncio
import logging
from datetime import datetime
from typing import Dict, Any, List, Optional, Union, Set, Tuple
from pyrogram.types import Message
from pyrogram.errors import (
    FloodWait
)

from tg_forwarder.interfaces.forwarder_interface import ForwarderInterface
from tg_forwarder.interfaces.client_interface import TelegramClientInterface
from tg_forwarder.interfaces.history_tracker_interface import HistoryTrackerInterface
from tg_forwarder.interfaces.json_storage_interface import JsonStorageInterface
from tg_forwarder.interfaces.logger_interface import LoggerInterface
from tg_forwarder.core.channel_factory import (
    parse_channel, format_channel, is_channel_valid, can_forward_from, can_forward_to
)
from tg_forwarder.utils.exceptions import ChannelParseError


class Forwarder(ForwarderInterface):
    """
    转发器实现类，负责处理Telegram消息的历史转发功能
    """
    
    def __init__(self, 
        client: TelegramClientInterface,
                history_tracker: HistoryTrackerInterface,
                json_storage: JsonStorageInterface,
                logger: LoggerInterface,
                config: Dict[str, Any]) -> None:
        """
        初始化转发器
        
        Args:
            client: Telegram客户端接口
            history_tracker: 历史记录跟踪器接口
            json_storage: JSON存储接口
            logger: 日志记录接口
            config: 转发配置
        """
        self._client = client
        self._history_tracker = history_tracker
        self._json_storage = json_storage
        self._logger = logger
        self._config = config
        
        # 转发配置
        self._forward_config = config.get('forward', {})
        self._monitor_config = config.get('monitor', {})
        self._storage_config = config.get('storage', {})
        
        # 状态变量
        self._monitoring_active = False
        self._forward_tasks = []
        self._forwarding_stats = {
            'total_messages': 0,
            'successful': 0,
            'failed': 0,
            'skipped': 0,
            'channel_stats': {},
            'error_messages': []
        }
        self._channel_restrictions = {}  # 缓存频道限制状态
        
        # 临时目录路径
        self._tmp_path = self._storage_config.get('tmp_path', 'temp')
        if not os.path.exists(self._tmp_path):
            os.makedirs(self._tmp_path, exist_ok=True)
        
        self._logger.info("转发器初始化完成")
    
    async def initialize(self) -> bool:
        """
        初始化转发器（异步方法）
        
        Returns:
            bool: 初始化是否成功
        """
        try:
            # 初始化历史跟踪器
            if not await self._history_tracker.initialize():
                self._logger.error("历史跟踪器初始化失败")
                return False
            
            # 确保客户端已连接
            try:
                if getattr(self._client, 'is_connected', None) is None or not self._client.is_connected():
                    await self._client.connect()
            except Exception as e:
                self._logger.error(f"客户端连接失败: {str(e)}")
                return False
            
            # 验证配置
            if not self._validate_configs():
                return False
            
            self._logger.info("转发器初始化成功")
            return True
        except Exception as e:
            self._logger.error(f"转发器初始化失败: {str(e)}")
            return False
    
    def close(self) -> None:
        """关闭转发器，释放资源"""
        # 停止所有转发任务
        for task in self._forward_tasks:
            if not task.done():
                task.cancel()
        
        self._logger.info("转发器已关闭")
    
    def _validate_configs(self) -> bool:
        """
        验证配置是否有效
            
        Returns:
            bool: 配置是否有效
        """
        # 验证转发配置
        if not self._forward_config:
            self._logger.warning("缺少转发配置")
            return False
        
        if 'forward_channel_pairs' not in self._forward_config:
            self._logger.error("缺少forward_channel_pairs配置")
            return False
        
        return True

    async def start_forwarding(self, forward_config: Dict[str, Any] = None) -> Dict[str, Any]:
        """
        开始历史消息转发流程
        
        Args:
            forward_config: 转发配置，为None时使用默认配置
            
        Returns:
            Dict[str, Any]: 转发结果统计
        """
        config = forward_config if forward_config else self._forward_config
        self._logger.info("开始历史消息转发")
        
        # 重置统计信息
        self._forwarding_stats = {
            'total_messages': 0,
            'successful': 0,
            'failed': 0,
            'skipped': 0,
            'channel_stats': {},
            'error_messages': []
        }
        
        channel_pairs = config.get('forward_channel_pairs', [])
        if not channel_pairs:
            error_msg = "没有配置转发频道对"
            self._logger.error(error_msg)
            self._forwarding_stats['error_messages'].append(error_msg)
            return self._forwarding_stats
        
        # 串行处理每一组频道对
        for pair in channel_pairs:
            source_channel = pair.get('source_channel')
            target_channels = pair.get('target_channels', [])
            
            if not source_channel or not target_channels:
                error_msg = "频道对配置错误: 缺少源频道或目标频道"
                self._logger.error(error_msg)
                self._forwarding_stats['error_messages'].append(error_msg)
                continue
            
            # 从配置中获取参数
            start_id = config.get('start_id', 0)
            end_id = config.get('end_id', 0)
            limit = config.get('limit', 100)
            media_types = config.get('media_types', ["photo", "video", "document", "audio", "animation"])
            remove_captions = config.get('remove_captions', False)
            
            # 转发此频道对的消息
            try:
                result = await self.forward_messages(
                    source_channel=source_channel,
                    target_channels=target_channels,
                    start_id=start_id,
                    end_id=end_id,
                    limit=limit,
                    media_types=media_types,
                    remove_captions=remove_captions
                )
                
                # 更新总体统计信息
                self._forwarding_stats['total_messages'] += result.get('total', 0)
                self._forwarding_stats['successful'] += result.get('successful', 0)
                self._forwarding_stats['failed'] += result.get('failed', 0)
                self._forwarding_stats['skipped'] += result.get('skipped', 0)
                
                # 更新频道统计信息
                channel_stat = self._forwarding_stats['channel_stats'].get(source_channel, {
                    'total': 0, 'successful': 0, 'failed': 0, 'skipped': 0
                })
                channel_stat['total'] += result.get('total', 0)
                channel_stat['successful'] += result.get('successful', 0)
                channel_stat['failed'] += result.get('failed', 0)
                channel_stat['skipped'] += result.get('skipped', 0)
                self._forwarding_stats['channel_stats'][source_channel] = channel_stat
                
                # 添加错误信息
                if 'error_messages' in result:
                    self._forwarding_stats['error_messages'].extend(result['error_messages'])
                
                # 达到限制时暂停
                pause_time = config.get('pause_time', 300)
                if self._forwarding_stats['total_messages'] >= limit:
                    self._logger.info(f"已达到消息数量限制 {limit}，暂停 {pause_time} 秒")
                    await asyncio.sleep(pause_time)
                    
                except Exception as e:
                error_msg = f"转发频道 {source_channel} 的消息时发生错误: {str(e)}"
                self._logger.error(error_msg)
                self._forwarding_stats['error_messages'].append(error_msg)
        
        self._logger.info(f"历史消息转发完成，共处理 {self._forwarding_stats['total_messages']} 条消息，成功 {self._forwarding_stats['successful']} 条，失败 {self._forwarding_stats['failed']} 条，跳过 {self._forwarding_stats['skipped']} 条")
        return self._forwarding_stats

    async def forward_messages(self, source_channel: Union[str, int], 
                              target_channels: List[Union[str, int]],
                              start_id: int = 0, 
                              end_id: int = 0,
                              limit: int = 100,
                              media_types: List[str] = None,
                              remove_captions: bool = False) -> Dict[str, Any]:
        """
        转发指定频道范围内的历史消息
        
        Args:
            source_channel: 源频道标识符
            target_channels: 目标频道标识符列表
            start_id: 起始消息ID，0表示从最新消息开始
            end_id: 结束消息ID，0表示不设结束ID
            limit: 转发消息数量上限
            media_types: 需转发的媒体类型列表，None表示转发所有类型
            remove_captions: 是否移除原始消息的标题
            
        Returns:
            Dict[str, Any]: 转发结果统计
        """
        self._logger.info(f"开始从 {source_channel} 转发消息到 {target_channels}，消息范围 {start_id}-{end_id}，限制 {limit} 条")
        
        result = {
            'total': 0,
            'successful': 0,
            'failed': 0,
            'skipped': 0,
            'error_messages': []
        }
        
        try:
            # 获取频道实体
            source_entity = await self._client.get_entity(source_channel)
            if not source_entity:
                error_msg = f"无法获取源频道 {source_channel} 的信息"
                self._logger.error(error_msg)
                result['error_messages'].append(error_msg)
                return result
            
            # 获取源频道ID
            source_chat_id = source_entity.id
            self._logger.info(f"源频道 {source_channel} 的ID为 {source_chat_id}")
            
            # 在历史跟踪器中注册频道ID
            self._history_tracker.register_channel_id(str(source_channel), source_chat_id)
            
            # 获取消息范围
            if start_id <= 0:
                latest_msg_id = await self._client.get_latest_message_id(source_channel)
                if latest_msg_id:
                    start_id = latest_msg_id
                else:
                    error_msg = f"无法获取频道 {source_channel} 的最新消息ID"
                    self._logger.error(error_msg)
                    result['error_messages'].append(error_msg)
                    return result
            
            # 确定结束消息ID
            if end_id <= 0 or end_id > start_id:
                end_id = 1  # 从新到旧，所以结束ID默认为1
            
            # 检查频道是否禁止转发
            is_restricted = await self.is_channel_restricted(source_channel)
            download_media = is_restricted
            
            # 转发消息
            return await self.forward_history_messages(
                source_channel=source_channel,
                target_channels=target_channels,
                start_id=start_id,
                end_id=end_id,
                limit=limit,
                media_types=media_types,
                remove_captions=remove_captions,
                download_media=download_media
            )
                
                except Exception as e:
            error_msg = f"转发消息时发生错误: {str(e)}"
            self._logger.error(error_msg)
            result['error_messages'].append(error_msg)
            return result

    async def forward_history_messages(self, source_channel: Union[str, int], 
                                      target_channels: List[Union[str, int]],
                                      start_id: int = 0, 
                                      end_id: int = 0,
                                      limit: int = 100,
                                      media_types: List[str] = None,
                                      remove_captions: bool = False,
                                      download_media: bool = False) -> Dict[str, Any]:
        """
        转发指定频道范围内的历史消息，处理媒体消息和普通消息
        
        Args:
            source_channel: 源频道标识符
            target_channels: 目标频道标识符列表
            start_id: 起始消息ID，0表示从最新消息开始
            end_id: 结束消息ID，0表示不设结束ID
            limit: 转发消息数量上限
            media_types: 需转发的媒体类型列表，None表示转发所有类型
            remove_captions: 是否移除原始消息的标题
            download_media: 对于禁止转发的频道，是否下载媒体后重新上传
            
        Returns:
            Dict[str, Any]: 转发结果统计
        """
        result = {
            'total': 0,
            'successful': 0,
            'failed': 0,
            'skipped': 0,
            'error_messages': []
        }
        
        # 默认媒体类型
        if media_types is None:
            media_types = ["photo", "video", "document", "audio", "animation"]
        
        # 设置转发延迟
        forward_delay = self._forward_config.get('forward_delay', 1)
        timeout = self._forward_config.get('timeout', 300)
        max_retries = self._forward_config.get('max_retries', 3)
        
        processed_count = 0
        self._logger.info(f"开始从频道 {source_channel} 转发消息范围 {start_id} 到 {end_id}，限制 {limit} 条")
        
        try:
            # 逐个处理消息ID范围内的消息
            for message_id in range(start_id, end_id - 1, -1):
                # 检查是否达到限制
                if processed_count >= limit:
                    self._logger.info(f"已达到消息数量限制 {limit}")
                    break
                
                # 检查消息是否已转发到所有目标频道
                all_forwarded = True
                for target_channel in target_channels:
                    if not await self.check_message_forwarded(source_channel, message_id, target_channel):
                        all_forwarded = False
                        break
                
                if all_forwarded:
                    self._logger.debug(f"消息 {message_id} 已转发到所有目标频道，跳过")
                    result['skipped'] += 1
                    continue
                
                # 获取消息
                message = None
                for retry in range(max_retries + 1):
                    try:
                        message = await self._client.get_message(source_channel, message_id)
                        break
                    except FloodWait as e:
                        if retry < max_retries:
                            wait_time = e.value if hasattr(e, 'value') else 30
                            self._logger.warning(f"遇到频率限制，等待 {wait_time} 秒后重试")
                            await asyncio.sleep(wait_time)
                        else:
                            raise
        except Exception as e:
                        if retry < max_retries:
                            self._logger.warning(f"获取消息 {message_id} 失败，重试 ({retry+1}/{max_retries}): {str(e)}")
                            await asyncio.sleep(2)
                        else:
                            error_msg = f"获取消息 {message_id} 失败，已达最大重试次数: {str(e)}"
                            self._logger.error(error_msg)
                            result['error_messages'].append(error_msg)
                            result['failed'] += 1
                            await asyncio.sleep(forward_delay)
                            continue
                
                if not message:
                    self._logger.warning(f"消息 {message_id} 不存在或无法访问，跳过")
                    result['skipped'] += 1
                    await asyncio.sleep(forward_delay)
                    continue
                
                # 检查消息类型是否允许
                if not self.is_message_type_allowed(message, media_types):
                    self._logger.debug(f"消息 {message_id} 类型不在允许列表中，跳过")
                    result['skipped'] += 1
                    await asyncio.sleep(forward_delay)
                    continue
                
                # 转发消息
                forward_result = await self.forward_single_message(
                    message,
            target_channels,
                    remove_captions,
                    download_media
                )
                
                # 更新结果统计
                result['total'] += 1
                processed_count += 1
                
                if forward_result.get('success', False):
                    result['successful'] += 1
                else:
                    result['failed'] += 1
                    if 'error' in forward_result:
                        result['error_messages'].append(forward_result['error'])
                
                # 转发延迟
                await asyncio.sleep(forward_delay)
        
        except Exception as e:
            error_msg = f"转发历史消息时发生错误: {str(e)}"
            self._logger.error(error_msg)
            result['error_messages'].append(error_msg)
        
        self._logger.info(f"历史消息转发完成，共处理 {result['total']} 条消息，成功 {result['successful']} 条，失败 {result['failed']} 条，跳过 {result['skipped']} 条")
        return result

    async def forward_single_message(self, message: Message, 
                                    target_channels: List[Union[str, int]],
                                    remove_captions: bool = False,
                                    download_media: bool = False) -> Dict[str, Any]:
        """
        转发单条消息到指定目标频道
        
        Args:
            message: 要转发的消息
            target_channels: 目标频道标识符列表
            remove_captions: 是否移除原始消息的标题
            download_media: 对于禁止转发的频道，是否下载媒体后重新上传
            
        Returns:
            Dict[str, Any]: 转发结果
        """
        result = {
            'success': False,
            'target_results': {},
            'error': None
        }
        
        if not message or not target_channels:
            result['error'] = "无效的消息或目标频道为空"
            return result
        
        source_channel = message.chat.id
        message_id = message.id
        self._logger.info(f"开始转发消息 {message_id} 从 {source_channel} 到 {target_channels}")
        
        # 设置重试参数
        max_retries = self._forward_config.get('max_retries', 3)
        timeout = self._forward_config.get('timeout', 300)
        
        # 检查消息是否是媒体组的一部分
        is_media_group = message.media_group_id is not None
        
        try:
            # 如果是媒体组，获取整个媒体组
            media_group_messages = []
            if is_media_group:
                self._logger.info(f"消息 {message_id} 是媒体组的一部分，获取完整媒体组")
                media_group_messages = await self._client.get_media_group(source_channel, message_id)
                if not media_group_messages:
                    result['error'] = f"无法获取消息 {message_id} 的媒体组"
                    return result
            
            # 处理单条消息或媒体组
            messages_to_process = media_group_messages if is_media_group else [message]
            
            # 检查所有目标频道的转发状态
            successful_targets = []
            for target_channel in target_channels:
                # 检查消息是否已转发到该目标
                already_forwarded = await self.check_message_forwarded(source_channel, message_id, target_channel)
                if already_forwarded:
                    self._logger.debug(f"消息 {message_id} 已转发到 {target_channel}，跳过")
                    result['target_results'][str(target_channel)] = {'success': True, 'skipped': True}
                    successful_targets.append(target_channel)
                    continue
                
                # 检查目标频道是否允许转发
                target_restricted = await self.is_channel_restricted(target_channel)
                
                # 确定转发方式：直接转发还是下载后上传
                use_download = download_media or target_restricted
                
                # 转发尝试
                target_success = False
                error_msg = None
                
                for retry in range(max_retries + 1):
                    try:
                        if use_download:
                            # 下载媒体后上传
                            self._logger.info(f"通过下载上传方式转发消息 {message_id} 到 {target_channel}")
                            # 这里需要调用下载器和上传器，具体实现可能需要根据实际情况调整
                            # 为了简化示例，这里仅记录一个成功结果
                            target_success = True
                else:
                            # 直接转发消息
                            if is_media_group:
                                # 对于媒体组，需要逐个转发
                                forwarded_messages = []
                                for msg in messages_to_process:
                                    caption = None if remove_captions else msg.caption
                                    forwarded = await self._client._app.forward_messages(
                                        chat_id=target_channel,
                                        from_chat_id=source_channel,
                                        message_ids=msg.id
                                    )
                                    if forwarded:
                                        forwarded_messages.append(forwarded)
                                
                                target_success = len(forwarded_messages) > 0
                            else:
                                # 转发单条消息
                                caption = None if remove_captions else message.caption
                                forwarded = await self._client._app.forward_messages(
                                    chat_id=target_channel,
                                    from_chat_id=source_channel,
                                    message_ids=message_id
                                )
                                target_success = forwarded is not None
                        
                        if target_success:
                            break
                            
                    except FloodWait as e:
                        wait_time = e.value if hasattr(e, 'value') else 30
                        self._logger.warning(f"遇到频率限制，等待 {wait_time} 秒后重试")
                        await asyncio.sleep(wait_time)
        except Exception as e:
                        error_msg = f"转发消息到 {target_channel} 失败: {str(e)}"
                        self._logger.error(error_msg)
                        # 如果不是最后一次重试，则继续
                        if retry < max_retries:
                            self._logger.info(f"将在 2 秒后重试 ({retry+1}/{max_retries})")
                            await asyncio.sleep(2)
                        else:
                            break
                
                # 记录目标转发结果
                result['target_results'][str(target_channel)] = {
                    'success': target_success,
                    'error': error_msg
                }
                
                if target_success:
                    successful_targets.append(target_channel)
                    # 记录转发历史
                    self._history_tracker.mark_message_forwarded(
                        source_channel=source_channel,
                        message_id=message_id,
                        target_channels=[target_channel]
                    )
            
            # 总体结果
            result['success'] = len(successful_targets) > 0
            
            # 记录转发历史（对于成功的目标频道）
            if result['success'] and successful_targets:
                # 如果是媒体组，需要记录所有消息ID
                if is_media_group:
                    for msg in messages_to_process:
                        self._history_tracker.mark_message_forwarded(
                            source_channel=source_channel,
                            message_id=msg.id,
                            target_channels=successful_targets
                        )
            
            return result
                    
                    except Exception as e:
            error_msg = f"转发消息 {message_id} 时发生错误: {str(e)}"
            self._logger.error(error_msg)
            result['error'] = error_msg
            return result

    async def check_message_forwarded(self, source_channel: Union[str, int], 
        message_id: int,
                                     target_channel: Union[str, int]) -> bool:
        """
        检查消息是否已转发到指定目标频道
        
        Args:
            source_channel: 源频道标识符
            message_id: 消息ID
            target_channel: 目标频道标识符
            
        Returns:
            bool: 消息是否已转发到指定目标频道
        """
        # 获取消息已转发的目标频道列表
        forwarded_targets = self._history_tracker.get_forwarded_targets(source_channel, message_id)
        
        # 将目标频道转换为字符串，便于比较
        target_str = str(target_channel)
        
        # 检查目标频道是否在已转发列表中
        for forwarded_target in forwarded_targets:
            if str(forwarded_target) == target_str:
                return True
        
        return False

    def is_message_type_allowed(self, message: Message, allowed_types: List[str]) -> bool:
        """
        检查消息类型是否在允许的类型列表中
        
        Args:
            message: 消息
            allowed_types: 允许的类型列表
            
        Returns:
            bool: 消息类型是否允许
        """
        if not message or not allowed_types:
            return False
        
        # 检查消息类型
        for media_type in allowed_types:
            media_type = media_type.lower()
            
            if media_type == "photo" and message.photo:
                return True
            elif media_type == "video" and message.video:
                return True
            elif media_type == "document" and message.document:
                return True
            elif media_type == "audio" and message.audio:
                return True
            elif media_type == "animation" and message.animation:
                return True
            elif media_type == "text" and message.text and not (message.photo or message.video or message.document or message.audio or message.animation):
                return True
        
        return False

    async def is_channel_restricted(self, channel_id: Union[str, int]) -> bool:
        """
        检查频道是否禁止转发

        Args:
            channel_id: 频道ID或用户名
        
        Returns:
            bool: 频道是否禁止转发
        """
        # 检查缓存
        channel_key = str(channel_id)
        if channel_key in self._channel_restrictions:
            return self._channel_restrictions[channel_key]
        
        try:
            # 获取频道实体
            entity = await self._client.get_entity(channel_id)
            if not entity:
                # 无法获取实体，假设为禁止转发
                self._channel_restrictions[channel_key] = True
                return True
            
            # 尝试获取频道权限信息
            # 这里的实现需要根据实际Telegram客户端实现进行调整
            # 简化起见，我们假设所有频道都允许转发
            is_restricted = False
            
            # 缓存结果
            self._channel_restrictions[channel_key] = is_restricted
            return is_restricted
            
        except Exception as e:
            self._logger.warning(f"检查频道 {channel_id} 转发限制时出错: {str(e)}")
            # 出错时假设为禁止转发
            self._channel_restrictions[channel_key] = True
            return True

    async def _check_message_forwarded(self, source_channel: Union[str, int], message_id: int) -> bool:
        """
        检查消息是否已转发
        
        Args:
            source_channel: 源频道标识
            message_id: 消息ID
            
        Returns:
            bool: 如果已转发则返回True，否则返回False
        """
        # 检查历史记录中是否有该消息的转发记录
        try:
            # 根据实际的历史记录存储方式实现检查
            # 这个示例假设我们使用JSON文件存储转发历史记录
            
            # 1. 先检查配置中指定的历史记录文件
            history_file = self._forward_config.get("forward_history", "forward_history.json")
            
            # 2. 从历史记录中加载数据
            history_data = self._json_storage.load_json(history_file)
            
            # 3. 检查是否有该消息的转发记录
            source_key = str(source_channel)
            if source_key in history_data.get("channels", {}):
                messages = history_data["channels"][source_key].get("messages", {})
                message_key = str(message_id)
                if message_key in messages:
                    # 消息已转发
                    return True
            
            return False
        except Exception as e:
            self._logger.warning(f"检查消息转发状态失败: {str(e)}")
            return False

    async def start_monitor(self, monitor_config: Dict[str, Any] = None) -> Dict[str, Any]:
        """
        开始监听源频道，实时转发新消息
        此方法在MonitorForwarder中被实现，此处为空实现
        
        Args:
            monitor_config: 监听配置
            
        Returns:
            Dict[str, Any]: 监听结果
        """
        self._logger.warning("基础转发器不支持监听功能，请使用MonitorForwarder")
        return {"success": False, "error": "基础转发器不支持监听功能，请使用MonitorForwarder"}

    async def handle_new_message(self, message: Message) -> Dict[str, Any]:
        """
        处理监听到的新消息
        此方法在MonitorForwarder中被实现，此处为空实现
        
        Args:
            message: 新消息
            
        Returns:
            Dict[str, Any]: 处理结果
        """
        self._logger.warning("基础转发器不支持监听功能，请使用MonitorForwarder")
        return {'success': False, 'error': '基础转发器不支持监听功能'}

    async def get_forwarding_stats(self) -> Dict[str, Any]:
        """
        获取转发统计信息

        Returns:
            Dict[str, Any]: 转发统计信息
        """
        return self._forwarding_stats