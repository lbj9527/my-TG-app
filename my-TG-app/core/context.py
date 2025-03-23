"""
应用上下文模块。

本模块提供应用的全局上下文，包含应用状态和核心服务的访问点。
上下文是应用的中央协调器，负责组织和管理各个核心组件。
"""

import asyncio
import logging
import os
from pathlib import Path
from typing import Dict, Any, Optional, List, Type, Set

from core.event_bus import EventBus
from core.config_manager import ConfigManager
from core.plugin_manager import PluginManager
from plugins.base import PluginBase
from events.event_types import (
    APP_INIT, APP_READY, APP_SHUTDOWN, APP_ERROR,
    create_event_data
)
from utils.logger import get_logger, setup_logger


# 获取日志记录器
logger = get_logger("app_context")


class ApplicationContext:
    """
    应用上下文，提供应用的全局状态和核心服务。
    
    上下文是一个单例对象，管理应用的生命周期和组件交互。
    """
    
    # 单例实例
    _instance = None
    
    @classmethod
    def get_instance(cls) -> 'ApplicationContext':
        """
        获取应用上下文的单例实例。
        
        Returns:
            ApplicationContext: 应用上下文实例
        """
        if cls._instance is None:
            cls._instance = ApplicationContext()
        return cls._instance
    
    def __init__(self):
        """初始化应用上下文"""
        # 防止多次初始化
        if ApplicationContext._instance is not None:
            logger.warning("尝试创建多个应用上下文实例，请使用get_instance()获取单例")
            return
        
        ApplicationContext._instance = self
        
        # 应用元数据
        self.app_name = "my-TG-app"
        self.app_version = "0.1.0"
        self.app_description = "基于插件架构的Telegram功能增强工具"
        
        # 应用状态
        self.is_initialized = False
        self.is_shutting_down = False
        
        # 核心组件
        self.event_bus: Optional[EventBus] = None
        self.config_manager: Optional[ConfigManager] = None
        self.plugin_manager: Optional[PluginManager] = None
        
        # 应用数据目录
        self.app_dir = Path.cwd()
        self.config_dir = self.app_dir / "config"
        self.logs_dir = self.app_dir / "logs"
        self.data_dir = self.app_dir / "data"
        self.downloads_dir = self.app_dir / "downloads"
        self.sessions_dir = self.app_dir / "sessions"
        
        # 确保目录存在
        self._ensure_directories()
        
        # 应用配置
        self.debug = False
        
        # 应用共享状态
        self.shared_state: Dict[str, Any] = {}
        
        logger.debug("应用上下文已创建")
    
    def _ensure_directories(self) -> None:
        """确保应用所需的目录结构存在"""
        for dir_path in [
            self.config_dir, 
            self.logs_dir, 
            self.data_dir, 
            self.downloads_dir,
            self.sessions_dir
        ]:
            if not dir_path.exists():
                dir_path.mkdir(parents=True, exist_ok=True)
                logger.debug(f"创建目录: {dir_path}")
    
    async def initialize(self) -> bool:
        """
        初始化应用上下文和核心组件。
        
        Returns:
            bool: 是否成功初始化
        """
        if self.is_initialized:
            logger.warning("应用上下文已经初始化")
            return True
        
        logger.info("初始化应用上下文")
        
        try:
            # 初始化事件总线
            self.event_bus = EventBus()
            logger.debug("事件总线已初始化")
            
            # 发布应用初始化事件
            await self.event_bus.publish(APP_INIT, create_event_data(APP_INIT))
            
            # 初始化配置管理器
            self.config_manager = ConfigManager(self.event_bus)
            
            # 加载默认配置
            if not self.config_manager.load_default_config():
                logger.error("加载默认配置失败")
                return False
            
            # 加载用户配置
            if not self.config_manager.load_user_config():
                logger.warning("加载用户配置失败，将使用默认配置")
            
            # 更新日志级别
            log_level = self.config_manager.get("app", "log_level", "INFO")
            setup_logger(log_level=log_level)
            logger.debug(f"日志级别设置为: {log_level}")
            
            # 更新调试模式
            self.debug = self.config_manager.get("app", "debug", False)
            logger.debug(f"调试模式: {'开启' if self.debug else '关闭'}")
            
            # 初始化插件管理器
            self.plugin_manager = PluginManager(self.event_bus)
            logger.debug("插件管理器已初始化")
            
            # 发现可用插件
            plugin_ids = await self.plugin_manager.discover_plugins()
            logger.info(f"发现了 {len(plugin_ids)} 个插件")
            
            self.is_initialized = True
            logger.info("应用上下文初始化完成")
            return True
            
        except Exception as e:
            logger.error(f"初始化应用上下文时出错: {str(e)}")
            
            # 发布应用错误事件
            if self.event_bus:
                event_data = create_event_data(APP_ERROR, error=str(e))
                await self.event_bus.publish(APP_ERROR, event_data)
                
            return False
    
    async def start(self) -> bool:
        """
        启动应用。
        
        Returns:
            bool: 是否成功启动
        """
        if not self.is_initialized:
            logger.error("应用上下文未初始化，无法启动")
            return False
        
        logger.info("启动应用")
        
        try:
            # 加载所有插件
            if self.plugin_manager:
                plugins = await self.plugin_manager.load_all_plugins()
                logger.info(f"加载了 {len(plugins)} 个插件")
            
            # 发布应用就绪事件
            if self.event_bus:
                event_data = create_event_data(APP_READY)
                await self.event_bus.publish(APP_READY, event_data)
            
            logger.info("应用已就绪")
            return True
            
        except Exception as e:
            logger.error(f"启动应用时出错: {str(e)}")
            
            # 发布应用错误事件
            if self.event_bus:
                event_data = create_event_data(APP_ERROR, error=str(e))
                await self.event_bus.publish(APP_ERROR, event_data)
                
            return False
    
    async def shutdown(self) -> bool:
        """
        关闭应用。
        
        Returns:
            bool: 是否成功关闭
        """
        if not self.is_initialized:
            logger.warning("应用上下文未初始化，无需关闭")
            return True
        
        if self.is_shutting_down:
            logger.warning("应用已经在关闭过程中")
            return True
        
        self.is_shutting_down = True
        logger.info("关闭应用")
        
        try:
            # 发布应用关闭事件
            if self.event_bus:
                event_data = create_event_data(APP_SHUTDOWN)
                await self.event_bus.publish(APP_SHUTDOWN, event_data)
            
            # 卸载所有插件
            if self.plugin_manager:
                success = await self.plugin_manager.unload_all_plugins()
                if not success:
                    logger.warning("卸载插件时发生错误")
            
            # 保存配置
            if self.config_manager:
                self.config_manager.save_config()
                
                # 停止配置监视
                self.config_manager.stop_config_watch()
            
            self.is_initialized = False
            logger.info("应用已关闭")
            return True
            
        except Exception as e:
            logger.error(f"关闭应用时出错: {str(e)}")
            
            # 发布应用错误事件
            if self.event_bus:
                event_data = create_event_data(APP_ERROR, error=str(e))
                await self.event_bus.publish(APP_ERROR, event_data)
                
            return False
    
    def get_plugin(self, plugin_id: str) -> Optional[PluginBase]:
        """
        获取指定ID的插件实例。
        
        Args:
            plugin_id: 插件ID
            
        Returns:
            Optional[PluginBase]: 插件实例，如果未找到则返回None
        """
        if not self.plugin_manager:
            logger.error("插件管理器未初始化")
            return None
            
        return self.plugin_manager.get_plugin(plugin_id)
    
    def get_config(self, section: str, key: str, default: Any = None) -> Any:
        """
        获取配置值。
        
        Args:
            section: 配置节
            key: 配置键
            default: 默认值
            
        Returns:
            Any: 配置值，如果不存在则返回默认值
        """
        if not self.config_manager:
            logger.error("配置管理器未初始化")
            return default
            
        return self.config_manager.get(section, key, default)
    
    def set_config(self, section: str, key: str, value: Any, description: str = "") -> bool:
        """
        设置配置值。
        
        Args:
            section: 配置节
            key: 配置键
            value: 配置值
            description: 配置描述
            
        Returns:
            bool: 是否设置成功
        """
        if not self.config_manager:
            logger.error("配置管理器未初始化")
            return False
            
        return self.config_manager.set(section, key, value, description)
    
    def get_downloads_dir(self) -> Path:
        """
        获取下载目录路径。
        
        如果config中有配置，则使用配置的路径，否则使用默认路径。
        
        Returns:
            Path: 下载目录路径
        """
        if self.config_manager:
            downloads_path = self.config_manager.get("download", "download_dir", None)
            if downloads_path:
                return Path(downloads_path)
        
        return self.downloads_dir
    
    def get_sessions_dir(self) -> Path:
        """
        获取会话目录路径。
        
        Returns:
            Path: 会话目录路径
        """
        return self.sessions_dir
    
    def get_session_path(self, session_name: str) -> Path:
        """
        获取指定会话文件的路径。
        
        Args:
            session_name: 会话名称
            
        Returns:
            Path: 会话文件路径
        """
        # 如果未指定扩展名，添加.session
        if not session_name.endswith(".session"):
            session_name += ".session"
            
        return self.get_sessions_dir() / session_name
    
    def set_shared_state(self, key: str, value: Any) -> None:
        """
        设置共享状态值。
        
        Args:
            key: 状态键
            value: 状态值
        """
        self.shared_state[key] = value
    
    def get_shared_state(self, key: str, default: Any = None) -> Any:
        """
        获取共享状态值。
        
        Args:
            key: 状态键
            default: 默认值
            
        Returns:
            Any: 状态值，如果不存在则返回默认值
        """
        return self.shared_state.get(key, default)
    
    def remove_shared_state(self, key: str) -> bool:
        """
        移除共享状态值。
        
        Args:
            key: 状态键
            
        Returns:
            bool: 是否成功移除
        """
        if key in self.shared_state:
            del self.shared_state[key]
            return True
        return False
    
    async def publish_event(self, event_type: str, data: Optional[Dict[str, Any]] = None) -> int:
        """
        发布事件。
        
        Args:
            event_type: 事件类型
            data: 事件数据
            
        Returns:
            int: 接收事件的处理器数量
        """
        if not self.event_bus:
            logger.error("事件总线未初始化")
            return 0
            
        if data is None:
            data = {}
            
        # 添加上下文标识到事件数据
        data["source"] = "app_context"
        
        return await self.event_bus.publish(event_type, data)
    
    def __str__(self) -> str:
        """返回应用上下文的字符串表示"""
        return f"{self.app_name} v{self.app_version}" 