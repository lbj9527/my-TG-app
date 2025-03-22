"""
应用程序实现类
负责整合所有核心组件并提供统一的应用程序管理
"""

import os
import asyncio
import time
from datetime import datetime
from typing import Dict, Any, List, Union, Optional, Tuple, Callable
import json
import shutil
import importlib
import pkg_resources

from tg_forwarder.interfaces.application_interface import ApplicationInterface
from tg_forwarder.interfaces.client_interface import TelegramClientInterface
from tg_forwarder.interfaces.downloader_interface import DownloaderInterface
from tg_forwarder.interfaces.uploader_interface import UploaderInterface
from tg_forwarder.interfaces.forwarder_interface import ForwarderInterface
from tg_forwarder.interfaces.config_interface import ConfigInterface
from tg_forwarder.interfaces.status_tracker_interface import StatusTrackerInterface
from tg_forwarder.interfaces.logger_interface import LoggerInterface
from tg_forwarder.interfaces.json_storage_interface import JsonStorageInterface
from tg_forwarder.interfaces.history_tracker_interface import HistoryTrackerInterface
from tg_forwarder.interfaces.channel_utils_interface import ChannelUtilsInterface

from tg_forwarder.core.config_manager import ConfigManager
from tg_forwarder.core.logger import Logger
from tg_forwarder.core.status_tracker import StatusTracker
from tg_forwarder.core.telegram_client import TelegramClient
from tg_forwarder.core.downloader import Downloader
from tg_forwarder.core.uploader import Uploader
from tg_forwarder.core.forwarder import Forwarder
from tg_forwarder.core.json_storage import JsonStorage
from tg_forwarder.core.history_tracker import HistoryTracker
from tg_forwarder.core.channel_utils import ChannelUtils
from tg_forwarder.core.channel_factory import get_channel_utils


class Application(ApplicationInterface):
    """
    应用程序类，实现ApplicationInterface接口
    负责整合所有核心组件并提供统一的应用程序管理
    """
    
    # 应用程序版本
    VERSION = "0.3.2"
    
    # 添加一个全局的应用程序实例引用，用于信号处理
    _instance = None
    
    @staticmethod
    def setup_signal_handling():
        """
        设置全局信号处理
        这必须在创建实例之前调用，以便准备好处理信号
        """
        import signal
        import sys
        import os
        
        def global_signal_handler(sig, frame):
            """
            顶层信号处理函数，将信号转发到应用实例
            """
            if Application._instance is not None:
                print(f"\n接收到信号 {sig}，正在优雅关闭...")
                
                # 使用asyncio处理关闭流程
                import asyncio
                
                # 获取或创建事件循环
                try:
                    loop = asyncio.get_event_loop()
                except RuntimeError:
                    # 如果没有事件循环，则创建一个新的
                    loop = asyncio.new_event_loop()
                    asyncio.set_event_loop(loop)
                
                if loop.is_running():
                    # 如果循环正在运行，使用call_soon_threadsafe安排关闭函数
                    def run_shutdown():
                        asyncio.create_task(Application._instance._handle_shutdown())
                    
                    loop.call_soon_threadsafe(run_shutdown)
                else:
                    # 如果循环没有运行，直接运行关闭函数
                    loop.run_until_complete(Application._instance._handle_shutdown())
                
                # 等待1秒，让关闭过程开始
                time.sleep(1)
                
                print("应用程序已关闭。")
                
                # 在特定平台安全退出
                if sys.platform == 'win32':
                    os._exit(0)
                else:
                    os.kill(os.getpid(), signal.SIGKILL)
        
        # 为Unix信号注册处理程序
        if sys.platform != 'win32':
            signal.signal(signal.SIGINT, global_signal_handler)
            signal.signal(signal.SIGTERM, global_signal_handler)
        else:
            # Windows平台处理
            try:
                # 尝试导入win32api模块
                import win32api
                
                def windows_handler(ctrl_type):
                    """Windows CTRL事件处理器"""
                    if ctrl_type in (0, 2, 6):  # CTRL+C, CTRL+BREAK, CTRL+CLOSE
                        global_signal_handler(signal.SIGINT, None)
                        return True  # 不继续其他处理器
                    return False
                
                win32api.SetConsoleCtrlHandler(windows_handler, 1)
            except ImportError:
                # 如果无法导入win32api，则使用标准信号处理
                signal.signal(signal.SIGINT, global_signal_handler)
    
    def __init__(self, config_path: str = None):
        """
        初始化Application实例
        
        Args:
            config_path: 配置文件路径，为None时使用默认路径
        """
        # 设置全局实例引用
        Application._instance = self
        
        # 初始化一个简单的日志器用于初始化过程
        import logging
        self._app_logger = logging.getLogger("Application")
        
        # 创建应用组件
        self._config = ConfigManager(config_path)
        self._logger = Logger()
        
        # 状态变量
        self._initialized = False
        self._shutting_down = False
        self._start_time = 0
        
        # 组件实例
        self._json_storage = None
        self._history_tracker = None
        self._status_tracker = None
        
        # 事件处理器注册表
        self._event_handlers = {}
        
        # 核心组件
        self._client = None
        self._downloader = None
        self._uploader = None
        self._forwarder = None
        
        # 新增成员变量
        self._running = False
        self._db_manager = None
        self._translation_manager = None
        
        # 监听相关成员变量
        self._monitor_status = {
            "running": False,
            "last_monitor_id": None,
            "last_duration": 0,
            "messages_forwarded": 0
        }
    
    async def initialize(self) -> bool:
        """
        初始化应用程序
        
        Returns:
            bool: 初始化是否成功
        """
        if self._initialized:
            self._app_logger.info("应用已初始化")
            return True
            
        self._app_logger.info("正在初始化应用...")
        
        try:
            # 加载配置
            try:
                config_loaded = self._config.load_config()
                if not config_loaded:
                    self._app_logger.error("加载配置失败，应用无法初始化")
                    # 但仍然继续初始化其他组件，设置配置有效性标志
                    self._config_valid = False
                else:
                    self._config_valid = True
            except Exception as e:
                self._app_logger.error(f"加载配置时出错: {str(e)}")
                self._config_valid = False
            
            # 初始化JSON存储
            try:
                self._json_storage = JsonStorage(config=self._config)
                await self._json_storage.initialize()
            except Exception as e:
                self._app_logger.error(f"初始化JSON存储失败: {str(e)}")
                if not self._json_storage:
                    self._json_storage = None
            
            # 初始化历史跟踪器
            try:
                self._history_tracker = HistoryTracker(self._config, self._json_storage)
                await self._history_tracker.initialize()
            except Exception as e:
                self._app_logger.error(f"初始化历史跟踪器失败: {str(e)}")
                if not self._history_tracker:
                    self._history_tracker = None
            
            # 初始化日志系统
            try:
                self._logger = Logger()
                log_config = self._config.get("log", {})
                log_file = log_config.get("file", "logs/tg_forwarder.log")
                log_level = log_config.get("level", "INFO")
                log_rotation = log_config.get("rotation", "10 MB")
                self._logger.initialize(log_file=log_file, log_level=log_level, rotation=log_rotation)
            except Exception as e:
                self._app_logger.error(f"初始化日志系统失败: {str(e)}")
                if not self._logger:
                    self._logger = None
            
            # 初始化状态追踪器
            self._status_tracker = StatusTracker(self._json_storage, self._logger)
            await self._status_tracker.initialize()
            
            # 通过配置初始化Telegram客户端
            try:
                if self._config_valid:
                    # 初始化客户端（只需要传递config和logger两个参数）
                    self._client = TelegramClient(
                        self._config,
                        self._logger
                    )
                    
                    # 连接客户端
                    await self._client.connect()
                    
                    # 添加客户端到全局引用
                    Application._global_client = self._client
                else:
                    # 如果配置无效，不初始化客户端
                    self._app_logger.warning("由于配置无效，跳过Telegram客户端初始化")
                    self._client = None
            except Exception as e:
                self._app_logger.error(f"初始化Telegram客户端失败: {str(e)}", exc_info=True)
                self._client = None
                return False
            
            # 初始化下载器
            if self._client:
                self._downloader = Downloader(
                    self._client,
                    self._config,
                    self._logger,
                    self._json_storage,
                    self._status_tracker,
                    self._history_tracker
                )
                await self._downloader.initialize()
                
                # 初始化上传器
                upload_config = self._config.get("upload") or {}
                self._uploader = Uploader(
                    self._client,
                    self._config,
                    self._logger,
                    self._json_storage,
                    self._status_tracker,
                    self._history_tracker
                )
                await self._uploader.initialize()
                
                # 初始化转发器
                self._forwarder = Forwarder(
                    self._client,
                    self._downloader,
                    self._uploader,
                    self._status_tracker,
                    self._config,
                    self._logger
                )
                await self._forwarder.initialize()
            else:
                self._app_logger.warning("由于Telegram客户端未初始化，跳过下载器、上传器和转发器初始化")
                self._downloader = None
                self._uploader = None
                self._forwarder = None
            
            # 注册信号处理器
            self._register_signal_handlers()
            
            # 记录启动时间
            self._start_time = time.time()
            
            self._initialized = True
            self._app_logger.info("应用初始化完成")
            
            # 触发初始化完成事件
            await self._trigger_event("app_initialized", {})
            
            return True
        
        except Exception as e:
            self._app_logger.error(f"应用初始化失败: {str(e)}", exc_info=True)
            
            # 按顺序关闭已初始化的组件
            try:
                # 依次关闭每个已创建的组件
                components_to_close = [
                    (self._forwarder, "shutdown", "转发器"),
                    (self._uploader, "shutdown", "上传器"),
                    (self._downloader, "shutdown", "下载器"),
                    (self._client, "disconnect", "客户端"),
                    (self._status_tracker, "shutdown", "状态追踪器"),
                    (self._history_tracker, "close", "历史记录跟踪器"),
                    (self._json_storage, "close", "JSON存储")
                ]
                
                for component, method_name, component_name in components_to_close:
                    if component is not None:
                        try:
                            close_method = getattr(component, method_name, None)
                            if close_method is not None and callable(close_method):
                                # 检查方法是否为协程方法
                                if asyncio.iscoroutinefunction(close_method):
                                    # 如果是协程方法，使用await
                                    await close_method()
                                else:
                                    # 如果不是协程方法，直接调用
                                    close_method()
                                self._app_logger.debug(f"{component_name}已关闭")
                        except Exception as component_error:
                            self._app_logger.error(f"关闭{component_name}时出错: {str(component_error)}")
                
                # 关闭日志记录器
                if self._logger:
                    self._logger.shutdown()
                
                self._app_logger.info("已清理初始化失败的资源")
            except Exception as cleanup_error:
                self._app_logger.error(f"清理资源时出错: {str(cleanup_error)}")
            
            return False
    
    async def shutdown(self) -> None:
        """关闭应用程序，释放所有资源"""
        if not self._initialized:
            return
        
        self._app_logger.info("正在关闭应用...")
        
        # 标记正在关闭
        self._shutting_down = True
        
        # 触发关闭事件
        await self._trigger_event("app_shutdown", {})
        
        # 停止转发服务
        if self._forwarder and self._forwarder.get_forwarding_status().get('running', False):
            await self.stop_forwarding()
        
        # 按顺序关闭组件
        components_to_close = [
            (self._forwarder, "shutdown", "转发器"),
            (self._uploader, "shutdown", "上传器"),
            (self._downloader, "shutdown", "下载器"),
            (self._client, "disconnect", "客户端"),
            (self._status_tracker, "shutdown", "状态追踪器"),
            (self._json_storage, "close", "JSON存储")
        ]
        
        for component, method_name, component_name in components_to_close:
            if component is not None:
                try:
                    self._app_logger.debug(f"正在关闭{component_name}...")
                    close_method = getattr(component, method_name, None)
                    if close_method is not None and callable(close_method):
                        # 检查方法是否为协程方法
                        if asyncio.iscoroutinefunction(close_method):
                            # 如果是协程方法，使用await
                            await close_method()
                        else:
                            # 如果不是协程方法，直接调用
                            close_method()
                    self._app_logger.debug(f"{component_name}已关闭")
                except Exception as e:
                    self._app_logger.error(f"关闭{component_name}时出错: {str(e)}")
        
        # 清空事件处理器
        self._event_handlers.clear()
        
        # 关闭日志记录器
        if self._logger:
            self._logger.shutdown()
        
        # 标记为未初始化
        self._initialized = False
        self._app_logger.info("应用已成功关闭")
    
    def get_client(self) -> TelegramClientInterface:
        """
        获取Telegram客户端实例
        
        Returns:
            TelegramClientInterface: Telegram客户端接口实例
        """
        return self._client
    
    def get_downloader(self) -> DownloaderInterface:
        """
        获取下载器实例
        
        Returns:
            DownloaderInterface: 下载器接口实例
        """
        return self._downloader
    
    def get_uploader(self) -> UploaderInterface:
        """
        获取上传器实例
        
        Returns:
            UploaderInterface: 上传器接口实例
        """
        return self._uploader
    
    def get_forwarder(self) -> ForwarderInterface:
        """
        获取转发器实例
        
        Returns:
            ForwarderInterface: 转发器接口实例
        """
        return self._forwarder
    
    def get_config(self) -> ConfigInterface:
        """
        获取配置管理实例
        
        Returns:
            ConfigInterface: 配置接口实例
        """
        return self._config
    
    def get_status_tracker(self) -> StatusTrackerInterface:
        """
        获取状态跟踪器实例
        
        Returns:
            StatusTrackerInterface: 状态跟踪器接口实例
        """
        return self._status_tracker
    
    def get_json_storage(self) -> JsonStorageInterface:
        """
        获取JSON存储实例
        
        Returns:
            JsonStorageInterface: JSON存储接口实例
        """
        return self._json_storage
    
    def get_history_tracker(self) -> HistoryTrackerInterface:
        """
        获取历史记录跟踪器实例
        
        Returns:
            HistoryTrackerInterface: 历史记录跟踪器接口实例
        """
        return self._history_tracker
    
    def get_logger(self) -> LoggerInterface:
        """
        获取日志器实例
        
        Returns:
            LoggerInterface: 日志接口实例
        """
        return self._logger
    
    async def start_forwarding(self) -> bool:
        """
        启动消息转发服务
        
        Returns:
            bool: 启动是否成功
        """
        self._app_logger.info("启动消息转发服务")
        
        if not self._initialized:
            await self.initialize()
        
        # 获取转发配置
        forward_config = self._config.get_forward_config()
        
        # 在配置中验证必要的参数
        channel_pairs = forward_config.get("channel_pairs", {})
        if not channel_pairs:
            self._app_logger.error("未配置有效的频道对")
            return False
        
        # 启动转发服务
        result = await self._forwarder.start_forwarding(forward_config, False)
        
        if result.get("success", False):
            self._app_logger.info("消息转发服务已启动")
            return True
        else:
            self._app_logger.error(f"启动消息转发服务失败: {result.get('error', '未知错误')}")
            return False
    
    async def stop_forwarding(self) -> bool:
        """
        停止消息转发服务
        
        Returns:
            bool: 停止是否成功
        """
        if not self._initialized:
            self._app_logger.error("应用未初始化，无法停止转发服务")
            return False
        
        if not self._running:
            self._app_logger.warning("转发服务未在运行")
            return True
        
        try:
            self._app_logger.info("正在停止转发服务...")
            
            result = await self._forwarder.stop_forwarding()
            
            if result["success"]:
                self._running = False
                self._app_logger.info("转发服务已停止")
                
                # 触发事件
                await self._trigger_event("forwarding_stopped", result)
                
                return True
            else:
                self._app_logger.error(f"停止转发服务失败: {result.get('error')}")
                return False
        
        except Exception as e:
            self._app_logger.error(f"停止转发服务时出错: {str(e)}", exc_info=True)
            return False
    
    async def restart_components(self, components: List[str] = None) -> Dict[str, bool]:
        """
        重启指定组件
        
        Args:
            components: 要重启的组件名称列表，为None时重启所有组件
            
        Returns:
            Dict[str, bool]: 各组件重启结果
        """
        if not self._initialized:
            self._app_logger.error("应用未初始化，无法重启组件")
            return {"error": "应用未初始化"}
        
        # 定义所有可重启的组件
        all_components = [
            "client", "downloader", "uploader", "forwarder",
            "status_tracker"
        ]
        
        # 如果未指定组件，重启所有组件
        if components is None:
            components = all_components
        
        results = {}
        was_running = self._running
        
        try:
            # 如果转发服务正在运行，先停止它
            if was_running:
                await self.stop_forwarding()
            
            # 按依赖关系反向顺序关闭组件
            for component_name in reversed(components):
                if component_name not in all_components:
                    results[component_name] = False
                    continue
                
                self._app_logger.info(f"正在关闭组件: {component_name}")
                
                component = getattr(self, f"_{component_name}")
                if component:
                    if hasattr(component, "shutdown"):
                        close_method = getattr(component, "shutdown")
                        if asyncio.iscoroutinefunction(close_method):
                            await close_method()
                        else:
                            close_method()
                    elif hasattr(component, "disconnect"):
                        close_method = getattr(component, "disconnect")
                        if asyncio.iscoroutinefunction(close_method):
                            await close_method()
                        else:
                            close_method()
                    elif hasattr(component, "close"):
                        close_method = getattr(component, "close")
                        if asyncio.iscoroutinefunction(close_method):
                            await close_method()
                        else:
                            close_method()
                
                results[component_name] = True
            
            # 按依赖关系正向顺序重新初始化组件
            for component_name in components:
                if component_name not in all_components or not results[component_name]:
                    continue
                
                self._app_logger.info(f"正在重新初始化组件: {component_name}")
                
                if component_name == "client":
                    await self._client.connect()
                
                elif component_name == "status_tracker":
                    await self._status_tracker.initialize()
                
                elif component_name == "downloader":
                    await self._downloader.initialize()
                
                elif component_name == "uploader":
                    await self._uploader.initialize()
                
                elif component_name == "forwarder":
                    await self._forwarder.initialize()
            
            # 如果之前在运行，重新启动转发服务
            if was_running:
                await self.start_forwarding()
            
            # 触发事件
            await self._trigger_event("components_restarted", results)
            
            return results
        
        except Exception as e:
            self._app_logger.error(f"重启组件时出错: {str(e)}", exc_info=True)
            return {"error": str(e)}
    
    def get_application_status(self) -> Dict[str, Any]:
        """
        获取应用程序状态
        
        Returns:
            Dict[str, Any]: 应用状态信息
        """
        status = {
            "initialized": self._initialized,
            "running": self._running,
            "version": self.get_version(),
            "uptime": time.time() - self._start_time if self._start_time else 0
        }
        
        # 如果应用已初始化，获取更多状态信息
        if self._initialized:
            # 获取各组件状态
            if self._client:
                status["client"] = {
                    "connected": self._client.is_connected() if hasattr(self._client, "is_connected") else False
                }
            
            if self._forwarder:
                status["forwarder"] = self._forwarder.get_forwarding_status()
        
        return status
    
    def get_version(self) -> str:
        """
        获取应用程序版本
        
        Returns:
            str: 版本号
        """
        return self.VERSION
    
    async def health_check(self) -> Dict[str, Any]:
        """
        执行应用健康检查
        
        Returns:
            Dict[str, Any]: 健康状态
        """
        health = {
            "success": True,
            "status": "healthy",
            "timestamp": datetime.now().isoformat(),
            "components": {}
        }
        
        if not self._initialized:
            health["success"] = False
            health["status"] = "not_initialized"
            return health
        
        # 检查各组件的状态
        try:
            # 检查客户端连接
            client_connected = await self._check_client_connection()
            health["components"]["client"] = {
                "status": "connected" if client_connected else "disconnected",
                "healthy": client_connected
            }
            
            # 检查存储
            storage_healthy = await self._check_storage()
            health["components"]["storage"] = {
                "status": "operational" if storage_healthy else "error",
                "healthy": storage_healthy
            }
            
            # 检查转发器
            forwarder_healthy = self._forwarder is not None and self._forwarder.is_initialized()
            health["components"]["forwarder"] = {
                "status": "operational" if forwarder_healthy else "error",
                "healthy": forwarder_healthy,
                "running": self._running
            }
            
            # 更新整体状态
            all_healthy = all(comp["healthy"] for comp in health["components"].values())
            health["success"] = all_healthy
            health["status"] = "healthy" if all_healthy else "degraded"
            
            return health
        
        except Exception as e:
            self._app_logger.error(f"健康检查时出错: {str(e)}", exc_info=True)
            return {
                "success": False,
                "status": "error",
                "error": str(e),
                "timestamp": datetime.now().isoformat()
            }
    
    def register_event_handler(self, event_type: str, handler_func: Callable) -> None:
        """
        注册事件处理器
        
        Args:
            event_type: 事件类型
            handler_func: 处理函数
        """
        if event_type not in self._event_handlers:
            self._event_handlers[event_type] = []
        
        if handler_func not in self._event_handlers[event_type]:
            self._event_handlers[event_type].append(handler_func)
            self._app_logger.debug(f"已注册事件处理器: {event_type}")
    
    def unregister_event_handler(self, event_type: str, handler_func: Callable) -> bool:
        """
        注销事件处理器
        
        Args:
            event_type: 事件类型
            handler_func: 处理函数
            
        Returns:
            bool: 是否成功注销
        """
        if event_type not in self._event_handlers:
            return False
        
        if handler_func in self._event_handlers[event_type]:
            self._event_handlers[event_type].remove(handler_func)
            self._app_logger.debug(f"已注销事件处理器: {event_type}")
            return True
        
        return False
    
    # 内部辅助方法
    
    async def _trigger_event(self, event_type: str, event_data: Dict[str, Any]) -> None:
        """
        触发事件并通知所有注册的处理器
        
        Args:
            event_type: 事件类型
            event_data: 事件数据
        """
        if event_type not in self._event_handlers:
            return
        
        for handler in self._event_handlers[event_type]:
            try:
                result = handler(event_data)
                if asyncio.iscoroutine(result):
                    await result
            except Exception as e:
                self._app_logger.error(f"事件处理器出错: {event_type}, {str(e)}", exc_info=True)
    
    def _register_signal_handlers(self) -> None:
        """注册信号处理器，用于优雅关闭"""
        try:
            import signal
            
            def signal_handler(sig, frame):
                print(f"\n收到信号 {sig}，正在关闭应用...")
                self._app_logger.info(f"收到信号 {sig}，准备关闭应用")
                
                # 直接使用os._exit()退出程序，不尝试进行优雅关闭
                # 这对CTRL+C响应更为可靠，尤其在Windows环境
                print("程序退出中...")
                os._exit(0)
            
            # 注册 SIGINT 和 SIGTERM 信号处理器
            signal.signal(signal.SIGINT, signal_handler)
            signal.signal(signal.SIGTERM, signal_handler)
            
            # 在Windows上，设置更直接的控制台处理函数
            if os.name == 'nt':
                try:
                    import win32api
                    def windows_handler(ctrl_type):
                        if ctrl_type in (0, 2):  # CTRL_C_EVENT 或 CTRL_BREAK_EVENT
                            print("\n收到Windows控制事件，强制退出程序...")
                            self._app_logger.info("收到Windows控制事件，强制退出程序")
                            # 直接退出，不尝试优雅关闭
                            os._exit(0)
                            return True  # 返回True表示我们处理了这个事件
                        return False
                    win32api.SetConsoleCtrlHandler(windows_handler, True)
                    self._app_logger.info("已注册Windows控制台处理函数")
                except ImportError:
                    self._app_logger.warning("无法导入win32api模块，Windows控制台事件可能无法正确处理")
        
        except (ImportError, AttributeError) as e:
            # Windows可能不支持某些信号
            self._app_logger.warning(f"无法注册所有信号处理器: {e}")
    
    async def _handle_shutdown(self) -> None:
        """处理应用关闭的辅助方法"""
        self._app_logger.info("正在处理应用关闭...")
        try:
            # 设置关闭标志，防止重复关闭
            if hasattr(self, '_shutting_down') and self._shutting_down:
                self._app_logger.info("应用已经在关闭过程中")
                return
            
            # 设置关闭标志
            self._shutting_down = True
            
            # 停止转发服务
            if self._running:
                try:
                    await self.stop_forwarding()
                except Exception as e:
                    self._app_logger.error(f"停止转发服务失败: {e}")
            
            # 执行完整的关闭流程
            await self.shutdown()
            
            # 强制结束程序，避免事件循环中的其他任务阻止退出
            self._app_logger.info("应用已完全关闭，退出程序")
            os._exit(0)
        except Exception as e:
            self._app_logger.error(f"关闭处理过程中出错: {e}")
            # 出现错误时，强制退出
            os._exit(1)
    
    async def _check_client_connection(self) -> bool:
        """
        检查Telegram客户端连接状态
        
        Returns:
            bool: 是否已连接
        """
        if not self._client:
            return False
        
        try:
            # 检查客户端是否已连接
            is_connected = False
            if hasattr(self._client, "is_connected"):
                try:
                    # 如果is_connected是一个方法而不是属性
                    if callable(self._client.is_connected):
                        is_connected_result = self._client.is_connected()
                        # 检查是否为协程对象
                        if asyncio.iscoroutine(is_connected_result):
                            is_connected = await is_connected_result
                        else:
                            is_connected = is_connected_result
                    else:
                        # 如果是属性而不是方法
                        is_connected = self._client.is_connected
                except Exception:
                    is_connected = False
            
            # 如果客户端未连接，尝试连接
            if not is_connected:
                try:
                    await self._client.connect()
                except Exception:
                    return False
            
            # 尝试获取自身信息以验证连接
            try:
                me = await self._client.get_me()
                return me is not None
            except Exception:
                return False
        except Exception:
            return False
    
    async def _check_storage(self) -> bool:
        """
        检查存储组件状态
        
        Returns:
            bool: 存储是否正常
        """
        # 检查JSON存储
        if not self._json_storage:
            self._app_logger.error("JSON存储组件未初始化")
            return False
        
        try:
            # 验证JSON存储结构
            if not await self._json_storage.validate_history_structure():
                self._app_logger.error("JSON存储结构验证失败")
                return False
            
            # 检查历史跟踪器
            if not self._history_tracker:
                self._app_logger.error("历史跟踪器未初始化")
                return False
            
            # 尝试导出数据验证历史跟踪器状态
            history_data = self._history_tracker.export_history_data()
            if history_data is None:
                self._app_logger.error("历史跟踪器数据导出失败")
                return False
            
            return True
        except Exception as e:
            self._app_logger.error(f"存储检查失败: {e}")
            return False
    
    async def upload_files(self, upload_config: Dict[str, Any] = None) -> Dict[str, Any]:
        """
        上传本地文件到目标频道
        
        Args:
            upload_config: 上传配置，为None时使用默认配置
            
        Returns:
            Dict[str, Any]: 上传结果
        """
        self._app_logger.info("开始上传本地文件")
        
        if not self._initialized:
            await self.initialize()
        
        if not upload_config:
            upload_config = self._config.get_upload_config()
        
        return await self._uploader.upload_files(upload_config)
    
    async def start_monitor(self, monitor_config: Dict[str, Any] = None) -> Dict[str, Any]:
        """
        启动监听服务，实时监听源频道的新消息并转发到目标频道
        
        Args:
            monitor_config: 监听配置，为None时使用默认配置。配置应包含：
                - channel_pairs: 源频道与目标频道的映射关系
                - duration: 监听时长，格式为"年-月-日-时"，如"2025-3-28-1"
                - remove_captions: 是否移除原始字幕
                - media_types: 要转发的媒体类型列表
                - forward_delay: 转发延迟（秒）
                - max_retries: 失败后最大重试次数
                - message_filter: 消息过滤器表达式
            
        Returns:
            Dict[str, Any]: 启动结果，包含以下字段：
                - success: 是否成功启动
                - error: 如果失败，包含错误信息
                - monitor_id: 监听任务ID
                - start_time: 开始时间
                - end_time: 预计结束时间（根据duration计算）
        """
        self._app_logger.info("开始启动监听服务")
        
        # 确保应用已初始化
        if not self._initialized:
            await self.initialize()
        
        # 如果没有提供配置，使用默认配置
        if monitor_config is None:
            monitor_config = self._config.get_monitor_config()
            self._app_logger.info(f"使用默认监听配置: {monitor_config}")
        
        # 验证频道对配置
        channel_pairs = monitor_config.get("channel_pairs", {})
        if not channel_pairs:
            error_msg = "监听配置中缺少有效的频道对"
            self._app_logger.error(error_msg)
            return {
                "success": False,
                "error": error_msg
            }
        
        # 确保频道对格式正确
        try:
            for source, targets in channel_pairs.items():
                if not isinstance(source, (str, int)):
                    raise ValueError(f"源频道格式不正确: {source}")
                if not isinstance(targets, list):
                    raise ValueError(f"目标频道必须是列表: {targets}")
                if not targets:
                    raise ValueError(f"源频道 {source} 没有指定目标频道")
        except ValueError as e:
            error_msg = f"监听配置验证失败: {str(e)}"
            self._app_logger.error(error_msg)
            return {
                "success": False,
                "error": error_msg
            }
        
        # 启动监听
        try:
            result = await self._forwarder.start_monitor(monitor_config)
            
            # 如果启动成功，记录监听状态
            if result.get("success", False):
                self._app_logger.info(f"监听服务启动成功: {result.get('monitor_id', '')}")
                self._monitor_status = {
                    "running": True,
                    "start_time": datetime.now(),
                    "monitor_id": result.get("monitor_id", ""),
                    "config": monitor_config
                }
            else:
                self._app_logger.error(f"监听服务启动失败: {result.get('error', '未知错误')}")
            
            return result
        except Exception as e:
            error_msg = f"启动监听服务出错: {str(e)}"
            self._app_logger.error(error_msg, exc_info=True)
            return {
                "success": False,
                "error": error_msg
            }
    
    async def stop_monitor(self) -> Dict[str, Any]:
        """
        停止监听服务
        
        Returns:
            Dict[str, Any]: 停止结果，包含以下字段：
                - success: 是否成功停止
                - error: 如果失败，包含错误信息
                - monitor_id: 监听任务ID
                - duration: 实际监听时长（秒）
                - messages_forwarded: 已转发的消息数量
        """
        self._app_logger.info("开始停止监听服务")
        
        # 检查监听服务是否在运行
        if not hasattr(self, '_monitor_status') or not self._monitor_status or not self._monitor_status.get("running", False):
            error_msg = "监听服务未在运行"
            self._app_logger.warning(error_msg)
            return {
                "success": False,
                "error": error_msg
            }
        
        # 停止监听
        try:
            result = await self._forwarder.stop_monitor()
            
            # 如果停止成功，更新监听状态
            if result.get("success", False):
                self._app_logger.info(f"监听服务已停止: {result.get('monitor_id', '')}")
                
                # 计算持续时间
                if "start_time" in self._monitor_status:
                    duration = (datetime.now() - self._monitor_status["start_time"]).total_seconds()
                    result["duration"] = duration
                
                # 重置监听状态
                self._monitor_status = {
                    "running": False,
                    "end_time": datetime.now(),
                    "last_monitor_id": self._monitor_status.get("monitor_id", ""),
                    "last_duration": result.get("duration", 0),
                    "messages_forwarded": result.get("messages_forwarded", 0)
                }
            else:
                self._app_logger.error(f"停止监听服务失败: {result.get('error', '未知错误')}")
            
            return result
        except Exception as e:
            error_msg = f"停止监听服务出错: {str(e)}"
            self._app_logger.error(error_msg, exc_info=True)
            return {
                "success": False,
                "error": error_msg
            }
    
    def get_monitor_status(self) -> Dict[str, Any]:
        """
        获取监听服务状态
        
        Returns:
            Dict[str, Any]: 监听服务状态信息，包含以下字段：
                - running: 是否正在运行
                - start_time: 开始时间
                - end_time: 预计结束时间
                - remaining_time: 剩余时间（秒）
                - messages_forwarded: 已转发的消息数量
                - channel_pairs: 监听的频道对
                - errors: 错误统计
        """
        # 如果应用未初始化或监听状态不存在，返回未运行状态
        if not self._initialized or not hasattr(self, '_monitor_status') or not self._monitor_status:
            return {
                "running": False,
                "message": "监听服务未初始化或未运行过"
            }
        
        # 获取转发器中的实时状态
        forwarder_status = self._forwarder.get_monitor_status()
        
        # 合并应用层和转发器层的状态
        status = {
            **self._monitor_status,
            **forwarder_status
        }
        
        # 确保基本字段存在
        status["running"] = status.get("running", False)
        
        # 格式化时间
        if "start_time" in status and not isinstance(status["start_time"], str):
            status["start_time"] = status["start_time"].isoformat()
        if "end_time" in status and not isinstance(status["end_time"], str):
            status["end_time"] = status["end_time"].isoformat()
        
        return status
    
    async def download_messages(self, download_config: Dict[str, Any] = None) -> Dict[str, Any]:
        """
        下载消息和媒体
        
        Args:
            download_config: 下载配置，为None时使用默认配置
            
        Returns:
            Dict[str, Any]: 下载结果
        """
        self._app_logger.info("开始下载消息")
        
        if not self._initialized:
            await self.initialize()
        
        if not download_config:
            download_config = self._config.get_download_config()
        
        return await self._downloader.download_messages(download_config)
    
    async def register_channel(self, channel_identifier: Union[str, int]) -> Dict[str, Any]:
        # ... existing code ...
        pass
    
    def get_channel_utils(self) -> ChannelUtilsInterface:
        """
        获取频道工具实例
        
        Returns:
            ChannelUtilsInterface: 频道工具接口实例
        """
        # 使用核心层的工厂函数获取或创建全局频道工具实例
        from tg_forwarder.core.channel_factory import get_channel_utils
        
        # 传递客户端到频道工具实例
        if self._client:
            return get_channel_utils(self._client)
        
        return get_channel_utils() 