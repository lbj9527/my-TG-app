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
        self.config_path = config_path
        self.config = {}
        self.parser = configparser.ConfigParser()
        self._loaded = False
    
    def load_config(self) -> bool:
        """
        加载配置文件
        
        Returns:
            bool: 加载是否成功
        """
        try:
            if not os.path.exists(self.config_path):
                raise ConfigError(f"配置文件 '{self.config_path}' 不存在")
            
            # 根据文件扩展名选择不同的加载方式
            if self.config_path.endswith('.ini'):
                self._load_ini_config()
            elif self.config_path.endswith('.json'):
                self._load_json_config()
            else:
                raise ConfigError(f"不支持的配置文件格式: {self.config_path}")
            
            # 验证配置有效性
            self._validate_config()
            self._loaded = True
            return True
        except Exception as e:
            error_msg = f"加载配置失败: {str(e)}"
            print(error_msg)  # 在日志模块初始化前先打印到控制台
            self._loaded = False
            return False
    
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
    
    def get(self, key: str, default: Optional[T] = None) -> T:
        """
        获取配置项
        
        Args:
            key: 配置键，支持点号分隔的路径，如 "api.api_id"
            default: 默认值
            
        Returns:
            配置值，若不存在则返回默认值
        """
        if not self._loaded:
            return default
        
        # 处理嵌套配置项
        if '.' in key:
            parts = key.split('.')
            current = self.config
            for part in parts:
                if isinstance(current, dict) and part in current:
                    current = current[part]
                else:
                    return default
            return current
        
        return self.config.get(key, default)
    
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
        api_id = self.get('api.api_id')
        if api_id is None:
            raise ConfigError("配置中缺少 api_id")
        return int(api_id)
    
    def get_telegram_api_hash(self) -> str:
        """
        获取Telegram API Hash
        
        Returns:
            str: API Hash
        """
        api_hash = self.get('api.api_hash')
        if api_hash is None:
            raise ConfigError("配置中缺少 api_hash")
        return str(api_hash)
    
    def get_session_name(self) -> str:
        """
        获取会话名称
        
        Returns:
            str: 会话名称
        """
        return self.get('api.session_name', 'tg_forwarder')
    
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
        if not self.get('api.api_id'):
            errors.setdefault('api.api_id', []).append("API ID不能为空")
        
        if not self.get('api.api_hash'):
            errors.setdefault('api.api_hash', []).append("API Hash不能为空")
        
        # 验证频道部分
        if not self.get_source_channels():
            errors.setdefault('channels.source_channels', []).append("源频道列表不能为空")
        
        if not self.get_target_channels():
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
    
    def _load_json_config(self) -> None:
        """从JSON文件加载配置"""
        with open(self.config_path, 'r', encoding='utf-8') as f:
            self.config = json.load(f)
    
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