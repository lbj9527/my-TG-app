"""
配置管理模块，负责读取和验证配置
"""

import os
import configparser
from typing import List, Optional, Dict, Any, Union
import logging

class ConfigError(Exception):
    """配置错误异常"""
    pass

class Config:
    """配置管理类"""
    
    def __init__(self, config_path: str = "config.ini"):
        """
        初始化配置
        
        Args:
            config_path: 配置文件路径
        """
        self.config_path = config_path
        self.config = configparser.ConfigParser()
        
        if not os.path.exists(config_path):
            raise ConfigError(f"配置文件 '{config_path}' 不存在，请复制 config_example.ini 并重命名为 {config_path}")
        
        self.config.read(config_path, encoding='utf-8')
        self._validate_config()
    
    def _validate_config(self) -> None:
        """验证配置文件的完整性和正确性"""
        # 验证API部分
        if 'API' not in self.config:
            raise ConfigError("配置文件中缺少 [API] 部分")
        
        required_api_fields = ['api_id', 'api_hash']
        for field in required_api_fields:
            if field not in self.config['API'] or not self.config['API'][field]:
                raise ConfigError(f"配置文件中缺少必要的API参数: {field}")
        
        # 验证CHANNELS部分
        if 'CHANNELS' not in self.config:
            raise ConfigError("配置文件中缺少 [CHANNELS] 部分")
        
        required_channel_fields = ['source_channel', 'target_channels']
        for field in required_channel_fields:
            if field not in self.config['CHANNELS'] or not self.config['CHANNELS'][field]:
                raise ConfigError(f"配置文件中缺少必要的频道参数: {field}")
    
    def get_api_config(self) -> Dict[str, Any]:
        """获取API配置"""
        api_config = {
            'api_id': int(self.config['API']['api_id']),
            'api_hash': self.config['API']['api_hash'],
        }
        
        # 可选的电话号码
        if 'phone_number' in self.config['API'] and self.config['API']['phone_number']:
            api_config['phone_number'] = self.config['API']['phone_number']
        
        return api_config
    
    def get_proxy_config(self) -> Optional[Dict[str, Any]]:
        """获取代理配置"""
        if 'PROXY' not in self.config or not self.config.getboolean('PROXY', 'enabled', fallback=False):
            return None
        
        proxy_config = {
            'proxy_type': self.config['PROXY']['proxy_type'],
            'addr': self.config['PROXY']['addr'],
            'port': int(self.config['PROXY']['port']),
        }
        
        # 可选的代理认证
        if 'username' in self.config['PROXY'] and self.config['PROXY']['username']:
            proxy_config['username'] = self.config['PROXY']['username']
        
        if 'password' in self.config['PROXY'] and self.config['PROXY']['password']:
            proxy_config['password'] = self.config['PROXY']['password']
        
        return proxy_config
    
    def get_channels_config(self) -> Dict[str, Union[str, List[str]]]:
        """获取频道配置"""
        source_channel = self.config['CHANNELS']['source_channel']
        target_channels = [
            channel.strip() 
            for channel in self.config['CHANNELS']['target_channels'].split(',')
        ]
        
        return {
            'source_channel': source_channel,
            'target_channels': target_channels
        }
    
    def get_forward_config(self) -> Dict[str, Any]:
        """
        获取转发配置
        
        Returns:
            Dict[str, Any]: 转发配置字典
        """
        forward_config = {}
        
        if 'FORWARD' in self.config:
            forward_config['start_message_id'] = self.config.getint('FORWARD', 'start_message_id', fallback=0)
            forward_config['end_message_id'] = self.config.getint('FORWARD', 'end_message_id', fallback=0)
            forward_config['hide_author'] = self.config.getboolean('FORWARD', 'hide_author', fallback=True)
            forward_config['delay'] = self.config.getfloat('FORWARD', 'delay', fallback=1.5)
            forward_config['batch_size'] = self.config.getint('FORWARD', 'batch_size', fallback=30)
            forward_config['skip_emoji_messages'] = self.config.getboolean('FORWARD', 'skip_emoji_messages', fallback=False)
        
        return forward_config
    
    def get_log_config(self) -> Dict[str, Any]:
        """
        获取日志配置
        
        Returns:
            Dict[str, Any]: 日志配置字典
        """
        log_config = {}
        
        if 'LOG' in self.config:
            log_config['level'] = self.config.get('LOG', 'level', fallback='INFO').upper()
            log_config['file'] = self.config.get('LOG', 'file', fallback='logs/app.log')
        
        return log_config
    
    def get_download_config(self) -> Dict[str, Any]:
        """
        获取下载配置
        
        Returns:
            Dict[str, Any]: 下载配置字典
        """
        download_config = {}
        
        if 'DOWNLOAD' in self.config:
            download_config['temp_folder'] = self.config.get('DOWNLOAD', 'temp_folder', fallback='temp')
            download_config['concurrent_downloads'] = self.config.getint('DOWNLOAD', 'concurrent_downloads', fallback=10)
            download_config['chunk_size'] = self.config.getint('DOWNLOAD', 'chunk_size', fallback=131072)
            download_config['retry_count'] = self.config.getint('DOWNLOAD', 'retry_count', fallback=3)
            download_config['retry_delay'] = self.config.getint('DOWNLOAD', 'retry_delay', fallback=5)
        else:
            # 默认配置
            download_config = {
                'temp_folder': 'temp',
                'concurrent_downloads': 10,
                'chunk_size': 131072,
                'retry_count': 3,
                'retry_delay': 5
            }
        
        return download_config
    
    def get_upload_config(self) -> Dict[str, Any]:
        """
        获取上传配置
        
        Returns:
            Dict[str, Any]: 上传配置字典
        """
        upload_config = {}
        
        if 'UPLOAD' in self.config:
            upload_config['concurrent_uploads'] = self.config.getint('UPLOAD', 'concurrent_uploads', fallback=3)
            upload_config['wait_between_messages'] = self.config.getfloat('UPLOAD', 'wait_between_messages', fallback=1.0)
            upload_config['preserve_formatting'] = self.config.getboolean('UPLOAD', 'preserve_formatting', fallback=True)
        else:
            # 默认配置
            upload_config = {
                'concurrent_uploads': 3,
                'wait_between_messages': 1.0,
                'preserve_formatting': True
            }
        
        return upload_config 