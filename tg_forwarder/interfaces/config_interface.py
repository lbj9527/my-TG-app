"""
配置接口抽象
定义了应用配置管理的必要方法
"""

from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional, Union, TypeVar, Generic

T = TypeVar('T')


class ConfigInterface(ABC):
    """
    配置接口，定义了管理应用配置的必要方法
    所有配置实现都应该继承此接口
    """
    
    @abstractmethod
    def load_config(self) -> bool:
        """
        加载配置文件
        
        Returns:
            bool: 加载是否成功
        """
        pass
    
    @abstractmethod
    def save_config(self) -> bool:
        """
        保存配置到文件
        
        Returns:
            bool: 保存是否成功
        """
        pass
    
    @abstractmethod
    def get(self, key: str, default: Optional[T] = None) -> T:
        """
        获取配置项
        
        Args:
            key: 配置键
            default: 默认值
            
        Returns:
            配置值，若不存在则返回默认值
        """
        pass
    
    @abstractmethod
    def get_value(self, key: str, default: Optional[T] = None) -> T:
        """
        获取配置项（与get方法相同，用于向后兼容）
        
        Args:
            key: 配置键，支持点号分隔的路径，如 "api.api_id"
            default: 默认值
            
        Returns:
            配置值，若不存在则返回默认值
        """
        pass
    
    @abstractmethod
    def set(self, key: str, value: Any) -> None:
        """
        设置配置项
        
        Args:
            key: 配置键
            value: 配置值
        """
        pass
    
    @abstractmethod
    def get_telegram_api_id(self) -> int:
        """
        获取Telegram API ID
        
        Returns:
            int: API ID
        """
        pass
    
    @abstractmethod
    def get_telegram_api_hash(self) -> str:
        """
        获取Telegram API Hash
        
        Returns:
            str: API Hash
        """
        pass
    
    @abstractmethod
    def get_session_name(self) -> str:
        """
        获取会话名称
        
        Returns:
            str: 会话名称
        """
        pass
    
    @abstractmethod
    def get_download_config(self) -> Dict[str, Any]:
        """
        获取下载配置
        
        Returns:
            Dict[str, Any]: 下载配置字典，包含source_channels、directory、timeout等参数
        """
        pass
    
    @abstractmethod
    def get_upload_config(self) -> Dict[str, Any]:
        """
        获取上传配置
        
        Returns:
            Dict[str, Any]: 上传配置字典，包含target_channels、directory、timeout等参数
        """
        pass
    
    @abstractmethod
    def get_forward_config(self) -> Dict[str, Any]:
        """
        获取转发配置
        
        Returns:
            Dict[str, Any]: 转发配置字典，包含channel_pairs、start_id、end_id等参数
        """
        pass
    
    @abstractmethod
    def get_monitor_config(self) -> Dict[str, Any]:
        """
        获取监听配置
        
        Returns:
            Dict[str, Any]: 监听配置字典，包含channel_pairs、duration、forward_delay等参数
        """
        pass
    
    @abstractmethod
    def get_storage_config(self) -> Dict[str, Any]:
        """
        获取存储配置
        
        Returns:
            Dict[str, Any]: 存储配置字典，包含tmp_path等参数
        """
        pass
    
    @abstractmethod
    def validate(self) -> Dict[str, List[str]]:
        """
        验证配置有效性
        
        Returns:
            Dict[str, List[str]]: 验证错误列表，键为配置项，值为错误信息列表
        """
        pass 