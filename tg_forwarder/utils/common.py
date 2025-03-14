"""
公共工具函数模块，提供各模块共用的工具函数
"""

import time
from typing import Union, Optional

def format_size(size_bytes: int) -> str:
    """
    将字节大小格式化为可读的字符串形式
    
    Args:
        size_bytes: 文件大小（字节）
    
    Returns:
        str: 格式化后的大小字符串，如 "1.23 MB"
    """
    if size_bytes < 1024:
        return f"{size_bytes} B"
    elif size_bytes < 1024 * 1024:
        return f"{size_bytes / 1024:.2f} KB"
    elif size_bytes < 1024 * 1024 * 1024:
        return f"{size_bytes / (1024 * 1024):.2f} MB"
    else:
        return f"{size_bytes / (1024 * 1024 * 1024):.2f} GB"

def format_time(seconds: float) -> str:
    """
    将秒数格式化为可读的时间形式
    
    Args:
        seconds: 秒数
    
    Returns:
        str: 格式化后的时间字符串，如 "1h 2m 3s"
    """
    if seconds < 60:
        return f"{seconds:.2f}s"
    elif seconds < 3600:
        m, s = divmod(seconds, 60)
        return f"{int(m)}m {int(s)}s"
    else:
        h, remainder = divmod(seconds, 3600)
        m, s = divmod(remainder, 60)
        return f"{int(h)}h {int(m)}m {int(s)}s"

def get_client_instance(client_obj):
    """
    统一获取有效的客户端实例
    
    Args:
        client_obj: 客户端对象，可能是TelegramClient实例或pyrogram.Client实例
    
    Returns:
        有效的Pyrogram客户端实例
    
    Raises:
        ValueError: 如果找不到有效的客户端实例
    """
    # 检查是否有.client属性 (TelegramClient类型)
    if hasattr(client_obj, 'client') and client_obj.client is not None:
        return client_obj.client
        
    # 如果是pyrogram.Client实例
    if client_obj is not None and hasattr(client_obj, 'get_me'):
        return client_obj
        
    # 如果都不可用，抛出错误
    raise ValueError("无法获取有效的客户端实例") 