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
    from utils.logger import get_logger

    # 获取日志记录器
    logger = get_logger("test_client")

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

    # 打印配置信息的辅助函数
    def print_config_info(config_data, proxy_data=None):
        """打印配置信息，隐藏敏感数据"""
        print("\n=== 配置信息 ===")
        
        # 打印完整的配置数据(调试用)
        print("完整配置数据:")
        for key, value in config_data.items():
            if key in ["api_hash", "api_id", "phone_number"]:
                value_str = str(value)
                if value_str and len(value_str) > 4:
                    print(f"  {key}: {'*'*(len(value_str)-4)}{value_str[-4:]}")
                else:
                    print(f"  {key}: {'*' * 6 if value_str else '未设置'}")
            else:
                print(f"  {key}: {value}")
        
        # 打印API信息
        if "api_id" in config_data:
            api_id = config_data["api_id"]
            if api_id:
                print(f"API ID: {'*'*(len(str(api_id))-2) + str(api_id)[-2:]}")
                print(f"API ID类型: {type(api_id)}")
            else:
                print("API ID: 未设置")
        else:
            print("API ID: 未设置")
            
        if "api_hash" in config_data:
            hash_value = config_data["api_hash"]
            if hash_value:
                print(f"API Hash: {'*'*(len(hash_value)-4) + hash_value[-4:]}")
                print(f"API Hash类型: {type(hash_value)}")
            else:
                print("API Hash: 未设置")
        else:
            print("API Hash: 未设置")
            
        # 打印会话名称
        print(f"会话名称: {config_data.get('session_name', 'tg_app')}")
        print(f"会话目录: {config_data.get('work_dir', './sessions')}")
        
        # 打印电话号码（部分隐藏）
        if "phone_number" in config_data:
            phone = config_data["phone_number"]
            if phone and len(str(phone)) > 4:
                print(f"电话号码: {'*'*(len(str(phone))-4) + str(phone)[-4:]}")
            else:
                print(f"电话号码: {phone or '未设置'}")
            print(f"电话号码类型: {type(phone)}")
        else:
            print("电话号码: 未设置")
        
        # 打印代理信息
        if proxy_data:
            print("\n--- 代理设置 ---")
            print("代理配置数据:")
            for key, value in proxy_data.items():
                print(f"  {key}: {value}")
                
            proxy_enabled = proxy_data.get("enabled", False)
            # 处理字符串和布尔值的情况
            if isinstance(proxy_enabled, str):
                proxy_enabled = proxy_enabled.lower() == "true"
            print(f"代理启用: {proxy_enabled}")
            
            if proxy_enabled:
                # 适配不同的参数名称
                proxy_type = proxy_data.get("type", proxy_data.get("proxy_type", ""))
                proxy_host = proxy_data.get("host", proxy_data.get("addr", ""))
                proxy_port = proxy_data.get("port", "")
                proxy_username = proxy_data.get("username", "")
                proxy_password = proxy_data.get("password", "")
                
                print(f"代理类型: {proxy_type}")
                print(f"代理地址: {proxy_host}:{proxy_port}")
                if proxy_username:
                    print(f"代理认证: 已配置用户名和密码")
            else:
                print("代理未启用")
        else:
            print("\n代理配置部分未找到")
        
        print("===============\n")

    # 设置超时处理
    async def connection_with_timeout(client_plugin, timeout=30):
        """带超时的连接测试"""
        try:
            # 创建超时任务
            connect_task = asyncio.create_task(client_plugin.connect())
            
            # 设置超时
            result = await asyncio.wait_for(connect_task, timeout=timeout)
            return result
        except asyncio.TimeoutError:
            logger.error(f"连接超时，超过了{timeout}秒")
            return {"success": False, "error": f"连接超时，超过了{timeout}秒"}
        except Exception as e:
            logger.error(f"连接过程中出错: {str(e)}")
            return {"success": False, "error": str(e)}

    async def test_client_plugin():
        """测试客户端插件的基本功能"""
        logger.info("开始测试客户端插件...")
        
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
                
                # 获取客户端配置信息和代理信息
                client_config = config_manager.get_section("client")
                proxy_config = config_manager.get_section("proxy")
                
                # 打印客户端配置信息
                print_config_info(client_config, proxy_config)
            else:
                logger.error("配置加载失败")
                return
            
            # 注册配置事件处理器
            async def handle_get_config(data):
                section = data.get('section')
                if not section:
                    return {"success": False, "error": "未指定配置节"}
                
                config_data = config_manager.get_section(section)
                
                # 打印请求的配置部分
                logger.info(f"请求配置部分: {section}")
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
            
            # 获取客户端配置并打印
            client_config = await client_plugin.get_config()
            logger.info("客户端配置:")
            for key, value in client_config.items():
                if key in ["api_hash", "api_id", "phone_number"]:
                    # 隐藏敏感信息
                    value_str = str(value)
                    if value_str and len(value_str) > 4:
                        logger.info(f"  {key}: {'*'*(len(value_str)-4)}{value_str[-4:]}")
                    else:
                        logger.info(f"  {key}: (敏感信息已隐藏)")
                else:
                    logger.info(f"  {key}: {value}")
            
            # 测试连接（带超时）
            logger.info("测试连接到Telegram（设置30秒超时）...")
            connect_result = await connection_with_timeout(client_plugin, timeout=30)
            
            if connect_result.get("success"):
                logger.info(f"连接成功: {connect_result.get('message')}")
                
                # 获取客户端实例
                response = await event_bus.publish_and_wait(
                    events.CLIENT_GET_INSTANCE,
                    {}
                )
                
                if response and response.get("success") and response.get("client"):
                    logger.info("成功获取客户端实例")
                    client = response.get("client")
                    
                    # 测试一个简单的API调用
                    try:
                        me = await client.get_me()
                        logger.info(f"当前用户: ID={me.id}, 用户名={me.username}, 名字={me.first_name}")
                    except Exception as e:
                        logger.error(f"API调用失败: {str(e)}")
                else:
                    logger.error(f"获取客户端实例失败: {response}")
                
                # 测试断开连接
                logger.info("测试断开连接...")
                disconnect_result = await client_plugin.disconnect()
                
                if disconnect_result.get("success"):
                    logger.info(f"断开连接成功: {disconnect_result.get('message')}")
                else:
                    logger.error(f"断开连接失败: {disconnect_result.get('error')}")
            else:
                logger.error(f"连接失败: {connect_result.get('error')}")
                logger.info("由于连接失败，跳过其余测试步骤")
            
            # 关闭插件
            await client_plugin.shutdown()
            logger.info("客户端插件测试完成")
            
        except Exception as e:
            logger.error(f"测试过程中出错: {str(e)}")
            traceback.print_exc()

    if __name__ == "__main__":
        # 运行测试
        asyncio.run(test_client_plugin())
except Exception as e:
    print(f"导入模块时出错: {str(e)}")
    traceback.print_exc() 