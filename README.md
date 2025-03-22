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
- **命令行界面**：提供丰富的命令行操作方式
- **媒体组顺序处理**：按媒体组 ID 进行有序转发，保证媒体组内消息顺序及媒体组间串行处理

## 系统要求

- Python 3.7 或更高版本
- 安装了 pip 包管理器
- 在 Windows 平台上需要安装 pywin32（用于信号处理）

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
   # 使用默认源安装
   pip install -r requirements.txt

   # 推荐：使用清华大学镜像源加速安装（国内用户）
   pip install -r requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple

   # Windows平台可能需要额外安装pywin32
   # pip install pywin32
   ```

4. 创建必要的目录：
   ```bash
   mkdir -p logs data downloads backups config
   ```

## 配置

TG Forwarder 使用 JSON 格式的配置文件。示例配置文件位于 `config/config.json`。

### 依赖说明

TG Forwarder 使用多个关键依赖包，主要包括：

- **pyrogram**: Telegram API 的 Python 客户端库，用于访问 Telegram 功能
- **TgCrypto**: 加密库，加速 Telegram API 通信
- **aiohttp/asyncio**: 异步网络和协程支持，提供高效的并发操作
- **pydantic**: 数据验证和设置管理
- **loguru**: 简化的日志记录系统，提供详细的错误追踪
- **aiosqlite**: 异步 SQLite 数据库接口，用于数据存储
- **pywin32**: Windows 平台特定功能支持，处理信号和系统调用
- **moviepy**: 视频处理库，用于生成缩略图和处理媒体

完整的依赖列表请参考 `requirements.txt` 文件。

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

完整配置选项请参考示例配置文件 `config_ex.ini` 中的注释说明。

## 使用方法

### 初次使用

首次运行需要登录 Telegram 账号，程序会自动请求登录：

```bash
python run.py forward
```

按照提示输入手机号和验证码完成登录。登录状态会保存在会话文件中，下次运行不需要重复登录。

### 命令行操作

TG Forwarder 支持四个主要命令行操作：

#### 历史消息转发

按照设置的消息范围，将源频道的历史消息保持原格式转发到目标频道：

```bash
# 使用默认配置进行历史消息转发
python run.py forward

# 指定消息数量限制
python run.py forward --limit 100

# 指定消息ID范围
python run.py forward --start-id 1000 --end-id 2000
```

支持的参数：

- `--config-section`：使用的配置部分名称，默认为"forward"
- `--limit`：覆盖配置文件中的消息数量限制
- `--start-id`：覆盖配置文件中的起始消息 ID
- `--end-id`：覆盖配置文件中的结束消息 ID

#### 历史消息下载

按照设置的消息范围，下载源频道的历史消息到配置文件中设置的下载保存路径：

```bash
# 使用默认配置进行历史消息下载
python run.py download

# 指定源频道
python run.py download --source-channels @channel1 @channel2

# 指定下载目录
python run.py download --directory "downloads/custom"

# 指定消息范围和数量限制
python run.py download --start-id 1000 --end-id 2000 --limit 500
```

支持的参数：

- `--config-section`：使用的配置部分名称，默认为"download"
- `--limit`：覆盖配置文件中的消息数量限制
- `--start-id`：覆盖配置文件中的起始消息 ID
- `--end-id`：覆盖配置文件中的结束消息 ID
- `--source-channels`：覆盖配置文件中的源频道列表
- `--directory`：覆盖配置文件中的下载目录

#### 本地文件上传

将本地"上传路径"中的文件上传到目标频道：

```bash
# 使用默认配置上传本地文件
python run.py upload

# 指定目标频道
python run.py upload --target-channels @channel1 @channel2

# 指定上传目录和移除标题选项
python run.py upload --directory "uploads/custom" --remove-captions
```

支持的参数：

- `--config-section`：使用的配置部分名称，默认为"upload"
- `--target-channels`：覆盖配置文件中的目标频道列表
- `--directory`：覆盖配置文件中的上传文件目录
- `--remove-captions`：覆盖配置文件中的移除字幕设置

#### 最新消息监听转发

监听源频道，检测到新消息就转发到目标频道：

```bash
# 使用默认配置启动监听服务
python run.py startmonitor

# 指定监听时长
python run.py startmonitor --duration "2025-12-31-23"

# 指定频道配对（JSON格式）
python run.py startmonitor --channel-pairs '{"@source_channel": ["@target1", "@target2"]}'
```

支持的参数：

- `--config-section`：使用的配置部分名称，默认为"monitor"
- `--duration`：覆盖配置文件中的监听时长设置，格式为年-月-日-时，例如 2025-12-31-23
- `--channel-pairs`：覆盖配置文件中的频道对应关系，格式为 JSON 字符串

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

3. **Windows 平台启动错误 (NotImplementedError)**

   - 这个错误是由于 Windows 平台不支持 Unix 风格的信号处理机制导致的
   - 确保已安装 pywin32 包：`pip install pywin32`
   - 如果在 v1.9.1 或更高版本仍然遇到此问题，请检查 pywin32 是否正确安装
   - 可以尝试重新安装 pywin32：`pip uninstall pywin32 && pip install pywin32`
   - 更新到 v1.9.2 或更高版本，此版本进一步改进了 Windows 平台兼容性

4. **应用崩溃**

   - 检查日志文件了解错误原因
   - 确保配置文件格式正确
   - 尝试以调试模式运行: `python run.py -l DEBUG forward`

5. **接口兼容性问题**
   - 如果遇到接口异步或同步方法的兼容性问题，请确保升级到 v0.2.1 或更高版本
   - 这些问题通常表现为`TypeError: object bool can't be used in 'await' expression`错误
   - 如果继续遇到问题，可能需要手动检查并确保所有接口和实现类的异步方法签名一致
   - 确保有关文件存储和状态跟踪的操作正确使用异步方法

### 联系支持

如有问题或建议，请提交 Issue 或联系项目维护者。

## 许可证

本项目采用 MIT 许可证。

## 贡献

欢迎贡献代码、报告问题或提出改进建议。请遵循项目的代码风格和贡献指南。

## 免责声明

本工具仅用于合法用途。用户应遵守 Telegram 服务条款和相关法律法规，不得用于未经授权的内容转发或其他违法行为。

## 版本历史

### v0.3.1 (2024-08-10)

#### 重构

- **任务管理系统改进**：
  - 完全移除对`TaskManager`的依赖，使用原生`asyncio`进行任务管理
  - 删除`tg_forwarder/core/task_manager.py`文件和相关实现类
  - 从`tg_forwarder/core/__init__.py`中移除`TaskManager`的导入和导出
  - 重构`Forwarder`类中的任务创建和管理方法：
    - 在`start_forwarding`方法中使用`asyncio.create_task`代替`task_manager.submit_task`
    - 在`stop_forwarding`方法中优化任务取消逻辑
    - 更新`schedule_forward`方法，实现基于`asyncio`的延时任务
    - 改进`cancel_scheduled_forward`和`get_forward_status`方法
  - 重构`Application`类，移除对`TaskManager`的引用
  - 使用字典存储所有任务引用，实现更高效的任务跟踪

#### 优化

- **代码简化**：减少了代码复杂度和依赖关系
- **性能提升**：直接使用 Python 内置的`asyncio`模块处理异步任务，减少中间层开销
- **可维护性**：使代码结构更加清晰，降低了维护成本

### v0.3.0 (2024-07-31)

#### 新增

- 精简命令行接口：

  - 按照需求文档规范重构命令行接口，只保留四个主要命令：`forward`、`download`、`upload` 和 `startmonitor`
  - 移除多余命令，使程序结构更加清晰简洁
  - 为每个命令添加了丰富的参数选项，支持覆盖配置文件中的设置
  - 提供更直观的命令行输出，包括操作进度和结果统计

- 增强历史记录功能：
  - 更好地支持跟踪下载、上传和转发状态
  - 实现基于 JSON 文件的高效历史记录管理
  - 添加了文件上传历史的特殊处理

### v0.2.9 (2024-07-27)

#### 新增

- 完善监听转发功能的接口：
  - 扩展 `ForwarderInterface`，添加监听相关的三个核心方法：
    - `start_monitor`: 启动监听服务，实时监听源频道新消息并转发
    - `stop_monitor`: 停止监听服务
    - `get_monitor_status`: 获取监听服务的状态信息
  - 增强 `ApplicationInterface`，添加与监听相关的三个方法：
    - `start_monitor`: 应用级别的监听启动方法
    - `stop_monitor`: 应用级别的监听停止方法
    - `get_monitor_status`: 应用级别的监听状态查询方法
  - 完善监听配置参数文档，明确支持的配置项：
    - duration: 监听时长设置，使用"年-月-日-时"格式
    - channel_pairs: 源频道与目标频道的映射关系
    - media_types: 要转发的媒体类型
    - message_filter: 消息过滤器表达式（预留接口）

#### 优化

- 接口一致性改进：
  - 确保监听方法在接口与实现类之间保持一致的方法签名
  - 为所有监听相关方法提供详细的参数和返回值文档
  - 统一返回值格式，包含成功状态、错误信息和详细数据
- 文档完善：
  - 为所有监听相关的方法添加详细的文档字符串
  - 明确说明配置参数的格式和用途
  - 对返回值的各字段提供清晰的解释

### v0.2.8 (2024-07-26)

- **重大变更**：完全移除备份和恢复功能
  - 删除`Application`类中的`backup_data()`和`restore_data()`方法
  - 移除命令行界面中的`backup`和`restore`命令
  - 更新 README 文档，移除所有备份功能相关描述
- **优化**：代码精简，去除不必要的功能，保持核心功能更清晰
- **文档**：更新所有相关文档，反映功能变更

### v0.2.7 (2024-07-25)

- **改进**：更新 Application 类，添加对 JsonStorage 和 HistoryTracker 的支持
  - 添加`get_json_storage()`和`get_history_tracker()`方法检索新的存储组件实例
  - 更新备份和恢复功能，使用 JSON 文件存储而非旧数据库
  - 改进健康检查，验证 JSON 存储和历史跟踪器状态
  - 优化应用初始化和关闭流程，确保新存储组件被正确处理
- **文档**：更新备份和恢复功能文档，反映存储机制的变化

### v0.2.6 (2024-07-25)

#### 新增

- 完整实现 `JsonStorage` 类：

  - 实现 `create_history_structure` 方法，根据历史记录类型创建标准的 JSON 结构
  - 实现 `update_timestamp` 方法，提供时间戳自动更新功能
  - 实现 `merge_json_data` 方法，支持递归合并多个 JSON 数据
  - 实现 `validate_history_structure` 方法，验证 JSON 数据结构的有效性
  - 实现 `format_datetime` 方法，标准化 ISO 8601 格式时间输出
  - 实现 `parse_datetime` 方法，支持解析多种 ISO 8601 格式的时间字符串

- 完整实现 `HistoryTracker` 类：
  - 实现 `register_channel_id` 和 `get_channel_id` 方法，支持频道 ID 与用户名的双向映射
  - 实现 `mark_message_forwarded` 和 `get_forwarded_targets` 方法，追踪消息转发状态
  - 实现 `add_file_upload_info` 和 `get_file_upload_info` 方法，管理文件上传的详细元数据
  - 实现 `update_last_timestamp` 和 `get_last_timestamp` 方法，管理时间戳
  - 实现 `export_history_data` 和 `import_history_data` 方法，支持历史数据的导入导出
  - 添加 `_guess_media_type` 辅助方法，根据文件扩展名智能判断媒体类型

#### 优化

- 优化历史记录结构，采用标准的 JSON 格式，提高数据一致性和可读性
- 改进错误处理，提供详细的日志信息便于调试
- 完善数据完整性检查，防止无效数据结构导致的错误
- 增强频道 ID 处理功能，支持多种频道标识方式（ID、用户名、链接）
- 增强时间戳处理，支持毫秒级精度和时区信息

#### 增强

- 改进历史记录初始化过程，自动验证并修复无效的数据结构
- 增强数据合并功能，避免数据丢失的情况
- 提高文件路径标准化处理，确保跨平台兼容性
- 增强频道 ID 映射缓存机制，提高查询性能

### v0.2.5 (2024-07-24)

#### 改进

- 增强接口层以支持详细的历史记录 JSON 格式：

  - 扩展 `HistoryTrackerInterface`，添加对频道 ID 与用户名映射的支持
  - 添加 `register_channel_id` 和 `get_channel_id` 方法，便于频道识别
  - 增加 `mark_message_forwarded` 和 `get_forwarded_targets` 方法，支持转发历史记录的详细跟踪
  - 添加 `add_file_upload_info` 和 `get_file_upload_info` 方法，记录文件上传的元数据
  - 增加时间戳相关方法 `update_last_timestamp` 和 `get_last_timestamp`
  - 添加历史数据导入导出方法 `export_history_data` 和 `import_history_data`

- 增强 `JsonStorageInterface` 以支持复杂的 JSON 数据结构：
  - 添加 `create_history_structure` 方法创建标准历史记录结构
  - 增加 `update_timestamp` 方法自动更新时间戳
  - 添加 `merge_json_data` 方法合并 JSON 数据
  - 增加 `validate_history_structure` 方法验证数据结构
  - 添加日期时间处理方法 `format_datetime` 和 `parse_datetime`

### v0.2.4 (2024-07-23)

#### 新增

- 重构存储和历史记录接口：
  - 新增 `JsonStorageInterface` 接口，专注于 JSON 文件操作，更符合项目实际需求
  - 新增 `HistoryTrackerInterface` 接口，专门管理下载、上传和转发历史记录
  - 实现 `JsonStorage` 类，提供 JSON 文件读写功能
  - 实现 `HistoryTracker` 类，提供历史记录跟踪功能
  - 简化 JSON 文件操作，提高代码可维护性
  - 使历史记录操作更加专注和高效
  - 标记 `StorageInterface` 为废弃状态，计划在未来版本中完全移除，由 `JsonStorageInterface` 和 `HistoryTrackerInterface` 代替

#### 优化

- 接口设计改进：
  - 简化了存储接口，移除不必要的数据库风格方法
  - 增强了历史记录管理功能，使其更加符合需求文档
  - 明确区分了存储操作和历史记录管理的职责
  - 提高了代码的可读性和可维护性
- 增强历史记录功能：
  - 更好地支持跟踪下载、上传和转发状态
  - 实现基于 JSON 文件的高效历史记录管理
  - 添加了文件上传历史的特殊处理

### v0.2.3 (2024-06-15)

#### 改进

- 完善程序文档：
  - 在需求文档中详细说明了历史记录 JSON 文件格式
  - 设计并添加了下载历史、上传历史和转发历史的 JSON 格式示例
  - 为每种历史记录文件提供了清晰的结构说明和字段解释
  - 增强了开发者对历史记录存储机制的理解

#### 优化

- 使用统一的 JSON 格式规范，确保历史记录数据的一致性
- 添加时间戳记录，便于跟踪数据更新情况
- 完善频道 ID 与用户名的对应关系存储

### v0.2.2 (2024-06-12)

#### 改进

- 重构接口层：
  - 更新 `ApplicationInterface`，添加 `get_json_storage` 和 `get_history_tracker` 方法
  - 将 `ApplicationInterface.get_storage()` 标记为废弃
  - 在 `interfaces/__init__.py` 中添加新接口的导入和导出

#### 优化

- 简化接口层依赖关系
- 为接口迁移提供明确的过渡路径

### v0.2.1 (2024-03-22)

#### 改进

- 优化配置文件结构：
  - 重构 `config.json` 文件，移除冗余配置项（删除 `backup`、`notifications`、`channel_pairs`、`source_channel_config` 和 `task_manager` 配置）
  - 保留核心功能配置：`telegram`、`log`、`ui` 和 `advanced`
  - 增加新的功能模块配置：`download`、`upload`、`forward`、`monitor` 和 `storage`
  - 每个功能模块配置项独立，提高代码可维护性

#### 新增

- 完善项目文档：

  - 在 `program-doc.md` 中添加 `storage.tmp_path` 配置说明，明确其用途为禁止转发频道的媒体文件临时存储目录
  - 增强配置字段说明，提高用户理解度

- 重构接口层：
  - 更新 `ConfigInterface` 接口，移除旧的配置获取方法，增加适配新配置结构的方法
  - 修改 `ForwarderInterface.start_forwarding()` 方法，支持新的配置格式
  - 在 `DownloaderInterface` 中添加 `download_messages()` 方法
  - 在 `UploaderInterface` 中添加 `upload_files()` 方法
  - 在 `StorageInterface` 中添加 `get_temp_directory()` 方法
  - 在 `ApplicationInterface` 中添加新的功能方法，支持下载、上传和监听功能
  - 精简接口层，移除不再需要的接口：
    - 从 `ApplicationInterface` 中移除 `get_task_manager()`、`backup_data()` 和 `restore_data()` 方法
    - 从 `ForwarderInterface` 中移除调度相关方法：`schedule_forward()`、`cancel_scheduled_forward()` 和 `get_forward_status()`
    - 完全删除 `TaskManagerInterface` 接口文件，不再支持复杂的任务调度管理
    - 从 `interfaces/__init__.py` 中移除对 `TaskManagerInterface` 的导入和导出
    - 从 `StorageInterface` 中移除 `backup()` 和 `restore()` 方法，不再支持数据备份和恢复功能

### v0.1.0 (2024-03-20)

#### 核心变更

- 完成了接口一致性验证：
  - 确认 `get_forwarding_status` 方法在接口与实现中保持同步调用特性
  - 验证了 `Application` 类中的同步状态获取方法能正确调用 `Forwarder` 的状态方法
  - 完成对所有相关接口方法的全面测试与验证

#### 修复

- 修复了接口一致性问题：
  - 在 `ForwarderInterface` 接口中添加了缺失的 `start_forwarding`、`stop_forwarding` 和 `get_forwarding_status` 方法定义
  - 将 `Forwarder` 类中的 `start_forwarding` 和 `stop_forwarding` 方法修改为异步方法，以保持与 `ApplicationInterface` 接口的一致性
  - 在 `Forwarder` 类中实现了 `get_forwarding_status` 方法，用于获取转发服务的状态
  - 更新了 `Application` 类中的方法调用，添加了缺失的 `await` 关键字

#### 基础构建

- 基于原始项目 v1.9.2 代码进行分支开发
- 重构项目结构，采用更现代的组织方式
- 添加接口定义和实现的分离设计
- 优化异步操作处理

### 原项目版本

#### v1.9.2 (2023-07-20)

- 修复多个接口异步兼容性问题，确保接口定义与实现一致
- 更新 Storage 类和 StatusTracker 类的异步方法实现
- 修正 Application 类中对 ConfigManager 错误方法调用的问题
- 优化初始化流程，提高应用启动稳定性
- 增强 Windows 平台支持，改善跨平台兼容性

#### v1.9.1 (2023-07-15)

- 修复 Windows 平台上的信号处理兼容性问题(NotImplementedError)
- 添加 pywin32 依赖支持 Windows 平台的优雅关闭
- 优化启动和退出流程
- 提高跨平台兼容性

## 未来计划

### v0.4.0 计划功能

- **图形用户界面(GUI)实现**：

  - 基于 PyQt6 开发直观的用户界面
  - 实现配置文件编辑器，可视化配置管理
  - 添加实时转发状态监控面板
  - 集成媒体文件预览功能
  - 设计任务管理器，支持任务暂停、恢复和优先级调整

- **性能优化**：

  - 实现多线程下载和上传，提升并发处理能力
  - 优化媒体文件处理流程，降低内存占用
  - 改进历史记录存储机制，提高查询效率
  - 添加本地文件缓存管理，避免重复下载

- **高级功能增强**：
  - 支持消息内容过滤，基于关键词、表情符号或正则表达式
  - 增加自动水印功能，支持图片和视频水印
  - 文件重命名模式扩展，支持更多变量和格式
  - 添加媒体转码选项，自动调整媒体质量和格式

### v0.5.0 计划功能

- **高级调度系统**：

  - 实现基于时间的任务调度
  - 支持周期性任务定义
  - 添加任务依赖关系管理
  - 实现负载均衡和资源限制

- **报告和分析**：

  - 生成详细的转发任务报告
  - 添加统计分析功能，展示转发模式和效率
  - 实现图表可视化，直观展示使用情况
  - 支持导出报告为 PDF 或 CSV 格式

- **安全和合规性增强**：
  - 添加内容审查功能，防止敏感内容转发
  - 实现用户权限管理，支持多用户操作
  - 增强数据加密，保护会话和配置安全
  - 添加合规性检查，确保遵循 Telegram API 使用条款

我们欢迎社区贡献和反馈，以上计划可能会根据用户需求和项目发展进行调整。如有功能建议或问题报告，请通过 Issue 与我们联系。

## 版本更新记录

### 版本 1.3.0 (2023-07-15)

- 实现了按媒体组 ID 进行顺序转发的功能
  - 修改了 `forward_range` 方法，确保媒体组内消息按 ID 排序处理
  - 修改了 `forward_media_group` 方法，实现媒体组消息的有序转发
  - 添加了媒体组之间的串行处理，避免消息错乱
  - 优化了媒体组内和媒体组间的延迟策略
- 添加了 `Downloader` 类中缺失的 `download_message` 方法实现
- 改进了日志记录，增加媒体组信息的详细记录

### 版本 1.2.0 (2023-06-20)

- 替换任务管理器，使用 asyncio 进行任务管理
- 优化异步任务的创建和取消机制
- 改进错误处理和状态跟踪

### 版本 1.1.0 (2023-05-10)

- 添加了新的配置选项
- 增强了消息过滤功能
- 改进了用户界面

### 版本 1.0.0 (2023-04-01)

- 首次发布
- 实现基本的消息转发功能
- 支持媒体下载和上传
