# my-TG-app

## 项目概述

my-TG-app 是一个基于插件架构的 Telegram 功能增强工具，旨在提供消息转发、媒体下载、频道管理等功能，采用模块化设计以便于扩展和维护。

**版本**: 0.2.1

## 版本记录

### v0.2.1 (2023-03-26)
- 修复客户端插件中未正确设置代理配置的问题
- 修复客户端插件中电话号码类型错误，确保传递给Pyrogram的电话号码为字符串类型
- 优化代理参数处理，支持不同的配置名称格式

### v0.2.0 (2023-03-25)
- 实现客户端插件（ClientPlugin）
- 支持Telegram账号登录和认证
- 支持会话管理和自动重连
- 提供客户端实例访问接口
- 支持代理设置
- 完善配置系统，添加客户端相关配置项

### v0.1.0 (2023-03-24)
- 初始版本发布
- 完成核心架构设计
- 实现基本事件总线
- 实现插件管理器
- 实现配置管理器
- 实现应用上下文
- 创建基础插件接口
- 支持日志记录系统
- 修复模块导入错误，优化项目结构

### 版本规范

本项目遵循[语义化版本 2.0.0](https://semver.org/lang/zh-CN/)规范：

- **主版本号**：当做了不兼容的 API 修改时递增（X.0.0）
- **次版本号**：当做了向下兼容的功能性新增时递增（0.X.0）
- **修订号**：当做了向下兼容的问题修正时递增（0.0.X）

### 版本计划

- **v0.2.0**：实现客户端插件，支持Telegram账号登录和基本操作
- **v0.3.0**：实现转发插件，支持消息转发功能
- **v0.4.0**：实现下载和上传插件，支持媒体处理
- **v0.5.0**：实现任务队列，支持异步任务处理
- **v1.0.0**：完成基本功能集，发布第一个稳定版本

## 功能特点

- **模块化插件系统**: 所有功能通过插件方式加载，便于扩展和定制
- **事件驱动架构**: 采用事件总线实现组件间解耦通信
- **多账户支持**: 支持同时管理多个 Telegram 账户
- **消息转发**: 支持在频道、群组、用户之间转发消息
- **媒体下载**: 支持下载图片、视频、文件等媒体内容
- **任务队列**: 异步处理大量任务，提高性能
- **日志记录**: 详细的日志记录系统，便于排查问题

## 技术架构

### 核心架构

项目采用事件驱动和插件架构设计，主要组件包括：

- **应用核心 (Application)**: 管理应用生命周期和全局状态
- **事件总线 (EventBus)**: 实现组件间通信的消息总线
- **插件管理器 (PluginManager)**: 负责插件的发现、加载和管理
- **配置管理器 (ConfigManager)**: 处理应用配置的加载、保存和监控
- **应用上下文 (Context)**: 提供全局服务和状态访问点

### 插件系统

插件系统包括以下几类主要插件：

- **客户端插件**: 管理与Telegram API的连接和认证
- **转发插件**: 实现消息转发功能
- **下载插件**: 处理媒体内容下载
- **上传插件**: 处理媒体内容上传
- **工具插件**: 提供频道管理等辅助功能

## 安装说明

### 系统要求

- Python 3.8 或更高版本
- 操作系统: Windows, macOS 或 Linux

### 依赖安装

```bash
pip install -r requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple
```

### 配置说明

首次运行时，程序会在 `config` 目录下创建默认配置文件。您需要编辑 `config/user_config.ini` 配置文件，添加您的 Telegram API ID 和 API Hash。

## 使用方法

### 命令行启动

```bash
python main.py [选项]
```

可用选项:
- `-c, --config`: 指定配置文件路径
- `-l, --log-level`: 设置日志级别 (DEBUG, INFO, WARNING, ERROR, CRITICAL)
- `-v, --version`: 显示版本信息

### 基本操作流程

1. 首次运行时，需要进行 Telegram 账号授权
2. 授权完成后，可以通过命令或配置文件设置需要监控的源频道和目标频道
3. 启用所需的插件功能（如转发、下载等）
4. 程序会自动按照设置处理消息和媒体内容

## 插件开发指南

### 创建新插件

要创建新插件，需要继承 `PluginBase` 类并实现 `initialize` 和 `shutdown` 方法：

```python
from my_TG_app.plugins.base import PluginBase

class MyPlugin(PluginBase):
    id = "my_plugin"
    name = "我的插件"
    version = "1.0.0"
    description = "这是一个示例插件"
    
    async def initialize(self):
        # 注册事件处理器
        self.register_event_handler("event.type", self._handle_event)
        return True
    
    async def shutdown(self):
        # 清理资源
        return True
    
    async def _handle_event(self, event_data):
        # 处理事件
        pass
```

### 插件安装

将插件放置在 `plugins` 目录下的适当位置，程序将在启动时自动发现并加载插件。

## 项目计划

### 当前阶段

- [x] 核心架构设计
- [x] 事件总线实现
- [x] 插件基础框架
- [x] 客户端插件实现
- [ ] 转发插件实现
- [ ] 下载插件实现

### 未来计划

- [ ] 图形用户界面
- [ ] 消息过滤和转换
- [ ] 定时任务支持
- [ ] 云端存储集成
- [ ] 移动端支持

## 问题反馈

如果您在使用过程中遇到任何问题，或有任何功能建议，请提交 issue 或联系开发者。

## 贡献指南

欢迎对本项目进行贡献！如果您想要参与开发，请遵循以下步骤：

1. Fork 本仓库
2. 创建您的特性分支 (`git checkout -b feature/amazing-feature`)
3. 提交您的更改 (`git commit -m '添加某些特性'`)
4. 推送到分支 (`git push origin feature/amazing-feature`)
5. 打开一个 Pull Request

在提交代码前，请确保：
- 代码符合项目的代码风格
- 添加了必要的测试
- 更新了相关文档
- 在CHANGELOG.md中记录了更改

## 更新日志

完整的更新历史请查看 [CHANGELOG.md](CHANGELOG.md) 文件。

## 致谢

- [Pyrogram](https://github.com/pyrogram/pyrogram) - 提供Telegram客户端功能
- [Loguru](https://github.com/Delgan/loguru) - 提供日志记录功能
- 所有贡献者和用户

## 许可协议

本项目采用 MIT 许可协议。详见 [LICENSE](LICENSE) 文件。 