"""
媒体处理工具
"""

import os
from typing import Dict, Any, List, Union, Optional, Tuple

from pyrogram.types import InputMediaPhoto, InputMediaVideo, InputMediaDocument, InputMediaAudio

from tg_forwarder.utils.logger import get_logger

# 获取日志记录器
logger = get_logger("media_utils")


class MediaUtils:
    """媒体处理工具类"""
    
    @staticmethod
    def get_media_type_from_file(file_path: str) -> str:
        """
        根据文件路径判断媒体类型
        
        Args:
            file_path: 文件路径
            
        Returns:
            str: 媒体类型 (photo, video, audio, document)
        """
        if not file_path or not os.path.exists(file_path):
            return "document"
        
        # 获取文件扩展名
        ext = os.path.splitext(file_path)[1].lower()
        
        # 根据扩展名判断类型
        if ext in ['.jpg', '.jpeg', '.png', '.webp']:
            return "photo"
        elif ext in ['.mp4', '.avi', '.mov', '.mkv']:
            return "video"
        elif ext in ['.mp3', '.ogg', '.m4a', '.wav']:
            return "audio"
        else:
            return "document"
    
    @staticmethod
    def extract_prop_from_message(msg: Dict[str, Any], prop_name: str, default=None) -> Any:
        """
        从消息结构中提取属性
        
        Args:
            msg: 消息数据
            prop_name: 属性名
            default: 默认值
            
        Returns:
            Any: 提取的属性值
        """
        # 直接在消息中查找
        value = msg.get(prop_name)
        if value is not None:
            return value
        
        # 在metadata中查找
        if isinstance(msg.get("metadata"), dict):
            value = msg.get("metadata", {}).get(prop_name)
            if value is not None:
                return value
        
        return default
    
    @staticmethod
    def create_media_item(msg: Dict[str, Any], file_path: str, use_caption: bool = False, 
                        caption: Optional[str] = None, caption_entities: Optional[List] = None) -> Optional[Union[InputMediaPhoto, InputMediaVideo, InputMediaDocument, InputMediaAudio]]:
        """
        创建媒体项
        
        Args:
            msg: 消息数据
            file_path: 文件路径
            use_caption: 是否使用标题
            caption: 标题内容
            caption_entities: 标题实体
            
        Returns:
            Optional[Union[InputMediaPhoto, InputMediaVideo, InputMediaDocument, InputMediaAudio]]: 创建的媒体项
        """
        if not file_path or not os.path.exists(file_path):
            logger.warning(f"文件不存在: {file_path}")
            return None
        
        # 获取媒体类型
        msg_type = MediaUtils.extract_prop_from_message(msg, "type") or MediaUtils.extract_prop_from_message(msg, "message_type")
        
        # 如果没有指定类型，根据文件扩展名判断
        if not msg_type:
            msg_type = MediaUtils.get_media_type_from_file(file_path)
            logger.info(f"根据扩展名判断媒体类型: {msg_type}")
        
        try:
            # 创建媒体项
            if msg_type == "photo":
                return InputMediaPhoto(
                    media=file_path,
                    caption=caption if use_caption else None,
                    caption_entities=caption_entities if use_caption else None
                )
            elif msg_type == "video":
                return InputMediaVideo(
                    media=file_path,
                    caption=caption if use_caption else None,
                    caption_entities=caption_entities if use_caption else None,
                    width=MediaUtils.extract_prop_from_message(msg, "width"),
                    height=MediaUtils.extract_prop_from_message(msg, "height"),
                    duration=MediaUtils.extract_prop_from_message(msg, "duration")
                )
            elif msg_type == "document":
                return InputMediaDocument(
                    media=file_path,
                    caption=caption if use_caption else None,
                    caption_entities=caption_entities if use_caption else None,
                    thumb=None,
                    file_name=MediaUtils.extract_prop_from_message(msg, "file_name")
                )
            elif msg_type == "audio":
                return InputMediaAudio(
                    media=file_path,
                    caption=caption if use_caption else None,
                    caption_entities=caption_entities if use_caption else None,
                    duration=MediaUtils.extract_prop_from_message(msg, "duration"),
                    performer=MediaUtils.extract_prop_from_message(msg, "performer"),
                    title=MediaUtils.extract_prop_from_message(msg, "title")
                )
            else:
                # 默认作为文档发送
                logger.warning(f"不支持的媒体类型: {msg_type}，使用文档类型代替")
                return InputMediaDocument(
                    media=file_path,
                    caption=caption if use_caption else None,
                    caption_entities=caption_entities if use_caption else None
                )
        
        except Exception as e:
            logger.error(f"创建媒体项时出错: {str(e)}")
            return None
    
    @staticmethod
    def get_caption_from_messages(messages: List[Dict[str, Any]]) -> Tuple[Optional[str], Optional[List]]:
        """
        从消息列表中获取标题
        
        Args:
            messages: 消息列表
            
        Returns:
            Tuple[Optional[str], Optional[List]]: (标题, 标题实体)
        """
        # 查找第一个有caption的消息
        for msg in messages:
            msg_caption = msg.get("caption")
            if msg_caption:
                return msg_caption, msg.get("caption_entities")
            
            # 兼容可能的嵌套metadata结构
            metadata = msg.get("metadata", {})
            if isinstance(metadata, dict) and metadata.get("caption"):
                return metadata.get("caption"), metadata.get("caption_entities")
        
        # 没有找到标题
        return None, None
    
    @staticmethod
    def create_media_group(messages: List[Dict[str, Any]]) -> List[Union[InputMediaPhoto, InputMediaVideo, InputMediaDocument, InputMediaAudio]]:
        """
        创建媒体组
        
        Args:
            messages: 消息列表
            
        Returns:
            List[Union[InputMediaPhoto, InputMediaVideo, InputMediaDocument, InputMediaAudio]]: 媒体组
        """
        media_group = []
        
        # 获取标题
        caption, caption_entities = MediaUtils.get_caption_from_messages(messages)
        if caption:
            logger.debug(f"找到媒体组标题: {caption[:30]}...")
        
        # 创建媒体项
        for i, msg in enumerate(messages):
            # 获取文件路径
            file_path = MediaUtils.extract_prop_from_message(msg, "file_path")
            
            if not file_path or not os.path.exists(file_path):
                logger.warning(f"消息 {msg.get('message_id')} 的文件不存在: {file_path}")
                continue
            
            # 第一个消息使用标题，其他消息不使用
            use_caption = i == 0 and caption is not None
            
            # 创建媒体项
            media_item = MediaUtils.create_media_item(msg, file_path, use_caption, caption, caption_entities)
            
            if media_item:
                media_group.append(media_item)
                logger.debug(f"已添加媒体项: 文件={os.path.basename(file_path)}")
        
        return media_group
    
    @staticmethod
    def prepare_single_message_args(message: Dict[str, Any], chat_id: Union[str, int]) -> Dict[str, Any]:
        """
        准备单条消息的参数
        
        Args:
            message: 消息数据
            chat_id: 目标聊天ID
            
        Returns:
            Dict[str, Any]: 消息参数
        """
        message_type = message.get("message_type")
        file_path = message.get("file_path")
        caption = message.get("caption")
        
        args = {
            "chat_id": chat_id,
            "caption": caption,
        }
        
        # 根据消息类型添加参数
        if message_type == "text":
            args["text"] = message.get("text", "")
            args["entities"] = message.get("text_entities")
        elif message_type == "photo":
            args["photo"] = file_path
        elif message_type == "video":
            args["video"] = file_path
            
            # 只添加有效的数值类型参数
            width = message.get("width")
            if isinstance(width, (int, float)) and width > 0:
                args["width"] = width
            
            height = message.get("height")
            if isinstance(height, (int, float)) and height > 0:
                args["height"] = height
            
            duration = message.get("duration")
            if isinstance(duration, (int, float)) and duration > 0:
                args["duration"] = duration
            
        elif message_type == "document":
            args["document"] = file_path
            
            file_name = message.get("file_name")
            if file_name:
                args["file_name"] = file_name
            
        elif message_type == "audio":
            args["audio"] = file_path
            
            duration = message.get("duration")
            if isinstance(duration, (int, float)) and duration > 0:
                args["duration"] = duration
            
            performer = message.get("performer")
            if performer:
                args["performer"] = performer
            
            title = message.get("title")
            if title:
                args["title"] = title
        
        return args 