# agentic 缺口闭合：OWASP 2026 清单挖掘结果 ＋ 候选定案 ＋ 技能自查

| 项 | 值 |
|---|---|
| 触发 | 用户问："agentic 那两条和 OWASP 2026 清单细节是啥玩意"——把此前【待确认】挂起的两条候选研究到位并定案 |
| 来源 | ①OWASP Top 10 for Agentic Applications（2025-12 发布，ASI01-10）；②OWASP Agentic Skills Top 10（AST10, v1.0-2026，更新至 2026-03）；③交叉验证：构建者解读文与技能安全统计（Snyk ToxicSkills 2026-02） |
| 产出 | 合入 3 条新检查点（202→205，v0.3.1）；ASI01-10 全覆盖映射；**本技能对照 AST10 自查表** |

---

## 一、OWASP Top 10 for Agentic Applications（2025-12，官方清单）

| # | 类别 | 我们池内覆盖 |
|---|---|---|
| ASI01 | Agent Goal Hijack（提示注入中途劫持 agent 目标） | ✓ LLM-SEC-001/002（直接/间接注入）+ LLM-RAG-005 |
| ASI02 | Tool Misuse & Exploitation（合法工具被武器化） | ✓ LLM-TOOL-003/004 |
| ASI03 | Identity & Privilege Abuse（身份继承/权限越权） | ✗→**本次并入 LLM-AGENT-001** |
| ASI04 | Agentic Supply Chain（插件/MCP/第三方工具被控） | ~→**本次并入 LLM-AGENT-002**（+已有 SEC-021/022 包级） |
| ASI05 | Unexpected Code Execution（生成代码无沙箱执行） | ~ SEC-028（代码注入）+ LLM-TOOL-003（授权门）——部分覆盖，维持现状并注记 |
| ASI06 | Memory & Context Poisoning（记忆/RAG 投毒） | ✓ LLM-POISON-001/002（v0.3.0 刚补） |
| ASI07 | Insecure Inter-Agent Communication（代理间消息未校验） | ✗→**本次并入 LLM-AGENT-001** |
| ASI08 | Cascading Failures（单点失败级联） | ✗→**本次并入 LLM-AGENT-003** |
| ASI09 | Human-Agent Trust Exploitation（对 agent 输出过度信任） | ✓ 设计层覆盖（证据级别/置信度陈述/不确定性仪表——即本体系的目的函数本身） |
| ASI10 | Rogue Agents（无攻击者亦越界运行） | ✗→**本次并入 LLM-AGENT-003** |

> 注：ASI 系列材料多版本流转（另见一种早期口径含 Prompt Injection/Insecure Output 等命名变体）；本表采用 2025-12 官方发布版命名。

## 二、候选定案：两条扩为三条，全部合入（v0.3.1）

| 新条目 | 回答的问题 | 归属层 | 验法 | 依据 |
|---|---|---|---|---|
| `LLM-AGENT-001` 身份与权限滥用＋代理间信任链 | 子代理/工具是否继承超范围身份与权限？代理间消息/委派是否无校验（谁都能指挥谁）？ | LLM·安全 | S/U | ASI03+ASI07 |
| `LLM-AGENT-002` 工具与插件供应链 | MCP server/插件/第三方工具的来源、权限声明与更新链是否可信与锁定？ | LLM·工具调用 | S | ASI04（+AST01/02 技能侧） |
| `LLM-AGENT-003` 级联失败与失控代理 | 多步骤/多代理链路的单点失败传播是否有熔断/全局停止开关？agent 是否可能在无攻击者情况下越界持续运行？ | LLM·韧性 | S/U | ASI08+ASI10 |

（原挂起两候选：`agentic-trust-chain`→LLM-AGENT-001、`agentic-tool-supply-chain`→LLM-AGENT-002；另按清单补齐第三项 LLM-AGENT-003。）

## 三、额外发现：OWASP Agentic Skills Top 10（AST10）——管"技能"本身的十条

**这是我们技能生态自己的威胁清单**（覆盖 OpenClaw SKILL.md / Claude Code skill.json / Cursor·Codex manifest / VS Code package.json）。行业实测：Snyk 扫描 3,984 个技能——**36.82% 有缺陷、13.4% 严重**、76+ 确认恶意载荷；ClawHavoc 行动投毒 1,184 个技能（Antiy CERT 2026-02）；Claude Code 相关 RCE（CVE-2025-59536/21852）。

| # | 风险 | 本技能（full-project-audit）自查 |
|---|---|---|
| AST01 | Malicious Skills | ✓ 自产自用、脚本无网络无混淆；分发给他人时按本表重审 |
| AST02 | Supply Chain Compromise | ✓ 强项：零第三方依赖（LCF）、不远程拉取任何指令/依赖 |
| AST03 | Over-Privileged Skills | ✓ 契约级最小权限：目标仓库只读；仅写自己的 review 输出目录 |
| AST04 | Insecure Metadata | ✓ frontmatter 校验入验收（首行/正则/长度） |
| AST05 | Untrusted External Instructions | ✓ 运行期不拉取外部指令；data/templates 均本地 |
| AST06 | Weak Isolation | △ 部分：契约级只读而非沙箱级——脚本以用户权限执行（技能机制固有限制，如实登记） |
| AST07 | Update Drift | ✓ 版本纪律（template_version/v1.0 锚定集/git 锚） |
| AST08 | Poor Scanning | △ 自测充分（self-test＋注入测试）但无第三方扫描器；接入 skill 扫描器为后续项 |
| AST09 | No Governance | ✓ 台账/审计/签字留痕齐全（本工程区先例） |
| AST10 | Cross-Platform Reuse | △ 部分：已双目录装机跨工具，但脚本为 Windows 专属（py 启动器/CMD），Linux/macOS 未适配 |

结论：6✓ / 3△ / 0✗——`本技能自身通过 AST10 自查的工程级基线`；三处△（隔离级别/扫描器/跨平台）如实登记为后续项。

## 四、状态

- 检查点库 v0.3.0 → **v0.3.1**（202→205 条；agentic 缺口全闭合，ASI01-10 除 ASI05/ASI09 为设计层覆盖外全部有实体条目）。
- 挂起的【待确认】全部消除（本周剩余的"待确认"仅记忆库/主权问题除外）。
