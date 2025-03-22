"""
存储接口抽象
定义了数据持久化的必要方法

@deprecated: 此接口将在未来版本中被移除。请使用JsonStorageInterface和HistoryTrackerInterface替代。
此接口中的数据库风格方法不符合项目存储需求，项目使用JSON文件存储历史记录，不使用数据库。
"""

from abc import ABC, abstractmethod
from typing import Dict, Any, List, Optional, Union, TypeVar, Generic

T = TypeVar('T')


class StorageInterface(ABC):
    """
    存储接口，定义了数据持久化的必要方法
    所有存储实现都应该继承此接口
    
    @deprecated: 此接口将在未来版本中被移除。请使用JsonStorageInterface和HistoryTrackerInterface替代。
    此接口中的数据库风格方法不符合项目存储需求，项目使用JSON文件存储历史记录，不使用数据库。
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
    def store(self, collection: str, key: str, data: Dict[str, Any]) -> bool:
        """
        存储数据
        
        Args:
            collection: 集合名称
            key: 数据键
            data: 要存储的数据
            
        Returns:
            bool: 存储是否成功
        """
        pass
    
    @abstractmethod
    def retrieve(self, collection: str, key: str) -> Optional[Dict[str, Any]]:
        """
        检索数据
        
        Args:
            collection: 集合名称
            key: 数据键
            
        Returns:
            Optional[Dict[str, Any]]: 检索到的数据，若不存在则返回None
        """
        pass
    
    @abstractmethod
    def delete(self, collection: str, key: str) -> bool:
        """
        删除数据
        
        Args:
            collection: 集合名称
            key: 数据键
            
        Returns:
            bool: 删除是否成功
        """
        pass
    
    @abstractmethod
    def update(self, collection: str, key: str, data: Dict[str, Any], upsert: bool = False) -> bool:
        """
        更新数据
        
        Args:
            collection: 集合名称
            key: 数据键
            data: 要更新的数据
            upsert: 若不存在是否插入
            
        Returns:
            bool: 更新是否成功
        """
        pass
    
    @abstractmethod
    async def query(self, collection: str, filter_dict: Dict[str, Any] = None, 
             sort_by: Optional[str] = None, limit: Optional[int] = None, 
             skip: Optional[int] = None) -> List[Dict[str, Any]]:
        """
        查询数据
        
        Args:
            collection: 集合名称
            filter_dict: 过滤条件
            sort_by: 排序字段
            limit: 限制返回数量
            skip: 跳过数量
            
        Returns:
            List[Dict[str, Any]]: 查询结果
        """
        pass
    
    @abstractmethod
    def count(self, collection: str, filter_dict: Dict[str, Any] = None) -> int:
        """
        计数
        
        Args:
            collection: 集合名称
            filter_dict: 过滤条件
            
        Returns:
            int: 计数结果
        """
        pass
    
    @abstractmethod
    async def ensure_index(self, collection: str, fields: List[str], unique: bool = False) -> bool:
        """
        确保索引存在
        
        Args:
            collection: 集合名称
            fields: 索引字段
            unique: 是否唯一索引
            
        Returns:
            bool: 操作是否成功
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