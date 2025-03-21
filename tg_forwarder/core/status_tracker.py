"""
状态追踪器实现类
负责跟踪和管理消息转发状态
"""

import uuid
from typing import Dict, Any, List, Union, Optional
from datetime import datetime, timedelta
import threading

from tg_forwarder.interfaces.status_tracker_interface import StatusTrackerInterface
from tg_forwarder.interfaces.storage_interface import StorageInterface
from tg_forwarder.interfaces.logger_interface import LoggerInterface


class StatusTracker(StatusTrackerInterface):
    """
    状态追踪器，实现StatusTrackerInterface接口
    负责跟踪和管理消息转发状态
    """
    
    def __init__(self, storage: StorageInterface, logger: LoggerInterface):
        """
        初始化状态追踪器
        
        Args:
            storage: 存储接口实例
            logger: 日志接口实例
        """
        self._storage = storage
        self._logger = logger.get_logger("StatusTracker")
        self._collection_name = "forwarding_tasks"
        self._initialized = False
        self._status_cache = {}
        self._last_updated = {}
        self._cache_ttl = 300  # 默认缓存有效期为5分钟
        self._lock = threading.RLock()
    
    async def initialize(self) -> bool:
        """
        初始化状态追踪器
        
        Returns:
            bool: 初始化是否成功
        """
        try:
            # 确保数据库已初始化
            if not self._storage._initialized:
                self._logger.error("存储系统未初始化")
                return False
            
            # 确保索引存在
            await self._ensure_indexes()
            
            self._initialized = True
            self._logger.info("状态追踪器初始化完成")
            return True
        except Exception as e:
            self._logger.error(f"初始化状态追踪器失败: {str(e)}", exc_info=True)
            self._initialized = False
            return False
    
    async def _ensure_indexes(self):
        """确保必要的索引存在"""
        # 为转发任务创建索引
        await self._storage.ensure_index(self._collection_name, ["source_chat_id", "message_id"], unique=True)
        await self._storage.ensure_index(self._collection_name, ["status"])
        await self._storage.ensure_index(self._collection_name, ["created_at"])
        
        # 为频道状态创建索引
        await self._storage.ensure_index("channel_status", ["chat_id"], unique=True)
        
        # 为系统状态创建索引
        await self._storage.ensure_index("system_status", ["component"], unique=True)
    
    def shutdown(self) -> None:
        """关闭状态追踪器，释放资源"""
        with self._lock:
            self._initialized = False
            self._logger.info("状态追踪器已关闭")
    
    def is_initialized(self) -> bool:
        """
        检查状态追踪器是否已初始化
        
        Returns:
            bool: 状态追踪器是否已初始化
        """
        return self._initialized
    
    def record_download_start(self, chat_id: Union[str, int], message_id: int, media_group_id: Optional[str] = None) -> str:
        """
        记录开始下载消息
        
        Args:
            chat_id: 聊天ID
            message_id: 消息ID
            media_group_id: 媒体组ID（可选）
            
        Returns:
            str: 任务ID
        """
        if not self._initialized:
            self._logger.error("状态追踪器未初始化")
            return ""
        
        task_id = str(uuid.uuid4())
        task_data = {
            "task_id": task_id,
            "chat_id": str(chat_id),
            "message_id": message_id,
            "media_group_id": media_group_id,
            "status": "downloading",
            "created_at": datetime.now().isoformat(),
            "updated_at": datetime.now().isoformat(),
            "download_started_at": datetime.now().isoformat(),
            "download_completed_at": None,
            "download_error": None,
            "file_path": None,
            "upload_tasks": []
        }
        
        if self._storage.store(self._collection_name, task_id, task_data):
            self._logger.info(f"开始下载消息: chat_id={chat_id}, message_id={message_id}, task_id={task_id}")
            return task_id
        else:
            self._logger.error(f"记录下载开始失败: chat_id={chat_id}, message_id={message_id}")
            return ""
    
    def record_download_complete(self, task_id: str, file_path: str) -> None:
        """
        记录下载完成
        
        Args:
            task_id: 任务ID
            file_path: 下载文件路径
        """
        if not self._initialized:
            self._logger.error("状态追踪器未初始化")
            return
        
        task = self._storage.retrieve(self._collection_name, task_id)
        if not task:
            self._logger.error(f"找不到任务: {task_id}")
            return
        
        task["status"] = "downloaded"
        task["updated_at"] = datetime.now().isoformat()
        task["download_completed_at"] = datetime.now().isoformat()
        task["file_path"] = file_path
        
        if self._storage.update(self._collection_name, task_id, task):
            self._logger.info(f"下载完成: task_id={task_id}, file_path={file_path}")
        else:
            self._logger.error(f"记录下载完成失败: task_id={task_id}")
    
    def record_download_failed(self, task_id: str, error: str) -> None:
        """
        记录下载失败
        
        Args:
            task_id: 任务ID
            error: 错误信息
        """
        if not self._initialized:
            self._logger.error("状态追踪器未初始化")
            return
        
        task = self._storage.retrieve(self._collection_name, task_id)
        if not task:
            self._logger.error(f"找不到任务: {task_id}")
            return
        
        task["status"] = "download_failed"
        task["updated_at"] = datetime.now().isoformat()
        task["download_error"] = error
        
        if self._storage.update(self._collection_name, task_id, task):
            self._logger.warning(f"下载失败: task_id={task_id}, error={error}")
        else:
            self._logger.error(f"记录下载失败状态失败: task_id={task_id}")
    
    def record_upload_start(self, task_id: str, target_chat_id: Union[str, int]) -> None:
        """
        记录开始上传消息
        
        Args:
            task_id: 任务ID
            target_chat_id: 目标聊天ID
        """
        if not self._initialized:
            self._logger.error("状态追踪器未初始化")
            return
        
        task = self._storage.retrieve(self._collection_name, task_id)
        if not task:
            self._logger.error(f"找不到任务: {task_id}")
            return
        
        # 查找是否已有该目标的上传任务
        target_chat_id_str = str(target_chat_id)
        upload_task = None
        for ut in task.get("upload_tasks", []):
            if ut.get("target_chat_id") == target_chat_id_str:
                upload_task = ut
                break
        
        # 如果没有，则创建新的上传任务
        if upload_task is None:
            upload_task = {
                "target_chat_id": target_chat_id_str,
                "status": "uploading",
                "upload_started_at": datetime.now().isoformat(),
                "upload_completed_at": None,
                "target_message_id": None,
                "upload_error": None
            }
            task["upload_tasks"].append(upload_task)
        else:
            upload_task["status"] = "uploading"
            upload_task["upload_started_at"] = datetime.now().isoformat()
            upload_task["upload_error"] = None
        
        task["status"] = "uploading"
        task["updated_at"] = datetime.now().isoformat()
        
        if self._storage.update(self._collection_name, task_id, task):
            self._logger.info(f"开始上传: task_id={task_id}, target_chat_id={target_chat_id}")
        else:
            self._logger.error(f"记录上传开始失败: task_id={task_id}, target_chat_id={target_chat_id}")
    
    def record_upload_complete(self, task_id: str, target_chat_id: Union[str, int], 
                              target_message_id: int) -> None:
        """
        记录上传完成
        
        Args:
            task_id: 任务ID
            target_chat_id: 目标聊天ID
            target_message_id: 目标消息ID
        """
        if not self._initialized:
            self._logger.error("状态追踪器未初始化")
            return
        
        task = self._storage.retrieve(self._collection_name, task_id)
        if not task:
            self._logger.error(f"找不到任务: {task_id}")
            return
        
        # 查找并更新对应的上传任务
        target_chat_id_str = str(target_chat_id)
        for ut in task.get("upload_tasks", []):
            if ut.get("target_chat_id") == target_chat_id_str:
                ut["status"] = "uploaded"
                ut["upload_completed_at"] = datetime.now().isoformat()
                ut["target_message_id"] = target_message_id
                break
        
        # 检查是否所有上传任务都已完成
        all_completed = True
        for ut in task.get("upload_tasks", []):
            if ut.get("status") not in ["uploaded", "upload_failed"]:
                all_completed = False
                break
        
        if all_completed and task["upload_tasks"]:
            task["status"] = "completed"
        
        task["updated_at"] = datetime.now().isoformat()
        
        if self._storage.update(self._collection_name, task_id, task):
            self._logger.info(f"上传完成: task_id={task_id}, target_chat_id={target_chat_id}, target_message_id={target_message_id}")
        else:
            self._logger.error(f"记录上传完成失败: task_id={task_id}, target_chat_id={target_chat_id}")
    
    def record_upload_failed(self, task_id: str, target_chat_id: Union[str, int], 
                           error: str) -> None:
        """
        记录上传失败
        
        Args:
            task_id: 任务ID
            target_chat_id: 目标聊天ID
            error: 错误信息
        """
        if not self._initialized:
            self._logger.error("状态追踪器未初始化")
            return
        
        task = self._storage.retrieve(self._collection_name, task_id)
        if not task:
            self._logger.error(f"找不到任务: {task_id}")
            return
        
        # 查找并更新对应的上传任务
        target_chat_id_str = str(target_chat_id)
        for ut in task.get("upload_tasks", []):
            if ut.get("target_chat_id") == target_chat_id_str:
                ut["status"] = "upload_failed"
                ut["upload_error"] = error
                break
        
        # 检查是否所有上传任务都已完成（成功或失败）
        all_completed = True
        all_failed = True
        for ut in task.get("upload_tasks", []):
            if ut.get("status") not in ["uploaded", "upload_failed"]:
                all_completed = False
            if ut.get("status") != "upload_failed":
                all_failed = False
        
        if all_completed and task["upload_tasks"]:
            if all_failed:
                task["status"] = "upload_failed"
            else:
                task["status"] = "completed_with_errors"
        
        task["updated_at"] = datetime.now().isoformat()
        
        if self._storage.update(self._collection_name, task_id, task):
            self._logger.warning(f"上传失败: task_id={task_id}, target_chat_id={target_chat_id}, error={error}")
        else:
            self._logger.error(f"记录上传失败状态失败: task_id={task_id}, target_chat_id={target_chat_id}")
    
    def get_task_status(self, task_id: str) -> Dict[str, Any]:
        """
        获取任务状态
        
        Args:
            task_id: 任务ID
            
        Returns:
            Dict[str, Any]: 任务状态信息
        """
        if not self._initialized:
            self._logger.error("状态追踪器未初始化")
            return {}
        
        task = self._storage.retrieve(self._collection_name, task_id)
        if not task:
            self._logger.warning(f"找不到任务: {task_id}")
            return {}
        
        return task
    
    def get_pending_tasks(self) -> List[Dict[str, Any]]:
        """
        获取未完成的任务
        
        Returns:
            List[Dict[str, Any]]: 未完成任务列表
        """
        if not self._initialized:
            self._logger.error("状态追踪器未初始化")
            return []
        
        # 查询所有未完成任务
        pending_statuses = ["downloading", "downloaded", "uploading"]
        result = []
        
        for status in pending_statuses:
            tasks = self._storage.query(
                self._collection_name,
                {"status": status},
                sort_by="created_at"
            )
            result.extend(tasks)
        
        return result
    
    def get_statistics(self, start_date: Optional[datetime] = None, 
                      end_date: Optional[datetime] = None) -> Dict[str, Any]:
        """
        获取统计信息
        
        Args:
            start_date: 开始日期（可选）
            end_date: 结束日期（可选）
            
        Returns:
            Dict[str, Any]: 统计信息
        """
        if not self._initialized:
            self._logger.error("状态追踪器未初始化")
            return {}
        
        # 设置默认时间范围
        if not start_date:
            start_date = datetime.now() - timedelta(days=30)
        if not end_date:
            end_date = datetime.now()
        
        start_str = start_date.isoformat()
        end_str = end_date.isoformat()
        
        # 获取所有时间范围内的任务
        tasks = self._storage.query(
            self._collection_name,
            {},
            sort_by="created_at"
        )
        
        # 筛选时间范围内的任务
        filtered_tasks = [
            task for task in tasks
            if start_str <= task.get("created_at", "") <= end_str
        ]
        
        # 计算统计信息
        total_tasks = len(filtered_tasks)
        completed_tasks = sum(1 for task in filtered_tasks if task.get("status") == "completed")
        failed_tasks = sum(1 for task in filtered_tasks if task.get("status") in ["download_failed", "upload_failed"])
        partial_success = sum(1 for task in filtered_tasks if task.get("status") == "completed_with_errors")
        
        # 计算成功率
        success_rate = (completed_tasks / total_tasks * 100) if total_tasks > 0 else 0
        
        # 按状态分组
        status_counts = {}
        for task in filtered_tasks:
            status = task.get("status", "unknown")
            status_counts[status] = status_counts.get(status, 0) + 1
        
        # 计算平均处理时间
        download_times = []
        upload_times = []
        total_times = []
        
        for task in filtered_tasks:
            # 下载时间
            if task.get("download_started_at") and task.get("download_completed_at"):
                try:
                    start = datetime.fromisoformat(task["download_started_at"])
                    end = datetime.fromisoformat(task["download_completed_at"])
                    download_times.append((end - start).total_seconds())
                except (ValueError, TypeError):
                    pass
            
            # 上传时间
            for ut in task.get("upload_tasks", []):
                if ut.get("upload_started_at") and ut.get("upload_completed_at"):
                    try:
                        start = datetime.fromisoformat(ut["upload_started_at"])
                        end = datetime.fromisoformat(ut["upload_completed_at"])
                        upload_times.append((end - start).total_seconds())
                    except (ValueError, TypeError):
                        pass
            
            # 总处理时间
            if task.get("created_at") and task.get("updated_at") and task.get("status") in ["completed", "completed_with_errors"]:
                try:
                    start = datetime.fromisoformat(task["created_at"])
                    end = datetime.fromisoformat(task["updated_at"])
                    total_times.append((end - start).total_seconds())
                except (ValueError, TypeError):
                    pass
        
        avg_download_time = sum(download_times) / len(download_times) if download_times else 0
        avg_upload_time = sum(upload_times) / len(upload_times) if upload_times else 0
        avg_total_time = sum(total_times) / len(total_times) if total_times else 0
        
        return {
            "period": {
                "start_date": start_str,
                "end_date": end_str
            },
            "counts": {
                "total_tasks": total_tasks,
                "completed_tasks": completed_tasks,
                "failed_tasks": failed_tasks,
                "partial_success": partial_success
            },
            "success_rate": success_rate,
            "status_distribution": status_counts,
            "average_times": {
                "download_seconds": avg_download_time,
                "upload_seconds": avg_upload_time,
                "total_seconds": avg_total_time
            }
        } 