"""
此模块负责转发媒体消息。
"""

from typing import Dict, Any, Optional, Union
from pyrogram.types import Message


class MediaHandler:
    """
    此类负责处理媒体消息的转发
    """

    def __init__(self, client, media_config: Dict[str, Any]):
        """
        初始化MediaHandler类
        
        参数:
            client: Pyrogram客户端实例
            media_config: 媒体配置字典
        """
        self.client = client
        self.media_config = media_config

    async def forward_media_message(self, message: Message, target_chat_id: Union[int, str],
                                    disable_notification: bool = False) -> Optional[Message]:
        """
        将媒体消息转发到目标频道
        
        参数:
            message: 源消息对象
            target_chat_id: 目标聊天ID
            disable_notification: 是否禁用通知
            
        返回:
            Message: 转发后的消息对象
            None: 如果消息不包含媒体
            
        异常:
            如果转发失败，会抛出异常
        """
        # 检查消息是否包含媒体
        if not message.media:
            return None
            
        # 如果配置设置了skip_media为True，则跳过媒体转发
        if self.media_config.get('skip_media', False):
            return None
            
        # 直接转发媒体消息
        forwarded_message = await message.forward(
            chat_id=target_chat_id,
            disable_notification=disable_notification
        )
        
        return forwarded_message 