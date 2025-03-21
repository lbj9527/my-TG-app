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
    def get_source_channels(self) -> List[Union[str, int]]:
        """
        获取源频道列表
        
        Returns:
            List[Union[str, int]]: 源频道列表
        """
        pass
    
    @abstractmethod
    def get_target_channels(self) -> List[Union[str, int]]:
        """
        获取目标频道列表
        
        Returns:
            List[Union[str, int]]: 目标频道列表
        """
        pass
    
    @abstractmethod
    def get_forward_config(self) -> Dict[str, Any]:
        """
        获取转发配置
        
        Returns:
            Dict[str, Any]: 转发配置字典，包含start_message_id、end_message_id等参数
        """
        pass
    
    @abstractmethod
    def get_channel_pairs(self) -> Dict[str, List[Union[str, int]]]:
        """
        获取频道配对信息（源频道到目标频道的映射）
        
        Returns:
            Dict[str, List[Union[str, int]]]: 源频道到目标频道的映射字典
        """
        pass
    
    @abstractmethod
    def get_source_channel_config(self, channel_id: str) -> Dict[str, Any]:
        """
        获取特定源频道的配置
        
        Args:
            channel_id: 源频道ID或URL
            
        Returns:
            Dict[str, Any]: 源频道配置字典
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