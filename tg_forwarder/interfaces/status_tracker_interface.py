"""
状态跟踪接口抽象
定义了跟踪消息转发状态的必要方法
"""

from abc import ABC, abstractmethod
from typing import Dict, Any, List, Union, Optional
from datetime import datetime


class StatusTrackerInterface(ABC):
    """
    状态跟踪接口，定义了跟踪消息转发状态的必要方法
    所有状态跟踪器实现都应该继承此接口
    """
    
    @abstractmethod
    def initialize(self) -> bool:
        """
        初始化状态跟踪器
        
        Returns:
            bool: 初始化是否成功
        """
        pass
    
    @abstractmethod
    def shutdown(self) -> None:
        """关闭状态跟踪器，释放资源"""
        pass
    
    @abstractmethod
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
        pass
    
    @abstractmethod
    def record_download_complete(self, task_id: str, file_path: str) -> None:
        """
        记录下载完成
        
        Args:
            task_id: 任务ID
            file_path: 下载文件路径
        """
        pass
    
    @abstractmethod
    def record_download_failed(self, task_id: str, error: str) -> None:
        """
        记录下载失败
        
        Args:
            task_id: 任务ID
            error: 错误信息
        """
        pass
    
    @abstractmethod
    def record_upload_start(self, task_id: str, target_chat_id: Union[str, int]) -> None:
        """
        记录开始上传消息
        
        Args:
            task_id: 任务ID
            target_chat_id: 目标聊天ID
        """
        pass
    
    @abstractmethod
    def record_upload_complete(self, task_id: str, target_chat_id: Union[str, int], 
                              target_message_id: int) -> None:
        """
        记录上传完成
        
        Args:
            task_id: 任务ID
            target_chat_id: 目标聊天ID
            target_message_id: 目标消息ID
        """
        pass
    
    @abstractmethod
    def record_upload_failed(self, task_id: str, target_chat_id: Union[str, int], 
                           error: str) -> None:
        """
        记录上传失败
        
        Args:
            task_id: 任务ID
            target_chat_id: 目标聊天ID
            error: 错误信息
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
    def get_pending_tasks(self) -> List[Dict[str, Any]]:
        """
        获取未完成的任务
        
        Returns:
            List[Dict[str, Any]]: 未完成任务列表
        """
        pass
    
    @abstractmethod
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
        pass 