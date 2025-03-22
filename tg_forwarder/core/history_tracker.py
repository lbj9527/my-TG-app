"""
历史记录跟踪实现类
提供下载、上传和转发历史记录的管理功能
"""

import os
import json
import logging
from typing import Dict, Any, List, Optional, Set, Union
from datetime import datetime

from tg_forwarder.interfaces import HistoryTrackerInterface, ConfigInterface, JsonStorageInterface

class HistoryTracker(HistoryTrackerInterface):
    """
    历史记录跟踪实现类，提供下载、上传和转发历史记录的管理功能
    """
    
    def __init__(self, config: ConfigInterface, json_storage: JsonStorageInterface):
        """
        初始化HistoryTracker实例
        
        Args:
            config: 配置接口实例
            json_storage: JSON存储接口实例
        """
        self.config = config
        self.json_storage = json_storage
        self.logger = logging.getLogger("HistoryTracker")
        
        # 历史记录文件路径
        self.history_files = {
            "download": self.config.get("download.download_history", "download_history.json"),
            "upload": self.config.get("upload.upload_history", "upload_history.json"),
            "forward": self.config.get("forward.forward_history", "forward_history.json")
        }
        
        # 缓存已加载的历史记录
        self.history_cache = {
            "download": {},
            "upload": {},
            "forward": {}
        }
        
        # 频道ID映射缓存
        self.channel_id_map = {}
    
    async def initialize(self) -> bool:
        """
        初始化历史记录跟踪器（异步方法）
        
        Returns:
            bool: 初始化是否成功
        """
        try:
            # 加载所有历史记录到缓存
            for history_type, file_path in self.history_files.items():
                data = self.json_storage.load_json(file_path)
                
                # 验证数据结构
                if not self.json_storage.validate_history_structure(data, history_type):
                    # 如果数据结构无效，创建新的基础结构
                    data = self.json_storage.create_history_structure(history_type)
                    self.json_storage.save_json(file_path, data)
                
                self.history_cache[history_type] = data
                
                # 加载频道ID映射
                if history_type in ["download", "forward"] and "channels" in data:
                    for channel_name, channel_data in data["channels"].items():
                        if "channel_id" in channel_data:
                            channel_id = channel_data["channel_id"]
                            self.channel_id_map[channel_name] = channel_id
            
            return True
        except Exception as e:
            self.logger.error(f"初始化HistoryTracker失败: {str(e)}")
            return False
    
    def close(self) -> None:
        """关闭历史记录跟踪器，释放资源"""
        # 确保所有缓存的历史记录都已保存
        for history_type, data in self.history_cache.items():
            if data:
                self.json_storage.save_json(self.history_files[history_type], data)
    
    def _get_channel_key(self, channel_id: Union[int, str]) -> str:
        """
        获取频道的键名
        
        Args:
            channel_id: 频道ID或用户名
            
        Returns:
            str: 频道键名
        """
        return str(channel_id)
    
    def is_message_processed(self, history_type: str, channel_id: Union[int, str], message_id: int) -> bool:
        """
        检查消息是否已处理
        
        Args:
            history_type: 历史记录类型（'download', 'upload', 'forward'）
            channel_id: 频道ID或用户名
            message_id: 消息ID
            
        Returns:
            bool: 消息是否已处理
        """
        if history_type not in self.history_cache:
            return False
        
        channel_key = self._get_channel_key(channel_id)
        history_data = self.history_cache[history_type]
        
        if "channels" not in history_data or channel_key not in history_data["channels"]:
            return False
        
        channel_data = history_data["channels"][channel_key]
        
        if history_type == "download":
            if "downloaded_messages" not in channel_data:
                return False
            return int(message_id) in channel_data["downloaded_messages"]
        elif history_type == "forward":
            if "forwarded_messages" not in channel_data:
                return False
            return str(message_id) in channel_data["forwarded_messages"]
        
        return False
    
    def mark_message_processed(self, history_type: str, channel_id: Union[int, str], message_id: int) -> bool:
        """
        标记消息为已处理
        
        Args:
            history_type: 历史记录类型（'download', 'upload', 'forward'）
            channel_id: 频道ID或用户名
            message_id: 消息ID
            
        Returns:
            bool: 标记是否成功
        """
        if history_type not in self.history_cache:
            return False
        
        try:
            channel_key = self._get_channel_key(channel_id)
            history_data = self.history_cache[history_type]
            
            # 确保channels结构存在
            if "channels" not in history_data:
                history_data["channels"] = {}
            
            # 确保频道数据存在
            if channel_key not in history_data["channels"]:
                history_data["channels"][channel_key] = {
                    "channel_id": int(channel_id) if str(channel_id).startswith("-100") else channel_id
                }
            
            channel_data = history_data["channels"][channel_key]
            
            # 根据历史类型标记消息
            if history_type == "download":
                if "downloaded_messages" not in channel_data:
                    channel_data["downloaded_messages"] = []
                if int(message_id) not in channel_data["downloaded_messages"]:
                    channel_data["downloaded_messages"].append(int(message_id))
            elif history_type == "forward":
                if "forwarded_messages" not in channel_data:
                    channel_data["forwarded_messages"] = {}
                if str(message_id) not in channel_data["forwarded_messages"]:
                    channel_data["forwarded_messages"][str(message_id)] = []
            
            # 更新时间戳
            history_data = self.json_storage.update_timestamp(history_data)
            
            # 保存到文件
            return self.json_storage.save_json(self.history_files[history_type], history_data)
        except Exception as e:
            self.logger.error(f"标记消息已处理失败: {history_type}, {channel_id}, {message_id}, 错误: {str(e)}")
            return False
    
    def get_processed_messages(self, history_type: str, channel_id: Union[int, str]) -> Set[int]:
        """
        获取已处理的消息ID集合
        
        Args:
            history_type: 历史记录类型（'download', 'upload', 'forward'）
            channel_id: 频道ID或用户名
            
        Returns:
            Set[int]: 已处理的消息ID集合
        """
        if history_type not in self.history_cache:
            return set()
        
        channel_key = self._get_channel_key(channel_id)
        history_data = self.history_cache[history_type]
        
        if "channels" not in history_data or channel_key not in history_data["channels"]:
            return set()
        
        channel_data = history_data["channels"][channel_key]
        
        if history_type == "download":
            if "downloaded_messages" not in channel_data:
                return set()
            return set(channel_data["downloaded_messages"])
        elif history_type == "forward":
            if "forwarded_messages" not in channel_data:
                return set()
            return {int(msg_id) for msg_id in channel_data["forwarded_messages"].keys()}
        
        return set()
    
    def mark_file_uploaded(self, file_path: str, channel_id: Union[int, str]) -> bool:
        """
        标记文件已上传到指定频道
        
        Args:
            file_path: 文件路径
            channel_id: 已上传的目标频道ID或用户名
            
        Returns:
            bool: 标记是否成功
        """
        try:
            history_data = self.history_cache["upload"]
            
            # 标准化文件路径
            file_path = os.path.normpath(file_path)
            
            # 确保files结构存在
            if "files" not in history_data:
                history_data["files"] = {}
            
            # 确保文件数据存在
            if file_path not in history_data["files"]:
                history_data["files"][file_path] = {
                    "uploaded_to": [],
                    "upload_time": self.json_storage.format_datetime(),
                    "file_size": os.path.getsize(file_path) if os.path.exists(file_path) else 0,
                    "media_type": self._guess_media_type(file_path)
                }
            
            channel_key = self._get_channel_key(channel_id)
            
            # 添加到上传目标列表
            if "uploaded_to" not in history_data["files"][file_path]:
                history_data["files"][file_path]["uploaded_to"] = []
                
            if channel_key not in history_data["files"][file_path]["uploaded_to"]:
                history_data["files"][file_path]["uploaded_to"].append(channel_key)
            
            # 更新时间戳
            history_data = self.json_storage.update_timestamp(history_data)
            
            # 保存到文件
            return self.json_storage.save_json(self.history_files["upload"], history_data)
        except Exception as e:
            self.logger.error(f"标记文件已上传失败: {file_path}, {channel_id}, 错误: {str(e)}")
            return False
    
    def _guess_media_type(self, file_path: str) -> str:
        """
        根据文件扩展名猜测媒体类型
        
        Args:
            file_path: 文件路径
            
        Returns:
            str: 媒体类型
        """
        ext = os.path.splitext(file_path)[1].lower()
        if ext in ['.jpg', '.jpeg', '.png', '.webp']:
            return "photo"
        elif ext in ['.mp4', '.avi', '.mov', '.mkv', '.webm']:
            return "video"
        elif ext in ['.gif']:
            return "animation"
        elif ext in ['.mp3', '.ogg', '.m4a', '.flac', '.wav']:
            return "audio"
        else:
            return "document"
    
    def is_file_uploaded(self, file_path: str, channel_id: Union[int, str]) -> bool:
        """
        检查文件是否已上传到指定频道
        
        Args:
            file_path: 文件路径
            channel_id: 目标频道ID或用户名
            
        Returns:
            bool: 文件是否已上传
        """
        history_data = self.history_cache["upload"]
        
        # 标准化文件路径
        file_path = os.path.normpath(file_path)
        
        if "files" not in history_data or file_path not in history_data["files"]:
            return False
        
        file_data = history_data["files"][file_path]
        
        if "uploaded_to" not in file_data:
            return False
        
        channel_key = self._get_channel_key(channel_id)
        return channel_key in file_data["uploaded_to"]
    
    def get_uploaded_files(self, channel_id: Union[int, str] = None) -> List[str]:
        """
        获取已上传的文件列表
        
        Args:
            channel_id: 目标频道ID或用户名，为None时返回所有已上传文件
            
        Returns:
            List[str]: 已上传的文件路径列表
        """
        history_data = self.history_cache["upload"]
        
        if "files" not in history_data:
            return []
        
        if channel_id is None:
            # 返回所有已上传文件
            return list(history_data["files"].keys())
        
        # 返回已上传到指定频道的文件
        channel_key = self._get_channel_key(channel_id)
        return [
            file_path for file_path, file_data in history_data["files"].items() 
            if "uploaded_to" in file_data and channel_key in file_data["uploaded_to"]
        ]
    
    def clear_history(self, history_type: str, channel_id: Union[int, str] = None) -> bool:
        """
        清除历史记录
        
        Args:
            history_type: 历史记录类型（'download', 'upload', 'forward'）
            channel_id: 频道ID或用户名，为None时清除该类型的所有历史记录
            
        Returns:
            bool: 清除是否成功
        """
        if history_type not in self.history_cache:
            return False
        
        try:
            history_data = self.history_cache[history_type]
            
            if channel_id is None:
                # 清除所有历史记录，但保留结构
                if history_type == "upload":
                    history_data["files"] = {}
                else:
                    history_data["channels"] = {}
            else:
                # 清除指定频道的历史记录
                channel_key = self._get_channel_key(channel_id)
                
                if history_type == "upload":
                    # 对于上传历史，需要移除每个文件上传到该频道的记录
                    if "files" in history_data:
                        for file_path in list(history_data["files"].keys()):
                            if "uploaded_to" in history_data["files"][file_path] and channel_key in history_data["files"][file_path]["uploaded_to"]:
                                history_data["files"][file_path]["uploaded_to"].remove(channel_key)
                                if not history_data["files"][file_path]["uploaded_to"]:
                                    del history_data["files"][file_path]
                else:
                    # 对于下载和转发历史，直接删除频道记录
                    if "channels" in history_data and channel_key in history_data["channels"]:
                        del history_data["channels"][channel_key]
            
            # 更新时间戳
            history_data = self.json_storage.update_timestamp(history_data)
            
            # 保存到文件
            return self.json_storage.save_json(self.history_files[history_type], history_data)
        except Exception as e:
            self.logger.error(f"清除历史记录失败: {history_type}, {channel_id}, 错误: {str(e)}")
            return False
    
    def get_history_file_path(self, history_type: str) -> str:
        """
        获取历史记录文件路径
        
        Args:
            history_type: 历史记录类型（'download', 'upload', 'forward'）
            
        Returns:
            str: 历史记录文件路径
        """
        if history_type in self.history_files:
            return self.history_files[history_type]
        return ""
    
    def register_channel_id(self, channel_name: str, channel_id: int) -> bool:
        """
        注册频道ID和用户名的对应关系
        
        Args:
            channel_name: 频道用户名（如"@channel_name"或"https://t.me/channel_name"）
            channel_id: 频道ID（如-100123456789）
            
        Returns:
            bool: 注册是否成功
        """
        try:
            # 更新内存缓存
            self.channel_id_map[channel_name] = channel_id
            
            # 更新所有历史记录中的频道ID信息
            for history_type in ["download", "forward"]:
                history_data = self.history_cache[history_type]
                
                if "channels" not in history_data:
                    history_data["channels"] = {}
                
                # 如果频道名称已存在于历史记录中，更新channel_id
                if channel_name in history_data["channels"]:
                    history_data["channels"][channel_name]["channel_id"] = channel_id
                
                # 如果频道ID已存在于历史记录中，但key不是channel_name，则需要添加新的映射
                channel_id_key = str(channel_id)
                if channel_id_key in history_data["channels"] and channel_id_key != channel_name:
                    # 合并记录
                    if channel_name not in history_data["channels"]:
                        history_data["channels"][channel_name] = history_data["channels"][channel_id_key].copy()
                        history_data["channels"][channel_name]["channel_id"] = channel_id
                
                # 更新时间戳
                history_data = self.json_storage.update_timestamp(history_data)
                
                # 保存到文件
                self.json_storage.save_json(self.history_files[history_type], history_data)
            
            return True
        except Exception as e:
            self.logger.error(f"注册频道ID失败: {channel_name}, {channel_id}, 错误: {str(e)}")
            return False
    
    def get_channel_id(self, channel_name: str) -> Optional[int]:
        """
        获取频道ID
        
        Args:
            channel_name: 频道用户名
            
        Returns:
            Optional[int]: 频道ID，不存在时返回None
        """
        # 如果以@开头的用户名，移除@
        if channel_name.startswith("@"):
            clean_name = channel_name[1:]
        else:
            clean_name = channel_name
        
        # 如果是t.me链接，提取用户名
        if "t.me/" in clean_name:
            parts = clean_name.split("t.me/")
            if len(parts) > 1:
                clean_name = parts[1].split("/")[0]  # 处理可能的额外路径
        
        # 尝试不同的格式查找
        candidates = [
            channel_name,          # 原始格式
            clean_name,            # 移除@后的格式
            f"@{clean_name}",      # 添加@的格式
            f"https://t.me/{clean_name}"  # 完整t.me链接
        ]
        
        for candidate in candidates:
            if candidate in self.channel_id_map:
                return self.channel_id_map[candidate]
        
        # 检查是否本身就是数字ID
        if channel_name.startswith("-100") and channel_name[4:].isdigit():
            return int(channel_name)
        
        return None
    
    def mark_message_forwarded(self, source_channel: Union[int, str], message_id: int, target_channels: List[Union[int, str]]) -> bool:
        """
        标记消息已转发到目标频道
        
        Args:
            source_channel: 源频道ID或用户名
            message_id: 消息ID
            target_channels: 目标频道ID或用户名列表
            
        Returns:
            bool: 标记是否成功
        """
        try:
            history_data = self.history_cache["forward"]
            source_key = self._get_channel_key(source_channel)
            
            # 确保channels结构存在
            if "channels" not in history_data:
                history_data["channels"] = {}
            
            # 确保源频道数据存在
            if source_key not in history_data["channels"]:
                channel_id = self.get_channel_id(source_key) if isinstance(source_channel, str) else source_channel
                history_data["channels"][source_key] = {
                    "channel_id": channel_id,
                    "forwarded_messages": {}
                }
            
            # 确保forwarded_messages结构存在
            if "forwarded_messages" not in history_data["channels"][source_key]:
                history_data["channels"][source_key]["forwarded_messages"] = {}
            
            # 添加或更新消息的目标频道列表
            str_message_id = str(message_id)
            current_targets = history_data["channels"][source_key]["forwarded_messages"].get(str_message_id, [])
            
            # 添加新的目标频道
            target_keys = [self._get_channel_key(target) for target in target_channels]
            for target_key in target_keys:
                if target_key not in current_targets:
                    current_targets.append(target_key)
            
            # 更新转发消息记录
            history_data["channels"][source_key]["forwarded_messages"][str_message_id] = current_targets
            
            # 更新时间戳
            history_data = self.json_storage.update_timestamp(history_data)
            
            # 保存到文件
            return self.json_storage.save_json(self.history_files["forward"], history_data)
        except Exception as e:
            self.logger.error(f"标记消息已转发失败: {source_channel}, {message_id}, {target_channels}, 错误: {str(e)}")
            return False
    
    def get_forwarded_targets(self, source_channel: Union[int, str], message_id: int) -> List[Union[int, str]]:
        """
        获取消息已转发到的目标频道列表
        
        Args:
            source_channel: 源频道ID或用户名
            message_id: 消息ID
            
        Returns:
            List[Union[int, str]]: 已转发到的目标频道列表
        """
        history_data = self.history_cache["forward"]
        source_key = self._get_channel_key(source_channel)
        
        if "channels" not in history_data or source_key not in history_data["channels"]:
            return []
        
        if "forwarded_messages" not in history_data["channels"][source_key]:
            return []
        
        str_message_id = str(message_id)
        if str_message_id not in history_data["channels"][source_key]["forwarded_messages"]:
            return []
        
        return history_data["channels"][source_key]["forwarded_messages"][str_message_id]
    
    def add_file_upload_info(self, file_path: str, target_channel: Union[int, str], file_info: Dict[str, Any]) -> bool:
        """
        添加文件上传信息
        
        Args:
            file_path: 文件路径
            target_channel: 目标频道ID或用户名
            file_info: 文件信息，包括上传时间、文件大小、媒体类型等
            
        Returns:
            bool: 添加是否成功
        """
        try:
            history_data = self.history_cache["upload"]
            
            # 标准化文件路径
            file_path = os.path.normpath(file_path)
            
            # 确保files结构存在
            if "files" not in history_data:
                history_data["files"] = {}
            
            # 获取目标频道键
            target_key = self._get_channel_key(target_channel)
            
            # 如果文件已存在，更新信息
            if file_path in history_data["files"]:
                # 确保uploaded_to列表存在并包含目标频道
                if "uploaded_to" not in history_data["files"][file_path]:
                    history_data["files"][file_path]["uploaded_to"] = []
                
                if target_key not in history_data["files"][file_path]["uploaded_to"]:
                    history_data["files"][file_path]["uploaded_to"].append(target_key)
                
                # 更新文件信息
                for key, value in file_info.items():
                    if key != "uploaded_to":  # 避免覆盖已有的uploaded_to列表
                        history_data["files"][file_path][key] = value
            else:
                # 创建新的文件记录
                new_file_info = file_info.copy()  # 复制，避免修改原始数据
                
                # 确保基本字段存在
                if "uploaded_to" not in new_file_info:
                    new_file_info["uploaded_to"] = []
                
                # 确保目标频道在列表中
                if target_key not in new_file_info["uploaded_to"]:
                    new_file_info["uploaded_to"].append(target_key)
                
                # 确保上传时间存在
                if "upload_time" not in new_file_info:
                    new_file_info["upload_time"] = self.json_storage.format_datetime()
                
                # 确保文件大小和媒体类型存在
                if "file_size" not in new_file_info and os.path.exists(file_path):
                    new_file_info["file_size"] = os.path.getsize(file_path)
                
                if "media_type" not in new_file_info:
                    new_file_info["media_type"] = self._guess_media_type(file_path)
                
                # 添加到历史记录
                history_data["files"][file_path] = new_file_info
            
            # 更新时间戳
            history_data = self.json_storage.update_timestamp(history_data)
            
            # 保存到文件
            return self.json_storage.save_json(self.history_files["upload"], history_data)
        except Exception as e:
            self.logger.error(f"添加文件上传信息失败: {file_path}, {target_channel}, 错误: {str(e)}")
            return False
    
    def get_file_upload_info(self, file_path: str) -> Dict[str, Any]:
        """
        获取文件上传信息
        
        Args:
            file_path: 文件路径
            
        Returns:
            Dict[str, Any]: 文件上传信息，包括上传目标、上传时间、文件大小、媒体类型等
        """
        history_data = self.history_cache["upload"]
        
        # 标准化文件路径
        file_path = os.path.normpath(file_path)
        
        if "files" not in history_data or file_path not in history_data["files"]:
            return {}
        
        return history_data["files"][file_path].copy()  # 返回副本，避免意外修改
    
    def update_last_timestamp(self, history_type: str) -> bool:
        """
        更新历史记录的最后更新时间戳
        
        Args:
            history_type: 历史记录类型（'download', 'upload', 'forward'）
            
        Returns:
            bool: 更新是否成功
        """
        if history_type not in self.history_cache:
            return False
        
        try:
            history_data = self.history_cache[history_type]
            
            # 更新时间戳
            history_data = self.json_storage.update_timestamp(history_data)
            
            # 保存到文件
            return self.json_storage.save_json(self.history_files[history_type], history_data)
        except Exception as e:
            self.logger.error(f"更新时间戳失败: {history_type}, 错误: {str(e)}")
            return False
    
    def get_last_timestamp(self, history_type: str) -> Optional[datetime]:
        """
        获取历史记录的最后更新时间戳
        
        Args:
            history_type: 历史记录类型（'download', 'upload', 'forward'）
            
        Returns:
            Optional[datetime]: 最后更新时间戳，不存在时返回None
        """
        if history_type not in self.history_cache:
            return None
        
        history_data = self.history_cache[history_type]
        
        if "last_updated" not in history_data:
            return None
        
        return self.json_storage.parse_datetime(history_data["last_updated"])
    
    def export_history_data(self, history_type: str) -> Dict[str, Any]:
        """
        导出历史记录数据
        
        Args:
            history_type: 历史记录类型（'download', 'upload', 'forward'）
            
        Returns:
            Dict[str, Any]: 导出的历史记录数据，与JSON格式一致
        """
        if history_type not in self.history_cache:
            # 如果缓存中没有，则尝试从文件加载
            if history_type in self.history_files and os.path.exists(self.history_files[history_type]):
                return self.json_storage.load_json(self.history_files[history_type])
            # 返回空的基础结构
            return self.json_storage.create_history_structure(history_type)
        
        # 返回缓存中的数据副本，避免意外修改
        return self.history_cache[history_type].copy()
    
    def import_history_data(self, history_type: str, data: Dict[str, Any]) -> bool:
        """
        导入历史记录数据
        
        Args:
            history_type: 历史记录类型（'download', 'upload', 'forward'）
            data: 要导入的历史记录数据，与JSON格式一致
            
        Returns:
            bool: 导入是否成功
        """
        if history_type not in self.history_cache:
            return False
        
        try:
            # 验证数据结构
            if not self.json_storage.validate_history_structure(data, history_type):
                self.logger.error(f"导入的数据结构无效: {history_type}")
                return False
            
            # 将现有数据与导入数据合并
            current_data = self.history_cache[history_type]
            merged_data = self.json_storage.merge_json_data(current_data, data)
            
            # 更新缓存
            self.history_cache[history_type] = merged_data
            
            # 更新时间戳
            self.history_cache[history_type] = self.json_storage.update_timestamp(self.history_cache[history_type])
            
            # 保存到文件
            return self.json_storage.save_json(self.history_files[history_type], self.history_cache[history_type])
        except Exception as e:
            self.logger.error(f"导入历史记录数据失败: {history_type}, 错误: {str(e)}")
            return False 