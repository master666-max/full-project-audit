# -*- coding: utf-8 -*-
"""budget.py —— 预算预估 v1（W3-3，零依赖）。
基线出处：B4 试点一（17 文件副本，5 臂合计 ≈22.2M token；单臂 P50≈4.4M / P90≈6.5M）。
v1 公式: 预估总 = 任务数 × 每任务 token 均值 × 臂数；超过阈值（默认 9M）建议 TRIMMED。
用法: py -X utf8 budget.py --tasks tasks.jsonl [--arms 5] [--per-task 27000] [--threshold 9000000]
"""
import argparse
import json
import os
import sys


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--tasks", required=True)
    ap.add_argument("--arms", type=int, default=5)
    ap.add_argument("--per-task", type=int, default=27000,
                    help="每任务每臂 token 均值（基线：B4 试点 22.2M/(160×5)≈27750）")
    ap.add_argument("--threshold", type=int, default=9000000)
    ap.add_argument("--out", default=None)
    args = ap.parse_args()
    n = sum(1 for line in open(args.tasks, encoding="utf-8") if line.strip())
    est = n * args.per_task * args.arms
    row = (f"| 预估 | 任务 {n} × {args.per_task}/任务/臂 × {args.arms} 臂 = "
           f"{est/1e6:.1f}M token | 基线：试点一（P50 臂 4.4M / P90 6.5M） |")
    suggest = "建议 TRIMMED" if est > args.threshold else "可按当前档执行"
    print(row)
    print(f"BUDGET 预估 {est/1e6:.1f}M token；阈值 {args.threshold/1e6:.0f}M → {suggest}")
    if args.out:
        with open(args.out, "a", encoding="utf-8") as f:
            f.write(f"- {row}\n- 判定：{suggest}\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
