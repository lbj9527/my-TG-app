"""
存储接口抽象
定义了数据持久化的必要方法
"""

from abc import ABC, abstractmethod
from typing import Dict, Any, List, Optional, Union, TypeVar, Generic

T = TypeVar('T')


class StorageInterface(ABC):
    """
    存储接口，定义了数据持久化的必要方法
    所有存储实现都应该继承此接口
    """
    
    @abstractmethod
    def initialize(self) -> bool:
        """
        初始化存储
        
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
    def query(self, collection: str, filter_dict: Dict[str, Any] = None, 
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
    def ensure_index(self, collection: str, fields: List[str], unique: bool = False) -> bool:
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
    def backup(self, backup_path: str) -> bool:
        """
        备份数据
        
        Args:
            backup_path: 备份路径
            
        Returns:
            bool: 备份是否成功
        """
        pass
    
    @abstractmethod
    def restore(self, backup_path: str) -> bool:
        """
        恢复数据
        
        Args:
            backup_path: 备份路径
            
        Returns:
            bool: 恢复是否成功
        """
        pass 