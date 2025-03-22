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
from tg_forwarder.interfaces.storage_interface import StorageInterface
from tg_forwarder.interfaces.logger_interface import LoggerInterface
from tg_forwarder.interfaces.json_storage_interface import JsonStorageInterface
from tg_forwarder.interfaces.history_tracker_interface import HistoryTrackerInterface


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
    def get_storage(self) -> StorageInterface:
        """
        获取存储实例
        
        Returns:
            StorageInterface: 存储接口实例
            
        @deprecated: 此方法将在未来版本中被移除。请使用get_json_storage和get_history_tracker替代。
        """
        pass
    
    @abstractmethod
    def get_json_storage(self) -> JsonStorageInterface:
        """
        获取JSON存储实例
        
        Returns:
            JsonStorageInterface: JSON存储接口实例
        """
        pass
    
    @abstractmethod
    def get_history_tracker(self) -> HistoryTrackerInterface:
        """
        获取历史记录跟踪器实例
        
        Returns:
            HistoryTrackerInterface: 历史记录跟踪接口实例
        """
        pass
    
    @abstractmethod
    def get_logger(self) -> LoggerInterface:
        """
        获取日志记录器实例
        
        Returns:
            LoggerInterface: 日志记录器接口实例
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
    
    @abstractmethod
    async def download_messages(self, download_config: Dict[str, Any] = None) -> Dict[str, Any]:
        """
        下载消息和媒体
        
        Args:
            download_config: 下载配置，为None时使用默认配置
            
        Returns:
            Dict[str, Any]: 下载结果
        """
        pass
    
    @abstractmethod
    async def upload_files(self, upload_config: Dict[str, Any] = None) -> Dict[str, Any]:
        """
        上传本地文件到目标频道
        
        Args:
            upload_config: 上传配置，为None时使用默认配置
            
        Returns:
            Dict[str, Any]: 上传结果
        """
        pass
    
    @abstractmethod
    async def start_monitor(self, monitor_config: Dict[str, Any] = None) -> Dict[str, Any]:
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
        pass
    
    @abstractmethod
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
        pass
    
    @abstractmethod
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
        pass 