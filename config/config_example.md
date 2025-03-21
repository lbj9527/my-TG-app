# TG Forwarder 配置参考指南

这是 TG Forwarder 的配置参考指南，包含所有可用选项及其说明。实际配置文件不需要包含所有这些字段，未指定的字段将使用默认值。

## 配置格式

TG Forwarder 使用 JSON 格式的配置文件，通常保存为`config.json`。下面是所有可用配置项的详细说明。

## 配置项详解

### Telegram 设置

Telegram API 凭据和连接设置

| 参数               | 类型   | 默认值         | 说明                                      |
| ------------------ | ------ | -------------- | ----------------------------------------- |
| api_id             | 整数   | -              | 从 Telegram 官方获取的 API ID，必须填写   |
| api_hash           | 字符串 | -              | 从 Telegram 官方获取的 API Hash，必须填写 |
| session_name       | 字符串 | "tg_forwarder" | Pyrogram 会话名称，用于保存登录状态       |
| connection_retries | 整数   | 5              | 连接失败时的重试次数                      |
| retry_delay        | 整数   | 2              | 重试之间的延迟秒数                        |
| auto_reconnect     | 布尔值 | true           | 是否自动重连                              |
| device_model       | 字符串 | "TG Forwarder" | 客户端设备型号，用于 Telegram 客户端识别  |
| system_version     | 字符串 | "1.0"          | 系统版本，用于 Telegram 客户端识别        |
| app_version        | 字符串 | "1.0.0"        | 应用版本，用于 Telegram 客户端识别        |

#### 代理设置

代理设置（可选），如果需要通过代理连接 Telegram

| 参数     | 类型   | 默认值      | 说明                                |
| -------- | ------ | ----------- | ----------------------------------- |
| enabled  | 布尔值 | false       | 是否启用代理                        |
| type     | 字符串 | "socks5"    | 代理类型，支持 socks5、socks4、http |
| host     | 字符串 | "127.0.0.1" | 代理服务器地址                      |
| port     | 整数   | 1080        | 代理服务器端口                      |
| username | 字符串 | ""          | 代理认证用户名，可选                |
| password | 字符串 | ""          | 代理认证密码，可选                  |

#### 示例

```json
"telegram": {
  "api_id": 12345678,
  "api_hash": "abcdef1234567890abcdef1234567890",
  "session_name": "tg_forwarder",
  "proxy": {
    "enabled": true,
    "type": "socks5",
    "host": "127.0.0.1",
    "port": 1080,
    "username": "",
    "password": ""
  },
  "connection_retries": 5,
  "retry_delay": 2,
  "auto_reconnect": true
}
```

### 日志设置

控制日志记录行为

| 参数          | 类型   | 默认值                  | 说明                                                    |
| ------------- | ------ | ----------------------- | ------------------------------------------------------- |
| file          | 字符串 | "logs/tg_forwarder.log" | 日志文件路径                                            |
| level         | 字符串 | "INFO"                  | 日志级别，可选值：DEBUG、INFO、WARNING、ERROR、CRITICAL |
| rotation      | 字符串 | "10 MB"                 | 日志文件大小轮转阈值                                    |
| backup_count  | 整数   | 5                       | 保留的备份日志文件数量                                  |
| console       | 布尔值 | true                    | 是否在控制台输出日志                                    |
| date_rotation | 布尔值 | true                    | 是否按日期轮转日志文件                                  |

#### 示例

```json
"log": {
  "file": "logs/tg_forwarder.log",
  "level": "INFO",
  "rotation": "10 MB",
  "backup_count": 5,
  "console": true,
  "date_rotation": true
}
```

### 存储设置

控制数据库和存储行为

| 参数             | 类型   | 默认值                 | 说明                                 |
| ---------------- | ------ | ---------------------- | ------------------------------------ |
| db_path          | 字符串 | "data/tg_forwarder.db" | SQLite 数据库文件路径                |
| timeout          | 整数   | 30                     | 数据库连接超时秒数                   |
| wal_mode         | 布尔值 | true                   | 是否启用 WAL（写前日志）模式提高性能 |
| backup_frequency | 整数   | 7                      | 数据库自动备份的天数间隔             |

#### 示例

```json
"storage": {
  "db_path": "data/tg_forwarder.db",
  "timeout": 30,
  "wal_mode": true,
  "backup_frequency": 7
}
```

### 任务管理器设置

控制异步任务执行

| 参数             | 类型 | 默认值 | 说明                                       |
| ---------------- | ---- | ------ | ------------------------------------------ |
| max_workers      | 整数 | 10     | 最大工作线程数量                           |
| max_queue_size   | 整数 | 1000   | 任务队列最大容量                           |
| task_expiry      | 整数 | 24     | 任务过期时间（小时），过期后自动从队列移除 |
| default_priority | 整数 | 5      | 默认任务优先级，范围 1-10，10 为最高       |
| retry_count      | 整数 | 3      | 任务失败后的自动重试次数                   |
| retry_delay      | 整数 | 30     | 重试之间的延迟秒数                         |

#### 示例

```json
"task_manager": {
  "max_workers": 10,
  "max_queue_size": 1000,
  "task_expiry": 24,
  "default_priority": 5,
  "retry_count": 3,
  "retry_delay": 30
}
```

### 下载设置

控制媒体文件下载行为

| 参数               | 类型   | 默认值                              | 说明                                                        |
| ------------------ | ------ | ----------------------------------- | ----------------------------------------------------------- |
| directory          | 字符串 | "downloads"                         | 下载文件保存的主目录                                        |
| organize_by_chat   | 布尔值 | true                                | 是否按聊天 ID 创建子目录组织文件                            |
| temp_directory     | 字符串 | "downloads/temp"                    | 临时文件目录，下载过程中的临时存储                          |
| timeout            | 整数   | 300                                 | 下载操作超时秒数                                            |
| skip_existing      | 布尔值 | true                                | 是否跳过已存在的文件                                        |
| parallel_downloads | 整数   | 3                                   | 并行下载的最大数量                                          |
| filename_pattern   | 字符串 | "{chat*id}*{message*id}*{filename}" | 文件命名模式，可用变量：{chat_id}、{message_id}、{filename} |
| chunk_size         | 整数   | 1048576                             | 分块下载的块大小（字节）                                    |

#### 示例

```json
"download": {
  "directory": "downloads",
  "organize_by_chat": true,
  "temp_directory": "downloads/temp",
  "timeout": 300,
  "skip_existing": true,
  "parallel_downloads": 3,
  "filename_pattern": "{chat_id}_{message_id}_{filename}",
  "chunk_size": 1048576
}
```

### 上传设置

控制媒体文件上传行为

| 参数                 | 类型   | 默认值 | 说明                     |
| -------------------- | ------ | ------ | ------------------------ |
| verify_before_upload | 布尔值 | true   | 上传前是否验证文件完整性 |
| timeout              | 整数   | 300    | 上传操作超时秒数         |
| preserve_filenames   | 布尔值 | true   | 是否保留原始文件名       |
| preserve_timestamps  | 布尔值 | true   | 是否保留文件时间戳       |
| retry_count          | 整数   | 3      | 上传失败后的重试次数     |
| parallel_uploads     | 整数   | 2      | 并行上传的最大数量       |

#### 示例

```json
"upload": {
  "verify_before_upload": true,
  "timeout": 300,
  "preserve_filenames": true,
  "preserve_timestamps": true,
  "retry_count": 3,
  "parallel_uploads": 2
}
```

### 转发设置

控制消息转发行为

| 参数                  | 类型   | 默认值                                                             | 说明                                                                  |
| --------------------- | ------ | ------------------------------------------------------------------ | --------------------------------------------------------------------- |
| default_mode          | 字符串 | "native"                                                           | 默认转发模式，'native'为原生转发，'download'为下载后再上传            |
| remove_captions       | 布尔值 | false                                                              | 是否移除原消息字幕                                                    |
| caption_template      | 字符串 | "转自 {source_chat_title}\n 原始消息: {message_id}\n 日期: {date}" | 自定义字幕模板，支持变量如{source_chat_title}、{message_id}、{date}等 |
| download_media        | 布尔值 | true                                                               | 是否下载媒体文件后再转发，用于绕过转发限制                            |
| media_types           | 数组   | ["photo", "video", "document", "audio", "animation"]               | 要处理的媒体类型列表                                                  |
| forward_delay         | 整数   | 2                                                                  | 两次转发操作之间的延迟秒数，避免触发限制                              |
| preserve_media_groups | 布尔值 | true                                                               | 是否保持媒体组的完整性                                                |
| max_retries           | 整数   | 3                                                                  | 转发失败后的最大重试次数                                              |
| message_filter        | 字符串 | ""                                                                 | 消息过滤器正则表达式，空字符串表示不过滤                              |
| add_watermark         | 布尔值 | false                                                              | 是否添加水印                                                          |
| watermark_text        | 字符串 | ""                                                                 | 水印文本内容                                                          |

#### 示例

```json
"forward": {
  "default_mode": "native",
  "remove_captions": false,
  "caption_template": "转自 {source_chat_title}\n原始消息: {message_id}\n日期: {date}",
  "download_media": true,
  "media_types": ["photo", "video", "document", "audio", "animation"],
  "forward_delay": 2,
  "preserve_media_groups": true,
  "max_retries": 3,
  "message_filter": "",
  "add_watermark": false,
  "watermark_text": ""
}
```

### 源频道设置

源频道列表，格式为名称:ID 或用户名，键值对类型

#### 示例

```json
"source_channels": {
  "channel1": -1001234567890,
  "channel2": "@channel_username"
}
```

### 目标频道设置

目标频道列表，格式为名称:ID 或用户名，键值对类型

#### 示例

```json
"target_channels": {
  "target1": -1001098765432,
  "target2": "@target_channel"
}
```

### 频道对应关系

频道转发对，指定源频道和目标频道的对应关系，键值对类型

#### 示例

```json
"channel_pairs": {
  "-1001234567890": "-1001098765432",
  "@channel_username": "@target_channel"
}
```

### 频道特定配置

针对特定频道的自定义配置，覆盖默认设置

#### 示例

```json
"channel_config": {
  "channel1": {
    "caption_template": "From: {source_chat_title}\nID: {message_id}",
    "remove_captions": true,
    "download_media": false,
    "media_types": ["photo", "video"]
  }
}
```

### 备份设置

控制数据备份行为

| 参数                 | 类型   | 默认值    | 说明                                 |
| -------------------- | ------ | --------- | ------------------------------------ |
| directory            | 字符串 | "backups" | 备份文件保存目录                     |
| include_media        | 布尔值 | false     | 备份是否包含媒体文件                 |
| auto_backup_interval | 整数   | 7         | 自动备份的天数间隔                   |
| max_backups          | 整数   | 5         | 保留的最大备份数量，超过会删除最旧的 |
| compress             | 布尔值 | true      | 是否压缩备份文件                     |
| compression_format   | 字符串 | "zip"     | 压缩格式，支持 zip、tar、gzip        |

#### 示例

```json
"backup": {
  "directory": "backups",
  "include_media": false,
  "auto_backup_interval": 7,
  "max_backups": 5,
  "compress": true,
  "compression_format": "zip"
}
```

### 通知设置

控制系统通知行为

| 参数                 | 类型   | 默认值     | 说明                                    |
| -------------------- | ------ | ---------- | --------------------------------------- |
| enabled              | 布尔值 | true       | 是否启用通知功能                        |
| method               | 字符串 | "telegram" | 通知方式，支持 telegram、email、webhook |
| notify_on_error      | 布尔值 | true       | 发生错误时是否发送通知                  |
| notify_on_completion | 布尔值 | false      | 任务完成时是否发送通知                  |

#### Telegram 通知设置

| 参数      | 类型        | 默认值 | 说明                           |
| --------- | ----------- | ------ | ------------------------------ |
| bot_token | 字符串      | ""     | Telegram 通知机器人的 API 令牌 |
| user_id   | 字符串/整数 | ""     | 接收通知的 Telegram 用户 ID    |

#### 电子邮件通知设置

| 参数          | 类型   | 默认值              | 说明                   |
| ------------- | ------ | ------------------- | ---------------------- |
| from          | 字符串 | ""                  | 发送通知的电子邮件地址 |
| to            | 字符串 | ""                  | 接收通知的电子邮件地址 |
| subject       | 字符串 | "TG Forwarder 通知" | 邮件主题模板           |
| smtp_server   | 字符串 | ""                  | SMTP 服务器地址        |
| smtp_port     | 整数   | 587                 | SMTP 服务器端口        |
| smtp_username | 字符串 | ""                  | SMTP 服务器用户名      |
| smtp_password | 字符串 | ""                  | SMTP 服务器密码        |
| use_tls       | 布尔值 | true                | 是否使用 TLS 加密连接  |

#### Webhook 通知设置

| 参数    | 类型   | 默认值                                 | 说明                              |
| ------- | ------ | -------------------------------------- | --------------------------------- |
| url     | 字符串 | ""                                     | 接收通知的 webhook URL            |
| method  | 字符串 | "POST"                                 | HTTP 请求方法，通常为 POST 或 GET |
| headers | 对象   | `{"Content-Type": "application/json"}` | HTTP 请求头                       |

#### 示例

```json
"notifications": {
  "enabled": true,
  "method": "telegram",
  "notify_on_error": true,
  "notify_on_completion": false,
  "telegram": {
    "bot_token": "1234567890:ABCDEFGHIJKLMNOPQRSTUVWXYZ",
    "user_id": 123456789
  },
  "email": {
    "from": "sender@example.com",
    "to": "recipient@example.com",
    "subject": "TG Forwarder 通知",
    "smtp_server": "smtp.example.com",
    "smtp_port": 587,
    "smtp_username": "username",
    "smtp_password": "password",
    "use_tls": true
  },
  "webhook": {
    "url": "https://example.com/webhook",
    "method": "POST",
    "headers": {
      "Content-Type": "application/json",
      "Authorization": "Bearer token"
    }
  }
}
```

### 用户界面设置

控制 GUI 显示（如果有）

| 参数               | 类型   | 默认值  | 说明                       |
| ------------------ | ------ | ------- | -------------------------- |
| theme              | 字符串 | "light" | 界面主题，支持 light、dark |
| language           | 字符串 | "zh_CN" | 界面语言，如 zh_CN、en_US  |
| start_minimized    | 布尔值 | false   | 启动时是否最小化窗口       |
| show_notifications | 布尔值 | true    | 是否显示桌面通知           |
| window_width       | 整数   | 1024    | 窗口宽度（像素）           |
| window_height      | 整数   | 768     | 窗口高度（像素）           |
| remember_position  | 布尔值 | true    | 是否记住窗口位置           |
| refresh_rate       | 整数   | 1000    | UI 刷新频率（毫秒）        |

#### 示例

```json
"ui": {
  "theme": "dark",
  "language": "zh_CN",
  "start_minimized": false,
  "show_notifications": true,
  "window_width": 1024,
  "window_height": 768,
  "remember_position": true,
  "refresh_rate": 1000
}
```

### 高级设置

用于调整系统行为

| 参数                     | 类型   | 默认值   | 说明                                 |
| ------------------------ | ------ | -------- | ------------------------------------ |
| debug_mode               | 布尔值 | false    | 是否启用调试模式，会记录更详细的日志 |
| enable_experimental      | 布尔值 | false    | 是否启用实验性功能                   |
| disable_ssl_verification | 布尔值 | false    | 是否禁用 SSL 证书验证，不推荐        |
| request_timeout          | 整数   | 60       | API 请求超时秒数                     |
| gc_interval              | 整数   | 300      | 垃圾回收间隔（秒）                   |
| process_priority         | 字符串 | "normal" | 进程优先级，支持 low、normal、high   |

#### 缓存设置

| 参数    | 类型   | 默认值 | 说明               |
| ------- | ------ | ------ | ------------------ |
| enabled | 布尔值 | true   | 是否启用内存缓存   |
| size    | 整数   | 100    | 缓存大小限制（MB） |

#### 示例

```json
"advanced": {
  "debug_mode": false,
  "enable_experimental": false,
  "disable_ssl_verification": false,
  "request_timeout": 60,
  "cache": {
    "enabled": true,
    "size": 100
  },
  "gc_interval": 300,
  "process_priority": "normal"
}
```

## 使用模板变量

在配置中的某些字符串值支持使用模板变量，特别是在`caption_template`配置项中。以下是可用的模板变量：

- `{source_chat_title}` - 源频道标题
- `{message_id}` - 原始消息 ID
- `{date}` - 消息日期（格式：YYYY-MM-DD）
- `{time}` - 消息时间（格式：HH:MM:SS）
- `{original_caption}` - 原始消息的字幕内容

## 完整配置示例

以下是一个完整的配置文件示例：

```json
{
  "telegram": {
    "api_id": 12345678,
    "api_hash": "abcdef1234567890abcdef1234567890",
    "session_name": "tg_forwarder",
    "proxy": {
      "enabled": true,
      "type": "socks5",
      "host": "127.0.0.1",
      "port": 1080
    },
    "connection_retries": 5,
    "auto_reconnect": true
  },
  "log": {
    "level": "INFO",
    "console": true
  },
  "forward": {
    "default_mode": "native",
    "caption_template": "转自 {source_chat_title}\n原始消息: {message_id}\n日期: {date}",
    "preserve_media_groups": true
  },
  "source_channels": {
    "channel1": -1001234567890
  },
  "target_channels": {
    "target1": -1001098765432
  }
}
```

## 注意事项

1. 所有配置项均为可选，未指定的项将使用默认值
2. 建议根据自己的需求自定义配置，不需要包含所有选项
3. 涉及 API 凭据的配置项应妥善保管，不要泄露给他人
4. 使用代理时，请确保代理服务器可以正常连接 Telegram 服务器
5. 对于大规模转发任务，建议适当调整`task_manager`和`forward`部分的参数，避免触发 Telegram 的限制
