"""
日志过滤器模块，提供日志筛选功能
"""

import re
from typing import Dict, Any, List, Optional

class LogFilter:
    """日志过滤器，用于过滤不需要的日志"""
    
    def __init__(self, patterns: List[str] = None):
        """
        初始化过滤器
        
        Args:
            patterns: 过滤模式列表，支持正则表达式
        """
        self.patterns = patterns or []
        self.compiled_patterns = [re.compile(pattern) for pattern in self.patterns]
    
    def filter(self, record: Dict[str, Any]) -> bool:
        """
        过滤日志记录
        
        Args:
            record: 日志记录
            
        Returns:
            bool: 如果返回True则记录日志，否则过滤掉
        """
        # 如果没有过滤模式，则不过滤
        if not self.compiled_patterns:
            return True
        
        # 获取日志消息
        message = record["message"]
        
        # 检查是否匹配任一过滤模式
        for pattern in self.compiled_patterns:
            if pattern.search(message):
                return False
        
        return True
    
    def add_pattern(self, pattern: str) -> None:
        """
        添加过滤模式
        
        Args:
            pattern: 过滤模式，支持正则表达式
        """
        self.patterns.append(pattern)
        self.compiled_patterns.append(re.compile(pattern))
    
    def remove_pattern(self, pattern: str) -> None:
        """
        移除过滤模式
        
        Args:
            pattern: 要移除的过滤模式
        """
        if pattern in self.patterns:
            idx = self.patterns.index(pattern)
            self.patterns.pop(idx)
            self.compiled_patterns.pop(idx)
    
    def clear(self) -> None:
        """清除所有过滤模式"""
        self.patterns = []
        self.compiled_patterns = []

# 常用过滤器实例
class CommonFilters:
    """常用日志过滤器"""
    
    @staticmethod
    def get_ffmpeg_filter() -> LogFilter:
        """
        获取ffmpeg输出过滤器
        
        Returns:
            LogFilter: 过滤ffmpeg输出的过滤器
        """
        return LogFilter([
            r"frame=\s*\d+\s+fps=",  # 过滤ffmpeg进度信息
            r"^(Input|Output) #\d+",  # 过滤输入输出信息
            r"^\s*Stream #\d+",       # 过滤流信息
            r"Press \[q\] to stop",    # 过滤按键提示
            r"^\s*Duration: \d+:\d+:\d+",  # 过滤持续时间信息
            r"^size=\s*\d+kB\s+time="  # 过滤大小和时间信息
        ])
    
    @staticmethod
    def get_system_filter() -> LogFilter:
        """
        获取系统日志过滤器
        
        Returns:
            LogFilter: 过滤系统日志的过滤器
        """
        return LogFilter([
            r"^\[INFO\].*\(MainThread\)",  # 过滤主线程INFO级别日志
            r"^\[DEBUG\].*",               # 过滤所有DEBUG级别日志
            r"^Starting new HTTP connection"  # 过滤HTTP连接信息
        ])
    
    @staticmethod
    def get_telegram_api_filter() -> LogFilter:
        """
        获取Telegram API日志过滤器
        
        Returns:
            LogFilter: 过滤Telegram API日志的过滤器
        """
        return LogFilter([
            r"^Telegram-Bot:",             # 过滤Telegram-Bot前缀的日志
            r"^Pyrogram:",                 # 过滤Pyrogram前缀的日志
            r"^TelegramClient:",           # 过滤TelegramClient前缀的日志
            r"^Connection to .* established",  # 过滤连接建立日志
            r"^Session .* created",           # 过滤会话创建日志
            r"^Message .* delivered"          # 过滤消息投递日志
        ]) 