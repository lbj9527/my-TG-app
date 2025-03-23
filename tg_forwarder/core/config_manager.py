"""
配置管理器实现类
负责加载、验证和管理应用程序配置
"""

import os
import json
import configparser
import copy
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
    
    def __init__(self, config_path: str = "config.ini", verbose: bool = False):
        """
        初始化配置管理器
        
        Args:
            config_path: 配置文件路径，支持.ini和.json格式
            verbose: 是否输出详细信息，默认为False
        """
        # 将相对路径转换为绝对路径
        if config_path and not os.path.isabs(config_path):
            config_path = os.path.abspath(config_path)
            if verbose:
                print(f"配置文件绝对路径: {config_path}")
        
        self.config_path = config_path
        self.config = {}
        self.parser = configparser.ConfigParser()
        self._loaded = False
        
        # 不再自动加载配置，让应用程序在需要时明确调用load_config()
    
    def load_config(self, verbose: bool = True) -> bool:
        """
        加载配置文件
        
        Args:
            verbose: 是否输出详细信息，默认为True
            
        Returns:
            bool: 成功返回True，失败返回False
        """
        if verbose:
            print(f"正在加载配置文件: {self.config_path}")
        
        # 将相对路径转换为绝对路径以确保文件读取
        if not os.path.isabs(self.config_path):
            self.config_path = os.path.abspath(self.config_path)
            if verbose:
                print(f"配置文件绝对路径: {self.config_path}")
        
        # 检查文件是否存在
        if not os.path.exists(self.config_path):
            print(f"配置文件不存在: {self.config_path}")
            return False
        
        if verbose:
            print(f"配置文件已找到")
        
        # 根据文件扩展名选择加载方式
        if self.config_path.endswith('.json'):
            load_success = self._load_json_config(verbose)
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
                if verbose:
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
            
        Raises:
            ConfigError: 如果配置项不存在且没有提供默认值
        """
        if not self._loaded:
            raise ConfigError(f"配置未加载，无法获取 {key}")
            
        try:
            # 处理嵌套键，如 'api.api_id'
            if '.' in key:
                parts = key.split('.')
                value = self.config
                for part in parts:
                    if isinstance(value, dict) and part in value:
                        value = value[part]
                    else:
                        if default is not None:
                            return default
                        raise ConfigError(f"配置项 {key} 不存在")
                return value
            else:
                if key in self.config:
                    return self.config[key]
                else:
                    if default is not None:
                        return default
                    raise ConfigError(f"配置项 {key} 不存在")
        except Exception as e:
            if not isinstance(e, ConfigError) and default is not None:
                return default
            raise ConfigError(f"获取配置 {key} 失败: {str(e)}")
    
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
            self.load_config(verbose=False)
        
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
    
    def get_temp_dir(self) -> str:
        """
        获取临时文件目录
        
        Returns:
            str: 临时文件目录路径
            
        Raises:
            ConfigError: 如果配置中没有指定临时目录
        """
        storage_config = self.get('storage')
        if not storage_config:
            raise ConfigError("配置中缺少存储配置")
            
        if 'tmp_path' not in storage_config:
            raise ConfigError("存储配置中缺少tmp_path参数")
            
        return storage_config['tmp_path']
    
    def get_session_name(self) -> str:
        """
        获取Telegram会话文件名
        
        Returns:
            str: 会话文件名
            
        Raises:
            ConfigError: 如果配置中没有指定会话名称
        """
        telegram_config = self.get('telegram')
        if not telegram_config:
            raise ConfigError("配置中缺少telegram配置")
            
        if 'session_name' not in telegram_config:
            raise ConfigError("telegram配置中缺少session_name参数")
            
        return telegram_config['session_name']
    
    def get_forward_config(self) -> Dict[str, Any]:
        """
        获取转发配置
        
        Returns:
            Dict[str, Any]: 转发配置字典
            
        Raises:
            ConfigError: 如果配置中没有转发配置
        """
        forward_config = self.get('forward')
        if not forward_config:
            raise ConfigError("配置中缺少转发配置")
            
        # 处理channel_pairs，优先使用forward_channel_pairs
        if 'forward_channel_pairs' in forward_config and forward_config['forward_channel_pairs']:
            # 将forward_channel_pairs转换为channel_pairs格式
            channel_pairs = {}
            for pair in forward_config['forward_channel_pairs']:
                source = pair.get('source_channel')
                targets = pair.get('target_channels', [])
                if source and targets:
                    channel_pairs[source] = targets
                    
            if channel_pairs:
                forward_config['channel_pairs'] = channel_pairs
                
        # 检查channel_pairs是否存在
        if not forward_config.get('channel_pairs'):
            raise ConfigError("转发配置中缺少有效的频道配对")
            
        return forward_config
    
    def get_download_config(self) -> Dict[str, Any]:
        """
        获取下载配置
        
        Returns:
            Dict[str, Any]: 下载配置字典，包含source_channels、directory、timeout等参数
            
        Raises:
            ConfigError: 如果配置中没有下载配置
        """
        download_config = self.get('download')
        if not download_config:
            raise ConfigError("配置中缺少下载配置")
        return download_config
    
    def get_upload_config(self) -> Dict[str, Any]:
        """
        获取上传配置
        
        Returns:
            Dict[str, Any]: 上传配置字典，包含target_channels、directory、timeout等参数
            
        Raises:
            ConfigError: 如果配置中没有上传配置
        """
        upload_config = self.get('upload')
        if not upload_config:
            raise ConfigError("配置中缺少上传配置")
        return upload_config
    
    def get_monitor_config(self) -> Dict[str, Any]:
        """
        获取监控配置
        
        Returns:
            Dict[str, Any]: 监控配置字典
            
        Raises:
            ConfigError: 如果配置中没有监控配置
        """
        monitor_config = self.get('monitor')
        if not monitor_config:
            raise ConfigError("配置中缺少监控配置")
            
        # 处理channel_pairs，优先使用monitor_channel_pairs
        if 'monitor_channel_pairs' in monitor_config and monitor_config['monitor_channel_pairs']:
            # 将monitor_channel_pairs转换为channel_pairs格式
            channel_pairs = {}
            for pair in monitor_config['monitor_channel_pairs']:
                source = pair.get('source_channel')
                targets = pair.get('target_channels', [])
                if source and targets:
                    channel_pairs[source] = targets
                    
            if channel_pairs:
                monitor_config['channel_pairs'] = channel_pairs
                
        # 检查channel_pairs是否存在
        if not monitor_config.get('channel_pairs'):
            raise ConfigError("监控配置中缺少有效的频道配对")
            
        # 检查监控时长配置
        if 'duration' not in monitor_config:
            raise ConfigError("监控配置中缺少监控时长(duration)参数")
            
        return monitor_config
    
    def get_storage_config(self) -> Dict[str, Any]:
        """
        获取存储配置
        
        Returns:
            Dict[str, Any]: 存储配置字典
            
        Raises:
            ConfigError: 如果配置中没有存储配置或缺少必要参数
        """
        storage_config = self.get('storage')
        if not storage_config:
            raise ConfigError("配置中缺少存储配置")
        
        # 检查必要的tmp_path参数
        if 'tmp_path' not in storage_config:
            raise ConfigError("存储配置中缺少临时路径(tmp_path)参数")
            
        return storage_config
    
    def get_channel_pairs(self) -> Dict[str, List[Union[str, int]]]:
        """
        获取频道配对信息（源频道到目标频道的映射）
        
        Returns:
            Dict[str, List[Union[str, int]]]: 源频道到目标频道的映射字典
            
        Raises:
            ConfigError: 如果找不到有效的频道配对
        """
        # 1. 首先尝试从forward.channel_pairs获取
        forward_config = self.get('forward', None)
        if forward_config and 'channel_pairs' in forward_config:
            return forward_config['channel_pairs']
            
        # 2. 尝试从forward.forward_channel_pairs获取并转换
        if forward_config and 'forward_channel_pairs' in forward_config:
            channel_pairs = {}
            for pair in forward_config['forward_channel_pairs']:
                source = pair.get('source_channel')
                targets = pair.get('target_channels', [])
                if source and targets:
                    channel_pairs[source] = targets
                    
            if channel_pairs:
                return channel_pairs
                
        raise ConfigError("无法找到有效的频道配对配置")
    
    def get_source_channel_config(self, channel_id: Optional[Union[int, str]] = None) -> Dict[str, Any]:
        """
        获取源频道配置
        
        Args:
            channel_id: 频道ID，可选
            
        Returns:
            Dict[str, Any]: 源频道配置
            
        Raises:
            ConfigError: 如果配置中缺少源频道配置
        """
        forward_config = self.get('forward')
        if not forward_config:
            raise ConfigError("配置中缺少转发配置")
        
        # 检查必要的参数是否存在
        if 'remove_captions' not in forward_config:
            raise ConfigError("转发配置中缺少remove_captions参数")
        
        if 'media_types' not in forward_config:
            raise ConfigError("转发配置中缺少media_types参数")
        
        # 返回全局配置
        return {
            'remove_captions': forward_config.get('remove_captions', False),
            'media_types': forward_config.get('media_types', []),
            'start_id': forward_config.get('start_message_id'),
            'end_id': forward_config.get('end_message_id'),
            'message_filter': forward_config.get('message_filter'),
            'add_watermark': forward_config.get('add_watermark', False),
            'watermark_text': forward_config.get('watermark_text', '')
        }
    
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
        
        # 验证频道配对配置
        forward_section = self.config.get('forward', {})
        
        # 检查forward_channel_pairs配置
        forward_channel_pairs = forward_section.get('forward_channel_pairs', [])
        if not forward_channel_pairs:
            errors.setdefault('forward.forward_channel_pairs', []).append("频道配对不能为空，请配置至少一对源频道到目标频道的映射")
        else:
            valid_pairs = False
            for idx, pair in enumerate(forward_channel_pairs):
                source = pair.get('source_channel')
                targets = pair.get('target_channels', [])
                
                if not source:
                    errors.setdefault(f'forward.forward_channel_pairs[{idx}].source_channel', []).append("源频道不能为空")
                    continue
                    
                if not targets:
                    errors.setdefault(f'forward.forward_channel_pairs[{idx}].target_channels', []).append("目标频道列表不能为空")
                    continue
                    
                # 发现至少一个有效的配对
                valid_pairs = True
                
            if not valid_pairs:
                errors.setdefault('forward.forward_channel_pairs', []).append("没有找到有效的频道配对")
        
        # 验证monitor_channel_pairs配置
        monitor_section = self.config.get('monitor', {})
        monitor_channel_pairs = monitor_section.get('monitor_channel_pairs', [])
        if monitor_section and not monitor_channel_pairs:
            errors.setdefault('monitor.monitor_channel_pairs', []).append("监听配置中缺少频道配对，请配置至少一对源频道到目标频道的映射")
        
        # 验证源频道配置部分
        source_channel_config = self.get('source_channel_config', {})
        for source_id, config in source_channel_config.items():
            # 检查必要的配置项
            if not isinstance(config, dict):
                errors.setdefault(f'source_channel_config.{source_id}', []).append("配置必须是一个字典")
                continue
                
            # 检查start_id和limit_messages的有效性（如果存在）
            if 'start_id' in config and (not isinstance(config['start_id'], int) or config['start_id'] < 0):
                errors.setdefault(f'source_channel_config.{source_id}.start_id', []).append("起始消息ID必须是一个非负整数")
                
            if 'limit_messages' in config and (not isinstance(config['limit_messages'], int) or config['limit_messages'] <= 0):
                errors.setdefault(f'source_channel_config.{source_id}.limit_messages', []).append("消息限制必须是一个正整数")
        
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
    
    def _load_json_config(self, verbose: bool = True) -> bool:
        """
        从JSON文件加载配置
        
        Args:
            verbose: 是否输出详细信息，默认为True
            
        Returns:
            bool: 加载成功返回True，否则返回False
        """
        try:
            with open(self.config_path, 'r', encoding='utf-8') as f:
                self.config = json.load(f)
                # 成功加载后设置_loaded为True
                self._loaded = True
                if verbose:
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
    
    def is_loaded(self) -> bool:
        """
        检查配置是否已经加载
        
        Returns:
            bool: 配置是否已加载
        """
        return self._loaded
    
    def get_config_dict(self) -> Dict[str, Any]:
        """
        获取完整的配置字典
        
        Returns:
            Dict[str, Any]: 包含所有配置项的字典
        """
        if not self.config or not self.is_loaded():
            self.load_config()
            
        # 返回整个配置字典的深拷贝，避免外部修改影响原配置
        return copy.deepcopy(self.config) 