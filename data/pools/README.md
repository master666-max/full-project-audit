# 池家族（7 名）

| # | 池 | 条数 | 文件 | 定位 |
|---|---|---|---|---|
| 0 | **full（全量）** | **222** | `../checkpoints.json` | 唯一权威源——其余成员皆由它机械派生 |
| 1 | micro | 29 | `micro.json` | 进门级快速体检（全 critical＋AI 幻觉 API＋agent 循环控制） |
| 2 | quick | 122 | `quick.json` | 通用快速审查（横切高收益面） |
| 3 | security | 55 | `security.json` | 安全专项（CWE 散点＋各安全层＋MCP/agent） |
| 4 | llm-app | 73 | `llm-app.json` | LLM 应用 14 层专项 |
| 5 | agentic | 25 | `agentic.json` | 多代理/MCP 编排专项 |
| 6 | ai-code | 35 | `ai-code.json` | AI 生成代码＋个人工程专项 |

## 不变式（构建时自动断言）

- `security ⊆ quick`、`micro ⊆ quick`（快速档必须收全安全面与进门面）

## 用法与重建

- 用法：任何脚本 `--data data/pools/<池>.json` 即换档；全量用 `--data data/checkpoints.json`。
- 重建：`py -X utf8 scripts/build_pools.py`（派生规则唯一事实源；每个池文件头部 `_pool` 块自带血缘——`derived_from` 记录全量池版本与 sha16）。
