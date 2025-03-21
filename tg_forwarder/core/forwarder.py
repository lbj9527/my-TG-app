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
from tg_forwarder.interfaces.task_manager_interface import TaskManagerInterface
from tg_forwarder.interfaces.config_interface import ConfigInterface


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
        task_manager: TaskManagerInterface,
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
            task_manager: 任务管理器接口实例
            config: 配置接口实例
            logger: 日志接口实例
        """
        self._client = client
        self._downloader = downloader
        self._uploader = uploader
        self._status_tracker = status_tracker
        self._task_manager = task_manager
        self._config = config
        self._logger = logger.get_logger("Forwarder")
        
        self._initialized = False
        self._running = False
        self._tasks = {}  # 正在进行的转发任务
        self._scheduled_tasks = {}  # 计划任务
    
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
            
            media_ids = [msg.id for msg in media_group]
            self._logger.info(f"找到媒体组，共 {len(media_ids)} 条消息: {media_ids}")
            
            results = {"success": True, "targets": {}, "source_channel": source_channel, "media_group_ids": media_ids}
            
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
            
            valid_message_ids = [msg.id for msg in messages if msg is not None]
            
            self._logger.info(f"在范围 {start_id}-{end_id} 中找到 {len(valid_message_ids)}/{total_messages} 条有效消息")
            
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
                    
                    for msg_id in valid_message_ids:
                        result = await self._forward_single_message(
                            source_channel, 
                            target, 
                            msg_id,
                            caption_template,
                            remove_captions,
                            download_media
                        )
                        
                        target_results.append(result)
                        
                        if not result["success"]:
                            failed_count += 1
                            self._logger.warning(f"转发消息 {msg_id} 到 {target} 失败: {result.get('error')}")
                        
                        # 添加延迟以避免API限制
                        await asyncio.sleep(delay)
                    
                    results["targets"][target] = {
                        "success": failed_count < len(valid_message_ids),
                        "total": len(valid_message_ids),
                        "succeeded": len(valid_message_ids) - failed_count,
                        "failed": failed_count,
                        "results": target_results
                    }
                    
                    if failed_count == len(valid_message_ids):
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
        
        # 创建调度任务
        task_id = self._task_manager.submit_task(
            "scheduled_forward",
            self._scheduled_forward_task,
            source_channel,
            message_id,
            target_channels,
            _name=f"计划转发任务: {source_channel}",
            _queue="scheduled"
        )
        
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
        if self._task_manager.cancel_task(task_id):
            self._scheduled_tasks[task_id]["status"] = "cancelled"
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
            task_status = self._task_manager.get_task_status(task_id)
            
            return {
                **scheduled_info,
                "task_type": "scheduled",
                "task_status": task_status.get("status", "unknown")
            }
        
        # 检查是否是常规转发任务
        if task_id in self._tasks:
            forward_info = self._tasks[task_id]
            task_status = self._task_manager.get_task_status(task_id)
            
            return {
                **forward_info,
                "task_type": "forward",
                "task_status": task_status.get("status", "unknown")
            }
        
        # 直接从任务管理器获取状态
        task_status = self._task_manager.get_task_status(task_id)
        if "error" in task_status:
            return {"error": f"找不到任务: {task_id}"}
        
        return {
            "task_id": task_id,
            "task_type": "unknown",
            "task_status": task_status.get("status", "unknown"),
            "details": task_status
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