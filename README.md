# full-project-audit · AI 全项目审查

一次性**全项目体检**技能：把一个项目里真实存在的问题**找全、判准、说清**，产出带证据链、可复核的问题清单。

> 本仓库是方法论工件：检查点库（214 条）＋ 可拔插池家族 ＋ 零依赖脚本 ＋ 报告模板。
> 适用的运行环境：支持 Agent Skills 的编码代理（Claude Code / ZCode 等）。

## 是什么

- **检查点库**（`data/checkpoints.json`）：45 层 × 子域 × 检查点，每条标注验法（S 静态／R 运行／A 消融／U 推断）、严重度、缺陷类、**失效模式来源**。
- **池家族**（`data/pools/`）：由全量池机械派生，`--data` 换池即换档：
  | 池 | 条数 | 定位 |
  |---|---|---|
  | micro | 29 | 进门级快速体检 |
  | quick | 117 | 通用快速审查 |
  | security | 55 | 安全专项 |
  | llm-app | 73 | LLM 应用专项 |
  | agentic | 25 | 多代理/MCP 专项 |
  | ai-code | 34 | AI 生成代码专项 |
- **三件套脚本**（零第三方依赖）：`enumerate.py`（八子命令前置解剖）、`generate_tasks.py`（原子任务生成）、`audit.py`（对账与覆盖断言）。
- **模板**：batch-report（证据五元组）、experiment 五件套、盲判记录。

## 快速开始

```bash
py -X utf8 scripts/enumerate.py files --root <项目> --out enumeration/files.jsonl
py -X utf8 scripts/generate_tasks.py --data data/checkpoints.json --enum enumeration/files.jsonl --out-dir .
py -X utf8 scripts/audit.py reconcile --tasks tasks.jsonl --enum enumeration/files.jsonl
py -X utf8 scripts/audit.py coverage  --tasks tasks.jsonl --data data/checkpoints.json
py -X utf8 scripts/audit.py --self-test
```

## 设计原则（摘要）

1. **完成由对账定义**——"做完了"不是模型的自我申报，是覆盖断言与计数对账全绿。
2. **证据五元组**——file:line ＋ 整块摘录 ＋ 判定 ＋ 严重度 ＋ 反证记录，缺一不计入统计。
3. **诚实降级**——RUNTIME-UNVERIFIED / DEFERRED / SKIP-HUMAN 三态禁止冒充 PASS。
4. **只读审查**——目标仓库只读；实验在副本进行；副本用完即弃。
5. **零依赖小核**——对账核心短到可一屏逐行审（LCF 纪律）。

## 威胁面覆盖（四轮外部对标）

CWE Top 25 / Top-10 KEV（在野利用榜）／OWASP LLM Top 10、API Top 10、MCP Top 10、Agentic Top 10（ASI）、Agentic Skills Top 10（AST10）／MAST 多代理失败分类学。对标报告见 `docs/`。

## 安全模型与自查

- 目标仓库只读；仅写自己的审查输出目录。
- 零第三方依赖、运行期不拉取外部指令（对照 OWASP AST10 技能威胁清单自查：6 过 / 3 部分）。
- 报告密钥纪律：只写位置与脱敏指纹，不落原始值。

## 已知限制

- 脚本当前为 Windows 优先（`py` 启动器 / cmd 路径），跨平台未适配。
- 锚定集样例已**脱敏**（去掉本地文件名）；本仓库不含任何真实项目的漏洞细节。
- 无第三方技能扫描器接入（AST10 自查的登记项）。

## 许可

MIT License。
