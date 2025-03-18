"""
Telegram客户端管理工具
"""

import time
import asyncio
import random
from typing import Dict, Any, Optional, Callable

from pyrogram import Client
from pyrogram.errors import FloodWait, InternalServerError, Unauthorized

from tg_forwarder.utils.logger import get_logger

# 获取日志记录器
logger = get_logger("client_manager")


class TelegramClientManager:
    """Telegram客户端管理器"""
    
    def __init__(self, api_id: int, api_hash: str, session_name: str = "media_uploader_temp",
                 proxy_config: Optional[Dict[str, Any]] = None):
        """
        初始化客户端管理器
        
        Args:
            api_id: Telegram API ID
            api_hash: Telegram API Hash
            session_name: 会话名称
            proxy_config: 代理配置（可选）
        """
        self.api_id = api_id
        self.api_hash = api_hash
        # 确保session_name不为None
        self.session_name = session_name if session_name else "media_uploader_temp"
        self.proxy_config = proxy_config
        
        # 客户端实例
        self.client = None
        
        # 客户端状态
        self.initialized = False
        self.last_activity = 0
        self.health_check_interval = 300  # 健康检查间隔（秒）
        self.reconnect_attempts = 0
        self.max_reconnect_attempts = 5
        
        # 健康检查任务
        self._health_check_task = None
    
    async def initialize(self, force: bool = False) -> bool:
        """
        初始化客户端
        
        Args:
            force: 是否强制重新初始化
            
        Returns:
            bool: 初始化是否成功
        """
        if self.initialized and not force:
            logger.debug("客户端已经初始化")
            return True
        
        # 如果有现有客户端，先关闭
        if self.client:
            await self.shutdown()
        
        logger.info("创建新的Telegram客户端")
        
        try:
            # 创建客户端
            self.client = Client(
                self.session_name,
                api_id=self.api_id,
                api_hash=self.api_hash,
                in_memory=False,
                app_version="TG Forwarder Temp Client v1.0",
                device_model="PC",
                system_version="Windows"
            )
            
            # 设置代理
            if self.proxy_config:
                proxy_type = self.proxy_config.get('scheme', 'SOCKS5').upper()
                if not proxy_type and 'proxy_type' in self.proxy_config:
                    proxy_type = self.proxy_config.get('proxy_type', 'SOCKS5').upper()
                
                # 确保代理参数不为None
                hostname = self.proxy_config.get('hostname')
                if not hostname and 'addr' in self.proxy_config:
                    hostname = self.proxy_config.get('addr')
                
                port = self.proxy_config.get('port')
                
                if hostname and port:
                    self.client.proxy = {
                        'scheme': proxy_type,
                        'hostname': hostname,
                        'port': port
                    }
                    
                    if 'username' in self.proxy_config and self.proxy_config['username']:
                        self.client.proxy['username'] = self.proxy_config['username']
                    
                    if 'password' in self.proxy_config and self.proxy_config['password']:
                        self.client.proxy['password'] = self.proxy_config['password']
                else:
                    logger.warning(f"代理配置不完整，跳过代理设置: {self.proxy_config}")
            
            # 启动客户端
            await self.client.start()
            
            # 验证客户端状态
            me = await self.client.get_me()
            if me:
                logger.info(f"客户端成功连接到账号: {me.first_name} {me.last_name or ''}")
                self.initialized = True
                self.last_activity = time.time()
                self.reconnect_attempts = 0
                
                # 启动健康检查
                self.start_health_check()
                
                return True
            else:
                logger.warning("客户端创建成功但无法获取用户信息")
                self.initialized = False
                return False
                
        except Exception as e:
            logger.error(f"初始化客户端时出错: {str(e)}")
            self.initialized = False
            return False
    
    async def shutdown(self) -> None:
        """关闭客户端并释放资源"""
        # 停止健康检查
        self.stop_health_check()
        
        if self.client:
            try:
                # 检查客户端是否已经终止
                if hasattr(self.client, "is_connected") and callable(self.client.is_connected):
                    if await self.client.is_connected():
                        await self.client.stop()
                        logger.info("客户端已关闭")
                    else:
                        logger.debug("客户端已经断开连接，无需关闭")
                else:
                    # 尝试直接关闭，可能会抛出异常
                    try:
                        await self.client.stop()
                        logger.info("客户端已关闭")
                    except Exception as e:
                        logger.debug(f"关闭客户端时出现可忽略的错误: {str(e)}")
            except Exception as e:
                logger.error(f"关闭客户端时出错: {str(e)}")
            finally:
                self.client = None
                self.initialized = False
    
    def start_health_check(self) -> None:
        """启动健康检查任务"""
        if self._health_check_task is None or self._health_check_task.done():
            self._health_check_task = asyncio.create_task(self._health_check_loop())
            logger.debug("启动客户端健康检查任务")
    
    def stop_health_check(self) -> None:
        """停止健康检查任务"""
        if self._health_check_task and not self._health_check_task.done():
            self._health_check_task.cancel()
            logger.debug("停止客户端健康检查任务")
    
    async def _health_check_loop(self) -> None:
        """健康检查循环"""
        try:
            while True:
                # 等待一段时间
                await asyncio.sleep(self.health_check_interval)
                
                # 检查是否需要进行健康检查
                current_time = time.time()
                if current_time - self.last_activity > self.health_check_interval:
                    # 执行健康检查
                    try:
                        healthy = await self._check_client_health()
                        if not healthy:
                            # 客户端不健康，尝试重连
                            if self.reconnect_attempts < self.max_reconnect_attempts:
                                await self._reconnect()
                            else:
                                logger.error(f"客户端重连失败达到最大次数 ({self.max_reconnect_attempts})，停止重连")
                        else:
                            # 重置重连计数
                            self.reconnect_attempts = 0
                    except Exception as e:
                        logger.error(f"健康检查过程中出错: {str(e)}")
        except asyncio.CancelledError:
            logger.debug("健康检查任务被取消")
        except Exception as e:
            logger.error(f"健康检查循环出错: {str(e)}")
    
    async def _check_client_health(self) -> bool:
        """
        检查客户端健康状态
        
        Returns:
            bool: 客户端是否健康
        """
        if not self.client or not self.initialized:
            return False
        
        try:
            # 检查是否已连接
            if hasattr(self.client, "is_connected") and callable(self.client.is_connected):
                if not await self.client.is_connected():
                    logger.warning("客户端已断开连接")
                    return False
            
            # 发送一个简单的请求
            me = await self.client.get_me()
            if me:
                logger.debug("客户端健康检查通过")
                self.last_activity = time.time()
                return True
            return False
        except Unauthorized:
            logger.warning("客户端授权已失效")
            return False
        except (FloodWait, InternalServerError) as e:
            # 这些错误不代表客户端不健康
            logger.warning(f"健康检查遇到临时错误: {str(e)}")
            return True
        except Exception as e:
            logger.warning(f"客户端健康检查失败: {str(e)}")
            return False
    
    async def _reconnect(self) -> bool:
        """
        尝试重新连接客户端
        
        Returns:
            bool: 重连是否成功
        """
        self.reconnect_attempts += 1
        
        # 计算退避延迟
        delay = min(30, 2 ** self.reconnect_attempts)
        delay_with_jitter = delay * (0.5 + random.random())
        
        logger.info(f"尝试重新连接客户端 (第 {self.reconnect_attempts} 次), 等待 {delay_with_jitter:.1f} 秒...")
        
        # 等待一段时间
        await asyncio.sleep(delay_with_jitter)
        
        # 重新初始化客户端
        return await self.initialize(force=True)
    
    async def with_error_handling(self, func: Callable, *args, **kwargs) -> Any:
        """
        带错误处理的函数调用包装器
        
        Args:
            func: 要调用的函数
            args: 位置参数
            kwargs: 关键字参数
            
        Returns:
            Any: 函数返回值
        """
        max_retries = 3
        retry_count = 0
        
        while retry_count <= max_retries:
            try:
                # 更新最后活动时间
                self.last_activity = time.time()
                
                # 调用函数
                result = await func(*args, **kwargs)
                return result
                
            except FloodWait as e:
                wait_time = e.value
                logger.warning(f"触发频率限制，等待 {wait_time} 秒")
                await asyncio.sleep(wait_time)
                # 不计入重试次数
                continue
                
            except (InternalServerError, ConnectionError) as e:
                retry_count += 1
                if retry_count <= max_retries:
                    delay = 2 ** retry_count
                    logger.warning(f"服务器错误: {str(e)}，第 {retry_count}/{max_retries} 次重试，等待 {delay} 秒")
                    await asyncio.sleep(delay)
                else:
                    logger.error(f"达到最大重试次数，操作失败: {str(e)}")
                    raise
                    
            except Unauthorized:
                logger.error("客户端授权已失效，尝试重新连接")
                if await self._reconnect():
                    retry_count += 1
                    continue
                else:
                    raise
                    
            except Exception as e:
                logger.error(f"操作出错: {str(e)}")
                raise 