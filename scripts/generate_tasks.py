# -*- coding: utf-8 -*-
"""generate_tasks.py —— 原子任务生成（AMR 循环 v1，零第三方依赖）。
粗网格（Tier1 池化筛查：每层一个任务，覆盖该层全部 active 检查点 × 全文件集）
→ 加密（Tier2 下钻：critical/high 检查点 × 高 churn 文件，上限 --max-tasks）
→ 停机：Tier2 额度耗尽即停（v1 占位；T3 最优停机规则后续接管）。
输出: atomic-tasks.md + tasks.jsonl + 台账统计。
用法:
  py -X utf8 generate_tasks.py --data ../data/checkpoints.json \
      --enum ../enumeration/files.jsonl --out-dir .. --max-tasks 300
"""
import argparse
import json
import os
import subprocess
import sys


def load_checkpoints(path):
    with open(path, encoding="utf-8") as f:
        doc = json.load(f)
    return doc, [c for c in doc["checkpoints"] if c.get("status") == "active"]


def load_jsonl(path):
    rows = []
    if os.path.exists(path):
        with open(path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    rows.append(json.loads(line))
    return rows


def snapshot(root):
    try:
        out = subprocess.run(["git", "rev-parse", "HEAD"], cwd=root, capture_output=True, timeout=15)
        return out.stdout.decode().strip() if out.returncode == 0 else "NO-GIT"
    except Exception:
        return "NO-GIT"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", required=True)
    ap.add_argument("--enum", required=True)
    ap.add_argument("--out-dir", required=True)
    ap.add_argument("--max-tasks", type=int, default=300)
    ap.add_argument("--tier2-topk", type=int, default=3)
    args = ap.parse_args()

    doc, active = load_checkpoints(args.data)
    enum = load_jsonl(args.enum)
    files = [r["key"] for r in enum if r.get("kind") == "file"]
    churn = {r["key"]: r.get("meta", {}).get("churn", 0) for r in enum if r.get("kind") == "file"}
    snap = snapshot(args.out_dir)
    os.makedirs(args.out_dir, exist_ok=True)

    # Tier1：每层一个池化筛查任务（粗网格＝全文件集）
    by_layer = {}
    for c in active:
        by_layer.setdefault(c["layer"], []).append(c["id"])
    tasks = []
    for i, (layer, cids) in enumerate(sorted(by_layer.items()), 1):
        tasks.append({
            "task_id": f"T1-POOL-{i:03d}", "tier": 1, "layer": layer,
            "checkpoint_ids": cids, "targets": ["<ALL>"],
            "snapshot": snap, "expected_format": "五元组+反证记录（池化筛查：阴性一次排除，阳性转 Tier2 下钻）",
        })

    # Tier2：critical/high 检查点 × 高 churn 文件（加密，额度受限）
    top = sorted(files, key=lambda p: churn.get(p, 0), reverse=True)[: max(args.tier2_topk, 1)]
    t2 = 0
    for c in sorted(active, key=lambda x: {"critical": 0, "high": 1}.get(x["severity_default"], 2)):
        if t2 >= args.max_tasks:
            break
        if c["severity_default"] not in ("critical", "high"):
            continue
        tasks.append({
            "task_id": f"T2-DRL-{t2 + 1:03d}", "tier": 2, "layer": c["layer"],
            "checkpoint_ids": [c["id"]], "targets": top,
            "snapshot": snap, "expected_format": "五元组+反证记录（下钻：单检查点单判定）",
        })
        t2 += 1

    # 覆盖台账：每个 active 检查点必须有 ≥1 任务（池化覆盖即满足）
    cid_tasks = {}
    for t in tasks:
        for cid in t["checkpoint_ids"]:
            cid_tasks.setdefault(cid, []).append(t["task_id"])
    uncovered = [c["id"] for c in active if c["id"] not in cid_tasks]

    with open(os.path.join(args.out_dir, "tasks.jsonl"), "w", encoding="utf-8") as f:
        for t in tasks:
            f.write(json.dumps(t, ensure_ascii=False) + "\n")

    md = ["# atomic-tasks（AMR v1·快照 %s）" % snap, "",
          f"- 总任务数：{len(tasks)}（Tier1 池化 {len(by_layer)} ＋ Tier2 下钻 {t2}）",
          f"- active 检查点：{len(active)}；未被任何任务覆盖：{len(uncovered)}",
          f"- Tier2 目标＝高 churn 前 {len(top)} 文件；停机＝额度 {args.max_tasks} 或穷尽", "",
          "| task_id | tier | layer | checkpoint_ids | targets |", "|---|---|---|---|---|"]
    for t in tasks[:120]:
        tgt = "<ALL>" if t["targets"] == ["<ALL>"] else ", ".join(t["targets"][:3])
        md.append(f"| {t['task_id']} | {t['tier']} | {t['layer']} | {len(t['checkpoint_ids'])} 个 | {tgt} |")
    if len(tasks) > 120:
        md.append(f"| … | | 其余 {len(tasks)-120} 行见 tasks.jsonl | | |")
    with open(os.path.join(args.out_dir, "atomic-tasks.md"), "w", encoding="utf-8") as f:
        f.write("\n".join(md) + "\n")

    print(f"tasks={len(tasks)} tier1={len(by_layer)} tier2={t2} active_ckpt={len(active)} uncovered={len(uncovered)}")
    print("written: tasks.jsonl / atomic-tasks.md")
    return 1 if uncovered else 0


if __name__ == "__main__":
    sys.exit(main())
