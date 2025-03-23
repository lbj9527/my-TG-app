# Telegram转发工具重构计划 - 第二阶段（任务队列插件实现）

## 任务2.7：实现任务队列插件(TaskQueuePlugin)

任务队列插件负责管理异步任务的调度和执行，对于需要并发处理的文件下载、上传等操作非常有用。

```python
# tg_app/plugins/utils/task_queue_plugin.py
import asyncio
import uuid
import time
from typing import Dict, Any, List, Optional, Union, Tuple, Callable, Coroutine
from collections import deque

from tg_app.plugins.base import PluginBase
from tg_app.events import event_types as events
from tg_app.utils.logger import get_logger

# 获取日志记录器
logger = get_logger("task_queue_plugin")

class Task:
    """任务类，表示一个异步任务"""
    
    def __init__(self, id: str, coroutine: Coroutine, priority: int = 0, metadata: Dict[str, Any] = None):
        """
        初始化任务
        
        Args:
            id: 任务ID
            coroutine: 要执行的协程
            priority: 优先级，数字越大优先级越高
            metadata: 任务元数据
        """
        self.id = id
        self.coroutine = coroutine
        self.priority = priority
        self.metadata = metadata or {}
        self.created_at = time.time()
        self.started_at = None
        self.finished_at = None
        self.result = None
        self.error = None
        self.status = "pending"  # pending, running, completed, failed, cancelled
    
    def __lt__(self, other):
        """比较任务优先级，用于队列排序"""
        return self.priority > other.priority  # 优先级高的排在前面

class TaskQueuePlugin(PluginBase):
    """
    任务队列插件，负责管理异步任务的调度和执行
    """
    
    def __init__(self, event_bus):
        """
        初始化任务队列插件
        
        Args:
            event_bus: 事件总线
        """
        super().__init__(event_bus)
        
        # 定义插件元数据
        self.id = "task_queue"
        self.name = "任务队列插件"
        self.version = "1.0.0"
        self.description = "管理异步任务的调度和执行"
        self.dependencies = []  # 任务队列插件没有依赖
        
        # 任务队列和任务映射
        self.task_queue = asyncio.PriorityQueue()
        self.tasks: Dict[str, Task] = {}
        
        # 运行状态
        self.is_running = False
        self.workers = []
        self.worker_count = 5  # 默认工作线程数
        self.should_stop = False
    
    async def initialize(self) -> None:
        """初始化插件"""
        logger.info("正在初始化任务队列插件...")
        
        # 注册事件处理器
        self.event_bus.subscribe(events.TASK_ADD, self._handle_task_add)
        self.event_bus.subscribe(events.TASK_CANCEL, self._handle_task_cancel)
        self.event_bus.subscribe(events.TASK_GET_STATUS, self._handle_task_get_status)
        self.event_bus.subscribe(events.TASK_GET_ALL, self._handle_task_get_all)
        self.event_bus.subscribe(events.APP_SHUTDOWN, self._handle_app_shutdown)
        
        # 从配置获取工作线程数
        response = await self.event_bus.publish_and_wait(
            events.CONFIG_GET_SECTION, 
            {"section": "task_queue"},
            timeout=5.0
        )
        
        if response and response.get("success", False):
            config = response.get("data", {})
            try:
                self.worker_count = int(config.get("worker_count", self.worker_count))
            except (ValueError, TypeError):
                logger.warning(f"配置中的工作线程数无效，使用默认值 {self.worker_count}")
        
        # 启动工作线程
        await self._start_workers()
        
        logger.info(f"任务队列插件初始化完成，启动了 {self.worker_count} 个工作线程")
    
    async def _handle_task_add(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """
        处理添加任务事件
        
        Args:
            data: 事件数据
            
        Returns:
            Dict[str, Any]: 添加结果
        """
        coroutine = data.get("coroutine")
        if not coroutine or not asyncio.iscoroutine(coroutine):
            return {"success": False, "error": "未提供有效的协程"}
            
        priority = data.get("priority", 0)
        metadata = data.get("metadata", {})
        
        # 生成任务ID
        task_id = data.get("id", str(uuid.uuid4()))
        
        # 创建任务
        task = Task(task_id, coroutine, priority, metadata)
        
        # 添加到队列
        await self.task_queue.put((task.priority, task))
        self.tasks[task_id] = task
        
        logger.debug(f"添加任务: {task_id}, 优先级: {priority}")
        
        return {"success": True, "task_id": task_id}
    
    async def _handle_task_cancel(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """
        处理取消任务事件
        
        Args:
            data: 事件数据
            
        Returns:
            Dict[str, Any]: 取消结果
        """
        task_id = data.get("task_id")
        if not task_id or task_id not in self.tasks:
            return {"success": False, "error": f"任务不存在: {task_id}"}
            
        task = self.tasks[task_id]
        
        # 检查任务状态
        if task.status == "running":
            logger.warning(f"任务 {task_id} 正在运行，无法取消")
            return {"success": False, "error": "任务正在运行，无法取消"}
            
        if task.status in ("completed", "failed", "cancelled"):
            logger.warning(f"任务 {task_id} 已经完成或取消，无需再次取消")
            return {"success": True, "message": "任务已经完成或取消"}
            
        # 标记为取消状态
        task.status = "cancelled"
        logger.debug(f"取消任务: {task_id}")
        
        # 从任务映射中移除
        # 注意：无法从优先级队列中移除特定任务，但我们标记了状态，工作线程会跳过它
        
        return {"success": True}
    
    async def _handle_task_get_status(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """
        处理获取任务状态事件
        
        Args:
            data: 事件数据
            
        Returns:
            Dict[str, Any]: 任务状态
        """
        task_id = data.get("task_id")
        if not task_id or task_id not in self.tasks:
            return {"success": False, "error": f"任务不存在: {task_id}"}
            
        task = self.tasks[task_id]
        
        # 构建状态信息
        status_info = {
            "id": task.id,
            "status": task.status,
            "priority": task.priority,
            "created_at": task.created_at,
            "started_at": task.started_at,
            "finished_at": task.finished_at,
            "duration": (task.finished_at - task.started_at) if task.finished_at and task.started_at else None,
            "metadata": task.metadata,
            "result": task.result,
            "error": task.error
        }
        
        return {"success": True, "task": status_info}
    
    async def _handle_task_get_all(self, data: Dict[str, Any] = None) -> Dict[str, Any]:
        """
        处理获取所有任务事件
        
        Args:
            data: 事件数据
            
        Returns:
            Dict[str, Any]: 所有任务信息
        """
        # 获取过滤条件
        filters = data.get("filters", {}) if data else {}
        status_filter = filters.get("status")
        
        # 收集任务信息
        tasks_info = []
        for task_id, task in self.tasks.items():
            # 应用过滤器
            if status_filter and task.status != status_filter:
                continue
                
            # 构建任务信息
            task_info = {
                "id": task.id,
                "status": task.status,
                "priority": task.priority,
                "created_at": task.created_at,
                "started_at": task.started_at,
                "finished_at": task.finished_at,
                "duration": (task.finished_at - task.started_at) if task.finished_at and task.started_at else None,
                "metadata": task.metadata
            }
            
            # 根据需要添加结果或错误信息
            if task.status == "completed" and task.result is not None:
                task_info["result"] = task.result
                
            if task.status == "failed" and task.error is not None:
                task_info["error"] = task.error
                
            tasks_info.append(task_info)
        
        # 按创建时间排序
        tasks_info.sort(key=lambda t: t["created_at"])
        
        return {"success": True, "tasks": tasks_info, "count": len(tasks_info)}
    
    async def _handle_app_shutdown(self, data: Dict[str, Any] = None) -> None:
        """
        处理应用关闭事件
        
        Args:
            data: 事件数据
        """
        await self.shutdown()
    
    async def _start_workers(self) -> None:
        """启动工作线程"""
        if self.is_running:
            logger.warning("工作线程已经在运行")
            return
            
        self.is_running = True
        self.should_stop = False
        
        # 创建工作线程
        self.workers = []
        for i in range(self.worker_count):
            worker = asyncio.create_task(self._worker_loop(i))
            self.workers.append(worker)
            
        logger.info(f"启动了 {self.worker_count} 个工作线程")
    
    async def _worker_loop(self, worker_id: int) -> None:
        """
        工作线程循环
        
        Args:
            worker_id: 工作线程ID
        """
        logger.debug(f"工作线程 {worker_id} 已启动")
        
        while not self.should_stop:
            try:
                # 从队列获取任务
                _, task = await self.task_queue.get()
                
                # 检查任务是否已取消
                if task.status == "cancelled":
                    logger.debug(f"跳过已取消的任务: {task.id}")
                    self.task_queue.task_done()
                    continue
                
                # 运行任务
                logger.debug(f"工作线程 {worker_id} 开始执行任务: {task.id}")
                task.status = "running"
                task.started_at = time.time()
                
                # 发布任务开始事件
                await self.event_bus.publish(events.TASK_STARTED, {"task_id": task.id})
                
                try:
                    # 执行协程
                    result = await task.coroutine
                    
                    # 更新任务状态
                    task.status = "completed"
                    task.result = result
                    task.finished_at = time.time()
                    
                    logger.debug(f"任务 {task.id} 执行成功")
                    
                    # 发布任务完成事件
                    await self.event_bus.publish(events.TASK_COMPLETED, {"task_id": task.id, "result": result})
                    
                except Exception as e:
                    # 更新任务状态
                    task.status = "failed"
                    task.error = str(e)
                    task.finished_at = time.time()
                    
                    logger.exception(f"任务 {task.id} 执行失败: {str(e)}")
                    
                    # 发布任务失败事件
                    await self.event_bus.publish(events.TASK_FAILED, {"task_id": task.id, "error": str(e)})
                
                finally:
                    # 标记任务完成
                    self.task_queue.task_done()
                    
            except asyncio.CancelledError:
                logger.info(f"工作线程 {worker_id} 被取消")
                break
                
            except Exception as e:
                logger.exception(f"工作线程 {worker_id} 出错: {str(e)}")
                # 短暂等待后继续
                await asyncio.sleep(1)
        
        logger.info(f"工作线程 {worker_id} 已停止")
    
    async def shutdown(self) -> None:
        """关闭插件"""
        logger.info("正在关闭任务队列插件...")
        
        if not self.is_running:
            logger.info("任务队列插件未运行")
            return
            
        # 标记停止
        self.should_stop = True
        
        # 等待所有任务完成
        if not self.task_queue.empty():
            logger.info("等待所有任务完成...")
            await self.task_queue.join()
            
        # 取消所有工作线程
        for worker in self.workers:
            worker.cancel()
            
        # 等待所有工作线程结束
        await asyncio.gather(*self.workers, return_exceptions=True)
        
        # 取消事件订阅
        self.event_bus.unsubscribe(events.TASK_ADD, self._handle_task_add)
        self.event_bus.unsubscribe(events.TASK_CANCEL, self._handle_task_cancel)
        self.event_bus.unsubscribe(events.TASK_GET_STATUS, self._handle_task_get_status)
        self.event_bus.unsubscribe(events.TASK_GET_ALL, self._handle_task_get_all)
        self.event_bus.unsubscribe(events.APP_SHUTDOWN, self._handle_app_shutdown)
        
        self.is_running = False
        self.workers = []
        logger.info("任务队列插件已关闭")
```

## 任务2.8：实现下载插件(DownloadPlugin)

下载插件负责从Telegram下载媒体文件。

```python
# tg_app/plugins/downloader/download_plugin.py
import os
import asyncio
import tempfile
from typing import Dict, Any, List, Optional, Union, Tuple

from pyrogram import Client
from pyrogram.types import Message
from pyrogram.errors import FloodWait

from tg_app.plugins.base import PluginBase
from tg_app.events import event_types as events
from tg_app.utils.logger import get_logger

# 获取日志记录器
logger = get_logger("download_plugin")

class DownloadPlugin(PluginBase):
    """
    下载插件，负责从Telegram下载媒体文件
    """
    
    def __init__(self, event_bus):
        """
        初始化下载插件
        
        Args:
            event_bus: 事件总线
        """
        super().__init__(event_bus)
        
        self.client = None
        
        # 定义插件元数据
        self.id = "download"
        self.name = "媒体下载插件"
        self.version = "1.0.0"
        self.description = "从Telegram下载媒体文件"
        self.dependencies = ["client", "task_queue"]
        
        # 下载目录
        self.download_dir = None
        
        # 活跃下载
        self.active_downloads = {}
    
    async def initialize(self) -> None:
        """初始化插件"""
        logger.info("正在初始化下载插件...")
        
        # 注册事件处理器
        self.event_bus.subscribe(events.MEDIA_DOWNLOAD, self._handle_media_download)
        self.event_bus.subscribe(events.MEDIA_DOWNLOAD_CANCEL, self._handle_media_download_cancel)
        self.event_bus.subscribe(events.MEDIA_DOWNLOAD_STATUS, self._handle_media_download_status)
        self.event_bus.subscribe(events.APP_SHUTDOWN, self._handle_app_shutdown)
        
        # 获取客户端实例
        response = await self.event_bus.publish_and_wait(
            events.CLIENT_GET_INSTANCE,
            timeout=5.0
        )
        
        if not response or not response.get("success", False) or not response.get("client"):
            logger.error("获取客户端实例失败")
            return
            
        self.client = response.get("client")
        
        # 获取配置
        config_response = await self.event_bus.publish_and_wait(
            events.CONFIG_GET_SECTION, 
            {"section": "download"},
            timeout=5.0
        )
        
        if config_response and config_response.get("success", False):
            config = config_response.get("data", {})
            self.download_dir = config.get("download_dir")
            
        # 如果没有配置下载目录，使用临时目录
        if not self.download_dir:
            self.download_dir = os.path.join(tempfile.gettempdir(), "tg_app_downloads")
            
        # 确保下载目录存在
        os.makedirs(self.download_dir, exist_ok=True)
        
        logger.info(f"下载插件初始化完成，下载目录: {self.download_dir}")
    
    async def _handle_media_download(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """
        处理媒体下载事件
        
        Args:
            data: 事件数据
            
        Returns:
            Dict[str, Any]: 下载结果
        """
        message = data.get("message")
        if not message:
            return {"success": False, "error": "未提供消息"}
            
        # 检查消息是否包含媒体
        if not message.media:
            return {"success": False, "error": "消息不包含媒体"}
            
        # 获取自定义文件名
        file_name = data.get("file_name")
        
        # 创建下载任务
        download_task = asyncio.create_task(self._download_media(message, file_name))
        
        # 将任务添加到任务队列
        response = await self.event_bus.publish_and_wait(
            events.TASK_ADD,
            {
                "coroutine": download_task,
                "priority": data.get("priority", 0),
                "metadata": {
                    "type": "media_download",
                    "message_id": message.id,
                    "chat_id": message.chat.id,
                    "media_type": self._get_media_type(message)
                }
            },
            timeout=5.0
        )
        
        if not response or not response.get("success", False):
            download_task.cancel()
            return {"success": False, "error": "添加下载任务失败"}
            
        task_id = response["task_id"]
        
        # 添加到活跃下载
        self.active_downloads[task_id] = {
            "message": message,
            "started_at": asyncio.get_event_loop().time(),
            "progress": 0,
            "status": "pending"
        }
        
        # 返回任务ID
        return {"success": True, "task_id": task_id}
    
    async def _handle_media_download_cancel(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """
        处理取消媒体下载事件
        
        Args:
            data: 事件数据
            
        Returns:
            Dict[str, Any]: 取消结果
        """
        task_id = data.get("task_id")
        if not task_id:
            return {"success": False, "error": "未提供任务ID"}
            
        # 取消任务
        response = await self.event_bus.publish_and_wait(
            events.TASK_CANCEL,
            {"task_id": task_id},
            timeout=5.0
        )
        
        if not response or not response.get("success", False):
            return {"success": False, "error": response.get("error", "取消任务失败")}
            
        # 从活跃下载中移除
        if task_id in self.active_downloads:
            del self.active_downloads[task_id]
            
        return {"success": True}
    
    async def _handle_media_download_status(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """
        处理获取媒体下载状态事件
        
        Args:
            data: 事件数据
            
        Returns:
            Dict[str, Any]: 下载状态
        """
        task_id = data.get("task_id")
        if not task_id:
            return {"success": False, "error": "未提供任务ID"}
            
        # 检查是否在活跃下载中
        if task_id not in self.active_downloads:
            # 尝试从任务队列获取状态
            response = await self.event_bus.publish_and_wait(
                events.TASK_GET_STATUS,
                {"task_id": task_id},
                timeout=5.0
            )
            
            if not response or not response.get("success", False):
                return {"success": False, "error": "任务不存在"}
                
            return response
            
        # 获取下载状态
        download_info = self.active_downloads[task_id]
        
        return {
            "success": True,
            "status": download_info["status"],
            "progress": download_info["progress"],
            "started_at": download_info["started_at"],
            "message_id": download_info["message"].id,
            "chat_id": download_info["message"].chat.id,
            "media_type": self._get_media_type(download_info["message"])
        }
    
    async def _handle_app_shutdown(self, data: Dict[str, Any] = None) -> None:
        """
        处理应用关闭事件
        
        Args:
            data: 事件数据
        """
        await self.shutdown()
    
    async def _download_media(self, message: Message, file_name: Optional[str] = None) -> Dict[str, Any]:
        """
        下载媒体文件
        
        Args:
            message: 包含媒体的消息
            file_name: 自定义文件名
            
        Returns:
            Dict[str, Any]: 下载结果
        """
        if not message.media:
            return {"success": False, "error": "消息不包含媒体"}
            
        # 生成唯一的文件名
        if not file_name:
            media_type = self._get_media_type(message)
            # 使用消息ID和聊天ID生成唯一文件名
            file_name = f"{message.chat.id}_{message.id}_{media_type}"
            
        # 确定文件扩展名
        file_ext = self._get_media_extension(message)
        if file_ext and not file_name.endswith(file_ext):
            file_name = f"{file_name}{file_ext}"
            
        # 完整的文件路径
        file_path = os.path.join(self.download_dir, file_name)
        
        # 更新进度回调
        task_id = asyncio.current_task().get_name()
        
        async def progress_callback(current, total):
            if total > 0:
                progress = current / total
            else:
                progress = 0
                
            # 更新活跃下载信息
            if task_id in self.active_downloads:
                self.active_downloads[task_id]["progress"] = progress
                self.active_downloads[task_id]["status"] = "downloading"
                
            # 发布进度事件
            await self.event_bus.publish(events.MEDIA_DOWNLOAD_PROGRESS, {
                "task_id": task_id,
                "current": current,
                "total": total,
                "progress": progress
            })
        
        try:
            logger.info(f"开始下载消息 {message.id} 的媒体到 {file_path}")
            
            # 下载媒体
            downloaded_file = await message.download(
                file_name=file_path,
                progress=progress_callback
            )
            
            if not downloaded_file:
                logger.error(f"下载消息 {message.id} 的媒体失败")
                return {"success": False, "error": "下载失败"}
                
            # 获取媒体信息
            media_info = self._extract_media_info(message)
            media_info["file_path"] = downloaded_file
            media_info["file_name"] = os.path.basename(downloaded_file)
            media_info["file_size"] = os.path.getsize(downloaded_file)
            
            logger.info(f"下载消息 {message.id} 的媒体成功: {downloaded_file}")
            
            # 更新活跃下载状态
            if task_id in self.active_downloads:
                self.active_downloads[task_id]["status"] = "completed"
                self.active_downloads[task_id]["progress"] = 1.0
                
            # 发布下载完成事件
            await self.event_bus.publish(events.MEDIA_DOWNLOAD_COMPLETED, {
                "task_id": task_id,
                "media_info": media_info,
                "message_id": message.id,
                "chat_id": message.chat.id
            })
            
            return {"success": True, "media_info": media_info}
            
        except FloodWait as e:
            logger.warning(f"下载受限，等待 {e.value} 秒")
            
            # 更新活跃下载状态
            if task_id in self.active_downloads:
                self.active_downloads[task_id]["status"] = "waiting"
                
            # 等待
            await asyncio.sleep(e.value)
            
            # 重试
            return await self._download_media(message, file_name)
            
        except Exception as e:
            error_msg = f"下载消息 {message.id} 的媒体时出错: {str(e)}"
            logger.exception(error_msg)
            
            # 更新活跃下载状态
            if task_id in self.active_downloads:
                self.active_downloads[task_id]["status"] = "failed"
                
            # 发布下载失败事件
            await self.event_bus.publish(events.MEDIA_DOWNLOAD_FAILED, {
                "task_id": task_id,
                "message_id": message.id,
                "chat_id": message.chat.id,
                "error": str(e)
            })
            
            return {"success": False, "error": str(e)}
    
    def _get_media_type(self, message: Message) -> str:
        """
        获取消息的媒体类型
        
        Args:
            message: 消息对象
            
        Returns:
            str: 媒体类型
        """
        if message.photo:
            return "photo"
        elif message.video:
            return "video"
        elif message.audio:
            return "audio"
        elif message.document:
            return "document"
        elif message.animation:
            return "animation"
        elif message.sticker:
            return "sticker"
        elif message.voice:
            return "voice"
        elif message.video_note:
            return "video_note"
        else:
            return "unknown"
    
    def _get_media_extension(self, message: Message) -> Optional[str]:
        """
        获取媒体文件的扩展名
        
        Args:
            message: 消息对象
            
        Returns:
            Optional[str]: 扩展名
        """
        media_type = self._get_media_type(message)
        
        if media_type == "photo":
            return ".jpg"
        elif media_type == "video":
            return ".mp4"
        elif media_type == "audio":
            if message.audio and message.audio.mime_type:
                if "mp3" in message.audio.mime_type:
                    return ".mp3"
                elif "ogg" in message.audio.mime_type:
                    return ".ogg"
                elif "m4a" in message.audio.mime_type:
                    return ".m4a"
            return ".mp3"
        elif media_type == "voice":
            return ".ogg"
        elif media_type == "document" and message.document and message.document.file_name:
            # 从文件名中提取扩展名
            file_name = message.document.file_name
            if "." in file_name:
                return file_name[file_name.rindex("."):]
        elif media_type == "animation":
            return ".mp4"
        elif media_type == "sticker":
            if message.sticker and message.sticker.is_animated:
                return ".tgs"
            elif message.sticker and message.sticker.is_video:
                return ".webm"
            return ".webp"
        elif media_type == "video_note":
            return ".mp4"
            
        return None
    
    def _extract_media_info(self, message: Message) -> Dict[str, Any]:
        """
        提取媒体信息
        
        Args:
            message: 消息对象
            
        Returns:
            Dict[str, Any]: 媒体信息
        """
        media_type = self._get_media_type(message)
        media_info = {
            "media_type": media_type,
            "message_id": message.id,
            "chat_id": message.chat.id,
            "caption": message.caption,
            "caption_entities": message.caption_entities
        }
        
        # 根据媒体类型提取特定信息
        if media_type == "photo":
            # 获取最大分辨率的照片
            photo = message.photo[-1]
            media_info.update({
                "file_id": photo.file_id,
                "file_unique_id": photo.file_unique_id,
                "width": photo.width,
                "height": photo.height,
                "file_size": photo.file_size
            })
        elif media_type == "video":
            video = message.video
            media_info.update({
                "file_id": video.file_id,
                "file_unique_id": video.file_unique_id,
                "width": video.width,
                "height": video.height,
                "duration": video.duration,
                "file_size": video.file_size,
                "mime_type": video.mime_type,
                "supports_streaming": video.supports_streaming,
                "has_thumbnail": bool(video.thumbs)
            })
        elif media_type == "audio":
            audio = message.audio
            media_info.update({
                "file_id": audio.file_id,
                "file_unique_id": audio.file_unique_id,
                "duration": audio.duration,
                "performer": audio.performer,
                "title": audio.title,
                "file_size": audio.file_size,
                "mime_type": audio.mime_type,
                "has_thumbnail": bool(audio.thumbs)
            })
        elif media_type == "document":
            document = message.document
            media_info.update({
                "file_id": document.file_id,
                "file_unique_id": document.file_unique_id,
                "file_name": document.file_name,
                "file_size": document.file_size,
                "mime_type": document.mime_type,
                "has_thumbnail": bool(document.thumbs)
            })
        elif media_type == "animation":
            animation = message.animation
            media_info.update({
                "file_id": animation.file_id,
                "file_unique_id": animation.file_unique_id,
                "width": animation.width,
                "height": animation.height,
                "duration": animation.duration,
                "file_size": animation.file_size,
                "mime_type": animation.mime_type,
                "file_name": animation.file_name,
                "has_thumbnail": bool(animation.thumbs)
            })
        elif media_type == "sticker":
            sticker = message.sticker
            media_info.update({
                "file_id": sticker.file_id,
                "file_unique_id": sticker.file_unique_id,
                "width": sticker.width,
                "height": sticker.height,
                "is_animated": sticker.is_animated,
                "is_video": sticker.is_video,
                "file_size": sticker.file_size,
                "emoji": sticker.emoji
            })
        elif media_type == "voice":
            voice = message.voice
            media_info.update({
                "file_id": voice.file_id,
                "file_unique_id": voice.file_unique_id,
                "duration": voice.duration,
                "file_size": voice.file_size,
                "mime_type": voice.mime_type
            })
        elif media_type == "video_note":
            video_note = message.video_note
            media_info.update({
                "file_id": video_note.file_id,
                "file_unique_id": video_note.file_unique_id,
                "duration": video_note.duration,
                "length": video_note.length,
                "file_size": video_note.file_size,
                "has_thumbnail": bool(video_note.thumbs)
            })
            
        return media_info
    
    async def shutdown(self) -> None:
        """关闭插件"""
        logger.info("正在关闭下载插件...")
        
        # 取消事件订阅
        self.event_bus.unsubscribe(events.MEDIA_DOWNLOAD, self._handle_media_download)
        self.event_bus.unsubscribe(events.MEDIA_DOWNLOAD_CANCEL, self._handle_media_download_cancel)
        self.event_bus.unsubscribe(events.MEDIA_DOWNLOAD_STATUS, self._handle_media_download_status)
        self.event_bus.unsubscribe(events.APP_SHUTDOWN, self._handle_app_shutdown)
        
        self.client = None
        logger.info("下载插件已关闭")
```

## 开发说明

1. **任务队列插件**:
   - 实现了一个灵活的异步任务队列系统
   - 支持任务优先级、状态跟踪和取消操作
   - 使用多个工作线程并行处理任务
   - 提供全面的任务状态查询功能

2. **下载插件**:
   - 实现了媒体文件下载功能
   - 支持所有Telegram媒体类型
   - 提供下载进度跟踪和状态查询
   - 通过任务队列管理并发下载
   - 详细的媒体信息提取和错误处理 