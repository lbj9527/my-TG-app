"""
JSON存储接口抽象
定义了JSON文件操作的必要方法
"""

from abc import ABC, abstractmethod
from typing import Dict, Any, Optional, List, Union
from datetime import datetime


class JsonStorageInterface(ABC):
    """
    JSON存储接口，定义了JSON文件操作的必要方法
    所有JSON存储实现都应该继承此接口
    """
    
    @abstractmethod
    async def initialize(self) -> bool:
        """
        初始化存储（异步方法）
        
        Returns:
            bool: 初始化是否成功
        """
        pass
    
    @abstractmethod
    def close(self) -> None:
        """关闭存储，释放资源"""
        pass
    
    @abstractmethod
    def load_json(self, file_path: str) -> Dict[str, Any]:
        """
        加载JSON文件内容
        
        Args:
            file_path: 文件路径
            
        Returns:
            Dict[str, Any]: 加载的JSON数据
        """
        pass
    
    @abstractmethod
    def save_json(self, file_path: str, data: Dict[str, Any]) -> bool:
        """
        保存数据到JSON文件
        
        Args:
            file_path: 文件路径
            data: 要保存的数据
            
        Returns:
            bool: 保存是否成功
        """
        pass
    
    @abstractmethod
    def update_json(self, file_path: str, updates: Dict[str, Any], create_if_not_exists: bool = False) -> bool:
        """
        更新JSON文件中的部分内容
        
        Args:
            file_path: 文件路径
            updates: 要更新的数据
            create_if_not_exists: 文件不存在时是否创建
            
        Returns:
            bool: 更新是否成功
        """
        pass
    
    @abstractmethod
    def get_temp_directory(self) -> str:
        """
        获取临时文件存储目录
        
        Returns:
            str: 临时文件目录路径
        """
        pass
    
    # 以下是新增方法，适配新的JSON格式
    
    @abstractmethod
    def create_history_structure(self, history_type: str) -> Dict[str, Any]:
        """
        创建历史记录的基础结构
        
        Args:
            history_type: 历史记录类型（'download', 'upload', 'forward'）
            
        Returns:
            Dict[str, Any]: 创建的基础结构
        """
        pass
    
    @abstractmethod
    def update_timestamp(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """
        更新数据中的时间戳
        
        Args:
            data: 要更新时间戳的数据
            
        Returns:
            Dict[str, Any]: 更新后的数据
        """
        pass
    
    @abstractmethod
    def merge_json_data(self, target: Dict[str, Any], source: Dict[str, Any]) -> Dict[str, Any]:
        """
        合并两个JSON数据
        
        Args:
            target: 目标数据
            source: 源数据
            
        Returns:
            Dict[str, Any]: 合并后的数据
        """
        pass
    
    @abstractmethod
    def validate_history_structure(self, data: Dict[str, Any], history_type: str) -> bool:
        """
        验证历史记录的数据结构是否有效
        
        Args:
            data: 要验证的数据
            history_type: 历史记录类型（'download', 'upload', 'forward'）
            
        Returns:
            bool: 数据结构是否有效
        """
        pass
    
    @abstractmethod
    def format_datetime(self, dt: datetime = None) -> str:
        """
        格式化日期时间为ISO 8601格式字符串
        
        Args:
            dt: 要格式化的日期时间，为None则使用当前时间
            
        Returns:
            str: 格式化的日期时间字符串
        """
        pass
    
    @abstractmethod
    def parse_datetime(self, dt_str: str) -> Optional[datetime]:
        """
        解析ISO 8601格式字符串为日期时间对象
        
        Args:
            dt_str: 日期时间字符串
            
        Returns:
            Optional[datetime]: 解析的日期时间对象，解析失败则返回None
        """
        pass 