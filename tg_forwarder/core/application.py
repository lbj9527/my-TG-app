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
from tg_forwarder.interfaces.task_manager_interface import TaskManagerInterface
from tg_forwarder.interfaces.storage_interface import StorageInterface
from tg_forwarder.interfaces.logger_interface import LoggerInterface

from tg_forwarder.core.config_manager import ConfigManager
from tg_forwarder.core.logger import Logger
from tg_forwarder.core.storage import Storage
from tg_forwarder.core.status_tracker import StatusTracker
from tg_forwarder.core.task_manager import TaskManager
from tg_forwarder.core.telegram_client import TelegramClient
from tg_forwarder.core.downloader import Downloader
from tg_forwarder.core.uploader import Uploader
from tg_forwarder.core.forwarder import Forwarder


class Application(ApplicationInterface):
    """
    应用程序类，实现ApplicationInterface接口
    负责整合所有核心组件并提供统一的应用程序管理
    """
    
    # 应用程序版本
    VERSION = "1.0.0"
    
    # 添加一个全局的应用程序实例引用，用于信号处理
    _instance = None
    
    @staticmethod
    def setup_signal_handling():
        """
        设置全局信号处理
        这个方法应该在主程序入口中调用
        """
        import signal
        import os
        import asyncio
        import threading
        
        def global_signal_handler(sig, frame):
            print(f"\n接收到信号 {sig}，正在关闭应用...")
            
            # 获取当前应用实例
            app = Application._instance
            if app:
                # 尝试使用事件循环关闭应用
                try:
                    loop = asyncio.get_event_loop()
                    if loop.is_running():
                        loop.create_task(app._handle_shutdown())
                    else:
                        # 如果事件循环未运行，创建新的事件循环
                        def run_shutdown():
                            new_loop = asyncio.new_event_loop()
                            asyncio.set_event_loop(new_loop)
                            try:
                                new_loop.run_until_complete(app._handle_shutdown())
                            finally:
                                new_loop.close()
                        
                        # 在新线程中运行关闭流程
                        shutdown_thread = threading.Thread(target=run_shutdown)
                        shutdown_thread.daemon = True
                        shutdown_thread.start()
                        shutdown_thread.join(timeout=5)  # 等待最多5秒
                except Exception as e:
                    print(f"关闭应用时出错: {e}")
            
            # 如果5秒内未完成关闭，强制退出
            print("强制退出程序")
            os._exit(0)
        
        # 注册全局信号处理
        signal.signal(signal.SIGINT, global_signal_handler)
        signal.signal(signal.SIGTERM, global_signal_handler)
        
        # 在Windows上设置控制台处理函数
        if os.name == 'nt':
            try:
                import win32api
                def windows_handler(ctrl_type):
                    if ctrl_type in (0, 2):  # CTRL_C_EVENT 或 CTRL_BREAK_EVENT
                        print("收到Windows控制事件，准备关闭应用")
                        global_signal_handler(signal.SIGINT, None)
                        return True  # 返回True表示我们处理了这个事件
                    return False
                win32api.SetConsoleCtrlHandler(windows_handler, True)
                print("已注册Windows控制台处理函数")
            except ImportError:
                print("无法导入win32api模块，Windows控制台事件可能无法正确处理")
    
    def __init__(self, config_path: str = None):
        """
        初始化应用程序
        
        Args:
            config_path: 配置文件路径，为None时使用默认路径
        """
        # 设置全局实例引用
        Application._instance = self
        
        # 初始化状态
        self._initialized = False
        self._running = False
        self._event_handlers = {}
        self._start_time = None
        
        # 创建并初始化配置管理器
        self._config = ConfigManager(config_path)
        
        # 创建日志记录器
        self._logger = Logger()
        self._app_logger = self._logger.get_logger("Application")
        
        # 其他组件将在initialize方法中初始化
        self._storage = None
        self._status_tracker = None
        self._task_manager = None
        self._client = None
        self._downloader = None
        self._uploader = None
        self._forwarder = None
    
    async def initialize(self) -> bool:
        """
        初始化应用程序
        
        Returns:
            bool: 初始化是否成功
        """
        if self._initialized:
            self._app_logger.warning("应用已经初始化")
            return True
        
        try:
            self._app_logger.info("正在初始化应用...")
            
            # 添加关闭标志
            self._shutting_down = False
            
            # 加载配置
            config_loaded = self._config.load_config()
            if not config_loaded:
                self._app_logger.error("加载配置失败，应用无法初始化")
                return False
            
            # 初始化日志记录器
            log_config = self._config.get("log") or {}
            log_file = log_config.get("file", "logs/tg_forwarder.log")
            log_level = log_config.get("level", "INFO")
            log_rotation = log_config.get("rotation", "10 MB")
            
            self._logger.initialize(log_file, log_level, log_rotation)
            
            # 初始化存储
            storage_config = self._config.get("storage") or {}
            db_path = storage_config.get("db_path", "data/tg_forwarder.db")
            self._storage = Storage(db_path)
            await self._storage.initialize()
            
            # 初始化状态追踪器
            self._status_tracker = StatusTracker(self._storage, self._logger)
            await self._status_tracker.initialize()
            
            # 初始化任务管理器
            task_manager_config = self._config.get("task_manager") or {}
            max_workers = task_manager_config.get("max_workers", 5)
            self._task_manager = TaskManager(self._logger)
            self._task_manager.initialize(max_workers)
            
            # 初始化Telegram客户端
            self._client = TelegramClient(self._config, self._logger)
            
            # 初始化下载器
            download_config = self._config.get("download") or {}
            self._downloader = Downloader(
                self._client,
                self._config,
                self._logger,
                self._storage,
                self._status_tracker
            )
            await self._downloader.initialize()
            
            # 初始化上传器
            upload_config = self._config.get("upload") or {}
            self._uploader = Uploader(
                self._client,
                self._config,
                self._logger,
                self._storage,
                self._status_tracker
            )
            await self._uploader.initialize()
            
            # 初始化转发器
            self._forwarder = Forwarder(
                self._client,
                self._downloader,
                self._uploader,
                self._status_tracker,
                self._task_manager,
                self._config,
                self._logger
            )
            await self._forwarder.initialize()
            
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
                    (self._task_manager, "shutdown", "任务管理器"),
                    (self._status_tracker, "shutdown", "状态追踪器"),
                    (self._storage, "close", "存储")
                ]
                
                for component, method_name, component_name in components_to_close:
                    if component is not None:
                        try:
                            close_method = getattr(component, method_name, None)
                            if close_method is not None and callable(close_method):
                                # 特殊处理任务管理器的关闭，因为它不是异步方法
                                if component is self._task_manager and method_name == "shutdown":
                                    close_method(wait=True)
                                else:
                                    result = close_method()
                                    
                                    if asyncio.iscoroutine(result):
                                        await result
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
        
        # 触发关闭事件
        await self._trigger_event("app_shutdown", {})
        
        # 停止转发服务
        if self._running:
            await self.stop_forwarding()
        
        # 按顺序关闭组件
        if self._forwarder:
            await self._forwarder.shutdown()
        
        if self._uploader:
            await self._uploader.shutdown()
        
        if self._downloader:
            await self._downloader.shutdown()
        
        if self._client:
            await self._client.disconnect()
        
        if self._task_manager:
            # TaskManager.shutdown 不是异步方法，不需要await
            self._task_manager.shutdown(wait=True)
        
        if self._status_tracker:
            self._status_tracker.shutdown()
        
        if self._storage:
            await self._storage.close()
        
        # 关闭日志记录器
        self._logger.shutdown()
        
        self._initialized = False
        self._app_logger.info("应用已关闭")
    
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
    
    def get_task_manager(self) -> TaskManagerInterface:
        """
        获取任务管理器实例
        
        Returns:
            TaskManagerInterface: 任务管理器接口实例
        """
        return self._task_manager
    
    def get_storage(self) -> StorageInterface:
        """
        获取存储实例
        
        Returns:
            StorageInterface: 存储接口实例
        """
        return self._storage
    
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
        if not self._initialized:
            self._app_logger.error("应用未初始化，无法启动转发服务")
            return False
        
        if self._running:
            self._app_logger.warning("转发服务已经在运行")
            return True
        
        try:
            self._app_logger.info("正在启动转发服务...")
            
            # 确保客户端已连接
            await self._client.connect()
            
            # 获取源频道和目标频道
            source_channels = self._config.get_source_channels()
            target_channels = self._config.get_target_channels()
            
            if not source_channels:
                self._app_logger.error("未配置源频道，无法启动转发服务")
                return False
            
            if not target_channels:
                self._app_logger.error("未配置目标频道，无法启动转发服务")
                return False
            
            # 获取转发配置
            forward_config = self._config.get_value("forward") or {}
            caption_template = forward_config.get("caption_template")
            remove_captions = forward_config.get("remove_captions", False)
            download_media = forward_config.get("download_media", True)
            
            # 启动转发
            result = self._forwarder.start_forwarding(
                source_channels,
                target_channels,
                caption_template=caption_template,
                remove_captions=remove_captions,
                download_media=download_media
            )
            
            if result["success"]:
                self._running = True
                self._app_logger.info("转发服务已启动")
                
                # 触发事件
                await self._trigger_event("forwarding_started", result)
                
                return True
            else:
                self._app_logger.error(f"启动转发服务失败: {result.get('error')}")
                return False
        
        except Exception as e:
            self._app_logger.error(f"启动转发服务时出错: {str(e)}", exc_info=True)
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
            
            result = self._forwarder.stop_forwarding()
            
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
            "task_manager", "status_tracker", "storage"
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
                        await component.shutdown()
                    elif hasattr(component, "disconnect"):
                        await component.disconnect()
                    elif hasattr(component, "close"):
                        await component.close()
                
                results[component_name] = True
            
            # 按依赖关系正向顺序重新初始化组件
            for component_name in components:
                if component_name not in all_components or not results[component_name]:
                    continue
                
                self._app_logger.info(f"正在重新初始化组件: {component_name}")
                
                if component_name == "client":
                    await self._client.connect()
                
                elif component_name == "storage":
                    await self._storage.initialize()
                
                elif component_name == "status_tracker":
                    await self._status_tracker.initialize()
                
                elif component_name == "task_manager":
                    task_config = self._config.get_value("task_manager") or {}
                    max_workers = task_config.get("max_workers", 10)
                    await self._task_manager.initialize(max_workers)
                
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
            
            if self._task_manager:
                all_tasks = self._task_manager.get_all_tasks()
                status["task_manager"] = {
                    "total_tasks": len(all_tasks),
                    "active_tasks": len(self._task_manager.get_active_tasks()),
                    "queues": self._task_manager.get_queue_info() if hasattr(self._task_manager, "get_queue_info") else {}
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
    
    async def backup_data(self, backup_path: Optional[str] = None) -> Dict[str, Any]:
        """
        备份应用数据
        
        Args:
            backup_path: 备份路径，为None时使用默认路径
            
        Returns:
            Dict[str, Any]: 备份结果
        """
        if not self._initialized:
            self._app_logger.error("应用未初始化，无法备份数据")
            return {"success": False, "error": "应用未初始化"}
        
        try:
            # 使用默认备份路径
            if backup_path is None:
                backup_config = self._config.get_value("backup") or {}
                backup_dir = backup_config.get("directory", "backups")
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                backup_path = os.path.join(backup_dir, f"tg_forwarder_backup_{timestamp}")
            
            # 确保备份目录存在
            os.makedirs(os.path.dirname(backup_path), exist_ok=True)
            
            self._app_logger.info(f"开始备份数据到: {backup_path}")
            
            # 备份配置文件
            config_backup = os.path.join(backup_path, "config")
            os.makedirs(config_backup, exist_ok=True)
            config_data = self._config.export()
            with open(os.path.join(config_backup, "config.json"), "w") as f:
                json.dump(config_data, f, indent=2)
            
            # 备份数据库
            db_backup = await self._storage.backup(os.path.join(backup_path, "database"))
            
            # 备份下载的媒体文件（如果配置了）
            backup_config = self._config.get_value("backup") or {}
            include_media = backup_config.get("include_media", False)
            
            if include_media and self._downloader:
                download_dir = self._downloader.get_download_directory()
                if os.path.exists(download_dir):
                    media_backup = os.path.join(backup_path, "media")
                    shutil.copytree(download_dir, media_backup)
            
            result = {
                "success": True,
                "backup_path": backup_path,
                "timestamp": datetime.now().isoformat(),
                "components": {
                    "config": True,
                    "database": db_backup["success"],
                    "media": include_media
                }
            }
            
            # 触发事件
            await self._trigger_event("data_backed_up", result)
            
            self._app_logger.info(f"数据备份完成: {backup_path}")
            return result
        
        except Exception as e:
            self._app_logger.error(f"备份数据时出错: {str(e)}", exc_info=True)
            return {"success": False, "error": str(e)}
    
    async def restore_data(self, backup_path: str) -> Dict[str, Any]:
        """
        恢复应用数据
        
        Args:
            backup_path: 备份路径
            
        Returns:
            Dict[str, Any]: 恢复结果
        """
        if not os.path.exists(backup_path):
            return {"success": False, "error": f"备份路径不存在: {backup_path}"}
        
        was_initialized = self._initialized
        was_running = self._running
        
        try:
            # 如果应用已初始化，先关闭它
            if was_initialized:
                if was_running:
                    await self.stop_forwarding()
                await self.shutdown()
            
            self._app_logger.info(f"开始从 {backup_path} 恢复数据")
            
            # 恢复配置文件
            config_file = os.path.join(backup_path, "config", "config.json")
            if os.path.exists(config_file):
                with open(config_file, "r") as f:
                    config_data = json.load(f)
                self._config = ConfigManager()
                self._config.import_data(config_data)
                self._config.save()
            
            # 初始化应用（会创建新的组件实例）
            await self.initialize()
            
            # 恢复数据库
            db_backup = os.path.join(backup_path, "database")
            if os.path.exists(db_backup):
                db_result = await self._storage.restore(db_backup)
            else:
                db_result = {"success": False, "error": "数据库备份不存在"}
            
            # 恢复媒体文件（如果存在）
            media_backup = os.path.join(backup_path, "media")
            media_result = {"success": False, "skipped": True}
            
            if os.path.exists(media_backup) and self._downloader:
                download_dir = self._downloader.get_download_directory()
                if os.path.exists(download_dir):
                    shutil.rmtree(download_dir)
                shutil.copytree(media_backup, download_dir)
                media_result = {"success": True, "skipped": False}
            
            # 如果之前在运行，重新启动转发服务
            if was_running:
                await self.start_forwarding()
            
            result = {
                "success": db_result["success"],
                "backup_path": backup_path,
                "timestamp": datetime.now().isoformat(),
                "components": {
                    "config": True,
                    "database": db_result,
                    "media": media_result
                }
            }
            
            # 触发事件
            await self._trigger_event("data_restored", result)
            
            self._app_logger.info(f"数据恢复完成: {backup_path}")
            return result
        
        except Exception as e:
            self._app_logger.error(f"恢复数据时出错: {str(e)}", exc_info=True)
            
            # 尝试重新初始化应用
            try:
                if not self._initialized:
                    await self.initialize()
                
                if was_running and not self._running:
                    await self.start_forwarding()
            except:
                pass
            
            return {"success": False, "error": str(e)}
    
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
            
            # 检查任务管理器
            task_manager_healthy = self._task_manager is not None
            health["components"]["task_manager"] = {
                "status": "operational" if task_manager_healthy else "error",
                "healthy": task_manager_healthy,
                "active_tasks": len(self._task_manager.get_active_tasks()) if task_manager_healthy else 0
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
        if not self._storage:
            return False
        
        try:
            # 尝试执行简单查询测试
            test_result = await self._storage.query("test")
            return True
        except Exception as e:
            self._app_logger.error(f"存储检查失败: {e}")
            return False 