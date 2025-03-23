"""
应用程序主类模块。

本模块定义应用程序的主类，作为应用的入口点和核心控制器。
应用程序类负责管理应用的生命周期，协调各个核心组件的运行。
"""

import asyncio
import signal
import sys
import time
from typing import Dict, Any, Optional, List, Set, Callable

# 修改导入语句
from core.context import ApplicationContext
from events.event_types import APP_ERROR, create_event_data
from utils.logger import get_logger

# 获取日志记录器
logger = get_logger("application")


class Application:
    """
    应用程序主类，作为应用的入口点和核心控制器。
    
    管理应用的生命周期，协调各个核心组件的运行。
    """
    
    def __init__(self):
        """初始化应用程序"""
        self.context = ApplicationContext.get_instance()
        self.running = False
        self.exit_code = 0
        
        # 注册信号处理
        self._setup_signal_handlers()
        
        logger.debug("应用程序已初始化")
    
    def _setup_signal_handlers(self) -> None:
        """设置信号处理器"""
        # 忽略 SIGPIPE 信号，防止在管道关闭时崩溃
        if hasattr(signal, 'SIGPIPE'):
            signal.signal(signal.SIGPIPE, signal.SIG_IGN)
        
        # 注册 SIGINT 和 SIGTERM 信号处理器
        if hasattr(signal, 'SIGINT'):
            signal.signal(signal.SIGINT, self._handle_exit_signal)
        if hasattr(signal, 'SIGTERM'):
            signal.signal(signal.SIGTERM, self._handle_exit_signal)
    
    def _handle_exit_signal(self, sig, frame) -> None:
        """
        处理退出信号。
        
        Args:
            sig: 信号
            frame: 栈帧
        """
        signal_name = signal.Signals(sig).name if hasattr(signal, 'Signals') else str(sig)
        logger.info(f"收到退出信号: {signal_name}")
        
        # 设置退出代码
        self.exit_code = 128 + sig
        
        # 停止应用
        if self.running:
            logger.debug("触发应用停止流程")
            asyncio.create_task(self.stop())
    
    async def run(self) -> int:
        """
        运行应用程序。
        
        Returns:
            int: 退出代码
        """
        if self.running:
            logger.warning("应用程序已经在运行")
            return self.exit_code
        
        logger.info("启动应用程序")
        start_time = time.time()
        
        try:
            # 初始化应用上下文
            if not await self.context.initialize():
                logger.error("初始化应用上下文失败")
                return 1
            
            # 启动应用
            if not await self.context.start():
                logger.error("启动应用失败")
                return 1
            
            # 标记为运行中
            self.running = True
            
            # 启动完成
            startup_time = time.time() - start_time
            logger.info(f"应用程序启动完成，耗时 {startup_time:.2f} 秒")
            
            # 运行主循环，等待停止信号
            await self._run_main_loop()
            
            return self.exit_code
            
        except Exception as e:
            logger.error(f"运行应用程序时出错: {str(e)}")
            
            # 发布应用错误事件
            if self.context.event_bus:
                event_data = create_event_data(APP_ERROR, error=str(e))
                await self.context.event_bus.publish(APP_ERROR, event_data)
            
            return 1
            
        finally:
            # 确保应用关闭
            if self.running:
                await self.stop()
    
    async def _run_main_loop(self) -> None:
        """运行主循环，等待停止信号"""
        try:
            # 创建一个无限期的future，直到取消
            stop_future = asyncio.Future()
            
            # 保存future，以便在stop()中取消
            self.context.set_shared_state("stop_future", stop_future)
            
            # 等待future被取消
            await stop_future
            
        except asyncio.CancelledError:
            logger.debug("主循环被取消")
            
        except Exception as e:
            logger.error(f"主循环中出错: {str(e)}")
            
            # 发布应用错误事件
            if self.context.event_bus:
                event_data = create_event_data(APP_ERROR, error=str(e))
                await self.context.event_bus.publish(APP_ERROR, event_data)
            
            # 设置退出代码
            self.exit_code = 1
    
    async def stop(self) -> None:
        """停止应用程序"""
        if not self.running:
            logger.warning("应用程序未运行")
            return
        
        logger.info("停止应用程序")
        
        # 取消停止future，结束主循环
        stop_future = self.context.get_shared_state("stop_future")
        if stop_future and not stop_future.done():
            stop_future.cancel()
        
        # 关闭应用上下文
        await self.context.shutdown()
        
        # 标记为未运行
        self.running = False
        logger.info("应用程序已停止")
    
    async def restart(self) -> int:
        """
        重启应用程序。
        
        Returns:
            int: 退出代码
        """
        logger.info("重启应用程序")
        
        # 停止当前实例
        if self.running:
            await self.stop()
        
        # 重新启动
        return await self.run()


def create_application() -> Application:
    """
    创建应用程序实例。
    
    Returns:
        Application: 应用程序实例
    """
    return Application()


def run_application() -> int:
    """
    运行应用程序，封装异步运行。
    
    Returns:
        int: 退出代码
    """
    app = create_application()
    
    try:
        # 使用事件循环运行应用
        if sys.platform == 'win32':
            # Windows平台需要使用特定的事件循环策略
            asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
        
        loop = asyncio.get_event_loop()
        return loop.run_until_complete(app.run())
        
    except KeyboardInterrupt:
        logger.info("用户中断，退出应用")
        return 130  # 128 + SIGINT(2)
        
    except Exception as e:
        logger.error(f"运行应用程序时出现未捕获的异常: {str(e)}")
        return 1 