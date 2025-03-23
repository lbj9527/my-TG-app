# Telegram转发工具重构计划 - 第二阶段（上传插件实现）

## 任务2.9：实现上传插件(UploadPlugin)

上传插件负责将下载的媒体文件上传到目标频道。

```python
# tg_app/plugins/uploader/upload_plugin.py
import os
import asyncio
from typing import Dict, Any, List, Optional, Union, Tuple

from pyrogram import Client
from pyrogram.types import Message, InputMedia
from pyrogram.errors import FloodWait, ChatWriteForbidden, MessageNotModified

from tg_app.plugins.base import PluginBase
from tg_app.events import event_types as events
from tg_app.utils.logger import get_logger

# 获取日志记录器
logger = get_logger("upload_plugin")

class UploadPlugin(PluginBase):
    """
    上传插件，负责将媒体文件上传到Telegram
    """
    
    def __init__(self, event_bus):
        """
        初始化上传插件
        
        Args:
            event_bus: 事件总线
        """
        super().__init__(event_bus)
        
        self.client = None
        
        # 定义插件元数据
        self.id = "upload"
        self.name = "媒体上传插件"
        self.version = "1.0.0"
        self.description = "将媒体文件上传到Telegram"
        self.dependencies = ["client", "task_queue"]
        
        # 活跃上传
        self.active_uploads = {}
    
    async def initialize(self) -> None:
        """初始化插件"""
        logger.info("正在初始化上传插件...")
        
        # 注册事件处理器
        self.event_bus.subscribe(events.MEDIA_UPLOAD, self._handle_media_upload)
        self.event_bus.subscribe(events.MEDIA_UPLOAD_CANCEL, self._handle_media_upload_cancel)
        self.event_bus.subscribe(events.MEDIA_UPLOAD_STATUS, self._handle_media_upload_status)
        self.event_bus.subscribe(events.MESSAGE_FORWARD, self._handle_message_forward)
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
        logger.info("上传插件初始化完成")
    
    async def _handle_media_upload(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """
        处理媒体上传事件
        
        Args:
            data: 事件数据
            
        Returns:
            Dict[str, Any]: 上传结果
        """
        chat_id = data.get("chat_id")
        media_info = data.get("media_info")
        message = data.get("message")  # 原始消息
        preserve_date = data.get("preserve_date", False)
        
        if not chat_id:
            return {"success": False, "error": "未提供聊天ID"}
            
        if not media_info:
            return {"success": False, "error": "未提供媒体信息"}
            
        # 检查必要的媒体信息
        if "media_type" not in media_info or "file_path" not in media_info:
            return {"success": False, "error": "媒体信息不完整"}
            
        # 检查文件是否存在
        if not os.path.exists(media_info["file_path"]):
            return {"success": False, "error": f"文件不存在: {media_info['file_path']}"}
            
        # 创建上传任务
        upload_task = asyncio.create_task(self._upload_media(
            chat_id, 
            media_info, 
            message, 
            preserve_date
        ))
        
        # 将任务添加到任务队列
        response = await self.event_bus.publish_and_wait(
            events.TASK_ADD,
            {
                "coroutine": upload_task,
                "priority": data.get("priority", 0),
                "metadata": {
                    "type": "media_upload",
                    "chat_id": chat_id,
                    "media_type": media_info["media_type"],
                    "file_path": media_info["file_path"]
                }
            },
            timeout=5.0
        )
        
        if not response or not response.get("success", False):
            upload_task.cancel()
            return {"success": False, "error": "添加上传任务失败"}
            
        task_id = response["task_id"]
        
        # 添加到活跃上传
        self.active_uploads[task_id] = {
            "chat_id": chat_id,
            "media_info": media_info,
            "started_at": asyncio.get_event_loop().time(),
            "progress": 0,
            "status": "pending"
        }
        
        # 返回任务ID
        return {"success": True, "task_id": task_id}
    
    async def _handle_media_upload_cancel(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """
        处理取消媒体上传事件
        
        Args:
            data: 事件数据
            
        Returns:
            Dict[str, Any]: 取消结果
        """
        task_id = data.get("task_id")
        if not task_id:
            return {"success": False, "error": "未提供任务ID"}
            
        # 取消任务
        response = await self.event_bus.publish_and_wait(
            events.TASK_CANCEL,
            {"task_id": task_id},
            timeout=5.0
        )
        
        if not response or not response.get("success", False):
            return {"success": False, "error": response.get("error", "取消任务失败")}
            
        # 从活跃上传中移除
        if task_id in self.active_uploads:
            del self.active_uploads[task_id]
            
        return {"success": True}
    
    async def _handle_media_upload_status(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """
        处理获取媒体上传状态事件
        
        Args:
            data: 事件数据
            
        Returns:
            Dict[str, Any]: 上传状态
        """
        task_id = data.get("task_id")
        if not task_id:
            return {"success": False, "error": "未提供任务ID"}
            
        # 检查是否在活跃上传中
        if task_id not in self.active_uploads:
            # 尝试从任务队列获取状态
            response = await self.event_bus.publish_and_wait(
                events.TASK_GET_STATUS,
                {"task_id": task_id},
                timeout=5.0
            )
            
            if not response or not response.get("success", False):
                return {"success": False, "error": "任务不存在"}
                
            return response
            
        # 获取上传状态
        upload_info = self.active_uploads[task_id]
        
        return {
            "success": True,
            "status": upload_info["status"],
            "progress": upload_info["progress"],
            "started_at": upload_info["started_at"],
            "chat_id": upload_info["chat_id"],
            "media_type": upload_info["media_info"]["media_type"]
        }
    
    async def _handle_message_forward(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """
        处理消息转发事件
        
        Args:
            data: 事件数据
            
        Returns:
            Dict[str, Any]: 转发结果
        """
        message = data.get("message")
        chat_id = data.get("chat_id")
        preserve_date = data.get("preserve_date", False)
        
        if not message:
            return {"success": False, "error": "未提供消息"}
            
        if not chat_id:
            return {"success": False, "error": "未提供目标聊天ID"}
            
        try:
            logger.info(f"转发消息 {message.id} 到聊天 {chat_id}")
            
            # 使用Pyrogram的forward_messages方法
            forwarded_message = await message.forward(
                chat_id=chat_id,
                disable_notification=False
            )
            
            if not forwarded_message:
                return {"success": False, "error": "转发消息失败"}
                
            logger.info(f"消息 {message.id} 成功转发到聊天 {chat_id}，新消息ID: {forwarded_message.id}")
            
            return {
                "success": True, 
                "message_id": forwarded_message.id,
                "chat_id": chat_id,
                "original_message_id": message.id,
                "original_chat_id": message.chat.id
            }
            
        except FloodWait as e:
            logger.warning(f"转发受限，等待 {e.value} 秒")
            await asyncio.sleep(e.value)
            return await self._handle_message_forward(data)
            
        except ChatWriteForbidden as e:
            error_msg = f"无权限向聊天 {chat_id} 发送消息: {str(e)}"
            logger.error(error_msg)
            return {"success": False, "error": error_msg}
            
        except Exception as e:
            error_msg = f"转发消息时出错: {str(e)}"
            logger.exception(error_msg)
            return {"success": False, "error": error_msg}
    
    async def _handle_app_shutdown(self, data: Dict[str, Any] = None) -> None:
        """
        处理应用关闭事件
        
        Args:
            data: 事件数据
        """
        await self.shutdown()
    
    async def _upload_media(
        self, 
        chat_id: Union[int, str], 
        media_info: Dict[str, Any], 
        original_message: Optional[Message] = None, 
        preserve_date: bool = False
    ) -> Dict[str, Any]:
        """
        上传媒体文件
        
        Args:
            chat_id: 目标聊天ID
            media_info: 媒体信息
            original_message: 原始消息
            preserve_date: 是否保留原始日期
            
        Returns:
            Dict[str, Any]: 上传结果
        """
        # 获取任务ID
        task_id = asyncio.current_task().get_name()
        
        # 更新活跃上传信息
        if task_id in self.active_uploads:
            self.active_uploads[task_id]["status"] = "uploading"
        
        # 定义进度回调
        async def progress_callback(current, total):
            if total > 0:
                progress = current / total
            else:
                progress = 0
                
            # 更新活跃上传信息
            if task_id in self.active_uploads:
                self.active_uploads[task_id]["progress"] = progress
                
            # 发布进度事件
            await self.event_bus.publish(events.MEDIA_UPLOAD_PROGRESS, {
                "task_id": task_id,
                "current": current,
                "total": total,
                "progress": progress,
                "chat_id": chat_id
            })
        
        try:
            media_type = media_info["media_type"]
            file_path = media_info["file_path"]
            caption = media_info.get("caption", "")
            
            # 准备上传参数
            upload_kwargs = {
                "chat_id": chat_id,
                "progress": progress_callback,
                "caption": caption
            }
            
            # 如果原始消息有字幕实体，保留它们
            if original_message and original_message.caption_entities:
                upload_kwargs["caption_entities"] = original_message.caption_entities
                
            # 如果需要保留原始日期
            if preserve_date and original_message:
                upload_kwargs["schedule_date"] = original_message.date
                
            logger.info(f"开始上传 {media_type} 到聊天 {chat_id}: {file_path}")
            
            # 根据媒体类型选择上传方法
            if media_type == "photo":
                sent_message = await self.client.send_photo(
                    **upload_kwargs,
                    photo=file_path
                )
            elif media_type == "video":
                # 如果有缩略图，也可以添加
                thumb = None
                if media_info.get("has_thumbnail") and original_message and original_message.video.thumbs:
                    # 可以考虑下载缩略图
                    pass
                    
                sent_message = await self.client.send_video(
                    **upload_kwargs,
                    video=file_path,
                    duration=media_info.get("duration"),
                    width=media_info.get("width"),
                    height=media_info.get("height"),
                    thumb=thumb,
                    supports_streaming=media_info.get("supports_streaming", True)
                )
            elif media_type == "audio":
                sent_message = await self.client.send_audio(
                    **upload_kwargs,
                    audio=file_path,
                    duration=media_info.get("duration"),
                    performer=media_info.get("performer"),
                    title=media_info.get("title")
                )
            elif media_type == "document":
                sent_message = await self.client.send_document(
                    **upload_kwargs,
                    document=file_path,
                    file_name=media_info.get("file_name")
                )
            elif media_type == "animation":
                sent_message = await self.client.send_animation(
                    **upload_kwargs,
                    animation=file_path,
                    duration=media_info.get("duration"),
                    width=media_info.get("width"),
                    height=media_info.get("height")
                )
            elif media_type == "voice":
                sent_message = await self.client.send_voice(
                    **upload_kwargs,
                    voice=file_path,
                    duration=media_info.get("duration")
                )
            elif media_type == "video_note":
                sent_message = await self.client.send_video_note(
                    **upload_kwargs,
                    video_note=file_path,
                    duration=media_info.get("duration"),
                    length=media_info.get("length", 0)
                )
            elif media_type == "sticker":
                # 移除进度回调和字幕，贴纸不支持这些参数
                upload_kwargs.pop("progress", None)
                upload_kwargs.pop("caption", None)
                upload_kwargs.pop("caption_entities", None)
                
                sent_message = await self.client.send_sticker(
                    chat_id=chat_id,
                    sticker=file_path
                )
            else:
                # 未知媒体类型，作为文档发送
                sent_message = await self.client.send_document(
                    **upload_kwargs,
                    document=file_path
                )
            
            logger.info(f"上传 {media_type} 到聊天 {chat_id} 成功，消息ID: {sent_message.id}")
            
            # 更新活跃上传状态
            if task_id in self.active_uploads:
                self.active_uploads[task_id]["status"] = "completed"
                self.active_uploads[task_id]["progress"] = 1.0
                
            # 发布上传完成事件
            upload_result = {
                "success": True,
                "message_id": sent_message.id,
                "chat_id": chat_id,
                "media_type": media_type,
                "message": sent_message
            }
            
            await self.event_bus.publish(events.MEDIA_UPLOAD_COMPLETED, {
                "task_id": task_id,
                **upload_result
            })
            
            return upload_result
            
        except FloodWait as e:
            logger.warning(f"上传受限，等待 {e.value} 秒")
            
            # 更新活跃上传状态
            if task_id in self.active_uploads:
                self.active_uploads[task_id]["status"] = "waiting"
                
            # 等待
            await asyncio.sleep(e.value)
            
            # 重试
            return await self._upload_media(chat_id, media_info, original_message, preserve_date)
            
        except Exception as e:
            error_msg = f"上传媒体到聊天 {chat_id} 时出错: {str(e)}"
            logger.exception(error_msg)
            
            # 更新活跃上传状态
            if task_id in self.active_uploads:
                self.active_uploads[task_id]["status"] = "failed"
                
            # 发布上传失败事件
            await self.event_bus.publish(events.MEDIA_UPLOAD_FAILED, {
                "task_id": task_id,
                "chat_id": chat_id,
                "media_type": media_info["media_type"],
                "error": str(e)
            })
            
            return {"success": False, "error": str(e)}
    
    async def shutdown(self) -> None:
        """关闭插件"""
        logger.info("正在关闭上传插件...")
        
        # 取消事件订阅
        self.event_bus.unsubscribe(events.MEDIA_UPLOAD, self._handle_media_upload)
        self.event_bus.unsubscribe(events.MEDIA_UPLOAD_CANCEL, self._handle_media_upload_cancel)
        self.event_bus.unsubscribe(events.MEDIA_UPLOAD_STATUS, self._handle_media_upload_status)
        self.event_bus.unsubscribe(events.MESSAGE_FORWARD, self._handle_message_forward)
        self.event_bus.unsubscribe(events.APP_SHUTDOWN, self._handle_app_shutdown)
        
        self.client = None
        logger.info("上传插件已关闭")
```

## 任务2.10：实现入口程序(main.py)

最后，我们需要实现应用程序的入口点：

```python
# tg_app/main.py
import os
import sys
import asyncio
import argparse

from tg_app.core.application import Application
from tg_app.utils.logger import setup_logger, get_logger

# 获取日志记录器
logger = get_logger("main")

def setup_environment():
    """设置环境变量"""
    # 确保程序目录存在于系统路径中
    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    if base_dir not in sys.path:
        sys.path.insert(0, base_dir)
        
    # 确保配置目录存在
    config_dir = os.path.join(base_dir, "config")
    os.makedirs(config_dir, exist_ok=True)
    
    # 确保日志目录存在
    log_dir = os.path.join(base_dir, "logs")
    os.makedirs(log_dir, exist_ok=True)
    
    # 确保下载目录存在
    download_dir = os.path.join(base_dir, "downloads")
    os.makedirs(download_dir, exist_ok=True)
    
    # 确保会话目录存在
    sessions_dir = os.path.join(base_dir, "sessions")
    os.makedirs(sessions_dir, exist_ok=True)

def parse_arguments():
    """解析命令行参数"""
    parser = argparse.ArgumentParser(description="Telegram频道消息转发工具")
    
    parser.add_argument(
        "-c", "--config", 
        dest="config_path",
        default="config/default_config.ini",
        help="配置文件路径 (默认: config/default_config.ini)"
    )
    
    parser.add_argument(
        "--verbose", 
        action="store_true",
        help="启用详细日志输出"
    )
    
    return parser.parse_args()

async def main():
    """主函数"""
    # 解析命令行参数
    args = parse_arguments()
    
    # 设置环境
    setup_environment()
    
    # 设置初始日志配置
    log_level = "DEBUG" if args.verbose else "INFO"
    setup_logger({"level": log_level, "file_path": "logs/tg_app.log"})
    
    logger.info("正在启动Telegram转发工具...")
    
    try:
        # 创建应用实例
        app = Application()
        
        # 初始化应用
        if not await app.initialize(args.config_path):
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
            
    except KeyboardInterrupt:
        logger.info("收到中断信号，正在关闭...")
        return 0
        
    except Exception as e:
        logger.exception(f"运行应用程序时出错: {str(e)}")
        return 1
        
    finally:
        if 'app' in locals():
            await app.shutdown()
        logger.info("应用程序已关闭")

if __name__ == "__main__":
    # 设置事件循环策略
    if sys.platform == "win32":
        # Windows平台使用ProactorEventLoop
        asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())
        
    # 运行主函数
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
```

## 开发说明

1. **上传插件**:
   - 实现了媒体文件上传功能，支持所有Telegram媒体类型
   - 提供上传进度跟踪和状态查询
   - 通过任务队列管理并发上传
   - 针对各种媒体类型进行优化，设置适当的参数

2. **入口程序**:
   - 提供应用程序的入口点
   - 设置环境变量和目录结构
   - 解析命令行参数
   - 初始化和运行应用
   - 优雅地处理异常和关闭 