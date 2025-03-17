## 版本更新记录

### v1.0.0 (2023-03-10)

### 核心改进

在此版本中，我们对日志系统进行了全面优化，构建了一个更加模块化、功能丰富且易于使用的日志记录系统。这些改进显著提升了程序的可维护性和用户体验。

#### 新增组件

- **增强型日志记录器**：

  - 支持多种日志级别（TRACE、DEBUG、INFO、SUCCESS、WARNING、ERROR、CRITICAL）
  - 为不同模块提供独立的日志级别控制
  - 集成进度条和过滤器功能

- **进度条模块**：

  - 支持创建和管理多个进度条
  - 显示完成百分比、处理速度和预估剩余时间
  - 确保日志输出不会干扰进度条显示

- **日志过滤器**：
  - FFmpeg 输出过滤器：自动过滤处理过程中的冗余输出
  - 系统日志过滤器：过滤不必要的系统级日志
  - Telegram API 过滤器：过滤 API 调试信息

#### 架构优化

1. **解耦合设计**：

   - 将进度条和日志过滤器分离成独立模块
   - 各模块可单独使用或组合使用

2. **灵活配置**：

   - 支持丰富的配置选项，适应不同场景需求
   - 可自定义日志格式、输出目标和过滤规则

3. **向后兼容**：
   - 保留原有的接口，确保与现有代码无缝集成
   - 支持渐进式迁移，新旧接口可混合使用

### 优化效果

1. **开发效率**：更清晰的日志输出，提高调试效率
2. **用户体验**：通过进度条直观展示操作进度
3. **代码质量**：模块化设计提高代码可维护性
4. **资源利用**：过滤不必要的日志信息，减少输出量

这些改进为程序提供了更强大的日志和进度跟踪能力，同时保持了简洁的使用接口，大大提升了开发和使用体验。

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

| 参数           | 说明             | 默认值       |
| -------------- | ---------------- | ------------ |
| level          | 日志级别         | INFO         |
| file           | 日志文件路径     | logs/app.log |
| format         | 日志格式         | default      |
| filters        | 过滤器列表       | []           |
| show_progress  | 是否显示进度条   | True         |
| console_output | 是否输出到控制台 | True         |
| file_output    | 是否输出到文件   | True         |
| rotation       | 日志文件轮换设置 | 1 day        |
| retention      | 日志保留时间     | 7 days       |
| compression    | 日志压缩方式     | zip          |
| enqueue        | 是否使用队列写入 | True         |
| colorize       | 是否使用彩色输出 | True         |

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

# 频道状态管理优化

### v1.1.0 (2023-03-17)

### 核心改进

在此版本中，我们对频道状态管理进行了重大优化，解决了频道状态信息分散在多个类中的问题。这些改进提高了代码的组织性、可维护性和可扩展性。

#### 新增组件

- **ChannelStateManager 类**：
  - 专门负责集中管理所有频道状态信息
  - 支持缓存过期机制，避免使用过时的状态信息
  - 提供丰富的状态管理方法，如排序、清除缓存等

#### 架构优化

1. **状态管理集中化**：

   - 将分散在多个类中的频道状态信息统一由`ChannelStateManager`管理
   - 所有组件通过`ChannelStateManager`获取和设置频道状态

2. **接口标准化**：

   - 提供标准的状态获取和设置方法
   - 统一的频道状态访问模式

3. **向后兼容性**：
   - 保留原有的缓存机制用于向后兼容
   - 新的状态管理器与旧代码可以无缝协作

#### 代码示例

```python
# 创建状态管理器
channel_state_manager = ChannelStateManager()

# 设置频道状态
channel_state_manager.set_forward_status("channel_id", True)

# 获取频道状态
allow_forward = channel_state_manager.get_forward_status("channel_id")

# 获取所有状态
all_statuses = channel_state_manager.get_all_statuses()

# 排序频道列表（优先转发允许的频道）
sorted_channels = channel_state_manager.sort_channels_by_status(channels)

# 清除缓存
channel_state_manager.invalidate_cache("channel_id")  # 清除单个频道的缓存
channel_state_manager.invalidate_cache()  # 清除所有缓存
```

#### 实施更改

1. **ForwardManager 类**：

   - 使用`ChannelStateManager`替代原有的`channel_forward_status`字典
   - 更新相关方法，通过状态管理器操作频道状态

2. **ChannelValidator 类**：

   - 添加对`ChannelStateManager`的支持
   - 在验证方法中更新状态管理器

3. **未来扩展**：
   - 为下载和上传功能准备了基础设施，支持在源频道禁止转发时的备用方案
   - 通过状态管理器在系统各部分共享频道状态信息

### 优化效果

1. **状态一致性**：确保所有组件使用相同的频道状态信息
2. **缓存管理**：通过过期机制避免使用过时的状态信息
3. **代码清晰度**：分离状态管理逻辑，提高代码可读性
4. **功能扩展**：为添加新的状态类型和管理功能提供了基础

这些改进使系统更加健壮和可维护，为后续功能扩展打下了坚实基础。

### v1.2.0 (2023-03-18)

#### 禁止转发频道功能

本次更新实现了对禁止转发频道的消息处理能力，通过下载后重新上传的方式克服了Telegram对禁止转发频道的限制。

##### 核心新增功能

- **任务队列系统**：
  - 基于生产者-消费者模式的异步任务队列
  - 支持并发处理和错误恢复
  - 实时统计处理进度和结果

- **媒体下载系统**：
  - 按批次获取消息并分离媒体组
  - 并发下载媒体文件，支持所有主流媒体类型
  - 完整保存消息元数据，确保重建消息时的完整性

- **媒体上传系统**：
  - 支持重组媒体组并保持原始格式
  - 智能处理caption和media_group
  - 上传到第一个目标频道后自动复制到其余频道

- **错误处理机制**：
  - 完善的错误处理和重试机制
  - 自动处理FloodWait和SlowmodeWait限制
  - 详细的错误日志记录

##### 配置系统增强

新增以下配置节点：

```ini
[DOWNLOAD]
temp_folder = temp
concurrent_downloads = 10
chunk_size = 131072
retry_count = 3
retry_delay = 5

[UPLOAD]
concurrent_uploads = 3
wait_between_messages = 1
preserve_formatting = true
```

##### 模块结构

新增的模块结构如下：

```
tg_forwarder/
├── taskQueue.py            # 任务队列管理模块
├── downloader/
│   ├── __init__.py
│   ├── message_fetcher.py  # 消息获取器
│   ├── media_downloader.py # 媒体下载器
├── uploader/
│   ├── __init__.py
│   ├── assember.py         # 消息重组器
│   ├── media_uploader.py   # 媒体上传器
└── utils/
    ├── progress_tracker.py # 进度跟踪器
    └── error_handler.py    # 错误处理器
```

##### 使用方式

程序会自动检测源频道是否禁止转发，若禁止转发则自动切换到下载上传模式：

1. 从源频道获取消息并按媒体组分组
2. 并发下载所有媒体文件
3. 重组消息并保持原始格式
4. 上传到第一个目标频道
5. 从第一个目标频道复制到其余频道

这种方式确保了即使是禁止转发的频道内容也能被成功转发，同时保留了原始消息的格式和内容完整性。
