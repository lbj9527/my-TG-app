"""
Telegram客户端模块，负责与Telegram API交互
"""

import os
import asyncio
from typing import Dict, Any, Optional, List, Union, Tuple
from pyrogram import Client, filters
from pyrogram.types import Message
from pyrogram.errors import FloodWait, AuthKeyUnregistered, AuthKeyDuplicated, SessionPasswordNeeded

from tg_forwarder.utils.logger import get_logger

logger = get_logger("client")

class TelegramClient:
    """Telegram客户端类，负责认证和API交互"""
    
    def __init__(self, api_config: Dict[str, Any], proxy_config: Optional[Dict[str, Any]] = None):
        """
        初始化Telegram客户端
        
        Args:
            api_config: API配置信息，包含api_id和api_hash
            proxy_config: 代理配置信息（可选）
        """
        self.api_id = api_config['api_id']
        self.api_hash = api_config['api_hash']
        self.phone_number = api_config.get('phone_number')
        self.proxy_config = proxy_config
        self.client = None
    
    async def _setup_client(self) -> Client:
        """设置客户端并处理代理配置"""
        client_params = {
            'api_id': self.api_id,
            'api_hash': self.api_hash,
            'app_version': "TG Forwarder v1.0",
            'device_model': "PC",
            'system_version': "Windows",
            'name': 'tg_forwarder'
        }
        
        # 添加代理配置
        if self.proxy_config:
            proxy_type = self.proxy_config['proxy_type'].upper()
            proxy = {
                'scheme': proxy_type,
                'hostname': self.proxy_config['addr'],
                'port': self.proxy_config['port']
            }
            
            if 'username' in self.proxy_config and self.proxy_config['username']:
                proxy['username'] = self.proxy_config['username']
            
            if 'password' in self.proxy_config and self.proxy_config['password']:
                proxy['password'] = self.proxy_config['password']
            
            client_params['proxy'] = proxy
            logger.info(f"使用{proxy_type}代理: {self.proxy_config['addr']}:{self.proxy_config['port']}")
        
        return Client(**client_params)
    
    async def connect(self) -> None:
        """
        连接到Telegram API
        
        Raises:
            Exception: 连接失败时抛出
        """
        try:
            self.client = await self._setup_client()
            await self.client.connect()
            
            # 检查是否已经授权，方法是尝试获取自己的用户信息
            try:
                # 如果已经认证，这个调用会成功
                me = await self.client.get_me()
                logger.info(f"成功登录账号: {me.first_name} {me.last_name or ''} (@{me.username or ''})")
                return
            except Exception:
                # 需要登录
                if not self.phone_number:
                    self.phone_number = input("请输入您的电话号码 (包含国家代码，例如: +86123456789): ")
                
                sent_code = await self.client.send_code(self.phone_number)
                
                try:
                    code = input(f"请输入发送到 {self.phone_number} 的验证码: ")
                    await self.client.sign_in(self.phone_number, sent_code.phone_code_hash, code)
                except SessionPasswordNeeded:
                    password = input("请输入您的两步验证密码: ")
                    await self.client.check_password(password)
                
                # 登录成功，获取用户信息
                me = await self.client.get_me()
                logger.info(f"成功登录账号: {me.first_name} {me.last_name or ''} (@{me.username or ''})")
            
        except (AuthKeyUnregistered, AuthKeyDuplicated) as e:
            logger.error(f"认证失败: {str(e)}")
            # 删除会话文件并重试
            if os.path.exists("tg_forwarder.session"):
                os.remove("tg_forwarder.session")
                logger.info("已删除会话文件，请重新运行程序")
            raise
        
        except Exception as e:
            logger.error(f"连接Telegram API时出错: {str(e)}")
            raise
    
    async def disconnect(self) -> None:
        """断开与Telegram API的连接"""
        if self.client:
            await self.client.disconnect()
            logger.info("已断开与Telegram的连接")
    
    async def get_entity(self, channel_identifier: Union[str, int]) -> Union[dict, None]:
        """
        获取频道、群组或用户的详细信息
        
        Args:
            channel_identifier: 频道标识符，可以是用户名或ID
        
        Returns:
            dict: 实体信息
        """
        try:
            if isinstance(channel_identifier, int):
                # 对于数字ID，我们需要获取对应的chat
                chat = await self.client.get_chat(channel_identifier)
                return chat
            else:
                # 对于用户名
                chat = await self.client.get_chat(channel_identifier)
                return chat
        except FloodWait as e:
            logger.warning(f"触发Telegram限流，等待{e.value}秒...")
            await asyncio.sleep(e.value)
            return await self.get_entity(channel_identifier)
        except Exception as e:
            logger.error(f"获取实体信息时出错 ({channel_identifier}): {str(e)}")
            return None
    
    async def get_message(self, channel: Union[str, int], message_id: int) -> Optional[Message]:
        """
        获取指定频道的指定消息
        
        Args:
            channel: 频道标识符
            message_id: 消息ID
        
        Returns:
            Optional[Message]: 消息对象，如果消息不存在则返回None
        """
        try:
            message = await self.client.get_messages(channel, message_id)
            return message
        except FloodWait as e:
            logger.warning(f"触发Telegram限流，等待{e.value}秒...")
            await asyncio.sleep(e.value)
            return await self.get_message(channel, message_id)
        except Exception as e:
            logger.error(f"获取消息时出错 (频道: {channel}, 消息ID: {message_id}): {str(e)}")
            return None
    
    async def get_messages_range(self, channel: Union[str, int], start_id: int, end_id: int, batch_size: int = 100) -> List[Message]:
        """
        获取指定范围内的消息
        
        Args:
            channel: 频道标识符
            start_id: 起始消息ID
            end_id: 结束消息ID
            batch_size: 每批次获取的消息数量
        
        Returns:
            List[Message]: 消息列表
        """
        messages = []
        current_id = start_id
        
        while current_id <= end_id:
            next_id = min(current_id + batch_size - 1, end_id)
            ids = list(range(current_id, next_id + 1))
            
            try:
                batch = await self.client.get_messages(channel, ids)
                valid_messages = [msg for msg in batch if msg is not None]
                messages.extend(valid_messages)
                
                logger.info(f"已获取消息: {current_id}-{next_id} (有效: {len(valid_messages)})")
                
                current_id = next_id + 1
                
            except FloodWait as e:
                logger.warning(f"触发Telegram限流，等待{e.value}秒...")
                await asyncio.sleep(e.value)
                # 不增加current_id，重试当前批次
                continue
                
            except Exception as e:
                logger.error(f"获取批量消息时出错: {str(e)}")
                # 继续下一批
                current_id = next_id + 1
        
        return messages
    
    async def get_chat_history(self, channel: Union[str, int], limit: int = 100) -> List[Message]:
        """
        获取频道历史消息
        
        Args:
            channel: 频道标识符
            limit: 最大获取消息数量
        
        Returns:
            List[Message]: 消息列表
        """
        messages = []
        
        try:
            async for message in self.client.get_chat_history(channel, limit=limit):
                messages.append(message)
            
            logger.info(f"已获取频道历史消息: {len(messages)}条")
        
        except FloodWait as e:
            logger.warning(f"触发Telegram限流，等待{e.value}秒...")
            await asyncio.sleep(e.value)
            # 递归调用
            return await self.get_chat_history(channel, limit)
        
        except Exception as e:
            logger.error(f"获取频道历史消息时出错: {str(e)}")
        
        return messages
    
    async def get_latest_message_id(self, channel: Union[str, int]) -> Optional[int]:
        """
        获取频道最新消息ID
        
        Args:
            channel: 频道标识符
        
        Returns:
            Optional[int]: 最新消息ID，如果获取失败则返回None
        """
        try:
            messages = await self.get_chat_history(channel, limit=1)
            if messages:
                return messages[0].id
            return None
        except Exception as e:
            logger.error(f"获取最新消息ID时出错: {str(e)}")
            return None 
