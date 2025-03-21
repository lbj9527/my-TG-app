# TG Forwarder

TG Forwarder 是一个功能强大的 Telegram 消息转发工具，用于在不同的 Telegram 频道、群组或聊天之间转发消息。

## 功能特点

- **灵活的消息转发**：支持单条消息、媒体组和日期范围的批量转发
- **多种转发模式**：支持原生转发或下载后再转发
- **媒体处理**：可下载媒体文件并重新上传，避免转发限制
- **字幕管理**：自定义转发消息的字幕格式或移除原始字幕
- **频道关联**：灵活配置源频道与目标频道的对应关系
- **任务调度**：支持计划任务和定时转发
- **状态追踪**：详细记录消息转发状态，支持失败重试
- **数据备份**：支持配置、数据库和媒体文件的备份和恢复
- **命令行界面**：提供丰富的命令行操作方式

## 系统要求

- Python 3.7 或更高版本
- 安装了 pip 包管理器

## 安装步骤

1. 克隆或下载本仓库：

   ```bash
   git clone https://your-repository-url/tg-forwarder.git
   cd tg-forwarder
   ```

2. 创建并激活虚拟环境（推荐）：

   ```bash
   # Windows
   python -m venv venv
   venv\Scripts\activate

   # Linux/macOS
   python3 -m venv venv
   source venv/bin/activate
   ```

3. 安装所需依赖：

   ```bash
   pip install -r requirements.txt
   ```

4. 创建必要的目录：
   ```bash
   mkdir -p logs data downloads backups config
   ```

## 配置

TG Forwarder 使用 JSON 格式的配置文件。示例配置文件位于 `config/config.json`。

### 必要配置

1. **Telegram API 凭据**：
   从 [my.telegram.org/apps](https://my.telegram.org/apps) 获取 API ID 和 API Hash，填入配置文件的 `telegram` 部分：

   ```json
   "telegram": {
     "api_id": 你的API_ID,
     "api_hash": "你的API_HASH",
     "session_name": "tg_forwarder"
   }
   ```

2. **源频道和目标频道**：
   配置要监控的源频道和转发目标频道：
   ```json
   "source_channels": {
     "channel1": -1001234567890,
     "channel2": "@channel_username"
   },
   "target_channels": {
     "target1": -1001098765432,
     "target2": "@target_channel"
   }
   ```

### 可选配置

- **代理设置**：如需使用代理连接 Telegram，配置 `telegram.proxy` 部分
- **转发设置**：在 `forward` 部分配置转发行为，如字幕模板、媒体处理等
- **下载设置**：在 `download` 部分配置媒体下载行为
- **备份设置**：在 `backup` 部分配置数据备份行为

完整配置选项请参考示例配置文件 `config_ex.ini` 中的注释说明。

## 使用方法

### 初次使用

首次运行会要求登录 Telegram 账号：

```bash
python run.py start
```

按照提示输入手机号和验证码完成登录。登录状态会保存在会话文件中，下次运行不需要重复登录。

### 命令行操作

TG Forwarder 支持多种命令行操作：

#### 启动应用

```bash
# 启动应用并自动开始转发服务
python run.py start

# 启动应用但不自动开始转发
python run.py start --no-forward
```

#### 控制转发状态

```bash
# 查看转发状态
python run.py forward status

# 启动转发服务
python run.py forward start

# 停止转发服务
python run.py forward stop
```

#### 转发单条消息

```bash
python run.py send --source @channel_name --target @target_channel --message-id 12345
```

添加 `--download-media` 参数可以启用下载媒体后再转发：

```bash
python run.py send --source @channel_name --target @target_channel --message-id 12345 --download-media
```

#### 数据备份与恢复

```bash
# 备份数据
python run.py backup --path ./my_backup

# 恢复数据
python run.py restore --path ./my_backup
```

#### 健康检查和版本信息

```bash
# 执行健康检查
python run.py healthcheck

# 显示版本信息
python run.py version
```

### 日志查看

日志文件默认保存在 `logs/tg_forwarder.log`，可通过查看此文件了解应用运行状态和错误信息。

## 高级功能

### 自定义字幕模板

在配置中的 `forward.caption_template` 可以使用以下变量：

- `{source_chat_title}` - 源频道标题
- `{message_id}` - 原始消息 ID
- `{date}` - 消息日期
- `{time}` - 消息时间
- `{original_caption}` - 原始字幕内容

例如：

```json
"caption_template": "转自 {source_chat_title}\n原始消息: {message_id}\n日期: {date}"
```

### 频道特定配置

可以为特定频道设置不同的转发行为，覆盖全局设置：

```json
"channel_config": {
  "channel1": {
    "caption_template": "From: {source_chat_title}\nID: {message_id}",
    "remove_captions": true,
    "download_media": false
  }
}
```

### 频道对应关系

可以设置特定的源频道和目标频道的对应关系：

```json
"channel_pairs": {
  "-1001234567890": "-1001098765432",
  "@channel_username": "@target_channel"
}
```

## 故障排除

### 常见问题

1. **无法连接到 Telegram**

   - 检查网络连接
   - 检查 API 凭据是否正确
   - 如果在受限区域，尝试配置代理

2. **转发失败**

   - 检查是否有足够的权限
   - 检查是否达到 Telegram API 限制
   - 查看日志文件获取详细错误信息

3. **应用崩溃**
   - 检查日志文件了解错误原因
   - 确保配置文件格式正确
   - 尝试以调试模式运行: `python run.py -l DEBUG start`

### 联系支持

如有问题或建议，请提交 Issue 或联系项目维护者。

## 许可证

本项目采用 MIT 许可证。

## 贡献

欢迎贡献代码、报告问题或提出改进建议。请遵循项目的代码风格和贡献指南。

## 免责声明

本工具仅用于合法用途。用户应遵守 Telegram 服务条款和相关法律法规，不得用于未经授权的内容转发或其他违法行为。

## 版本更新记录

### v1.9.0 (2025-03-25)

#### 项目架构改进与模块化重组

本次更新对项目的整体架构进行了重要重组，更加清晰地划分了不同功能模块，提高了代码的模块化程度和整体可维护性。

##### 主要架构变更

- **转发模块独立**：

  - 创建了新的 `forward` 子包，将 `forwarder.py` 移入该目录
  - 添加了 `forward/__init__.py` 以导出 `MessageForwarder` 类
  - 修改了主模块的导入路径以适应新结构

- **工具类模块化**：

  - 将各种工具类移入 `utils` 子包
  - `channel_utils.py` 和 `channel_parser.py` 统一归入工具模块
  - 添加了通用工具函数，促进代码重用

- **导入优化**：
  - 更新了所有模块的导入路径，确保兼容新结构
  - 简化了模块间的依赖关系
  - 优化了循环导入问题

##### 新的项目结构

```
tg_forwarder/
├── __init__.py
├── client.py
├── config.py
├── forward/
│   ├── __init__.py
│   └── forwarder.py
├── manager.py
├── downloader/
│   ├── __init__.py
│   ├── message_fetcher.py
│   └── media_downloader.py
├── uploader/
│   ├── __init__.py
│   ├── assember.py
│   └── media_uploader.py
├── logModule/
│   ├── __init__.py
│   └── logger.py
├── taskQueue.py
└── utils/
    ├── __init__.py
    ├── channel_utils.py
    ├── channel_parser.py
    └── common.py
```

##### 代码质量改进

- **明确的模块边界**：

  - 每个模块具有更清晰的责任边界
  - 减少了跨模块访问的复杂度
  - 提高了代码的可测试性

- **接口标准化**：

  - 统一了各模块的公共接口设计
  - 简化了模块间的交互方式
  - 降低了模块间的耦合度

- **导入优化**：
  - 使用了更清晰的相对导入语法
  - 避免了循环导入问题
  - 提高了导入层次的清晰度

##### 使用示例

```python
# 旧的导入方式
from tg_forwarder.forwarder import MessageForwarder

# 新的导入方式
from tg_forwarder.forward import MessageForwarder
```

这次架构重组使项目结构更加清晰合理，符合 Python 项目的最佳实践，为未来的功能扩展和代码维护奠定了坚实基础。

### v1.8.0 (2025-03-21)

#### 核心改进

在本次更新中，我们对转发管理器的代码结构进行了重要重构，显著提高了代码的可维护性和可读性。

##### 代码结构优化

- **拆分 run 方法**：

  - 将长达 400 行的 run 方法分解为 7 个职责明确的子方法
  - 每个子方法专注于单一功能，遵循单一职责原则
  - 提高了代码的可读性、可测试性和可维护性

- **新增的子方法**：
  - `_get_real_channel_ids`：获取源频道和目标频道的真实 ID
  - `_setup_media_components`：设置媒体处理相关组件
  - `_download_producer`：处理下载任务生产
  - `_upload_producer`：处理上传任务生产
  - `_upload_consumer`：处理上传任务消费
  - `_process_download_upload`：处理完整的下载上传流程
  - `_create_error_result`：创建标准错误结果

##### 错误处理优化

- **统一错误处理**：
  - 使用`_create_error_result`方法统一生成错误结果格式
  - 在所有可能发生错误的位置添加详细的错误日志
  - 确保错误信息的一致性和可追踪性

##### 媒体上传器初始化修复

- **解决 MediaUploader 初始化问题**：
  - 修复`_setup_media_components`方法，支持传入目标频道列表
  - 解决了空目标频道列表导致初始化失败的问题
  - 增加占位 ID 机制，确保在不提供真实 ID 时也能正常初始化
  - 添加更多日志记录，便于调试上传过程

#### 代码质量改进

- **增强方法文档**：

  - 为所有新方法添加详细的 docstring
  - 明确参数类型和返回值
  - 提供方法功能描述

- **日志增强**：
  - 添加关键流程节点的日志记录
  - 在关键操作前后添加状态日志
  - 为重要参数添加值验证日志

#### 重构效益

1. **可维护性**：单一职责的方法更易于维护和更新
2. **可读性**：小型专注的方法更易于理解
3. **可测试性**：独立方法便于单元测试
4. **扩展性**：模块化结构为未来功能扩展奠定基础
5. **稳定性**：更健壮的错误处理减少运行时崩溃

此版本的重构是持续改进和代码质量提升计划的一部分，通过逐步优化代码结构，我们致力于打造更易于维护、更可靠的应用程序。

### v1.7.0 (2025-03-20)

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

本次更新实现了对禁止转发频道的消息处理能力，通过下载后重新上传的方式克服了 Telegram 对禁止转发频道的限制。

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
  - 智能处理 caption 和 media_group
  - 上传到第一个目标频道后自动复制到其余频道

- **错误处理机制**：
  - 完善的错误处理和重试机制
  - 自动处理 FloodWait 和 SlowmodeWait 限制
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

### v1.3.0 (2023-03-20)

#### 临时客户端管理与媒体转发优化

本次更新改进了临时客户端的管理机制和媒体组转发功能，提高了程序的稳定性和资源利用效率。

##### 临时客户端管理优化

- **客户端状态管理**：

  - 引入`_client_initialized`标志追踪客户端状态
  - 添加`initialize()`和`shutdown()`方法统一管理客户端生命周期
  - 所有操作前统一检查客户端状态，确保连接可用

- **长期会话支持**：

  - 取消每批次创建和关闭临时客户端的机制
  - 改为在应用启动时创建并在应用结束时关闭
  - 显著降低认证开销和 API 调用频率

- **错误处理增强**：
  - 全面检查客户端初始化失败的情况
  - 提供更清晰的错误信息和状态反馈
  - 改进会话重连和异常恢复逻辑

##### 媒体组转发功能增强

- **媒体组完整性保证**：

  - 添加`is_media_group`参数区分媒体组和单条消息
  - 媒体组使用`copy_media_group()`方法进行转发
  - 单条消息保持使用`copy_message()`方法

- **上传历史记录完善**：
  - 加入源频道 ID 作为记录键的一部分
  - 正确处理不同源频道相同消息 ID 的情况
  - 防止误判已上传状态

##### 代码架构改进

- **职责明确划分**：

  - 分离客户端管理逻辑和业务逻辑
  - 统一接口设计，提高代码可读性

- **资源管理优化**：
  - 减少不必要的客户端创建和释放
  - 更合理地管理网络连接和系统资源

##### 使用方式

新版本的使用方式简化了客户端管理流程：

1. 应用启动时调用`media_uploader.initialize()`初始化客户端
2. 正常使用上传和转发功能，无需关心客户端状态
3. 应用结束时调用`media_uploader.shutdown()`释放资源

这些优化显著提高了程序在处理大批量媒体时的稳定性和效率，特别是对于需要长时间运行的任务。

### v1.4.0 (2023-03-22)

#### 新日志系统

我们完全重构了日志系统，使用 loguru 库实现，提供了更简洁、高效的日志记录功能。

##### 特点

1. **简洁易用**：使用简单的 API 接口记录日志
2. **分级管理**：支持 TRACE、DEBUG、INFO、SUCCESS、WARNING、ERROR、CRITICAL 多个日志级别
3. **日志轮转**：自动根据配置进行日志轮转，避免日志文件过大
4. **错误跟踪**：提供异常堆栈跟踪，方便 Debug
5. **独立错误日志**：单独记录错误日志，方便问题排查

##### 使用方法

1. 初始化日志系统：

```python
from tg_forwarder.logs.logger import setup_logger

# 设置日志系统
setup_logger({
    'level': 'INFO',  # 日志级别
    'file': 'logs/app.log',  # 日志文件路径
    'rotation': '10 MB',  # 日志轮转大小
    'retention': '7 days'  # 日志保留时间
})
```

2. 在代码中使用：

```python
from tg_forwarder.logs.logger import get_logger

# 获取日志记录器
logger = get_logger("module_name")  # 推荐使用模块名作为记录器名称

# 记录不同级别的日志
logger.debug("调试信息")
logger.info("普通信息")
logger.success("成功信息")
logger.warning("警告信息")
logger.error("错误信息")
logger.critical("严重错误信息")

# 记录异常
try:
    # 可能抛出异常的代码
    result = some_function()
except Exception as e:
    logger.exception(f"发生错误: {str(e)}")  # 自动记录异常堆栈
```

##### 配置选项

日志系统支持以下配置选项：

- `level`: 日志级别，可选值包括 TRACE、DEBUG、INFO、SUCCESS、WARNING、ERROR、CRITICAL
- `file`: 日志文件路径
- `rotation`: 日志轮转策略，如"10 MB"、"1 day"等
- `retention`: 日志保留策略，如"7 days"
- `compression`: 日志压缩格式，如"zip"
- `format`: 日志格式模板
- `
