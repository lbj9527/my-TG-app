"""
任务管理器实现类
负责任务调度和管理
"""

import uuid
import time
import threading
import asyncio
from typing import Dict, Any, List, Union, Optional, Callable, Tuple
from concurrent.futures import ThreadPoolExecutor, Future, CancelledError
from queue import Queue, Empty
from datetime import datetime

from tg_forwarder.interfaces.task_manager_interface import TaskManagerInterface
from tg_forwarder.interfaces.logger_interface import LoggerInterface


class TaskError(Exception):
    """任务执行错误"""
    pass


class TaskManager(TaskManagerInterface):
    """
    任务管理器，实现TaskManagerInterface接口
    负责管理和调度异步任务执行
    """
    
    def __init__(self, logger: LoggerInterface):
        """
        初始化任务管理器
        
        Args:
            logger: 日志接口实例
        """
        self._logger = logger.get_logger("TaskManager")
        self._executor = None
        self._tasks = {}  # 任务字典: {task_id: task_info}
        self._callbacks = {}  # 回调字典: {task_id: [callbacks]}
        self._task_lock = threading.RLock()  # 任务字典锁
        
        # 任务队列和队列状态
        self._queues = {}  # 队列字典: {queue_name: Queue}
        self._queue_status = {}  # 队列状态: {queue_name: "running" | "paused"}
        self._queue_workers = {}  # 队列工作线程: {queue_name: Thread}
        
        self._initialized = False
        self._shutdown_event = threading.Event()
    
    def initialize(self, max_workers: int = 5) -> bool:
        """
        初始化任务管理器
        
        Args:
            max_workers: 最大工作线程数
            
        Returns:
            bool: 初始化是否成功
        """
        try:
            # 创建线程池
            self._executor = ThreadPoolExecutor(max_workers=max_workers)
            
            # 创建默认队列
            self._create_queue("default")
            
            self._initialized = True
            self._shutdown_event.clear()
            
            self._logger.info(f"任务管理器初始化完成，最大工作线程: {max_workers}")
            return True
        except Exception as e:
            self._logger.error(f"初始化任务管理器失败: {str(e)}", exc_info=True)
            self._initialized = False
            return False
    
    def shutdown(self, wait: bool = True) -> None:
        """
        关闭任务管理器
        
        Args:
            wait: 是否等待所有任务完成
        """
        if not self._initialized:
            return
        
        self._logger.info("正在关闭任务管理器...")
        self._shutdown_event.set()
        
        # 停止所有队列工作线程
        for queue_name, worker in self._queue_workers.items():
            self._logger.debug(f"正在停止队列工作线程: {queue_name}")
            self._queue_status[queue_name] = "paused"
            if worker.is_alive():
                worker.join(timeout=5.0 if wait else 0.1)
        
        # 关闭执行器
        if self._executor:
            self._executor.shutdown(wait=wait)
            self._executor = None
        
        # 清理任务信息
        with self._task_lock:
            cancelled_tasks = []
            for task_id, task_info in self._tasks.items():
                if task_info.get("status") in ["pending", "running"]:
                    task_info["status"] = "cancelled"
                    task_info["finished_at"] = datetime.now().isoformat()
                    task_info["error"] = "任务管理器关闭"
                    cancelled_tasks.append(task_id)
            
            if cancelled_tasks:
                self._logger.warning(f"取消了 {len(cancelled_tasks)} 个未完成任务")
        
        self._initialized = False
        self._logger.info("任务管理器已关闭")
    
    def submit_task(self, task_type: str, func: Callable, *args, **kwargs) -> str:
        """
        提交任务
        
        Args:
            task_type: 任务类型
            func: 要执行的函数
            *args: 函数参数
            **kwargs: 函数关键字参数
            
        Returns:
            str: 任务ID
        """
        if not self._initialized:
            raise TaskError("任务管理器未初始化")
        
        # 从关键字参数中提取特殊配置
        queue_name = kwargs.pop("_queue", "default")
        priority = kwargs.pop("_priority", 0)
        task_name = kwargs.pop("_name", f"{task_type}-task")
        
        # 确保队列存在
        if queue_name not in self._queues:
            self._create_queue(queue_name)
        
        # 生成任务ID
        task_id = str(uuid.uuid4())
        
        # 创建任务信息
        task_info = {
            "task_id": task_id,
            "name": task_name,
            "type": task_type,
            "queue": queue_name,
            "priority": priority,
            "status": "pending",
            "created_at": datetime.now().isoformat(),
            "started_at": None,
            "finished_at": None,
            "result": None,
            "error": None
        }
        
        # 创建任务封装
        task_item = {
            "id": task_id,
            "func": func,
            "args": args,
            "kwargs": kwargs,
            "info": task_info
        }
        
        # 保存任务信息
        with self._task_lock:
            self._tasks[task_id] = task_info
        
        # 将任务放入队列
        self._queues[queue_name].put((priority, task_item))
        
        self._logger.debug(f"提交任务: id={task_id}, type={task_type}, queue={queue_name}")
        return task_id
    
    def cancel_task(self, task_id: str) -> bool:
        """
        取消任务
        
        Args:
            task_id: 任务ID
            
        Returns:
            bool: 是否成功取消
        """
        if not self._initialized:
            return False
        
        with self._task_lock:
            if task_id not in self._tasks:
                self._logger.warning(f"取消任务失败: 找不到任务 {task_id}")
                return False
            
            task_info = self._tasks[task_id]
            
            # 如果任务已完成或已取消，无法再取消
            if task_info["status"] in ["completed", "failed", "cancelled"]:
                self._logger.warning(f"无法取消任务 {task_id}: 当前状态为 {task_info['status']}")
                return False
            
            # 如果任务正在运行，尝试取消Future
            if task_info["status"] == "running" and "future" in task_info:
                future = task_info["future"]
                cancelled = future.cancel()
                if not cancelled:
                    self._logger.warning(f"无法取消正在运行的任务 {task_id}")
                    return False
            
            # 更新任务状态
            task_info["status"] = "cancelled"
            task_info["finished_at"] = datetime.now().isoformat()
            task_info["error"] = "任务被用户取消"
            
            self._logger.info(f"已取消任务: {task_id}")
            return True
    
    def get_task_status(self, task_id: str) -> Dict[str, Any]:
        """
        获取任务状态
        
        Args:
            task_id: 任务ID
            
        Returns:
            Dict[str, Any]: 任务状态信息
        """
        if not self._initialized:
            return {"error": "任务管理器未初始化"}
        
        with self._task_lock:
            if task_id not in self._tasks:
                return {"error": f"找不到任务: {task_id}"}
            
            # 返回任务信息的副本
            return dict(self._tasks[task_id])
    
    def get_all_tasks(self) -> Dict[str, Dict[str, Any]]:
        """
        获取所有任务
        
        Returns:
            Dict[str, Dict[str, Any]]: 所有任务状态
        """
        if not self._initialized:
            return {}
        
        with self._task_lock:
            # 返回所有任务信息的副本
            return {task_id: dict(task_info) for task_id, task_info in self._tasks.items()}
    
    def get_active_tasks(self) -> Dict[str, Dict[str, Any]]:
        """
        获取活动任务
        
        Returns:
            Dict[str, Dict[str, Any]]: 活动任务状态
        """
        if not self._initialized:
            return {}
        
        with self._task_lock:
            # 筛选活动任务
            active_tasks = {
                task_id: dict(task_info)
                for task_id, task_info in self._tasks.items()
                if task_info["status"] in ["pending", "running"]
            }
            return active_tasks
    
    def pause_queue(self, queue_name: Optional[str] = None) -> None:
        """
        暂停任务队列
        
        Args:
            queue_name: 队列名称，为None时暂停所有队列
        """
        if not self._initialized:
            return
        
        if queue_name is None:
            # 暂停所有队列
            for q_name in self._queue_status:
                self._queue_status[q_name] = "paused"
            self._logger.info("已暂停所有任务队列")
        elif queue_name in self._queue_status:
            # 暂停指定队列
            self._queue_status[queue_name] = "paused"
            self._logger.info(f"已暂停任务队列: {queue_name}")
        else:
            self._logger.warning(f"无法暂停队列: 找不到队列 {queue_name}")
    
    def resume_queue(self, queue_name: Optional[str] = None) -> None:
        """
        恢复任务队列
        
        Args:
            queue_name: 队列名称，为None时恢复所有队列
        """
        if not self._initialized:
            return
        
        if queue_name is None:
            # 恢复所有队列
            for q_name in self._queue_status:
                self._queue_status[q_name] = "running"
            self._logger.info("已恢复所有任务队列")
        elif queue_name in self._queue_status:
            # 恢复指定队列
            self._queue_status[queue_name] = "running"
            self._logger.info(f"已恢复任务队列: {queue_name}")
        else:
            self._logger.warning(f"无法恢复队列: 找不到队列 {queue_name}")
    
    def add_task_completion_callback(self, task_id: str, callback: Callable[[str, Any], None]) -> None:
        """
        添加任务完成回调
        
        Args:
            task_id: 任务ID
            callback: 回调函数，接收任务ID和结果
        """
        if not self._initialized:
            return
        
        with self._task_lock:
            if task_id not in self._tasks:
                self._logger.warning(f"无法添加回调: 找不到任务 {task_id}")
                return
            
            # 初始化回调列表
            if task_id not in self._callbacks:
                self._callbacks[task_id] = []
            
            # 添加回调
            self._callbacks[task_id].append(callback)
            
            # 如果任务已完成，立即执行回调
            task_info = self._tasks[task_id]
            if task_info["status"] in ["completed", "failed", "cancelled"]:
                result = task_info.get("result")
                error = task_info.get("error")
                
                try:
                    callback(task_id, result if task_info["status"] == "completed" else error)
                except Exception as e:
                    self._logger.error(f"执行回调函数失败: {str(e)}", exc_info=True)
    
    def _create_queue(self, queue_name: str) -> None:
        """
        创建新的任务队列
        
        Args:
            queue_name: 队列名称
        """
        if queue_name in self._queues:
            return
        
        # 创建优先级队列
        self._queues[queue_name] = Queue()
        self._queue_status[queue_name] = "running"
        
        # 创建队列工作线程
        worker_thread = threading.Thread(
            target=self._queue_worker,
            args=(queue_name,),
            name=f"TaskManager-{queue_name}-worker",
            daemon=True
        )
        
        self._queue_workers[queue_name] = worker_thread
        worker_thread.start()
        
        self._logger.debug(f"创建任务队列: {queue_name}")
    
    def _queue_worker(self, queue_name: str) -> None:
        """
        队列工作线程
        
        Args:
            queue_name: 队列名称
        """
        queue = self._queues[queue_name]
        
        self._logger.debug(f"队列工作线程 {queue_name} 已启动")
        
        while not self._shutdown_event.is_set():
            # 检查队列状态
            if self._queue_status.get(queue_name) == "paused":
                time.sleep(0.1)
                continue
            
            try:
                # 获取任务，有0.5秒超时以便检查关闭事件
                try:
                    _, task_item = queue.get(timeout=0.5)
                except Empty:
                    continue
                
                # 执行任务
                self._execute_task(task_item)
                
                # 标记任务完成
                queue.task_done()
                
            except Exception as e:
                self._logger.error(f"队列工作线程 {queue_name} 处理任务时出错: {str(e)}", exc_info=True)
                time.sleep(1)  # 防止错误循环过快
        
        self._logger.debug(f"队列工作线程 {queue_name} 已停止")
    
    def _execute_task(self, task_item: Dict[str, Any]) -> None:
        """
        执行任务
        
        Args:
            task_item: 任务项
        """
        task_id = task_item["id"]
        func = task_item["func"]
        args = task_item["args"]
        kwargs = task_item["kwargs"]
        task_info = task_item["info"]
        
        # 更新任务状态为运行中
        with self._task_lock:
            if task_id in self._tasks:
                self._tasks[task_id]["status"] = "running"
                self._tasks[task_id]["started_at"] = datetime.now().isoformat()
        
        # 提交到线程池执行
        self._logger.debug(f"开始执行任务: {task_id}")
        
        future = self._executor.submit(self._wrapped_task, func, args, kwargs)
        
        # 存储future对象
        with self._task_lock:
            if task_id in self._tasks:
                self._tasks[task_id]["future"] = future
        
        # 添加完成回调
        future.add_done_callback(
            lambda f: self._handle_task_completion(task_id, f)
        )
    
    def _wrapped_task(self, func: Callable, args: Tuple, kwargs: Dict[str, Any]) -> Any:
        """
        包装任务函数以捕获异常
        
        Args:
            func: 要执行的函数
            args: 函数参数
            kwargs: 函数关键字参数
            
        Returns:
            Any: 函数结果
            
        Raises:
            TaskError: 任务执行错误
        """
        try:
            # 判断是否是协程函数
            if asyncio.iscoroutinefunction(func):
                # 创建新的事件循环
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                try:
                    # 执行协程函数
                    return loop.run_until_complete(func(*args, **kwargs))
                finally:
                    loop.close()
            else:
                # 执行普通函数
                return func(*args, **kwargs)
        except Exception as e:
            self._logger.error(f"任务执行失败: {str(e)}", exc_info=True)
            raise TaskError(f"{type(e).__name__}: {str(e)}")
    
    def _handle_task_completion(self, task_id: str, future: Future) -> None:
        """
        处理任务完成
        
        Args:
            task_id: 任务ID
            future: Future对象
        """
        try:
            # 获取结果或异常
            error = None
            result = None
            status = "completed"
            
            try:
                result = future.result()
            except CancelledError:
                status = "cancelled"
                error = "任务被取消"
            except Exception as e:
                status = "failed"
                error = str(e)
            
            # 更新任务状态
            finished_at = datetime.now().isoformat()
            
            with self._task_lock:
                if task_id in self._tasks:
                    self._tasks[task_id]["status"] = status
                    self._tasks[task_id]["finished_at"] = finished_at
                    
                    if status == "completed":
                        self._tasks[task_id]["result"] = result
                    else:
                        self._tasks[task_id]["error"] = error
                    
                    # 移除future引用
                    if "future" in self._tasks[task_id]:
                        del self._tasks[task_id]["future"]
            
            # 记录日志
            if status == "completed":
                self._logger.debug(f"任务完成: {task_id}")
            elif status == "cancelled":
                self._logger.info(f"任务取消: {task_id}")
            else:
                self._logger.warning(f"任务失败: {task_id}, 错误: {error}")
            
            # 执行回调
            if task_id in self._callbacks:
                callbacks = self._callbacks[task_id]
                for callback in callbacks:
                    try:
                        callback(task_id, result if status == "completed" else error)
                    except Exception as e:
                        self._logger.error(f"执行回调函数失败: {str(e)}", exc_info=True)
            
        except Exception as e:
            self._logger.error(f"处理任务完成时出错: {str(e)}", exc_info=True) 