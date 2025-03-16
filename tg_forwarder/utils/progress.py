"""
进度条模块，提供命令行进度条显示功能
"""

import sys
import time

class ProgressBar:
    """进度条类，用于显示任务进度"""
    
    def __init__(self, total: int, desc: str = "", width: int = 50, 
                 fill_char: str = "█", empty_char: str = "░", 
                 file=sys.stdout, update_interval: float = 0.1):
        """
        初始化进度条
        
        Args:
            total: 总步骤数
            desc: 进度条描述
            width: 进度条宽度
            fill_char: 填充字符
            empty_char: 空白字符
            file: 输出文件对象
            update_interval: 更新间隔，单位秒
        """
        self.total = total
        self.desc = desc
        self.width = width
        self.fill_char = fill_char
        self.empty_char = empty_char
        self.file = file
        self.update_interval = update_interval
        self.current = 0
        self.start_time = time.time()
        self.last_update_time = 0
        self.visible = True
    
    def update(self, step: int = 1) -> None:
        """
        更新进度条
        
        Args:
            step: 步进值，默认为1
        """
        if not self.visible:
            return
            
        self.current += step
        current_time = time.time()
        
        # 控制更新频率，避免频繁刷新
        if current_time - self.last_update_time < self.update_interval and self.current < self.total:
            return
            
        self.last_update_time = current_time
        
        # 计算进度
        percent = min(self.current / self.total * 100, 100)
        filled_length = int(self.width * self.current // self.total)
        bar = self.fill_char * filled_length + self.empty_char * (self.width - filled_length)
        
        # 计算速度和剩余时间
        elapsed_time = current_time - self.start_time
        speed = self.current / elapsed_time if elapsed_time > 0 else 0
        remaining = (self.total - self.current) / speed if speed > 0 else 0
        
        # 格式化输出
        bar_str = f"\r{self.desc} |{bar}| {percent:.1f}% ({self.current}/{self.total})"
        time_str = f" - {elapsed_time:.1f}s elapsed, {remaining:.1f}s remaining, {speed:.1f} it/s"
        
        # 输出到终端
        print(f"{bar_str}{time_str}", end="", file=self.file)
        
        # 如果完成，添加换行
        if self.current >= self.total:
            print(file=self.file)
    
    def hide(self) -> None:
        """隐藏进度条"""
        self.visible = False
    
    def show(self) -> None:
        """显示进度条"""
        self.visible = True
    
    def close(self) -> None:
        """关闭进度条"""
        if self.visible and self.current < self.total:
            self.current = self.total
            self.update(0)

# 创建一个进度条管理器
class ProgressManager:
    """进度条管理器，管理多个进度条"""
    
    _instance = None
    _progress_bars = {}
    _active_progress_bar = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(ProgressManager, cls).__new__(cls)
        return cls._instance
    
    @classmethod
    def create_progress_bar(cls, id: str, total: int, desc: str = "", **kwargs) -> ProgressBar:
        """
        创建进度条
        
        Args:
            id: 进度条ID
            total: 总步骤数
            desc: 进度条描述
            **kwargs: 其他进度条参数
            
        Returns:
            ProgressBar: 进度条实例
        """
        progress_bar = ProgressBar(total, desc, **kwargs)
        cls._progress_bars[id] = progress_bar
        return progress_bar
    
    @classmethod
    def update_progress(cls, id: str, step: int = 1) -> None:
        """
        更新指定ID的进度条
        
        Args:
            id: 进度条ID
            step: 步进值
        """
        if id in cls._progress_bars:
            cls._progress_bars[id].update(step)
    
    @classmethod
    def set_active_progress_bar(cls, id: str) -> None:
        """
        设置活跃进度条
        
        Args:
            id: 进度条ID
        """
        if id in cls._progress_bars:
            cls._active_progress_bar = cls._progress_bars[id]
    
    @classmethod
    def get_active_progress_bar(cls) -> ProgressBar:
        """
        获取当前活跃的进度条
        
        Returns:
            ProgressBar: 当前活跃的进度条实例
        """
        return cls._active_progress_bar
    
    @classmethod
    def close_progress_bar(cls, id: str) -> None:
        """
        关闭进度条
        
        Args:
            id: 进度条ID
        """
        if id in cls._progress_bars:
            cls._progress_bars[id].close()
            if cls._active_progress_bar == cls._progress_bars[id]:
                cls._active_progress_bar = None
                
            del cls._progress_bars[id]
    
    @classmethod
    def close_all_progress_bars(cls) -> None:
        """关闭所有进度条"""
        for id in list(cls._progress_bars.keys()):
            cls.close_progress_bar(id) 