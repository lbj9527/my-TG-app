"""
JSON存储实现类
提供JSON文件读写功能
"""

import os
import json
import logging
from typing import Dict, Any, Optional, List, Union
from datetime import datetime

from tg_forwarder.interfaces import JsonStorageInterface, ConfigInterface

class JsonStorage(JsonStorageInterface):
    """
    JSON存储实现类，提供JSON文件读写功能
    """
    
    def __init__(self, config: ConfigInterface):
        """
        初始化JsonStorage实例
        
        Args:
            config: 配置接口实例
        """
        self.config = config
        self.logger = logging.getLogger("JsonStorage")
        self.temp_directory = None
    
    async def initialize(self) -> bool:
        """
        初始化存储（异步方法）
        
        Returns:
            bool: 初始化是否成功
        """
        try:
            # 获取临时目录
            self.temp_directory = self.config.get("storage.tmp_path", "temp")
            
            # 确保临时目录存在
            os.makedirs(self.temp_directory, exist_ok=True)
            
            # 确保历史记录目录存在
            history_files = [
                self.config.get("download.download_history", "download_history.json"),
                self.config.get("upload.upload_history", "upload_history.json"),
                self.config.get("forward.forward_history", "forward_history.json")
            ]
            
            for file_path in history_files:
                directory = os.path.dirname(file_path)
                if directory and not os.path.exists(directory):
                    os.makedirs(directory, exist_ok=True)
                
                # 如果文件不存在，创建一个空的JSON文件
                if not os.path.exists(file_path):
                    # 创建基础结构
                    history_type = None
                    if "download_history" in file_path:
                        history_type = "download"
                    elif "upload_history" in file_path:
                        history_type = "upload"
                    elif "forward_history" in file_path:
                        history_type = "forward"
                    
                    if history_type:
                        data = self.create_history_structure(history_type)
                        self.save_json(file_path, data)
                    else:
                        self.save_json(file_path, {})
                    
            return True
        except Exception as e:
            self.logger.error(f"初始化JsonStorage失败: {str(e)}")
            return False
    
    def close(self) -> None:
        """关闭存储，释放资源"""
        # JSON文件操作不需要特殊的关闭过程
        pass
    
    def load_json(self, file_path: str) -> Dict[str, Any]:
        """
        加载JSON文件内容
        
        Args:
            file_path: 文件路径
            
        Returns:
            Dict[str, Any]: 加载的JSON数据，如果文件不存在或格式错误，返回空字典
        """
        try:
            if os.path.exists(file_path):
                with open(file_path, 'r', encoding='utf-8') as f:
                    return json.load(f)
            return {}
        except Exception as e:
            self.logger.error(f"加载JSON文件失败: {file_path}, 错误: {str(e)}")
            return {}
    
    def save_json(self, file_path: str, data: Dict[str, Any]) -> bool:
        """
        保存数据到JSON文件
        
        Args:
            file_path: 文件路径
            data: 要保存的数据
            
        Returns:
            bool: 保存是否成功
        """
        try:
            # 确保目录存在
            directory = os.path.dirname(file_path)
            if directory and not os.path.exists(directory):
                os.makedirs(directory, exist_ok=True)
                
            with open(file_path, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            return True
        except Exception as e:
            self.logger.error(f"保存JSON文件失败: {file_path}, 错误: {str(e)}")
            return False
    
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
        try:
            if os.path.exists(file_path):
                # 文件存在，加载然后更新
                data = self.load_json(file_path)
                data.update(updates)
                return self.save_json(file_path, data)
            elif create_if_not_exists:
                # 文件不存在，创建新文件
                return self.save_json(file_path, updates)
            else:
                # 文件不存在且不允许创建
                self.logger.error(f"更新JSON文件失败: {file_path} 不存在且不允许创建")
                return False
        except Exception as e:
            self.logger.error(f"更新JSON文件失败: {file_path}, 错误: {str(e)}")
            return False
    
    def get_temp_directory(self) -> str:
        """
        获取临时文件存储目录
        
        Returns:
            str: 临时文件目录路径
        """
        return self.temp_directory
    
    # 以下是新增方法，适配新的JSON格式
    
    def create_history_structure(self, history_type: str) -> Dict[str, Any]:
        """
        创建历史记录的基础结构
        
        Args:
            history_type: 历史记录类型（'download', 'upload', 'forward'）
            
        Returns:
            Dict[str, Any]: 创建的基础结构
        """
        # 根据不同的历史记录类型创建基础结构
        structure = {}
        
        if history_type == "download":
            structure = {
                "channels": {},
                "last_updated": self.format_datetime()
            }
        elif history_type == "upload":
            structure = {
                "files": {},
                "last_updated": self.format_datetime()
            }
        elif history_type == "forward":
            structure = {
                "channels": {},
                "last_updated": self.format_datetime()
            }
        else:
            self.logger.warning(f"未知的历史记录类型: {history_type}")
            structure = {
                "last_updated": self.format_datetime()
            }
        
        return structure
    
    def update_timestamp(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """
        更新数据中的时间戳
        
        Args:
            data: 要更新时间戳的数据
            
        Returns:
            Dict[str, Any]: 更新后的数据
        """
        # 创建数据的副本，避免直接修改原始数据
        updated_data = data.copy()
        
        # 更新最后更新时间戳
        updated_data["last_updated"] = self.format_datetime()
        
        return updated_data
    
    def merge_json_data(self, target: Dict[str, Any], source: Dict[str, Any]) -> Dict[str, Any]:
        """
        合并两个JSON数据
        
        Args:
            target: 目标数据
            source: 源数据
            
        Returns:
            Dict[str, Any]: 合并后的数据
        """
        # 创建目标数据的副本
        result = target.copy()
        
        # 递归合并数据
        for key, value in source.items():
            if key in result and isinstance(result[key], dict) and isinstance(value, dict):
                # 如果两者都是字典，递归合并
                result[key] = self.merge_json_data(result[key], value)
            elif key in result and isinstance(result[key], list) and isinstance(value, list):
                # 如果两者都是列表，合并并去重
                result[key] = list(set(result[key] + value))
            else:
                # 其他情况，直接覆盖
                result[key] = value
        
        # 更新时间戳
        if "last_updated" in result or "last_updated" in source:
            result["last_updated"] = self.format_datetime()
        
        return result
    
    def validate_history_structure(self, data: Dict[str, Any], history_type: str) -> bool:
        """
        验证历史记录的数据结构是否有效
        
        Args:
            data: 要验证的数据
            history_type: 历史记录类型（'download', 'upload', 'forward'）
            
        Returns:
            bool: 数据结构是否有效
        """
        # 检查是否包含必要的顶级字段
        if "last_updated" not in data:
            self.logger.warning(f"历史记录缺少last_updated字段: {history_type}")
            return False
        
        if history_type == "download" or history_type == "forward":
            if "channels" not in data:
                self.logger.warning(f"历史记录缺少channels字段: {history_type}")
                return False
                
            # 检查channels是否是字典
            if not isinstance(data["channels"], dict):
                self.logger.warning(f"历史记录的channels不是字典: {history_type}")
                return False
                
            # 检查channels中的每个频道是否符合规范
            for channel_name, channel_data in data["channels"].items():
                if not isinstance(channel_data, dict):
                    self.logger.warning(f"频道数据不是字典: {channel_name}")
                    return False
                    
                if "channel_id" not in channel_data:
                    self.logger.warning(f"频道数据缺少channel_id字段: {channel_name}")
                    return False
                
                if history_type == "download":
                    if "downloaded_messages" not in channel_data:
                        self.logger.warning(f"频道数据缺少downloaded_messages字段: {channel_name}")
                        return False
                        
                    if not isinstance(channel_data["downloaded_messages"], list):
                        self.logger.warning(f"频道的downloaded_messages不是列表: {channel_name}")
                        return False
                
                elif history_type == "forward":
                    if "forwarded_messages" not in channel_data:
                        self.logger.warning(f"频道数据缺少forwarded_messages字段: {channel_name}")
                        return False
                        
                    if not isinstance(channel_data["forwarded_messages"], dict):
                        self.logger.warning(f"频道的forwarded_messages不是字典: {channel_name}")
                        return False
                        
                    # 检查每个转发消息的目标频道是否是列表
                    for message_id, target_channels in channel_data["forwarded_messages"].items():
                        if not isinstance(target_channels, list):
                            self.logger.warning(f"消息的目标频道不是列表: {message_id}")
                            return False
        
        elif history_type == "upload":
            if "files" not in data:
                self.logger.warning(f"历史记录缺少files字段: {history_type}")
                return False
                
            # 检查files是否是字典
            if not isinstance(data["files"], dict):
                self.logger.warning(f"历史记录的files不是字典: {history_type}")
                return False
                
            # 检查files中的每个文件是否符合规范
            for file_path, file_data in data["files"].items():
                if not isinstance(file_data, dict):
                    self.logger.warning(f"文件数据不是字典: {file_path}")
                    return False
                    
                if "uploaded_to" not in file_data:
                    self.logger.warning(f"文件数据缺少uploaded_to字段: {file_path}")
                    return False
                    
                if not isinstance(file_data["uploaded_to"], list):
                    self.logger.warning(f"文件的uploaded_to不是列表: {file_path}")
                    return False
        
        return True
    
    def format_datetime(self, dt: datetime = None) -> str:
        """
        格式化日期时间为ISO 8601格式字符串
        
        Args:
            dt: 要格式化的日期时间，为None则使用当前时间
            
        Returns:
            str: 格式化的日期时间字符串
        """
        if dt is None:
            dt = datetime.now()
        
        # 使用ISO 8601格式，包含毫秒和时区信息
        return dt.isoformat(timespec='milliseconds')
    
    def parse_datetime(self, dt_str: str) -> Optional[datetime]:
        """
        解析时间字符串为datetime对象
        
        Args:
            dt_str: 时间字符串，支持ISO8601格式
            
        Returns:
            Optional[datetime]: 解析后的datetime对象，失败时返回None
        """
        try:
            # 尝试解析ISO8601格式
            return datetime.fromisoformat(dt_str.replace('Z', '+00:00'))
        except (ValueError, AttributeError):
            try:
                # 尝试解析没有时区信息的格式
                return datetime.fromisoformat(dt_str)
            except (ValueError, AttributeError):
                self.logger.error(f"无法解析时间字符串: {dt_str}")
                return None
    
    def query_data(self, collection_name: str, query: Dict[str, Any]) -> List[Dict[str, Any]]:
        """
        查询JSON文件中的数据（兼容旧接口）
        
        Args:
            collection_name: 集合名称，对应文件名前缀
            query: 查询条件
        
        Returns:
            List[Dict[str, Any]]: 查询结果列表，失败或无匹配时返回空列表
        """
        self.logger.warning("使用了已废弃的 query_data 方法，请迁移到新的 JSON 存储 API")
        
        try:
            # 构建文件路径
            file_path = f"{collection_name}.json"
            
            # 加载数据
            data = self.load_json(file_path)
            if not data:
                return []
            
            # 将数据扁平化为列表
            results = []
            if isinstance(data, dict):
                # 如果是字典，尝试将所有值作为记录
                for key, value in data.items():
                    if isinstance(value, dict):
                        # 将键添加到值中
                        record = {"key": key, **value}
                        results.append(record)
            
            # 返回所有记录，不做过滤（简化实现）
            # 注意：这里不实现完整的 MongoDB 风格查询，只是返回所有数据
            return results
        except Exception as e:
            self.logger.error(f"查询数据失败: {collection_name}, 错误: {str(e)}")
            return []
    
    def get_data(self, collection_name: str, key: str) -> Optional[Dict[str, Any]]:
        """
        获取指定键的数据（兼容旧接口）
        
        Args:
            collection_name: 集合名称，对应文件名前缀
            key: 数据键
        
        Returns:
            Optional[Dict[str, Any]]: 对应键的数据，不存在或失败时返回None
        """
        self.logger.warning("使用了已废弃的 get_data 方法，请迁移到新的 JSON 存储 API")
        
        try:
            # 构建文件路径
            file_path = f"{collection_name}.json"
            
            # 加载数据
            data = self.load_json(file_path)
            if not data or not isinstance(data, dict):
                return None
            
            # 检查键是否存在
            return data.get(key)
        except Exception as e:
            self.logger.error(f"获取数据失败: {collection_name}/{key}, 错误: {str(e)}")
            return None
    
    def store_data(self, collection_name: str, key: str, value: Dict[str, Any]) -> bool:
        """
        存储数据（兼容旧接口）
        
        Args:
            collection_name: 集合名称，对应文件名前缀
            key: 数据键
            value: 要存储的数据
        
        Returns:
            bool: 存储是否成功
        """
        self.logger.warning("使用了已废弃的 store_data 方法，请迁移到新的 JSON 存储 API")
        
        try:
            # 构建文件路径
            file_path = f"{collection_name}.json"
            
            # 加载现有数据
            data = self.load_json(file_path)
            if not isinstance(data, dict):
                data = {}
            
            # 更新数据
            data[key] = value
            
            # 保存数据
            return self.save_json(file_path, data)
        except Exception as e:
            self.logger.error(f"存储数据失败: {collection_name}/{key}, 错误: {str(e)}")
            return False 