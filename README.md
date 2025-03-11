# Telegram 频道消息转发工具

这是一个基于 Pyrogram 的 Telegram 频道消息转发工具，能够自动从指定频道获取消息并将其转发到一个或多个目标频道。

## 功能特点

- 支持从公开频道和私有频道获取消息
- 支持指定消息 ID 范围的精确转发
- 支持向多个目标频道同时转发
- 支持多种消息类型（文本、图片、视频、文档等）
- 支持 SOCKS5/SOCKS4 代理设置
- 自动处理连接中断和重试
- 完善的日志记录系统

## 使用方法

1. 复制`config_example.ini`为`config.ini`并填写相关配置
2. 运行`python main.py`开始转发

## 配置说明

```ini
[API]
api_id = 你的API_ID
api_hash = 你的API_HASH
phone_number = 你的电话号码（可选）

[PROXY]
enabled = False
proxy_type = SOCKS5
addr = 127.0.0.1
port = 1080
username =
password =

[CHANNELS]
source_channel = https://t.me/channel_name
target_channels = @channel1,@channel2

[FORWARD]
start_message_id = 0
end_message_id = 0
hide_author = False
delay = 1
```

## 安装依赖

```bash
pip install -r requirements.txt
```
