"""
转发器实现类
负责消息转发逻辑处理
"""

import os
import asyncio
from typing import List, Dict, Any, Optional, Union, Tuple
from datetime import datetime

from tg_forwarder.interfaces.forwarder_interface import ForwarderInterface
from tg_forwarder.interfaces.client_interface import TelegramClientInterface
from tg_forwarder.interfaces.downloader_interface import DownloaderInterface
from tg_forwarder.interfaces.uploader_interface import UploaderInterface
from tg_forwarder.interfaces.status_tracker_interface import StatusTrackerInterface
from tg_forwarder.interfaces.logger_interface import LoggerInterface
from tg_forwarder.interfaces.config_interface import ConfigInterface
from tg_forwarder.core.channel_factory import (
    parse_channel, format_channel, is_channel_valid, can_forward_from, can_forward_to
)
from tg_forwarder.utils.exceptions import ChannelParseError


class Forwarder(ForwarderInterface):
    """
    转发器，实现ForwarderInterface接口
    负责处理从源频道到目标频道的消息转发
    """
    
    def __init__(
        self,
        client: TelegramClientInterface,
        downloader: DownloaderInterface,
        uploader: UploaderInterface,
        status_tracker: StatusTrackerInterface,
        config: ConfigInterface,
        logger: LoggerInterface
    ):
        """
        初始化转发器
        
        Args:
            client: Telegram客户端接口实例
            downloader: 下载器接口实例
            uploader: 上传器接口实例
            status_tracker: 状态追踪器接口实例
            config: 配置接口实例
            logger: 日志接口实例
        """
        self._client = client
        self._downloader = downloader
        self._uploader = uploader
        self._status_tracker = status_tracker
        self._config = config
        self._logger = logger.get_logger("Forwarder")
        
        self._initialized = False
        self._running = False
        self._tasks = {}  # 存储任务对象(asyncio.Task)和任务信息的字典
        self._scheduled_tasks = {}  # 计划任务信息
        self._forward_config = {}  # 当前的转发配置
        self._source_channels = []  # 当前监听的源频道
        self._target_channels = []  # 当前的目标频道
        self._forward_interval = 60  # 默认转发检查间隔（秒）
        self._forward_task = None  # 转发任务
        
        # 监听相关成员变量
        self._monitor_running = False  # 监听服务是否在运行
        self._monitor_config = {}  # 监听配置
        self._monitor_start_time = None  # 监听开始时间
        self._monitor_end_time = None  # 监听结束时间
        self._monitor_id = None  # 监听任务ID
        self._monitor_source_channels = []  # 监听的源频道
        self._monitor_forwarded_count = 0  # 已转发消息数量
        self._monitor_errors = {}  # 错误统计
    
    async def initialize(self) -> bool:
        """
        初始化转发器
        
        Returns:
            bool: 初始化是否成功
        """
        try:
            self._logger.info("正在初始化转发器...")
            
            # 确保下载器和上传器已初始化
            if not self._downloader.is_initialized():
                await self._downloader.initialize()
            
            if not self._uploader.is_initialized():
                await self._uploader.initialize()
            
            # 确保状态追踪器已初始化
            if not self._status_tracker.is_initialized():
                await self._status_tracker.initialize()
            
            self._initialized = True
            self._logger.info("转发器初始化完成")
            return True
        except Exception as e:
            self._logger.error(f"初始化转发器失败: {str(e)}", exc_info=True)
            self._initialized = False
            return False
    
    def is_initialized(self) -> bool:
        """
        检查转发器是否已初始化
        
        Returns:
            bool: 是否已初始化
        """
        return self._initialized
    
    async def shutdown(self) -> None:
        """关闭转发器，释放资源"""
        if not self._initialized:
            return
        
        self._logger.info("正在关闭转发器...")
        
        # 停止所有正在进行的转发任务
        if self._running:
            await self.stop_forwarding()
        
        self._initialized = False
        self._logger.info("转发器已关闭")
    
    async def forward_message(
        self, 
        source_channel: Union[str, int], 
        message_id: int,
        target_channels: List[Union[str, int]] = None
    ) -> Dict[str, Any]:
        """
        转发单条消息
        
        Args:
            source_channel: 源频道标识
            message_id: 消息ID
            target_channels: 目标频道列表，为None时使用配置的默认目标
            
        Returns:
            Dict[str, Any]: 转发结果，包含成功和失败的目标频道信息
        """
        if not self._initialized:
            return {"success": False, "error": "转发器未初始化"}
        
        try:
            self._logger.info(f"正在转发消息: {source_channel} -> {target_channels}, 消息ID: {message_id}")
            
            # 如果没有指定目标频道，获取默认目标
            if target_channels is None:
                target_channels = self._get_default_target_channels()
                
            if not target_channels:
                return {"success": False, "error": "未指定目标频道且无默认目标频道"}
            
            results = {"success": True, "targets": {}, "source_channel": source_channel, "message_id": message_id}
            
            for target in target_channels:
                try:
                    # 获取配置中此目标的转发配置
                    config = self._get_forward_config(source_channel, target)
                    caption_template = config.get("caption_template")
                    remove_captions = config.get("remove_captions", False)
                    download_media = config.get("download_media", True)
                    
                    # 执行转发
                    result = await self._forward_single_message(
                        source_channel, 
                        target, 
                        message_id,
                        caption_template,
                        remove_captions,
                        download_media
                    )
                    
                    results["targets"][target] = result
                    
                    if not result["success"]:
                        self._logger.warning(f"转发到 {target} 失败: {result.get('error')}")
                        results["success"] = False
                    
                except Exception as e:
                    self._logger.error(f"转发到 {target} 时出错: {str(e)}", exc_info=True)
                    results["targets"][target] = {"success": False, "error": str(e)}
                    results["success"] = False
            
            return results
        
        except Exception as e:
            self._logger.error(f"转发消息失败: {str(e)}", exc_info=True)
            return {"success": False, "error": str(e)}
    
    async def forward_media_group(
        self, 
        source_channel: Union[str, int],
        message_id: int,
        target_channels: List[Union[str, int]] = None
    ) -> Dict[str, Any]:
        """
        转发媒体组
        
        Args:
            source_channel: 源频道标识
            message_id: 媒体组中任一消息ID
            target_channels: 目标频道列表，为None时使用配置的默认目标
            
        Returns:
            Dict[str, Any]: 转发结果，包含成功和失败的目标频道信息
        """
        if not self._initialized:
            return {"success": False, "error": "转发器未初始化"}
        
        try:
            self._logger.info(f"正在转发媒体组: {source_channel}, 消息ID: {message_id}")
            
            # 如果没有指定目标频道，获取默认目标
            if target_channels is None:
                target_channels = self._get_default_target_channels()
                
            if not target_channels:
                return {"success": False, "error": "未指定目标频道且无默认目标频道"}
            
            # 获取媒体组中的所有消息
            media_group = await self._client.get_media_group(source_channel, message_id)
            if not media_group:
                return {"success": False, "error": "获取媒体组失败或该消息不属于媒体组"}
            
            # 按消息ID排序媒体组中的消息
            media_group.sort(key=lambda msg: msg.id)
            media_ids = [msg.id for msg in media_group]
            
            self._logger.info(f"找到媒体组，共 {len(media_ids)} 条消息: {media_ids}（已按ID排序）")
            
            results = {
                "success": True, 
                "targets": {}, 
                "source_channel": source_channel, 
                "media_group_ids": media_ids,
                "media_group_id": media_group[0].media_group_id if media_group else None
            }
            
            for target in target_channels:
                try:
                    # 获取配置中此目标的转发配置
                    config = self._get_forward_config(source_channel, target)
                    caption_template = config.get("caption_template")
                    remove_captions = config.get("remove_captions", False)
                    download_media = config.get("download_media", True)
                    delay = config.get("delay", 0.5)
                    
                    # 对于媒体组，我们需要确保下载再上传，以保持组关系
                    target_results = []
                    
                    for msg_id in media_ids:
                        result = await self._forward_single_message(
                            source_channel, 
                            target, 
                            msg_id,
                            caption_template,
                            remove_captions,
                            download_media=True  # 强制下载媒体以保持组关系
                        )
                        target_results.append(result)
                        
                        if not result["success"]:
                            self._logger.warning(f"转发媒体组消息 {msg_id} 到 {target} 失败: {result.get('error')}")
                        
                        # 短暂延迟，避免API限制
                        await asyncio.sleep(delay)
                    
                    # 计算整个媒体组的转发成功率
                    success_count = sum(1 for r in target_results if r["success"])
                    
                    results["targets"][target] = {
                        "success": success_count > 0,
                        "total": len(media_ids),
                        "succeeded": success_count,
                        "failed": len(media_ids) - success_count,
                        "results": target_results
                    }
                    
                    if success_count == 0:
                        results["success"] = False
                    
                except Exception as e:
                    self._logger.error(f"转发媒体组到 {target} 时出错: {str(e)}", exc_info=True)
                    results["targets"][target] = {"success": False, "error": str(e)}
                    results["success"] = False
            
            return results
        
        except Exception as e:
            self._logger.error(f"转发媒体组失败: {str(e)}", exc_info=True)
            return {"success": False, "error": str(e)}
    
    async def forward_range(
        self, 
        source_channel: Union[str, int],
        start_id: int,
        end_id: int,
        target_channels: List[Union[str, int]] = None
    ) -> Dict[str, Any]:
        """
        转发一个范围内的消息
        
        Args:
            source_channel: 源频道标识
            start_id: 起始消息ID
            end_id: 结束消息ID
            target_channels: 目标频道列表，为None时使用配置的默认目标
            
        Returns:
            Dict[str, Any]: 转发结果统计
        """
        if not self._initialized:
            return {"success": False, "error": "转发器未初始化"}
        
        # 确保start_id <= end_id
        if start_id > end_id:
            start_id, end_id = end_id, start_id
        
        try:
            self._logger.info(f"正在转发消息范围: {source_channel}, ID: {start_id} - {end_id}")
            
            # 如果没有指定目标频道，获取默认目标
            if target_channels is None:
                target_channels = self._get_default_target_channels()
                
            if not target_channels:
                return {"success": False, "error": "未指定目标频道且无默认目标频道"}
            
            # 获取消息列表
            total_messages = end_id - start_id + 1
            
            messages = await self._client.get_messages_range(
                source_channel, 
                start_id, 
                end_id
            )
            
            if not messages:
                return {"success": False, "error": "指定范围内没有有效消息"}
            
            # 按媒体组分类消息
            message_groups = {}
            single_messages = []
            
            # 1. 收集并整理媒体组
            for msg in messages:
                if msg is None:
                    continue
                    
                if msg.media_group_id:
                    if msg.media_group_id not in message_groups:
                        message_groups[msg.media_group_id] = []
                    message_groups[msg.media_group_id].append(msg)
                else:
                    single_messages.append(msg)
            
            valid_message_ids = [msg.id for msg in single_messages]
            valid_message_ids.extend([msg.id for group in message_groups.values() for msg in group])
            
            self._logger.info(f"在范围 {start_id}-{end_id} 中找到 {len(valid_message_ids)}/{total_messages} 条有效消息")
            self._logger.info(f"其中包含 {len(message_groups)} 个媒体组和 {len(single_messages)} 条单独消息")
            
            if not valid_message_ids:
                return {"success": False, "error": "指定范围内没有有效消息"}
            
            results = {
                "success": True, 
                "source_channel": source_channel, 
                "range": {"start": start_id, "end": end_id},
                "total_messages": total_messages,
                "valid_messages": len(valid_message_ids),
                "targets": {}
            }
            
            # 初始化每个目标的结果
            for target in target_channels:
                results["targets"][target] = {
                    "success": True,
                    "total": len(valid_message_ids),
                    "succeeded": 0,
                    "failed": 0,
                    "results": []
                }
            
            # 2. 按媒体组ID排序（确保媒体组有序处理）
            sorted_media_groups = sorted(message_groups.keys())
            
            for target in target_channels:
                try:
                    # 获取配置中此目标的转发配置
                    config = self._get_forward_config(source_channel, target)
                    caption_template = config.get("caption_template")
                    remove_captions = config.get("remove_captions", False)
                    download_media = config.get("download_media", True)
                    delay = config.get("delay", 1.0)
                    
                    target_results = []
                    failed_count = 0
                    
                    # 3. 首先转发所有单独消息
                    for msg in single_messages:
                        result = await self._forward_single_message(
                            source_channel, 
                            target, 
                            msg.id,
                            caption_template,
                            remove_captions,
                            download_media
                        )
                        
                        target_results.append(result)
                        
                        if not result["success"]:
                            failed_count += 1
                            self._logger.warning(f"转发消息 {msg.id} 到 {target} 失败: {result.get('error')}")
                        else:
                            results["targets"][target]["succeeded"] += 1
                        
                        # 添加延迟以避免API限制
                        await asyncio.sleep(delay)
                    
                    # 4. 然后按顺序处理每个媒体组（确保媒体组整体转发）
                    for group_id in sorted_media_groups:
                        group_messages = message_groups[group_id]
                        
                        # 确保媒体组内消息按ID排序
                        group_messages.sort(key=lambda msg: msg.id)
                        
                        # 整体转发媒体组
                        for msg in group_messages:
                            result = await self._forward_single_message(
                                source_channel, 
                                target, 
                                msg.id,
                                caption_template,
                                remove_captions,
                                download_media
                            )
                            
                            target_results.append(result)
                            
                            if not result["success"]:
                                failed_count += 1
                                self._logger.warning(f"转发媒体组消息 {msg.id} (组ID: {group_id}) 到 {target} 失败: {result.get('error')}")
                            else:
                                results["targets"][target]["succeeded"] += 1
                            
                            # 媒体组内消息间添加短暂延迟
                            await asyncio.sleep(max(0.5, delay / 2))
                        
                        # 媒体组之间添加完整延迟，确保媒体组间串行处理
                        await asyncio.sleep(delay)
                    
                    results["targets"][target]["failed"] = failed_count
                    results["targets"][target]["results"] = target_results
                    
                    if failed_count == len(valid_message_ids):
                        results["targets"][target]["success"] = False
                        results["success"] = False
                
                except Exception as e:
                    self._logger.error(f"转发范围到 {target} 时出错: {str(e)}", exc_info=True)
                    results["targets"][target] = {"success": False, "error": str(e)}
                    results["success"] = False
            
            return results
        
        except Exception as e:
            self._logger.error(f"转发消息范围失败: {str(e)}", exc_info=True)
            return {"success": False, "error": str(e)}
    
    async def forward_date_range(
        self, 
        source_channel: Union[str, int],
        start_date: datetime,
        end_date: datetime,
        target_channels: List[Union[str, int]] = None
    ) -> Dict[str, Any]:
        """
        转发指定日期范围内的消息
        
        Args:
            source_channel: 源频道标识
            start_date: 起始日期
            end_date: 结束日期
            target_channels: 目标频道列表，为None时使用配置的默认目标
            
        Returns:
            Dict[str, Any]: 转发结果统计
        """
        if not self._initialized:
            return {"success": False, "error": "转发器未初始化"}
        
        try:
            self._logger.info(
                f"正在转发日期范围内的消息: {source_channel}, "
                f"日期: {start_date.strftime('%Y-%m-%d')} - {end_date.strftime('%Y-%m-%d')}"
            )
            
            # 如果没有指定目标频道，获取默认目标
            if target_channels is None:
                target_channels = self._get_default_target_channels()
                
            if not target_channels:
                return {"success": False, "error": "未指定目标频道且无默认目标频道"}
            
            # 获取指定日期范围内的消息
            # 这需要实现一个方法来获取特定日期范围的消息
            messages = await self._get_messages_by_date_range(source_channel, start_date, end_date)
            
            if not messages:
                return {
                    "success": False, 
                    "error": "指定日期范围内没有消息",
                    "source_channel": source_channel,
                    "date_range": {
                        "start": start_date.isoformat(),
                        "end": end_date.isoformat()
                    }
                }
            
            valid_message_ids = [msg.id for msg in messages]
            
            self._logger.info(f"在日期范围内找到 {len(valid_message_ids)} 条消息")
            
            # 调用forward_range转发这些消息
            return await self.forward_range(
                source_channel,
                min(valid_message_ids),
                max(valid_message_ids),
                target_channels
            )
        
        except Exception as e:
            self._logger.error(f"转发日期范围内的消息失败: {str(e)}", exc_info=True)
            return {"success": False, "error": str(e)}
    
    async def schedule_forward(
        self, 
        source_channel: Union[str, int],
        message_id: Union[int, Tuple[int, int]],
        schedule_time: datetime,
        target_channels: List[Union[str, int]] = None
    ) -> str:
        """
        调度消息转发任务
        
        Args:
            source_channel: 源频道标识
            message_id: 消息ID或范围(起始ID, 结束ID)
            schedule_time: 调度时间
            target_channels: 目标频道列表，为None时使用配置的默认目标
            
        Returns:
            str: 任务ID
        """
        if not self._initialized:
            raise Exception("转发器未初始化")
        
        # 如果没有指定目标频道，获取默认目标
        if target_channels is None:
            target_channels = self._get_default_target_channels()
            
        if not target_channels:
            raise Exception("未指定目标频道且无默认目标频道")
        
        # 计算延迟秒数
        delay_seconds = (schedule_time - datetime.now()).total_seconds()
        if delay_seconds < 0:
            raise Exception("调度时间不能早于当前时间")
        
        # 使用uuid生成唯一任务ID
        import uuid
        task_id = str(uuid.uuid4())
        
        # 创建异步延迟任务
        async def delayed_task():
            # 等待直到计划时间
            await asyncio.sleep(delay_seconds)
            # 执行转发任务
            return await self._scheduled_forward_task(source_channel, message_id, target_channels)
        
        # 创建异步任务
        task = asyncio.create_task(delayed_task())
        
        # 记录任务信息
        self._tasks[task_id] = task
        
        # 记录调度信息
        self._scheduled_tasks[task_id] = {
            "source_channel": source_channel,
            "message_id": message_id,
            "target_channels": target_channels,
            "schedule_time": schedule_time.isoformat(),
            "created_at": datetime.now().isoformat(),
            "status": "scheduled"
        }
        
        self._logger.info(
            f"已调度转发任务: ID={task_id}, 源={source_channel}, "
            f"消息ID={message_id}, 时间={schedule_time.isoformat()}"
        )
        
        return task_id
    
    async def cancel_scheduled_forward(self, task_id: str) -> bool:
        """
        取消调度的转发任务
        
        Args:
            task_id: 任务ID
            
        Returns:
            bool: 取消是否成功
        """
        if not self._initialized:
            return False
        
        if task_id not in self._scheduled_tasks:
            self._logger.warning(f"无法取消转发任务: 找不到任务 {task_id}")
            return False
        
        # 尝试取消任务
        if task_id in self._tasks and isinstance(self._tasks[task_id], asyncio.Task):
            task = self._tasks[task_id]
            if not task.done():
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass
            
            # 更新任务状态
            self._scheduled_tasks[task_id]["status"] = "cancelled"
            # 从任务列表中移除
            self._tasks.pop(task_id, None)
            
            self._logger.info(f"已取消计划转发任务: {task_id}")
            return True
        else:
            self._logger.warning(f"无法取消计划转发任务: {task_id}")
            return False
    
    async def get_forward_status(self, task_id: str) -> Dict[str, Any]:
        """
        获取转发任务状态
        
        Args:
            task_id: 任务ID
            
        Returns:
            Dict[str, Any]: 任务状态信息
        """
        if not self._initialized:
            return {"error": "转发器未初始化"}
        
        # 检查是否是调度任务
        if task_id in self._scheduled_tasks:
            scheduled_info = self._scheduled_tasks[task_id]
            
            # 检查任务是否在运行中
            task_status = "unknown"
            if task_id in self._tasks:
                task = self._tasks[task_id]
                if isinstance(task, asyncio.Task):
                    if task.done():
                        if task.cancelled():
                            task_status = "cancelled"
                        elif task.exception() is not None:
                            task_status = "failed"
                        else:
                            task_status = "completed"
                    else:
                        task_status = "running"
            
            return {
                **scheduled_info,
                "task_type": "scheduled",
                "task_status": task_status
            }
        
        # 检查是否是常规转发任务
        if task_id in self._tasks:
            task = self._tasks[task_id]
            task_status = "unknown"
            
            if isinstance(task, asyncio.Task):
                if task.done():
                    if task.cancelled():
                        task_status = "cancelled"
                    elif task.exception() is not None:
                        task_status = "failed"
                    else:
                        task_status = "completed"
                else:
                    task_status = "running"
            
            return {
                "task_id": task_id,
                "task_type": "forward",
                "task_status": task_status,
                "created_at": datetime.now().isoformat()
            }
        
        # 未找到任务
        return {
            "error": f"找不到任务: {task_id}",
            "task_id": task_id,
            "task_type": "unknown",
            "task_status": "not_found"
        }
    
    async def get_forward_statistics(
        self, 
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None
    ) -> Dict[str, Any]:
        """
        获取转发统计信息
        
        Args:
            start_date: 开始日期，为None表示不限制
            end_date: 结束日期，为None表示不限制
            
        Returns:
            Dict[str, Any]: 统计信息
        """
        if not self._initialized:
            return {"error": "转发器未初始化"}
        
        # 从状态追踪器获取统计信息
        statistics = await self._status_tracker.get_statistics(
            start_date.isoformat() if start_date else None,
            end_date.isoformat() if end_date else None
        )
        
        # 增加一些额外的统计信息
        active_tasks = len([t for t in self._tasks.values() if t.get("status") == "running"])
        scheduled_tasks = len([t for t in self._scheduled_tasks.values() if t.get("status") == "scheduled"])
        
        return {
            "period": {
                "start": start_date.isoformat() if start_date else "all_time",
                "end": end_date.isoformat() if end_date else "present"
            },
            "active_tasks": active_tasks,
            "scheduled_tasks": scheduled_tasks,
            "forward_statistics": statistics
        }
    
    async def retry_failed_forward(self, task_id: str = None) -> Dict[str, Any]:
        """
        重试失败的转发任务
        
        Args:
            task_id: 任务ID，为None时重试所有失败任务
            
        Returns:
            Dict[str, Any]: 重试结果
        """
        if not self._initialized:
            return {"success": False, "error": "转发器未初始化"}
        
        try:
            if task_id:
                # 重试特定任务
                task_status = await self.get_forward_status(task_id)
                if "error" in task_status:
                    return {"success": False, "error": task_status["error"]}
                
                if task_status.get("task_status") != "failed":
                    return {"success": False, "error": f"任务 {task_id} 未失败，无需重试"}
                
                # 提取任务信息并重新提交
                source_channel = task_status.get("source_chat") or task_status.get("source_channel")
                if not source_channel:
                    return {"success": False, "error": f"无法获取任务 {task_id} 的源频道信息"}
                
                # 重新提交任务（具体逻辑取决于任务类型）
                if task_status.get("task_type") == "scheduled":
                    # 重新调度任务
                    new_task_id = await self.schedule_forward(
                        source_channel,
                        task_status.get("message_id"),
                        datetime.fromisoformat(task_status.get("schedule_time")),
                        task_status.get("target_channels")
                    )
                    return {"success": True, "original_task_id": task_id, "new_task_id": new_task_id}
                else:
                    # 根据任务信息重新转发
                    if isinstance(task_status.get("message_id"), tuple) or isinstance(task_status.get("range"), dict):
                        # 范围转发
                        range_info = task_status.get("range", {})
                        start_id = range_info.get("start") if range_info else None
                        end_id = range_info.get("end") if range_info else None
                        
                        if start_id is None or end_id is None:
                            msg_id = task_status.get("message_id")
                            if isinstance(msg_id, tuple) and len(msg_id) == 2:
                                start_id, end_id = msg_id
                        
                        if start_id is not None and end_id is not None:
                            result = await self.forward_range(
                                source_channel,
                                start_id,
                                end_id,
                                task_status.get("target_chat") or task_status.get("target_channels")
                            )
                            result["original_task_id"] = task_id
                            return result
                    
                    # 单条消息转发
                    msg_id = task_status.get("message_id")
                    if isinstance(msg_id, int):
                        result = await self.forward_message(
                            source_channel,
                            msg_id,
                            task_status.get("target_chat") or task_status.get("target_channels")
                        )
                        result["original_task_id"] = task_id
                        return result
                    
                    return {"success": False, "error": f"无法确定任务 {task_id} 的转发类型"}
            else:
                # 重试所有失败任务
                failed_tasks = await self._status_tracker.get_failed_tasks()
                
                retry_results = []
                for failed_task in failed_tasks:
                    retry_result = await self.retry_failed_forward(failed_task["task_id"])
                    retry_results.append(retry_result)
                
                success_count = sum(1 for r in retry_results if r.get("success", False))
                
                return {
                    "success": success_count > 0,
                    "total_failed": len(failed_tasks),
                    "retried": len(retry_results),
                    "succeeded": success_count,
                    "failed": len(retry_results) - success_count,
                    "results": retry_results
                }
        
        except Exception as e:
            self._logger.error(f"重试失败任务时出错: {str(e)}", exc_info=True)
            return {"success": False, "error": str(e)}

    async def start_forwarding(
        self,
        forward_config: Dict[str, Any] = None,
        monitor_mode: bool = False
    ) -> Dict[str, Any]:
        """
        启动转发服务
        
        Args:
            forward_config: 转发配置，为None时使用默认配置
            monitor_mode: 是否为监听模式，为True时使用monitor配置
            
        Returns:
            Dict[str, Any]: 启动结果
        """
        if not self._initialized:
            await self.initialize()
        
        # 如果没有提供配置，使用默认配置
        if forward_config is None:
            if monitor_mode:
                forward_config = self._config.get_monitor_config()
            else:
                forward_config = self._config.get_forward_config()
        
        self._logger.info(f"启动转发服务，配置: {forward_config}, 监听模式: {monitor_mode}")
        
        try:
            # 提取配置参数
            channel_pairs = forward_config.get("channel_pairs", {})
            if not channel_pairs:
                return {"success": False, "error": "未提供有效的频道对配置"}
            
            # 提取源频道和目标频道
            source_channels = list(channel_pairs.keys())
            # 对于目标频道，使用第一个源频道的目标频道作为默认值
            default_targets = channel_pairs.get(source_channels[0], []) if source_channels else []
            target_channels = []
            
            # 验证源频道
            valid_source_channels = []
            for source in source_channels:
                try:
                    # 使用新的频道解析功能解析频道标识符
                    channel_id, _ = parse_channel(source)
                    valid, reason = await is_channel_valid(source)
                    
                    if valid:
                        # 检查转发权限
                        can_forward, reason = await can_forward_from(source)
                        if can_forward:
                            valid_source_channels.append(source)
                            self._logger.info(f"源频道 {format_channel(channel_id)} 有效且允许转发")
                        else:
                            self._logger.warning(f"源频道 {format_channel(channel_id)} 不允许转发: {reason}")
                    else:
                        self._logger.warning(f"无效的源频道 {source}: {reason}")
                except ChannelParseError as e:
                    self._logger.error(f"解析源频道 {source} 失败: {str(e)}")
            
            if not valid_source_channels:
                return {"success": False, "error": "没有有效的源频道可用于转发"}
            
            # 验证目标频道
            valid_target_channels = []
            for targets in channel_pairs.values():
                for target in targets:
                    try:
                        # 使用新的频道解析功能解析频道标识符
                        channel_id, _ = parse_channel(target)
                        valid, reason = await is_channel_valid(target)
                        
                        if valid:
                            # 检查转发权限
                            can_forward, reason = await can_forward_to(target)
                            if can_forward:
                                if target not in valid_target_channels:
                                    valid_target_channels.append(target)
                                    self._logger.info(f"目标频道 {format_channel(channel_id)} 有效且可接收转发")
                            else:
                                self._logger.warning(f"无法转发到目标频道 {format_channel(channel_id)}: {reason}")
                        else:
                            self._logger.warning(f"无效的目标频道 {target}: {reason}")
                    except ChannelParseError as e:
                        self._logger.error(f"解析目标频道 {target} 失败: {str(e)}")
            
            if not valid_target_channels:
                return {"success": False, "error": "没有有效的目标频道可接收转发"}
            
            # 更新配置中的频道信息
            updated_channel_pairs = {}
            for source in valid_source_channels:
                valid_targets = []
                for target in channel_pairs.get(source, []):
                    if target in valid_target_channels:
                        valid_targets.append(target)
                if valid_targets:
                    updated_channel_pairs[source] = valid_targets
            
            if not updated_channel_pairs:
                return {"success": False, "error": "没有有效的源频道到目标频道的映射"}
            
            forward_config["channel_pairs"] = updated_channel_pairs
            target_channels = valid_target_channels
            
            # 提取其他参数
            caption_template = forward_config.get("caption_template", "{original_caption}")
            remove_captions = forward_config.get("remove_captions", False)
            download_media = forward_config.get("download_media", True)
            
            self._logger.info(f"启动转发服务，监控源频道: {valid_source_channels}")
            
            # 保存转发配置
            self._source_channels = valid_source_channels
            self._target_channels = target_channels
            self._forward_config = forward_config
            
            # 获取配置中的转发间隔
            self._forward_interval = forward_config.get("forward_delay", 2)
            
            # 创建转发任务，使用asyncio.create_task替代task_manager
            method_to_run = self._forward_monitoring_task if not monitor_mode else self._message_monitoring_task
            self._forward_task = asyncio.create_task(method_to_run())
            
            self._running = True
            self._logger.info("转发服务已启动")
            
            return {
                "success": True, 
                "task_id": id(self._forward_task),
                "source_channels": valid_source_channels,
                "target_channels": target_channels,
                "config": self._forward_config
            }
        
        except Exception as e:
            self._logger.error(f"启动转发服务失败: {str(e)}", exc_info=True)
            return {"success": False, "error": str(e)}
    
    async def stop_forwarding(self) -> Dict[str, Any]:
        """
        停止转发服务
        
        Returns:
            Dict[str, Any]: 停止结果
        """
        if not self._running:
            return {"success": False, "error": "转发服务未在运行"}
        
        try:
            # 取消转发监控任务
            if self._forward_task:
                if not self._forward_task.done():
                    self._forward_task.cancel()
                    try:
                        await self._forward_task
                    except asyncio.CancelledError:
                        pass
                self._forward_task = None
            
            # 取消所有进行中的任务
            for task_id, task in list(self._tasks.items()):
                if isinstance(task, asyncio.Task) and not task.done():
                    task.cancel()
                    try:
                        await task
                    except asyncio.CancelledError:
                        pass
                self._tasks.pop(task_id, None)
            
            self._running = False
            self._logger.info("转发服务已停止")
            
            return {"success": True}
        
        except Exception as e:
            self._logger.error(f"停止转发服务失败: {str(e)}", exc_info=True)
            return {"success": False, "error": str(e)}
    
    def get_forwarding_status(self) -> Dict[str, Any]:
        """
        获取转发服务状态
        
        Returns:
            Dict[str, Any]: 转发服务状态信息
        """
        if not self._initialized:
            return {"initialized": False, "running": False}
        
        status = {
            "initialized": True,
            "running": self._running,
            "source_channels": self._source_channels.copy() if self._running else [],
            "target_channels": self._target_channels.copy() if self._running else [],
            "forward_interval": self._forward_interval,
            "active_tasks": len(self._tasks),
            "scheduled_tasks": len(self._scheduled_tasks),
            "monitoring_task": self._forward_task,
            "config": self._forward_config.copy() if self._running else {}
        }
        
        return status
    
    async def start_monitor(
        self,
        monitor_config: Dict[str, Any] = None
    ) -> Dict[str, Any]:
        """
        启动监听服务，实时监听源频道的新消息并转发到目标频道
        
        Args:
            monitor_config: 监听配置，为None时使用默认配置。配置应包含：
                - channel_pairs: 源频道与目标频道的映射关系
                - duration: 监听时长，格式为"年-月-日-时"，如"2025-3-28-1"
                - remove_captions: 是否移除原始字幕
                - media_types: 要转发的媒体类型列表
                - forward_delay: 转发延迟（秒）
                - max_retries: 失败后最大重试次数
                - message_filter: 消息过滤器表达式
            
        Returns:
            Dict[str, Any]: 启动结果，包含以下字段：
                - success: 是否成功启动
                - error: 如果失败，包含错误信息
                - monitor_id: 监听任务ID
                - start_time: 开始时间
                - end_time: 预计结束时间（根据duration计算）
        """
        # 检查是否已经在监听中
        if self._running and self._forward_task:
            self._logger.warning("监听服务已在运行中")
            return {
                "success": False,
                "error": "监听服务已在运行中",
                "monitor_id": str(self._forward_task)
            }
        
        try:
            # 如果没有提供配置，使用默认配置
            if monitor_config is None:
                monitor_config = self._config.get_monitor_config()
            
            # 从配置中提取必要的参数
            channel_pairs = monitor_config.get("channel_pairs", {})
            if not channel_pairs:
                return {
                    "success": False,
                    "error": "未提供有效的频道对配置"
                }
            
            # 提取源频道和目标频道
            source_channels = list(channel_pairs.keys())
            
            # 验证监听持续时间
            duration = monitor_config.get("duration", "2025-12-31-23")  # 默认到2025年底
            
            # 解析持续时间
            try:
                end_time = None
                if duration:
                    parts = duration.split("-")
                    if len(parts) >= 4:
                        year, month, day, hour = map(int, parts[:4])
                        from datetime import datetime
                        end_time = datetime(year, month, day, hour)
                    else:
                        self._logger.warning(f"无效的持续时间格式: {duration}，使用默认值")
            except Exception as e:
                self._logger.error(f"解析持续时间出错: {str(e)}")
                return {
                    "success": False,
                    "error": f"解析持续时间出错: {str(e)}"
                }
            
            # 初始化监听配置
            self._monitor_running = True
            self._monitor_config = monitor_config
            self._monitor_start_time = datetime.now()
            self._monitor_end_time = end_time
            self._monitor_source_channels = source_channels
            self._monitor_forwarded_count = 0
            self._monitor_errors = {}
            
            # 生成唯一的监听ID
            import uuid
            monitor_id = str(uuid.uuid4())
            self._monitor_id = monitor_id
            
            # 启动监听任务
            self._forward_task = asyncio.create_task(self._message_monitoring_task())
            
            self._logger.info(f"监听服务已启动，监听ID: {monitor_id}")
            
            # 返回启动结果
            return {
                "success": True,
                "monitor_id": monitor_id,
                "start_time": self._monitor_start_time.isoformat(),
                "end_time": self._monitor_end_time.isoformat() if self._monitor_end_time else None,
                "channel_pairs": channel_pairs
            }
            
        except Exception as e:
            self._logger.error(f"启动监听服务失败: {str(e)}", exc_info=True)
            return {
                "success": False,
                "error": f"启动监听服务失败: {str(e)}"
            }
    
    async def stop_monitor(self) -> Dict[str, Any]:
        """
        停止监听服务
        
        Returns:
            Dict[str, Any]: 停止结果，包含以下字段：
                - success: 是否成功停止
                - error: 如果失败，包含错误信息
                - monitor_id: 监听任务ID
                - duration: 实际监听时长（秒）
                - messages_forwarded: 已转发的消息数量
        """
        if not self._monitor_running or not self._forward_task:
            return {
                "success": False,
                "error": "监听服务未在运行"
            }
        
        try:
            # 取消监听任务
            if not self._forward_task.done():
                self._forward_task.cancel()
                try:
                    await self._forward_task
                except asyncio.CancelledError:
                    pass
            
            # 计算实际监听时长
            end_time = datetime.now()
            duration = (end_time - self._monitor_start_time).total_seconds()
            
            # 更新状态
            self._monitor_running = False
            self._forward_task = None
            
            self._logger.info(f"监听服务已停止，ID: {self._monitor_id}, 持续时间: {duration}秒")
            
            # 返回停止结果
            return {
                "success": True,
                "monitor_id": self._monitor_id,
                "duration": duration,
                "messages_forwarded": self._monitor_forwarded_count
            }
            
        except Exception as e:
            self._logger.error(f"停止监听服务失败: {str(e)}", exc_info=True)
            return {
                "success": False,
                "error": f"停止监听服务失败: {str(e)}"
            }
    
    def get_monitor_status(self) -> Dict[str, Any]:
        """
        获取监听服务状态
        
        Returns:
            Dict[str, Any]: 监听服务状态信息，包含以下字段：
                - running: 是否正在运行
                - start_time: 开始时间
                - end_time: 预计结束时间
                - remaining_time: 剩余时间（秒）
                - messages_forwarded: 已转发的消息数量
                - channel_pairs: 监听的频道对
                - errors: 错误统计
        """
        if not hasattr(self, '_monitor_running') or not self._monitor_running:
            return {
                "running": False
            }
        
        # 计算剩余时间
        now = datetime.now()
        remaining_time = 0
        if self._monitor_end_time and self._monitor_end_time > now:
            remaining_time = (self._monitor_end_time - now).total_seconds()
        
        # 组装状态信息
        status = {
            "running": self._monitor_running,
            "monitor_id": getattr(self, "_monitor_id", ""),
            "start_time": self._monitor_start_time.isoformat() if hasattr(self, "_monitor_start_time") else None,
            "end_time": self._monitor_end_time.isoformat() if hasattr(self, "_monitor_end_time") and self._monitor_end_time else None,
            "remaining_time": remaining_time,
            "messages_forwarded": getattr(self, "_monitor_forwarded_count", 0),
            "channel_pairs": self._monitor_config.get("channel_pairs", {}) if hasattr(self, "_monitor_config") else {},
            "errors": getattr(self, "_monitor_errors", {})
        }
        
        return status
    
    async def _message_monitoring_task(self) -> None:
        """
        消息监听任务，监听源频道的新消息并转发
        """
        self._logger.info("开始监听消息")
        
        # 从监听配置中获取相关参数
        if not hasattr(self, "_monitor_config") or not self._monitor_config:
            self._logger.error("监听配置不存在，无法启动监听任务")
            return
            
        channel_pairs = self._monitor_config.get("channel_pairs", {})
        forward_delay = self._monitor_config.get("forward_delay", 2)
        media_types = self._monitor_config.get("media_types", ["photo", "video", "document", "audio", "animation"])
        remove_captions = self._monitor_config.get("remove_captions", False)
        max_retries = self._monitor_config.get("max_retries", 3)
        message_filter = self._monitor_config.get("message_filter", "")
        
        # 存储每个源频道的最新消息ID
        last_message_ids = {}
        
        try:
            while True:
                # 检查是否到达结束时间
                now = datetime.now()
                if hasattr(self, "_monitor_end_time") and self._monitor_end_time and now >= self._monitor_end_time:
                    self._logger.info(f"已到达监听结束时间: {self._monitor_end_time.isoformat()}")
                    break
                
                # 处理每个频道对
                for source_channel, target_channels in channel_pairs.items():
                    try:
                        # 检查目标频道是否有效
                        if not target_channels:
                            continue
                            
                        # 获取源频道最新消息ID
                        latest_id = await self._client.get_latest_message_id(source_channel)
                        if latest_id is None:
                            self._logger.warning(f"无法获取频道 {source_channel} 的最新消息ID")
                            continue
                        
                        # 获取上次处理的消息ID
                        last_id = last_message_ids.get(source_channel, 0)
                        
                        # 首次运行只记录最新ID，不处理消息
                        if last_id == 0:
                            last_message_ids[source_channel] = latest_id
                            self._logger.info(f"已记录频道 {source_channel} 的最新消息ID: {latest_id}")
                            continue
                        
                        # 处理新消息
                        if latest_id > last_id:
                            self._logger.info(f"频道 {source_channel} 有新消息: {last_id+1} 到 {latest_id}")
                            
                            # 处理每条新消息
                            for msg_id in range(last_id + 1, latest_id + 1):
                                # 获取消息
                                message = await self._client.get_message(source_channel, msg_id)
                                if not message:
                                    self._logger.warning(f"无法获取消息: {source_channel}, ID={msg_id}")
                                    continue
                                
                                # 检查媒体类型是否符合条件
                                message_type = self._get_message_type(message)
                                if message_type not in media_types and message_type != "text":
                                    self._logger.info(f"消息类型 {message_type} 不在转发列表中，跳过: {source_channel}, ID={msg_id}")
                                    continue
                                
                                # 如果有过滤器，检查消息内容
                                if message_filter and message.text:
                                    # 简单实现的过滤器，如果消息中不包含过滤器文本则跳过
                                    # 未来可以实现更复杂的过滤逻辑
                                    if message_filter not in message.text:
                                        self._logger.info(f"消息内容不符合过滤条件，跳过: {source_channel}, ID={msg_id}")
                                        continue
                                
                                # 转发消息
                                retry_count = 0
                                while retry_count <= max_retries:
                                    try:
                                        # 对单条消息进行转发
                                        result = await self.forward_message(
                                            source_channel, 
                                            msg_id, 
                                            target_channels
                                        )
                                        
                                        # 检查转发结果
                                        if result.get("success", False):
                                            self._logger.info(f"成功转发消息: {source_channel}, ID={msg_id}")
                                            self._monitor_forwarded_count += 1
                                            break
                                        else:
                                            error_msg = result.get("error", "未知错误")
                                            self._logger.warning(f"转发消息失败: {source_channel}, ID={msg_id}, 错误: {error_msg}")
                                            
                                            # 记录错误统计
                                            error_type = error_msg[:50]  # 截取错误类型
                                            if error_type not in self._monitor_errors:
                                                self._monitor_errors[error_type] = 0
                                            self._monitor_errors[error_type] += 1
                                            
                                            # 准备重试
                                            retry_count += 1
                                            if retry_count <= max_retries:
                                                self._logger.info(f"准备重试 ({retry_count}/{max_retries}): {source_channel}, ID={msg_id}")
                                                await asyncio.sleep(2 * retry_count)  # 指数退避
                                    except Exception as e:
                                        self._logger.error(f"转发过程中出错: {source_channel}, ID={msg_id}, 错误: {str(e)}")
                                        retry_count += 1
                                        if retry_count <= max_retries:
                                            await asyncio.sleep(2 * retry_count)
                                        else:
                                            break
                                
                                # 添加延迟，避免速率限制
                                await asyncio.sleep(forward_delay)
                            
                            # 更新最新处理的消息ID
                            last_message_ids[source_channel] = latest_id
                    
                    except Exception as e:
                        self._logger.error(f"处理频道 {source_channel} 时出错: {str(e)}", exc_info=True)
                        
                        # 记录错误统计
                        error_type = str(e)[:50]  # 截取错误类型
                        if error_type not in self._monitor_errors:
                            self._monitor_errors[error_type] = 0
                        self._monitor_errors[error_type] += 1
                
                # 检查间隔，避免过于频繁轮询
                await asyncio.sleep(10)  # 每10秒检查一次新消息
                
        except asyncio.CancelledError:
            self._logger.info("监听任务已取消")
            
        except Exception as e:
            self._logger.error(f"监听任务出错: {str(e)}", exc_info=True)
            
            # 记录错误统计
            error_type = str(e)[:50]
            if error_type not in self._monitor_errors:
                self._monitor_errors[error_type] = 0
            self._monitor_errors[error_type] += 1
    
    def _get_message_type(self, message) -> str:
        """
        获取消息的类型
        
        Args:
            message: 消息对象
            
        Returns:
            str: 消息类型，如 'photo', 'video', 'text' 等
        """
        if message.photo:
            return "photo"
        elif message.video:
            return "video"
        elif message.document:
            return "document"
        elif message.audio:
            return "audio"
        elif message.animation:
            return "animation"
        elif message.voice:
            return "voice"
        elif message.sticker:
            return "sticker"
        elif message.text:
            return "text"
        else:
            return "unknown"
    
    async def _forward_monitoring_task(self) -> None:
        """
        转发监控任务，定期检查源频道的新消息并转发
        """
        self._logger.info(f"开始转发监控任务，检查间隔: {self._forward_interval}秒")
        
        # 存储每个源频道的最新消息ID
        last_message_ids = {}
        
        try:
            while True:
                for source_channel in self._source_channels:
                    try:
                        # 获取该频道的最新消息ID
                        latest_id = await self._client.get_latest_message_id(source_channel)
                        
                        if latest_id is None:
                            self._logger.warning(f"无法获取频道 {source_channel} 的最新消息ID")
                            continue
                        
                        # 检查是否有新消息
                        last_id = last_message_ids.get(source_channel, 0)
                        
                        if last_id == 0:
                            # 首次运行，仅记录最新ID但不转发
                            last_message_ids[source_channel] = latest_id
                            self._logger.info(f"已记录频道 {source_channel} 的最新消息ID: {latest_id}")
                            continue
                        
                        if latest_id > last_id:
                            self._logger.info(f"频道 {source_channel} 有新消息: {last_id+1} - {latest_id}")
                            
                            # 转发新消息
                            for msg_id in range(last_id + 1, latest_id + 1):
                                await self.forward_message(
                                    source_channel,
                                    msg_id,
                                    self._target_channels
                                )
                                # 添加短暂延迟，避免API限制
                                await asyncio.sleep(1)
                            
                            # 更新最新ID
                            last_message_ids[source_channel] = latest_id
                    
                    except Exception as e:
                        self._logger.error(f"处理频道 {source_channel} 的消息时出错: {str(e)}", exc_info=True)
                
                # 等待下一次检查
                await asyncio.sleep(self._forward_interval)
        
        except asyncio.CancelledError:
            self._logger.info("转发监控任务已取消")
        
        except Exception as e:
            self._logger.error(f"转发监控任务出错: {str(e)}", exc_info=True)
            raise

    # 以下是内部辅助方法
    
    async def _forward_single_message(
        self, 
        source_channel: Union[str, int], 
        target_channel: Union[str, int], 
        message_id: int,
        caption_template: Optional[str] = None,
        remove_captions: bool = False,
        download_media: bool = True
    ) -> Dict[str, Any]:
        """
        转发单个消息的内部实现
        
        Args:
            source_channel: 源频道标识
            target_channel: 目标频道标识
            message_id: 消息ID
            caption_template: 可选的标题模板
            remove_captions: 是否移除标题
            download_media: 是否下载媒体然后重新发送
            
        Returns:
            Dict[str, Any]: 转发结果
        """
        try:
            # 如果需要直接转发（不下载媒体）
            if not download_media:
                result = await self._client.forward_message(target_channel, source_channel, message_id)
                if result:
                    return {
                        "success": True,
                        "source_channel": source_channel,
                        "target_channel": target_channel,
                        "source_message_id": message_id,
                        "target_message_id": result.id,
                        "forwarded_directly": True
                    }
                else:
                    return {"success": False, "error": "直接转发失败"}
            
            # 下载消息及媒体
            download_result = await self._downloader.download_message(source_channel, message_id)
            if not download_result["success"]:
                return {
                    "success": False, 
                    "error": f"下载消息失败: {download_result.get('error')}"
                }
            
            task_id = download_result.get("task_id")
            
            # 处理标题
            message_data = download_result.get("message_data", {})
            if remove_captions:
                if "caption" in message_data:
                    del message_data["caption"]
            elif caption_template and "caption" in message_data:
                # 替换标题中的模板变量
                original_caption = message_data.get("caption", "")
                message_data["caption"] = self._process_caption_template(
                    caption_template, 
                    original_caption,
                    source_channel,
                    message_id
                )
            
            # 上传消息到目标频道
            upload_result = await self._uploader.upload_message(
                target_channel, 
                message_data,
                task_id=task_id
            )
            
            if not upload_result["success"]:
                return {
                    "success": False, 
                    "error": f"上传消息失败: {upload_result.get('error')}"
                }
            
            return {
                "success": True,
                "source_channel": source_channel,
                "target_channel": target_channel,
                "source_message_id": message_id,
                "target_message_id": upload_result.get("message_id"),
                "task_id": task_id,
                "forwarded_directly": False
            }
        
        except Exception as e:
            self._logger.error(f"转发单个消息失败: {str(e)}", exc_info=True)
            return {"success": False, "error": str(e)}
    
    async def _get_messages_by_date_range(
        self, 
        channel: Union[str, int],
        start_date: datetime,
        end_date: datetime
    ) -> List[Any]:
        """
        获取指定日期范围内的消息
        
        Args:
            channel: 频道标识
            start_date: 起始日期
            end_date: 结束日期
            
        Returns:
            List[Any]: 消息列表
        """
        # 确保客户端已连接
        await self._client.connect()
        
        messages = []
        limit = 100  # 每次获取的消息数量
        
        try:
            # 获取消息历史
            async for message in self._client.get_chat_history(channel, limit=limit):
                # 检查消息日期是否在范围内
                if message.date:
                    msg_date = datetime.fromtimestamp(message.date)
                    if start_date <= msg_date <= end_date:
                        messages.append(message)
                    elif msg_date < start_date:
                        # 如果消息日期早于起始日期，可以停止获取
                        break
            
            return messages
        except Exception as e:
            self._logger.error(f"获取日期范围内的消息失败: {str(e)}", exc_info=True)
            return []
    
    def _get_default_target_channels(self) -> List[Union[str, int]]:
        """
        获取默认的目标频道列表
        
        Returns:
            List[Union[str, int]]: 默认目标频道列表
        """
        try:
            # 从配置中获取默认目标频道
            target_channels = self._config.get_target_channels()
            
            if not target_channels:
                self._logger.warning("配置中未找到默认目标频道")
            
            return target_channels
        except Exception as e:
            self._logger.error(f"获取默认目标频道失败: {str(e)}", exc_info=True)
            return []
    
    def _get_forward_config(
        self,
        source_channel: Union[str, int],
        target_channel: Union[str, int]
    ) -> Dict[str, Any]:
        """
        获取特定源频道和目标频道组合的转发配置
        
        Args:
            source_channel: 源频道标识
            target_channel: 目标频道标识
            
        Returns:
            Dict[str, Any]: 转发配置
        """
        try:
            # 获取基本配置
            base_config = {
                "caption_template": None,
                "remove_captions": False,
                "download_media": True,
                "delay": 1.0
            }
            
            # 尝试从配置中获取特定频道组合的配置
            channel_key = f"forward_config:{source_channel}:{target_channel}"
            specific_config = self._config.get_value(channel_key)
            
            if specific_config and isinstance(specific_config, dict):
                # 合并特定配置和基本配置
                for key, value in specific_config.items():
                    base_config[key] = value
            
            return base_config
        except Exception as e:
            self._logger.error(f"获取转发配置失败: {str(e)}", exc_info=True)
            return {
                "caption_template": None,
                "remove_captions": False,
                "download_media": True,
                "delay": 1.0
            }
    
    async def _scheduled_forward_task(
        self,
        source_channel: Union[str, int],
        message_id: Union[int, Tuple[int, int]],
        target_channels: List[Union[str, int]]
    ) -> Dict[str, Any]:
        """
        执行计划的转发任务
        
        Args:
            source_channel: 源频道标识
            message_id: 消息ID或范围(起始ID, 结束ID)
            target_channels: 目标频道列表
            
        Returns:
            Dict[str, Any]: 转发结果
        """
        try:
            # 连接客户端
            await self._client.connect()
            
            # 根据消息ID类型决定转发方式
            if isinstance(message_id, tuple) and len(message_id) == 2:
                start_id, end_id = message_id
                return await self.forward_range(source_channel, start_id, end_id, target_channels)
            else:
                # 单条消息或媒体组
                # 检查是否是媒体组
                message = await self._client.get_message(source_channel, message_id)
                if message and message.media_group_id:
                    return await self.forward_media_group(source_channel, message_id, target_channels)
                else:
                    return await self.forward_message(source_channel, message_id, target_channels)
        
        except Exception as e:
            self._logger.error(f"执行计划转发任务失败: {str(e)}", exc_info=True)
            return {"success": False, "error": str(e)}
    
    def _process_caption_template(
        self, 
        template: str, 
        original_caption: str,
        source_chat: Union[str, int],
        message_id: int
    ) -> str:
        """
        处理标题模板
        
        Args:
            template: 标题模板
            original_caption: 原始标题
            source_chat: 源聊天ID或用户名
            message_id: 消息ID
            
        Returns:
            str: 处理后的标题
        """
        # 替换模板变量
        result = template
        
        # 可用变量：
        # {original} - 原始标题
        # {source} - 源频道
        # {date} - 当前日期
        # {time} - 当前时间
        # {message_id} - 消息ID
        
        result = result.replace("{original}", original_caption)
        result = result.replace("{source}", str(source_chat))
        result = result.replace("{message_id}", str(message_id))
        
        now = datetime.now()
        result = result.replace("{date}", now.strftime("%Y-%m-%d"))
        result = result.replace("{time}", now.strftime("%H:%M:%S"))
        
        return result