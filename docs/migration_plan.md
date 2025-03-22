# 迁移计划：从 StorageInterface 到 JsonStorageInterface 和 HistoryTrackerInterface

## 背景

在 v0.2.4 版本中，我们引入了两个新的接口来替代原有的`StorageInterface`：

1. `JsonStorageInterface`：专注于 JSON 文件操作
2. `HistoryTrackerInterface`：专门管理下载、上传和转发历史记录

这一变更符合需求文档中"统一使用 JSON 文件保存历史记录，不使用数据库"的要求。`StorageInterface`包含许多数据库风格的方法（如`query`、`ensure_index`等），这些在基于 JSON 文件的存储实现中是不必要的。

## 当前状态

`StorageInterface`已被标记为废弃，但由于有许多现有代码依赖它，我们采用渐进式迁移策略。

## 迁移步骤

### 1. 确定依赖组件

以下组件当前依赖`StorageInterface`：

- `Application`类（通过`get_storage`方法）
- `Downloader`类
- `Uploader`类
- `StatusTracker`类

### 2. 迁移策略

#### 对于新功能

- 直接使用`JsonStorageInterface`和`HistoryTrackerInterface`
- 不要在新代码中使用`StorageInterface`

#### 对于现有组件

按照以下优先级顺序迁移：

1. **StatusTracker** - 首先迁移这个组件，因为它主要关注历史记录

   - 修改构造函数使用`HistoryTrackerInterface`而非`StorageInterface`
   - 更新所有使用历史记录的方法

2. **Downloader 和 Uploader** - 这些组件需要下载/上传历史记录和临时文件管理

   - 修改构造函数接受`JsonStorageInterface`和`HistoryTrackerInterface`
   - 更新历史记录相关逻辑使用`HistoryTrackerInterface`
   - 更新文件操作使用`JsonStorageInterface`

3. **Application** - 最后迁移此组件
   - 添加`get_json_storage`和`get_history_tracker`方法
   - 更新依赖注入逻辑，为其他组件提供正确的接口实例
   - 更新`get_storage`方法添加废弃警告

### 3. 测试策略

每个组件迁移后执行以下测试：

- 单元测试：确保组件功能正常
- 集成测试：确保组件间交互正常
- 端到端测试：确保用户功能正常

### 4. 完全移除计划

在所有依赖组件都已迁移到新接口后：

1. 更新`Application`类，完全移除`get_storage`方法
2. 移除`StorageInterface`接口
3. 移除`Storage`实现类
4. 更新文档，删除所有对这些废弃组件的引用

## 时间线

- **v0.2.4**：引入新接口，标记旧接口为废弃
- **v0.2.5**：迁移`StatusTracker`
- **v0.2.6**：迁移`Downloader`和`Uploader`
- **v0.2.7**：迁移`Application`，完全移除旧接口

## 注意事项

- 保持向后兼容性，直到完全迁移完成
- 在迁移过程中保持充分的测试覆盖
- 更新文档，反映接口变更
