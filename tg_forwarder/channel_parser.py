"""
频道链接解析模块，负责解析各种格式的频道链接
"""

import re
from typing import Optional, Tuple, Union, Dict, List, Any
from urllib.parse import urlparse
import logging

from pyrogram import Client
from pyrogram.types import Chat

# 获取日志记录器
logger = logging.getLogger("channel_parser")

class ChannelParseError(Exception):
    """频道解析错误异常"""
    pass

class ChannelValidator:
    """频道验证器，负责验证频道的有效性和可用性"""
    
    def __init__(self, client: Client):
        """
        初始化频道验证器
        
        Args:
            client: Pyrogram客户端实例
        """
        self.client = client
        self.channel_forward_status_cache = {}
    
    async def validate_channel(self, channel: str) -> Tuple[bool, str, Optional[Chat]]:
        """
        验证单个频道是否存在且有权限
        
        Args:
            channel: 频道标识符，可以是URL、用户名或频道ID
            
        Returns:
            Tuple[bool, str, Optional[Chat]]: (是否有效, 错误信息, 频道对象)
        """
        # 处理URL格式的频道标识符
        actual_channel = channel
        if isinstance(channel, str) and channel.startswith('https://t.me/'):
            # 提取用户名部分（不包括https://t.me/）
            username = channel.replace('https://t.me/', '')
            # 如果是私有频道邀请链接（以+开头）
            if '+' in username or 'joinchat' in username:
                actual_channel = channel  # 保持原样
            else:
                # 普通公开频道链接，只使用用户名部分
                actual_channel = username
        
        try:
            # 尝试获取频道信息
            chat = await self.client.get_chat(actual_channel)
            
            # 检查是否禁止转发
            can_forward = True
            if hasattr(chat, 'has_protected_content') and chat.has_protected_content:
                can_forward = False
                self.channel_forward_status_cache[str(channel)] = False
                logger.info(f"频道验证成功: {channel} ({chat.title}) - 禁止转发 (has_protected_content=True)")
            else:
                self.channel_forward_status_cache[str(channel)] = True
                logger.info(f"频道验证成功: {channel} ({chat.title}) - 允许转发 (has_protected_content=False)")
            
            return True, "", chat
            
        except Exception as e:
            error_msg = str(e)
            if "USERNAME_INVALID" in error_msg or "USERNAME_NOT_OCCUPIED" in error_msg:
                logger.error(f"频道验证失败: {channel} - {error_msg[:80]}")
                return False, error_msg, None
            elif "Peer id invalid" in error_msg:
                logger.error(f"频道验证失败: {channel} - 无效的ID格式")
                return False, f"无效的ID格式: {error_msg}", None
            else:
                logger.error(f"频道验证失败: {channel} - {error_msg[:80]}")
                return False, error_msg, None
    
    async def validate_channels(self, channels: List[str]) -> Tuple[List[str], List[str], Dict[str, bool]]:
        """
        批量验证频道是否有效
        
        Args:
            channels: 频道标识符列表
            
        Returns:
            Tuple[List[str], List[str], Dict[str, bool]]: (有效频道列表, 无效频道列表, 频道转发状态字典)
        """
        if not channels:
            logger.error("没有设置目标频道")
            return [], [], {}
            
        valid_channels = []
        invalid_channels = []
        protected_channels = []  # 受保护的频道（禁止转发）
        forward_status = {}  # 记录每个频道的转发状态
        
        # 验证每个频道
        for channel in channels:
            valid, error_msg, chat = await self.validate_channel(channel)
            
            if valid:
                valid_channels.append(channel)
                
                # 检查是否禁止转发
                if hasattr(chat, 'has_protected_content') and chat.has_protected_content:
                    protected_channels.append(channel)
                    forward_status[str(channel)] = False
                else:
                    forward_status[str(channel)] = True
            else:
                invalid_channels.append(channel)
        
        # 输出验证结果
        if invalid_channels:
            logger.warning(f"⚠️ 发现 {len(invalid_channels)} 个无效频道: {', '.join(invalid_channels)}")
            print("\n" + "="*60)
            print(f"⚠️ 警告: {len(invalid_channels)}/{len(channels)} 个频道验证失败")
            print("💡 这些无效频道将被自动跳过")
            print("="*60 + "\n")
            
        # 输出禁止转发的频道
        if protected_channels:
            logger.warning(f"⚠️ 发现 {len(protected_channels)} 个禁止转发的频道: {', '.join(protected_channels)}")
            print("\n" + "="*60)
            print(f"⚠️ 注意: {len(protected_channels)}/{len(valid_channels)} 个有效频道禁止转发")
            print("💡 这些频道可以上传文件，但不能用作转发源")
            print("="*60 + "\n")
            
            # 如果第一个频道禁止转发，输出更明确的提示
            if protected_channels and channels[0] in protected_channels:
                logger.warning("⚠️ 第一个目标频道禁止转发，系统将尝试查找其他可转发的频道作为源")
                
        # 更新缓存
        self.channel_forward_status_cache.update(forward_status)
        
        return valid_channels, invalid_channels, forward_status
    
    def get_forward_status(self, channel: str, default: bool = True) -> bool:
        """
        获取频道的转发状态
        
        Args:
            channel: 频道标识符
            default: 默认状态
            
        Returns:
            bool: 是否允许转发
        """
        return self.channel_forward_status_cache.get(str(channel), default)
    
    def get_actual_chat_id(self, channel: str) -> str:
        """
        根据频道标识符获取实际的聊天ID
        
        Args:
            channel: 频道标识符
            
        Returns:
            str: 实际的聊天ID
        """
        if isinstance(channel, str) and channel.startswith('https://t.me/'):
            username = channel.replace('https://t.me/', '')
            if '+' in username or 'joinchat' in username:
                return channel  # 保持原样
            else:
                return username
        return channel

class ChannelParser:
    """频道链接解析器"""
    
    @staticmethod
    def parse_channel(channel_identifier: str) -> Tuple[Union[str, int], Optional[int]]:
        """
        解析频道标识符，支持多种格式
        
        Args:
            channel_identifier: 频道标识符，支持以下格式：
                - 公有频道/群组链接：https://t.me/channel_name
                - 用户名：@channel_name
                - 私有频道/群组链接：https://t.me/c/channel_id/message_id
                - 公有频道消息链接：https://t.me/channel_name/message_id
                - 私有频道邀请链接：https://t.me/+invite_code
                - 私有频道邀请码: +invite_code
                - 带前缀的私有频道链接: @https://t.me/+invite_code
        
        Returns:
            Tuple[Union[str, int], Optional[int]]: (频道标识符, 消息ID)
                - 对于公有频道，返回频道用户名和可能的消息ID
                - 对于私有频道，返回频道ID(int)和可能的消息ID
                - 对于私有频道邀请链接，返回邀请链接字符串和None
        
        Raises:
            ChannelParseError: 当无法解析频道标识符时抛出
        """
        original_identifier = channel_identifier
        
        # 处理带@前缀的链接，例如 @https://t.me/+invite_code
        if channel_identifier.startswith('@https://'):
            channel_identifier = channel_identifier[1:]  # 去掉@前缀
        
        # 处理纯+开头的邀请码
        if channel_identifier.startswith('+') and '/' not in channel_identifier:
            # 这是私有频道的邀请码
            return f"https://t.me/{channel_identifier}", None
        
        # 处理@开头的用户名
        if channel_identifier.startswith('@'):
            return channel_identifier[1:], None
        
        # 处理URL
        if channel_identifier.startswith(('https://', 'http://')):
            try:
                parsed_url = urlparse(channel_identifier)
                path_parts = parsed_url.path.strip('/').split('/')
                
                # 检查域名是否为t.me
                if parsed_url.netloc != 't.me':
                    raise ChannelParseError(f"不支持的域名: {parsed_url.netloc}")
                
                # 处理私有频道邀请链接: https://t.me/+invite_code
                if len(path_parts) == 1 and path_parts[0].startswith('+'):
                    return channel_identifier, None
                
                # 处理公有频道链接: https://t.me/channel_name
                if len(path_parts) == 1:
                    return path_parts[0], None
                
                # 处理私有频道链接: https://t.me/c/channel_id/message_id
                if len(path_parts) >= 2 and path_parts[0] == 'c':
                    try:
                        channel_id = int(path_parts[1])
                        message_id = int(path_parts[2]) if len(path_parts) > 2 else None
                        return channel_id, message_id
                    except (ValueError, IndexError):
                        raise ChannelParseError(f"无效的私有频道链接: {channel_identifier}")
                
                # 处理公有频道消息链接: https://t.me/channel_name/message_id
                if len(path_parts) == 2:
                    channel_name = path_parts[0]
                    try:
                        message_id = int(path_parts[1])
                        return channel_name, message_id
                    except ValueError:
                        raise ChannelParseError(f"无效的消息ID: {path_parts[1]}")
                
                raise ChannelParseError(f"无法解析频道链接: {channel_identifier}")
            
            except Exception as e:
                if isinstance(e, ChannelParseError):
                    raise
                raise ChannelParseError(f"解析频道链接时出错: {str(e)}")
        
        # 尝试将输入解析为数字（频道ID）
        try:
            return int(channel_identifier), None
        except ValueError:
            pass
        
        # 如果没有前缀，假设是频道用户名
        if re.match(r'^[a-zA-Z][a-zA-Z0-9_]{3,}$', channel_identifier):
            return channel_identifier, None
        
        raise ChannelParseError(f"无法识别的频道标识符格式: {original_identifier}")
    
    @staticmethod
    def format_channel_identifier(identifier: Union[str, int]) -> str:
        """
        格式化频道标识符为友好显示格式
        
        Args:
            identifier: 频道标识符
        
        Returns:
            str: 格式化后的频道标识符
        """
        if isinstance(identifier, int):
            return f"私有频道({identifier})"
        
        # 处理私有频道邀请链接
        if isinstance(identifier, str) and ('t.me/+' in identifier or identifier.startswith('+')):
            return f"私有频道(邀请链接)"
            
        return f"@{identifier}"
        
    @staticmethod
    def filter_channels(channels: List[str]) -> List[str]:
        """
        过滤频道列表，移除明显无效的频道标识符
        
        Args:
            channels: 频道标识符列表
            
        Returns:
            List[str]: 过滤后的频道标识符列表
        """
        if not channels:
            return []
            
        filtered_channels = []
        filtered_out = []
        
        for channel in channels:
            # 如果为空，跳过
            if not channel or not channel.strip():
                filtered_out.append(channel)
                continue
                
            # 标准化频道
            channel = channel.strip()
            
            # 去除@前缀便于判断
            channel_name = channel[1:] if channel.startswith('@') else channel
            
            # 如果是私有频道邀请链接，直接保留
            if channel.startswith('https://t.me/+') or channel.startswith('https://t.me/joinchat/'):
                filtered_channels.append(channel)
                continue
                
            # 如果是完整的公开频道链接，保留
            if channel.startswith('https://t.me/') and not '+' in channel.replace('https://t.me/', ''):
                filtered_channels.append(channel)
                continue
                
            # 如果是纯+开头的邀请码，保留
            if channel.startswith('+') and len(channel) > 1:
                filtered_channels.append(channel)
                continue
                
            # 如果是普通公开频道用户名（包括@前缀的形式）
            if channel.startswith('@'):
                if len(channel) > 4 and re.match(r'^@[a-zA-Z][a-zA-Z0-9_]{3,}$', channel):
                    filtered_channels.append(channel)
                    continue
                else:
                    logger.warning(f"频道名 {channel} 不符合Telegram命名规则，将被跳过")
                    filtered_out.append(channel)
                    continue
                    
            # 如果是不带@的用户名
            if re.match(r'^[a-zA-Z][a-zA-Z0-9_]{3,}$', channel):
                filtered_channels.append(channel)
                continue
                
            # 检查是否是数字ID（私有频道ID）
            try:
                int(channel)
                filtered_channels.append(channel)
                continue
            except ValueError:
                pass
                
            # 其他格式，视为无效
            logger.warning(f"频道标识符 {channel} 格式无效，将被跳过")
            filtered_out.append(channel)
            
        # 输出过滤结果
        if filtered_out:
            logger.info(f"已过滤 {len(filtered_out)} 个无效频道标识符")
            
        return filtered_channels 