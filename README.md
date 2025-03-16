# 日志系统优化说明

## 日志系统特性

日志系统经过全面优化，具有以下主要特性：

### 模块化设计
- **进度条模块**：独立的 `progress.py` 支持创建和管理多个进度条
- **日志过滤器**：`log_filter.py` 提供可自定义的日志过滤功能
- **增强型日志记录器**：`logger.py` 集成了日志记录、进度条和过滤器功能

### 增强的日志能力
- 支持多种日志级别：TRACE、DEBUG、INFO、SUCCESS、WARNING、ERROR、CRITICAL
- 支持为不同模块设置不同的日志级别
- 通过过滤器实现对不需要的日志信息的过滤，保持控制台输出清晰

### 进度条支持
- 支持创建和管理多个进度条
- 进度条显示完成百分比、处理速度和预估剩余时间
- 日志输出不会干扰进度条显示

### 预设过滤器
- FFmpeg 输出过滤器：自动过滤 FFmpeg 处理过程中的冗余输出
- 系统日志过滤器：过滤不必要的系统级日志
- Telegram API 过滤器：过滤 Telegram API 调试信息

### 向后兼容性
- 保留原有的 `setup_logger` 和 `get_logger` 函数，确保与现有代码无缝集成
- 新旧接口可以混合使用，方便渐进式迁移

## 使用示例

### 基本日志使用

```python
from tg_forwarder.utils.logger import get_logger, setup_logger

# 初始化日志系统
setup_logger({
    'level': 'DEBUG',
    'file': 'logs/app.log'
})

# 获取日志记录器
logger = get_logger('my_module')

# 记录不同级别的日志
logger.debug("这是一条调试日志")
logger.info("这是一条信息日志")
logger.success("这是一条成功日志")
logger.warning("这是一条警告日志")
logger.error("这是一条错误日志")
```

### 使用进度条

```python
from tg_forwarder.utils.logger import get_logger

logger = get_logger('downloader')

# 创建进度条
total_files = 100
progress_bar = logger.create_progress_bar(
    id="file_download", 
    total=total_files, 
    desc="下载文件"
)

# 在处理过程中更新进度条
for i in range(total_files):
    # 处理文件...
    
    # 更新进度条
    logger.update_progress("file_download", 1)
    
    # 可以在进度条显示的同时输出日志
    if i % 20 == 0:
        logger.info(f"已下载 {i} 个文件")

# 关闭进度条
logger.close_progress_bar("file_download")
logger.success("所有文件下载完成！")
```

### 启用 FFmpeg 输出过滤

```python
from tg_forwarder.utils.logger import get_logger

logger = get_logger('media_processor')

# 启用 FFmpeg 输出过滤
logger.enable_ffmpeg_filter()

# FFmpeg 相关的输出会被自动过滤
# 例如："frame=  100 fps=50.0 q=29.0 size=128kB time=00:00:10.00"
```

### 多模块日志级别控制

```python
from tg_forwarder.utils.logger import LogManager

# 全局配置
LogManager.setup({
    'level': 'INFO',
    'file': 'logs/app.log'
})

# 为不同模块设置不同的日志级别
downloader_logger = LogManager.get_logger('downloader')
uploader_logger = LogManager.get_logger('uploader')

# 全局启用 FFmpeg 过滤器
LogManager.enable_ffmpeg_filter()
```

## 重构下载和上传模块的示例

以下是将新日志系统集成到下载管理器的示例：

```python
from tg_forwarder.utils.logger import get_logger

class DownloadManager:
    """文件下载管理器"""
    
    def __init__(self, config):
        self.config = config
        self.logger = get_logger('downloader')
        # 启用 FFmpeg 输出过滤，避免大量进度输出
        self.logger.enable_ffmpeg_filter()
    
    async def download_media(self, media_list):
        """下载媒体文件列表"""
        total = len(media_list)
        self.logger.info(f"开始下载 {total} 个媒体文件")
        
        # 创建进度条
        progress_bar = self.logger.create_progress_bar(
            id="media_download",
            total=total,
            desc="下载媒体文件"
        )
        
        for i, media in enumerate(media_list):
            try:
                # 下载单个文件
                await self.download_file(media)
                self.logger.update_progress("media_download", 1)
            except Exception as e:
                self.logger.error(f"下载文件失败: {str(e)}")
        
        self.logger.close_progress_bar("media_download")
        self.logger.success(f"媒体下载完成，共 {total} 个文件")
        
    async def download_file(self, media):
        """下载单个文件"""
        # 下载逻辑...
        pass
```

## 日志系统配置选项

LogConfig 支持以下配置项：

| 参数 | 说明 | 默认值 |
|------|------|---------|
| level | 日志级别 | INFO |
| file | 日志文件路径 | logs/app.log |
| format | 日志格式 | default |
| filters | 过滤器列表 | [] |
| show_progress | 是否显示进度条 | True |
| console_output | 是否输出到控制台 | True |
| file_output | 是否输出到文件 | True |
| rotation | 日志文件轮换设置 | 1 day |
| retention | 日志保留时间 | 7 days |
| compression | 日志压缩方式 | zip |
| enqueue | 是否使用队列写入 | True |
| colorize | 是否使用彩色输出 | True |

## 升级说明

该日志系统的升级主要集中在以下方面：

1. **解耦合**：将进度条和日志过滤器分离成独立模块
2. **易用性**：提供简洁的接口，使日志记录和进度展示更加方便
3. **灵活性**：支持多种日志级别和过滤规则，适应不同场景
4. **可扩展性**：采用模块化设计，便于未来功能扩展

通过这些优化，日志系统不仅提供了更清晰的输出，还能有效地跟踪各种操作的进度，大大提升了程序的用户体验和可维护性。

## 推荐的重构实践

对于现有的下载和上传模块，建议采取以下重构方式：

1. **中心化日志过滤**：在日志系统中集中处理 FFmpeg 和系统日志的过滤，保持模块代码的清洁
2. **统一进度显示**：使用日志系统的进度条功能，替代自定义的进度显示代码
3. **模块化日志**：为每个功能模块创建独立的日志记录器，方便单独控制和查看
4. **异常处理标准化**：统一异常处理和日志记录格式，提高调试效率