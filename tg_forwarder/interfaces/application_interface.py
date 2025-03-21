"""
应用程序接口抽象
定义了应用程序的主要功能和组件协调方法
"""

from abc import ABC, abstractmethod
from typing import Dict, Any, List, Union, Optional, Tuple
from datetime import datetime

from tg_forwarder.interfaces.client_interface import TelegramClientInterface
from tg_forwarder.interfaces.downloader_interface import DownloaderInterface
from tg_forwarder.interfaces.uploader_interface import UploaderInterface
from tg_forwarder.interfaces.forwarder_interface import ForwarderInterface
from tg_forwarder.interfaces.config_interface import ConfigInterface
from tg_forwarder.interfaces.status_tracker_interface import StatusTrackerInterface
from tg_forwarder.interfaces.task_manager_interface import TaskManagerInterface
from tg_forwarder.interfaces.storage_interface import StorageInterface
from tg_forwarder.interfaces.logger_interface import LoggerInterface


class ApplicationInterface(ABC):
    """
    应用程序接口，定义了整个应用的管理方法和组件协调
    所有应用实现都应该继承此接口
    """
    
    @abstractmethod
    async def initialize(self) -> bool:
        """
        初始化应用程序
        
        Returns:
            bool: 初始化是否成功
        """
        pass
    
    @abstractmethod
    async def shutdown(self) -> None:
        """关闭应用程序，释放所有资源"""
        pass
    
    @abstractmethod
    def get_client(self) -> TelegramClientInterface:
        """
        获取Telegram客户端实例
        
        Returns:
            TelegramClientInterface: Telegram客户端接口实例
        """
        pass
    
    @abstractmethod
    def get_downloader(self) -> DownloaderInterface:
        """
        获取下载器实例
        
        Returns:
            DownloaderInterface: 下载器接口实例
        """
        pass
    
    @abstractmethod
    def get_uploader(self) -> UploaderInterface:
        """
        获取上传器实例
        
        Returns:
            UploaderInterface: 上传器接口实例
        """
        pass
    
    @abstractmethod
    def get_forwarder(self) -> ForwarderInterface:
        """
        获取转发器实例
        
        Returns:
            ForwarderInterface: 转发器接口实例
        """
        pass
    
    @abstractmethod
    def get_config(self) -> ConfigInterface:
        """
        获取配置管理实例
        
        Returns:
            ConfigInterface: 配置接口实例
        """
        pass
    
    @abstractmethod
    def get_status_tracker(self) -> StatusTrackerInterface:
        """
        获取状态跟踪器实例
        
        Returns:
            StatusTrackerInterface: 状态跟踪器接口实例
        """
        pass
    
    @abstractmethod
    def get_task_manager(self) -> TaskManagerInterface:
        """
        获取任务管理器实例
        
        Returns:
            TaskManagerInterface: 任务管理器接口实例
        """
        pass
    
    @abstractmethod
    def get_storage(self) -> StorageInterface:
        """
        获取存储实例
        
        Returns:
            StorageInterface: 存储接口实例
        """
        pass
    
    @abstractmethod
    def get_logger(self) -> LoggerInterface:
        """
        获取日志器实例
        
        Returns:
            LoggerInterface: 日志接口实例
        """
        pass
    
    @abstractmethod
    async def start_forwarding(self) -> bool:
        """
        启动消息转发服务
        
        Returns:
            bool: 启动是否成功
        """
        pass
    
    @abstractmethod
    async def stop_forwarding(self) -> bool:
        """
        停止消息转发服务
        
        Returns:
            bool: 停止是否成功
        """
        pass
    
    @abstractmethod
    async def restart_components(self, components: List[str] = None) -> Dict[str, bool]:
        """
        重启指定组件
        
        Args:
            components: 要重启的组件名称列表，为None时重启所有组件
            
        Returns:
            Dict[str, bool]: 各组件重启结果
        """
        pass
    
    @abstractmethod
    def get_application_status(self) -> Dict[str, Any]:
        """
        获取应用程序状态
        
        Returns:
            Dict[str, Any]: 应用状态信息
        """
        pass
    
    @abstractmethod
    def get_version(self) -> str:
        """
        获取应用程序版本
        
        Returns:
            str: 版本号
        """
        pass
    
    @abstractmethod
    async def backup_data(self, backup_path: Optional[str] = None) -> Dict[str, Any]:
        """
        备份应用数据
        
        Args:
            backup_path: 备份路径，为None时使用默认路径
            
        Returns:
            Dict[str, Any]: 备份结果
        """
        pass
    
    @abstractmethod
    async def restore_data(self, backup_path: str) -> Dict[str, Any]:
        """
        恢复应用数据
        
        Args:
            backup_path: 备份路径
            
        Returns:
            Dict[str, Any]: 恢复结果
        """
        pass
    
    @abstractmethod
    async def health_check(self) -> Dict[str, Any]:
        """
        执行应用健康检查
        
        Returns:
            Dict[str, Any]: 健康状态
        """
        pass
    
    @abstractmethod
    def register_event_handler(self, event_type: str, handler_func: callable) -> None:
        """
        注册事件处理器
        
        Args:
            event_type: 事件类型
            handler_func: 处理函数
        """
        pass
    
    @abstractmethod
    def unregister_event_handler(self, event_type: str, handler_func: callable) -> bool:
        """
        注销事件处理器
        
        Args:
            event_type: 事件类型
            handler_func: 处理函数
            
        Returns:
            bool: 是否成功注销
        """
        pass 