"""
事件类型定义模块。

本模块定义了应用中所有可能的事件类型，作为事件总线的事件标识符。
"""

from enum import Enum
from typing import Dict, Any, List

# 应用生命周期事件
APP_INIT = "app.init"              # 应用初始化
APP_READY = "app.ready"            # 应用就绪
APP_SHUTDOWN = "app.shutdown"      # 应用关闭
APP_ERROR = "app.error"            # 应用错误

# 配置相关事件
CONFIG_LOADED = "config.loaded"    # 配置加载完成
CONFIG_CHANGED = "config.changed"  # 配置变更
CONFIG_ERROR = "config.error"      # 配置错误

# 插件相关事件
PLUGIN_LOADED = "plugin.loaded"    # 插件加载
PLUGIN_UNLOADED = "plugin.unloaded"  # 插件卸载
PLUGIN_ERROR = "plugin.error"      # 插件错误

# Telegram客户端事件
CLIENT_CONNECTING = "client.connecting"      # 客户端连接中
CLIENT_CONNECTED = "client.connected"        # 客户端已连接
CLIENT_DISCONNECTED = "client.disconnected"  # 客户端断开连接
CLIENT_ERROR = "client.error"                # 客户端错误

# 消息事件
MESSAGE_RECEIVED = "message.received"        # 收到消息
MESSAGE_SENT = "message.sent"                # 发送消息
MESSAGE_EDITED = "message.edited"            # 消息编辑
MESSAGE_DELETED = "message.deleted"          # 消息删除

# 频道事件
CHANNEL_JOINED = "channel.joined"            # 加入频道
CHANNEL_LEFT = "channel.left"                # 离开频道
CHANNEL_CREATED = "channel.created"          # 创建频道
CHANNEL_DELETED = "channel.deleted"          # 删除频道
CHANNEL_UPDATED = "channel.updated"          # 频道更新

# 转发事件
FORWARD_STARTED = "forward.started"          # 开始转发
FORWARD_COMPLETED = "forward.completed"      # 转发完成
FORWARD_FAILED = "forward.failed"            # 转发失败
FORWARD_PROGRESS = "forward.progress"        # 转发进度更新

# 媒体下载事件
DOWNLOAD_STARTED = "download.started"        # 开始下载
DOWNLOAD_PROGRESS = "download.progress"      # 下载进度
DOWNLOAD_COMPLETED = "download.completed"    # 下载完成
DOWNLOAD_FAILED = "download.failed"          # 下载失败

# 媒体上传事件
UPLOAD_STARTED = "upload.started"            # 开始上传
UPLOAD_PROGRESS = "upload.progress"          # 上传进度
UPLOAD_COMPLETED = "upload.completed"        # 上传完成
UPLOAD_FAILED = "upload.failed"              # 上传失败

# 任务队列事件
TASK_CREATED = "task.created"                # 任务创建
TASK_STARTED = "task.started"                # 任务开始
TASK_COMPLETED = "task.completed"            # 任务完成
TASK_FAILED = "task.failed"                  # 任务失败
TASK_CANCELLED = "task.cancelled"            # 任务取消
TASK_PROGRESS = "task.progress"              # 任务进度

# UI事件
UI_READY = "ui.ready"                        # UI就绪
UI_ACTION = "ui.action"                      # UI操作
UI_UPDATED = "ui.updated"                    # UI更新
UI_ERROR = "ui.error"                        # UI错误


class EventCategory(Enum):
    """事件类别枚举"""
    APPLICATION = "application"    # 应用事件
    CONFIG = "config"              # 配置事件
    PLUGIN = "plugin"              # 插件事件
    CLIENT = "client"              # 客户端事件
    MESSAGE = "message"            # 消息事件
    CHANNEL = "channel"            # 频道事件
    FORWARD = "forward"            # 转发事件
    DOWNLOAD = "download"          # 下载事件
    UPLOAD = "upload"              # 上传事件
    TASK = "task"                  # 任务事件
    UI = "ui"                      # UI事件


# 事件类别映射
EVENT_CATEGORIES: Dict[str, EventCategory] = {
    # 应用事件
    APP_INIT: EventCategory.APPLICATION,
    APP_READY: EventCategory.APPLICATION,
    APP_SHUTDOWN: EventCategory.APPLICATION,
    APP_ERROR: EventCategory.APPLICATION,
    
    # 配置事件
    CONFIG_LOADED: EventCategory.CONFIG,
    CONFIG_CHANGED: EventCategory.CONFIG,
    CONFIG_ERROR: EventCategory.CONFIG,
    
    # 插件事件
    PLUGIN_LOADED: EventCategory.PLUGIN,
    PLUGIN_UNLOADED: EventCategory.PLUGIN,
    PLUGIN_ERROR: EventCategory.PLUGIN,
    
    # 客户端事件
    CLIENT_CONNECTING: EventCategory.CLIENT,
    CLIENT_CONNECTED: EventCategory.CLIENT,
    CLIENT_DISCONNECTED: EventCategory.CLIENT,
    CLIENT_ERROR: EventCategory.CLIENT,
    
    # 消息事件
    MESSAGE_RECEIVED: EventCategory.MESSAGE,
    MESSAGE_SENT: EventCategory.MESSAGE,
    MESSAGE_EDITED: EventCategory.MESSAGE,
    MESSAGE_DELETED: EventCategory.MESSAGE,
    
    # 频道事件
    CHANNEL_JOINED: EventCategory.CHANNEL,
    CHANNEL_LEFT: EventCategory.CHANNEL,
    CHANNEL_CREATED: EventCategory.CHANNEL,
    CHANNEL_DELETED: EventCategory.CHANNEL,
    CHANNEL_UPDATED: EventCategory.CHANNEL,
    
    # 转发事件
    FORWARD_STARTED: EventCategory.FORWARD,
    FORWARD_COMPLETED: EventCategory.FORWARD,
    FORWARD_FAILED: EventCategory.FORWARD,
    FORWARD_PROGRESS: EventCategory.FORWARD,
    
    # 下载事件
    DOWNLOAD_STARTED: EventCategory.DOWNLOAD,
    DOWNLOAD_PROGRESS: EventCategory.DOWNLOAD,
    DOWNLOAD_COMPLETED: EventCategory.DOWNLOAD,
    DOWNLOAD_FAILED: EventCategory.DOWNLOAD,
    
    # 上传事件
    UPLOAD_STARTED: EventCategory.UPLOAD,
    UPLOAD_PROGRESS: EventCategory.UPLOAD,
    UPLOAD_COMPLETED: EventCategory.UPLOAD,
    UPLOAD_FAILED: EventCategory.UPLOAD,
    
    # 任务事件
    TASK_CREATED: EventCategory.TASK,
    TASK_STARTED: EventCategory.TASK,
    TASK_COMPLETED: EventCategory.TASK,
    TASK_FAILED: EventCategory.TASK,
    TASK_CANCELLED: EventCategory.TASK,
    TASK_PROGRESS: EventCategory.TASK,
    
    # UI事件
    UI_READY: EventCategory.UI,
    UI_ACTION: EventCategory.UI,
    UI_UPDATED: EventCategory.UI,
    UI_ERROR: EventCategory.UI,
}


def get_event_category(event_type: str) -> EventCategory:
    """
    获取事件类型对应的类别。
    
    Args:
        event_type: 事件类型标识符
        
    Returns:
        EventCategory: 事件类别
        
    Raises:
        ValueError: 如果事件类型未注册
    """
    if event_type not in EVENT_CATEGORIES:
        raise ValueError(f"未知的事件类型: {event_type}")
    
    return EVENT_CATEGORIES[event_type]


def create_event_data(event_type: str, **kwargs) -> Dict[str, Any]:
    """
    创建事件数据字典。
    
    Args:
        event_type: 事件类型
        **kwargs: 事件数据键值对
        
    Returns:
        Dict[str, Any]: 事件数据字典，包含事件类型和时间戳
    """
    import time
    
    # 基础事件数据
    event_data = {
        "event_type": event_type,
        "category": get_event_category(event_type).value,
        "timestamp": time.time(),
    }
    
    # 添加自定义数据
    event_data.update(kwargs)
    
    return event_data


# 按类别获取所有事件类型
def get_events_by_category(category: EventCategory) -> List[str]:
    """
    获取指定类别的所有事件类型。
    
    Args:
        category: 事件类别
        
    Returns:
        List[str]: 事件类型列表
    """
    return [
        event_type for event_type, cat in EVENT_CATEGORIES.items()
        if cat == category
    ] 