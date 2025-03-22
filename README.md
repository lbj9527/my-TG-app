## 版本历史

### v0.3.7 (2024-08-30)

#### 重大变更

- **彻底移除旧配置格式支持**：
  - 完全删除了所有处理旧版配置格式的代码，不再保留任何兼容性支持
  - 修改 `get_forward_config` 方法，只保留新格式 `forward_channel_pairs` 的处理逻辑
  - 修改 `get_monitor_config` 方法，只保留新格式 `monitor_channel_pairs` 的处理逻辑
  - 修改 `get_channel_pairs` 方法，只从 `forward_channel_pairs` 中获取配置
  - 修改 `validate` 方法，删除对旧格式的验证，专注于验证新格式的配置完整性

#### 改进

- **配置处理流程优化**：
  - 删除了复杂的向后兼容逻辑，使代码更简洁易读
  - 优化了默认配置值的应用方式，提高了配置处理的效率
  - 改进了配置处理中的异常处理和错误提示

#### 文档

- 更新了命令行错误提示，移除了所有旧格式配置示例
- 修改 `forward` 和 `startmonitor` 命令的帮助文本，只包含新格式配置的说明
- 更新 README.md，将支持的配置格式版本更新为 v0.3.7

### v0.3.6 (2024-08-28)

#### 重大变更

- **移除旧配置格式支持**：
  - 完全移除了对旧版配置格式（字典格式的`channel_pairs`）的支持
  - 只保留对新版配置格式（数组格式的`forward_channel_pairs`和`monitor_channel_pairs`）的支持
  - 修改了`get_forward_config`方法，删除对旧格式配置的处理逻辑
  - 修改了`get_monitor_config`方法，删除对旧格式配置的处理逻辑
  - 修改了`get_channel_pairs`方法，只保留对新格式配置的解析
  - 更新了`validate`方法，删除对旧格式配置的验证，增加了对`monitor_channel_pairs`的验证

#### 改进

- **配置处理优化**：
  - 简化了配置解析逻辑，提高了代码可读性和维护性
  - 改进了错误提示信息，更明确地指导用户使用新的配置格式
  - 确保默认值处理更加一致和可靠

#### 文档

- 更新错误提示消息，只保留新配置格式的示例
- 移除所有关于旧配置格式的引用和说明
- 确保配置示例清晰准确，便于用户理解新的配置方式

### v0.3.5 (2024-08-26)

#### 修复

- **应用关闭流程修复**：
  - 修复了应用关闭时尝试在无法等待的对象上使用 `await` 关键字的错误
  - 正确实现了 `Application.shutdown()` 方法中对 `get_forwarding_status()` 的调用，使用同步方式检查服务状态

- **存储兼容性增强**：
  - 为 `JsonStorage` 类添加了与旧接口兼容的方法：`query_data`、`get_data` 和 `store_data`
  - 确保 `Downloader` 的缓存加载和保存功能能正常工作
  - 添加了警告日志，提示开发者使用新的 JSON 存储 API

#### 改进

- 提高了系统在迁移到新存储机制过程中的向后兼容性
- 增强了应用程序关闭流程的健壮性
- 优化了错误处理，提供更明确的错误消息

### v0.3.4 (2024-08-25)

#### 修复

- **存储兼容性修复**：
  - 修复`StatusTracker`类初始化方法中对不存在的`_json_storage._initialized`属性的检查
  - 删除`StatusTracker`类中与旧存储系统相关的`_ensure_indexes`方法
  - 确保状态跟踪器可以正确使用新的`JsonStorage`存储系统

- **接口一致性修复**：
  - 修复`Application`类中`TelegramClient`的初始化参数不匹配问题
  - 调整客户端初始化过程，使之与当前实现的接口兼容
  - 移除`tg_forwarder/core/__init__.py`中对已删除`Storage`类的引用

#### 改进

- 提高应用程序的稳定性和健壮性
- 确保存储相关组件的平滑迁移
- 完成从旧存储系统到JSON存储的最终适配

### v0.3.3 (2024-08-20)

#### 新增

- **频道解析功能**：
  - 设计并实现了`ChannelParserInterface`和`ChannelUtilsInterface`接口
  - 实现了`ChannelParser`类，负责解析不同格式的频道标识符
  - 实现了`ChannelUtils`类，负责频道验证和状态管理
  - 创建了`ChannelParseError`异常类用于处理解析错误
  - 添加了`channel_factory.py`模块提供全局实例和工厂函数

#### 集成与优化

- **核心组件集成**：
  - 更新`Application`类，添加`get_channel_utils`方法
  - 重构`Forwarder`类，使用新的频道解析验证功能
  - 重构`Downloader`类，使用频道解析功能验证源频道
  - 重构`Uploader`类，使用频道解析功能验证目标频道
  - 更新`run.py`中的`start_monitor`函数，增强频道配置验证

#### 增强

- **频道管理改进**：
  - 支持多种频道标识符格式：ID、用户名、t.me链接
  - 智能频道验证系统，检查频道的有效性和权限
  - 频道信息缓存机制，提高频繁查询的性能
  - 用户友好的错误处理和消息格式化
  - 全局辅助函数用于简化频道操作

### v0.3.2 (2024-08-15)

#### 重大变更

- **完全移除storage相关代码**：
  - 删除旧的`StorageInterface`接口及其实现类`Storage`
  - 从`interfaces/__init__.py`中移除对`StorageInterface`的导入和导出
  - 更新`Application`类移除对`StorageInterface`的所有引用：
    - 移除`get_storage`方法
    - 更新初始化和健康检查方法，完全基于`JsonStorageInterface`和`HistoryTrackerInterface`
  - 更新所有依赖组件：
    - 修改`StatusTracker`类使用`JsonStorageInterface`
    - 修改`Downloader`类使用`JsonStorageInterface`和`HistoryTrackerInterface`
    - 修改`Uploader`类使用`JsonStorageInterface`和`HistoryTrackerInterface`

#### 优化

- **完成存储层迁移**：完全完成从旧版`StorageInterface`到新版`JsonStorageInterface`和`HistoryTrackerInterface`的迁移
- **代码简化**：移除不必要的功能，减少了代码复杂度
- **接口一致性**：确保所有组件与接口层保持一致
- **存储机制标准化**：统一使用JSON文件进行历史记录存储，符合需求文档要求

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
  - 更新 `ApplicationInterface`，添加 `get_json_storage`