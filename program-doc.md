# TG Forwarder 程序文档

## 1. 项目概述

TG Forwarder 是一个 Telegram 消息转发工具，用于在不同的 Telegram 频道、群组或聊天之间转发消息。该工具提供多种功能，包括历史消息转发、媒体下载、本地文件上传以及最新消息监听转发。

## 2. 技术架构

### 2.1 设计原则

- 采用生产者消费者模式：下载完一个媒体组，上传一个媒体组，上传的同时，允许第二个媒体组同时下载
- 统一使用 JSON 文件保存历史记录，不使用数据库
- 模块化设计，各功能独立实现

## 3. 功能需求

### 3.1 历史消息转发

- **功能描述**：根据统一设置的消息范围，配置多组"一个源频道和多个目标频道"的消息映射，根据媒体组 ID 顺序串行转发
- **实现方式**：
  - 一组映射转发完成后再转发下一组
  - 每组以一对多的形式转发
  - 保持源频道消息格式
  - 可配置需转发的文件类型
  - 可设置消息过滤器，过滤特定的文字、链接、表情等（暂不实现，留好接口）
  - 非禁止频道直接转发
  - 禁止频道先下载后上传
  - 上传成功一个媒体组后，就删除本地临时目录内的对应文件
  - 首先获取各频道真实 ID
  - 获取频道转发状态，可转发频道排序
  - 自动判断源频道是否为禁止转发频道
  - 对禁止转发频道，统一采用先下载后转发的方式
  - 一个消息转发到多目标频道时，采用先上传到第一个非禁止转发目标频道，再通过 copy 的方法转发到其余目标频道
  - 各功能模块（下载/上传/转发）失败后，等待 timeout 秒，再尝试 max_retries 次，若仍失败则跳过
  - 通过记录已转发消息，防止下次转发时，重复转发
  - 水印功能，暂不实现，预留接口

### 3.2 历史消息媒体下载

- **功能描述**：根据统一设置的消息范围，下载视频/图片/文件到指定路径
- **实现方式**：
  - 可按源频道用户名分类保存
  - 可设置下载类型和范围
  - 支持断点续传（跳过已下载文件）

### 3.3 本地文件上传

- **功能描述**：上传本地文件到目标频道
- **实现方式**：
  - 通过设置每个媒体组的文件数量及 caption
  - 以媒体组形式上传到多个目标频道
  - 媒体组组织：在 uploads 文件夹中创建子文件夹，文件夹名作为媒体组的 caption，文件夹内文件组成媒体组（最多 10 个文件）

### 3.4 最新消息监听转发

- **功能描述**：监听源频道的新消息，实时转发到目标频道
- **实现方式**：
  - 配置多组"一个源频道和多个目标频道"的消息映射
  - 保持源频道消息格式
  - 可配置需转发的文件类型
  - 可设置消息过滤器，过滤特定的文字、链接、表情等
  - 设置监听时间（duration），格式为年-月-日-时，到期自动停止监听
  - 如何实现参考 pyrogram 的文档

## 4. 命令行接口

应用提供以下四种命令行参数：

1. `python run.py forward`

   - 按照设置的消息范围，将源频道的历史消息保持原格式转发到目标频道

2. `python run.py download`

   - 按照设置的消息范围，下载源频道的历史消息到配置文件中设置的下载保存路径

3. `python run.py upload`

   - 将本地"上传路径"中的文件上传到目标频道
   - 支持按媒体组设置或单条消息上传

4. `python run.py startmonitor`
   - 监听源频道，检测到新消息就转发到目标频道

## 5. 配置字段说明

### 5.1 通用字段

- `limit`：下载/上传/转发的数量限制，达到数量限制后，程序休眠 pause_time 秒后再启动
- `pause_time`：达到限制后的休眠时间（秒）
- `timeout`：操作超时时间（秒）
- `max_retries`：失败后重试次数

### 5.2 下载配置

- `download_history`：记录各源频道已下载成功的消息 ID，避免重复下载
- `start_id`/`end_id`：下载消息的 ID 范围
- `source_channels`：源频道列表
- `organize_by_chat`：是否按源频道分类保存文件

### 5.3 上传配置

- `upload_history`：记录已上传的本地文件及已上传目标频道，避免重复上传
- `target_channels`：目标频道列表
- `directory`：本地上传文件路径

### 5.4 转发配置

- `forward_history`：记录各源频道已转发的消息 ID，避免重复转发
- `forward_channel_pairs`：源频道与目标频道的映射关系
  - 数据结构为数组形式，每个元素为包含源频道和目标频道列表的对象
  - 每个对象包含 `source_channel` 和 `target_channels` 两个字段
  - `source_channel` 可以是频道链接（如 "https://t.me/channel_name"）或频道用户名（如 "@channel_name"）
  - `target_channels` 为数组格式，可包含多个频道，支持同样的格式（链接或用户名）
  - 示例：
    ```json
    "forward_channel_pairs": [
      {"source_channel": "https://t.me/source_channel",
       "target_channels": ["https://t.me/target1", "https://t.me/target2"]
      }
    ]
    ```
- `remove_captions`：是否移除原始消息的标题，设为 `true` 则发送时不带原始标题
- `media_types`：需转发的媒体类型，如 ["photo", "video", "document", "audio", "animation"]
- `forward_delay`：转发延迟（秒），用于避免触发 Telegram 的速率限制
- `timeout`：转发操作超时时间（秒）
- `max_retries`：转发失败后的最大重试次数
- `message_filter`：消息过滤器（预留接口，暂不实现）
- `add_watermark`：是否添加水印（预留接口，暂不实现）
- `watermark_text`：水印文本（预留接口，暂不实现）
- `start_id`：起始消息 ID，从此 ID 开始转发
- `end_id`：结束消息 ID，转发到此 ID 为止
- `limit`：转发消息数量上限，达到此数量后暂停转发
- `pause_time`：达到限制后的暂停时间（秒）

### 5.5 监听配置

- `monitor_channel_pairs`：源频道与目标频道的映射关系
  - 数据结构与 `forward_channel_pairs` 相同，为数组形式
  - 每个元素为包含 `source_channel` 和 `target_channels` 字段的对象
  - 示例：
    ```json
    "monitor_channel_pairs": [
      {"source_channel": "https://t.me/source_channel",
       "target_channels": ["https://t.me/target1", "https://t.me/target2"]
      }
    ]
    ```
- `remove_captions`：是否移除原始消息的标题
- `media_types`：需转发的媒体类型，如 ["photo", "video", "document", "audio", "animation"]
- `duration`：监听时长，格式为"年-月-日-时"，如"2025-3-28-1"（表示监听截止到 2025 年 3 月 28 日 1 点）
- `forward_delay`：转发延迟（秒）
- `max_retries`：转发失败后的最大重试次数
- `message_filter`：消息过滤器（预留接口，暂不实现）
- `add_watermark`：是否添加水印（预留接口，暂不实现）
- `watermark_text`：水印文本（预留接口，暂不实现）

### 5.6 存储配置

- `tmp_path`：用于禁止转发频道下载上传文件的临时文件目录，系统将在此目录中存储从禁止转发频道下载的媒体文件，以便于后续上传

## 6. 技术实现注意事项

1. 本地文件上传组织：

   - 在 uploads 文件夹中，创建多个子文件夹
   - 文件夹名即为媒体组的 caption
   - 文件夹内文件组成媒体组，一个媒体组最多 10 个文件

2. 消息过滤器功能：

   - 预留接口
   - 主要功能包括过滤消息文本中的特定文字、特定格式的链接等

3. 统一使用 JSON 文件存储历史记录：

   - 下载历史记录（download_history.json）：

     ```json
     {
       "channels": {
         "@channel_name1": {
           "channel_id": -100123456789,
           "downloaded_messages": [12345, 12346, 12347]
         },
         "https://t.me/channel_name2": {
           "channel_id": -100987654321,
           "downloaded_messages": [56789, 56790]
         }
       },
       "last_updated": "2023-06-15T08:30:45.123Z"
     }
     ```

   - 上传历史记录（upload_history.json）：

     ```json
     {
       "files": {
         "C:/path/to/file1.jpg": {
           "uploaded_to": ["@target_channel1", "https://t.me/target_channel2"],
           "upload_time": "2023-06-15T09:15:30.456Z",
           "file_size": 1024567,
           "media_type": "photo"
         },
         "C:/path/to/file2.mp4": {
           "uploaded_to": ["@target_channel1"],
           "upload_time": "2023-06-15T09:20:45.789Z",
           "file_size": 25678912,
           "media_type": "video"
         }
       },
       "last_updated": "2023-06-15T09:20:45.789Z"
     }
     ```

   - 转发历史记录（forward_history.json）：
     ```json
     {
       "channels": {
         "@source_channel1": {
           "channel_id": -100123456789,
           "forwarded_messages": {
             "12345": ["@target_channel1", "https://t.me/target_channel2"],
             "12346": ["@target_channel1"]
           }
         },
         "https://t.me/source_channel2": {
           "channel_id": -100987654321,
           "forwarded_messages": {
             "56789": ["@target_channel1", "@target_channel3"]
           }
         }
       },
       "last_updated": "2023-06-15T10:05:12.345Z"
     }
     ```

4. 转发模式处理：
   - 对于禁止转发的频道，采用先下载后上传的方式
   - 对于多目标频道，先上传到第一个非禁止转发频道，再转发到其他目标频道

## 8. 频道解析功能

### 8.1 功能描述

频道解析功能是整个应用的基础功能之一，主要负责解析各种格式的 Telegram 频道链接或标识符，将其转换为程序内部可处理的标准格式，并提供频道有效性验证、频道状态管理等核心功能。

### 8.2 支持的频道标识符格式

- **公有频道/群组**:

  - 用户名格式: `@channel_name`
  - 纯用户名格式: `channel_name`
  - 链接格式: `https://t.me/channel_name`
  - 消息链接格式: `https://t.me/channel_name/123`

- **私有频道/群组**:
  - 数字 ID 格式: `1234567890`
  - 链接格式: `https://t.me/c/1234567890/123`
  - 邀请链接格式: `https://t.me/+abcdefghijk`
  - 纯邀请码格式: `+abcdefghijk`
  - 带前缀的邀请链接: `@https://t.me/+abcdefghijk`

### 8.3 核心功能

- **链接解析**: 将各种格式的频道标识符解析为标准化的(频道 ID/用户名, 消息 ID)元组
- **格式化显示**: 将内部频道标识符格式化为用户友好的显示格式
- **有效性验证**: 验证频道是否存在、是否可访问、是否可转发
- **状态缓存**: 缓存频道转发状态，减少 API 请求
- **批量处理**: 支持过滤和批量验证频道列表

### 8.4 频道状态管理

- **转发状态缓存**: 缓存频道的转发权限状态，避免重复验证
- **缓存过期策略**: 设置缓存有效期，确保数据的时效性
- **状态判断**: 自动判断频道是否允许转发内容
- **频道排序**: 根据转发状态对频道列表进行优先级排序

### 8.5 技术实现关键点

- **严格错误处理**: 对各种格式的解析错误提供详细的错误信息
- **实时验证**: 通过 Telegram API 实时验证频道状态
- **ID 转换**: 支持将用户名转换为内部频道 ID，便于程序处理
- **缓存机制**: 使用内存缓存减少 API 调用次数，提高性能
- **友好显示**: 为不同类型的频道提供人类可读的格式化显示

通过频道解析功能，应用能够统一处理各种格式的频道标识符，简化用户输入，并为转发、下载和上传操作提供必要的频道信息支持。
