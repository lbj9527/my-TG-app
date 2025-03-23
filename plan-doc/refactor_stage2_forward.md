# Telegram转发工具重构计划 - 第二阶段（转发插件实现）

## 任务2.5：实现转发插件(ForwardPlugin)

转发插件是整个应用的核心功能组件，负责将消息从源频道转发到目标频道。

```python
# tg_app/plugins/forward/forward_plugin.py
import asyncio
import time
from typing import Dict, Any, List, Optional, Union, Tuple

from pyrogram import Client
from pyrogram.types import Message
from pyrogram.errors import FloodWait, ChatAdminRequired, ChatWriteForbidden

from tg_app.plugins.base import PluginBase
from tg_app.events import event_types as events
from tg_app.utils.logger import get_logger

# 获取日志记录器
logger = get_logger("forward_plugin")

class ForwardPlugin(PluginBase):
    """
    转发插件，负责将消息从源频道转发到目标频道
    """
    
    def __init__(self, event_bus):
        """
        初始化转发插件
        
        Args:
            event_bus: 事件总线
        """
        super().__init__(event_bus)
        
        self.client = None
        
        # 定义插件元数据
        self.id = "forward"
        self.name = "消息转发插件"
        self.version = "1.0.0"
        self.description = "将消息从源频道转发到目标频道"
        self.dependencies = ["client", "channel", "download", "upload", "task_queue"]
        
        # 运行状态
        self.is_running = False
        self.should_stop = False
        
        # 统计信息
        self.stats = {
            "total_messages": 0,
            "forwarded_messages": 0,
            "failed_messages": 0,
            "start_time": 0,
            "end_time": 0
        }
    
    async def initialize(self) -> None:
        """初始化插件"""
        logger.info("正在初始化转发插件...")
        
        # 注册事件处理器
        self.event_bus.subscribe(events.FORWARD_START, self._handle_forward_start)
        self.event_bus.subscribe(events.FORWARD_STOP, self._handle_forward_stop)
        self.event_bus.subscribe(events.APP_SHUTDOWN, self._handle_app_shutdown)
        
        # 获取客户端实例
        response = await self.event_bus.publish_and_wait(
            events.CLIENT_GET_INSTANCE,
            timeout=5.0
        )
        
        if not response or not response.get("success", False) or not response.get("client"):
            logger.error("获取客户端实例失败")
            return
            
        self.client = response.get("client")
        logger.info("转发插件初始化完成")
    
    async def _handle_forward_start(self, data: Dict[str, Any] = None) -> None:
        """
        处理开始转发事件
        
        Args:
            data: 事件数据
        """
        if not data:
            logger.error("未提供转发配置")
            await self.event_bus.publish(events.FORWARD_ERROR, {
                "error": "未提供转发配置"
            })
            return
            
        source_channel = data.get("source_channel")
        target_channels = data.get("target_channels", [])
        config = data.get("config", {})
        
        if not source_channel:
            logger.error("未指定源频道")
            await self.event_bus.publish(events.FORWARD_ERROR, {
                "error": "未指定源频道"
            })
            return
            
        if not target_channels:
            logger.error("未指定目标频道")
            await self.event_bus.publish(events.FORWARD_ERROR, {
                "error": "未指定目标频道"
            })
            return
            
        # 异步运行转发任务
        asyncio.create_task(
            self.run_forward(source_channel, target_channels, config)
        )
    
    async def _handle_forward_stop(self, data: Dict[str, Any] = None) -> None:
        """
        处理停止转发事件
        
        Args:
            data: 事件数据
        """
        if self.is_running:
            logger.info("收到停止转发命令")
            self.should_stop = True
    
    async def _handle_app_shutdown(self, data: Dict[str, Any] = None) -> None:
        """
        处理应用关闭事件
        
        Args:
            data: 事件数据
        """
        if self.is_running:
            logger.info("应用关闭，停止转发")
            self.should_stop = True
    
    async def run_forward(
        self, 
        source_channel: str, 
        target_channels: List[str], 
        config: Dict[str, Any] = None
    ) -> Dict[str, Any]:
        """
        运行转发流程
        
        Args:
            source_channel: 源频道
            target_channels: 目标频道列表
            config: 转发配置
            
        Returns:
            Dict[str, Any]: 转发结果
        """
        if self.is_running:
            logger.warning("转发任务已在运行中")
            return {"success": False, "error": "转发任务已在运行中"}
            
        if not self.client:
            logger.error("客户端未初始化")
            return {"success": False, "error": "客户端未初始化"}
            
        # 设置默认配置
        if not config:
            config = {}
            
        batch_size = config.get("batch_size", 10)
        delay_between_batches = config.get("delay_between_batches", 2)
        preserve_date = config.get("preserve_date", False)
        copy_media = config.get("copy_media", True)
        
        # 重置状态
        self.is_running = True
        self.should_stop = False
        self.stats = {
            "total_messages": 0,
            "forwarded_messages": 0,
            "failed_messages": 0,
            "start_time": time.time(),
            "end_time": 0
        }
        
        logger.info(f"开始转发: 从 {source_channel} 到 {', '.join(target_channels)}")
        
        # 发布转发开始事件
        await self.event_bus.publish(events.FORWARD_STARTED, {
            "source_channel": source_channel,
            "target_channels": target_channels,
            "config": config
        })
        
        try:
            # 解析源频道
            source_entity_result = await self.event_bus.publish_and_wait(
                events.CHANNEL_PARSE,
                {"channel": source_channel},
                timeout=30.0
            )
            
            if not source_entity_result or not source_entity_result.get("success", False):
                error_msg = source_entity_result.get("error", "无法解析源频道")
                logger.error(error_msg)
                return {"success": False, "error": error_msg}
                
            source_entity = source_entity_result["entity"]
            
            # 解析目标频道
            target_entities = []
            for target in target_channels:
                target_entity_result = await self.event_bus.publish_and_wait(
                    events.CHANNEL_PARSE,
                    {"channel": target},
                    timeout=30.0
                )
                
                if not target_entity_result or not target_entity_result.get("success", False):
                    error_msg = target_entity_result.get("error", f"无法解析目标频道 {target}")
                    logger.error(error_msg)
                    continue
                    
                target_entities.append(target_entity_result["entity"])
            
            if not target_entities:
                logger.error("无法解析任何目标频道")
                return {"success": False, "error": "无法解析任何目标频道"}
                
            # 获取源频道消息
            messages_result = await self.event_bus.publish_and_wait(
                events.MESSAGE_GET_FROM_CHANNEL,
                {
                    "chat_id": source_entity.id,
                    "limit": config.get("limit", 100)  # 默认获取最新的100条消息
                },
                timeout=120.0
            )
            
            if not messages_result or not messages_result.get("success", False):
                error_msg = messages_result.get("error", "获取源频道消息失败")
                logger.error(error_msg)
                return {"success": False, "error": error_msg}
                
            messages = messages_result["messages"]
            self.stats["total_messages"] = len(messages)
            
            logger.info(f"从源频道获取到 {len(messages)} 条消息")
            
            # 分批转发消息
            batches = [messages[i:i+batch_size] for i in range(0, len(messages), batch_size)]
            
            for batch_idx, batch in enumerate(batches):
                if self.should_stop:
                    logger.info("收到停止命令，中断转发")
                    break
                    
                logger.info(f"正在处理批次 {batch_idx+1}/{len(batches)} ({len(batch)} 条消息)")
                
                # 发布批次开始事件
                await self.event_bus.publish(events.FORWARD_BATCH_START, {
                    "batch_index": batch_idx,
                    "batch_size": len(batch),
                    "total_batches": len(batches)
                })
                
                # 转发批次消息
                batch_results = await self._forward_batch(
                    batch, 
                    target_entities, 
                    preserve_date=preserve_date,
                    copy_media=copy_media
                )
                
                # 更新统计信息
                self.stats["forwarded_messages"] += batch_results["forwarded"]
                self.stats["failed_messages"] += batch_results["failed"]
                
                # 发布批次完成事件
                await self.event_bus.publish(events.FORWARD_BATCH_COMPLETE, {
                    "batch_index": batch_idx,
                    "results": batch_results,
                    "stats": self.stats
                })
                
                # 批次之间延迟
                if batch_idx < len(batches) - 1 and not self.should_stop:
                    logger.info(f"等待 {delay_between_batches} 秒后继续")
                    await asyncio.sleep(delay_between_batches)
            
            # 完成转发
            self.stats["end_time"] = time.time()
            elapsed_time = self.stats["end_time"] - self.stats["start_time"]
            
            logger.info(f"转发完成: {self.stats['forwarded_messages']}/{self.stats['total_messages']} "
                       f"条消息成功，耗时 {elapsed_time:.2f} 秒")
            
            # 发布转发完成事件
            await self.event_bus.publish(events.FORWARD_COMPLETED, {
                "stats": self.stats
            })
            
            return {
                "success": True,
                "stats": self.stats,
                "message": f"转发完成: {self.stats['forwarded_messages']}/{self.stats['total_messages']} 条消息成功"
            }
            
        except Exception as e:
            error_msg = f"转发过程中出错: {str(e)}"
            logger.exception(error_msg)
            
            # 发布转发错误事件
            await self.event_bus.publish(events.FORWARD_ERROR, {
                "error": error_msg,
                "stats": self.stats
            })
            
            return {"success": False, "error": error_msg, "stats": self.stats}
            
        finally:
            self.is_running = False
            self.should_stop = False
    
    async def _forward_batch(
        self, 
        messages: List[Message], 
        target_entities: List[Any],
        preserve_date: bool = False,
        copy_media: bool = True
    ) -> Dict[str, Any]:
        """
        转发一批消息
        
        Args:
            messages: 消息列表
            target_entities: 目标实体列表
            preserve_date: 是否保留原始日期
            copy_media: 是否复制媒体文件
            
        Returns:
            Dict[str, Any]: 转发结果
        """
        results = {
            "forwarded": 0,
            "failed": 0,
            "details": []
        }
        
        for msg_idx, message in enumerate(messages):
            if self.should_stop:
                break
                
            logger.debug(f"正在转发消息 {msg_idx+1}/{len(messages)}")
            
            # 处理媒体消息
            if copy_media and message.media:
                # 发布下载媒体事件
                download_result = await self.event_bus.publish_and_wait(
                    events.MEDIA_DOWNLOAD,
                    {"message": message},
                    timeout=300.0  # 大文件可能需要较长时间
                )
                
                if not download_result or not download_result.get("success", False):
                    error_msg = download_result.get("error", "下载媒体失败")
                    logger.error(f"消息 {message.id} 的媒体下载失败: {error_msg}")
                    
                    results["failed"] += 1
                    results["details"].append({
                        "message_id": message.id,
                        "success": False,
                        "error": error_msg
                    })
                    continue
                    
                # 获取下载的媒体信息
                media_info = download_result.get("media_info", {})
                
                # 对每个目标频道上传媒体
                msg_results = []
                for target in target_entities:
                    try:
                        # 发布上传媒体事件
                        upload_result = await self.event_bus.publish_and_wait(
                            events.MEDIA_UPLOAD,
                            {
                                "chat_id": target.id,
                                "media_info": media_info,
                                "message": message,
                                "preserve_date": preserve_date
                            },
                            timeout=300.0  # 大文件可能需要较长时间
                        )
                        
                        if not upload_result or not upload_result.get("success", False):
                            error_msg = upload_result.get("error", "上传媒体失败")
                            logger.error(f"消息 {message.id} 上传到 {target.username or target.id} 失败: {error_msg}")
                            
                            msg_results.append({
                                "target": target.id,
                                "success": False,
                                "error": error_msg
                            })
                        else:
                            logger.debug(f"消息 {message.id} 上传到 {target.username or target.id} 成功")
                            
                            msg_results.append({
                                "target": target.id,
                                "success": True,
                                "new_message_id": upload_result.get("message_id")
                            })
                            
                    except Exception as e:
                        error_msg = f"上传媒体时出错: {str(e)}"
                        logger.exception(error_msg)
                        
                        msg_results.append({
                            "target": target.id,
                            "success": False,
                            "error": error_msg
                        })
                
                # 检查是否至少有一个目标成功
                if any(result["success"] for result in msg_results):
                    results["forwarded"] += 1
                else:
                    results["failed"] += 1
                    
                results["details"].append({
                    "message_id": message.id,
                    "results": msg_results
                })
                
            else:
                # 非媒体消息或不复制媒体，直接转发
                msg_results = []
                for target in target_entities:
                    try:
                        # 发布转发消息事件
                        forward_result = await self.event_bus.publish_and_wait(
                            events.MESSAGE_FORWARD,
                            {
                                "message": message,
                                "chat_id": target.id,
                                "preserve_date": preserve_date
                            },
                            timeout=30.0
                        )
                        
                        if not forward_result or not forward_result.get("success", False):
                            error_msg = forward_result.get("error", "转发消息失败")
                            logger.error(f"消息 {message.id} 转发到 {target.username or target.id} 失败: {error_msg}")
                            
                            msg_results.append({
                                "target": target.id,
                                "success": False,
                                "error": error_msg
                            })
                        else:
                            logger.debug(f"消息 {message.id} 转发到 {target.username or target.id} 成功")
                            
                            msg_results.append({
                                "target": target.id,
                                "success": True,
                                "new_message_id": forward_result.get("message_id")
                            })
                            
                    except FloodWait as e:
                        # 遇到限制，等待指定时间
                        logger.warning(f"遇到限制，等待 {e.value} 秒")
                        await asyncio.sleep(e.value)
                        
                        # 重试
                        try:
                            forward_result = await self.event_bus.publish_and_wait(
                                events.MESSAGE_FORWARD,
                                {
                                    "message": message,
                                    "chat_id": target.id,
                                    "preserve_date": preserve_date
                                },
                                timeout=30.0
                            )
                            
                            if forward_result and forward_result.get("success", False):
                                logger.debug(f"重试后消息 {message.id} 转发到 {target.username or target.id} 成功")
                                
                                msg_results.append({
                                    "target": target.id,
                                    "success": True,
                                    "new_message_id": forward_result.get("message_id")
                                })
                            else:
                                error_msg = forward_result.get("error", "重试后转发消息失败")
                                logger.error(f"重试后消息 {message.id} 转发到 {target.username or target.id} 失败: {error_msg}")
                                
                                msg_results.append({
                                    "target": target.id,
                                    "success": False,
                                    "error": error_msg
                                })
                                
                        except Exception as e:
                            error_msg = f"重试转发时出错: {str(e)}"
                            logger.exception(error_msg)
                            
                            msg_results.append({
                                "target": target.id,
                                "success": False,
                                "error": error_msg
                            })
                            
                    except (ChatAdminRequired, ChatWriteForbidden) as e:
                        error_msg = f"无权限向频道 {target.username or target.id} 发送消息: {str(e)}"
                        logger.error(error_msg)
                        
                        msg_results.append({
                            "target": target.id,
                            "success": False,
                            "error": error_msg
                        })
                        
                    except Exception as e:
                        error_msg = f"转发消息时出错: {str(e)}"
                        logger.exception(error_msg)
                        
                        msg_results.append({
                            "target": target.id,
                            "success": False,
                            "error": error_msg
                        })
                
                # 检查是否至少有一个目标成功
                if any(result["success"] for result in msg_results):
                    results["forwarded"] += 1
                else:
                    results["failed"] += 1
                    
                results["details"].append({
                    "message_id": message.id,
                    "results": msg_results
                })
        
        return results
    
    async def shutdown(self) -> None:
        """关闭插件"""
        logger.info("正在关闭转发插件...")
        
        # 停止正在运行的转发任务
        if self.is_running:
            logger.info("有转发任务正在运行，尝试停止")
            self.should_stop = True
            
            # 等待任务停止
            for _ in range(10):  # 最多等待10秒
                if not self.is_running:
                    break
                await asyncio.sleep(1)
        
        # 取消事件订阅
        self.event_bus.unsubscribe(events.FORWARD_START, self._handle_forward_start)
        self.event_bus.unsubscribe(events.FORWARD_STOP, self._handle_forward_stop)
        self.event_bus.unsubscribe(events.APP_SHUTDOWN, self._handle_app_shutdown)
        
        self.client = None
        logger.info("转发插件已关闭")
```

## 开发说明

1. **转发流程**:
   - 将复杂的转发流程拆分为多个步骤和批次处理
   - 支持中断和恢复功能，以及进度跟踪
   - 通过事件总线与下载、上传等组件交互

2. **错误处理**:
   - 实现了细粒度的错误处理机制
   - 针对常见问题如速率限制、权限错误等进行专门处理
   - 详细记录每个消息的转发结果

3. **媒体处理**:
   - 支持媒体文件的下载和上传
   - 可选择是否保留原始日期
   - 对大文件设置更长的超时时间

4. **批次处理**:
   - 按批次处理消息，每批之间添加延迟避免触发限制
   - 提供批次开始和完成事件，便于监控进度

5. **统计信息**:
   - 跟踪总消息数、成功数、失败数和耗时
   - 记录每个消息的详细结果 