"""
上传历史记录管理工具
"""

import os
import json
import time
import asyncio
from typing import Dict, Any, List, Union, Optional

from tg_forwarder.utils.logger import get_logger

# 获取日志记录器
logger = get_logger("history_manager")


class UploadHistoryManager:
    """上传历史记录管理器"""
    
    def __init__(self, history_path: str, auto_save_interval: int = 300):
        """
        初始化上传历史记录管理器
        
        Args:
            history_path: 历史记录文件路径
            auto_save_interval: 自动保存间隔（秒）
        """
        self.history_path = history_path
        self.history_data = self._load_history()
        self.auto_save_interval = auto_save_interval
        self.last_saved = time.time()
        self.lock = asyncio.Lock()  # 并发访问锁
        self.dirty = False  # 是否有未保存的更改
        
        # 创建历史记录文件所在目录
        os.makedirs(os.path.dirname(self.history_path), exist_ok=True)
        
        # 启动自动保存任务
        self._auto_save_task = None
    
    def start_auto_save(self):
        """启动自动保存任务"""
        if self._auto_save_task is None or self._auto_save_task.done():
            self._auto_save_task = asyncio.create_task(self._auto_save_loop())
            logger.debug("启动上传历史自动保存任务")
    
    async def _auto_save_loop(self):
        """自动保存循环"""
        try:
            while True:
                await asyncio.sleep(self.auto_save_interval)
                await self.save_if_dirty()
        except asyncio.CancelledError:
            # 任务被取消时确保保存数据
            await self.save_if_dirty()
            logger.debug("上传历史自动保存任务已停止")
        except Exception as e:
            logger.error(f"自动保存上传历史时出错: {str(e)}")
    
    def stop_auto_save(self):
        """停止自动保存任务"""
        if self._auto_save_task and not self._auto_save_task.done():
            self._auto_save_task.cancel()
    
    def _load_history(self) -> Dict[str, Dict[str, Any]]:
        """
        加载上传历史记录
        
        Returns:
            Dict[str, Dict[str, Any]]: 上传历史记录
        """
        try:
            if os.path.exists(self.history_path):
                with open(self.history_path, "r", encoding="utf-8") as f:
                    history = json.load(f)
                logger.info(f"加载上传历史记录: {len(history)} 条记录")
                return history
        except Exception as e:
            logger.error(f"加载上传历史记录时出错: {str(e)}")
        
        return {}
    
    async def save_if_dirty(self) -> bool:
        """
        如果有未保存的更改，则保存上传历史记录
        
        Returns:
            bool: 是否执行了保存操作
        """
        async with self.lock:
            if self.dirty:
                await self._save_history()
                return True
        return False
    
    async def _save_history(self) -> None:
        """保存上传历史记录"""
        try:
            # 创建临时文件
            temp_path = f"{self.history_path}.tmp"
            with open(temp_path, "w", encoding="utf-8") as f:
                json.dump(self.history_data, f, ensure_ascii=False, indent=2)
            
            # 安全替换原文件
            os.replace(temp_path, self.history_path)
            
            self.last_saved = time.time()
            self.dirty = False
            logger.debug("保存上传历史记录成功")
        except Exception as e:
            logger.error(f"保存上传历史记录时出错: {str(e)}")
    
    async def record_upload(self, original_id: Union[str, int], channel_id: Union[str, int], 
                     message_ids: List[int], source_channel_id: Union[str, int] = None) -> None:
        """
        记录上传结果
        
        Args:
            original_id: 原始消息ID或媒体组ID
            channel_id: 目标频道ID
            message_ids: 上传后的消息ID列表
            source_channel_id: 源频道ID（可选）
        """
        async with self.lock:
            # 如果提供了源频道ID，将其添加到键中
            if source_channel_id:
                original_key = f"{source_channel_id}_{original_id}"
            else:
                original_key = str(original_id)
            
            channel_key = str(channel_id)
            
            # 初始化原始ID的记录
            if original_key not in self.history_data:
                self.history_data[original_key] = {}
            
            # 记录上传结果
            self.history_data[original_key][channel_key] = {
                "message_ids": message_ids,
                "timestamp": time.time()
            }
            
            self.dirty = True
    
    def is_message_uploaded(self, message_id: Union[str, int], channel_id: Union[str, int], 
                           source_channel_id: Union[str, int] = None) -> bool:
        """
        检查消息是否已上传到指定频道
        
        Args:
            message_id: 消息ID
            channel_id: 频道ID
            source_channel_id: 源频道ID（可选）
            
        Returns:
            bool: 是否已上传
        """
        if source_channel_id:
            message_key = f"{source_channel_id}_{message_id}"
        else:
            message_key = str(message_id)
        
        channel_key = str(channel_id)
        
        if message_key in self.history_data and channel_key in self.history_data[message_key]:
            return True
        
        return False
    
    def is_group_uploaded(self, group_id: str, channel_id: Union[str, int], 
                         source_channel_id: Union[str, int] = None) -> bool:
        """
        检查媒体组是否已上传到指定频道
        
        Args:
            group_id: 媒体组ID
            channel_id: 频道ID
            source_channel_id: 源频道ID（可选）
            
        Returns:
            bool: 是否已上传
        """
        return self.is_message_uploaded(group_id, channel_id, source_channel_id)
    
    def get_uploaded_message_ids(self, message_id: Union[str, int], channel_id: Union[str, int],
                                source_channel_id: Union[str, int] = None) -> List[int]:
        """
        获取上传的消息ID列表
        
        Args:
            message_id: 原始消息ID
            channel_id: 频道ID
            source_channel_id: 源频道ID（可选）
            
        Returns:
            List[int]: 上传的消息ID列表
        """
        if source_channel_id:
            message_key = f"{source_channel_id}_{message_id}"
        else:
            message_key = str(message_id)
        
        channel_key = str(channel_id)
        
        if message_key in self.history_data and channel_key in self.history_data[message_key]:
            return self.history_data[message_key][channel_key].get("message_ids", [])
        
        return []
    
    def cleanup_old_records(self, max_age_days: int = 30) -> int:
        """
        清理旧的上传记录
        
        Args:
            max_age_days: 最大保留天数
            
        Returns:
            int: 清理的记录数量
        """
        current_time = time.time()
        cleanup_threshold = current_time - (max_age_days * 24 * 3600)
        
        count = 0
        keys_to_delete = []
        
        for original_key, channels in self.history_data.items():
            channels_to_delete = []
            
            for channel_key, record in channels.items():
                if record.get("timestamp", 0) < cleanup_threshold:
                    channels_to_delete.append(channel_key)
                    count += 1
            
            # 删除旧的频道记录
            for channel_key in channels_to_delete:
                del channels[channel_key]
            
            # 如果没有频道记录，标记删除整个原始ID
            if not channels:
                keys_to_delete.append(original_key)
        
        # 删除空的原始ID记录
        for key in keys_to_delete:
            del self.history_data[key]
        
        # 标记为脏数据，需要保存
        if count > 0:
            self.dirty = True
            logger.info(f"清理了 {count} 条旧的上传记录")
        
        return count 