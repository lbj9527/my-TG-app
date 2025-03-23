"""
插件管理器模块。

本模块负责发现、加载、管理和卸载应用中的插件。
插件管理器是插件系统的核心，提供动态插件加载和生命周期管理。
"""

import os
import sys
import importlib
import importlib.util
import inspect
import pkgutil
import asyncio
import time
from pathlib import Path
from typing import Dict, List, Set, Type, Optional, Any, Tuple, cast

# 修改导入语句
from core.event_bus import EventBus
from events.event_types import (
    PLUGIN_LOADED, PLUGIN_UNLOADED, PLUGIN_ERROR,
    create_event_data
)
from plugins.base import PluginBase
from utils.logger import get_logger

# 获取日志记录器
logger = get_logger("plugin_manager")


class PluginManager:
    """
    插件管理器，负责插件的加载、初始化、卸载和管理。
    
    管理插件的完整生命周期，处理插件依赖关系，维护已加载插件的列表。
    """
    
    def __init__(self, event_bus: EventBus):
        """
        初始化插件管理器。
        
        Args:
            event_bus: 事件总线实例
        """
        self._event_bus = event_bus
        
        # 已加载的插件实例 {插件ID: 插件实例}
        self._plugins: Dict[str, PluginBase] = {}
        
        # 已发现的插件类 {插件ID: (插件类, 模块路径)}
        self._discovered_plugins: Dict[str, Tuple[Type[PluginBase], str]] = {}
        
        # 插件加载顺序，用于按顺序卸载
        self._load_order: List[str] = []
        
        # 插件依赖图 {插件ID: 依赖的插件ID集合}
        self._dependencies: Dict[str, Set[str]] = {}
        
        # 依赖当前插件的插件 {插件ID: 依赖此插件的插件ID集合}
        self._dependents: Dict[str, Set[str]] = {}
        
        # 自动发现的插件根目录
        self._plugin_dir = Path(__file__).parent.parent / "plugins"
        
        logger.info("插件管理器已初始化")
    
    async def discover_plugins(self, plugin_dirs: Optional[List[str]] = None) -> List[str]:
        """
        发现可用的插件。
        
        Args:
            plugin_dirs: 插件目录列表，如果为None则使用默认目录
            
        Returns:
            List[str]: 发现的插件ID列表
        """
        # 清除之前发现的插件
        self._discovered_plugins.clear()
        
        # 默认使用内置插件目录
        if plugin_dirs is None:
            plugin_dirs = [str(self._plugin_dir)]
        
        # 确保插件目录在sys.path中
        for plugin_dir in plugin_dirs:
            if plugin_dir not in sys.path:
                sys.path.insert(0, plugin_dir)
        
        all_plugins: List[str] = []
        
        # 遍历所有插件目录
        for plugin_dir in plugin_dirs:
            logger.info(f"开始在目录中发现插件: {plugin_dir}")
            dir_path = Path(plugin_dir)
            
            if not dir_path.exists() or not dir_path.is_dir():
                logger.warning(f"插件目录不存在或不是目录: {dir_path}")
                continue
            
            # 遍历目录下的所有Python模块
            for finder, name, is_pkg in pkgutil.iter_modules([str(dir_path)]):
                # 跳过非包和基础插件模块
                if not is_pkg or name == "base":
                    continue
                
                # 递归搜索包内的模块
                pkg_path = dir_path / name
                pkg_plugins = await self._discover_plugins_in_package(name, pkg_path)
                all_plugins.extend(pkg_plugins)
        
        logger.info(f"发现了 {len(self._discovered_plugins)} 个可用插件")
        return all_plugins
    
    async def _discover_plugins_in_package(self, pkg_name: str, pkg_path: Path) -> List[str]:
        """
        在包中递归发现插件。
        
        Args:
            pkg_name: 包名
            pkg_path: 包路径
            
        Returns:
            List[str]: 发现的插件ID列表
        """
        discovered: List[str] = []
        
        # 检查当前包是否有 __init__.py
        if not (pkg_path / "__init__.py").exists():
            return discovered
        
        # 遍历包中的所有模块
        for finder, name, is_pkg in pkgutil.iter_modules([str(pkg_path)]):
            module_path = f"{pkg_name}.{name}"
            
            if is_pkg:
                # 递归搜索子包
                sub_pkg_path = pkg_path / name
                sub_discovered = await self._discover_plugins_in_package(module_path, sub_pkg_path)
                discovered.extend(sub_discovered)
            else:
                # 检查模块中的插件类
                try:
                    # 导入模块
                    spec = importlib.util.find_spec(module_path)
                    if spec is None:
                        logger.warning(f"无法找到模块: {module_path}")
                        continue
                    
                    module = importlib.util.module_from_spec(spec)
                    spec.loader.exec_module(module)
                    
                    # 查找模块中的插件类
                    for _, obj in inspect.getmembers(module, inspect.isclass):
                        # 检查是否是PluginBase的子类但不是PluginBase本身
                        if (
                            issubclass(obj, PluginBase) and 
                            obj is not PluginBase and 
                            obj.__module__ == module_path
                        ):
                            # 创建临时实例获取ID
                            try:
                                plugin_id = obj.get_id_from_class()
                                
                                # 记录发现的插件
                                self._discovered_plugins[plugin_id] = (obj, module_path)
                                discovered.append(plugin_id)
                                
                                logger.debug(f"发现插件: {plugin_id} ({module_path}.{obj.__name__})")
                                
                            except Exception as e:
                                logger.warning(f"获取插件ID时出错: {module_path}.{obj.__name__} - {str(e)}")
                    
                except Exception as e:
                    logger.error(f"加载模块 {module_path} 时出错: {str(e)}")
        
        return discovered
    
    async def load_plugin(self, plugin_id: str, initialize: bool = True) -> Optional[PluginBase]:
        """
        加载指定ID的插件。
        
        Args:
            plugin_id: 插件ID
            initialize: 是否初始化插件
            
        Returns:
            Optional[PluginBase]: 加载的插件实例，如果加载失败则返回None
        """
        # 插件已加载，直接返回
        if plugin_id in self._plugins:
            logger.info(f"插件已加载: {plugin_id}")
            return self._plugins[plugin_id]
        
        # 检查插件是否已发现
        if plugin_id not in self._discovered_plugins:
            logger.error(f"未发现插件: {plugin_id}")
            self._publish_plugin_error(plugin_id, f"未发现插件: {plugin_id}")
            return None
        
        # 获取插件类和模块路径
        plugin_class, module_path = self._discovered_plugins[plugin_id]
        
        try:
            logger.info(f"加载插件: {plugin_id}")
            
            # 加载插件依赖
            if hasattr(plugin_class, 'dependencies'):
                dependencies = getattr(plugin_class, 'dependencies', [])
                
                # 记录依赖关系
                self._dependencies[plugin_id] = set(dependencies)
                
                # 加载依赖
                for dep_id in dependencies:
                    # 添加反向依赖关系
                    if dep_id not in self._dependents:
                        self._dependents[dep_id] = set()
                    self._dependents[dep_id].add(plugin_id)
                    
                    # 依赖尚未加载，递归加载
                    if dep_id not in self._plugins:
                        logger.info(f"加载插件 {plugin_id} 的依赖: {dep_id}")
                        dep_plugin = await self.load_plugin(dep_id, initialize)
                        
                        if dep_plugin is None:
                            logger.error(f"无法加载插件 {plugin_id} 的依赖: {dep_id}")
                            self._publish_plugin_error(
                                plugin_id, 
                                f"无法加载依赖: {dep_id}"
                            )
                            return None
            
            # 创建插件实例
            plugin = plugin_class(self._event_bus)
            
            # 添加到已加载插件列表
            self._plugins[plugin_id] = plugin
            self._load_order.append(plugin_id)
            
            # 初始化插件
            if initialize:
                success = await self._initialize_plugin(plugin)
                if not success:
                    # 初始化失败，卸载插件
                    await self.unload_plugin(plugin_id)
                    return None
            
            # 发布插件加载事件
            self._publish_plugin_loaded(plugin)
            
            logger.info(f"插件已成功加载: {plugin_id}")
            return plugin
            
        except Exception as e:
            logger.error(f"加载插件时出错: {plugin_id} - {str(e)}")
            self._publish_plugin_error(plugin_id, f"加载出错: {str(e)}")
            return None
    
    async def _initialize_plugin(self, plugin: PluginBase) -> bool:
        """
        初始化插件。
        
        Args:
            plugin: 插件实例
            
        Returns:
            bool: 是否成功初始化
        """
        try:
            logger.info(f"初始化插件: {plugin.id}")
            await plugin.initialize()
            return True
            
        except Exception as e:
            logger.error(f"初始化插件时出错: {plugin.id} - {str(e)}")
            self._publish_plugin_error(plugin.id, f"初始化出错: {str(e)}")
            return False
    
    async def unload_plugin(self, plugin_id: str) -> bool:
        """
        卸载指定ID的插件。
        
        Args:
            plugin_id: 插件ID
            
        Returns:
            bool: 是否成功卸载
        """
        # 插件未加载，直接返回
        if plugin_id not in self._plugins:
            logger.warning(f"插件未加载，无法卸载: {plugin_id}")
            return False
        
        # 检查是否有其他插件依赖此插件
        if plugin_id in self._dependents and self._dependents[plugin_id]:
            dependent_plugins = self._dependents[plugin_id]
            logger.warning(
                f"插件 {plugin_id} 被以下插件依赖，无法卸载: {', '.join(dependent_plugins)}"
            )
            self._publish_plugin_error(
                plugin_id, 
                f"无法卸载: 被以下插件依赖 {', '.join(dependent_plugins)}"
            )
            return False
        
        try:
            logger.info(f"卸载插件: {plugin_id}")
            
            # 获取插件实例
            plugin = self._plugins[plugin_id]
            
            # 关闭插件
            await plugin.shutdown()
            
            # 从已加载插件列表中移除
            del self._plugins[plugin_id]
            
            # 从加载顺序列表中移除
            if plugin_id in self._load_order:
                self._load_order.remove(plugin_id)
            
            # 从依赖关系中移除
            if plugin_id in self._dependencies:
                # 清理依赖关系
                for dep_id in self._dependencies[plugin_id]:
                    if dep_id in self._dependents:
                        self._dependents[dep_id].discard(plugin_id)
                        
                        # 如果没有依赖了，删除整个条目
                        if not self._dependents[dep_id]:
                            del self._dependents[dep_id]
                
                # 删除依赖条目
                del self._dependencies[plugin_id]
            
            # 发布插件卸载事件
            self._publish_plugin_unloaded(plugin_id)
            
            logger.info(f"插件已成功卸载: {plugin_id}")
            return True
            
        except Exception as e:
            logger.error(f"卸载插件时出错: {plugin_id} - {str(e)}")
            self._publish_plugin_error(plugin_id, f"卸载出错: {str(e)}")
            return False
    
    async def unload_all_plugins(self) -> bool:
        """
        卸载所有插件。
        
        Returns:
            bool: 是否所有插件都成功卸载
        """
        logger.info("卸载所有插件")
        
        # 按照加载的相反顺序卸载插件
        unload_order = self._load_order.copy()
        unload_order.reverse()
        
        success = True
        
        for plugin_id in unload_order:
            plugin_success = await self.unload_plugin(plugin_id)
            success = success and plugin_success
        
        return success
    
    async def reload_plugin(self, plugin_id: str) -> Optional[PluginBase]:
        """
        重新加载插件。
        
        Args:
            plugin_id: 插件ID
            
        Returns:
            Optional[PluginBase]: 重新加载的插件实例，如果重新加载失败则返回None
        """
        logger.info(f"重新加载插件: {plugin_id}")
        
        # 检查插件是否已加载
        if plugin_id not in self._plugins:
            logger.warning(f"插件未加载，无法重新加载: {plugin_id}")
            return None
        
        # 卸载插件
        unload_success = await self.unload_plugin(plugin_id)
        if not unload_success:
            logger.error(f"卸载插件失败，无法重新加载: {plugin_id}")
            return None
        
        # 重新导入模块
        try:
            if plugin_id in self._discovered_plugins:
                _, module_path = self._discovered_plugins[plugin_id]
                
                # 重新加载模块
                logger.debug(f"重新加载模块: {module_path}")
                module = importlib.import_module(module_path)
                importlib.reload(module)
        except Exception as e:
            logger.error(f"重新加载模块时出错: {plugin_id} - {str(e)}")
            self._publish_plugin_error(plugin_id, f"重新加载模块出错: {str(e)}")
            return None
        
        # 从发现的插件中删除插件类，以便从模块重新发现
        if plugin_id in self._discovered_plugins:
            del self._discovered_plugins[plugin_id]
            
        # 重新发现插件
        await self.discover_plugins()
        
        # 加载插件
        return await self.load_plugin(plugin_id)
    
    async def load_all_plugins(self) -> List[PluginBase]:
        """
        加载所有发现的插件。
        
        Returns:
            List[PluginBase]: 成功加载的插件实例列表
        """
        logger.info("加载所有插件")
        
        # 获取所有发现的插件ID
        plugin_ids = list(self._discovered_plugins.keys())
        loaded_plugins: List[PluginBase] = []
        
        # 按顺序加载插件
        for plugin_id in plugin_ids:
            plugin = await self.load_plugin(plugin_id)
            if plugin:
                loaded_plugins.append(plugin)
        
        logger.info(f"成功加载了 {len(loaded_plugins)} 个插件")
        return loaded_plugins
    
    def get_plugin(self, plugin_id: str) -> Optional[PluginBase]:
        """
        获取指定ID的插件实例。
        
        Args:
            plugin_id: 插件ID
            
        Returns:
            Optional[PluginBase]: 插件实例，如果未找到则返回None
        """
        return self._plugins.get(plugin_id)
    
    def get_plugins(self) -> Dict[str, PluginBase]:
        """
        获取所有已加载的插件。
        
        Returns:
            Dict[str, PluginBase]: 已加载的插件字典 {插件ID: 插件实例}
        """
        return self._plugins.copy()
    
    def get_discovered_plugins(self) -> List[str]:
        """
        获取所有已发现但未必加载的插件ID列表。
        
        Returns:
            List[str]: 已发现的插件ID列表
        """
        return list(self._discovered_plugins.keys())
    
    def get_plugin_info(self, plugin_id: str) -> Optional[Dict[str, Any]]:
        """
        获取指定插件的详细信息。
        
        Args:
            plugin_id: 插件ID
            
        Returns:
            Optional[Dict[str, Any]]: 插件信息字典，包含ID、名称、版本等信息
        """
        # 已加载的插件
        if plugin_id in self._plugins:
            plugin = self._plugins[plugin_id]
            
            # 获取插件元数据
            info = plugin.get_metadata()
            
            # 添加加载状态和依赖信息
            info.update({
                "loaded": True,
                "dependencies": list(self._dependencies.get(plugin_id, set())),
                "dependents": list(self._dependents.get(plugin_id, set()))
            })
            
            return info
            
        # 未加载但已发现的插件
        elif plugin_id in self._discovered_plugins:
            plugin_class, module_path = self._discovered_plugins[plugin_id]
            
            # 获取类级别的插件元数据
            info = {
                "id": plugin_id,
                "name": getattr(plugin_class, "name", plugin_id),
                "version": getattr(plugin_class, "version", "0.1.0"),
                "description": getattr(plugin_class, "description", ""),
                "module_path": module_path,
                "loaded": False,
                "dependencies": getattr(plugin_class, "dependencies", []),
                "dependents": list(self._dependents.get(plugin_id, set()))
            }
            
            return info
            
        return None
    
    def get_all_plugins_info(self) -> List[Dict[str, Any]]:
        """
        获取所有已发现插件的详细信息。
        
        Returns:
            List[Dict[str, Any]]: 插件信息字典列表
        """
        all_info: List[Dict[str, Any]] = []
        
        # 获取所有已发现插件的ID
        all_plugin_ids = set(self._discovered_plugins.keys()) | set(self._plugins.keys())
        
        # 收集每个插件的信息
        for plugin_id in all_plugin_ids:
            info = self.get_plugin_info(plugin_id)
            if info:
                all_info.append(info)
        
        return all_info
    
    def has_plugin(self, plugin_id: str) -> bool:
        """
        检查指定ID的插件是否已加载。
        
        Args:
            plugin_id: 插件ID
            
        Returns:
            bool: 插件是否已加载
        """
        return plugin_id in self._plugins
    
    def is_plugin_discovered(self, plugin_id: str) -> bool:
        """
        检查指定ID的插件是否已发现。
        
        Args:
            plugin_id: 插件ID
            
        Returns:
            bool: 插件是否已发现
        """
        return plugin_id in self._discovered_plugins
    
    def _publish_plugin_loaded(self, plugin: PluginBase) -> None:
        """
        发布插件加载事件。
        
        Args:
            plugin: 已加载的插件实例
        """
        event_data = create_event_data(
            PLUGIN_LOADED,
            plugin_id=plugin.id,
            plugin_name=plugin.name,
            plugin_version=plugin.version
        )
        
        try:
            # 异步执行，需要在事件循环中运行
            asyncio.create_task(self._event_bus.publish(PLUGIN_LOADED, event_data))
        except RuntimeError:
            # 不在事件循环中，记录日志但不发布事件
            logger.debug(f"插件加载事件无法发布: {plugin.id}")
    
    def _publish_plugin_unloaded(self, plugin_id: str) -> None:
        """
        发布插件卸载事件。
        
        Args:
            plugin_id: 已卸载的插件ID
        """
        event_data = create_event_data(
            PLUGIN_UNLOADED,
            plugin_id=plugin_id
        )
        
        try:
            # 异步执行，需要在事件循环中运行
            asyncio.create_task(self._event_bus.publish(PLUGIN_UNLOADED, event_data))
        except RuntimeError:
            # 不在事件循环中，记录日志但不发布事件
            logger.debug(f"插件卸载事件无法发布: {plugin_id}")
    
    def _publish_plugin_error(self, plugin_id: str, error_message: str) -> None:
        """
        发布插件错误事件。
        
        Args:
            plugin_id: 出错的插件ID
            error_message: 错误消息
        """
        event_data = create_event_data(
            PLUGIN_ERROR,
            plugin_id=plugin_id,
            error=error_message
        )
        
        try:
            # 异步执行，需要在事件循环中运行
            asyncio.create_task(self._event_bus.publish(PLUGIN_ERROR, event_data))
        except RuntimeError:
            # 不在事件循环中，记录日志但不发布事件
            logger.debug(f"插件错误事件无法发布: {plugin_id} - {error_message}") 