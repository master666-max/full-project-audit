# -*- coding: utf-8 -*-
"""t3_shadow.py —— T3 最优停机 · 影子模式（零依赖）。
机制完整：读批次台账 → 逐批估"下一批期望信息价值 EVI" → 给出停机点建议。
影子语义：只计算与落盘（t3-shadow.md），**不驱动任何实际停机**；执行停机仍按额度（v1）。
台账格式（每批一行 JSONL）：
  {"batch_id":1,"tasks":16,"sev":{"critical":0,"high":2,"other":6},"tokens":8647488}
用法: py -X utf8 t3_shadow.py --ledger batch-ledger.jsonl [--out .]
参数（可配，默认=任意价值单位）:
  --v-crit 100 --v-high 30 --v-low 5   价值权重；--cost-per-mtoken 1.0  成本单价（单位/Mtoken）
"""
import argparse
import json
import os
import sys


def load_ledger(p):
    rows = []
    for line in open(p, encoding="utf-8"):
        line = line.strip()
        if line:
            rows.append(json.loads(line))
    return sorted(rows, key=lambda r: r["batch_id"])


def main():
    ap = argparse.ArgumentParser(allow_abbrev=False,
                                 description="T3 影子停机（不驱动停机；价值权重未校准——自审 12 批真值下 EVI 全程>0，待下轮预注册重定基）")
    ap.add_argument("--ledger", required=True)
    ap.add_argument("--out", default=".")
    ap.add_argument("--v-crit", type=float, default=100)
    ap.add_argument("--v-high", type=float, default=30)
    ap.add_argument("--v-low", type=float, default=5)
    ap.add_argument("--cost-per-mtoken", type=float, default=1.0)
    args = ap.parse_args()

    rows = load_ledger(args.ledger)
    if not rows:
        print("台账为空"); return 1

    def value(sev):
        return sev.get("critical", 0) * args.v_crit + sev.get("high", 0) * args.v_high + sev.get("other", 0) * args.v_low

    cum_tasks = cum_val = cum_tok = 0.0
    table, stop_at, reasons = [], None, []
    for i, r in enumerate(rows):
        v = value(r.get("sev", {}))
        tok = r.get("tokens", 0)
        cum_tasks += r.get("tasks", 0); cum_val += v; cum_tok += tok
        # 下一批 EVI 估计：用近两批的"每任务价值产率"外推
        recent = rows[max(0, i - 1): i + 1]
        rate = sum(value(x.get("sev", {})) for x in recent) / max(sum(x.get("tasks", 0) for x in recent), 1)
        next_tasks = r.get("tasks", 0) or 1
        next_cost = args.cost_per_mtoken * (r.get("tokens", 0) / 1e6) if r.get("tokens") else 0.0
        evi = rate * next_tasks - next_cost
        table.append({"batch": r["batch_id"], "tasks": r.get("tasks", 0), "batch_value": v,
                      "cum_tasks": int(cum_tasks), "cum_value": round(cum_val, 1),
                      "cum_tokens_M": round(cum_tok / 1e6, 1),
                      "next_EVI": round(evi, 2), "stop_recommend": evi < 0})
        if evi < 0 and stop_at is None:
            stop_at = r["batch_id"]
            reasons.append(f"批次 {r['batch_id']} 后 EVI({evi:.2f}) < 0：按影子口径建议停机")

    lines = ["# T3 停机 · 影子记录（**不驱动实际停机**；执行判据仍为额度上限 v1）", "",
             f"- 台账：{os.path.basename(args.ledger)}；价值权重 crit/high/low = {args.v_crit}/{args.v_high}/{args.v_low}；成本单价 = {args.cost_per_mtoken}/Mtoken",
             "- 影子语义：本文件只做建议与留痕；停机参数须经下轮预注册埋点校准后才可接管", "",
             "| 批次 | 任务 | 本批价值 | 累计任务 | 累计价值 | 累计成本(M) | 下一批EVI | 影子建议停 |",
             "|---|---|---|---|---|---|---|---|"]
    for t in table:
        lines.append(f"| {t['batch']} | {t['tasks']} | {t['batch_value']} | {t['cum_tasks']} | {t['cum_value']} | {t['cum_tokens_M']} | {t['next_EVI']} | {'★停' if t['stop_recommend'] else ''} |")
    lines += ["", f"**影子结论**：{'；'.join(reasons) if reasons else '未达停机点（EVI 全程为正）'}", ""]
    out = os.path.join(args.out, "t3-shadow.md")
    open(out, "w", encoding="utf-8").write("\n".join(lines))
    print(f"T3-SHADOW: 批次 {len(table)}｜影子停机点: {stop_at if stop_at else '无（全程 EVI>0）'} -> {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
