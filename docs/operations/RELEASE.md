# RewrZ 发布包生成手册

本文档用于生成可直接上传到 GitHub Release 的干净 ZIP 发布包。

## 1. 目标

发布包脚本默认只做两件事：

- 仅打包 Git 已跟踪文件的当前工作区内容
- 自动排除本地运行环境、缓存、临时文件和发布产物目录

这样可以避免把以下内容误塞进发布包：

- `.venv/`
- `node_modules/`
- `data/`
- `media_uploads/`
- `release/`
- `dist/`
- `__pycache__/`
- `tmp_*`
- `*.log`

## 2. 生成命令

### 2.1 Windows 一键命令

```powershell
.\scripts\build_release_package.ps1 -Version v2026.06.21
```

### 2.2 直接调用 Python

```powershell
.\.venv\Scripts\python.exe .\scripts\build_release_package.py --version v2026.06.21
```

如不传 `--version`，脚本会自动生成：

- `YYYYMMDD-HHMM-提交短哈希`

例如：

- `20260621-1645-a1b2c3d`

## 3. 输出位置

默认输出到：

```text
release/
```

默认文件名格式：

```text
RewrZ-<version>.zip
```

压缩包内会带一层根目录：

```text
RewrZ-<version>/
```

## 4. 推荐发布流程

1. 先清理本地临时文件与无效文档
2. 确认需要发布的代码和文档已经更新完成
3. 运行最小测试或专项回归
4. 执行发布包脚本生成 ZIP
5. 在 GitHub 创建 Release
6. 上传 `release/` 目录下生成的 ZIP

## 5. 使用建议

- 建议先提交或至少自查工作区，确保当前文件就是你想发布的内容
- 未跟踪文件不会进入发布包；如果某个文件需要进入 Release，先纳入版本控制
- `release/` 目录本身已忽略，不会污染仓库
- 如果你准备对外发正式版本，建议把版本号和 Git Tag 保持一致

## 6. 常见问题

### Q1：为什么本地 `.env` 没进发布包？

因为发布脚本默认只打包 Git 已跟踪文件，而 `.env` 属于本地敏感配置，不应该进入公开发布包。

### Q2：为什么媒体和数据库没进发布包？

`data/` 和 `media_uploads/` 属于站点运行数据，不属于源码发布包的一部分。需要迁移站点数据时，应使用备份导出链路，而不是靠 GitHub Release ZIP。

### Q3：如何改发布包输出目录？

```powershell
.\scripts\build_release_package.ps1 -Version v2026.06.21 -OutputDir out
```

或：

```powershell
.\.venv\Scripts\python.exe .\scripts\build_release_package.py --version v2026.06.21 --output-dir out
```
