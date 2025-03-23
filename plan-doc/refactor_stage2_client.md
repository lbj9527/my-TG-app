# Telegram转发工具重构计划 - 第二阶段（客户端插件实现）

## 任务2.3：实现客户端插件(ClientPlugin)

首先我们需要实现客户端插件，它是其他插件的基础。这个插件将负责与Telegram API的连接和交互。

```python
# tg_app/plugins/client/client_plugin.py
import os
import asyncio
from typing import Dict, Any, Optional, List, Union

from pyrogram import Client
from pyrogram.errors import AuthKeyUnregistered, AuthKeyDuplicated, PhoneNumberInvalid

from tg_app.plugins.base import PluginBase
from tg_app.events import event_types as events
from tg_app.utils.logger import get_logger

# 获取日志记录器
logger = get_logger("client_plugin")

class ClientPlugin(PluginBase):
    """
    Telegram客户端插件，负责管理与Telegram API的连接
    """
    
    def __init__(self, event_bus):
        """
        初始化客户端插件
        
        Args:
            event_bus: 事件总线
        """
        super().__init__(event_bus)
        
        self.client = None
        self.is_connected = False
        
        # 定义插件元数据
        self.id = "client"
        self.name = "Telegram客户端插件"
        self.version = "1.0.0"
        self.description = "管理与Telegram API的连接"
        self.dependencies = []  # 客户端插件是基础插件，没有依赖
    
    async def initialize(self) -> None:
        """初始化插件"""
        logger.info("正在初始化Telegram客户端插件...")
        
        # 注册事件处理器
        self.event_bus.subscribe(events.CLIENT_CONNECT, self._handle_connect)
        self.event_bus.subscribe(events.CLIENT_DISCONNECT, self._handle_disconnect)
        self.event_bus.subscribe(events.APP_SHUTDOWN, self._handle_app_shutdown)
        
        # 获取配置
        config = await self.get_config()
        
        # 创建客户端实例（但不连接）
        self.client = Client(
            name=config.get("session_name", "tg_app"),
            api_id=config.get("api_id"),
            api_hash=config.get("api_hash"),
            workdir=config.get("work_dir", "./sessions"),
            no_updates=config.get("no_updates", True),
            phone_number=config.get("phone_number")
        )
        
        logger.info("Telegram客户端插件初始化完成")
    
    async def _handle_connect(self, data: Dict[str, Any] = None) -> None:
        """
        处理连接事件
        
        Args:
            data: 事件数据
        """
        await self.connect()
    
    async def _handle_disconnect(self, data: Dict[str, Any] = None) -> None:
        """
        处理断开连接事件
        
        Args:
            data: 事件数据
        """
        await self.disconnect()
    
    async def _handle_app_shutdown(self, data: Dict[str, Any] = None) -> None:
        """
        处理应用关闭事件
        
        Args:
            data: 事件数据
        """
        await self.disconnect()
    
    async def get_config(self) -> Dict[str, Any]:
        """
        获取客户端配置
        
        Returns:
            Dict[str, Any]: 客户端配置字典
        """
        # 发布获取配置事件
        response = await self.event_bus.publish_and_wait(
            events.CONFIG_GET_SECTION, 
            {"section": "client"},
            timeout=5.0
        )
        
        if not response or not response.get("success", False):
            logger.error("获取客户端配置失败")
            return {}
            
        return response.get("data", {})
    
    async def connect(self) -> Dict[str, Any]:
        """
        连接到Telegram API
        
        Returns:
            Dict[str, Any]: 包含连接结果的字典
        """
        if self.is_connected:
            logger.warning("客户端已经连接")
            return {"success": True, "message": "客户端已经连接"}
            
        if not self.client:
            logger.error("客户端未初始化")
            return {"success": False, "error": "客户端未初始化"}
            
        logger.info("正在连接到Telegram...")
        
        try:
            # 启动客户端
            await self.client.start()
            self.is_connected = True
            
            # 获取用户信息
            me = await self.client.get_me()
            
            # 发布连接成功事件
            await self.event_bus.publish(events.CLIENT_CONNECTED, {
                "client": self.client,
                "user": me
            })
            
            logger.info(f"已连接到Telegram，用户: {me.first_name} (@{me.username})")
            return {
                "success": True, 
                "user": me,
                "message": f"已连接到Telegram，用户: {me.first_name} (@{me.username})"
            }
            
        except AuthKeyUnregistered:
            error_msg = "会话已失效，请重新登录"
            logger.error(error_msg)
            return {"success": False, "error": error_msg}
            
        except AuthKeyDuplicated:
            error_msg = "会话在其他地方登录，此会话已失效"
            logger.error(error_msg)
            return {"success": False, "error": error_msg}
            
        except PhoneNumberInvalid:
            error_msg = "无效的电话号码"
            logger.error(error_msg)
            return {"success": False, "error": error_msg}
            
        except Exception as e:
            error_msg = f"连接Telegram时出错: {str(e)}"
            logger.exception(error_msg)
            return {"success": False, "error": error_msg}
    
    async def disconnect(self) -> Dict[str, Any]:
        """
        断开与Telegram API的连接
        
        Returns:
            Dict[str, Any]: 包含断开连接结果的字典
        """
        if not self.is_connected or not self.client:
            logger.warning("客户端未连接")
            return {"success": True, "message": "客户端未连接"}
            
        logger.info("正在断开与Telegram的连接...")
        
        try:
            # 停止客户端
            await self.client.stop()
            self.is_connected = False
            
            # 发布断开连接事件
            await self.event_bus.publish(events.CLIENT_DISCONNECTED)
            
            logger.info("已断开与Telegram的连接")
            return {"success": True, "message": "已断开与Telegram的连接"}
            
        except Exception as e:
            error_msg = f"断开与Telegram连接时出错: {str(e)}"
            logger.exception(error_msg)
            return {"success": False, "error": error_msg}
    
    async def get_client(self) -> Optional[Client]:
        """
        获取Pyrogram客户端实例
        
        Returns:
            Optional[Client]: Pyrogram客户端实例
        """
        if not self.is_connected:
            logger.warning("尝试获取未连接的客户端")
            
        return self.client
    
    async def shutdown(self) -> None:
        """关闭插件，断开连接"""
        logger.info("正在关闭Telegram客户端插件...")
        
        # 断开连接
        await self.disconnect()
        
        # 取消事件订阅
        self.event_bus.unsubscribe(events.CLIENT_CONNECT, self._handle_connect)
        self.event_bus.unsubscribe(events.CLIENT_DISCONNECT, self._handle_disconnect)
        self.event_bus.unsubscribe(events.APP_SHUTDOWN, self._handle_app_shutdown)
        
        self.client = None
        logger.info("Telegram客户端插件已关闭")
```

### 任务2.4：实现配置管理器(ConfigManager)

接下来完善配置管理器的实现：

```python
# tg_app/core/config_manager.py
import os
import configparser
from typing import Dict, Any, List, Optional, Union

from tg_app.events import event_types as events
from tg_app.utils.logger import get_logger

# 获取日志记录器
logger = get_logger("config_manager")

class ConfigManager:
    """配置管理器，负责加载、验证和管理配置"""
    
    def __init__(self):
        """初始化配置管理器"""
        self.config = configparser.ConfigParser()
        self.config_path = None
        
        # 定义必需的配置节和字段
        self.required_sections = {
            "client": ["api_id", "api_hash", "session_name"],
            "channels": ["source_channel", "target_channels"],
            "forward": ["batch_size", "delay_between_batches"],
            "log": ["level", "file_path"]
        }
    
    def load_config(self, config_path: str) -> bool:
        """
        加载配置文件
        
        Args:
            config_path: 配置文件路径
            
        Returns:
            bool: 是否成功加载
        """
        if not os.path.exists(config_path):
            logger.error(f"配置文件不存在: {config_path}")
            return False
            
        try:
            self.config.read(config_path, encoding="utf-8")
            self.config_path = config_path
            logger.info(f"已加载配置文件: {config_path}")
            return True
            
        except Exception as e:
            logger.error(f"加载配置文件时出错: {str(e)}")
            return False
    
    def save_config(self, config_path: Optional[str] = None) -> bool:
        """
        保存配置文件
        
        Args:
            config_path: 配置文件路径，为None则使用加载时的路径
            
        Returns:
            bool: 是否成功保存
        """
        if not config_path:
            if not self.config_path:
                logger.error("未指定配置文件路径")
                return False
            config_path = self.config_path
            
        # 确保目录存在
        os.makedirs(os.path.dirname(config_path), exist_ok=True)
        
        try:
            with open(config_path, "w", encoding="utf-8") as f:
                self.config.write(f)
                
            logger.info(f"已保存配置文件: {config_path}")
            return True
            
        except Exception as e:
            logger.error(f"保存配置文件时出错: {str(e)}")
            return False
    
    def validate_config(self) -> bool:
        """
        验证配置文件是否包含所有必需的配置项
        
        Returns:
            bool: 配置是否有效
        """
        if not self.config_path:
            logger.error("配置文件尚未加载")
            return False
            
        # 检查必需的配置节和字段
        for section, keys in self.required_sections.items():
            if section not in self.config:
                logger.error(f"配置文件缺少必需的节: [{section}]")
                return False
                
            for key in keys:
                if key not in self.config[section]:
                    logger.error(f"配置节 [{section}] 缺少必需的字段: {key}")
                    return False
        
        # 验证特定字段的值
        try:
            # 验证API ID是否为整数
            api_id = self.config.getint("client", "api_id")
            
            # 验证批处理大小和延迟是否为整数
            batch_size = self.config.getint("forward", "batch_size")
            delay = self.config.getint("forward", "delay_between_batches")
            
            if batch_size <= 0:
                logger.error("批处理大小必须大于0")
                return False
                
            if delay < 0:
                logger.error("批处理延迟不能为负数")
                return False
                
            # 验证目标频道是否为逗号分隔的列表
            target_channels = self.config.get("channels", "target_channels").strip()
            if not target_channels:
                logger.error("目标频道列表不能为空")
                return False
                
            # 验证源频道是否有效
            source_channel = self.config.get("channels", "source_channel").strip()
            if not source_channel:
                logger.error("源频道不能为空")
                return False
                
        except ValueError as e:
            logger.error(f"配置值类型错误: {str(e)}")
            return False
            
        logger.info("配置文件验证通过")
        return True
    
    def get_section(self, section: str) -> Dict[str, Any]:
        """
        获取配置节
        
        Args:
            section: 配置节名称
            
        Returns:
            Dict[str, Any]: 配置节内容
        """
        if not self.config_path:
            logger.warning("配置文件尚未加载")
            return {}
            
        if section not in self.config:
            logger.warning(f"配置节不存在: {section}")
            return {}
            
        return dict(self.config[section])
    
    def get_client_config(self) -> Dict[str, Any]:
        """
        获取客户端配置
        
        Returns:
            Dict[str, Any]: 客户端配置
        """
        client_config = self.get_section("client")
        
        # 转换API ID为整数
        if "api_id" in client_config:
            try:
                client_config["api_id"] = int(client_config["api_id"])
            except ValueError:
                logger.error("API ID必须为整数")
                client_config["api_id"] = 0
                
        # 设置工作目录
        client_config.setdefault("work_dir", "./sessions")
        
        # 设置是否接收更新
        client_config.setdefault("no_updates", "true")
        client_config["no_updates"] = client_config["no_updates"].lower() == "true"
        
        return client_config
    
    def get_channels_config(self) -> Dict[str, Any]:
        """
        获取频道配置
        
        Returns:
            Dict[str, Any]: 频道配置
        """
        channels_config = self.get_section("channels")
        
        # 处理目标频道列表
        if "target_channels" in channels_config:
            target_channels = channels_config["target_channels"].split(",")
            channels_config["target_channels"] = [ch.strip() for ch in target_channels if ch.strip()]
            
        return channels_config
    
    def get_forward_config(self) -> Dict[str, Any]:
        """
        获取转发配置
        
        Returns:
            Dict[str, Any]: 转发配置
        """
        forward_config = self.get_section("forward")
        
        # 转换批处理大小为整数
        if "batch_size" in forward_config:
            try:
                forward_config["batch_size"] = int(forward_config["batch_size"])
            except ValueError:
                logger.error("批处理大小必须为整数")
                forward_config["batch_size"] = 10
                
        # 转换批处理延迟为整数
        if "delay_between_batches" in forward_config:
            try:
                forward_config["delay_between_batches"] = int(forward_config["delay_between_batches"])
            except ValueError:
                logger.error("批处理延迟必须为整数")
                forward_config["delay_between_batches"] = 2
                
        # 转换是否保留原始日期为布尔值
        if "preserve_date" in forward_config:
            forward_config["preserve_date"] = forward_config["preserve_date"].lower() == "true"
        else:
            forward_config["preserve_date"] = False
            
        # 转换是否复制媒体文件为布尔值
        if "copy_media" in forward_config:
            forward_config["copy_media"] = forward_config["copy_media"].lower() == "true"
        else:
            forward_config["copy_media"] = True
            
        return forward_config
    
    def get_log_config(self) -> Dict[str, Any]:
        """
        获取日志配置
        
        Returns:
            Dict[str, Any]: 日志配置
        """
        log_config = self.get_section("log")
        
        # 设置默认日志级别
        log_config.setdefault("level", "INFO")
        
        # 设置默认日志文件路径
        log_config.setdefault("file_path", "logs/tg_app.log")
        
        return log_config
    
    def update_section(self, section: str, values: Dict[str, Any]) -> bool:
        """
        更新配置节
        
        Args:
            section: 配置节名称
            values: 要更新的值
            
        Returns:
            bool: 是否成功更新
        """
        if not self.config_path:
            logger.error("配置文件尚未加载")
            return False
            
        # 确保配置节存在
        if section not in self.config:
            self.config[section] = {}
            
        # 更新值
        for key, value in values.items():
            # 将非字符串值转换为字符串
            if isinstance(value, (list, tuple)):
                # 将列表转换为逗号分隔的字符串
                value = ",".join(str(item) for item in value)
            elif not isinstance(value, str):
                value = str(value)
                
            self.config[section][key] = value
            
        # 保存配置
        return self.save_config()
    
    def handle_config_get_section(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """
        处理获取配置节事件
        
        Args:
            data: 事件数据
            
        Returns:
            Dict[str, Any]: 响应数据
        """
        section = data.get("section")
        if not section:
            return {"success": False, "error": "未指定配置节"}
            
        section_data = self.get_section(section)
        return {"success": True, "data": section_data}
    
    def handle_config_update_section(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """
        处理更新配置节事件
        
        Args:
            data: 事件数据
            
        Returns:
            Dict[str, Any]: 响应数据
        """
        section = data.get("section")
        values = data.get("values")
        
        if not section:
            return {"success": False, "error": "未指定配置节"}
            
        if not values or not isinstance(values, dict):
            return {"success": False, "error": "未提供有效的配置值"}
            
        success = self.update_section(section, values)
        if success:
            return {"success": True}
        else:
            return {"success": False, "error": "更新配置失败"}
    
    def register_event_handlers(self, event_bus):
        """
        注册事件处理器
        
        Args:
            event_bus: 事件总线
        """
        event_bus.subscribe(events.CONFIG_GET_SECTION, self.handle_config_get_section)
        event_bus.subscribe(events.CONFIG_UPDATE_SECTION, self.handle_config_update_section)
```

## 开发说明

1. **客户端插件**:
   - 实现了与Telegram API的连接和交互功能
   - 通过事件机制处理连接和断开连接操作
   - 提供了对外的接口，供其他插件获取客户端实例

2. **配置管理器**:
   - 负责加载、验证和管理配置文件
   - 提供各种配置获取方法，并进行类型转换
   - 通过事件机制与其他组件交互

3. **类型转换**:
   - 确保配置值具有正确的类型，如整数和布尔值
   - 将列表类型的配置项（如目标频道）从字符串转换为列表

4. **错误处理**:
   - 添加了全面的错误处理和日志记录
   - 验证配置文件的完整性和有效性 