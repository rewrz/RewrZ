# RewrZ 文档中心

本目录是项目文档中枢，面向“使用者 + 维护者 + 二次开发者”。

## 快速导航

| 目标 | 建议阅读 |
|---|---|
| 本地运行与线上部署 | [`guides/USAGE.md`](guides/USAGE.md) |
| 开发入门与协作约束 | [`guides/DEVELOPMENT.md`](guides/DEVELOPMENT.md) |
| 架构总览与关键设计 | [`architecture/ARCHITECTURE.md`](architecture/ARCHITECTURE.md) |
| 数据模型与关系 | [`architecture/DATA_MODEL.md`](architecture/DATA_MODEL.md) |
| API 约定与安全要求 | [`architecture/API_CONVENTIONS.md`](architecture/API_CONVENTIONS.md) |
| API 到 APP 的实现路径 | [`architecture/API_APP.md`](architecture/API_APP.md) |
| 生产部署手册 | [`operations/DEPLOYMENT.md`](operations/DEPLOYMENT.md) |
| 生产更新手册 | [`operations/UPDATE.md`](operations/UPDATE.md) |
| 故障排查与运维检查 | [`operations/TROUBLESHOOTING.md`](operations/TROUBLESHOOTING.md) |
| 版本变更记录 | [`operations/CHANGELOG.md`](operations/CHANGELOG.md) |
| 当前路线与下一步方向 | [`planning/ROADMAP.md`](planning/ROADMAP.md) |
| 当前 API 边界状态 | [`planning/API_BOUNDARY_LEGACY_AUDIT.md`](planning/API_BOUNDARY_LEGACY_AUDIT.md) |
| 当前测试基线 | [`testing/TEST_BASELINE.md`](testing/TEST_BASELINE.md) |
| 常用开发命令速查 | [`references/常用开发命令.md`](references/常用开发命令.md) |

## 目录规划（避免重复）

| 目录 | 职责边界 | 不要写什么 |
|---|---|---|
| `guides/` | 面向使用与开发流程（部署、运行、协作） | 架构细节与数据模型推导 |
| `architecture/` | 系统分层、模型关系、API 约定、流程图 | 逐条部署命令 |
| `operations/` | 排障、变更记录、运维检查项 | 功能愿景与长期规划 |
| `planning/` | 当前路线、边界决策、仍有效的后续方向 | 过时的阶段性推进过程 |
| `testing/` | 当前测试基线、真实环境验收结论 | 失效的中间测试记录 |
| `references/` | 高频命令与速查表 | 设计决策与背景说明 |

文档去重规则：
- `README.md` 只保留项目定位、亮点和文档入口，不承载细节手册。
- 具体步骤只保留一处权威来源，其他文档统一使用链接引用。
- 行为变化优先更新对应“主文档”，避免在多处复制同一段说明。

## 阅读顺序建议
1. 新接手项目：`ARCHITECTURE -> DATA_MODEL -> API_CONVENTIONS`
2. 直接修 Bug：`TROUBLESHOOTING -> API_CONVENTIONS -> 对应模块代码`
3. 计划做新功能：`ROADMAP -> ARCHITECTURE -> DEVELOPMENT`

## 文档维护规则
- 功能行为变化时，至少同步更新一份文档。
- 涉及接口行为变更，必须更新 `API_CONVENTIONS.md` 或 `CHANGELOG.md`。
- 涉及部署与运维变化，必须更新 `USAGE.md` 或 `TROUBLESHOOTING.md`。
- 涉及测试基线或真实验收变化，必须更新 `docs/testing/` 下对应主文档。
