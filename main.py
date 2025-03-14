#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
Telegram频道消息转发工具主程序
"""

import os
import sys
import asyncio
import argparse
from loguru import logger

from tg_forwarder.manager import ForwardManager
from tg_forwarder.utils.logger import setup_logger

def parse_arguments():
    """解析命令行参数"""
    parser = argparse.ArgumentParser(description="Telegram频道消息转发工具")
    
    parser.add_argument(
        "-c", "--config", 
        dest="config_path",
        default="config.ini",
        help="配置文件路径 (默认: config.ini)"
    )
    
    parser.add_argument(
        "--source", 
        dest="source_channel",
        help="源频道标识符，优先于配置文件中的设置"
    )
    
    parser.add_argument(
        "--target", 
        dest="target_channels",
        help="目标频道标识符，多个频道用逗号分隔，优先于配置文件中的设置"
    )
    
    parser.add_argument(
        "--start", 
        dest="start_id",
        type=int,
        help="起始消息ID，优先于配置文件中的设置"
    )
    
    parser.add_argument(
        "--end", 
        dest="end_id",
        type=int,
        help="结束消息ID，优先于配置文件中的设置"
    )
    
    return parser.parse_args()

async def main():
    """主程序"""
    args = parse_arguments()
    
    try:
        # 检查配置文件是否存在
        if not os.path.exists(args.config_path):
            if os.path.exists("config_example.ini"):
                print(f"错误: 配置文件 '{args.config_path}' 不存在。请复制并修改 config_example.ini")
            else:
                print(f"错误: 配置文件 '{args.config_path}' 不存在。")
            return 1
        
        # 创建转发管理器
        manager = ForwardManager(args.config_path)
        
        # 设置管理器
        await manager.setup()
        
        try:
            # 运行转发流程
            result = await manager.run()
            
            # 输出统计信息
            logger.info(f"统计信息: 总数 {result.get('total', 0)}, 处理 {result.get('processed', 0)}, 成功 {result.get('success', 0)}, 失败 {result.get('failed', 0)}")
            
            # 根据操作是否成功输出最终结果
            if result.get('success_flag', False):
                logger.info("转发任务执行成功")
            else:
                logger.error("转发任务执行失败")
            
            return 0
        
        finally:
            # 关闭管理器
            await manager.shutdown()
    
    except KeyboardInterrupt:
        print("\n程序被用户中断")
        return 130
    
    except Exception as e:
        print(f"发生错误: {str(e)}")
        import traceback
        traceback.print_exc()
        return 1

if __name__ == "__main__":
    # 在Windows上运行异步事件循环的修复
    if sys.platform == 'win32':
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    
    exit_code = asyncio.run(main())
    sys.exit(exit_code) 