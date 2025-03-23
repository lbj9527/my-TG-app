import os
import asyncio
from typing import Dict, Any, Optional, List, Union

from pyrogram import Client
from pyrogram.errors import AuthKeyUnregistered, AuthKeyDuplicated, PhoneNumberInvalid

from plugins.base import PluginBase
from events import event_types as events
from utils.logger import get_logger

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
        self.register_event_handler(events.CLIENT_CONNECT, self._handle_connect)
        self.register_event_handler(events.CLIENT_DISCONNECT, self._handle_disconnect)
        self.register_event_handler(events.APP_SHUTDOWN, self._handle_app_shutdown)
        self.register_event_handler(events.CLIENT_GET_INSTANCE, self._handle_get_instance)
        
        # 获取配置
        config = await self.get_config()
        
        if not config:
            logger.error("无法获取客户端配置，插件初始化失败")
            return
            
        # 验证必要的配置项
        if not config.get("api_id") or not config.get("api_hash"):
            logger.error("API ID或API Hash缺失，插件初始化失败")
            return
        
        # 获取代理配置
        proxy_config = None
        proxy_response = await self.publish_and_wait(
            events.CONFIG_GET_SECTION, 
            {"section": "proxy"},
            timeout=5.0
        )
        
        if proxy_response and proxy_response.get("success", False):
            proxy_config = proxy_response.get("data", {})
            
        # 设置代理
        proxy = None
        if proxy_config:
            proxy_enabled = proxy_config.get("enabled", False)
            if isinstance(proxy_enabled, str):
                proxy_enabled = proxy_enabled.lower() == "true"
                
            if proxy_enabled:
                proxy_type = proxy_config.get("proxy_type", None) or proxy_config.get("type", None)
                proxy_host = proxy_config.get("addr", None) or proxy_config.get("host", None)
                proxy_port = proxy_config.get("port", None)
                proxy_username = proxy_config.get("username", None)
                proxy_password = proxy_config.get("password", None)
                
                if proxy_type and proxy_host and proxy_port:
                    logger.info(f"使用代理: {proxy_type} {proxy_host}:{proxy_port}")
                    proxy = {
                        "scheme": proxy_type.lower(),
                        "hostname": proxy_host,
                        "port": int(proxy_port)
                    }
                    
                    # 如果有用户名和密码，添加到代理配置
                    if proxy_username and proxy_password:
                        proxy["username"] = proxy_username
                        proxy["password"] = proxy_password
                else:
                    logger.warning("代理配置不完整，将不使用代理")
        
        # 创建客户端实例（但不连接）
        self.client = Client(
            name=config.get("session_name", "tg_app"),
            api_id=config.get("api_id"),
            api_hash=config.get("api_hash"),
            workdir=config.get("work_dir", "./sessions"),
            no_updates=config.get("no_updates", True),
            phone_number=config.get("phone_number"),
            proxy=proxy  # 添加代理配置
        )
        
        # 如果配置了自动连接，则连接
        if config.get("auto_connect", False):
            asyncio.create_task(self.connect())
        
        logger.info("Telegram客户端插件初始化完成")
    
    async def _handle_connect(self, data: Dict[str, Any]) -> None:
        """
        处理连接事件
        
        Args:
            data: 事件数据
        """
        await self.connect()
    
    async def _handle_disconnect(self, data: Dict[str, Any]) -> None:
        """
        处理断开连接事件
        
        Args:
            data: 事件数据
        """
        await self.disconnect()
    
    async def _handle_app_shutdown(self, data: Dict[str, Any]) -> None:
        """
        处理应用关闭事件
        
        Args:
            data: 事件数据
        """
        await self.disconnect()
    
    async def _handle_get_instance(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """
        处理获取客户端实例事件
        
        Args:
            data: 事件数据
            
        Returns:
            Dict[str, Any]: 包含客户端实例的响应
        """
        if not self.client:
            return {"success": False, "error": "客户端未初始化"}
            
        if not self.is_connected:
            logger.warning("请求获取未连接的客户端实例")
            
        return {"success": True, "client": self.client}
    
    async def get_config(self) -> Dict[str, Any]:
        """
        获取客户端配置
        
        Returns:
            Dict[str, Any]: 客户端配置字典
        """
        # 发布获取配置事件
        response = await self.publish_and_wait(
            events.CONFIG_GET_SECTION, 
            {"section": "client"},
            timeout=5.0
        )
        
        if not response or not response.get("success", False):
            logger.error("获取客户端配置失败")
            return {}
            
        config = response.get("data", {})
        
        # 确保API ID是整数
        if "api_id" in config and isinstance(config["api_id"], str):
            try:
                config["api_id"] = int(config["api_id"])
            except ValueError:
                logger.error("API ID必须为整数")
                return {}
        
        # 确保phone_number是字符串类型
        if "phone_number" in config and not isinstance(config["phone_number"], str):
            config["phone_number"] = str(config["phone_number"])
        
        # 设置默认值        
        config.setdefault("session_name", "tg_app")
        config.setdefault("work_dir", "./sessions")
        config.setdefault("no_updates", True)
        
        # 将字符串布尔值转换为实际布尔值
        if isinstance(config.get("no_updates"), str):
            config["no_updates"] = config["no_updates"].lower() == "true"
            
        if isinstance(config.get("auto_connect"), str):
            config["auto_connect"] = config["auto_connect"].lower() == "true"
        
        return config
    
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
            await self.publish_event(events.CLIENT_CONNECTED, {
                "user": {
                    "id": me.id,
                    "username": me.username,
                    "first_name": me.first_name,
                    "last_name": me.last_name
                }
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
            await self.publish_event(events.CLIENT_DISCONNECTED, {})
            
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
        self.unregister_event_handler(events.CLIENT_CONNECT)
        self.unregister_event_handler(events.CLIENT_DISCONNECT)
        self.unregister_event_handler(events.APP_SHUTDOWN)
        self.unregister_event_handler(events.CLIENT_GET_INSTANCE)
        
        self.client = None
        logger.info("Telegram客户端插件已关闭") 