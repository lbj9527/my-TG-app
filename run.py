#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
TG Forwarder 应用程序入口点
提供命令行接口和应用程序启动功能
"""

import os
import sys
import asyncio
import signal
import argparse
import logging
from typing import Dict, Any, Optional, List

# 添加项目根目录到Python路径
PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, PROJECT_ROOT)

from tg_forwarder.core.application import Application


def setup_argument_parser() -> argparse.ArgumentParser:
    """
    设置命令行参数解析器
    
    Returns:
        argparse.ArgumentParser: 参数解析器
    """
    parser = argparse.ArgumentParser(
        description="TG Forwarder - Telegram消息转发工具",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter
    )
    
    # 全局选项
    parser.add_argument(
        "-c", "--config", 
        help="配置文件路径", 
        default="config/config.json"
    )
    parser.add_argument(
        "-l", "--log-level", 
        help="日志级别", 
        choices=["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"], 
        default="INFO"
    )
    
    # 子命令
    subparsers = parser.add_subparsers(dest="command", help="命令")
    
    # 启动命令
    start_parser = subparsers.add_parser(
        "start", 
        help="启动应用程序"
    )
    start_parser.add_argument(
        "--no-forward", 
        action="store_true", 
        help="启动应用但不自动开始转发"
    )
    
    # 转发控制命令
    forward_parser = subparsers.add_parser(
        "forward", 
        help="控制转发功能"
    )
    forward_parser.add_argument(
        "action", 
        choices=["start", "stop", "status"], 
        help="转发操作: 启动、停止或查看状态"
    )
    
    # 转发单条消息命令
    send_parser = subparsers.add_parser(
        "send", 
        help="转发单条消息"
    )
    send_parser.add_argument(
        "--source", 
        required=True, 
        help="源频道标识(ID或用户名)"
    )
    send_parser.add_argument(
        "--target", 
        required=True, 
        help="目标频道标识(ID或用户名)"
    )
    send_parser.add_argument(
        "--message-id", 
        type=int, 
        required=True, 
        help="消息ID"
    )
    send_parser.add_argument(
        "--download-media", 
        action="store_true", 
        help="下载媒体后发送"
    )
    
    # 备份与恢复命令
    backup_parser = subparsers.add_parser(
        "backup", 
        help="备份应用数据"
    )
    backup_parser.add_argument(
        "--path", 
        help="备份目录路径", 
        default=None
    )
    
    restore_parser = subparsers.add_parser(
        "restore", 
        help="恢复应用数据"
    )
    restore_parser.add_argument(
        "--path", 
        required=True, 
        help="备份目录路径"
    )
    
    # 健康检查命令
    subparsers.add_parser(
        "healthcheck", 
        help="执行应用健康检查"
    )
    
    # 版本命令
    subparsers.add_parser(
        "version", 
        help="显示应用版本"
    )
    
    return parser


async def start_application(args: argparse.Namespace) -> None:
    """
    启动应用程序
    
    Args:
        args: 命令行参数
    """
    print("正在启动 TG Forwarder 应用...")
    
    # 创建应用实例
    app = Application(config_path=args.config)
    
    # 设置信号处理
    loop = asyncio.get_event_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(
            sig,
            lambda s=sig: asyncio.create_task(handle_exit(s, app, loop))
        )
    
    # 初始化应用
    init_success = await app.initialize()
    if not init_success:
        print("应用初始化失败，无法启动")
        await app.shutdown()
        sys.exit(1)
    
    # 根据参数决定是否自动启动转发
    if args.command == "start" and not args.no_forward:
        print("自动启动转发服务...")
        forward_success = await app.start_forwarding()
        if not forward_success:
            print("警告: 转发服务启动失败，应用将继续运行但不会转发消息")
    
    print("应用已就绪，按Ctrl+C退出")
    
    try:
        # 持续运行直到收到停止信号
        while True:
            await asyncio.sleep(1)
    except asyncio.CancelledError:
        pass
    finally:
        await app.shutdown()


async def forward_control(args: argparse.Namespace) -> None:
    """
    控制转发功能
    
    Args:
        args: 命令行参数
    """
    app = Application(config_path=args.config)
    await app.initialize()
    
    try:
        if args.action == "start":
            result = await app.start_forwarding()
            print(f"转发服务启动: {'成功' if result else '失败'}")
        
        elif args.action == "stop":
            result = await app.stop_forwarding()
            print(f"转发服务停止: {'成功' if result else '失败'}")
        
        elif args.action == "status":
            status = app.get_application_status()
            print(f"应用状态: {'运行中' if status.get('running', False) else '已停止'}")
            
            if status.get('initialized', False):
                if "forwarder" in status:
                    forwarder_status = status["forwarder"]
                    print(f"消息已转发: {forwarder_status.get('messages_forwarded', 0)}")
                    print(f"转发失败: {forwarder_status.get('forward_failures', 0)}")
                
                if "task_manager" in status:
                    task_status = status["task_manager"]
                    print(f"活跃任务: {task_status.get('active_tasks', 0)}")
                    print(f"总任务数: {task_status.get('total_tasks', 0)}")
    
    finally:
        await app.shutdown()


async def send_message(args: argparse.Namespace) -> None:
    """
    转发单条消息
    
    Args:
        args: 命令行参数
    """
    app = Application(config_path=args.config)
    await app.initialize()
    
    try:
        forwarder = app.get_forwarder()
        result = await forwarder.forward_message(
            source_chat=args.source,
            target_chat=args.target,
            message_id=args.message_id,
            download_media=args.download_media
        )
        
        if result["success"]:
            print("消息转发成功")
            print(f"转发ID: {result.get('forward_id')}")
        else:
            print(f"消息转发失败: {result.get('error')}")
    
    finally:
        await app.shutdown()


async def backup_data(args: argparse.Namespace) -> None:
    """
    备份应用数据
    
    Args:
        args: 命令行参数
    """
    app = Application(config_path=args.config)
    await app.initialize()
    
    try:
        result = await app.backup_data(backup_path=args.path)
        
        if result["success"]:
            print(f"数据备份成功: {result.get('backup_path')}")
            print(f"备份时间: {result.get('timestamp')}")
            
            components = result.get("components", {})
            print("备份组件:")
            print(f"- 配置: {'成功' if components.get('config', False) else '失败'}")
            print(f"- 数据库: {'成功' if components.get('database', False) else '失败'}")
            print(f"- 媒体文件: {'成功' if components.get('media', False) else '跳过'}")
        else:
            print(f"数据备份失败: {result.get('error')}")
    
    finally:
        await app.shutdown()


async def restore_data(args: argparse.Namespace) -> None:
    """
    恢复应用数据
    
    Args:
        args: 命令行参数
    """
    app = Application(config_path=args.config)
    
    try:
        # 这里不需要初始化，因为恢复过程会自行处理初始化
        result = await app.restore_data(backup_path=args.path)
        
        if result["success"]:
            print(f"数据恢复成功: {result.get('backup_path')}")
            print(f"恢复时间: {result.get('timestamp')}")
            
            components = result.get("components", {})
            print("恢复组件:")
            print(f"- 配置: {'成功' if components.get('config', False) else '失败'}")
            
            db_result = components.get("database", {})
            if isinstance(db_result, dict):
                print(f"- 数据库: {'成功' if db_result.get('success', False) else '失败'}")
            else:
                print(f"- 数据库: {'成功' if db_result else '失败'}")
            
            media_result = components.get("media", {})
            if isinstance(media_result, dict):
                if media_result.get("skipped", False):
                    print("- 媒体文件: 跳过")
                else:
                    print(f"- 媒体文件: {'成功' if media_result.get('success', False) else '失败'}")
            else:
                print(f"- 媒体文件: {'成功' if media_result else '失败'}")
        else:
            print(f"数据恢复失败: {result.get('error')}")
    
    finally:
        await app.shutdown()


async def health_check(args: argparse.Namespace) -> None:
    """
    执行应用健康检查
    
    Args:
        args: 命令行参数
    """
    app = Application(config_path=args.config)
    await app.initialize()
    
    try:
        result = await app.health_check()
        
        print(f"健康状态: {result.get('status', 'unknown')}")
        print(f"时间戳: {result.get('timestamp')}")
        
        components = result.get("components", {})
        print("\n组件状态:")
        
        for name, status in components.items():
            print(f"- {name}: {status.get('status')}")
            
            if name == "client":
                print(f"  连接状态: {'已连接' if status.get('healthy') else '未连接'}")
            
            elif name == "task_manager" and "active_tasks" in status:
                print(f"  活跃任务: {status.get('active_tasks')}")
            
            elif name == "forwarder" and "running" in status:
                print(f"  运行状态: {'运行中' if status.get('running') else '已停止'}")
        
        sys.exit(0 if result.get("success") else 1)
    
    finally:
        await app.shutdown()


async def show_version(args: argparse.Namespace) -> None:
    """
    显示应用版本
    
    Args:
        args: 命令行参数
    """
    app = Application(config_path=args.config)
    version = app.get_version()
    print(f"TG Forwarder 版本: {version}")


async def handle_exit(sig: signal.Signals, app: Application, loop: asyncio.AbstractEventLoop) -> None:
    """
    处理退出信号
    
    Args:
        sig: 信号
        app: 应用实例
        loop: 事件循环
    """
    print(f"收到信号 {sig.name}，正在关闭应用...")
    await app.shutdown()
    tasks = [task for task in asyncio.all_tasks() if task is not asyncio.current_task()]
    
    for task in tasks:
        task.cancel()
    
    await asyncio.gather(*tasks, return_exceptions=True)
    loop.stop()


def main() -> None:
    """主函数"""
    parser = setup_argument_parser()
    args = parser.parse_args()
    
    # 设置基础日志配置
    logging.basicConfig(
        level=getattr(logging, args.log_level),
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    )
    
    # 如果没有指定命令，默认为启动
    if not args.command:
        args.command = "start"
        args.no_forward = False
    
    # 根据命令选择操作
    commands = {
        "start": start_application,
        "forward": forward_control,
        "send": send_message,
        "backup": backup_data,
        "restore": restore_data,
        "healthcheck": health_check,
        "version": show_version
    }
    
    if args.command in commands:
        asyncio.run(commands[args.command](args))
    else:
        parser.print_help()


if __name__ == "__main__":
    main() 