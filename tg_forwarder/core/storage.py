"""
存储实现类
提供数据持久化功能
"""

import os
import json
import shutil
import sqlite3
from typing import Dict, Any, List, Optional, Union, TypeVar
from pathlib import Path
from datetime import datetime, timedelta
import threading

from tg_forwarder.interfaces.storage_interface import StorageInterface

T = TypeVar('T')


class Storage(StorageInterface):
    """
    存储类，实现StorageInterface接口
    提供基于SQLite和JSON的数据持久化功能
    """
    
    def __init__(self, db_path: str = "data/tg_forwarder.db"):
        """
        初始化存储
        
        Args:
            db_path: 数据库路径
        """
        self.db_path = db_path
        self.conn = None
        self.lock = threading.RLock()  # 可重入锁，用于线程安全
        self._initialized = False
    
    def initialize(self) -> bool:
        """
        初始化存储
        
        Returns:
            bool: 初始化是否成功
        """
        try:
            # 确保目录存在
            db_dir = os.path.dirname(self.db_path)
            if db_dir and not os.path.exists(db_dir):
                os.makedirs(db_dir)
            
            # 连接到数据库
            self.conn = sqlite3.connect(self.db_path, check_same_thread=False)
            # 使用行工厂，结果集将作为字典返回
            self.conn.row_factory = sqlite3.Row
            
            # 创建必要的表
            self._create_tables()
            
            self._initialized = True
            return True
        except Exception as e:
            print(f"初始化存储失败: {str(e)}")
            self._initialized = False
            return False
    
    def close(self) -> None:
        """关闭存储，释放资源"""
        with self.lock:
            if self.conn:
                self.conn.close()
                self.conn = None
            self._initialized = False
    
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
        if not self._initialized:
            return False
        
        with self.lock:
            try:
                # 确保集合表存在
                self._ensure_collection(collection)
                
                # 准备数据
                json_data = json.dumps(data)
                timestamp = datetime.now().isoformat()
                
                # 插入或更新数据
                cursor = self.conn.cursor()
                cursor.execute(
                    f"INSERT OR REPLACE INTO {collection} (key, data, created_at, updated_at) VALUES (?, ?, ?, ?)",
                    (key, json_data, timestamp, timestamp)
                )
                self.conn.commit()
                return True
            except Exception as e:
                print(f"存储数据失败: {str(e)}")
                self.conn.rollback()
                return False
    
    def retrieve(self, collection: str, key: str) -> Optional[Dict[str, Any]]:
        """
        检索数据
        
        Args:
            collection: 集合名称
            key: 数据键
            
        Returns:
            Optional[Dict[str, Any]]: 检索到的数据，若不存在则返回None
        """
        if not self._initialized:
            return None
        
        with self.lock:
            try:
                # 检查集合是否存在
                if not self._collection_exists(collection):
                    return None
                
                # 查询数据
                cursor = self.conn.cursor()
                cursor.execute(f"SELECT data FROM {collection} WHERE key = ?", (key,))
                row = cursor.fetchone()
                
                if row:
                    return json.loads(row[0])
                return None
            except Exception as e:
                print(f"检索数据失败: {str(e)}")
                return None
    
    def delete(self, collection: str, key: str) -> bool:
        """
        删除数据
        
        Args:
            collection: 集合名称
            key: 数据键
            
        Returns:
            bool: 删除是否成功
        """
        if not self._initialized:
            return False
        
        with self.lock:
            try:
                # 检查集合是否存在
                if not self._collection_exists(collection):
                    return False
                
                # 删除数据
                cursor = self.conn.cursor()
                cursor.execute(f"DELETE FROM {collection} WHERE key = ?", (key,))
                self.conn.commit()
                return cursor.rowcount > 0
            except Exception as e:
                print(f"删除数据失败: {str(e)}")
                self.conn.rollback()
                return False
    
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
        if not self._initialized:
            return False
        
        with self.lock:
            try:
                # 确保集合表存在
                self._ensure_collection(collection)
                
                # 检查记录是否存在
                cursor = self.conn.cursor()
                cursor.execute(f"SELECT COUNT(*) FROM {collection} WHERE key = ?", (key,))
                exists = cursor.fetchone()[0] > 0
                
                if not exists and not upsert:
                    return False
                
                if exists:
                    # 获取现有数据，合并新数据
                    cursor.execute(f"SELECT data FROM {collection} WHERE key = ?", (key,))
                    row = cursor.fetchone()
                    if row:
                        existing_data = json.loads(row[0])
                        # 递归合并字典
                        self._merge_dicts(existing_data, data)
                        data = existing_data
                
                # 准备数据
                json_data = json.dumps(data)
                timestamp = datetime.now().isoformat()
                
                # 更新或插入数据
                if exists:
                    cursor.execute(
                        f"UPDATE {collection} SET data = ?, updated_at = ? WHERE key = ?",
                        (json_data, timestamp, key)
                    )
                else:
                    cursor.execute(
                        f"INSERT INTO {collection} (key, data, created_at, updated_at) VALUES (?, ?, ?, ?)",
                        (key, json_data, timestamp, timestamp)
                    )
                
                self.conn.commit()
                return True
            except Exception as e:
                print(f"更新数据失败: {str(e)}")
                self.conn.rollback()
                return False
    
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
        if not self._initialized:
            return []
        
        with self.lock:
            try:
                # 检查集合是否存在
                if not self._collection_exists(collection):
                    return []
                
                # 构建查询
                query = f"SELECT key, data, created_at, updated_at FROM {collection}"
                params = []
                
                # 添加过滤条件（简单实现，只支持基本字段过滤）
                if filter_dict:
                    conditions = []
                    for key, value in filter_dict.items():
                        if key in ['key', 'created_at', 'updated_at']:
                            conditions.append(f"{key} = ?")
                            params.append(value)
                    
                    if conditions:
                        query += " WHERE " + " AND ".join(conditions)
                
                # 添加排序
                if sort_by:
                    direction = "ASC"
                    if sort_by.startswith("-"):
                        sort_by = sort_by[1:]
                        direction = "DESC"
                    
                    if sort_by in ['key', 'created_at', 'updated_at']:
                        query += f" ORDER BY {sort_by} {direction}"
                
                # 添加分页
                if skip is not None:
                    query += f" OFFSET {int(skip)}"
                
                if limit is not None:
                    query += f" LIMIT {int(limit)}"
                
                # 执行查询
                cursor = self.conn.cursor()
                cursor.execute(query, params)
                rows = cursor.fetchall()
                
                # 处理结果
                result = []
                for row in rows:
                    item = {
                        'key': row['key'],
                        'created_at': row['created_at'],
                        'updated_at': row['updated_at'],
                        **json.loads(row['data'])
                    }
                    result.append(item)
                
                return result
            except Exception as e:
                print(f"查询数据失败: {str(e)}")
                return []
    
    def count(self, collection: str, filter_dict: Dict[str, Any] = None) -> int:
        """
        计数
        
        Args:
            collection: 集合名称
            filter_dict: 过滤条件
            
        Returns:
            int: 计数结果
        """
        if not self._initialized:
            return 0
        
        with self.lock:
            try:
                # 检查集合是否存在
                if not self._collection_exists(collection):
                    return 0
                
                # 构建查询
                query = f"SELECT COUNT(*) FROM {collection}"
                params = []
                
                # 添加过滤条件
                if filter_dict:
                    conditions = []
                    for key, value in filter_dict.items():
                        if key in ['key', 'created_at', 'updated_at']:
                            conditions.append(f"{key} = ?")
                            params.append(value)
                    
                    if conditions:
                        query += " WHERE " + " AND ".join(conditions)
                
                # 执行查询
                cursor = self.conn.cursor()
                cursor.execute(query, params)
                count = cursor.fetchone()[0]
                
                return count
            except Exception as e:
                print(f"计数失败: {str(e)}")
                return 0
    
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
        if not self._initialized:
            return False
        
        with self.lock:
            try:
                # 确保集合表存在
                self._ensure_collection(collection)
                
                # 验证字段
                valid_fields = [f for f in fields if f in ['key', 'created_at', 'updated_at']]
                if not valid_fields:
                    return False
                
                # 生成索引名称
                index_name = f"idx_{collection}_{'_'.join(valid_fields)}"
                unique_str = "UNIQUE " if unique else ""
                
                # 创建索引
                cursor = self.conn.cursor()
                cursor.execute(
                    f"CREATE {unique_str}INDEX IF NOT EXISTS {index_name} ON {collection} ({', '.join(valid_fields)})"
                )
                self.conn.commit()
                return True
            except Exception as e:
                print(f"创建索引失败: {str(e)}")
                self.conn.rollback()
                return False
    
    def backup(self, backup_path: str) -> bool:
        """
        备份数据
        
        Args:
            backup_path: 备份路径
            
        Returns:
            bool: 备份是否成功
        """
        if not self._initialized:
            return False
        
        with self.lock:
            try:
                # 确保备份目录存在
                backup_dir = os.path.dirname(backup_path)
                if backup_dir and not os.path.exists(backup_dir):
                    os.makedirs(backup_dir)
                
                # 创建备份
                self.conn.commit()  # 确保所有变更都已提交
                shutil.copy2(self.db_path, backup_path)
                return True
            except Exception as e:
                print(f"备份数据失败: {str(e)}")
                return False
    
    def restore(self, backup_path: str) -> bool:
        """
        恢复数据
        
        Args:
            backup_path: 备份路径
            
        Returns:
            bool: 恢复是否成功
        """
        if not os.path.exists(backup_path):
            print(f"备份文件不存在: {backup_path}")
            return False
        
        with self.lock:
            try:
                # 关闭现有连接
                if self.conn:
                    self.conn.close()
                
                # 恢复数据库文件
                shutil.copy2(backup_path, self.db_path)
                
                # 重新连接
                self.conn = sqlite3.connect(self.db_path, check_same_thread=False)
                self.conn.row_factory = sqlite3.Row
                
                self._initialized = True
                return True
            except Exception as e:
                print(f"恢复数据失败: {str(e)}")
                self._initialized = False
                return False
    
    def _create_tables(self) -> None:
        """创建必要的表和索引"""
        cursor = self.conn.cursor()
        
        # 创建元数据表，用于存储集合信息
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS _metadata (
            collection TEXT PRIMARY KEY,
            created_at TEXT NOT NULL
        )
        """)
        
        # 提交更改
        self.conn.commit()
    
    def _ensure_collection(self, collection: str) -> None:
        """
        确保集合表存在
        
        Args:
            collection: 集合名称
        """
        # 验证集合名称，避免SQL注入
        if not collection.isalnum():
            raise ValueError(f"无效的集合名称: {collection}")
        
        cursor = self.conn.cursor()
        
        # 检查集合是否已存在
        cursor.execute("SELECT COUNT(*) FROM _metadata WHERE collection = ?", (collection,))
        if cursor.fetchone()[0] == 0:
            # 创建新集合表
            cursor.execute(f"""
            CREATE TABLE IF NOT EXISTS {collection} (
                key TEXT PRIMARY KEY,
                data TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
            """)
            
            # 记录新集合
            timestamp = datetime.now().isoformat()
            cursor.execute(
                "INSERT INTO _metadata (collection, created_at) VALUES (?, ?)",
                (collection, timestamp)
            )
            
            # 创建默认索引
            cursor.execute(f"CREATE INDEX IF NOT EXISTS idx_{collection}_updated_at ON {collection} (updated_at)")
            
            self.conn.commit()
    
    def _collection_exists(self, collection: str) -> bool:
        """
        检查集合是否存在
        
        Args:
            collection: 集合名称
            
        Returns:
            bool: 集合是否存在
        """
        if not self.conn:
            return False
        
        cursor = self.conn.cursor()
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name=?", (collection,))
        return cursor.fetchone() is not None
    
    def _merge_dicts(self, target: Dict[str, Any], source: Dict[str, Any]) -> None:
        """
        递归合并字典
        
        Args:
            target: 目标字典
            source: 源字典
        """
        for key, value in source.items():
            if key in target and isinstance(target[key], dict) and isinstance(value, dict):
                self._merge_dicts(target[key], value)
            else:
                target[key] = value 