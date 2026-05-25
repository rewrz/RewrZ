# RewrZ 开发文档

本文档面向二次开发者，覆盖架构、约束、开发流程、测试与提交流程。

## 1. 项目现状与设计目标

RewrZ 当前处于开发收敛阶段，优先目标是：
- 模型一致性
- 代码可维护性
- 安全基线可验证

不以历史兼容为默认目标。

## 2. 开发架构硬约束（必须遵守）

### 2.1 内容模型约束
- `post_type` 只允许：`post`、`page`
- `article` / `micro` / `poem` 是内容意图（formats），不是 `post_type`
- 图片/视频/音频/外链属于媒体附件能力层

### 2.2 兼容策略约束
- 不默认新增历史兼容分支
- 发现旧数据冲突时，优先一次性迁移/修复，不在运行时加 fallback

### 2.3 文案约束
- 注释、提示、报错优先中文

## 3. 技术栈与分层

- 后端：FastAPI + SQLAlchemy + Pydantic
- 前端：Jinja2 + HTMX + Tailwind CSS
- 数据库：SQLite（默认）
- 测试：pytest

分层结构：
- `api/`：路由与请求处理
- `crud/`：数据库操作
- `models/`：ORM 模型
- `schemas/`：请求/响应模型
- `core/`：配置、安全、模板上下文、基础服务

## 4. 目录概览

```text
rewrz/
  api/
  core/
  crud/
  models/
  schemas/
  templates/
  static/
tests/
alembic/
```

## 5. 本地开发流程

### 5.1 启动
```bash
python -m venv .venv
# Windows
.venv\Scripts\activate
pip install -r requirements.txt
npm install
npm run build:css
uvicorn rewrz.main:app --reload
```

### 5.2 数据库迁移
```bash
alembic revision --autogenerate -m "描述"
alembic upgrade head
```

### 5.3 运行测试
```bash
pytest -q
```

### 5.4 前端样式构建
```bash
npm run build:css
```

开发时如果需要边改模板边看样式变化：
```bash
npm run watch:css
```

需要重新构建的典型场景：
- 修改 `rewrz/templates/` 中的 Tailwind 类名
- 修改 `rewrz/static/js/` 中会动态写入 Tailwind 类名的逻辑
- 修改 `tailwind.config.js`

提交前要求：
- 本地 Tailwind 编译产物已更新
- 前台 `site-tailwind.css` 与后台 `admin-tailwind.css` 均可正常生成

## 6. 安全开发要求

### 6.1 鉴权与 CSRF
- 管理后台写操作必须同时具备：
  - 登录态（`get_current_user`）
  - CSRF 校验（`verify_csrf_token`）

### 6.2 上传与导入
- 上传使用流式写入，禁止 `await file.read()` 整包读入大文件
- 导入 ZIP 必须做解包安全校验（路径穿越、压缩比、总大小、单文件大小）

### 6.3 Cookie 与会话
- 通过配置控制 `secure cookie` 与 `https_only session`
- 生产建议在 HTTPS 下启用：
  - `COOKIE_SECURE=true`
  - `SESSION_HTTPS_ONLY=true`

## 7. 关键代码路径

- 应用入口：`rewrz/main.py`
- 配置：`rewrz/core/config.py`
- 安全：`rewrz/core/security.py`
- 文章模型与约束：`rewrz/crud/post.py`
- 内容意图：`rewrz/core/content_intents.py`
- 媒体接口：`rewrz/api/media.py`
- 数据导入导出：`rewrz/api/data_import_export.py`

## 8. 开发规范与建议

### 8.1 提交前检查
1. 代码可运行
2. 受影响测试通过
3. 全量测试可通过（至少在提交前跑一次）
4. 必要文档同步更新

### 8.2 常见反模式
- 在 CRUD 底层提前 `commit`，破坏外层事务一致性
- 为“可能有旧数据”新增运行时兼容分支
- 在管理写接口漏加 CSRF
- 上传/导入路径未做边界校验

## 9. 文档协同

- 文档中心：[`docs/INDEX.md`](../INDEX.md)
- 面向使用者的文档在：[`USAGE.md`](USAGE.md)
- 面向项目概览与定位的文档在：[`README.md`](../../README.md)

当功能改动涉及行为变化时，至少同步更新上述一个或多个文档。

## 10. 贡献建议

- 新功能优先做最小可用实现，再补测试
- 安全与模型一致性问题优先级高于样式与文案
- 对高风险改动（鉴权、导入、上传、会话）建议附测试
