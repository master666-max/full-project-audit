# 终报规范（final-report）v2.0

> 定位：本文件既是模板也是**规范**——每节给出〔必填〕〔写作规范〕〔机械校验〕三条。
> 带 ✓ 的条目由 `audit.py final-check --report <本件> --tasks tasks.jsonl --reports batch-reports` 机械执行；
> 终报未过 final-check 不得交付（与 reconcile 同级的收尾门）。
> 总纪律：**能被机械核验的结论才允许写成确定性语气**；其余必须带证据级别限定词
> （断言级/执行级/复现级）或悬置三态（RUNTIME-UNVERIFIED/DEFERRED/SKIP-HUMAN）。

## 1. 档位与等级 ✓

〔必填〕档位（FULL/TRIMMED/CUSTOM）｜集等级（GOLD/SEMI/REGRESSION/SMOKE）｜模板版本（checkpoints.json template_version＋条数）｜快照（任务集 snapshot，逐字登载）｜评审时间窗。
〔写作规范〕**非 GOLD 不得出现「全量跑分」字样**；档位若有裁撤，逐项列裁撤物＋判据（禁 silent-trim）。
〔机械校验〕final-check：快照字串必须在报告内；「全量跑分」与 GOLD 互斥。

## 2. 判定分布 ✓

〔必填〕任务数/报告数/对账结论（reconcile 模式与 PASS/FAIL）｜三级判定计数表（池：阳性/混合/阴性；下钻：命中/未命中/N-A；机械闭环数）｜命中按严重度分布（critical/high/medium/low）｜悬置三态计数（RUNTIME-UNVERIFIED/DEFERRED/SKIP-HUMAN）。
〔写作规范〕数字必须与 batch-reports 聚合**逐位一致**——本节是全报告唯一允许出现的计数来源，别处引用同一数字。
〔机械校验〕final-check：命中数与机械闭环数和 reports 聚合交叉对账。

## 3. 检出率 / 精确率对账 ✓

〔必填〕注入基准（有则逐点表：注入 N→命中 M＋未命中逐条原因；无则写"无注入基准"并注明检出率解释力受限）｜精确率抽验（抽 n→复核真 k＋假阳清单）｜翻案清单（池误阴/误阳、严重度修正，逐条链接报告）。
〔写作规范〕无注入基准时**禁止**给出"检出率 X%"的绝对表述，只允许"在无觉知/无金标条件下的相对结论"。
〔机械校验〕无独立器（人工节），但本节引用的 file:line 受 fields --repo 全量校验。

## 4. 组合不确定性预算 ✓

〔必填〕边界带矩阵登记对数＋未入耦合矩阵的缺陷类数（`audit.py boundary` 输出）｜本报告**能承诺**的组合级结论（逐条附证据级别）｜**明确不能承诺**的区域清单。
〔写作规范〕警示语（禁用措辞，final-check 抓）："整体没事"、"层层都过"、"万无一失"、"绝对安全"、"零风险"。正确表述：组合置信度**低于**各层之积的直觉；组合风险只由边界带登记＋抽验管理，不消除（无切消定理）。

## 5. 盲法记录与执行重跑 ✓

〔必填〕盲判抽样数/不一致率/按预注册判据的处置（转核心/退役/持平）｜盲判自身漏检数（同源审计的诚实度量）｜执行型重跑清单（实验 id/rc/与判定相容性；log 在 runtime-lab/experiments/）。
〔写作规范〕凡"执行级/复现级"结论必须给出对应实验目录名；无实验支持的"复现级"表述是虚报。

## 6. 悬置与腐烂清单 ✓

〔必填〕每个 RUNTIME-UNVERIFIED/DEFERRED/SKIP-HUMAN 项：**重试条件**（何时刻、用什么手段可解除）｜腐烂清单（超期悬置，首轮可写"无"并注明核验方式）。
〔机械校验〕final-check：出现 RUNTIME-UNVERIFIED 而无"重试条件"字样即 FAIL。

## 7. 评估觉知披露 ✓

〔必填〕注入是否私有新造（对照 Muse Spark 公开基准 19.8% vs 私有 2.0% 识别率）｜"检出率为无觉知条件下上界"声明是否适用（自审/觉知场景必须显式否认并降级解释力）｜D-004 密钥纪律合规声明。
〔写作规范〕自审或标准公开的场景，检出的绝对数值**只能作下界使用**并写明。

## 8. 盲区回写（G9）✓

〔必填〕本轮发现的覆盖外问题：登记＋建议归属层＋拟新增检查点（零盲区须显式声明"本轮零盲区"并给核验方式）。
〔写作规范〕每条回写须指明"哪类项目会踩、现池哪一层查不到"——写不出的不算盲区，算缺陷，归第 2/3 节。

## 9. 修复台账（可选节；全修轮启用）

〔必填〕A/B/C/D 四档处置表（A 已落地/B 部分/C 合规裁剪/D 真欠账）；D 档逐项：现状/为何欠/落地路径/成本估/撤销条件。**"既不做也不裁"是本规范的唯一禁止态。**

---

### 交付门（收尾序列，全部 PASS 才算完）

```
py -X utf8 scripts/audit.py reconcile --tasks tasks.jsonl --enum enumeration/files.jsonl --semantic
py -X utf8 scripts/audit.py coverage  --tasks tasks.jsonl --data data/checkpoints.json
py -X utf8 scripts/audit.py fields    --reports batch-reports --repo <被审根>
py -X utf8 scripts/audit.py final-check --report audit/final-report.md --tasks tasks.jsonl --reports batch-reports
```
