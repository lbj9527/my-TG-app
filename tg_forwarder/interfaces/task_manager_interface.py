"""
任务管理器接口抽象
定义了任务调度和管理的必要方法
"""

from abc import ABC, abstractmethod
from typing import Dict, Any, List, Union, Optional, Callable
from concurrent.futures import Future


class TaskManagerInterface(ABC):
    """
    任务管理器接口，定义了任务调度和管理的必要方法
    所有任务管理器实现都应该继承此接口
    """
    
    @abstractmethod
    def initialize(self, max_workers: int = 5) -> bool:
        """
        初始化任务管理器
        
        Args:
            max_workers: 最大工作线程数
            
        Returns:
            bool: 初始化是否成功
        """
        pass
    
    @abstractmethod
    def shutdown(self, wait: bool = True) -> None:
        """
        关闭任务管理器
        
        Args:
            wait: 是否等待所有任务完成
        """
        pass
    
    @abstractmethod
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
        pass
    
    @abstractmethod
    def cancel_task(self, task_id: str) -> bool:
        """
        取消任务
        
        Args:
            task_id: 任务ID
            
        Returns:
            bool: 是否成功取消
        """
        pass
    
    @abstractmethod
    def get_task_status(self, task_id: str) -> Dict[str, Any]:
        """
        获取任务状态
        
        Args:
            task_id: 任务ID
            
        Returns:
            Dict[str, Any]: 任务状态信息
        """
        pass
    
    @abstractmethod
    def get_all_tasks(self) -> Dict[str, Dict[str, Any]]:
        """
        获取所有任务
        
        Returns:
            Dict[str, Dict[str, Any]]: 所有任务状态
        """
        pass
    
    @abstractmethod
    def get_active_tasks(self) -> Dict[str, Dict[str, Any]]:
        """
        获取活动任务
        
        Returns:
            Dict[str, Dict[str, Any]]: 活动任务状态
        """
        pass
    
    @abstractmethod
    def pause_queue(self, queue_name: Optional[str] = None) -> None:
        """
        暂停任务队列
        
        Args:
            queue_name: 队列名称，为None时暂停所有队列
        """
        pass
    
    @abstractmethod
    def resume_queue(self, queue_name: Optional[str] = None) -> None:
        """
        恢复任务队列
        
        Args:
            queue_name: 队列名称，为None时恢复所有队列
        """
        pass
    
    @abstractmethod
    def add_task_completion_callback(self, task_id: str, callback: Callable[[str, Any], None]) -> None:
        """
        添加任务完成回调
        
        Args:
            task_id: 任务ID
            callback: 回调函数，接收任务ID和结果
        """
        pass 