# 扩大化搜查报告（v0.4.0 合入）

| 项 | 值 |
|---|---|
| 触发 | 用户令："审查条目池，扩大化搜查！！！！！" |
| 本轮扫源 | ①OWASP API Security Top 10 (2023) 全十项 ②OWASP MCP Top 10 (2025 v0.1) 全十项 ③MAST 多代理失败分类学（arXiv 2503.13657 主源 definitions.txt，14 模式全文核对）④Lethal Trifecta（Simon Willison/Palo Alto 2026）⑤CWE 2025 Top 10 KEV（在野利用榜） |
| 产出 | **合入 9 条新检查点（205→214，v0.4.0）＋ 1 条 cwe_map 标注；KEV 榜单验证：十条九中一注记——全对齐** |

---

## 一、OWASP API Security Top 10 (2023) 对表

| # | 类别 | 覆盖动作 |
|---|---|---|
| API1 | Broken Object Level Authorization | ✓ SEC-030（v0.3.1） |
| API2 | Broken Authentication | ✓ SEC-013 |
| API3 | Broken Object Property Level Authorization（批量赋值/过度暴露） | ✗→**新增 SEC-032**（cwe-915 家族） |
| API4 | Unrestricted Resource Consumption | ✓ SEC-024＋LLM-COST |
| API5 | Broken Function Level Authorization | ✓ SEC-030（cwe-863） |
| API6 | Unrestricted Access to Sensitive Business Flows（自动化滥用业务流） | ~ 低相关注记（个人项目无高价值业务流时 gated N/A） |
| API7 | SSRF | ✓ SEC-008 |
| API8 | Security Misconfiguration | ~ 由 GEN-SEC-003＋AIG-SEC-002 近邻覆盖 |
| API9 | Improper Inventory Management（影子/僵尸 API） | ✗→**新增 GEN-API-004** |
| API10 | Unsafe Consumption of APIs（信任第三方响应） | ✗→**新增 SEC-033** |

## 二、OWASP MCP Top 10 (2025 v0.1) 对表

| # | 类别 | 覆盖动作 |
|---|---|---|
| MCP01 | Token Mismanagement & Secret Exposure | ✗→**新增 LLM-MCP-003** |
| MCP02 | Privilege Escalation via Scope Creep | ~ LLM-AGENT-001/002 已覆盖 |
| MCP03 | **Tool Poisoning**（工具元数据藏指令） | ✗→**新增 LLM-MCP-001**（Simon Willison 工具投毒先例同源） |
| MCP04 | Software Supply Chain & Dependency Tampering | ✓ LLM-AGENT-002（v0.3.1） |
| MCP05 | Command Injection & Execution | ✓ SEC-002/028 |
| MCP06 | Intent Flow Subversion / Prompt Injection via Contextual Payloads | ~ LLM-SEC-002＋RAG-005 |
| MCP07 | Insufficient Authentication & Authorization | ✓ SEC-013/030 |
| MCP08 | Lack of Audit and Telemetry | ~ LLM-OBS-001/002 |
| MCP09 | **Shadow MCP Servers**（未纳管服务器） | ✗→**新增 LLM-MCP-004**（并入 MCP08 审计项） |
| MCP10 | **Context Injection & Over-Sharing** | ✗→**新增 LLM-MCP-002** |

## 三、MAST 多代理失败分类学（14 模式，主源全文核对）

**System Design**（5）：1.1 违反任务规范／1.2 违反角色规范／1.3 步骤重复／1.4 会话历史丢失／1.5 终止条件失知
**Inter-Agent Misalignment**（6）：2.1 会话重置／2.2 不追问澄清／2.3 任务脱轨／2.4 信息隐匿／2.5 忽视他代理输入／2.6 行动-推理错配
**Task Verification**（3）：3.1 过早终止／3.2 弱验证／**3.3 无验证或错误验证**

覆盖动作：合入单条扫描项 **LLM-AGENT-005**（U 类，14 模式清单化检查）；模式级映射注记：1.5/3.1→LLM-LOOP；2.x→LLM-AGENT-001（通信信任）；3.2/3.3→本体系审计设计本身（盲判/复跑即其对策）。

## 四、Lethal Trifecta（组合风险）

私有数据访问 × 不可信内容摄入 × 外部通信通道，三者同时具备即高危组合（2026 年技能生态实证：生产部署大多三条全占）。覆盖动作：合入 **LLM-AGENT-004**（组合判定：三要素齐备且无隔离即 critical 档候选）。

## 五、CWE Top 10 KEV（在野利用榜）验证结果

| KEV # | 弱点 | 我们的条目 |
|---|---|---|
| 1 | CWE-78 命令注入 | ✓ SEC-002 |
| 2 | CWE-416 UAF | ✓ SEC-026（gated） |
| 3 | CWE-787 越界写 | ✓ SEC-019/026 |
| 4 | CWE-306 关键功能缺认证 | ✓ SEC-013 |
| 5 | CWE-502 反序列化 | ✓ SEC-004 |
| 6 | CWE-22 路径遍历 | ✓ SEC-003 |
| 7 | CWE-94 代码注入 | ✓ SEC-028 |
| 8 | **CWE-288 备用路径/通道认证绕过** | △→**SEC-013 补 cwe_map [287,288]** |
| 9 | CWE-122 堆溢出 | ✓ SEC-026（gated） |
| 10 | CWE-79 XSS | ✓ SEC-005 |

**十条九中——本体系安全散点对"实际被在野利用"的弱点面已全对齐。**

## 六、v0.4.0 合入清单（9 新增＋1 标注）

| id | 层 | 内容 | 验法 | 依据 |
|---|---|---|---|---|
| SEC-032 | 安全散点 | 对象属性级授权缺失/批量赋值（过度暴露与可写字段） | S | API3:2023 |
| SEC-033 | 安全散点 | 不安全消费第三方 API 响应（不校验直接采信） | S/U | API10:2023 |
| GEN-API-004 | 通用·API | API 清单与退役治理（影子端点/旧版本未停用） | S | API9:2023 |
| LLM-MCP-001 | LLM·工具调用 | 工具描述投毒（工具元数据/说明中藏指令） | S/U | MCP03 |
| LLM-MCP-002 | LLM·工具调用 | 上下文注入与过度共享（跨服务器上下文越权互见） | S/U | MCP10 |
| LLM-MCP-003 | LLM·工具调用 | MCP 令牌与密钥管理（存储/传递/权限范围） | S | MCP01 |
| LLM-MCP-004 | LLM·工具调用 | 影子 MCP 服务器＋审计遥测缺失 | S | MCP09+08 |
| LLM-AGENT-004 | LLM·安全 | 致命三要素组合（私有数据×不可信内容×外联） | S | Lethal Trifecta |
| LLM-AGENT-005 | LLM·韧性 | MAST 14 模式多代理失败扫描 | U | MAST |
| — | 标注 | SEC-013 cwe_map=[287,288] | — | KEV #8 |

## 七、诚实边界

- CWE "On the Cusp 15 条"清单 URL 未取到（404，两种命名尝试）【待确认】——下轮补。
- AI Incident Database 未扫（本轮信源已饱和，价值边际低）。
- MAST 模式定义已全文核对（主源 definitions.txt），可信度高；LLM-AGENT-005 为 U 类扫描项（模式清单驱动，不做单模式条目——避免 14 条低判别力条目注水）。
