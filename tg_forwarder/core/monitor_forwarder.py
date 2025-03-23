"""
监听转发器模块
实现Telegram消息的实时监听和转发功能
"""

import os
import time
import asyncio
from datetime import datetime
from typing import Dict, Any, List, Optional, Union, Set, Tuple
from pyrogram.types import Message
from pyrogram.errors import (
    FloodWait
)

from tg_forwarder.interfaces.forwarder_interface import ForwarderInterface
from tg_forwarder.interfaces.client_interface import TelegramClientInterface
from tg_forwarder.interfaces.history_tracker_interface import HistoryTrackerInterface
from tg_forwarder.interfaces.json_storage_interface import JsonStorageInterface
from tg_forwarder.interfaces.logger_interface import LoggerInterface
from tg_forwarder.core.channel_factory import (
    parse_channel, format_channel, is_channel_valid, can_forward_from, can_forward_to
)
from tg_forwarder.utils.exceptions import ChannelParseError
from tg_forwarder.core.forwarder import Forwarder


class MonitorForwarder(Forwarder):
    """
    监听转发器实现类，负责处理Telegram消息的实时监听和转发功能
    继承自基础转发器类，添加监听特定功能
    """

    def __init__(self, 
                client: TelegramClientInterface,
                history_tracker: HistoryTrackerInterface,
                json_storage: JsonStorageInterface,
                logger: LoggerInterface,
                config: Dict[str, Any]) -> None:
        """
        初始化监听转发器

        Args:
            client: Telegram客户端接口
            history_tracker: 历史记录跟踪器接口
            json_storage: JSON存储接口
            logger: 日志记录接口
            config: 转发配置
        """
        super().__init__(client, history_tracker, json_storage, logger, config)
        
        # 监听状态变量
        self._monitoring_active = False
        self._monitor_tasks = []
        self._monitor_handler = None

    async def start_monitor(self, monitor_config: Dict[str, Any] = None) -> Dict[str, Any]:
        """
        开始监听源频道，实时转发新消息

        Args:
            monitor_config: 监听配置，为None时使用默认配置

        Returns:
            Dict[str, Any]: 监听结果
        """
        try:
            config = monitor_config if monitor_config else self._monitor_config
            self._logger.info("开始监听源频道新消息")
            
            if not config:
                self._logger.error("监听配置为空")
                return {"success": False, "error": "监听配置为空"}
            
            channel_pairs = config.get('monitor_channel_pairs', [])
            if not channel_pairs:
                self._logger.error("没有配置监听频道对")
                return {"success": False, "error": "没有配置监听频道对"}
            
            # 解析监听时长
            duration_str = config.get('duration', '')
            end_time = None
            if duration_str:
                try:
                    # 格式为"年-月-日-时"，如"2025-3-28-1"
                    parts = duration_str.split('-')
                    if len(parts) >= 4:
                        year = int(parts[0])
                        month = int(parts[1])
                        day = int(parts[2])
                        hour = int(parts[3])
                        end_time = datetime(year, month, day, hour)
                        self._logger.info(f"监听将于 {end_time} 结束")
                except Exception as e:
                    self._logger.error(f"解析监听时长时出错: {str(e)}")
                    return {"success": False, "error": f"解析监听时长时出错: {str(e)}"}
            
            # 标记监听状态为激活
            self._monitoring_active = True
            
            # 创建监听任务
            self._monitor_task = asyncio.create_task(self._monitor_channels(config, end_time))
            self._monitor_tasks.append(self._monitor_task)
            
            self._logger.info("监听任务已启动")
            return {"success": True, "message": "监听任务已启动"}
            
        except Exception as e:
            error_msg = f"启动监听时出错: {str(e)}"
            self._logger.error(error_msg)
            return {"success": False, "error": error_msg}

    async def _monitor_channels(self, config: Dict[str, Any], end_time: Optional[datetime] = None) -> None:
        """
        监听频道任务

        Args:
            config: 监听配置
            end_time: 结束时间
        """
        try:
            # 获取频道对列表
            channel_pairs = config.get('monitor_channel_pairs', [])
            
            # 设置handler来处理新消息
            @self._client._app.on_message()
            async def message_handler(client, message):
                if not self._monitoring_active:
                    return
                
                # 检查是否过期
                if end_time and datetime.now() > end_time:
                    self._logger.info("监听时间已到，停止监听")
                    self._monitoring_active = False
                    return
                
                # 处理新消息
                await self.handle_new_message(message)
            
            # 保存handler引用以便后续移除
            self._monitor_handler = message_handler
            
            # 持续监听直到结束时间或手动停止
            while self._monitoring_active:
                # 检查是否过期
                if end_time and datetime.now() > end_time:
                    self._logger.info("监听时间已到，停止监听")
                    self._monitoring_active = False
                    break
                
                await asyncio.sleep(1)
                
        except Exception as e:
            self._logger.error(f"监听频道时出错: {str(e)}")
            self._monitoring_active = False

    async def handle_new_message(self, message: Message) -> Dict[str, Any]:
        """
        处理监听到的新消息

        Args:
            message: 新消息

        Returns:
            Dict[str, Any]: 处理结果
        """
        result = {
            'success': False,
            'forwarded': False,
            'error': None
        }
        
        if not message or not hasattr(message, 'chat') or not hasattr(message.chat, 'id'):
            result['error'] = "无效的消息"
            return result
        
        # 获取源频道ID
        source_channel = message.chat.id
        message_id = message.id
        
        # 获取监听配置
        config = self._monitor_config
        
        # 找到对应的频道对
        target_channels = []
        for pair in config.get('monitor_channel_pairs', []):
            pair_source = pair.get('source_channel', '')
            # 尝试解析和匹配源频道
            if str(source_channel) in str(pair_source) or str(pair_source) in str(source_channel):
                target_channels = pair.get('target_channels', [])
                break
        
        if not target_channels:
            result['error'] = f"找不到源频道 {source_channel} 对应的目标频道"
            return result
        
        # 检查消息类型是否允许
        media_types = config.get('media_types', ["photo", "video", "document", "audio", "animation"])
        if not self.is_message_type_allowed(message, media_types):
            result['error'] = "消息类型不符合转发要求"
            return result
        
        # 转发消息
        remove_captions = config.get('remove_captions', False)
        download_media = await self.is_channel_restricted(source_channel)
        
        # 转发消息
        forward_result = await self.forward_single_message(
            message=message,
            target_channels=target_channels,
            remove_captions=remove_captions,
            download_media=download_media
        )
        
        result['success'] = forward_result.get('success', False)
        result['forwarded'] = result['success']
        if not result['success'] and 'error' in forward_result:
            result['error'] = forward_result['error']
        
        # 应用转发延迟
        forward_delay = config.get('forward_delay', 2)
        await asyncio.sleep(forward_delay)
        
        return result

    async def stop_monitoring(self) -> Dict[str, Any]:
        """
        停止监听功能
        
        Returns:
            Dict[str, Any]: 停止结果
        """
        if not self._monitoring_active:
            return {"success": False, "error": "监听服务未在运行"}
        
        try:
            # 取消所有监听任务
            for task in self._monitor_tasks:
                if not task.done():
                    task.cancel()
            
            # 移除消息处理器
            if self._monitor_handler:
                self._client._app.remove_handler(self._monitor_handler)
                self._monitor_handler = None
            
            self._monitoring_active = False
            self._logger.info("监听功能已停止")
            
            return {"success": True, "message": "监听服务已停止"}
        except Exception as e:
            self._logger.error(f"停止监听功能失败: {str(e)}")
            return {"success": False, "error": str(e)}

    def get_monitoring_stats(self) -> Dict[str, Any]:
        """
        获取监听状态统计信息
        
        Returns:
            Dict[str, Any]: 监听状态统计
        """
        return {
            "monitoring_active": self._monitoring_active,
            "tasks_count": len(self._monitor_tasks),
            "active_tasks": sum(1 for task in self._monitor_tasks if not task.done()),
            "handler_active": self._monitor_handler is not None
        }

    def close(self) -> None:
        """关闭监听转发器，释放资源"""
        # 停止监听
        if self._monitoring_active:
            self.stop_monitoring()
        
        # 调用父类关闭方法
        super().close() 