---
name: full-project-audit
description: Use when 用户要求对某个 AI 工程做一次性全项目审查/全项目体检——接手项目审查、发布前审查、大重构后审查、一次性体检。触发词：全项目体检、全项目审查、接手项目审查、发布前审查、大重构后审查、一次性体检；English: full project audit, take-over review, pre-release audit, one-shot health check, project-wide review.
---

# 全项目审查（full-project-audit）

一次性全项目体检：把项目里真实存在的问题找全、判准、说清，产出带证据链、可复核的问题清单。只做一次性全量；日常增量与合并前审查移交 code-review-and-quality。

## 何时不使用

- 合并前/增量变更审查 → 移交 code-review-and-quality。
- 需合规背书（供应链认证、上线合规）→ 本技能产出工程证据，不是合规结论；高对抗场景叠加 security-audit 或专业渗透测试。
- 目标无版本控制（git）→ 拒绝启动（实验无法存档）。

## 硬约束

- 原始仓库只读；证据行号只认原始仓库；FIX-VERIFIED-ON-COPY 不改 FAIL 判定。
- 密钥纪律（D-004）：安全发现只写位置＋类型＋脱敏指纹，原始密钥值禁止写入任何文件。
- 快照：每个任务携带 commit 快照；批次执行前校验 HEAD，漂移则受影响任务作废重排。
- 完成由对账定义：对账不平，不得收尾。

## 五阶段

1. 预算预估：估任务数与 token/时长，定档（FULL / TRIMMED / CUSTOM），声明评估等级；超阈值降档。
2. 前置解剖（只读）：跑枚举器产出底册（文件/入口/env/工具/prompt/依赖/意图/危险汇聚点）＋ N/A 预判；另做**工作树定性**——`git diff` 未提交改动逐处定性（试点教训：未提交改动是最高频的"半成品缺陷"来源）。
3. 原子任务生成：检查点 × 底册 × 意图 按 AMR 循环展开（池化筛查＋下钻加密），产出任务集与覆盖台账。
4. 执行（自由区）：方法/顺序/并行度/实验设计全放开；按 batch-report 模板产出判定，逐条带证据。
5. 事后审计＋盲区回写：对账、覆盖断言、抽验、重跑；未覆盖发现登记回写模板。

## 五条结果契约

1. 查证五元组：file:line＋整块摘录＋判定＋严重度＋反证记录（PASS 必附；FAIL 豁免）；
2. 只读＋预算上限；
3. N/A 双轨：机械可核验（对照底册）或 JUDGMENT-NA（入人工复核）；
4. 动态证据四元组＋诚实降级三态（RUNTIME-UNVERIFIED / DEFERRED / SKIP-HUMAN，禁止冒充 PASS）；
5. 副本铁律（实验＝commit＋patch.diff＋setup.sh＋log，副本弃）。

## 审计关注点（七项；【】内为实现状态，v0.2.1 如实标注）

计数对账【已实现】｜文件覆盖断言【已实现】＋缺陷类覆盖断言【待实现】｜风险加权抽验·盲法【模板已备，流程待实现】｜执行型重跑【待实现】｜边界带矩阵【待实现】｜判级一致性【周期性体检启用，未实现】｜悬置台账【周期性启用；一次性体检交付悬置清单，未实现】。

## 资产与脚本

- `${CLAUDE_SKILL_DIR}/data/checkpoints.json`：检查点库全量池（214 条；层×子域×验法 S/R/A/U；security-* 对齐 CWE）。
- `${CLAUDE_SKILL_DIR}/data/pools/`：池家族（拔插式——给脚本 `--data` 换池即换档）：micro 29（进门级）｜quick 117（快速通用）｜security 55（安全专项）｜llm-app 73｜agentic 25｜ai-code 34。
- `${CLAUDE_SKILL_DIR}/data/severity-anchors.json`：严重度锚定集 v1.0（已冻结；定级对照）。
- `${CLAUDE_SKILL_DIR}/scripts/enumerate.py`：枚举器八子命令（files｜entry｜env｜tools｜prompts｜deps｜intent｜sinks）。
- `${CLAUDE_SKILL_DIR}/scripts/generate_tasks.py`：任务生成（AMR v1）。
- `${CLAUDE_SKILL_DIR}/scripts/audit.py`：对账器（reconcile｜coverage｜sample｜rerun｜boundary｜suspension）。
- `${CLAUDE_SKILL_DIR}/templates/`：batch-report / experiment 五件套 / blind-review。

运行方式：`py -X utf8 <脚本路径> <子命令> …`（零第三方依赖）。

## 输出

在目标项目内建 `review-{date}/`：enumeration/（底册＋N/A 预判）、atomic-tasks.md＋tasks.jsonl、batch-reports/（每批一份五元组）、runtime-lab/experiments/（五件套）、audit/（对账/抽验/重跑/边界带/终报）。

## 词表

- 证据级别：断言级（读码）/ 执行级（跑测试）/ 复现级（构造触发用例）。
- 悬置三态：RUNTIME-UNVERIFIED / DEFERRED / SKIP-HUMAN。
- 判定：PASS / FAIL / N/A（JUDGMENT-NA 须附撤销条件）。
- **引用格式（强制）**：所有 file:line 一律"完整文件名:行号"（如 `src/agent/loop.py:42`）；省略文件名将导致机械对账低估（试点实测教训）。

> v0.2（2026-10-07）：工作树定性扫描 + 引用格式规范（B4 多臂试点 REFACTOR 产出）。
