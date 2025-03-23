"""
Telegram客户端插件包。

该包提供了与Telegram API的连接和管理功能，是其他功能插件的基础。
"""

from .client_plugin import ClientPlugin

__all__ = ['ClientPlugin']
