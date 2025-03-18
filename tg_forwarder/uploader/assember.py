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
            # 检查路径的完整性
            metadata_dir = os.path.dirname(self.metadata_path)
            logger.debug(f"元数据目录: {metadata_dir}, 是否存在: {os.path.exists(metadata_dir)}")
            logger.debug(f"元数据路径: {self.metadata_path}, 是否存在: {os.path.exists(self.metadata_path)}")
            logger.debug(f"下载映射路径: {self.download_mapping_path}, 是否存在: {os.path.exists(self.download_mapping_path)}")
            
            # 加载消息元数据
            if os.path.exists(self.metadata_path):
                try:
                    start_time = time.time()
                    with open(self.metadata_path, "r", encoding="utf-8") as f:
                        content = f.read()
                    
                    logger.debug(f"元数据文件读取耗时: {time.time() - start_time:.3f}秒, 内容大小: {len(content)} 字节")
                    
                    # 检查文件不为空
                    if content.strip():
                        try:
                            start_time = time.time()
                            self.message_metadata = json.loads(content)
                            logger.info(f"解析消息元数据: {len(self.message_metadata)} 条记录, 耗时: {time.time() - start_time:.3f}秒")
                            
                            # 检查元数据的结构
                            if self.message_metadata:
                                # 确保所有键都是字符串类型
                                if not all(isinstance(k, str) for k in self.message_metadata.keys()):
                                    logger.warning("元数据键不全是字符串类型，进行转换")
                                    self.message_metadata = {str(k): v for k, v in self.message_metadata.items()}
                                
                                sample_keys = list(self.message_metadata.keys())[:3]
                                logger.debug(f"元数据示例键: {sample_keys}")
                                
                                # 检查一个示例记录
                                sample_metadata = self.message_metadata.get(sample_keys[0]) if sample_keys else {}
                                logger.debug(f"元数据示例结构: {list(sample_metadata.keys()) if sample_metadata else '空'}")
                                
                                # 统计包含媒体组ID的消息数量
                                media_group_count = sum(1 for meta in self.message_metadata.values() 
                                                       if meta.get("media_group_id"))
                                logger.info(f"元数据中包含媒体组ID的消息数量: {media_group_count}")
                                
                                # 获取唯一的媒体组ID
                                unique_groups = {str(meta.get("media_group_id")) for meta in self.message_metadata.values() 
                                               if meta.get("media_group_id")}
                                logger.info(f"元数据中包含 {len(unique_groups)} 个不同的媒体组ID")
                                if unique_groups:
                                    logger.debug(f"媒体组ID样例: {list(unique_groups)[:3]}")
                        except json.JSONDecodeError as je:
                            logger.error(f"解析消息元数据时出错: {str(je)}")
                            logger.debug(f"元数据文件前100个字符: {content[:100]}...")
                            self.message_metadata = {}
                    else:
                        logger.warning(f"元数据文件为空: {self.metadata_path}")
                        self.message_metadata = {}
                except Exception as e:
                    logger.error(f"读取消息元数据文件时出错: {str(e)}")
                    import traceback
                    logger.debug(f"错误详情: {traceback.format_exc()}")
                    self.message_metadata = {}
            else:
                logger.warning(f"消息元数据文件不存在: {self.metadata_path}")
                self.message_metadata = {}
            
            # 加载下载映射
            if os.path.exists(self.download_mapping_path):
                try:
                    start_time = time.time()
                    with open(self.download_mapping_path, "r", encoding="utf-8") as f:
                        content = f.read()
                    
                    logger.debug(f"下载映射文件读取耗时: {time.time() - start_time:.3f}秒, 内容大小: {len(content)} 字节")
                    
                    # 检查文件不为空
                    if content.strip():
                        try:
                            start_time = time.time()
                            self.download_mapping = json.loads(content)
                            logger.info(f"解析下载映射: {len(self.download_mapping)} 条记录, 耗时: {time.time() - start_time:.3f}秒")
                            
                            # 确保所有键都是字符串类型
                            if not all(isinstance(k, str) for k in self.download_mapping.keys()):
                                logger.warning("下载映射键不全是字符串类型，进行转换")
                                self.download_mapping = {str(k): v for k, v in self.download_mapping.items()}
                            
                            # 验证映射记录
                            if self.download_mapping:
                                existing_files = 0
                                missing_files = 0
                                
                                for msg_id, file_path in list(self.download_mapping.items())[:20]:  # 仅检查前20条
                                    if os.path.exists(file_path):
                                        existing_files += 1
                                    else:
                                        missing_files += 1
                                
                                logger.debug(f"下载映射文件状态检查(前20条): 存在文件={existing_files}, 缺失文件={missing_files}")
                                
                                # 检查键的类型
                                sample_key = next(iter(self.download_mapping.keys()))
                                logger.debug(f"下载映射示例键类型: {type(sample_key).__name__}, 值: {sample_key}")
                                
                                # 检查下载映射与元数据的键对应关系
                                metadata_match = sum(1 for k in self.download_mapping.keys() 
                                                   if k in self.message_metadata)
                                logger.info(f"下载映射与元数据的键匹配: {metadata_match}/{len(self.download_mapping)}")
                                
                        except json.JSONDecodeError as je:
                            logger.error(f"解析下载映射时出错: {str(je)}")
                            logger.debug(f"下载映射文件前100个字符: {content[:100]}...")
                            self.download_mapping = {}
                    else:
                        logger.warning(f"下载映射文件为空: {self.download_mapping_path}")
                        self.download_mapping = {}
                except Exception as e:
                    logger.error(f"读取下载映射文件时出错: {str(e)}")
                    import traceback
                    logger.debug(f"错误详情: {traceback.format_exc()}")
                    self.download_mapping = {}
            else:
                logger.warning(f"下载映射文件不存在: {self.download_mapping_path}")
                self.download_mapping = {}
                
        except Exception as e:
            logger.error(f"加载元数据时出错: {str(e)}")
            import traceback
            logger.debug(f"错误详情: {traceback.format_exc()}")
            # 重置为空字典
            self.message_metadata = {}
            self.download_mapping = {}
    
    def assemble_media_group(self, group_id: Union[str, int]) -> List[Dict[str, Any]]:
        """
        重组媒体组
        
        Args:
            group_id: 媒体组ID
            
        Returns:
            List[Dict[str, Any]]: 重组后的媒体组消息列表
        """
        # 记录执行的详细过程
        logger.debug(f"开始重组媒体组 {group_id} 的详细执行")
        
        # 避免传入None值
        if not group_id:
            logger.warning(f"媒体组ID为空，无法重组")
            return []
        
        # 在元数据中寻找属于该媒体组的消息
        group_messages = []
        logger.debug(f"扫描元数据查找媒体组 {group_id} 的消息，元数据条目数: {len(self.message_metadata)}")
        
        # 获取所有包含媒体组ID的媒体组ID列表，用于调试
        all_group_ids = {str(meta.get("media_group_id")) for meta in self.message_metadata.values() 
                      if meta.get("media_group_id") is not None}
        logger.debug(f"元数据中包含的媒体组ID: {list(all_group_ids)}")
        
        # 尝试不同的类型匹配，因为ID可能以字符串或整数形式存储
        group_id_variants = [group_id, str(group_id)]
        # 如果是字符串，尝试转换为整数
        if isinstance(group_id, str) and group_id.isdigit():
            group_id_variants.append(int(group_id))
        logger.debug(f"将尝试以下变体的媒体组ID: {group_id_variants}")
        
        # 检查元数据键和值的类型
        if self.message_metadata:
            sample_key = next(iter(self.message_metadata.keys()))
            sample_value = self.message_metadata[sample_key]
            logger.debug(f"元数据键类型: {type(sample_key).__name__}, 示例键: {sample_key}")
            if "media_group_id" in sample_value and sample_value["media_group_id"]:
                logger.debug(f"元数据中媒体组ID类型: {type(sample_value['media_group_id']).__name__}, 示例值: {sample_value['media_group_id']}")
        else:
            logger.debug(f"元数据键类型: 未知")
        
        # 查找所有属于该媒体组的消息
        for msg_id, metadata in self.message_metadata.items():
            msg_group_id = metadata.get("media_group_id")
            
            # 检查媒体组ID是否匹配（考虑不同类型）
            if msg_group_id is not None and any(variant == msg_group_id for variant in group_id_variants):
                # 检查是否有对应的下载映射
                if msg_id in self.download_mapping:
                    file_path = self.download_mapping[msg_id]
                    
                    # 检查文件是否存在
                    if os.path.exists(file_path):
                        group_messages.append({
                            "message_id": msg_id,
                            "metadata": metadata,
                            "file_path": file_path
                        })
                        logger.debug(f"找到媒体组消息: 消息ID={msg_id}, 文件路径={file_path}")
                    else:
                        logger.warning(f"消息 {msg_id} 的文件不存在: {file_path}")
                else:
                    logger.warning(f"消息 {msg_id} 没有对应的下载映射")
        
        # 如果没有找到媒体组消息，记录日志并返回空列表
        if not group_messages:
            logger.warning(f"没有找到媒体组 {group_id} 的消息，已尝试以下变体: {group_id_variants}")
            # 输出一些额外的调试信息
            if all_group_ids:
                logger.debug(f"元数据中存在的媒体组ID: {list(all_group_ids)[:5]}...")
            return []
        
        # 按消息ID排序
        try:
            # 尝试转换为数字排序
            group_messages.sort(key=lambda x: int(x["message_id"]))
            logger.debug(f"使用数字排序方式对 {len(group_messages)} 条消息进行排序")
        except (ValueError, TypeError):
            # 如果无法转换为数字，则按字符串排序
            group_messages.sort(key=lambda x: str(x["message_id"]))
            logger.debug(f"使用字符串排序方式对 {len(group_messages)} 条消息进行排序")
        
        # 构建重组后的媒体组
        result = []
        for message in group_messages:
            msg_id = message["message_id"]
            metadata = message["metadata"]
            file_path = message["file_path"]
            
            # 获取媒体类型
            message_type = metadata.get("message_type")
            
            # 构建媒体项
            media_item = {
                "message_id": msg_id,
                "type": message_type,
                "file_path": file_path,
                "media_group_id": group_id,
            }
            
            # 添加其他元数据
            for key, value in metadata.items():
                if key not in media_item and value is not None:
                    media_item[key] = value
            
            result.append(media_item)
        
        # 设置第一条消息的标题
        if result and "caption" in result[0].get("metadata", {}):
            caption = result[0]["metadata"]["caption"]
            for item in result:
                if item != result[0]:
                    # 其他消息应当删除标题，避免重复
                    if "caption" in item:
                        del item["caption"]
            
            # 记录日志
            logger.debug(f"设置媒体组的标题: {caption[:30] if caption else 'None'}")
        
        logger.info(f"重组媒体组 {group_id}，包含 {len(result)} 条消息")
        
        # 记录前三条消息的信息
        for i, item in enumerate(result[:3]):
            logger.debug(f"媒体组消息 {i+1}: ID={item['message_id']}, 类型={item.get('type')}, 文件路径={item.get('file_path')}")
        
        return result
    
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
            downloaded_items: 下载项列表，每个下载项包含message_id, media_group_id等信息
            
        Returns:
            Dict[str, Any]: 重组结果，包含media_groups和single_messages
        """
        logger.info(f"开始重组批次，收到 {len(downloaded_items)} 个下载项")
        
        # 重新加载最新的元数据文件，确保获取最新数据
        self._load_metadata()
        
        # 打印部分下载项信息用于调试
        for i, item in enumerate(downloaded_items[:5], 1):
            logger.debug(f"下载项 {i}: message_id={item.get('message_id')}, media_group_id={item.get('media_group_id')}, type={item.get('type')}")
        if len(downloaded_items) > 5:
            logger.debug(f"... 等共 {len(downloaded_items)} 个下载项")
        
        # 检查临时目录
        temp_dir = os.path.dirname(self.metadata_path)
        logger.debug(f"临时目录状态: 存在={os.path.exists(temp_dir)}, 路径={os.path.abspath(temp_dir)}")
        
        # 检查临时目录内容
        if os.path.exists(temp_dir):
            files = os.listdir(temp_dir)
            logger.debug(f"临时目录内容: {files}... 等共 {len(files)} 项")
        
        # 检查元数据文件状态
        metadata_exists = os.path.exists(self.metadata_path)
        metadata_size = os.path.getsize(self.metadata_path) if metadata_exists else 0
        logger.debug(f"元数据文件状态: 存在={metadata_exists}, 大小={metadata_size} 字节")
        
        # 检查下载映射文件状态
        mapping_exists = os.path.exists(self.download_mapping_path)
        mapping_size = os.path.getsize(self.download_mapping_path) if mapping_exists else 0
        logger.debug(f"下载映射文件状态: 存在={mapping_exists}, 大小={mapping_size} 字节")
        
        # 检查元数据内容
        logger.debug(f"已加载元数据数量: {len(self.message_metadata)} 条")
        logger.debug(f"已加载下载映射数量: {len(self.download_mapping)} 条")
        
        if self.message_metadata:
            sample_keys = list(self.message_metadata.keys())[:3]
            logger.debug(f"元数据示例key: {sample_keys}")
            for key in sample_keys:
                metadata = self.message_metadata[key]
                logger.debug(f"元数据示例[{key}]: media_group_id={metadata.get('media_group_id')}, "
                          f"message_type={metadata.get('message_type')}")
        
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
                logger.debug(f"发现媒体组消息: message_id={message_id}, group_id={media_group_id}")
            else:
                # 检查元数据中是否有媒体组ID
                metadata = self.message_metadata.get(message_id, {})
                metadata_group_id = metadata.get("media_group_id")
                
                if metadata_group_id:
                    group_ids.add(metadata_group_id)
                    logger.debug(f"从元数据发现媒体组消息: message_id={message_id}, group_id={metadata_group_id}")
                else:
                    single_message_ids.append(message_id)
                    logger.debug(f"发现单独消息: message_id={message_id}")
        
        # 打印收集结果
        logger.info(f"收集到 {len(group_ids)} 个媒体组和 {len(single_message_ids)} 条单独消息")
        if group_ids:
            logger.debug(f"媒体组ID列表: {list(group_ids)}")
        
        # 重组媒体组
        media_groups = []
        for group_id in group_ids:
            logger.info(f"开始重组媒体组 {group_id}")
            
            # 检查元数据中属于该组的消息
            messages_in_metadata = 0
            for msg_id, meta in self.message_metadata.items():
                if meta.get("media_group_id") == group_id:
                    messages_in_metadata += 1
            logger.debug(f"元数据中属于媒体组 {group_id} 的消息数量: {messages_in_metadata}")
            
            # 检查下载映射中属于该组的消息
            mapped_messages = []
            for msg_id, meta in self.message_metadata.items():
                if meta.get("media_group_id") == group_id and msg_id in self.download_mapping:
                    file_path = self.download_mapping[msg_id]
                    file_exists = os.path.exists(file_path)
                    mapped_messages.append((msg_id, file_path, file_exists))
            
            logger.debug(f"下载映射中属于媒体组 {group_id} 的消息: {mapped_messages}")
            
            group = self.assemble_media_group(group_id)
            if group:
                media_groups.append({
                    "media_group_id": group_id,
                    "messages": group
                })
                logger.debug(f"成功重组媒体组 {group_id}, 包含 {len(group)} 条消息")
            else:
                logger.warning(f"媒体组 {group_id} 重组失败或为空")
        
        # 重组单条消息
        single_messages = []
        for msg_id in single_message_ids:
            logger.debug(f"开始重组单条消息 {msg_id}")
            msg = self.assemble_single_message(msg_id)
            if msg:
                single_messages.append(msg)
                logger.debug(f"成功重组单条消息 {msg_id}")
            else:
                logger.warning(f"单条消息 {msg_id} 重组失败或为空")
        
        result = {
            "media_groups": media_groups,
            "single_messages": single_messages
        }
        
        # 添加调试信息：重组结果
        logger.info(f"重组完成: {len(media_groups)} 个媒体组, {len(single_messages)} 条单独消息")
        if media_groups:
            for i, group in enumerate(media_groups):
                group_id = group.get("media_group_id")
                messages = group.get("messages", [])
                logger.debug(f"媒体组 {i+1}/{len(media_groups)}: ID={group_id}, 消息数量={len(messages)}")
                if messages:
                    logger.debug(f"媒体组 {group_id} 的第一条消息: type={messages[0].get('message_type')}, "
                               f"file_path存在={bool(messages[0].get('file_path') and os.path.exists(messages[0].get('file_path', '')))}")
        
        return result 