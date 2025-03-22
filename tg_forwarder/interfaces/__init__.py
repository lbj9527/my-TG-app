"""
接口包，定义系统中各组件的接口抽象
这个包遵循依赖倒置原则，高层模块通过这些抽象接口与低层模块交互
"""

from tg_forwarder.interfaces.client_interface import TelegramClientInterface
from tg_forwarder.interfaces.downloader_interface import DownloaderInterface
from tg_forwarder.interfaces.uploader_interface import UploaderInterface
from tg_forwarder.interfaces.config_interface import ConfigInterface
from tg_forwarder.interfaces.status_tracker_interface import StatusTrackerInterface
from tg_forwarder.interfaces.storage_interface import StorageInterface
from tg_forwarder.interfaces.logger_interface import LoggerInterface
from tg_forwarder.interfaces.forwarder_interface import ForwarderInterface
from tg_forwarder.interfaces.application_interface import ApplicationInterface
from tg_forwarder.interfaces.json_storage_interface import JsonStorageInterface
from tg_forwarder.interfaces.history_tracker_interface import HistoryTrackerInterface

__all__ = [
    'TelegramClientInterface',
    'DownloaderInterface',
    'UploaderInterface',
    'ConfigInterface',
    'StatusTrackerInterface',
    'StorageInterface',
    'LoggerInterface',
    'ForwarderInterface',
    'ApplicationInterface',
    'JsonStorageInterface',
    'HistoryTrackerInterface',
] 