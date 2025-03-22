"""
核心实现包，包含各种接口的具体实现类
"""

from tg_forwarder.core.config_manager import ConfigManager
from tg_forwarder.core.logger import Logger
from tg_forwarder.core.status_tracker import StatusTracker
from tg_forwarder.core.telegram_client import TelegramClient
from tg_forwarder.core.downloader import Downloader
from tg_forwarder.core.uploader import Uploader
from tg_forwarder.core.forwarder import Forwarder
from tg_forwarder.core.json_storage import JsonStorage
from tg_forwarder.core.history_tracker import HistoryTracker
from tg_forwarder.core.application import Application
from tg_forwarder.core.channel_parser import ChannelParser
from tg_forwarder.core.channel_utils import ChannelUtils
from tg_forwarder.core.channel_factory import (
    get_channel_parser,
    get_channel_utils,
    get_actual_chat_id,
    parse_channel,
    format_channel,
    is_channel_valid,
    can_forward_from,
    can_forward_to,
    filter_channels
)

__all__ = [
    'ConfigManager',
    'Logger',
    'StatusTracker',
    'TelegramClient',
    'Downloader',
    'Uploader',
    'Forwarder',
    'Application',
    'JsonStorage',
    'HistoryTracker',
    'ChannelParser',
    'ChannelUtils',
    # 工厂函数
    'get_channel_parser',
    'get_channel_utils',
    # 常用工具函数
    'get_actual_chat_id',
    'parse_channel',
    'format_channel',
    'is_channel_valid',
    'can_forward_from',
    'can_forward_to',
    'filter_channels'
] 