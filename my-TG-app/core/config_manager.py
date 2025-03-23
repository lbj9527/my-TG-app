"""
配置管理器模块。

本模块提供配置的读取、保存和更新功能，支持多种配置格式（INI、JSON、YAML）。
配置管理器会自动监视配置文件的变更并发布事件通知。
"""

import os
import json
import time
import configparser
import threading
import shutil
from pathlib import Path
from typing import Dict, Any, Optional, Union, List, Callable, Set
from dataclasses import dataclass

from core.event_bus import EventBus
from events.event_types import CONFIG_LOADED, CONFIG_CHANGED, CONFIG_ERROR, create_event_data
from utils.logger import get_logger

# 获取日志记录器
logger = get_logger("config_manager")

# 默认配置文件路径
DEFAULT_CONFIG_DIR = Path("config")
DEFAULT_CONFIG_FILE = DEFAULT_CONFIG_DIR / "default_config.ini"
USER_CONFIG_FILE = DEFAULT_CONFIG_DIR / "config.ini"

# 支持的配置文件格式
CONFIG_FORMATS = {
    ".ini": "ini",
    ".json": "json",
    ".yaml": "yaml",
    ".yml": "yaml"
}


@dataclass
class ConfigValue:
    """配置值类，用于跟踪配置项的元数据"""
    value: Any
    default: Any
    description: str = ""
    last_modified: float = 0.0

    def is_default(self) -> bool:
        """检查当前值是否为默认值"""
        return self.value == self.default


class ConfigManager:
    """
    配置管理器，负责读取、保存和更新应用配置。
    
    支持多种配置格式，提供配置监视和变更通知。
    """
    
    def __init__(self, event_bus: EventBus):
        """
        初始化配置管理器。
        
        Args:
            event_bus: 事件总线实例
        """
        self._event_bus = event_bus
        self._config_lock = threading.RLock()
        
        # 配置数据 {section: {key: ConfigValue}}
        self._config_data: Dict[str, Dict[str, ConfigValue]] = {}
        
        # 已注册的配置文件
        self._config_files: Dict[str, Path] = {}
        
        # 配置文件监视线程
        self._watch_thread: Optional[threading.Thread] = None
        self._watch_stop_event = threading.Event()
        
        # 配置观察者 {section: set(回调函数)}
        self._observers: Dict[str, Set[Callable[[str, Dict[str, Any]], None]]] = {}
        
        logger.info("配置管理器已初始化")
    
    def load_default_config(self) -> bool:
        """
        加载默认配置文件。
        
        Returns:
            bool: 是否成功加载
        """
        # 检查默认配置目录是否存在
        if not DEFAULT_CONFIG_DIR.exists():
            logger.info(f"创建默认配置目录: {DEFAULT_CONFIG_DIR}")
            DEFAULT_CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        
        # 检查默认配置文件是否存在
        if not DEFAULT_CONFIG_FILE.exists():
            logger.warning(f"默认配置文件不存在: {DEFAULT_CONFIG_FILE}")
            self._create_default_config()
        
        # 加载默认配置
        return self.load_config(DEFAULT_CONFIG_FILE, "default")
    
    def load_user_config(self) -> bool:
        """
        加载用户配置文件。
        
        Returns:
            bool: 是否成功加载
        """
        # 如果用户配置文件不存在，复制默认配置
        if not USER_CONFIG_FILE.exists() and DEFAULT_CONFIG_FILE.exists():
            logger.info(f"用户配置文件不存在，从默认配置复制: {USER_CONFIG_FILE}")
            shutil.copy(DEFAULT_CONFIG_FILE, USER_CONFIG_FILE)
        
        # 加载用户配置
        return self.load_config(USER_CONFIG_FILE, "user")
    
    def load_config(self, config_file: Union[str, Path], config_id: str = "default") -> bool:
        """
        加载指定的配置文件。
        
        Args:
            config_file: 配置文件路径
            config_id: 配置文件标识符
            
        Returns:
            bool: 是否成功加载
        """
        config_path = Path(config_file)
        if not config_path.exists():
            logger.error(f"配置文件不存在: {config_path}")
            self._publish_config_error(f"配置文件不存在: {config_path}")
            return False
        
        # 确定配置文件格式
        file_format = self._get_config_format(config_path)
        if not file_format:
            logger.error(f"不支持的配置文件格式: {config_path}")
            self._publish_config_error(f"不支持的配置文件格式: {config_path}")
            return False
        
        try:
            logger.info(f"加载配置文件: {config_path} (格式: {file_format})")
            
            with self._config_lock:
                # 注册配置文件
                self._config_files[config_id] = config_path
                
                # 根据格式加载配置
                if file_format == "ini":
                    self._load_ini_config(config_path, config_id == "default")
                elif file_format == "json":
                    self._load_json_config(config_path, config_id == "default")
                elif file_format == "yaml":
                    self._load_yaml_config(config_path, config_id == "default")
            
            # 发布配置加载事件
            self._publish_config_loaded(config_id)
            
            # 启动配置监视
            self._start_config_watch()
            
            return True
            
        except Exception as e:
            logger.error(f"加载配置文件时出错: {str(e)}")
            self._publish_config_error(f"加载配置文件时出错: {str(e)}")
            return False
    
    def save_config(self, config_id: str = "user") -> bool:
        """
        保存配置到文件。
        
        Args:
            config_id: 配置文件标识符
            
        Returns:
            bool: 是否成功保存
        """
        if config_id not in self._config_files:
            logger.error(f"未注册的配置文件ID: {config_id}")
            return False
        
        config_path = self._config_files[config_id]
        file_format = self._get_config_format(config_path)
        
        if not file_format:
            logger.error(f"不支持的配置文件格式: {config_path}")
            return False
        
        try:
            logger.info(f"保存配置到文件: {config_path}")
            
            with self._config_lock:
                # 根据格式保存配置
                if file_format == "ini":
                    self._save_ini_config(config_path)
                elif file_format == "json":
                    self._save_json_config(config_path)
                elif file_format == "yaml":
                    self._save_yaml_config(config_path)
            
            return True
            
        except Exception as e:
            logger.error(f"保存配置文件时出错: {str(e)}")
            self._publish_config_error(f"保存配置文件时出错: {str(e)}")
            return False
    
    def get(self, section: str, key: str, default: Any = None) -> Any:
        """
        获取配置值。
        
        Args:
            section: 配置节
            key: 配置键
            default: 默认值
            
        Returns:
            Any: 配置值，如果不存在则返回默认值
        """
        with self._config_lock:
            if section not in self._config_data:
                return default
            
            if key not in self._config_data[section]:
                return default
            
            return self._config_data[section][key].value
    
    def get_section(self, section: str) -> Dict[str, Any]:
        """
        获取配置节的所有键值对。
        
        Args:
            section: 配置节
            
        Returns:
            Dict[str, Any]: 配置节的键值对
        """
        with self._config_lock:
            if section not in self._config_data:
                return {}
            
            return {
                key: value.value
                for key, value in self._config_data[section].items()
            }
    
    def get_all(self) -> Dict[str, Dict[str, Any]]:
        """
        获取所有配置。
        
        Returns:
            Dict[str, Dict[str, Any]]: 所有配置节和键值对
        """
        with self._config_lock:
            return {
                section: {key: value.value for key, value in items.items()}
                for section, items in self._config_data.items()
            }
    
    def set(self, section: str, key: str, value: Any, description: str = "") -> bool:
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
        with self._config_lock:
            # 确保配置节存在
            if section not in self._config_data:
                self._config_data[section] = {}
            
            # 检查是否有变更
            old_value = None
            if key in self._config_data[section]:
                old_value = self._config_data[section][key].value
                
                # 值未变更，直接返回
                if old_value == value:
                    return True
                
                # 更新现有配置值
                self._config_data[section][key].value = value
                self._config_data[section][key].last_modified = time.time()
                
                # 如果提供了描述，则更新
                if description:
                    self._config_data[section][key].description = description
            else:
                # 创建新配置值
                self._config_data[section][key] = ConfigValue(
                    value=value,
                    default=value,
                    description=description,
                    last_modified=time.time()
                )
        
        # 发布配置变更事件
        if old_value != value:
            self._notify_observers(section, {key: value})
            self._publish_config_changed(section, key, old_value, value)
        
        return True
    
    def update_section(self, section: str, values: Dict[str, Any]) -> bool:
        """
        更新配置节的多个键值对。
        
        Args:
            section: 配置节
            values: 键值对字典
            
        Returns:
            bool: 是否更新成功
        """
        if not values:
            return True
        
        changed_keys = {}
        
        with self._config_lock:
            # 确保配置节存在
            if section not in self._config_data:
                self._config_data[section] = {}
            
            # 更新多个键值对
            for key, value in values.items():
                old_value = None
                if key in self._config_data[section]:
                    old_value = self._config_data[section][key].value
                    
                    # 值未变更，跳过
                    if old_value == value:
                        continue
                    
                    # 更新现有配置值
                    self._config_data[section][key].value = value
                    self._config_data[section][key].last_modified = time.time()
                else:
                    # 创建新配置值
                    self._config_data[section][key] = ConfigValue(
                        value=value,
                        default=value,
                        description="",
                        last_modified=time.time()
                    )
                
                # 记录变更的键
                if old_value != value:
                    changed_keys[key] = value
        
        # 如果有变更，通知观察者并发布事件
        if changed_keys:
            self._notify_observers(section, changed_keys)
            self._publish_config_section_changed(section, changed_keys)
        
        return True
    
    def reset(self, section: str, key: str) -> bool:
        """
        重置配置项为默认值。
        
        Args:
            section: 配置节
            key: 配置键
            
        Returns:
            bool: 是否重置成功
        """
        with self._config_lock:
            if section not in self._config_data:
                return False
            
            if key not in self._config_data[section]:
                return False
            
            config_value = self._config_data[section][key]
            old_value = config_value.value
            
            # 已经是默认值，无需重置
            if config_value.is_default():
                return True
            
            # 重置为默认值
            config_value.value = config_value.default
            config_value.last_modified = time.time()
        
        # 发布配置变更事件
        self._notify_observers(section, {key: config_value.default})
        self._publish_config_changed(section, key, old_value, config_value.default)
        
        return True
    
    def reset_section(self, section: str) -> bool:
        """
        重置配置节的所有项为默认值。
        
        Args:
            section: 配置节
            
        Returns:
            bool: 是否重置成功
        """
        changed_keys = {}
        
        with self._config_lock:
            if section not in self._config_data:
                return False
            
            # 重置所有配置项
            for key, config_value in self._config_data[section].items():
                if not config_value.is_default():
                    old_value = config_value.value
                    config_value.value = config_value.default
                    config_value.last_modified = time.time()
                    changed_keys[key] = config_value.default
        
        # 如果有变更，通知观察者并发布事件
        if changed_keys:
            self._notify_observers(section, changed_keys)
            self._publish_config_section_changed(section, changed_keys)
        
        return True
    
    def add_observer(self, section: str, callback: Callable[[str, Dict[str, Any]], None]) -> None:
        """
        添加配置观察者。
        
        Args:
            section: 要观察的配置节
            callback: 回调函数，接收section和变更的键值对
        """
        with self._config_lock:
            if section not in self._observers:
                self._observers[section] = set()
            
            self._observers[section].add(callback)
    
    def remove_observer(self, section: str, callback: Callable[[str, Dict[str, Any]], None]) -> bool:
        """
        移除配置观察者。
        
        Args:
            section: 观察的配置节
            callback: 回调函数
            
        Returns:
            bool: 是否成功移除
        """
        with self._config_lock:
            if section not in self._observers:
                return False
            
            if callback not in self._observers[section]:
                return False
            
            self._observers[section].remove(callback)
            
            # 如果没有观察者了，删除该节的观察者集
            if not self._observers[section]:
                del self._observers[section]
            
            return True
    
    def _notify_observers(self, section: str, changed: Dict[str, Any]) -> None:
        """
        通知配置节的观察者。
        
        Args:
            section: 配置节
            changed: 变更的键值对
        """
        observers = set()
        
        with self._config_lock:
            if section in self._observers:
                observers = self._observers[section].copy()
        
        # 调用所有观察者
        for callback in observers:
            try:
                callback(section, changed)
            except Exception as e:
                logger.error(f"调用配置观察者回调时出错: {str(e)}")
    
    def _get_config_format(self, config_path: Path) -> Optional[str]:
        """
        获取配置文件的格式。
        
        Args:
            config_path: 配置文件路径
            
        Returns:
            Optional[str]: 配置格式，如果不支持则返回None
        """
        suffix = config_path.suffix.lower()
        return CONFIG_FORMATS.get(suffix)
    
    def _load_ini_config(self, config_path: Path, is_default: bool) -> None:
        """
        加载INI格式的配置文件。
        
        Args:
            config_path: 配置文件路径
            is_default: 是否为默认配置
        """
        parser = configparser.ConfigParser()
        parser.read(config_path, encoding="utf-8")
        
        # 处理所有节
        for section in parser.sections():
            # 确保配置节存在
            if section not in self._config_data:
                self._config_data[section] = {}
            
            # 读取节中的所有配置项
            for key, value in parser[section].items():
                # 尝试转换值类型
                typed_value = self._parse_string_value(value)
                
                # 如果是默认配置或配置项不存在，则创建新配置项
                if is_default or key not in self._config_data[section]:
                    if key in self._config_data[section]:
                        # 更新默认值但保留当前值
                        self._config_data[section][key].default = typed_value
                    else:
                        # 创建新配置项
                        self._config_data[section][key] = ConfigValue(
                            value=typed_value,
                            default=typed_value,
                            description="",
                            last_modified=time.time()
                        )
                
                # 非默认配置，更新现有配置项的值
                elif not is_default:
                    self._config_data[section][key].value = typed_value
                    self._config_data[section][key].last_modified = time.time()
    
    def _load_json_config(self, config_path: Path, is_default: bool) -> None:
        """
        加载JSON格式的配置文件。
        
        Args:
            config_path: 配置文件路径
            is_default: 是否为默认配置
        """
        with open(config_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        
        # 处理所有节
        for section, section_data in data.items():
            # 确保配置节存在
            if section not in self._config_data:
                self._config_data[section] = {}
            
            # 读取节中的所有配置项
            if isinstance(section_data, dict):
                for key, value in section_data.items():
                    # 如果是默认配置或配置项不存在，则创建新配置项
                    if is_default or key not in self._config_data[section]:
                        if key in self._config_data[section]:
                            # 更新默认值但保留当前值
                            self._config_data[section][key].default = value
                        else:
                            # 创建新配置项
                            self._config_data[section][key] = ConfigValue(
                                value=value,
                                default=value,
                                description="",
                                last_modified=time.time()
                            )
                    
                    # 非默认配置，更新现有配置项的值
                    elif not is_default:
                        self._config_data[section][key].value = value
                        self._config_data[section][key].last_modified = time.time()
    
    def _load_yaml_config(self, config_path: Path, is_default: bool) -> None:
        """
        加载YAML格式的配置文件。
        
        Args:
            config_path: 配置文件路径
            is_default: 是否为默认配置
        """
        try:
            import yaml
            with open(config_path, "r", encoding="utf-8") as f:
                data = yaml.safe_load(f)
            
            # 处理所有节
            for section, section_data in data.items():
                # 确保配置节存在
                if section not in self._config_data:
                    self._config_data[section] = {}
                
                # 读取节中的所有配置项
                if isinstance(section_data, dict):
                    for key, value in section_data.items():
                        # 如果是默认配置或配置项不存在，则创建新配置项
                        if is_default or key not in self._config_data[section]:
                            if key in self._config_data[section]:
                                # 更新默认值但保留当前值
                                self._config_data[section][key].default = value
                            else:
                                # 创建新配置项
                                self._config_data[section][key] = ConfigValue(
                                    value=value,
                                    default=value,
                                    description="",
                                    last_modified=time.time()
                                )
                        
                        # 非默认配置，更新现有配置项的值
                        elif not is_default:
                            self._config_data[section][key].value = value
                            self._config_data[section][key].last_modified = time.time()
                            
        except ImportError:
            logger.error("加载YAML配置失败: 缺少PyYAML库，请安装 pip install pyyaml")
            raise
    
    def _save_ini_config(self, config_path: Path) -> None:
        """
        保存配置到INI文件。
        
        Args:
            config_path: 配置文件路径
        """
        parser = configparser.ConfigParser()
        
        # 写入所有配置节
        for section, items in self._config_data.items():
            parser[section] = {}
            
            # 写入节中的所有配置项
            for key, config_value in items.items():
                parser[section][key] = str(config_value.value)
        
        # 确保目录存在
        config_path.parent.mkdir(parents=True, exist_ok=True)
        
        # 写入文件
        with open(config_path, "w", encoding="utf-8") as f:
            parser.write(f)
    
    def _save_json_config(self, config_path: Path) -> None:
        """
        保存配置到JSON文件。
        
        Args:
            config_path: 配置文件路径
        """
        data = {}
        
        # 构建配置数据
        for section, items in self._config_data.items():
            data[section] = {}
            
            # 添加节中的所有配置项
            for key, config_value in items.items():
                data[section][key] = config_value.value
        
        # 确保目录存在
        config_path.parent.mkdir(parents=True, exist_ok=True)
        
        # 写入文件，使用漂亮打印格式
        with open(config_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=4, ensure_ascii=False)
    
    def _save_yaml_config(self, config_path: Path) -> None:
        """
        保存配置到YAML文件。
        
        Args:
            config_path: 配置文件路径
        """
        try:
            import yaml
            
            data = {}
            
            # 构建配置数据
            for section, items in self._config_data.items():
                data[section] = {}
                
                # 添加节中的所有配置项
                for key, config_value in items.items():
                    data[section][key] = config_value.value
            
            # 确保目录存在
            config_path.parent.mkdir(parents=True, exist_ok=True)
            
            # 写入文件
            with open(config_path, "w", encoding="utf-8") as f:
                yaml.dump(data, f, default_flow_style=False, sort_keys=False, allow_unicode=True)
                
        except ImportError:
            logger.error("保存YAML配置失败: 缺少PyYAML库，请安装 pip install pyyaml")
            raise
    
    def _create_default_config(self) -> None:
        """创建默认配置文件"""
        logger.info(f"创建默认配置文件: {DEFAULT_CONFIG_FILE}")
        
        # 确保配置目录存在
        DEFAULT_CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        
        # 创建默认配置
        parser = configparser.ConfigParser()
        
        # 应用配置节
        parser["app"] = {
            "name": "my-TG-app",
            "version": "0.1.0",
            "debug": "false",
            "log_level": "INFO",
            "ui_enabled": "false"
        }
        
        # 客户端配置节
        parser["client"] = {
            "api_id": "",
            "api_hash": "",
            "phone": "",
            "session_name": "my_telegram_session",
            "proxy_enabled": "false",
            "proxy_type": "socks5",
            "proxy_host": "127.0.0.1",
            "proxy_port": "1080",
            "proxy_username": "",
            "proxy_password": ""
        }
        
        # 转发配置节
        parser["forward"] = {
            "use_threads": "true",
            "thread_num": "5",
            "delay_between_messages": "1.5",
            "caption_format": "{original_caption}",
            "preserve_media_group": "true",
            "skip_duplicate": "true"
        }
        
        # 下载配置节
        parser["download"] = {
            "download_dir": "downloads",
            "organize_by_chat": "true",
            "skip_existing": "true",
            "max_concurrent_downloads": "3",
            "download_history_size": "1000"
        }
        
        # 写入配置文件
        with open(DEFAULT_CONFIG_FILE, "w", encoding="utf-8") as f:
            parser.write(f)
    
    def _parse_string_value(self, value: str) -> Any:
        """
        尝试将字符串值转换为适当的类型。
        
        Args:
            value: 字符串值
            
        Returns:
            Any: 转换后的值
        """
        # 尝试转换为布尔值
        if value.lower() in ("true", "yes", "1"):
            return True
        elif value.lower() in ("false", "no", "0"):
            return False
        
        # 尝试转换为整数
        try:
            return int(value)
        except ValueError:
            pass
        
        # 尝试转换为浮点数
        try:
            return float(value)
        except ValueError:
            pass
        
        # 保持为字符串
        return value
    
    def _start_config_watch(self) -> None:
        """启动配置文件监视线程"""
        if self._watch_thread and self._watch_thread.is_alive():
            return
        
        # 重置停止事件
        self._watch_stop_event.clear()
        
        # 创建监视线程
        self._watch_thread = threading.Thread(
            target=self._watch_config_files,
            daemon=True,
            name="ConfigWatchThread"
        )
        
        # 启动线程
        self._watch_thread.start()
    
    def _watch_config_files(self) -> None:
        """监视配置文件变更"""
        logger.debug("启动配置文件监视线程")
        
        # 记录文件的最后修改时间 {config_id: (文件路径, 最后修改时间)}
        last_modified: Dict[str, Tuple[Path, float]] = {}
        
        with self._config_lock:
            for config_id, path in self._config_files.items():
                if path.exists():
                    last_modified[config_id] = (path, path.stat().st_mtime)
        
        # 监视循环
        while not self._watch_stop_event.is_set():
            reload_needed = []
            
            # 检查所有配置文件
            with self._config_lock:
                for config_id, path in self._config_files.items():
                    if path.exists() and config_id in last_modified:
                        current_mtime = path.stat().st_mtime
                        if current_mtime > last_modified[config_id][1]:
                            logger.info(f"检测到配置文件变更: {path}")
                            reload_needed.append(config_id)
                            last_modified[config_id] = (path, current_mtime)
            
            # 重新加载变更的配置
            for config_id in reload_needed:
                path = self._config_files[config_id]
                try:
                    self.load_config(path, config_id)
                except Exception as e:
                    logger.error(f"重新加载配置文件时出错: {str(e)}")
            
            # 等待一段时间
            self._watch_stop_event.wait(5.0)
    
    def stop_config_watch(self) -> None:
        """停止配置文件监视线程"""
        if self._watch_thread and self._watch_thread.is_alive():
            logger.debug("停止配置文件监视线程")
            self._watch_stop_event.set()
            self._watch_thread.join(timeout=1.0)
    
    def _publish_config_loaded(self, config_id: str) -> None:
        """
        发布配置加载事件。
        
        Args:
            config_id: 配置文件标识符
        """
        event_data = create_event_data(
            CONFIG_LOADED,
            config_id=config_id,
            config_file=str(self._config_files.get(config_id, ""))
        )
        
        try:
            # 异步执行，需要在事件循环中运行
            asyncio.create_task(self._event_bus.publish(CONFIG_LOADED, event_data))
        except RuntimeError:
            # 不在事件循环中，记录日志但不发布事件
            logger.debug(f"配置加载事件无法发布: {event_data}")
    
    def _publish_config_changed(
        self, 
        section: str, 
        key: str, 
        old_value: Any, 
        new_value: Any
    ) -> None:
        """
        发布配置变更事件。
        
        Args:
            section: 配置节
            key: 配置键
            old_value: 旧值
            new_value: 新值
        """
        event_data = create_event_data(
            CONFIG_CHANGED,
            section=section,
            key=key,
            old_value=old_value,
            new_value=new_value,
            is_section_update=False
        )
        
        try:
            # 异步执行，需要在事件循环中运行
            asyncio.create_task(self._event_bus.publish(CONFIG_CHANGED, event_data))
        except RuntimeError:
            # 不在事件循环中，记录日志但不发布事件
            logger.debug(f"配置变更事件无法发布: {event_data}")
    
    def _publish_config_section_changed(
        self, 
        section: str, 
        changed: Dict[str, Any]
    ) -> None:
        """
        发布配置节变更事件。
        
        Args:
            section: 配置节
            changed: 变更的键值对
        """
        event_data = create_event_data(
            CONFIG_CHANGED,
            section=section,
            changes=changed,
            is_section_update=True
        )
        
        try:
            # 异步执行，需要在事件循环中运行
            asyncio.create_task(self._event_bus.publish(CONFIG_CHANGED, event_data))
        except RuntimeError:
            # 不在事件循环中，记录日志但不发布事件
            logger.debug(f"配置节变更事件无法发布: {event_data}")
    
    def _publish_config_error(self, error_message: str) -> None:
        """
        发布配置错误事件。
        
        Args:
            error_message: 错误消息
        """
        event_data = create_event_data(
            CONFIG_ERROR,
            error=error_message
        )
        
        try:
            # 异步执行，需要在事件循环中运行
            asyncio.create_task(self._event_bus.publish(CONFIG_ERROR, event_data))
        except RuntimeError:
            # 不在事件循环中，记录日志但不发布事件
            logger.debug(f"配置错误事件无法发布: {event_data}")
    
    def __del__(self) -> None:
        """析构函数，停止监视线程"""
        self.stop_config_watch() 