#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
TG Forwarder 应用程序入口点
提供命令行接口和应用程序启动功能

版本: v0.3.7
更新日期: 2024-08-30
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
from tg_forwarder.core.channel_factory import (
    parse_channel, format_channel, is_channel_valid, can_forward_from, can_forward_to, filter_channels
)
from tg_forwarder.utils.exceptions import ChannelParseError


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
    
    # 子命令 - 简化后只保留命令名称，所有参数只从配置文件读取
    subparsers = parser.add_subparsers(dest="command", help="命令")
    
    # 1. 历史消息转发命令
    subparsers.add_parser(
        "forward", 
        help="按照设置的消息范围，将源频道的历史消息保持原格式转发到目标频道"
    )
    
    # 2. 历史消息下载命令
    subparsers.add_parser(
        "download", 
        help="按照设置的消息范围，下载源频道的历史消息到配置文件中设置的下载保存路径"
    )
    
    # 3. 本地文件上传命令
    subparsers.add_parser(
        "upload", 
        help="将本地'上传路径'中的文件上传到目标频道"
    )
    
    # 4. 最新消息监听转发命令
    subparsers.add_parser(
        "startmonitor", 
        help="监听源频道，检测到新消息就转发到目标频道"
    )
    
    return parser


async def forward_messages(args: argparse.Namespace) -> None:
    """
    按照设置的消息范围，将源频道的历史消息转发到目标频道
    
    Args:
        args: 命令行参数
    """
    app = Application(config_path=args.config)
    
    # 使用Application类中的全局信号处理设置
    Application.setup_signal_handling()
    
    await app.initialize()
    
    try:
        # 获取转发配置
        config = app.get_config()
        forward_config = config.get_forward_config()
            
        print(f"开始转发历史消息...")
        print(f"消息ID范围: {forward_config.get('start_id', 0)} - {forward_config.get('end_id', '最新消息')}")
        print(f"消息数量限制: {forward_config.get('limit', '无限制')}")
        
        # 显示频道配对数量
        channel_pairs = forward_config.get('channel_pairs', {})
        print(f"频道配对: {len(channel_pairs)}对")
        
        # 开始转发
        forwarder = app.get_forwarder()
        if forwarder is None:
            print("错误: 转发器初始化失败。请检查配置文件中的forward_channel_pairs是否正确设置。")
            print("配置格式示例:")
            print('  "forward_channel_pairs": [')
            print('    {')
            print('      "source_channel": "https://t.me/source_channel",')
            print('      "target_channels": ["https://t.me/target1", "https://t.me/target2"]')
            print('    }')
            print('  ]')
            return
        
        # 获取客户端并确保它传递给频道工具实例
        client = app.get_client()
        if client:
            # 从app获取channel_utils
            channel_utils = app.get_channel_utils()
            # 设置客户端
            channel_utils.set_client(client)
            
        result = await forwarder.start_forwarding(forward_config=forward_config)
        
        if isinstance(result, dict) and result.get("success", False):
            print("历史消息转发成功完成")
            print(f"成功转发: {result.get('forwarded', 0)}条消息")
            print(f"失败: {result.get('failed', 0)}条消息")
            print(f"跳过: {result.get('skipped', 0)}条消息")
        else:
            print(f"历史消息转发失败: {result}")
    
    finally:
        await app.shutdown()


async def download_messages(args: argparse.Namespace) -> None:
    """
    按照设置的消息范围，下载源频道的历史消息
    
    Args:
        args: 命令行参数
    """
    app = Application(config_path=args.config)
    
    # 使用Application类中的全局信号处理设置
    Application.setup_signal_handling()
    
    await app.initialize()
    
    try:
        # 获取下载配置
        config = app.get_config()
        download_config = config.get_download_config()
            
        print(f"开始下载历史消息...")
        print(f"消息ID范围: {download_config.get('start_id', 0)} - {download_config.get('end_id', '最新消息')}")
        print(f"消息数量限制: {download_config.get('limit', '无限制')}")
        print(f"源频道: {', '.join(str(ch) for ch in download_config.get('source_channels', []))}")
        print(f"下载目录: {download_config.get('directory', 'downloads')}")
        
        # 开始下载
        downloader = app.get_downloader()
        if downloader is None:
            print("错误: 下载器初始化失败。请检查配置文件中的source_channels是否正确设置。")
            print("下载配置应包含source_channels列表，例如:")
            print('  "download": {')
            print('    "source_channels": ["@channel_username1", "@channel_username2"],')
            print('    "directory": "downloads"')
            print('  }')
            return
        
        # 获取客户端并确保它传递给频道工具实例
        client = app.get_client()
        if client:
            # 从app获取channel_utils
            channel_utils = app.get_channel_utils()
            # 设置客户端
            channel_utils.set_client(client)
            
        result = await downloader.download_messages(download_config=download_config)
        
        if isinstance(result, dict) and "success" in result:
            if result.get("success") is False:
                print(f"下载失败: {result.get('error', '未知错误')}")
            else:
                print("下载任务完成")
                print(f"成功下载: {len(result.get('success', []))}个文件")
                print(f"失败: {len(result.get('failed', []))}个文件")
                print(f"跳过: {len(result.get('skipped', []))}个文件")
        else:
            print(f"下载任务完成")
    
    finally:
        await app.shutdown()


async def upload_files(args: argparse.Namespace) -> None:
    """
    将本地文件上传到目标频道
    
    Args:
        args: 命令行参数
    """
    app = Application(config_path=args.config)
    
    # 使用Application类中的全局信号处理设置
    Application.setup_signal_handling()
    
    await app.initialize()
    
    try:
        # 获取上传配置
        config = app.get_config()
        upload_config = config.get_upload_config()
            
        print(f"开始上传本地文件...")
        print(f"上传目录: {upload_config.get('directory', 'uploads')}")
        print(f"目标频道: {', '.join(str(ch) for ch in upload_config.get('target_channels', []))}")
        
        # 开始上传
        uploader = app.get_uploader()
        if uploader is None:
            print("错误: 上传器初始化失败。请检查配置文件中的target_channels是否正确设置。")
            print("上传配置应包含target_channels列表，例如:")
            print('  "upload": {')
            print('    "target_channels": ["@channel_username1", "@channel_username2"],')
            print('    "directory": "uploads"')
            print('  }')
            return
            
        # 获取客户端并确保它传递给频道工具实例
        client = app.get_client()
        if client:
            # 从app获取channel_utils
            channel_utils = app.get_channel_utils()
            # 设置客户端
            channel_utils.set_client(client)
            
        result = await app.upload_files(upload_config)
        
        if isinstance(result, dict) and result.get("success", False):
            print("文件上传成功完成")
            print(f"成功上传: {result.get('success_count', 0)}个文件")
            print(f"失败: {result.get('failed_count', 0)}个文件")
            print(f"跳过: {result.get('skipped_count', 0)}个文件")
        else:
            print(f"文件上传失败: {result}")
    
    finally:
        await app.shutdown()


async def start_monitor(args: argparse.Namespace) -> None:
    """
    启动监听服务，实时监听源频道的新消息并转发
    
    Args:
        args: 命令行参数
    """
    app = Application(config_path=args.config)
    
    # 使用Application类中的全局信号处理设置
    Application.setup_signal_handling()
    
    await app.initialize()
    
    try:
        # 获取监听配置
        config = app.get_config()
        monitor_config = config.get_monitor_config()
        
        # 检查channel_pairs，它应该已经被ConfigManager从monitor_channel_pairs转换过来
        if not monitor_config.get("channel_pairs"):
            print("错误: 监听配置中缺少频道配对。请检查配置文件中的monitor_channel_pairs设置。")
            print("配置格式示例:")
            print('  "monitor": {')
            print('    "monitor_channel_pairs": [')
            print('      {')
            print('        "source_channel": "https://t.me/source_channel",')
            print('        "target_channels": ["https://t.me/target1", "https://t.me/target2"]')
            print('      }')
            print('    ],')
            print('    "duration": "2025-3-28-1"')
            print('  }')
            return
        
        # 验证频道对配置
        channel_pairs = monitor_config.get("channel_pairs", {})
        updated_channel_pairs = {}
        
        # 获取频道工具实例进行频道验证
        channel_utils = app.get_channel_utils()
        
        # 获取客户端并确保它传递给频道工具实例
        client = app.get_client()
        if client:
            # 设置客户端
            channel_utils.set_client(client)
        
        print("正在验证频道配置...")
        
        # 验证源频道
        source_channels = list(channel_pairs.keys())
        filtered_source_channels = filter_channels(source_channels)
        
        if not filtered_source_channels:
            print("错误: 所有源频道格式无效。请检查monitor.channel_pairs中的源频道配置。")
            return
            
        valid_source_channels = []
        for source in filtered_source_channels:
            try:
                # 验证频道有效性
                channel_id, _ = parse_channel(source)
                valid, reason = await is_channel_valid(source)
                
                if valid:
                    # 检查转发权限
                    can_forward, reason = await can_forward_from(source)
                    if can_forward:
                        valid_source_channels.append(source)
                        print(f"源频道 {format_channel(channel_id)} 有效且允许转发")
                    else:
                        print(f"警告: 源频道 {format_channel(channel_id)} 不允许转发: {reason}")
                else:
                    print(f"警告: 无效的源频道 {source}: {reason}")
            except ChannelParseError as e:
                print(f"错误: 解析源频道 {source} 失败: {str(e)}")
                
        if not valid_source_channels:
            print("错误: 没有有效的源频道可用于监听转发。请检查频道配置和权限。")
            return
        
        # 验证每个源频道的目标频道
        for source in valid_source_channels:
            target_channels = channel_pairs.get(source, [])
            if not target_channels:
                print(f"警告: 源频道 {source} 没有配置目标频道，将被跳过")
                continue
                
            filtered_target_channels = filter_channels(target_channels)
            valid_target_channels = []
            
            for target in filtered_target_channels:
                try:
                    # 验证频道有效性
                    channel_id, _ = parse_channel(target)
                    valid, reason = await is_channel_valid(target)
                    
                    if valid:
                        # 检查转发权限
                        can_forward, reason = await can_forward_to(target)
                        if can_forward:
                            valid_target_channels.append(target)
                            print(f"目标频道 {format_channel(channel_id)} 有效且可接收转发")
                        else:
                            print(f"警告: 无法转发到目标频道 {format_channel(channel_id)}: {reason}")
                    else:
                        print(f"警告: 无效的目标频道 {target}: {reason}")
                except ChannelParseError as e:
                    print(f"错误: 解析目标频道 {target} 失败: {str(e)}")
                    
            if valid_target_channels:
                updated_channel_pairs[source] = valid_target_channels
                
        if not updated_channel_pairs:
            print("错误: 没有有效的频道对可用于监听转发。请检查频道配置和权限。")
            return
            
        # 更新配置
        monitor_config["channel_pairs"] = updated_channel_pairs
            
        # 解析持续时间
        duration = monitor_config.get("duration", "2025-12-31-23")
        try:
            parts = duration.split("-")
            if len(parts) >= 3:
                year, month, day = map(int, parts[:3])
                hour = int(parts[3]) if len(parts) > 3 else 0
                from datetime import datetime
                end_time = datetime(year, month, day, hour)
                
                print(f"开始监听源频道的消息...")
                print(f"频道配对: {len(updated_channel_pairs)}对")
                print(f"监听截止时间: {end_time.strftime('%Y-%m-%d %H:%M:%S')}")
                
                # 开始监听
                forwarder = app.get_forwarder()
                if forwarder is None:
                    print("错误: 转发器初始化失败。请检查Telegram API配置是否正确。")
                    return
                    
                result = await app.start_monitor(monitor_config)
                
                if isinstance(result, dict) and result.get("success", False):
                    print(f"监听服务已启动，监听ID: {result.get('monitor_id', '')}")
                    print(f"按Ctrl+C退出监听")
                    
                    # 持续运行，直到用户中断
                    try:
                        while True:
                            await asyncio.sleep(60)  # 每分钟检查一次
                            
                            # 获取监听状态
                            status = app.get_monitor_status()
                            if not status.get("running", False):
                                print("监听服务已停止")
                                break
                    except KeyboardInterrupt:
                        print("\n正在停止监听...")
                        stop_result = await app.stop_monitor()
                        if stop_result.get("success", False):
                            print("监听服务已停止")
                            print(f"已转发: {stop_result.get('messages_forwarded', 0)}条消息")
                        else:
                            print(f"停止监听服务失败: {stop_result.get('error', '未知错误')}")
                else:
                    print(f"启动监听服务失败: {result.get('error', '未知错误')}")
            else:
                print(f"无效的持续时间格式: {duration}")
                print("格式应为: 年-月-日-时，如 2025-3-28-1")
        except Exception as e:
            print(f"解析监听持续时间出错: {str(e)}")
    
    finally:
        # 如果不是因为键盘中断，确保应用程序正常关闭
        await app.shutdown()


def main() -> None:
    """主函数"""
    parser = setup_argument_parser()
    args = parser.parse_args()
    
    # 设置基础日志配置
    logging.basicConfig(
        level=getattr(logging, args.log_level),
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    )
    
    # 根据命令选择操作
    commands = {
        "forward": forward_messages,
        "download": download_messages,
        "upload": upload_files,
        "startmonitor": start_monitor
    }
    
    if not args.command:
        parser.print_help()
        sys.exit(1)
    
    if args.command in commands:
        asyncio.run(commands[args.command](args))
    else:
        parser.print_help()


if __name__ == "__main__":
    main() 