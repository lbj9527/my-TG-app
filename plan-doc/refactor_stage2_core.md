# Telegram转发工具重构计划 - 第二阶段（核心组件实现）

## 第二阶段：重构和迁移(5天)

### 任务2.1：实现插件管理器(PluginManager)

在第一阶段我们已经设计了插件管理器的接口，现在我们来实现完整功能：

```python
# tg_app/core/plugin_manager.py
import asyncio
import importlib
import inspect
from typing import Dict, List, Any, Type, Optional, Set

from tg_app.plugins.base import PluginBase
from tg_app.core.event_bus import EventBus
from tg_app.events import event_types as events
from tg_app.utils.logger import get_logger

# 获取日志记录器
logger = get_logger("plugin_manager")

class PluginManager:
    """插件管理器，负责插件的加载、卸载和管理"""
    
    def __init__(self, event_bus: EventBus):
        """
        初始化插件管理器
        
        Args:
            event_bus: 事件总线
        """
        self.event_bus = event_bus
        self.plugins: Dict[str, PluginBase] = {}
        self.activated_plugins: Set[str] = set()
    
    async def load_plugin(self, plugin_path: str) -> Optional[PluginBase]:
        """
        加载插件
        
        Args:
            plugin_path: 插件路径，格式为"包.模块.类名"
            
        Returns:
            Optional[PluginBase]: 加载的插件实例
        """
        try:
            # 分割路径
            parts = plugin_path.split(".")
            if len(parts) < 2:
                logger.error(f"插件路径格式错误: {plugin_path}")
                return None
                
            plugin_class_name = parts[-1]
            module_path = ".".join(parts[:-1])
            
            # 导入模块
            logger.debug(f"正在导入模块: {module_path}")
            module = importlib.import_module(module_path)
            
            # 获取插件类
            if not hasattr(module, plugin_class_name):
                logger.error(f"找不到插件类: {plugin_class_name}")
                return None
                
            plugin_class = getattr(module, plugin_class_name)
            
            # 检查是否是PluginBase的子类
            if not inspect.isclass(plugin_class) or not issubclass(plugin_class, PluginBase):
                logger.error(f"类 {plugin_class_name} 不是PluginBase的子类")
                return None
            
            # 创建插件实例
            logger.debug(f"正在创建插件实例: {plugin_class_name}")
            plugin = plugin_class(self.event_bus)
            plugin_id = plugin.id
            
            # 检查插件ID是否已存在
            if plugin_id in self.plugins:
                logger.error(f"插件ID已存在: {plugin_id}")
                return None
                
            # 存储插件实例
            self.plugins[plugin_id] = plugin
            
            # 发布插件加载事件
            await self.event_bus.publish(events.PLUGIN_LOADED, {
                "plugin_id": plugin_id,
                "plugin": plugin
            })
            
            logger.info(f"插件 {plugin.name} ({plugin_id}) 加载成功")
            return plugin
            
        except Exception as e:
            logger.error(f"加载插件时出错: {str(e)}")
            return None
    
    async def load_plugins_from_path(self, package_path: str) -> List[str]:
        """
        从指定包路径加载所有插件
        
        Args:
            package_path: 包路径，如"tg_app.plugins.client"
            
        Returns:
            List[str]: 成功加载的插件ID列表
        """
        try:
            # 导入包
            package = importlib.import_module(package_path)
            
            # 获取包的路径
            if not hasattr(package, "__path__"):
                logger.error(f"{package_path} 不是一个包")
                return []
                
            package_dir = package.__path__[0]
            
            # 查找所有模块
            loaded_plugins = []
            for module_info in pkgutil.iter_modules([package_dir]):
                module_name = module_info.name
                full_module_path = f"{package_path}.{module_name}"
                
                # 导入模块
                module = importlib.import_module(full_module_path)
                
                # 查找所有Plugin类
                for attr_name in dir(module):
                    attr = getattr(module, attr_name)
                    if (inspect.isclass(attr) and 
                        issubclass(attr, PluginBase) and 
                        attr is not PluginBase):
                        
                        # 加载插件
                        plugin_path = f"{full_module_path}.{attr_name}"
                        plugin = await self.load_plugin(plugin_path)
                        if plugin:
                            loaded_plugins.append(plugin.id)
            
            return loaded_plugins
            
        except Exception as e:
            logger.error(f"从路径加载插件时出错: {str(e)}")
            return []
    
    async def activate_plugin(self, plugin_id: str) -> bool:
        """
        激活插件
        
        Args:
            plugin_id: 插件ID
            
        Returns:
            bool: 是否成功激活
        """
        if plugin_id not in self.plugins:
            logger.error(f"插件不存在: {plugin_id}")
            return False
            
        if plugin_id in self.activated_plugins:
            logger.warning(f"插件 {plugin_id} 已经激活")
            return True
            
        plugin = self.plugins[plugin_id]
        
        # 检查依赖
        if not await self._check_dependencies(plugin):
            logger.error(f"插件 {plugin_id} 的依赖未满足")
            return False
            
        try:
            # 初始化插件
            logger.info(f"正在激活插件: {plugin.name} ({plugin_id})")
            await plugin.initialize()
            
            # 标记为已激活
            self.activated_plugins.add(plugin_id)
            
            # 发布插件激活事件
            await self.event_bus.publish(events.PLUGIN_ACTIVATED, {
                "plugin_id": plugin_id,
                "plugin": plugin
            })
            
            logger.info(f"插件 {plugin.name} ({plugin_id}) 激活成功")
            return True
            
        except Exception as e:
            logger.error(f"激活插件 {plugin_id} 时出错: {str(e)}")
            return False
    
    async def activate_plugins(self, plugin_ids: List[str]) -> Dict[str, bool]:
        """
        激活多个插件
        
        Args:
            plugin_ids: 插件ID列表
            
        Returns:
            Dict[str, bool]: 激活结果，键为插件ID，值为是否成功激活
        """
        results = {}
        
        # 首先建立依赖图
        dependencies = {}
        for plugin_id in plugin_ids:
            if plugin_id in self.plugins:
                dependencies[plugin_id] = self.plugins[plugin_id].dependencies
        
        # 拓扑排序，确保依赖先激活
        sorted_plugins = []
        visited = set()
        temp_visited = set()
        
        def visit(plugin_id):
            if plugin_id in temp_visited:
                logger.error(f"检测到循环依赖: {plugin_id}")
                return
            if plugin_id in visited:
                return
                
            temp_visited.add(plugin_id)
            
            if plugin_id in dependencies:
                for dep_id in dependencies[plugin_id]:
                    if dep_id in plugin_ids:  # 只访问我们想激活的插件
                        visit(dep_id)
            
            temp_visited.remove(plugin_id)
            visited.add(plugin_id)
            sorted_plugins.append(plugin_id)
        
        # 对每个插件执行拓扑排序
        for plugin_id in plugin_ids:
            if plugin_id not in visited:
                visit(plugin_id)
        
        # 按依赖顺序激活插件
        for plugin_id in sorted_plugins:
            results[plugin_id] = await self.activate_plugin(plugin_id)
        
        return results
    
    async def deactivate_plugin(self, plugin_id: str) -> bool:
        """
        停用插件
        
        Args:
            plugin_id: 插件ID
            
        Returns:
            bool: 是否成功停用
        """
        if plugin_id not in self.plugins or plugin_id not in self.activated_plugins:
            logger.warning(f"插件 {plugin_id} 未激活，无需停用")
            return False
            
        plugin = self.plugins[plugin_id]
        
        # 检查是否有其他插件依赖于此插件
        dependents = []
        for other_id, other_plugin in self.plugins.items():
            if other_id in self.activated_plugins and plugin_id in other_plugin.dependencies:
                dependents.append(other_id)
        
        if dependents:
            logger.error(f"以下插件依赖于 {plugin_id}，无法停用: {', '.join(dependents)}")
            return False
        
        try:
            # 关闭插件
            logger.info(f"正在停用插件: {plugin.name} ({plugin_id})")
            await plugin.shutdown()
            
            # 从激活列表中移除
            self.activated_plugins.remove(plugin_id)
            
            # 发布插件停用事件
            await self.event_bus.publish(events.PLUGIN_DEACTIVATED, {
                "plugin_id": plugin_id,
                "plugin": plugin
            })
            
            logger.info(f"插件 {plugin.name} ({plugin_id}) 已停用")
            return True
            
        except Exception as e:
            logger.error(f"停用插件 {plugin_id} 时出错: {str(e)}")
            return False
    
    async def unload_plugin(self, plugin_id: str) -> bool:
        """
        卸载插件
        
        Args:
            plugin_id: 插件ID
            
        Returns:
            bool: 是否成功卸载
        """
        if plugin_id not in self.plugins:
            logger.warning(f"插件 {plugin_id} 不存在，无需卸载")
            return False
            
        # 如果插件已激活，先停用
        if plugin_id in self.activated_plugins:
            if not await self.deactivate_plugin(plugin_id):
                logger.error(f"无法停用插件 {plugin_id}，卸载失败")
                return False
                
        # 获取插件实例
        plugin = self.plugins[plugin_id]
        
        # 从插件列表中移除
        del self.plugins[plugin_id]
        
        # 发布插件卸载事件
        await self.event_bus.publish(events.PLUGIN_UNLOADED, {
            "plugin_id": plugin_id,
            "plugin": plugin
        })
        
        logger.info(f"插件 {plugin.name} ({plugin_id}) 已卸载")
        return True
    
    async def _check_dependencies(self, plugin: PluginBase) -> bool:
        """
        检查插件依赖是否满足
        
        Args:
            plugin: 插件实例
            
        Returns:
            bool: 依赖是否满足
        """
        for dep_id in plugin.dependencies:
            if dep_id not in self.plugins:
                logger.error(f"依赖的插件不存在: {dep_id}")
                return False
                
            if dep_id not in self.activated_plugins:
                logger.error(f"依赖的插件未激活: {dep_id}")
                return False
                
        return True
        
    async def get_plugin(self, plugin_id: str) -> Optional[PluginBase]:
        """
        获取插件实例
        
        Args:
            plugin_id: 插件ID
            
        Returns:
            Optional[PluginBase]: 插件实例
        """
        return self.plugins.get(plugin_id)
    
    async def shutdown_all(self):
        """关闭所有插件"""
        logger.info("正在关闭所有插件...")
        
        # 按照依赖关系的反序停用插件
        # 构建依赖图
        graph = {}
        for plugin_id in self.activated_plugins:
            plugin = self.plugins[plugin_id]
            graph[plugin_id] = []
            
        for plugin_id in self.activated_plugins:
            plugin = self.plugins[plugin_id]
            for dep_id in plugin.dependencies:
                if dep_id in self.activated_plugins:
                    graph[dep_id].append(plugin_id)
        
        # 拓扑排序（反向）
        visited = set()
        result = []
        
        def dfs(node):
            visited.add(node)
            for dependent in graph[node]:
                if dependent not in visited:
                    dfs(dependent)
            result.append(node)
            
        for plugin_id in self.activated_plugins:
            if plugin_id not in visited:
                dfs(plugin_id)
        
        # 按顺序停用插件
        for plugin_id in result:
            await self.deactivate_plugin(plugin_id)
            
        self.plugins.clear()
        self.activated_plugins.clear()
        logger.info("所有插件已关闭")
```

### Tip：加入所需的缺失模块
```python
import pkgutil  # 需要在开头添加这个导入
```

### 任务2.2：实现应用类(Application)

```python
# tg_app/core/application.py
import os
import sys
import asyncio
import argparse
from typing import Dict, Any, List, Optional

from tg_app.core.event_bus import EventBus
from tg_app.core.plugin_manager import PluginManager
from tg_app.core.config_manager import ConfigManager
from tg_app.core.context import Context
from tg_app.events import event_types as events
from tg_app.utils.logger import setup_logger, get_logger

# 获取日志记录器
logger = get_logger("application")

class Application:
    """应用程序主类，负责整体流程的协调"""
    
    def __init__(self):
        """初始化应用程序"""
        self.event_bus = EventBus()
        self.config_manager = ConfigManager()
        self.plugin_manager = PluginManager(self.event_bus)
        self.context = Context(self.event_bus, self.plugin_manager, self.config_manager)
        
        self.initialized = False
        self.running = False
        
        # 注册事件处理器
        self._register_event_handlers()
    
    def _register_event_handlers(self):
        """注册应用程序级别的事件处理器"""
        # 这里可以添加对一些全局事件的处理
        pass
    
    async def initialize(self, config_path: str = "config/default_config.ini") -> bool:
        """
        初始化应用程序
        
        Args:
            config_path: 配置文件路径
            
        Returns:
            bool: 是否成功初始化
        """
        if self.initialized:
            logger.warning("应用程序已经初始化")
            return True
            
        logger.info("正在初始化应用程序...")
        
        # 发布应用初始化事件
        await self.event_bus.publish(events.APP_INIT)
        
        # 加载配置文件
        if not self.config_manager.load_config(config_path):
            logger.error(f"加载配置文件失败: {config_path}")
            return False
            
        # 验证配置文件
        if not self.config_manager.validate_config():
            logger.error("配置文件验证失败")
            return False
            
        # 设置日志系统
        log_config = self.config_manager.get_log_config()
        setup_logger(log_config)
        
        self.initialized = True
        logger.info("应用程序初始化完成")
        return True
    
    async def load_core_plugins(self) -> bool:
        """
        加载核心插件
        
        Returns:
            bool: 是否成功加载所有核心插件
        """
        logger.info("正在加载核心插件...")
        
        # 定义核心插件列表
        core_plugins = [
            "tg_app.plugins.client.ClientPlugin",
            "tg_app.plugins.utils.ChannelPlugin",
            "tg_app.plugins.utils.TaskQueuePlugin",
            "tg_app.plugins.forward.ForwardPlugin",
            "tg_app.plugins.downloader.DownloadPlugin",
            "tg_app.plugins.uploader.UploadPlugin"
        ]
        
        # 加载所有核心插件
        loaded_plugins = []
        for plugin_path in core_plugins:
            plugin = await self.plugin_manager.load_plugin(plugin_path)
            if plugin:
                loaded_plugins.append(plugin.id)
            else:
                logger.error(f"加载核心插件失败: {plugin_path}")
        
        # 检查是否所有核心插件都已加载
        success = len(loaded_plugins) == len(core_plugins)
        if success:
            logger.info(f"所有核心插件加载成功: {', '.join(loaded_plugins)}")
        else:
            logger.warning(f"部分核心插件加载失败，已加载: {', '.join(loaded_plugins)}")
            
        return success
    
    async def activate_core_plugins(self) -> bool:
        """
        激活核心插件
        
        Returns:
            bool: 是否成功激活所有核心插件
        """
        logger.info("正在激活核心插件...")
        
        # 获取所有已加载的插件
        plugin_ids = list(self.plugin_manager.plugins.keys())
        
        # 激活所有插件
        results = await self.plugin_manager.activate_plugins(plugin_ids)
        
        # 检查是否所有插件都已激活
        success = all(results.values())
        
        if success:
            logger.info("所有核心插件激活成功")
        else:
            failed_plugins = [plugin_id for plugin_id, result in results.items() if not result]
            logger.error(f"部分核心插件激活失败: {', '.join(failed_plugins)}")
            
        return success
    
    async def run(self) -> Dict[str, Any]:
        """
        运行应用程序
        
        Returns:
            Dict[str, Any]: 运行结果
        """
        if not self.initialized:
            logger.error("应用程序尚未初始化")
            return {"success": False, "error": "应用程序尚未初始化"}
            
        if self.running:
            logger.warning("应用程序已经在运行")
            return {"success": False, "error": "应用程序已经在运行"}
            
        logger.info("正在启动应用程序...")
        self.running = True
        
        try:
            # 发布应用启动事件
            await self.event_bus.publish(events.APP_START)
            
            # 获取客户端插件和转发插件
            client_plugin = await self.plugin_manager.get_plugin("client")
            forward_plugin = await self.plugin_manager.get_plugin("forward")
            
            if not client_plugin or not forward_plugin:
                logger.error("无法获取核心插件")
                return {"success": False, "error": "无法获取核心插件"}
            
            # 连接到Telegram
            connect_result = await client_plugin.connect()
            if not connect_result.get("success", False):
                logger.error(f"连接Telegram失败: {connect_result.get('error', '未知错误')}")
                return {"success": False, "error": f"连接Telegram失败: {connect_result.get('error', '未知错误')}"}
            
            # 解析频道配置
            channels_config = self.config_manager.get_channels_config()
            forward_config = self.config_manager.get_forward_config()
            
            # 运行转发流程
            forward_result = await forward_plugin.run_forward(
                channels_config["source_channel"],
                channels_config["target_channels"],
                forward_config
            )
            
            # 处理结果
            if forward_result.get("success", False):
                logger.info("转发任务执行成功")
            else:
                logger.error(f"转发任务执行失败: {forward_result.get('error', '未知错误')}")
            
            # 断开连接
            await client_plugin.disconnect()
            
            return forward_result
            
        except Exception as e:
            logger.exception(f"运行应用程序时出错: {str(e)}")
            # 发布错误事件
            await self.event_bus.publish(events.APP_ERROR, {"error": str(e)})
            return {"success": False, "error": str(e)}
            
        finally:
            self.running = False
    
    async def shutdown(self) -> None:
        """关闭应用程序"""
        if not self.initialized:
            logger.warning("应用程序尚未初始化，无需关闭")
            return
            
        logger.info("正在关闭应用程序...")
        
        # 发布应用关闭事件
        await self.event_bus.publish(events.APP_SHUTDOWN)
        
        # 关闭所有插件
        await self.plugin_manager.shutdown_all()
        
        self.initialized = False
        self.running = False
        
        logger.info("应用程序已关闭")
    
    @classmethod
    async def run_from_args(cls, args: Optional[List[str]] = None) -> int:
        """
        从命令行参数运行应用程序
        
        Args:
            args: 命令行参数，为None则使用sys.argv
            
        Returns:
            int: 退出代码
        """
        # 解析命令行参数
        parser = argparse.ArgumentParser(description="Telegram频道消息转发工具")
        
        parser.add_argument(
            "-c", "--config", 
            dest="config_path",
            default="config/default_config.ini",
            help="配置文件路径 (默认: config/default_config.ini)"
        )
        
        # 解析参数
        parsed_args = parser.parse_args(args)
        
        # 创建应用实例
        app = cls()
        
        try:
            # 初始化应用
            if not await app.initialize(parsed_args.config_path):
                logger.error("应用程序初始化失败")
                return 1
                
            # 加载核心插件
            if not await app.load_core_plugins():
                logger.error("加载核心插件失败")
                return 1
                
            # 激活核心插件
            if not await app.activate_core_plugins():
                logger.error("激活核心插件失败")
                return 1
                
            # 运行应用
            result = await app.run()
            
            # 处理结果
            if result.get("success", False):
                logger.info("应用程序运行成功")
                return 0
            else:
                logger.error(f"应用程序运行失败: {result.get('error', '未知错误')}")
                return 1
                
        except Exception as e:
            logger.exception(f"运行应用程序时出错: {str(e)}")
            return 1
            
        finally:
            # 关闭应用
            await app.shutdown()
```

### 开发说明

1. **插件管理**:
   - 实现了插件的加载、激活、停用和卸载功能
   - 添加了依赖检查和拓扑排序，确保插件按正确顺序激活和停用
   - 实现了从包路径加载多个插件的功能

2. **应用类**:
   - 作为整个应用的核心控制器
   - 管理应用的生命周期（初始化、运行、关闭）
   - 协调各个插件之间的交互
   - 提供命令行参数处理功能

3. **事件处理**:
   - 通过事件机制实现各组件之间的松耦合通信
   - 定义了丰富的事件类型，覆盖各个功能模块

## 实现建议

1. **错误处理**：确保在每个关键步骤添加适当的错误处理和日志记录
2. **依赖管理**：留意插件之间的依赖关系，避免循环依赖
3. **类型提示**：使用类型提示增强代码可读性和编辑器支持
4. **日志详情**：在关键操作点添加充分的日志，方便调试 