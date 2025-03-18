"""
上传模块的配置验证工具
"""

import os
from typing import Dict, Any, List, Union, Optional


class UploaderConfigValidator:
    """配置验证器，用于验证和规范化上传配置"""
    
    @staticmethod
    def validate_client_config(client: Any) -> Dict[str, Any]:
        """
        验证客户端配置
        
        Args:
            client: Telegram客户端
            
        Returns:
            Dict[str, Any]: 验证后的客户端配置
        
        Raises:
            ValueError: 配置无效时抛出
        """
        if not client:
            raise ValueError("客户端不能为空")
        
        # 检查必要属性
        if not hasattr(client, 'api_id') or not hasattr(client, 'api_hash'):
            # 尝试查找嵌套客户端
            if hasattr(client, 'client'):
                actual_client = client.client
                if not hasattr(actual_client, 'api_id') or not hasattr(actual_client, 'api_hash'):
                    raise ValueError("无法获取客户端API信息")
                
                api_config = {
                    'api_id': actual_client.api_id,
                    'api_hash': actual_client.api_hash
                }
            else:
                raise ValueError("无法获取客户端API信息")
        else:
            api_config = {
                'api_id': client.api_id,
                'api_hash': client.api_hash
            }
        
        # 检查代理设置
        proxy_config = None
        if hasattr(client, 'proxy_config') and client.proxy_config:
            proxy_config = client.proxy_config.copy() if isinstance(client.proxy_config, dict) else None
        
        return {
            'api_config': api_config,
            'proxy_config': proxy_config
        }
    
    @staticmethod
    def validate_upload_config(config: Dict[str, Any]) -> Dict[str, Any]:
        """
        验证上传配置
        
        Args:
            config: 原始配置字典
            
        Returns:
            Dict[str, Any]: 验证后的配置
        """
        validated_config = {}
        
        # 检查并设置默认值
        validated_config['temp_folder'] = config.get('temp_folder', 'temp')
        validated_config['wait_time'] = float(config.get('wait_time', 1.0))
        validated_config['retry_count'] = int(config.get('retry_count', 3))
        validated_config['retry_delay'] = int(config.get('retry_delay', 5))
        
        # 验证临时文件夹路径
        if not os.path.exists(validated_config['temp_folder']):
            try:
                os.makedirs(validated_config['temp_folder'], exist_ok=True)
            except Exception as e:
                raise ValueError(f"无法创建临时文件夹: {str(e)}")
        
        # 验证等待时间
        if validated_config['wait_time'] < 0.1:
            validated_config['wait_time'] = 0.1
        
        # 验证重试次数
        if validated_config['retry_count'] < 0:
            validated_config['retry_count'] = 0
        
        # 验证重试延迟
        if validated_config['retry_delay'] < 1:
            validated_config['retry_delay'] = 1
        
        return validated_config
    
    @staticmethod
    def validate_channels(channels: List[Union[str, int]]) -> List[Union[str, int]]:
        """
        验证频道列表
        
        Args:
            channels: 频道ID或用户名列表
            
        Returns:
            List[Union[str, int]]: 验证后的频道列表
        
        Raises:
            ValueError: 频道列表无效时抛出
        """
        if not channels:
            raise ValueError("目标频道列表不能为空")
        
        validated_channels = []
        for channel in channels:
            if isinstance(channel, (str, int)):
                validated_channels.append(channel)
            else:
                raise ValueError(f"无效的频道标识符: {channel}")
        
        return validated_channels 