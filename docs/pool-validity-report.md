# 检查点池有效性调查报告（v0.2.0 · 191 条 · 三路验证）

| 项 | 值 |
|---|---|
| 任务来源 | 用户令："仔细核查＋网络调研，我们的审查条目池是否真的有效，必须深入调查"（2026-10-07） |
| 方法 | 三路交叉：①内部效度（B4 试点 190/191 判定数据机械抽取）②外部对标（CWE Top 25 2025 / OWASP LLM Top 10 2025 / Veracode 2025 实证 / Spracklen 幽灵包研究）③缺口清单与增补提案 |
| 总判定 | **有效，非完备**——判别力过（五板块全有 FAIL）、主流威胁覆盖 70-80%、实证事件类型吻合；缺口集中在"LLM 安全深水区（投毒/嵌入/提示泄漏）＋ C 系内存安全"——v0.3 增补 12 条候选（M1 合入） |

---

## 一、路线一：内部效度（试点数据，机械抽取）

从五份批量报告抽取每个检查点判定（`audit/` 脚本口径，可复算）：

| 指标 | 数值 |
|---|---|
| 全库 191 条 · 有判定 | **190**（唯一无判定：GEN-DOC-001，悬置 RUNTIME-UNVERIFIED——正确行为） |
| 全 N/A | 81（GEN 28 / AIG 6 / LLM 32 / SEC 15） |
| 全 PASS | 60 |
| **含 FAIL** | **46**（GEN 18 / AIG 11 / PER 6 / LLM 5 / SEC 6） |

**结论：判别力成立。** ①五个板块（通用/AI/个人/LLM/安全）全部产出过 FAIL——无"死板块"；②全 N/A 的 81 条集中于"该项目天然没有的面"（DB/前端/CI/依赖/LLM 应用面——受审项目是单机运维工具），属**正确 N/A 而非惰性条目**；③无一条"永远无法判定"（S/R/A/U 四类全部实际使用）。
**限制声明**：单项目（17 文件小库）不能证明对"有 DB/前端/多用户面的项目"的判别力；81 条全 N/A 条目尚未在任何项目上实战检验——下轮换一个含 Web/DB 面的项目复测。

## 二、路线二：外部对标

### 2.A　CWE Top 25 (2025) 对表

| 覆盖档 | 条目 | 判读 |
|---|---|---|
| **直接命中 13/25（52%）** | 79(XSS)=SEC-005／89(SQLi)=SEC-001／352(CSRF)=SEC-016／862=SEC-014／787=SEC-019／22=SEC-003／78=SEC-002／434=SEC-025／502=SEC-004／306=SEC-013／918=SEC-008／77=SEC-002 家族／770=SEC-024 | 安全散点重建的 CWE 映射有效 |
| **部分命中 7/25** | 94(CodeInj)→sinks.py exec/eval 检测半覆盖；476(NULL)→AIG-CORR 边界臆造近邻；863/639(授权变体)→SEC-014 近邻；20(输入校验)→AIG-DEFE 近邻；284(访问控制)→GEN-SEC-003 近邻；200(信息暴露)→SEC-020+LLM-SEC-004 半覆盖 | 需显式化为独立条目或映射标注 |
| **缺口 5/25** | 416(UseAfterFree)／125(越界读)／120／121／122(缓冲区家族) | 全为 C/C++ 内存安全——对个人 AI 工程域低相关，**建议以 gated 条目补齐**（非 C/C++/unsafe Rust 项目自动 N/A） |

### 2.B　OWASP LLM Top 10 (2025) 对表

| # | 类别 | 我们的覆盖 |
|---|---|---|
| LLM01 | Prompt Injection | ✓ LLM-SEC-001/002（直接/间接）+ LLM-RAG-005（经检索） |
| LLM02 | Sensitive Info Disclosure | ✓ LLM-SEC-004（密钥引用×日志×出站交集） |
| LLM03 | Supply Chain | ~ AIG-DEP + SEC-021/022 + 盲区回写候选（unlocked-interpreter-trust）——近邻充分但无独立"模型/组件供应链"条目 |
| LLM04 | Data & Model Poisoning | ✗ **缺口**（训练/微调/嵌入投毒与 L7 RAG 的索引污染均无条目） |
| LLM05 | Improper Output Handling | ✓ LLM-STRUCT 1-4 + LLM-SEC-005（渲染 XSS） |
| LLM06 | Excessive Agency | ✓ LLM-TOOL-003/004（危险工具无授权门/并发无隔离） |
| LLM07 | System Prompt Leakage | ✗ **缺口**（LLM-SEC-001 为近邻，但"系统提示泄漏"未单列） |
| LLM08 | Vector & Embedding Weaknesses | ✗ **缺口**（全库无 embody/vector 关键词条目） |
| LLM09 | Misinformation | ✓ LLM-GROUND 1-4（含弃答路径） |
| LLM10 | Unbounded Consumption | ✓ LLM-COST 1-4 + LLM-LOOP-002 |

**覆盖 7/10 直接＋1 部分（80%），缺口 3（投毒/提示泄漏/嵌入弱点）。**

### 2.C　AI 代码实证对标

- **Veracode《2025 GenAI Code Security Report》**（100+ 模型，Java/JS/Python/C#）：**45% 的测试任务中 AI 生成代码引入真实漏洞**；"更大更新的模型并未改善安全性"。→ 直接支持 AIG-SEC 层与 v1.4 安全回归的决策；也提示 AIG-SEC 条目应对"模型代际"不敏感（实证如此）。
- **Spracklen et al.《We Have a Package for You!》（arXiv 2406.10279，576k 样本 16 模型）**：幽灵包率 **商用模型 ≥5.2%／开源 ≥21.7%**；识别出 **205,474 个唯一幽灵包名**——为 slopsquatting（抢注投毒）提供攻击面。→ 我们已有 AIG-DEP-001（导入未声明包）/AIG-DEP-004（typosquatting）/SEC-022（来源可信度），**但缺"registry 存在性核验"这一关键动作条目**（幽灵包检测的正确动作是查 registry 而非查代码）。
- **OWASP Agentic Security Initiative**（2025-02 指南已发布；2026 Agentic Top 10 清单存在但线上仅见封面描述，逐条类别【待确认】）——池内 LLM-TOOL/LOOP/SEC 为 agentic 近邻覆盖；"多代理信任链""工具/组件供应链"为候选缺口。

## 三、路线三：缺口清单与 v0.3 增补提案（12 条）

| # | 提案条目 | 归属 | 验法 | 依据 |
|---|---|---|---|---|
| 1 | `security-memory-unsafe-*`（UAF/越界读/缓冲区 5 合 1，**gated**：非 C/C++/unsafe Rust 自动 N/A） | 安全散点 | S | CWE Top25 缺口 5 条 |
| 2 | `security-null-deref`（空引用/None 链解引用） | 安全散点 | S | CWE-476 升 8 位 |
| 3 | `security-code-injection`（eval/exec/动态导入的显式注入面，与反序列化分列） | 安全散点 | S | CWE-94 |
| 4 | `security-input-validation`（边界校验缺失，从 AIG-DEFE 显式化） | 安全散点 | S | CWE-20 |
| 5 | `security-authz-variants`（IDOR/纵向越权，从 SEC-014 拆出 639/863） | 安全散点 | S | CWE-639/863 |
| 6 | **`security-package-existence`（包名对 registry 存在性核验——幽灵包专项）** | 安全散点 | R | Spracklen 205k 幽灵名 |
| 7 | `LLM-POISON-001..002`（训练/微调数据投毒面、RAG 索引/嵌入污染面） | LLM 应用 | U/R | OWASP LLM04 |
| 8 | `LLM-SEC-006 系统提示泄漏`（输出中回显系统提示/经错误路径带出） | LLM 应用 | S/R | OWASP LLM07 |
| 9 | `LLM-RAG-006..007`（向量库访问控制、嵌入倒推/相似度倒推敏感内容） | LLM 应用 | S/U | OWASP LLM08 |
| 10 | `agentic-trust-chain`（多代理/跨工具信任链与身份） | LLM 应用 | U | ASI 候选【待确认 2026 清单】 |
| 11 | `agentic-tool-supply-chain`（工具/插件来源与权限供应链） | LLM 应用 | S | ASI 候选 |
| 12 | 陈旧/近邻条目的**映射标注**（476/94/20/284/863/200 六条在现有条目上加 `cwe_map` 字段） | 元数据 | — | 对标可审计化 |

处置：1-6 与 7-9 为**直接增补候选**（M1 合入，模板版本 0.2.0→0.3.0）；10-11 挂 ASI 2026 清单【待确认】后定稿；12 为字段级增补不动条目计数。**现有 191 条维持不删**（内部效度已证无惰性死板块）。

## 四、总判定

1. **有效**：判别力（内·五板块全产出 FAIL）、主流威胁覆盖（外·CWE 52%直接/80%含部分；OWASP LLM 70-80%）、实证事件类型（Veracode 45%、幽灵包）三路一致。
2. **非完备**：12 条增补候选（其中 3 条 OWASP LLM 深水区为实质缺口）。
3. **诚实边界**：全 N/A 的 81 条未经任何项目实战；单项目效度不外推；agentic 清单细节待补查。

## 五、来源

- [CWE Top 25 2025](https://cwe.mitre.org/top25/archive/2025/2025_cwe_top25.html)（XSS 居首；NULL 解引用 +8 位；命令注入 −10 位）
- [OWASP Top 10 for LLM Applications 2025](https://genai.owasp.org/llm-top-10/)（LLM07 系统提示泄漏、LLM08 向量嵌入弱点为 2025 新增面）
- [Veracode 2025 GenAI Code Security Report（2025-10 更新版）](https://www.veracode.com/resources/analyst-reports/2025-genai-code-security-report/)（45% 引入漏洞；模型代际不改善安全）
- [Spracklen et al. arXiv 2406.10279](https://arxiv.org/abs/2406.10279)（幽灵包 5.2%/21.7%；205,474 唯一名）
- [OWASP Agentic Security Initiative 指南（2025-02）](https://genai.owasp.org/resource/agentic-ai-threats-and-mitigations/)——2026 Top 10 逐条类别线上未取到【待确认】
