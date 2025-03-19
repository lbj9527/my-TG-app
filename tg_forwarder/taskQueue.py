"""
任务队列管理模块，采用生产者-消费者模式处理任务
"""

import asyncio
from typing import Dict, Any, List, Callable, Awaitable, Optional, Union
import time
from concurrent.futures import ThreadPoolExecutor

from tg_forwarder.logModule.logger import get_logger

# 获取日志记录器
logger = get_logger("task_queue")

class TaskQueue:
    """任务队列类，基于生产者-消费者模式"""
    
    def __init__(self, max_queue_size: int = 5, max_workers: int = 3):
        """
        初始化任务队列
        
        Args:
            max_queue_size: 最大队列大小
            max_workers: 最大消费者数量
        """
        self.queue = asyncio.Queue(maxsize=max_queue_size)
        self.max_workers = max_workers
        self.stats = {
            "enqueued": 0,  # 入队总数
            "dequeued": 0,  # 出队总数
            "completed": 0, # 成功完成数
            "failed": 0,    # 失败数
            "start_time": 0,
            "end_time": 0
        }
        self.consumer_tasks = []
        self.producer_task = None
        self.is_running = False
    
    async def put(self, item: Any) -> None:
        """
        将任务添加到队列
        
        Args:
            item: 要添加的任务
        """
        await self.queue.put(item)
        self.stats["enqueued"] += 1
    
    async def run(self, producer_func: Callable[[], Awaitable[None]], 
                 consumer_func: Callable[[Any], Awaitable[bool]]) -> Dict[str, Any]:
        """
        运行任务队列
        
        Args:
            producer_func: 生产者函数，负责将任务添加到队列
            consumer_func: 消费者函数，处理从队列中取出的任务
        
        Returns:
            Dict[str, Any]: 任务统计信息
        """
        self.is_running = True
        self.stats["start_time"] = time.time()
        
        # 创建并启动生产者任务
        self.producer_task = asyncio.create_task(self._producer_wrapper(producer_func))
        
        # 创建并启动消费者任务
        self.consumer_tasks = []
        for i in range(self.max_workers):
            consumer_id = i + 1
            consumer_task = asyncio.create_task(self._consumer_wrapper(consumer_func, consumer_id))
            self.consumer_tasks.append(consumer_task)
            logger.info(f"消费者 #{consumer_id} 开始运行...")
        
        try:
            # 等待生产者和消费者完成
            await self.producer_task
            logger.info("生产者任务已完成")
            
            # 向每个消费者发送结束信号
            for _ in range(len(self.consumer_tasks)):
                await self.queue.put(None)
            
            # 等待所有消费者处理完毕
            await asyncio.gather(*self.consumer_tasks)
            logger.info("所有消费者任务已完成")
            
        except Exception as e:
            logger.error(f"任务队列执行错误: {str(e)}")
            logger.exception("错误详情:")
            
            # 取消所有未完成的任务
            if not self.producer_task.done():
                self.producer_task.cancel()
            
            for task in self.consumer_tasks:
                if not task.done():
                    task.cancel()
        
        finally:
            self.is_running = False
            self.stats["end_time"] = time.time()
            duration = self.stats["end_time"] - self.stats["start_time"]
            
            # 生成任务统计
            logger.info(f"任务队列统计: 入队 {self.stats['enqueued']}, 出队 {self.stats['dequeued']}, " +
                      f"完成 {self.stats['completed']}, 失败 {self.stats['failed']}, " +
                      f"耗时 {duration:.2f}秒")
            
            return self.stats
    
    async def _producer_wrapper(self, producer_func: Callable[[], Awaitable[None]]) -> None:
        """
        生产者包装函数，调用生产者并处理异常
        
        Args:
            producer_func: 生产者函数
        """
        try:
            logger.info("生产者开始运行...")
            await producer_func()
        except asyncio.CancelledError:
            logger.warning("生产者任务被取消")
        except Exception as e:
            logger.error(f"生产者任务出错: {str(e)}")
            logger.exception("错误详情:")
        finally:
            logger.info(f"生产者完成任务，已入队 {self.stats['enqueued']} 项")
    
    async def _consumer_wrapper(self, consumer_func: Callable[[Any], Awaitable[bool]], consumer_id: int) -> None:
        """
        消费者包装函数，从队列获取任务并处理
        
        Args:
            consumer_func: 消费者函数
            consumer_id: 消费者ID
        """
        while self.is_running:
            try:
                # 从队列获取任务
                item = await self.queue.get()
                
                # 判断是否为结束信号
                if item is None:
                    logger.info(f"消费者 #{consumer_id} 收到结束信号")
                    self.queue.task_done()
                    break
                
                # 处理任务
                self.stats["dequeued"] += 1
                result = await consumer_func(item)
                
                # 更新统计信息
                if result is False:
                    self.stats["failed"] += 1
                else:
                    self.stats["completed"] += 1
                
                # 标记任务完成
                self.queue.task_done()
                
            except asyncio.CancelledError:
                logger.warning(f"消费者 #{consumer_id} 被取消")
                break
            except Exception as e:
                logger.error(f"消费者 #{consumer_id} 处理任务时出错: {str(e)}")
                logger.exception("错误详情:")
                self.stats["failed"] += 1
                # 确保队列任务被标记为完成，避免阻塞
                try:
                    self.queue.task_done()
                except:
                    pass
        
        logger.info(f"消费者 #{consumer_id} 完成所有任务")
    
    async def shutdown(self) -> None:
        """安全关闭任务队列，取消所有任务"""
        self.is_running = False
        
        # 取消所有消费者任务
        for task in self.consumer_tasks:
            if not task.done():
                task.cancel()
        
        # 取消生产者任务
        if self.producer_task and not self.producer_task.done():
            self.producer_task.cancel()
        
        # 等待队列中的所有任务被处理完毕
        try:
            if hasattr(self.queue, '_unfinished_tasks') and self.queue._unfinished_tasks > 0:
                logger.info(f"等待队列中的 {self.queue._unfinished_tasks} 个任务完成...")
                await asyncio.wait_for(self.queue.join(), timeout=5.0)
                logger.info("队列中所有任务已处理完成")
        except asyncio.TimeoutError:
            logger.warning("等待队列任务完成超时")
        except Exception as e:
            logger.error(f"关闭队列时出错: {str(e)}")
            logger.exception("错误详情:")
    
    async def start(self, producer_func: Callable[[], Awaitable[None]], 
                   consumer_func: Callable[[Any], Awaitable[Any]], 
                   num_consumers: int = 3) -> Dict[str, Any]:
        """
        启动任务队列（兼容旧接口）
        
        Args:
            producer_func: 生产者函数
            consumer_func: 消费者函数
            num_consumers: 消费者数量
        
        Returns:
            Dict[str, Any]: 任务统计信息
        """
        if num_consumers != self.max_workers:
            self.max_workers = num_consumers
        
        return await self.run(producer_func, consumer_func) 