# TG Forwarder 程序文档

## 1. 项目概述

TG Forwarder 是一个 Telegram 消息转发工具，用于在不同的 Telegram 频道、群组或聊天之间转发消息。该工具提供多种功能，包括历史消息转发、媒体下载、本地文件上传以及最新消息监听转发。

## 2. 技术架构

### 2.1 设计原则

- 采用生产者消费者模式：下载完一个媒体组，上传一个媒体组，上传的同时，允许第二个媒体组同时下载
- 统一使用 JSON 文件保存历史记录，不使用数据库
- 模块化设计，各功能独立实现

### 2.2 核心逻辑

- 应用启动时获取各频道真实 ID
- 获取频道转发状态，可转发频道排序
- 自动判断源频道是否为禁止转发频道
- 对禁止转发频道，统一采用先下载后上传的方式
- 对多目标频道上传，采用先上传到第一个非禁止转发目标频道，再转发到其余目标频道
- 各功能模块（下载/上传/转发）失败后，等待 timeout 秒，再尝试 max_retries 次，若仍失败则跳过

## 3. 功能需求

### 3.1 历史消息转发

- **功能描述**：根据统一设置的消息范围，配置多组源频道和目标频道的消息映射，根据媒体组 ID 顺序串行转发
- **实现方式**：
  - 一组映射转发完成后再转发下一组
  - 每组以一对多的形式转发
  - 保持源频道消息格式
  - 可配置需转发的文件类型
  - 可设置消息过滤器，过滤特定的文字、链接、表情等
  - 非禁止频道直接转发，禁止频道先下载后转发
  - 上传成功一个媒体组后，就删除本地临时目录内的对应文件

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
  - 配置多组源频道和目标频道的消息映射，串行转发
  - 一组映射转发完成后再转发下一组
  - 每组以一对多的形式转发
  - 保持源频道消息格式
  - 可配置需转发的文件类型
  - 可设置消息过滤器，过滤特定的文字、链接、表情等
  - 设置监听时间（duration），格式为年-月-日-时，到期自动停止监听

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

## 5. 配置文件规范

### 5.1 保留配置项

- `telegram`：Telegram API 配置
- `log`：日志配置
- `ui`：用户界面配置
- `advanced`：高级设置

### 5.2 需删除配置项

- `backup`：备份配置
- `notifications`：通知配置
- `channel_pairs`：旧版频道配对
- `source_channel_config`：旧版源频道配置
- `task_manager`：任务管理器配置

### 5.3 修改后的配置结构

```json
{
  "download": {
    "source_channels": ["@channel_username1", "@channel_username2"],
    "directory": "downloads",
    "organize_by_chat": true,
    "timeout": 300,
    "max_retries": 1,
    "skip_existing": true,
    "filename_pattern": "{chat_id}_{message_id}_{filename}",
    "chunk_size": 1048576,
    "download_history": "download_history_file_path.json",
    "start_id": 0,
    "end_id": 1000,
    "limit": 500,
    "pause_time": 300
  },
  "upload": {
    "target_channels": ["@channel_username1", "@channel_username2"],
    "remove_captions": false,
    "directory": "uploads",
    "verify_before_upload": true,
    "timeout": 300,
    "max_retries": 1,
    "upload_history": "upload_history_file_path.json",
    "add_watermark": false,
    "watermark_text": "",
    "limit": 500,
    "pause_time": 300
  },
  "forward": {
    "channel_pairs": {
      "https://t.me/xxzq6/3581": ["https://t.me/cuyfcopu", "https://t.me/gsbsbt"],
      "https://t.me/zbzwx": ["https://t.me/cuyfcopu", "https://t.me/gsbsbt"]
    },
    "remove_captions": true,
    "media_types": ["photo", "video", "document", "audio", "animation"],
    "forward_delay": 2,
    "timeout": 500,
    "max_retries": 1,
    "message_filter": "",
    "add_watermark": false,
    "watermark_text": "",
    "forward_history": "forward_history_file_path.json",
    "start_id": 0,
    "end_id": 2000,
    "limit": 1000,
    "pause_time": 300
  },
  "storage": {
    "tmp_path": "temp"
  },
  "monitor": {
    "channel_pairs": {
      "https://t.me/xxzq6/3581": ["https://t.me/cuyfcopu", "https://t.me/gsbsbt"],
      "https://t.me/zbzwx": ["https://t.me/cuyfcopu", "https://t.me/gsbsbt"]
    },
    "remove_captions": true,
    "media_types": ["photo", "video", "document", "audio", "animation"],
    "duration": "2025-3-28-1",
    "forward_delay": 2,
    "max_retries": 3,
    "message_filter": "",
    "add_watermark": false,
    "watermark_text": ""
  }
}
```

## 6. 配置字段说明

### 6.1 通用字段

- `limit`：下载/上传/转发的数量限制，达到数量限制后，程序休眠 pause_time 秒后再启动
- `pause_time`：达到限制后的休眠时间（秒）
- `timeout`：操作超时时间（秒）
- `max_retries`：失败后重试次数

### 6.2 下载配置

- `download_history`：记录各源频道已下载成功的消息 ID，避免重复下载
- `start_id`/`end_id`：下载消息的 ID 范围
- `source_channels`：源频道列表
- `organize_by_chat`：是否按源频道分类保存文件

### 6.3 上传配置

- `upload_history`：记录已上传的本地文件及已上传目标频道，避免重复上传
- `target_channels`：目标频道列表
- `directory`：本地上传文件路径

### 6.4 转发配置

- `forward_history`：记录各源频道已转发的消息 ID，避免重复转发
- `channel_pairs`：源频道与目标频道的映射关系
  - 数据结构为 JSON 对象，其中键（冒号前）为源频道，值（冒号后）为目标频道数组
  - 源频道格式可以是频道链接（如 "https://t.me/channel_name"）或频道用户名（如 "@channel_name"）
  - 目标频道为数组格式，可包含多个频道，支持同样的格式（链接或用户名）
  - 示例：`"https://t.me/source_channel": ["https://t.me/target1", "https://t.me/target2"]`
- `media_types`：需转发的媒体类型
- `message_filter`：消息过滤器（预留接口，暂不实现）

### 6.5 监听配置

- `duration`：监听时长，格式为"年-月-日-时"，如"2025-3-28-1"
- `channel_pairs`：源频道与目标频道的映射关系
  - 与转发配置中的 `channel_pairs` 具有相同的数据结构
  - 键值对格式为：`"源频道": ["目标频道1", "目标频道2", ...]`
  - 每个源频道的新消息将被转发到对应的所有目标频道

### 6.6 存储配置

- `tmp_path`：用于禁止转发频道下载上传文件的临时文件目录，系统将在此目录中存储从禁止转发频道下载的媒体文件，以便于后续上传

## 7. 技术实现注意事项

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
