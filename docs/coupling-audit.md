# 检查点池耦合审计（问题：池与本项目其他部分是否耦合）

| 项 | 值 |
|---|---|
| 触发 | 用户提问："审查条目池是否与本项目其他部分耦合" |
| 方法 | 机械取证：全库引用点 grep × 三副本 sha256 比对 × 依赖字段消费核查 × 锚定集引用逐条提取 |
| 总判定 | **结构性解耦良好**——审查引擎对池是"可插拔"的（除 schema 字段名外零内容耦合；池可整体替换，"树是假设件"在工程上成立）；唯一实操隐患＝三副本手工同步（本次已修）；另发现"params 声明未接线"与"README 版本漂移"两处，前者留作接线前的对照表项、后者已修 |

---

## 一、耦合矩阵（组件 × 池）

| 组件 | 耦合类型 | 依赖面（机械取证） | 风险 | 处置 |
|---|---|---|---|---|
| `scripts/generate_tasks.py` | **硬读（设计内）** | 仅 4 个字段：`id/layer/status/severity_default` | 字段重命名会 KeyError——但 fail-fast，可接受 | schema 变更纪律（见 §三） |
| `scripts/audit.py`（coverage 子命令） | **硬读（设计内）** | 仅 2 个字段：`id/status` | 同上 | 同上 |
| `scripts/enumerate.py` / reconcile 算法 | **零耦合** | 不读池（grep 无引用） | 无——项目侧完全独立 | 保持 |
| `data/severity-anchors.json`（v1.0 冻结） | **软引用（极低）** | 机械提取结果：**条目 ID 零引用**；仅 1 处**前缀级**引用（"LLM-LOOP 类"）＋1 处版本戳（`drawn_from: 检查点库 v0.3.0`） | 只要不改 id 前缀命名即无悬空风险 | 纪律：**ID 前缀名视为破坏性变更** |
| `SKILL.md` / `templates/` | 路径级引用 | 仅文件名（`${CLAUDE_SKILL_DIR}/data/checkpoints.json`） | 无内容耦合 | 无 |
| `pilot/` 工件（tasks.jsonl/batch-reports） | **历史快照** | 试点时点的 checkpoint_ids（v0.1.0→0.2.0 期） | 不追池＝正确行为（历史证据冻结） | 无（版本戳已在批量报告内） |
| `params` 字段（214 条全员携带） | **声明未接线** | 脚本 grep：**零消费者** | 将来接线时词表与枚举器输出仅部分可映射——`file_glob/entrypoint/sink=/env_key/tool_name/prompt_path` 可映射到 enumerate 的 kind；`model_config/retry_config/timeout_config/budget_config/cache_config/…`（约 17 个）**无对应枚举器** | 接线前先出《params 词表↔枚举器输出对照表》；当前状态如实标注为"接口预留，未接线" |
| 装机位 ×2（~/.zcode/skills 与 ~/.agents/skills） | **复制体** | 全文件复制 | **漂移风险（唯一实操隐患）**——此前同步全凭手工 | ✅ **已修**：`audit/sync_install.py`（同步＋三处 sha256 校验，漂移即报） |
| `README.md` | 文档引用 | 版本号字样 | 漂移（写 v0.1.0/191 条，实为 v0.4.0/214 条） | ✅ **已修**（本次刷新） |

## 二、三副本一致性快照（审计时点）

```
工程区         583958fb419bb9ce   checkpoints.json
装机(.zcode)   583958fb419bb9ce   ← 一致
装机(.agents)  583958fb419bb9ce   ← 一致
```
（此后由 sync_install.py 承担校验，不再依赖手工比对。）

## 三、结论与纪律

1. **池是可插拔件**：审查引擎的算法（reconcile/coverage/task 生成）只依赖池的 6 个字段名，不依赖任何内容语义——换掉整个池，引擎照跑（这正是设计书"42 层树是可替换的假设件"的工程兑现）。
2. **锚定集与池的低耦合是意外的好消息**：冻结时对池只留了前缀级引用，真正锁死锚定集的是 B4 试点证据（受审项目文件:行号，外部工件）而非池条目。
3. **新增纪律两条**（写入工单附录建议）：
   - schema 变更纪律：池字段名变更＝破坏性变更，须同步改 generate_tasks/coverage 并复跑冒烟；
   - ID 前缀冻结：`GEN-/AIG-/PER-/LLM-/SEC-/LLM-MCP-/LLM-AGENT-` 前缀名视同公开接口，改名须走版本递增与引用清单刷新。
4. **待办一项**：params 接线对照表（接线时执行；当前如实登记"未接线"）。
