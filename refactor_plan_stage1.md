# Telegram转发工具重构计划 - 第一阶段实现指南

## 第一阶段：准备工作(3天)

这一阶段的目标是创建基础架构，包括目录结构、核心组件和基本接口定义。这些将为后续阶段提供基础支持。

### 任务1.1：创建新的目录结构(0.5天)

#### 步骤1：创建项目根目录
```bash
mkdir -p tg_app
cd tg_app
```

#### 步骤2：创建基本模块目录
```bash
# 创建核心模块目录
mkdir -p core
touch core/__init__.py

# 创建插件模块目录
mkdir -p plugins
touch plugins/__init__.py
mkdir -p plugins/client plugins/forward plugins/downloader plugins/uploader plugins/utils
touch plugins/client/__init__.py plugins/forward/__init__.py plugins/downloader/__init__.py plugins/uploader/__init__.py plugins/utils/__init__.py

# 创建事件模块目录
mkdir -p events
touch events/__init__.py

# 创建工具模块目录
mkdir -p utils
touch utils/__init__.py

# 创建配置目录
mkdir -p config

# 创建入口脚本
touch __init__.py
touch main.py
```

#### 步骤3：创建空的核心文件
```bash
touch core/application.py core/event_bus.py core/plugin_manager.py core/context.py core/config_manager.py
touch plugins/base.py
touch events/event_types.py
touch utils/logger.py utils/helpers.py
```

#### 步骤4：初始化配置文件
```bash
# 从现有项目复制配置文件
cp /path/to/your/config.ini config/default_config.ini
```

### 任务1.2：设计核心抽象(1天)

#### 1.2.1 事件总线(EventBus)接口设计

```python
# tg_app/core/event_bus.py (接口部分)
import asyncio
from typing import Dict, List, Any, Callable, Awaitable, Optional

class EventBus:
    """事件总线，负责事件的发布和订阅"""
    
    async def subscribe(self, event_type: str, callback: Callable[[Dict[str, Any]], Awaitable[None]]) -> None:
        """
        订阅事件
        
        Args:
            event_type: 事件类型
            callback: 回调函数
        """
        pass
    
    async def unsubscribe(self, event_type: str, callback: Callable[[Dict[str, Any]], Awaitable[None]]) -> bool:
        """
        取消事件订阅
        
        Args:
            event_type: 事件类型
            callback: 回调函数
            
        Returns:
            bool: 是否成功取消订阅
        """
        pass
    
    async def publish(self, event_type: str, data: Optional[Dict[str, Any]] = None) -> None:
        """
        发布事件
        
        Args:
            event_type: 事件类型
            data: 事件数据
        """
        pass
```

#### 1.2.2 插件管理器(PluginManager)接口设计

```python
# tg_app/core/plugin_manager.py (接口部分)
from typing import Dict, List, Any, Optional

from tg_app.plugins.base import PluginBase
from tg_app.core.event_bus import EventBus

class PluginManager:
    """插件管理器，负责插件的加载、卸载和管理"""
    
    async def load_plugin(self, plugin_path: str) -> Optional[PluginBase]:
        """
        加载插件
        
        Args:
            plugin_path: 插件路径，格式为"包.模块.类名"
            
        Returns:
            Optional[PluginBase]: 加载的插件实例
        """
        pass
    
    async def activate_plugin(self, plugin_id: str) -> bool:
        """
        激活插件
        
        Args:
            plugin_id: 插件ID
            
        Returns:
            bool: 是否成功激活
        """
        pass
    
    async def deactivate_plugin(self, plugin_id: str) -> bool:
        """
        停用插件
        
        Args:
            plugin_id: 插件ID
            
        Returns:
            bool: 是否成功停用
        """
        pass
    
    async def unload_plugin(self, plugin_id: str) -> bool:
        """
        卸载插件
        
        Args:
            plugin_id: 插件ID
            
        Returns:
            bool: 是否成功卸载
        """
        pass
    
    async def get_plugin(self, plugin_id: str) -> Optional[PluginBase]:
        """
        获取插件实例
        
        Args:
            plugin_id: 插件ID
            
        Returns:
            Optional[PluginBase]: 插件实例
        """
        pass
```

#### 1.2.3 应用上下文(Context)接口设计

```python
# tg_app/core/context.py (接口部分)
from typing import Dict, Any, Optional

from tg_app.core.event_bus import EventBus
from tg_app.core.plugin_manager import PluginManager
from tg_app.core.config_manager import ConfigManager

class Context:
    """应用上下文，提供全局访问点"""
    
    def set_shared_data(self, key: str, value: Any) -> None:
        """
        设置共享数据
        
        Args:
            key: 数据键
            value: 数据值
        """
        pass
    
    def get_shared_data(self, key: str, default: Any = None) -> Any:
        """
        获取共享数据
        
        Args:
            key: 数据键
            default: 默认值
            
        Returns:
            Any: 数据值
        """
        pass
    
    def remove_shared_data(self, key: str) -> bool:
        """
        移除共享数据
        
        Args:
            key: 数据键
            
        Returns:
            bool: 是否成功移除
        """
        pass
```

#### 1.2.4 插件基类(PluginBase)接口设计

```python
# tg_app/plugins/base.py (接口部分)
from abc import ABC, abstractmethod
from typing import Dict, List, Any, Optional

from tg_app.core.event_bus import EventBus

class PluginBase(ABC):
    """插件基类，所有插件必须继承此类"""
    
    @property
    @abstractmethod
    def id(self) -> str:
        """插件唯一标识符"""
        pass
        
    @property
    @abstractmethod
    def name(self) -> str:
        """插件名称"""
        pass
        
    @property
    @abstractmethod
    def description(self) -> str:
        """插件描述"""
        pass
    
    async def initialize(self) -> None:
        """初始化插件"""
        pass
    
    async def shutdown(self) -> None:
        """关闭插件"""
        pass
```

### 任务1.3：定义事件类型(0.5天)

#### 步骤1：创建事件类型定义文件

```python
# tg_app/events/event_types.py

# 应用事件
APP_INIT = "app.init"                 # 应用初始化
APP_START = "app.start"               # 应用启动
APP_SHUTDOWN = "app.shutdown"         # 应用关闭
APP_ERROR = "app.error"               # 应用错误

# 插件事件
PLUGIN_LOADED = "plugin.loaded"       # 插件加载
PLUGIN_ACTIVATED = "plugin.activated" # 插件激活
PLUGIN_DEACTIVATED = "plugin.deactivated"  # 插件停用
PLUGIN_UNLOADED = "plugin.unloaded"   # 插件卸载
PLUGIN_ERROR = "plugin.error"         # 插件错误

# 配置事件
CONFIG_LOADED = "config.loaded"       # 配置加载
CONFIG_CHANGED = "config.changed"     # 配置改变
CONFIG_ERROR = "config.error"         # 配置错误

# 客户端事件
CLIENT_CONNECT = "client.connect"     # 客户端连接
CLIENT_DISCONNECT = "client.disconnect"  # 客户端断开
CLIENT_AUTH = "client.auth"           # 客户端认证
CLIENT_ERROR = "client.error"         # 客户端错误

# 频道事件
CHANNEL_VALIDATE = "channel.validate"  # 频道验证
CHANNEL_STATUS_CHANGED = "channel.status_changed"  # 频道状态改变
CHANNEL_ERROR = "channel.error"        # 频道错误

# 转发事件
FORWARD_START = "forward.start"        # 转发开始
FORWARD_PROGRESS = "forward.progress"  # 转发进度
FORWARD_COMPLETE = "forward.complete"  # 转发完成
FORWARD_ERROR = "forward.error"        # 转发错误

# 下载事件
DOWNLOAD_START = "download.start"      # 下载开始
DOWNLOAD_PROGRESS = "download.progress"  # 下载进度
DOWNLOAD_COMPLETE = "download.complete"  # 下载完成
DOWNLOAD_ERROR = "download.error"      # 下载错误

# 上传事件
UPLOAD_START = "upload.start"          # 上传开始
UPLOAD_PROGRESS = "upload.progress"    # 上传进度
UPLOAD_COMPLETE = "upload.complete"    # 上传完成
UPLOAD_ERROR = "upload.error"          # 上传错误

# 消息事件
MESSAGE_FETCHED = "message.fetched"    # 消息获取
MESSAGE_PROCESSED = "message.processed"  # 消息处理
MESSAGE_GROUPED = "message.grouped"    # 消息分组
MESSAGE_ERROR = "message.error"        # 消息错误

# 任务事件
TASK_CREATED = "task.created"          # 任务创建
TASK_STARTED = "task.started"          # 任务开始
TASK_PROGRESS = "task.progress"        # 任务进度
TASK_COMPLETED = "task.completed"      # 任务完成
TASK_FAILED = "task.failed"            # 任务失败
```

#### 步骤2：在事件模块的__init__.py导出事件类型

```python
# tg_app/events/__init__.py
from tg_app.events.event_types import *

__all__ = [
    # 应用事件
    'APP_INIT', 'APP_START', 'APP_SHUTDOWN', 'APP_ERROR',
    
    # 插件事件
    'PLUGIN_LOADED', 'PLUGIN_ACTIVATED', 'PLUGIN_DEACTIVATED', 'PLUGIN_UNLOADED', 'PLUGIN_ERROR',
    
    # 配置事件
    'CONFIG_LOADED', 'CONFIG_CHANGED', 'CONFIG_ERROR',
    
    # 客户端事件
    'CLIENT_CONNECT', 'CLIENT_DISCONNECT', 'CLIENT_AUTH', 'CLIENT_ERROR',
    
    # 频道事件
    'CHANNEL_VALIDATE', 'CHANNEL_STATUS_CHANGED', 'CHANNEL_ERROR',
    
    # 转发事件
    'FORWARD_START', 'FORWARD_PROGRESS', 'FORWARD_COMPLETE', 'FORWARD_ERROR',
    
    # 下载事件
    'DOWNLOAD_START', 'DOWNLOAD_PROGRESS', 'DOWNLOAD_COMPLETE', 'DOWNLOAD_ERROR',
    
    # 上传事件
    'UPLOAD_START', 'UPLOAD_PROGRESS', 'UPLOAD_COMPLETE', 'UPLOAD_ERROR',
    
    # 消息事件
    'MESSAGE_FETCHED', 'MESSAGE_PROCESSED', 'MESSAGE_GROUPED', 'MESSAGE_ERROR',
    
    # 任务事件
    'TASK_CREATED', 'TASK_STARTED', 'TASK_PROGRESS', 'TASK_COMPLETED', 'TASK_FAILED'
]
```

### 任务1.4：实现核心组件(1天)

#### 1.4.1 实现事件总线(EventBus)

```python
# tg_app/core/event_bus.py
import asyncio
from typing import Dict, List, Any, Callable, Awaitable, Optional

class EventBus:
    """事件总线，负责事件的发布和订阅"""
    
    def __init__(self):
        """初始化事件总线"""
        self._subscribers = {}
        self._lock = asyncio.Lock()
    
    async def subscribe(self, event_type: str, callback: Callable[[Dict[str, Any]], Awaitable[None]]) -> None:
        """
        订阅事件
        
        Args:
            event_type: 事件类型
            callback: 回调函数
        """
        async with self._lock:
            if event_type not in self._subscribers:
                self._subscribers[event_type] = []
            self._subscribers[event_type].append(callback)
    
    async def unsubscribe(self, event_type: str, callback: Callable[[Dict[str, Any]], Awaitable[None]]) -> bool:
        """
        取消事件订阅
        
        Args:
            event_type: 事件类型
            callback: 回调函数
            
        Returns:
            bool: 是否成功取消订阅
        """
        async with self._lock:
            if event_type in self._subscribers and callback in self._subscribers[event_type]:
                self._subscribers[event_type].remove(callback)
                return True
            return False
    
    async def publish(self, event_type: str, data: Optional[Dict[str, Any]] = None) -> None:
        """
        发布事件
        
        Args:
            event_type: 事件类型
            data: 事件数据
        """
        if not data:
            data = {}
            
        data["event_type"] = event_type
        
        if event_type in self._subscribers:
            tasks = []
            for callback in self._subscribers[event_type]:
                tasks.append(self._safe_callback(callback, data))
            
            if tasks:
                await asyncio.gather(*tasks)
    
    async def _safe_callback(self, callback: Callable[[Dict[str, Any]], Awaitable[None]], data: Dict[str, Any]) -> None:
        """
        安全执行回调函数
        
        Args:
            callback: 回调函数
            data: 事件数据
        """
        try:
            await callback(data)
        except Exception as e:
            # 暂时使用print输出错误，后面会替换为日志
            print(f"事件回调执行错误: {str(e)}")
```

#### 1.4.2 实现公共日志模块

```python
# tg_app/utils/logger.py
import os
import sys
import logging
from pathlib import Path
from typing import Dict, Any, Optional

class Logger:
    """日志工具类，负责日志记录"""
    
    _instance = None
    
    def __new__(cls):
        """单例模式"""
        if cls._instance is None:
            cls._instance = super(Logger, cls).__new__(cls)
            cls._instance._initialized = False
        return cls._instance
    
    def __init__(self):
        """初始化日志工具"""
        if self._initialized:
            return
            
        self._loggers = {}
        self._default_level = logging.INFO
        self._setup_default_logger()
        self._initialized = True
    
    def _setup_default_logger(self):
        """设置默认日志配置"""
        # 设置默认处理器
        logging.basicConfig(
            level=self._default_level,
            format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
            handlers=[logging.StreamHandler(sys.stdout)]
        )
    
    def setup(self, config: Dict[str, Any]):
        """
        配置日志
        
        Args:
            config: 日志配置，包含level, file等参数
        """
        # 解析日志级别
        level_str = config.get('level', 'INFO').upper()
        level_map = {
            'DEBUG': logging.DEBUG,
            'INFO': logging.INFO,
            'WARNING': logging.WARNING,
            'ERROR': logging.ERROR,
            'CRITICAL': logging.CRITICAL
        }
        level = level_map.get(level_str, logging.INFO)
        
        # 设置根日志级别
        logging.getLogger().setLevel(level)
        self._default_level = level
        
        # 设置日志文件
        log_file = config.get('file')
        if log_file:
            # 确保日志目录存在
            log_path = Path(log_file)
            log_path.parent.mkdir(parents=True, exist_ok=True)
            
            # 添加文件处理器
            file_handler = logging.FileHandler(log_file, encoding='utf-8')
            file_handler.setLevel(level)
            formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
            file_handler.setFormatter(formatter)
            
            # 添加到根日志
            root_logger = logging.getLogger()
            for handler in root_logger.handlers[:]:
                if isinstance(handler, logging.FileHandler):
                    root_logger.removeHandler(handler)
            root_logger.addHandler(file_handler)
    
    def get_logger(self, name: str) -> logging.Logger:
        """
        获取日志记录器
        
        Args:
            name: 日志记录器名称
            
        Returns:
            logging.Logger: 日志记录器
        """
        if name not in self._loggers:
            self._loggers[name] = logging.getLogger(name)
        return self._loggers[name]

# 全局日志工具实例
_logger = Logger()

def setup_logger(config: Dict[str, Any]):
    """
    配置日志系统
    
    Args:
        config: 日志配置
    """
    _logger.setup(config)

def get_logger(name: str) -> logging.Logger:
    """
    获取日志记录器
    
    Args:
        name: 日志记录器名称
        
    Returns:
        logging.Logger: 日志记录器
    """
    return _logger.get_logger(name)
```

#### 1.4.3 实现配置管理器

```python
# tg_app/core/config_manager.py
import os
import configparser
from typing import Dict, Any, Optional, List
from pathlib import Path

from tg_app.utils.logger import get_logger

# 获取日志记录器
logger = get_logger("config_manager")

class ConfigError(Exception):
    """配置错误异常"""
    pass

class ConfigManager:
    """配置管理器，负责读取和验证配置"""
    
    def __init__(self, config_path: str = "config/default_config.ini"):
        """
        初始化配置管理器
        
        Args:
            config_path: 配置文件路径
        """
        self.config_path = config_path
        self.config = configparser.ConfigParser()
        self.loaded = False
    
    def load_config(self, config_path: Optional[str] = None) -> bool:
        """
        加载配置文件
        
        Args:
            config_path: 配置文件路径，为None则使用初始化时的路径
            
        Returns:
            bool: 是否成功加载
        """
        if config_path:
            self.config_path = config_path
            
        if not os.path.exists(self.config_path):
            logger.error(f"配置文件 '{self.config_path}' 不存在")
            return False
            
        try:
            self.config.read(self.config_path, encoding='utf-8')
            self.loaded = True
            logger.info(f"成功加载配置文件: {self.config_path}")
            return True
        except Exception as e:
            logger.error(f"加载配置文件时出错: {str(e)}")
            return False
    
    def validate_config(self) -> bool:
        """
        验证配置文件的完整性和正确性
        
        Returns:
            bool: 是否验证通过
        """
        if not self.loaded:
            logger.error("尚未加载配置文件，无法验证")
            return False
            
        try:
            # 验证API部分
            if 'API' not in self.config:
                raise ConfigError("配置文件中缺少 [API] 部分")
            
            required_api_fields = ['api_id', 'api_hash']
            for field in required_api_fields:
                if field not in self.config['API'] or not self.config['API'][field]:
                    raise ConfigError(f"配置文件中缺少必要的API参数: {field}")
            
            # 验证CHANNELS部分
            if 'CHANNELS' not in self.config:
                raise ConfigError("配置文件中缺少 [CHANNELS] 部分")
            
            required_channel_fields = ['source_channel', 'target_channels']
            for field in required_channel_fields:
                if field not in self.config['CHANNELS'] or not self.config['CHANNELS'][field]:
                    raise ConfigError(f"配置文件中缺少必要的频道参数: {field}")
                    
            logger.info("配置验证通过")
            return True
            
        except ConfigError as e:
            logger.error(f"配置验证失败: {str(e)}")
            return False
    
    def get_api_config(self) -> Dict[str, Any]:
        """
        获取API配置
        
        Returns:
            Dict[str, Any]: API配置字典
        """
        if not self.loaded:
            logger.warning("尚未加载配置文件，返回空API配置")
            return {}
            
        api_config = {}
        
        if 'API' in self.config:
            try:
                api_config['api_id'] = int(self.config['API']['api_id'])
                api_config['api_hash'] = self.config['API']['api_hash']
                
                # 可选的电话号码
                if 'phone_number' in self.config['API'] and self.config['API']['phone_number']:
                    api_config['phone_number'] = self.config['API']['phone_number']
            except Exception as e:
                logger.error(f"解析API配置时出错: {str(e)}")
                
        return api_config
    
    def get_proxy_config(self) -> Optional[Dict[str, Any]]:
        """
        获取代理配置
        
        Returns:
            Optional[Dict[str, Any]]: 代理配置字典，无代理则返回None
        """
        if not self.loaded:
            logger.warning("尚未加载配置文件，返回空代理配置")
            return None
            
        if 'PROXY' not in self.config or not self.config.getboolean('PROXY', 'enabled', fallback=False):
            return None
            
        proxy_config = {}
        
        try:
            proxy_config['proxy_type'] = self.config['PROXY']['proxy_type']
            proxy_config['addr'] = self.config['PROXY']['addr']
            proxy_config['port'] = int(self.config['PROXY']['port'])
            
            # 可选的代理认证
            if 'username' in self.config['PROXY'] and self.config['PROXY']['username']:
                proxy_config['username'] = self.config['PROXY']['username']
            
            if 'password' in self.config['PROXY'] and self.config['PROXY']['password']:
                proxy_config['password'] = self.config['PROXY']['password']
                
        except Exception as e:
            logger.error(f"解析代理配置时出错: {str(e)}")
            return None
            
        return proxy_config
    
    def get_channels_config(self) -> Dict[str, Any]:
        """
        获取频道配置
        
        Returns:
            Dict[str, Any]: 频道配置字典
        """
        if not self.loaded:
            logger.warning("尚未加载配置文件，返回空频道配置")
            return {'source_channel': '', 'target_channels': []}
            
        channels_config = {}
        
        if 'CHANNELS' in self.config:
            try:
                source_channel = self.config['CHANNELS']['source_channel']
                target_channels = [
                    channel.strip() 
                    for channel in self.config['CHANNELS']['target_channels'].split(',')
                    if channel.strip()  # 过滤空字符串
                ]
                
                channels_config['source_channel'] = source_channel
                channels_config['target_channels'] = target_channels
                
            except Exception as e:
                logger.error(f"解析频道配置时出错: {str(e)}")
                
        return channels_config
```

#### 1.4.4 完善插件基类的实现

```python
# tg_app/plugins/base.py
from abc import ABC, abstractmethod
from typing import Dict, List, Any, Optional, Set

from tg_app.core.event_bus import EventBus
from tg_app.utils.logger import get_logger

# 获取日志记录器
logger = get_logger("plugin_base")

class PluginBase(ABC):
    """插件基类，所有插件必须继承此类"""
    
    def __init__(self, event_bus: EventBus):
        """
        初始化插件
        
        Args:
            event_bus: 事件总线
        """
        self.event_bus = event_bus
        self._event_handlers = {}
        self._initialized = False
        
    @property
    @abstractmethod
    def id(self) -> str:
        """插件唯一标识符"""
        pass
        
    @property
    @abstractmethod
    def name(self) -> str:
        """插件名称"""
        pass
        
    @property
    @abstractmethod
    def description(self) -> str:
        """插件描述"""
        pass
        
    @property
    def version(self) -> str:
        """插件版本"""
        return "1.0.0"
        
    @property
    def dependencies(self) -> List[str]:
        """插件依赖列表"""
        return []
    
    async def initialize(self) -> None:
        """初始化插件"""
        if self._initialized:
            logger.warning(f"插件 {self.id} 已经初始化")
            return
            
        logger.info(f"正在初始化插件: {self.name} ({self.id})")
        await self._register_event_handlers()
        self._initialized = True
        logger.info(f"插件 {self.name} ({self.id}) 初始化完成")
    
    async def shutdown(self) -> None:
        """关闭插件"""
        if not self._initialized:
            logger.warning(f"插件 {self.id} 尚未初始化，无需关闭")
            return
            
        logger.info(f"正在关闭插件: {self.name} ({self.id})")
        await self._unregister_event_handlers()
        self._initialized = False
        logger.info(f"插件 {self.name} ({self.id}) 已关闭")
    
    async def _register_event_handlers(self) -> None:
        """注册事件处理器"""
        for event_type, handler in self._event_handlers.items():
            logger.debug(f"插件 {self.id} 注册事件处理器: {event_type}")
            await self.event_bus.subscribe(event_type, handler)
    
    async def _unregister_event_handlers(self) -> None:
        """注销事件处理器"""
        for event_type, handler in self._event_handlers.items():
            logger.debug(f"插件 {self.id} 注销事件处理器: {event_type}")
            await self.event_bus.unsubscribe(event_type, handler)
    
    def register_event_handler(self, event_type: str, handler) -> None:
        """
        注册事件处理器
        
        Args:
            event_type: 事件类型
            handler: 处理函数
        """
        self._event_handlers[event_type] = handler
        logger.debug(f"插件 {self.id} 添加事件处理器: {event_type}")
    
    async def emit_event(self, event_type: str, data: Optional[Dict[str, Any]] = None) -> None:
        """
        发布事件
        
        Args:
            event_type: 事件类型
            data: 事件数据
        """
        if not data:
            data = {}
            
        data["plugin_id"] = self.id
        data["plugin_name"] = self.name
        
        logger.debug(f"插件 {self.id} 发布事件: {event_type}")
        await self.event_bus.publish(event_type, data)
```

## 步骤验证

完成以上所有实现后，请确保：

1. 所有文件夹和文件结构已创建
2. 所有核心接口已定义
3. 所有核心组件已实现
4. 日志模块可正常工作
5. 插件基类已实现完善的基础功能

## 下阶段准备

在进入第二阶段前，您需要：

1. 检查所有的实现是否正确
2. 确保目录结构清晰
3. 测试事件总线的基本功能
4. 理解插件的加载和管理流程

## 问题排查

如果在实现过程中遇到问题：

1. **导入错误**: 确保路径正确，并在各级目录中添加了`__init__.py`文件
2. **类型错误**: 检查函数签名和类型提示
3. **逻辑错误**: 使用`logger.debug`输出中间状态进行调试
4. **并发问题**: 确保在使用锁的地方正确地处理异步操作 