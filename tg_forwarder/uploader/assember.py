"""
消息重组模块，负责将下载的媒体文件重组成消息
"""

import os
import json
import logging
import time
from typing import Dict, Any, List, Tuple, Union, Optional
from collections import defaultdict

from tg_forwarder.utils.logger import get_logger

# 获取日志记录器
logger = get_logger("message_assembler")

class MessageAssembler:
    """消息重组器，将下载的媒体文件重组成原始格式的消息"""
    
    def __init__(self, metadata_path: str = "temp/message_metadata.json", 
                download_mapping_path: str = "temp/download_mapping.json"):
        """
        初始化消息重组器
        
        Args:
            metadata_path: 消息元数据路径
            download_mapping_path: 下载映射路径
        """
        self.metadata_path = metadata_path
        self.download_mapping_path = download_mapping_path
        
        # 加载元数据
        self.message_metadata = {}
        self.download_mapping = {}
        self._load_metadata()
        
        # 媒体组缓存
        self.media_groups = defaultdict(list)
    
    def _load_metadata(self) -> None:
        """加载元数据"""
        try:
            if os.path.exists(self.metadata_path):
                with open(self.metadata_path, "r", encoding="utf-8") as f:
                    self.message_metadata = json.load(f)
                logger.info(f"加载消息元数据: {len(self.message_metadata)} 条记录")
            
            if os.path.exists(self.download_mapping_path):
                with open(self.download_mapping_path, "r", encoding="utf-8") as f:
                    self.download_mapping = json.load(f)
                logger.info(f"加载下载映射: {len(self.download_mapping)} 条记录")
        except Exception as e:
            logger.error(f"加载元数据时出错: {str(e)}")
    
    def assemble_media_group(self, group_id: str) -> List[Dict[str, Any]]:
        """
        重组媒体组消息
        
        Args:
            group_id: 媒体组ID
            
        Returns:
            List[Dict[str, Any]]: 重组后的媒体组，每个元素为要发送的媒体文件信息
        """
        if not group_id:
            return []
        
        # 如果已缓存，直接返回
        if group_id in self.media_groups:
            return self.media_groups[group_id]
        
        # 查找属于该媒体组的所有消息
        group_messages = []
        for msg_id, metadata in self.message_metadata.items():
            if metadata.get("media_group_id") == group_id:
                # 检查是否有对应的下载文件
                if msg_id in self.download_mapping:
                    file_path = self.download_mapping[msg_id]
                    if os.path.exists(file_path):
                        # 复制一份元数据添加文件路径
                        msg_data = metadata.copy()
                        msg_data["file_path"] = file_path
                        group_messages.append(msg_data)
        
        # 按照message_id排序，确保顺序正确
        group_messages.sort(key=lambda x: x.get("message_id", 0))
        
        # 为第一个消息设置caption，其他消息清空caption
        if group_messages:
            caption = None
            caption_entities = None
            
            # 查找有caption的第一个消息
            for msg in group_messages:
                if msg.get("caption"):
                    caption = msg["caption"]
                    caption_entities = msg.get("caption_entities")
                    break
            
            # 设置caption
            if caption:
                for i, msg in enumerate(group_messages):
                    if i == 0:
                        msg["caption"] = caption
                        msg["caption_entities"] = caption_entities
                    else:
                        msg["caption"] = None
                        msg["caption_entities"] = None
        
        # 缓存结果
        self.media_groups[group_id] = group_messages
        
        logger.info(f"重组媒体组 {group_id}，包含 {len(group_messages)} 条消息")
        return group_messages
    
    def assemble_single_message(self, message_id: str) -> Optional[Dict[str, Any]]:
        """
        重组单条消息
        
        Args:
            message_id: 消息ID
            
        Returns:
            Optional[Dict[str, Any]]: 重组后的消息信息
        """
        if message_id not in self.message_metadata:
            logger.warning(f"消息 {message_id} 不存在元数据")
            return None
        
        metadata = self.message_metadata[message_id]
        
        # 检查是否属于媒体组
        if metadata.get("media_group_id"):
            logger.info(f"消息 {message_id} 属于媒体组 {metadata['media_group_id']}，将作为组消息处理")
            return None
        
        # 检查是否有对应的下载文件
        has_media = metadata.get("message_type") in ["photo", "video", "document", "audio", "voice", "animation"]
        
        if has_media:
            if message_id not in self.download_mapping:
                logger.warning(f"消息 {message_id} 没有对应的下载文件")
                return None
            
            file_path = self.download_mapping[message_id]
            if not os.path.exists(file_path):
                logger.warning(f"消息 {message_id} 的文件 {file_path} 不存在")
                return None
            
            # 添加文件路径
            metadata = metadata.copy()
            metadata["file_path"] = file_path
        
        logger.info(f"重组单条消息 {message_id}，类型: {metadata.get('message_type')}")
        return metadata
    
    def assemble_batch(self, downloaded_items: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        重组一批下载项
        
        Args:
            downloaded_items: 下载项列表，每个元素包含message_id和其他信息
            
        Returns:
            Dict[str, Any]: 重组结果，包含媒体组和单条消息
        """
        # 收集媒体组ID和消息ID
        group_ids = set()
        single_message_ids = []
        
        for item in downloaded_items:
            message_id = str(item.get("message_id"))
            media_group_id = item.get("media_group_id")
            
            if not message_id:
                continue
            
            if media_group_id:
                group_ids.add(media_group_id)
            else:
                # 检查元数据中是否有媒体组ID
                metadata = self.message_metadata.get(message_id, {})
                metadata_group_id = metadata.get("media_group_id")
                
                if metadata_group_id:
                    group_ids.add(metadata_group_id)
                else:
                    single_message_ids.append(message_id)
        
        # 重组媒体组
        media_groups = []
        for group_id in group_ids:
            group = self.assemble_media_group(group_id)
            if group:
                media_groups.append({
                    "media_group_id": group_id,
                    "messages": group
                })
        
        # 重组单条消息
        single_messages = []
        for msg_id in single_message_ids:
            msg = self.assemble_single_message(msg_id)
            if msg:
                single_messages.append(msg)
        
        logger.info(f"重组完成: {len(media_groups)} 个媒体组, {len(single_messages)} 条单独消息")
        
        return {
            "media_groups": media_groups,
            "single_messages": single_messages
        } 