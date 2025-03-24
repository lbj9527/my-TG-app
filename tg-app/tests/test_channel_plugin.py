import asyncio
import sys
import os
import traceback
import signal

# 添加项目根目录到Python路径
current_dir = os.path.dirname(os.path.abspath(__file__))
parent_dir = os.path.dirname(current_dir)  # tg-app目录
sys.path.insert(0, parent_dir)
print(f"添加项目根目录到路径: {parent_dir}")
print(f"Python路径: {sys.path}")

try:
    # ConfigManager中缺少asyncio导入的补丁
    import core.config_manager
    import asyncio as asyncio_module
    core.config_manager.asyncio = asyncio_module
    
    from core.event_bus import EventBus
    from core.config_manager import ConfigManager
    from events import event_types as events
    from plugins.client import ClientPlugin
    from plugins.utils import ChannelPlugin
    from utils.logger import get_logger

    # 获取日志记录器
    logger = get_logger("test_channel")

    # 设置配置文件路径
    CONFIG_FILE = os.path.join(parent_dir, "config", "config.ini")
    print(f"配置文件路径: {CONFIG_FILE}")
    
    # 创建必要的目录
    SESSIONS_DIR = os.path.join(parent_dir, "sessions")
    if not os.path.exists(SESSIONS_DIR):
        os.makedirs(SESSIONS_DIR)
        print(f"创建会话目录: {SESSIONS_DIR}")
    else:
        print(f"会话目录已存在: {SESSIONS_DIR}")
    
    # 确保 sessions 目录有写权限
    if not os.access(SESSIONS_DIR, os.W_OK):
        print(f"警告: 会话目录没有写权限: {SESSIONS_DIR}")

    async def test_channel_plugin():
        """测试频道工具插件的基本功能"""
        logger.info("开始测试频道工具插件...")
        
        try:
            # 初始化事件总线
            event_bus = EventBus()
            logger.info("事件总线初始化完成")
            
            # 初始化配置管理器
            config_manager = ConfigManager(event_bus)
            # 加载配置文件
            success = config_manager.load_config(CONFIG_FILE, "user")
            if success:
                logger.info("配置加载成功")
            else:
                logger.error("配置加载失败")
                return
            
            # 注册配置事件处理器
            async def handle_get_config(data):
                section = data.get('section')
                if not section:
                    return {"success": False, "error": "未指定配置节"}
                
                config_data = config_manager.get_section(section)
                
                # 为客户端配置设置会话目录
                if section == "client":
                    logger.info("获取客户端配置")
                    config_data["work_dir"] = SESSIONS_DIR
                    logger.info(f"会话目录设置为: {SESSIONS_DIR}")
                
                return {"success": True, "data": config_data}
            
            event_bus.subscribe(events.CONFIG_GET_SECTION, handle_get_config)
            logger.info("配置事件处理器注册完成")
            
            # 创建并初始化客户端插件
            client_plugin = ClientPlugin(event_bus)
            await client_plugin.initialize()
            logger.info("客户端插件初始化完成")
            
            # 连接到Telegram
            logger.info("正在连接到Telegram...")
            connect_result = await client_plugin.connect()
            
            if not connect_result.get("success", False):
                logger.error(f"连接Telegram失败: {connect_result.get('error', '未知错误')}")
                return
                
            logger.info("已连接到Telegram")
            
            # 客户端实例获取处理器
            async def handle_get_client(data):
                client = await client_plugin.get_client()
                return {"success": True, "client": client}
            
            event_bus.subscribe(events.CLIENT_GET_INSTANCE, handle_get_client)
            logger.info("客户端实例获取处理器注册完成")
            
            # 创建并初始化频道工具插件
            channel_plugin = ChannelPlugin(event_bus)
            await channel_plugin.initialize()
            logger.info("频道工具插件初始化完成")
            
            # 测试频道解析
            # 使用公开频道进行测试
            test_channels = ["https://t.me/xgyvcu", "https://t.me/+JvLn20QQesE4M2Ux", "https://t.me/+GsKs6Y_IbpxiYzQx", "https://t.me/c/2320594305"]
            
            for channel in test_channels:
                logger.info(f"\n测试解析频道: {channel}")
                
                # 解析频道
                parse_result = await event_bus.publish_and_wait(
                    events.CHANNEL_PARSE,
                    {"channel": channel}
                )
                
                if parse_result and parse_result.get("success", False):
                    entity = parse_result.get("entity")
                    logger.info(f"频道解析成功:")
                    logger.info(f"  ID: {entity.id}")
                    logger.info(f"  标题: {entity.title}")
                    logger.info(f"  类型: {entity.type}")
                    logger.info(f"  用户名: {entity.username}")
                    
                    # 获取频道详细信息
                    info_result = await event_bus.publish_and_wait(
                        events.CHANNEL_GET_INFO,
                        {"channel": channel}
                    )
                    
                    if info_result and info_result.get("success", False):
                        info = info_result.get("info", {})
                        logger.info(f"频道信息获取成功:")
                        logger.info(f"  ID: {info.get('id')}")
                        logger.info(f"  标题: {info.get('title')}")
                        logger.info(f"  类型: {info.get('type')}")
                        logger.info(f"  用户名: {info.get('username')}")
                        logger.info(f"  描述: {info.get('description')}")
                        logger.info(f"  成员数: {info.get('members_count')}")
                        logger.info(f"  已验证: {info.get('is_verified')}")
                        logger.info(f"  受限制: {info.get('is_restricted')}")
                        logger.info(f"  是诈骗: {info.get('is_scam')}")
                        logger.info(f"  是虚假: {info.get('is_fake')}")
                    else:
                        logger.error(f"获取频道信息失败: {info_result.get('error', '未知错误')}")
                    
                    # 检查访问权限
                    access_result = await event_bus.publish_and_wait(
                        events.CHANNEL_CHECK_ACCESS,
                        {"channel": channel}
                    )
                    
                    if access_result and access_result.get("success", False):
                        logger.info(f"频道访问权限检查成功:")
                        logger.info(f"  有访问权限: {access_result.get('has_access', False)}")
                        logger.info(f"  有读权限: {access_result.get('has_read_access', False)}")
                        logger.info(f"  有写权限: {access_result.get('has_write_access', False)}")
                        
                        # 如果有读权限，尝试获取消息
                        if access_result.get("has_read_access", False):
                            messages_result = await event_bus.publish_and_wait(
                                events.MESSAGE_GET_FROM_CHANNEL,
                                {
                                    "chat_id": entity.id,
                                    "limit": 5  # 仅获取少量消息用于测试
                                }
                            )
                            
                            if messages_result and messages_result.get("success", False):
                                messages = messages_result.get("messages", [])
                                logger.info(f"获取消息成功，共 {len(messages)} 条消息:")
                                
                                for i, message in enumerate(messages[:3]):  # 仅显示前3条
                                    logger.info(f"  消息 {i+1}:")
                                    logger.info(f"    ID: {message.id}")
                                    logger.info(f"    日期: {message.date}")
                                    logger.info(f"    内容: {message.text[:50] + '...' if len(message.text or '') > 50 else message.text}")
                            else:
                                logger.error(f"获取消息失败: {messages_result.get('error', '未知错误')}")
                    else:
                        logger.error(f"频道访问权限检查失败: {access_result.get('error', '未知错误')}")
                else:
                    logger.error(f"频道解析失败: {parse_result.get('error', '未知错误')}")
            
            # 测试无效频道解析
            invalid_channel = "@this_channel_does_not_exist_12345"
            logger.info(f"\n测试解析无效频道: {invalid_channel}")
            
            invalid_result = await event_bus.publish_and_wait(
                events.CHANNEL_PARSE,
                {"channel": invalid_channel}
            )
            
            if not invalid_result or not invalid_result.get("success", False):
                logger.info(f"成功处理无效频道: {invalid_result.get('error', '未知错误')}")
            else:
                logger.error("无效频道解析应该失败，但成功了")
                
            # 关闭插件
            logger.info("\n关闭插件...")
            await channel_plugin.shutdown()
            logger.info("频道工具插件已关闭")
            
            # 断开客户端连接
            await client_plugin.disconnect()
            await client_plugin.shutdown()
            logger.info("客户端插件已关闭")
            
        except Exception as e:
            logger.error(f"测试过程中出错: {str(e)}")
            traceback.print_exc()
        finally:
            # 如果还有运行中的任务，尝试取消
            for task in asyncio.all_tasks():
                if task is not asyncio.current_task():
                    task.cancel()
            
        logger.info("频道工具插件测试完成")

    # 处理中断信号
    def handle_interrupt():
        for task in asyncio.all_tasks():
            task.cancel()
        logger.info("收到中断信号，已取消所有任务")

    if __name__ == "__main__":
        # 注册信号处理
        try:
            signal.signal(signal.SIGINT, lambda s, f: handle_interrupt())
        except ValueError:
            # 在Windows上可能无法在子线程中设置信号处理器
            pass
            
        # 运行测试
        asyncio.run(test_channel_plugin())
except Exception as e:
    print(f"导入模块时出错: {str(e)}")
    traceback.print_exc() 