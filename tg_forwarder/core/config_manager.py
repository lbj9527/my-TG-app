"""
配置管理器实现类
负责加载、验证和管理应用程序配置
"""

import os
import json
import configparser
from typing import Any, Dict, List, Optional, Union, TypeVar
from pathlib import Path

from tg_forwarder.interfaces.config_interface import ConfigInterface

T = TypeVar('T')


class ConfigError(Exception):
    """配置错误异常"""
    pass


class ConfigManager(ConfigInterface):
    """
    配置管理器，实现ConfigInterface接口
    负责加载、验证和管理应用程序配置
    """
    
    def __init__(self, config_path: str = "config.ini"):
        """
        初始化配置管理器
        
        Args:
            config_path: 配置文件路径，支持.ini和.json格式
        """
        # 将相对路径转换为绝对路径
        if config_path and not os.path.isabs(config_path):
            config_path = os.path.abspath(config_path)
            print(f"配置文件绝对路径: {config_path}")
        
        self.config_path = config_path
        self.config = {}
        self.parser = configparser.ConfigParser()
        self._loaded = False
        
        # 初始化时就尝试加载配置
        self.load_config()
    
    def load_config(self) -> bool:
        """
        加载配置文件
        
        Returns:
            bool: 成功返回True，失败返回False
        """
        print(f"正在加载配置文件: {self.config_path}")
        
        # 将相对路径转换为绝对路径以确保文件读取
        if not os.path.isabs(self.config_path):
            self.config_path = os.path.abspath(self.config_path)
            print(f"配置文件绝对路径: {self.config_path}")
        
        # 检查文件是否存在
        if not os.path.exists(self.config_path):
            print(f"配置文件不存在: {self.config_path}")
            return False
        
        print(f"配置文件已找到")
        
        # 根据文件扩展名选择加载方式
        if self.config_path.endswith('.json'):
            load_success = self._load_json_config()
            if not load_success:
                print(f"加载JSON配置文件失败: {self.config_path}")
                return False
        elif self.config_path.endswith('.ini'):
            try:
                # 加载INI配置
                self.parser.read(self.config_path, encoding='utf-8')
                # 转换为字典
                for section in self.parser.sections():
                    self.config[section.lower()] = {}
                    for key, value in self.parser.items(section):
                        self.config[section.lower()][key.lower()] = self._parse_ini_value(value)
                self._loaded = True
                print(f"配置加载成功: {self.config_path}")
            except Exception as e:
                print(f"加载INI配置文件失败: {e}")
                return False
        else:
            print(f"不支持的配置文件格式: {self.config_path}")
            return False
        
        # 验证配置
        errors = self.validate()
        if errors:
            error_msg = "\n  - ".join([f"{k}: {', '.join(v)}" for k, v in errors.items()])
            print(f"加载配置失败: 配置验证失败:\n  - {error_msg}")
            return False
        
        return True
    
    def save_config(self) -> bool:
        """
        保存配置到文件
        
        Returns:
            bool: 保存是否成功
        """
        try:
            if not self._loaded:
                raise ConfigError("保存前必须先加载配置")
            
            # 根据文件扩展名选择不同的保存方式
            if self.config_path.endswith('.ini'):
                self._save_ini_config()
            elif self.config_path.endswith('.json'):
                self._save_json_config()
            else:
                raise ConfigError(f"不支持的配置文件格式: {self.config_path}")
            
            return True
        except Exception as e:
            error_msg = f"保存配置失败: {str(e)}"
            print(error_msg)  # 在日志模块初始化前先打印到控制台
            return False
    
    def get(self, key: str, default: Any = None) -> Any:
        """
        获取配置值
        
        Args:
            key: 配置键名，可以使用点号分隔，如 'api.api_id'
            default: 默认值，如果配置项不存在则返回此值
            
        Returns:
            Any: 配置值或默认值
        """
        if not self._loaded:
            print(f"配置未加载，获取 {key} 返回默认值")
            return default
            
        try:
            # 处理嵌套键，如 'api.api_id'
            if '.' in key:
                parts = key.split('.')
                value = self.config
                for part in parts:
                    if isinstance(value, dict) and part in value:
                        value = value[part]
                    else:
                        print(f"键 {key} 在配置中未找到，返回默认值")
                        return default
                return value
            else:
                if key in self.config:
                    return self.config[key]
                else:
                    print(f"键 {key} 在配置中未找到，返回默认值")
                    return default
        except Exception as e:
            print(f"获取配置 {key} 时出错: {e}，返回默认值")
            return default
    
    def get_value(self, key: str, default: Optional[T] = None) -> T:
        """
        获取配置项（与get方法相同，用于向后兼容）
        
        Args:
            key: 配置键，支持点号分隔的路径，如 "api.api_id"
            default: 默认值
            
        Returns:
            配置值，若不存在则返回默认值
        """
        return self.get(key, default)
    
    def set(self, key: str, value: Any) -> None:
        """
        设置配置项
        
        Args:
            key: 配置键，支持点号分隔的路径，如 "api.api_id"
            value: 配置值
        """
        if not self._loaded:
            self.load_config()
        
        # 处理嵌套配置项
        if '.' in key:
            parts = key.split('.')
            current = self.config
            for i, part in enumerate(parts[:-1]):
                if part not in current:
                    current[part] = {}
                current = current[part]
            current[parts[-1]] = value
        else:
            self.config[key] = value
    
    def get_telegram_api_id(self) -> int:
        """
        获取Telegram API ID
        
        Returns:
            int: API ID
        """
        api_id = self.get('telegram.api_id')
        if api_id is None:
            raise ConfigError("配置中缺少 api_id")
        return int(api_id)
    
    def get_telegram_api_hash(self) -> str:
        """
        获取Telegram API Hash
        
        Returns:
            str: API Hash
        """
        api_hash = self.get('telegram.api_hash')
        if api_hash is None:
            raise ConfigError("配置中缺少 api_hash")
        return str(api_hash)
    
    def get_download_path(self) -> str:
        """
        获取下载路径
        
        Returns:
            str: 下载路径，默认为'downloads'
        """
        return self.get('download.directory', 'downloads')
    
    def get_max_concurrent_uploads(self) -> int:
        """
        获取最大并发上传数量
        
        Returns:
            int: 最大并发上传数量，默认为5
        """
        return int(self.get('upload.parallel_uploads', 5))
    
    def get_temp_dir(self) -> str:
        """
        获取临时文件目录
        
        Returns:
            str: 临时文件目录路径，默认为'temp'
        """
        return self.get('download.temp_directory', 'temp')
    
    def get_session_name(self) -> str:
        """
        获取会话名称
        
        Returns:
            str: 会话名称
        """
        return self.get('telegram.session_name', 'tg_forwarder')
    
    def get_source_channels(self) -> List[Union[str, int]]:
        """
        获取源频道列表
        
        Returns:
            List[Union[str, int]]: 源频道列表
        """
        source_channels = self.get('channels.source_channels', [])
        if isinstance(source_channels, str):
            # 处理逗号分隔的字符串
            return [channel.strip() for channel in source_channels.split(',')]
        return source_channels
    
    def get_target_channels(self) -> List[Union[str, int]]:
        """
        获取目标频道列表
        
        Returns:
            List[Union[str, int]]: 目标频道列表
        """
        target_channels = self.get('channels.target_channels', [])
        if isinstance(target_channels, str):
            # 处理逗号分隔的字符串
            return [channel.strip() for channel in target_channels.split(',')]
        return target_channels
    
    def validate(self) -> Dict[str, List[str]]:
        """
        验证配置有效性
        
        Returns:
            Dict[str, List[str]]: 验证错误列表，键为配置项，值为错误信息列表
        """
        errors = {}
        
        # 验证API部分
        telegram_section = self.config.get('telegram', {})
        if not telegram_section or not telegram_section.get('api_id'):
            errors.setdefault('telegram.api_id', []).append("API ID不能为空")
        
        if not telegram_section or not telegram_section.get('api_hash'):
            errors.setdefault('telegram.api_hash', []).append("API Hash不能为空")
        
        # 验证频道部分
        channels_section = self.config.get('channels', {})
        source_channels = channels_section.get('source_channels', [])
        if not source_channels:
            errors.setdefault('channels.source_channels', []).append("源频道列表不能为空")
        
        target_channels = channels_section.get('target_channels', [])
        if not target_channels:
            errors.setdefault('channels.target_channels', []).append("目标频道列表不能为空")
        
        return errors
    
    def _load_ini_config(self) -> None:
        """从INI文件加载配置"""
        self.parser.read(self.config_path, encoding='utf-8')
        
        # 将ConfigParser对象转换为字典
        self.config = {}
        for section in self.parser.sections():
            self.config[section.lower()] = {}
            for key, value in self.parser[section].items():
                self.config[section.lower()][key.lower()] = self._parse_ini_value(value)
    
    def _load_json_config(self) -> bool:
        """
        从JSON文件加载配置
        
        Returns:
            bool: 加载成功返回True，否则返回False
        """
        try:
            with open(self.config_path, 'r', encoding='utf-8') as f:
                self.config = json.load(f)
                # 成功加载后设置_loaded为True
                self._loaded = True
                print(f"配置加载成功: {self.config_path}")
                return True
        except json.JSONDecodeError as e:
            print(f"配置文件JSON解析错误: {e}")
            return False
        except Exception as e:
            print(f"加载配置文件时出错: {e}")
            return False
    
    def _save_ini_config(self) -> None:
        """保存配置到INI文件"""
        # 将字典转换为ConfigParser对象
        config_parser = configparser.ConfigParser()
        
        for section, items in self.config.items():
            config_parser[section.upper()] = {}
            for key, value in items.items():
                if isinstance(value, (list, dict)):
                    value = json.dumps(value)
                config_parser[section.upper()][key] = str(value)
        
        # 写入文件
        with open(self.config_path, 'w', encoding='utf-8') as f:
            config_parser.write(f)
    
    def _save_json_config(self) -> None:
        """保存配置到JSON文件"""
        with open(self.config_path, 'w', encoding='utf-8') as f:
            json.dump(self.config, f, indent=4, ensure_ascii=False)
    
    def _validate_config(self) -> None:
        """验证配置必要字段"""
        errors = self.validate()
        if errors:
            error_msg = "配置验证失败:\n"
            for key, msgs in errors.items():
                for msg in msgs:
                    error_msg += f"  - {key}: {msg}\n"
            raise ConfigError(error_msg)
    
    def _parse_ini_value(self, value: str) -> Any:
        """解析INI文件中的值，自动转换类型"""
        # 尝试转换为数字
        if value.isdigit():
            return int(value)
        
        try:
            return float(value)
        except ValueError:
            pass
        
        # 尝试转换为布尔值
        if value.lower() in ('true', 'yes', 'on', '1'):
            return True
        elif value.lower() in ('false', 'no', 'off', '0'):
            return False
        
        # 尝试解析JSON
        if value.startswith('{') or value.startswith('['):
            try:
                return json.loads(value)
            except json.JSONDecodeError:
                pass
        
        # 默认作为字符串返回
        return value 