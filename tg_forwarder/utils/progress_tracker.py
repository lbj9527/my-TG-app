"""
进度跟踪模块，负责跟踪任务进度和提供统计信息
"""

import time
import asyncio
from typing import Dict, Any, Optional, List, Union
from datetime import datetime, timedelta

from tg_forwarder.utils.logger import get_logger

# 获取日志记录器
logger = get_logger("progress_tracker")

class ProgressTracker:
    """进度跟踪器，用于跟踪任务进度和提供统计信息"""
    
    def __init__(self, total_items: int = 0, update_interval: float = 1.0, 
                 log_interval: float = 5.0, auto_start: bool = True):
        """
        初始化进度跟踪器
        
        Args:
            total_items: 总项目数
            update_interval: 更新间隔（秒）
            log_interval: 日志记录间隔（秒）
            auto_start: 是否自动启动
        """
        self.total_items = total_items
        self.update_interval = update_interval
        self.log_interval = log_interval
        
        # 进度统计
        self.stats = {
            "total": total_items,
            "processed": 0,
            "success": 0,
            "failed": 0,
            "start_time": None,
            "end_time": None,
            "duration": 0,
            "last_update": 0,
            "last_log": 0,
            "progress": 0,
            "speed": 0,  # 项/秒
            "eta": None  # 预计剩余时间（秒）
        }
        
        # 历史进度数据，用于计算速度
        self.history = []
        self.history_length = 10  # 保留的历史记录数
        
        # 跟踪状态
        self.is_running = False
        
        # 自动启动
        if auto_start:
            self.start()
    
    def start(self) -> None:
        """启动进度跟踪"""
        if not self.is_running:
            self.stats["start_time"] = time.time()
            self.stats["last_update"] = self.stats["start_time"]
            self.stats["last_log"] = self.stats["start_time"]
            self.is_running = True
            logger.info(f"开始跟踪进度，总项目数: {self.total_items}")
    
    def stop(self) -> None:
        """停止进度跟踪"""
        if self.is_running:
            self.stats["end_time"] = time.time()
            self.stats["duration"] = self.stats["end_time"] - self.stats["start_time"]
            self.is_running = False
            
            # 记录最终日志
            self.log_progress(force=True)
            
            logger.info(f"进度跟踪结束，总耗时: {self._format_time(self.stats['duration'])}")
    
    def update(self, increment: int = 1, success: int = 0, failed: int = 0) -> Dict[str, Any]:
        """
        更新进度
        
        Args:
            increment: 增加的处理项数
            success: 成功项数
            failed: 失败项数
            
        Returns:
            Dict[str, Any]: 当前统计信息
        """
        if not self.is_running:
            return self.stats
        
        # 更新统计信息
        self.stats["processed"] += increment
        self.stats["success"] += success
        self.stats["failed"] += failed
        
        current_time = time.time()
        time_since_last_update = current_time - self.stats["last_update"]
        
        # 如果距离上次更新时间足够长，更新速度和ETA
        if time_since_last_update >= self.update_interval:
            # 添加历史记录
            self.history.append({
                "time": current_time,
                "processed": self.stats["processed"]
            })
            
            # 保持历史记录在指定长度
            if len(self.history) > self.history_length:
                self.history = self.history[-self.history_length:]
            
            # 计算速度和ETA
            self._calculate_speed_and_eta()
            
            # 更新最后更新时间
            self.stats["last_update"] = current_time
            
            # 计算进度百分比
            if self.total_items > 0:
                self.stats["progress"] = self.stats["processed"] / self.total_items * 100
            
            # 如果距离上次日志记录时间足够长，记录日志
            if current_time - self.stats["last_log"] >= self.log_interval:
                self.log_progress()
                self.stats["last_log"] = current_time
        
        return self.stats
    
    def log_progress(self, force: bool = False) -> None:
        """
        记录当前进度
        
        Args:
            force: 是否强制记录
        """
        if not self.is_running and not force:
            return
        
        # 进度百分比
        progress_percent = self.stats["progress"]
        
        # 计算成功率
        if self.stats["processed"] > 0:
            success_rate = self.stats["success"] / self.stats["processed"] * 100
        else:
            success_rate = 0
        
        # 格式化ETA
        eta_str = "未知"
        if self.stats["eta"] is not None:
            eta_str = self._format_time(self.stats["eta"])
        
        # 记录日志
        logger.info(
            f"进度: {progress_percent:.2f}% ({self.stats['processed']}/{self.total_items}), "
            f"速度: {self.stats['speed']:.2f} 项/秒, "
            f"成功率: {success_rate:.2f}%, "
            f"预计剩余时间: {eta_str}"
        )
    
    def _calculate_speed_and_eta(self) -> None:
        """计算速度和预计剩余时间"""
        if len(self.history) < 2:
            return
        
        # 使用最近的历史记录计算速度
        oldest = self.history[0]
        newest = self.history[-1]
        
        time_diff = newest["time"] - oldest["time"]
        processed_diff = newest["processed"] - oldest["processed"]
        
        if time_diff > 0:
            # 计算速度（项/秒）
            self.stats["speed"] = processed_diff / time_diff
            
            # 计算预计剩余时间
            if self.stats["speed"] > 0 and self.total_items > 0:
                remaining_items = self.total_items - self.stats["processed"]
                self.stats["eta"] = remaining_items / self.stats["speed"]
            else:
                self.stats["eta"] = None
        else:
            self.stats["speed"] = 0
            self.stats["eta"] = None
    
    def set_total(self, total: int) -> None:
        """
        设置总项目数
        
        Args:
            total: 总项目数
        """
        self.total_items = total
        self.stats["total"] = total
        logger.info(f"更新总项目数: {total}")
    
    def get_stats(self) -> Dict[str, Any]:
        """
        获取当前统计信息
        
        Returns:
            Dict[str, Any]: 当前统计信息
        """
        # 如果正在运行，更新持续时间
        if self.is_running:
            self.stats["duration"] = time.time() - self.stats["start_time"]
        
        return self.stats
    
    def _format_time(self, seconds: float) -> str:
        """
        格式化时间
        
        Args:
            seconds: 秒数
            
        Returns:
            str: 格式化后的时间字符串
        """
        if seconds is None:
            return "未知"
            
        # 转换为时分秒
        td = timedelta(seconds=seconds)
        
        days = td.days
        hours, remainder = divmod(td.seconds, 3600)
        minutes, seconds = divmod(remainder, 60)
        
        # 格式化输出
        if days > 0:
            return f"{days}天 {hours:02d}:{minutes:02d}:{seconds:02d}"
        else:
            return f"{hours:02d}:{minutes:02d}:{seconds:02d}" 