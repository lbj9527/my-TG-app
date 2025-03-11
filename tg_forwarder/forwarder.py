"""
消息转发模块，负责转发消息的主要逻辑
"""

import asyncio
import time
import os
from typing import Dict, Any, Optional, List, Union, Tuple
from collections import defaultdict
from pyrogram.types import Message, InputMediaPhoto, InputMediaVideo, InputMediaDocument
from pyrogram.errors import FloodWait

from tg_forwarder.utils.logger import get_logger
from tg_forwarder.channel_parser import ChannelParser
from tg_forwarder.media_handler import MediaHandler

logger = get_logger("forwarder")

class MessageForwarder:
    """消息转发类，负责消息转发的主要逻辑"""
    
    def __init__(self, client, config: Dict[str, Any], media_handler: MediaHandler):
        """
        初始化消息转发器
        
        Args:
            client: Telegram客户端实例
            config: 转发配置信息
            media_handler: 媒体处理器实例
        """
        self.client = client
        self.config = config
        self.media_handler = media_handler
        
        self.start_message_id = config.get('start_message_id', 0)
        self.end_message_id = config.get('end_message_id', 0)
        self.hide_author = config.get('hide_author', False)
        self.delay = config.get('delay', 1)
        self.batch_size = config.get('batch_size', 100)
    
    async def forward_message(self, source_message: Message, target_channels: List[Union[str, int]]) -> Dict[str, List[Optional[Message]]]:
        """
        转发单条消息到多个目标频道
        
        Args:
            source_message: 源消息对象
            target_channels: 目标频道列表
        
        Returns:
            Dict[str, List[Optional[Message]]]: 转发结果，格式为 {target_channel: [forwarded_message, ...]}
        """
        results = defaultdict(list)
        
        for target in target_channels:
            try:
                # 第一层：优先尝试直接转发，这样可以保持原始格式
                forwarded = None
                try:
                    # 确保 target ID 格式正确
                    target_id = target
                    if isinstance(target, str) and target.startswith('-100'):
                        try:
                            target_id = int(target)
                        except ValueError:
                            pass
                            
                    # 如果需要隐藏作者，使用copy_message替代forward
                    if self.hide_author:
                        # 使用copy_message方法可以复制消息而不显示来源
                        client_to_use = self.client.client if hasattr(self.client, 'client') else self.client
                        
                        # 获取消息内容
                        caption = source_message.caption
                        
                        # 复制消息
                        forwarded = await client_to_use.copy_message(
                            chat_id=target_id,
                            from_chat_id=source_message.chat.id,
                            message_id=source_message.id,
                            caption=caption,  # 保持原始标题
                            disable_notification=True
                        )
                    else:
                        # 直接转发，保持原始格式
                        forwarded = await source_message.forward(target_id)
                    
                    if forwarded:
                        logger.info(f"消息 {source_message.id} 成功转发到 {target}")
                        results[str(target)].append(forwarded)
                        # 如果第一层成功，直接进入下一个目标频道
                        await asyncio.sleep(self.delay)
                        continue
                    
                except ValueError as ve:
                    logger.error(f"无效的频道ID格式: {target}, 错误: {str(ve)}")
                    # 尝试使用原始格式
                    if target_id != target:
                        logger.info(f"尝试使用原始格式发送到: {target}")
                        try:
                            client_to_use = self.client.client if hasattr(self.client, 'client') else self.client
                            
                            if self.hide_author:
                                # 使用copy_message方法隐藏来源
                                forwarded = await client_to_use.copy_message(
                                    chat_id=target,
                                    from_chat_id=source_message.chat.id,
                                    message_id=source_message.id,
                                    caption=source_message.caption,
                                    disable_notification=True
                                )
                            else:
                                forwarded = await source_message.forward(target)
                                
                            if forwarded:
                                logger.info(f"使用原始格式成功转发消息 {source_message.id} 到 {target}")
                                results[str(target)].append(forwarded)
                                await asyncio.sleep(self.delay)
                                continue
                        except Exception as inner_err:
                            logger.warning(f"使用原始格式转发消息 {source_message.id} 到 {target} 失败: {str(inner_err)}")
                            # 继续尝试第二层
                
                except Exception as e:
                    logger.warning(f"直接转发消息 {source_message.id} 到 {target} 失败: {str(e)}")
                    # 继续尝试第二层
                
                # 第二层：如果直接转发失败，尝试下载媒体后重新发送
                if source_message.media and not forwarded:
                    try:
                        logger.info(f"尝试下载并重新发送消息 {source_message.id} 到 {target}")
                        
                        # 下载文件
                        file_path = await self.media_handler.download_media(source_message)
                        if not file_path:
                            logger.warning(f"无法下载消息 {source_message.id} 的媒体文件")
                            await asyncio.sleep(self.delay)
                            continue
                        
                        # 根据媒体类型发送
                        try:
                            media_type = self.media_handler._get_media_type(source_message)
                            caption = source_message.caption
                            
                            # 检查client引用是否正确，通常只需要一层client
                            client_to_use = self.client.client if hasattr(self.client, 'client') else self.client
                            
                            # 确保 target ID 格式正确
                            target_id = target
                            if isinstance(target, str) and target.startswith('-100'):
                                try:
                                    target_id = int(target)
                                except ValueError:
                                    pass
                            
                            try:
                                if media_type == "photo":
                                    sent = await client_to_use.send_photo(
                                        chat_id=target_id,
                                        photo=file_path,
                                        caption=caption
                                    )
                                elif media_type == "video":
                                    sent = await client_to_use.send_video(
                                        chat_id=target_id,
                                        video=file_path,
                                        caption=caption
                                    )
                                elif media_type == "audio":
                                    sent = await client_to_use.send_audio(
                                        chat_id=target_id,
                                        audio=file_path,
                                        caption=caption
                                    )
                                elif media_type == "document":
                                    sent = await client_to_use.send_document(
                                        chat_id=target_id,
                                        document=file_path,
                                        caption=caption
                                    )
                                else:
                                    logger.warning(f"跳过不支持的媒体类型: {media_type}")
                                    continue
                                
                                if sent:
                                    results[str(target)].append(sent)
                                    logger.info(f"成功发送媒体消息 {source_message.id} 到 {target}")
                            
                            except ValueError as ve:
                                logger.error(f"无效的频道ID格式: {target}, 错误: {str(ve)}")
                                # 尝试使用原始格式
                                if target_id != target:
                                    logger.info(f"尝试使用原始格式发送到: {target}")
                                    if media_type == "photo":
                                        sent = await client_to_use.send_photo(
                                            chat_id=target,
                                            photo=file_path,
                                            caption=caption
                                        )
                                    elif media_type == "video":
                                        sent = await client_to_use.send_video(
                                            chat_id=target,
                                            video=file_path,
                                            caption=caption
                                        )
                                    elif media_type == "audio":
                                        sent = await client_to_use.send_audio(
                                            chat_id=target,
                                            audio=file_path,
                                            caption=caption
                                        )
                                    elif media_type == "document":
                                        sent = await client_to_use.send_document(
                                            chat_id=target,
                                            document=file_path,
                                            caption=caption
                                        )
                                    else:
                                        logger.warning(f"跳过不支持的媒体类型: {media_type}")
                                        continue
                                        
                                    if sent:
                                        results[str(target)].append(sent)
                                        logger.info(f"使用原始格式成功发送媒体消息 {source_message.id} 到 {target}")
                            
                            except Exception as send_err:
                                logger.warning(f"发送媒体消息 {source_message.id} 到 {target} 失败: {str(send_err)}")
                        
                        except Exception as send_err:
                            logger.warning(f"发送媒体消息 {source_message.id} 到 {target} 失败: {str(send_err)}")
                        
                        finally:
                            # 清理临时文件
                            if file_path and os.path.exists(file_path):
                                try:
                                    os.remove(file_path)
                                except Exception:
                                    pass
                    
                    except Exception as media_err:
                        logger.error(f"处理媒体消息 {source_message.id} 失败: {str(media_err)}")
                
                # 如果是纯文本消息且直接转发失败
                elif not source_message.media and not forwarded:
                    try:
                        # 检查client引用是否正确，通常只需要一层client
                        client_to_use = self.client.client if hasattr(self.client, 'client') else self.client
                        
                        # 确保 target ID 格式正确
                        target_id = target
                        if isinstance(target, str) and target.startswith('-100'):
                            try:
                                target_id = int(target)
                            except ValueError:
                                pass
                        
                        try:
                            # 重新发送纯文本
                            sent = await client_to_use.send_message(
                                chat_id=target_id,
                                text=source_message.text or "",
                                disable_web_page_preview=source_message.web_page is None
                            )
                            
                            if sent:
                                results[str(target)].append(sent)
                                logger.info(f"成功发送文本消息 {source_message.id} 到 {target}")
                        
                        except ValueError as ve:
                            logger.error(f"无效的频道ID格式: {target}, 错误: {str(ve)}")
                            # 尝试使用原始格式
                            if target_id != target:
                                logger.info(f"尝试使用原始格式发送到: {target}")
                                sent = await client_to_use.send_message(
                                    chat_id=target,
                                    text=source_message.text or "",
                                    disable_web_page_preview=source_message.web_page is None
                                )
                                
                                if sent:
                                    results[str(target)].append(sent)
                                    logger.info(f"使用原始格式成功发送文本消息 {source_message.id} 到 {target}")
                        
                        except Exception as text_err:
                            logger.warning(f"发送文本消息 {source_message.id} 到 {target} 失败: {str(text_err)}")
                    
                    except Exception as e:
                        logger.warning(f"处理文本消息 {source_message.id} 失败: {str(e)}")
                
                # 添加延迟，避免触发限流
                await asyncio.sleep(self.delay)
            
            except FloodWait as e:
                logger.warning(f"转发消息时触发Telegram限流，等待{e.value}秒...")
                await asyncio.sleep(e.value)
                # 递归重试
                try:
                    single_result = await self.forward_message(source_message, [target])
                    results.update(single_result)
                except Exception as retry_err:
                    logger.warning(f"重试转发消息 {source_message.id} 到 {target} 失败: {str(retry_err)}")
            
            except Exception as e:
                logger.error(f"转发消息 {source_message.id} 到 {target} 时出错: {str(e)}")
                logger.warning(f"跳过转发此消息到 {target}")
        
        return dict(results)
    
    async def forward_media_group(self, media_group: List[Message], target_channels: List[Union[str, int]]) -> Dict[str, List[Optional[Message]]]:
        """
        转发媒体组到多个目标频道
        
        Args:
            media_group: 媒体组消息列表
            target_channels: 目标频道列表
        
        Returns:
            Dict[str, List[Optional[Message]]]: 转发结果
        """
        results = defaultdict(list)
        
        for target in target_channels:
            try:
                # 第一层：优先尝试整体直接转发媒体组
                forwarded_messages = []
                
                try:
                    # 确保 target ID 格式正确
                    target_id = target
                    if isinstance(target, str) and target.startswith('-100'):
                        try:
                            target_id = int(target)
                        except ValueError:
                            pass
                    
                    # 检查client引用是否正确，通常只需要一层client
                    client_to_use = self.client.client if hasattr(self.client, 'client') else self.client
                    
                    # 如果需要隐藏作者，使用copy_media_group替代forward
                    if self.hide_author:
                        # 使用copy_media_group方法可以复制媒体组而不显示来源
                        try:
                            # 只需要提供媒体组中的一个消息ID，Pyrogram会自动获取整个组
                            forwarded_messages = await client_to_use.copy_media_group(
                                chat_id=target_id,
                                from_chat_id=media_group[0].chat.id,
                                message_id=media_group[0].id,
                                disable_notification=True
                            )
                            
                            if forwarded_messages:
                                logger.info(f"成功使用copy_media_group复制媒体组 {media_group[0].media_group_id} 到 {target} (共{len(forwarded_messages)}条)")
                                results[str(target)].extend(forwarded_messages)
                                await asyncio.sleep(self.delay)
                                continue
                        except Exception as copy_err:
                            logger.warning(f"使用copy_media_group复制媒体组 {media_group[0].media_group_id} 到 {target} 失败: {str(copy_err)}")
                            # 如果复制失败，会继续尝试下一种方法
                    else:
                        # 如果不需要隐藏作者，尝试直接转发整个媒体组
                        # 尝试一个一个转发消息（保持原格式）
                        for message in media_group:
                            try:
                                forwarded = await message.forward(target_id)
                                if forwarded:
                                    forwarded_messages.append(forwarded)
                                await asyncio.sleep(0.3)  # 添加短暂延迟防止限流
                            except Exception as msg_err:
                                logger.warning(f"转发媒体组中的单条消息 {message.id} 到 {target} 失败: {str(msg_err)}")
                                # 如果任何一条消息转发失败，则整个媒体组视为转发失败
                                forwarded_messages = []
                                break
                        
                        # 如果所有媒体都成功转发，则认为第一层转发成功
                        if forwarded_messages and len(forwarded_messages) == len(media_group):
                            logger.info(f"媒体组 {media_group[0].media_group_id} 全部成功直接转发到 {target}")
                            results[str(target)].extend(forwarded_messages)
                            await asyncio.sleep(self.delay)
                            continue
                    
                except ValueError as ve:
                    logger.error(f"无效的频道ID格式: {target}, 错误: {str(ve)}")
                    # 尝试使用原始格式
                    if target_id != target:
                        logger.info(f"尝试使用原始格式发送到: {target}")
                        try:
                            if self.hide_author:
                                # 使用原始格式尝试复制媒体组
                                forwarded_messages = await client_to_use.copy_media_group(
                                    chat_id=target,
                                    from_chat_id=media_group[0].chat.id,
                                    message_id=media_group[0].id,
                                    disable_notification=True
                                )
                                
                                if forwarded_messages:
                                    logger.info(f"成功使用原始格式复制媒体组 {media_group[0].media_group_id} 到 {target} (共{len(forwarded_messages)}条)")
                                    results[str(target)].extend(forwarded_messages)
                                    await asyncio.sleep(self.delay)
                                    continue
                            else:
                                # 直接转发模式下，再次尝试一个一个转发消息
                                for message in media_group:
                                    try:
                                        forwarded = await message.forward(target)
                                        if forwarded:
                                            forwarded_messages.append(forwarded)
                                        await asyncio.sleep(0.3)
                                    except Exception as msg_err:
                                        logger.warning(f"使用原始格式转发媒体组中的单条消息 {message.id} 到 {target} 失败: {str(msg_err)}")
                                        forwarded_messages = []
                                        break
                                
                                if forwarded_messages and len(forwarded_messages) == len(media_group):
                                    logger.info(f"使用原始格式成功转发媒体组 {media_group[0].media_group_id} 到 {target}")
                                    results[str(target)].extend(forwarded_messages)
                                    await asyncio.sleep(self.delay)
                                    continue
                        except Exception as inner_err:
                            logger.warning(f"使用原始格式复制媒体组 {media_group[0].media_group_id} 到 {target} 失败: {str(inner_err)}")
                            # 不抛出异常，继续使用下一种方法
                
                except Exception as e:
                    logger.warning(f"直接转发媒体组 {media_group[0].media_group_id} 到 {target} 失败: {str(e)}")
                    forwarded_messages = []
                
                # 第二层：如果直接转发失败或需要隐藏作者，尝试下载全部媒体并作为媒体组发送
                if not forwarded_messages:
                    logger.info(f"尝试下载并重新发送媒体组 {media_group[0].media_group_id} 到 {target}")
                    
                    # 收集所有媒体文件和信息
                    media_files = []
                    
                    for message in media_group:
                        try:
                            # 下载文件
                            file_path = await self.media_handler.download_media(message)
                            if not file_path:
                                logger.warning(f"无法下载媒体组中消息 {message.id} 的媒体文件")
                                continue
                            
                            media_type = self.media_handler._get_media_type(message)
                            caption = message.caption
                            
                            # 保存每个媒体的所有信息，包括其原始标题
                            media_files.append({
                                "file_path": file_path,
                                "media_type": media_type,
                                "caption": caption,  # 保存每个媒体的原始标题
                                "message_id": message.id
                            })
                        
                        except Exception as download_err:
                            logger.warning(f"下载媒体组中消息 {message.id} 失败: {str(download_err)}")
                    
                    # 如果成功下载了文件，尝试作为媒体组发送
                    if media_files:
                        try:
                            # 准备媒体对象列表
                            media_list = []
                            
                            for media_item in media_files:
                                file_path = media_item["file_path"]
                                media_type = media_item["media_type"]
                                item_caption = media_item["caption"]  # 使用每个媒体自己的标题
                                
                                if media_type == "photo":
                                    media_list.append(InputMediaPhoto(
                                        media=file_path,
                                        caption=item_caption
                                    ))
                                elif media_type == "video":
                                    media_list.append(InputMediaVideo(
                                        media=file_path,
                                        caption=item_caption
                                    ))
                                elif media_type == "document":
                                    media_list.append(InputMediaDocument(
                                        media=file_path,
                                        caption=item_caption
                                    ))
                            
                            # 发送媒体组
                            if media_list:
                                # 检查client引用是否正确，通常只需要一层client
                                client_to_use = self.client.client if hasattr(self.client, 'client') else self.client
                                
                                # 确保 target ID 格式正确
                                target_id = target
                                if isinstance(target, str) and target.startswith('-100'):
                                    try:
                                        target_id = int(target)
                                    except ValueError:
                                        pass
                                
                                try:
                                    sent_group = await client_to_use.send_media_group(
                                        chat_id=target_id,
                                        media=media_list
                                    )
                                    
                                    if sent_group:
                                        results[str(target)].extend(sent_group)
                                        logger.info(f"成功发送媒体组 {media_group[0].media_group_id} 到 {target} (共{len(sent_group)}条)")
                                except ValueError as ve:
                                    logger.error(f"无效的频道ID格式: {target}, 错误: {str(ve)}")
                                    # 尝试使用原始格式
                                    if target_id != target:
                                        logger.info(f"尝试使用原始格式发送到: {target}")
                                        try:
                                            sent_group = await client_to_use.send_media_group(
                                                chat_id=target,
                                                media=media_list
                                            )
                                            
                                            if sent_group:
                                                results[str(target)].extend(sent_group)
                                                logger.info(f"成功使用原始格式发送媒体组 {media_group[0].media_group_id} 到 {target} (共{len(sent_group)}条)")
                                        except Exception as inner_err:
                                            logger.error(f"使用原始格式发送到 {target} 失败: {str(inner_err)}")
                                            # 不抛出异常，继续使用下一种方法
                        
                        except Exception as send_err:
                            logger.warning(f"发送媒体组 {media_group[0].media_group_id} 到 {target} 失败: {str(send_err)}")
                            
                            # 如果发送媒体组失败，尝试一个一个发送
                            logger.info(f"尝试单独发送媒体组中的每个文件到 {target}")
                            sent_messages = []
                            
                            for media_item in media_files:
                                try:
                                    file_path = media_item["file_path"]
                                    media_type = media_item["media_type"]
                                    item_caption = media_item["caption"]  # 使用每个媒体自己的标题
                                    
                                    # 检查client引用是否正确，通常只需要一层client
                                    client_to_use = self.client.client if hasattr(self.client, 'client') else self.client
                                    
                                    # 确保 target ID 格式正确
                                    target_id = target
                                    if isinstance(target, str) and target.startswith('-100'):
                                        try:
                                            target_id = int(target)
                                        except ValueError:
                                            pass
                                    
                                    try:
                                        if media_type == "photo":
                                            sent = await client_to_use.send_photo(
                                                chat_id=target_id,
                                                photo=file_path,
                                                caption=item_caption
                                            )
                                        elif media_type == "video":
                                            sent = await client_to_use.send_video(
                                                chat_id=target_id,
                                                video=file_path,
                                                caption=item_caption
                                            )
                                        elif media_type == "audio":
                                            sent = await client_to_use.send_audio(
                                                chat_id=target_id,
                                                audio=file_path,
                                                caption=item_caption
                                            )
                                        elif media_type == "document":
                                            sent = await client_to_use.send_document(
                                                chat_id=target_id,
                                                document=file_path,
                                                caption=item_caption
                                            )
                                        else:
                                            logger.warning(f"跳过不支持的媒体类型: {media_type}")
                                            continue
                                    except ValueError as ve:
                                        logger.error(f"无效的频道ID格式: {target}, 错误: {str(ve)}")
                                        # 尝试使用原始格式
                                        if target_id != target:
                                            logger.info(f"尝试使用原始格式发送到: {target}")
                                            if media_type == "photo":
                                                sent = await client_to_use.send_photo(
                                                    chat_id=target,
                                                    photo=file_path,
                                                    caption=item_caption
                                                )
                                            elif media_type == "video":
                                                sent = await client_to_use.send_video(
                                                    chat_id=target,
                                                    video=file_path,
                                                    caption=item_caption
                                                )
                                            elif media_type == "audio":
                                                sent = await client_to_use.send_audio(
                                                    chat_id=target,
                                                    audio=file_path,
                                                    caption=item_caption
                                                )
                                            elif media_type == "document":
                                                sent = await client_to_use.send_document(
                                                    chat_id=target,
                                                    document=file_path,
                                                    caption=item_caption
                                                )
                                            else:
                                                logger.warning(f"跳过不支持的媒体类型: {media_type}")
                                                continue
                                    
                                    if sent:
                                        sent_messages.append(sent)
                                        logger.info(f"成功发送媒体组中第 {media_item['message_id']} 个文件到 {target}")
                                
                                except Exception as single_send_err:
                                    logger.warning(f"发送媒体组中第 {media_item['message_id']} 个文件到 {target} 失败: {str(single_send_err)}")
                                
                                # 添加短暂延迟防止限流
                                await asyncio.sleep(0.5)
                            
                            if sent_messages:
                                results[str(target)].extend(sent_messages)
                                logger.info(f"媒体组 {media_group[0].media_group_id} 部分发送成功: {len(sent_messages)}/{len(media_files)} 个文件")
                        
                        finally:
                            # 清理临时文件
                            for media_item in media_files:
                                file_path = media_item["file_path"]
                                if file_path and os.path.exists(file_path):
                                    try:
                                        os.remove(file_path)
                                    except Exception:
                                        pass
                
                # 添加延迟，避免触发限流
                await asyncio.sleep(self.delay)
            
            except FloodWait as e:
                logger.warning(f"转发媒体组时触发Telegram限流，等待{e.value}秒...")
                await asyncio.sleep(e.value)
                # 递归重试
                try:
                    single_result = await self.forward_media_group(media_group, [target])
                    results.update(single_result)
                except Exception as retry_err:
                    logger.warning(f"重试转发媒体组 {media_group[0].media_group_id} 到 {target} 失败: {str(retry_err)}")
            
            except Exception as e:
                logger.error(f"转发媒体组 {media_group[0].media_group_id} 到 {target} 时出错: {str(e)}")
                logger.warning(f"跳过此媒体组")
        
        return dict(results)
    
    async def process_messages(self, source_channel: Union[str, int], target_channels: List[Union[str, int]], 
                             start_id: Optional[int] = None, end_id: Optional[int] = None) -> Dict[str, Any]:
        """
        处理和转发消息
        
        Args:
            source_channel: 源频道
            target_channels: 目标频道列表
            start_id: 起始消息ID（可选）
            end_id: 结束消息ID（可选）
        
        Returns:
            Dict[str, Any]: 处理结果统计
        """
        # 使用配置中的值作为默认值
        start_id = start_id if start_id is not None else self.start_message_id
        end_id = end_id if end_id is not None else self.end_message_id
        
        # 如果没有指定结束ID，获取频道最新消息ID
        if end_id <= 0:
            latest_id = await self.client.get_latest_message_id(source_channel)
            if latest_id:
                end_id = latest_id
                logger.info(f"已获取最新消息ID: {end_id}")
            else:
                logger.error("无法获取最新消息ID")
                return {"success": False, "error": "无法获取最新消息ID"}
        
        # 如果起始ID为0，从1开始
        if start_id <= 0:
            start_id = 1
            logger.info(f"未指定起始消息ID，将从ID=1开始")
        
        logger.info(f"开始处理消息: 从 {start_id} 到 {end_id}")
        
        # 检查频道是否存在
        source_entity = await self.client.get_entity(source_channel)
        if not source_entity:
            logger.error(f"源频道不存在或无法访问: {source_channel}")
            return {"success": False, "error": f"源频道不存在或无法访问: {source_channel}"}
        
        # 检查目标频道是否存在
        valid_targets = []
        for target in target_channels:
            target_entity = await self.client.get_entity(target)
            if target_entity:
                valid_targets.append(target)
            else:
                logger.warning(f"目标频道不存在或无法访问: {target}")
        
        if not valid_targets:
            logger.error("没有有效的目标频道")
            return {"success": False, "error": "没有有效的目标频道"}
        
        # 开始批量获取和转发消息
        media_groups = {}  # 用于收集媒体组消息
        stats = {
            "total": end_id - start_id + 1,
            "processed": 0,
            "success": 0,
            "failed": 0,
            "media_groups": 0,
            "text_messages": 0,
            "media_messages": 0,
            "skipped": 0,
            "start_time": time.time()
        }
        
        # 获取消息
        messages = await self.client.get_messages_range(
            source_channel, start_id, end_id, self.batch_size
        )
        
        # 先对消息进行分组，将媒体组消息放在一起
        grouped_messages = []
        current_media_group = None
        
        for msg in messages:
            if msg is None:
                stats["skipped"] += 1
                continue
            
            if msg.media_group_id:
                if current_media_group and current_media_group[0].media_group_id == msg.media_group_id:
                    # 添加到当前媒体组
                    current_media_group.append(msg)
                else:
                    # 开始新的媒体组
                    if current_media_group:
                        grouped_messages.append(("media_group", current_media_group))
                    current_media_group = [msg]
            else:
                # 如果有未完成的媒体组，先添加它
                if current_media_group:
                    grouped_messages.append(("media_group", current_media_group))
                    current_media_group = None
                
                # 添加普通消息
                grouped_messages.append(("message", msg))
        
        # 添加最后一个媒体组（如果有）
        if current_media_group:
            grouped_messages.append(("media_group", current_media_group))
        
        # 处理分组后的消息
        for msg_type, msg_data in grouped_messages:
            try:
                if msg_type == "media_group":
                    # 转发媒体组
                    media_group = msg_data
                    result = await self.forward_media_group(media_group, valid_targets)
                    
                    success = any(bool(msgs) for msgs in result.values())
                    stats["processed"] += len(media_group)
                    if success:
                        stats["success"] += len(media_group)
                        stats["media_groups"] += 1
                    else:
                        stats["failed"] += len(media_group)
                    
                    # 更新媒体消息计数
                    stats["media_messages"] += len(media_group)
                
                else:
                    # 转发单条消息
                    message = msg_data
                    result = await self.forward_message(message, valid_targets)
                    
                    success = any(bool(msgs) for msgs in result.values())
                    stats["processed"] += 1
                    if success:
                        stats["success"] += 1
                    else:
                        stats["failed"] += 1
                    
                    # 更新消息类型计数
                    if message.media:
                        stats["media_messages"] += 1
                    else:
                        stats["text_messages"] += 1
                
                # 防止处理太快触发限流
                await asyncio.sleep(self.delay)
            
            except Exception as e:
                logger.error(f"处理消息时出错: {str(e)}")
                if msg_type == "media_group":
                    stats["failed"] += len(msg_data)
                    stats["processed"] += len(msg_data)
                else:
                    stats["failed"] += 1
                    stats["processed"] += 1
        
        # 计算总耗时
        stats["end_time"] = time.time()
        stats["duration"] = stats["end_time"] - stats["start_time"]
        stats["success"] = True
        
        logger.info(f"消息处理完成: 总数 {stats['total']}, 处理 {stats['processed']}, 成功 {stats['success']}, 失败 {stats['failed']}, 跳过 {stats['skipped']}")
        logger.info(f"耗时: {stats['duration']:.2f}秒")
        
        return stats