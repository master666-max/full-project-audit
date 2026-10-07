# -*- coding: utf-8 -*-
"""budget.py —— 预算预估 v2（W3-3 起家，自审真值重定基 2026-10-08，零依赖）。
基线沿革：v1＝B4 试点一 27k token/任务/臂——被自审 12 批 harness 真值否证（低估 6~31×）。
自审实测：池任务（全库粗筛型）均价 ≈827k；语义下钻（锚点直指型）均价 ≈159k；
混合档默认 250k 取两型加权近似。阈值 9M 在真值口径下 ≈25~40 任务/全链。
用法: py -X utf8 budget.py --tasks tasks.jsonl [--arms 5] [--per-task 250000] [--threshold 9000000]
"""
import argparse
import json
import os
import sys


def main():
    ap = argparse.ArgumentParser(allow_abbrev=False)
    ap.add_argument("--tasks", required=True)
    ap.add_argument("--arms", type=int, default=1)
    ap.add_argument("--per-task", type=int, default=250000,
                    help="每任务每臂 token 均值（自审真值重定基：池 827k／下钻 159k／混合默认 250k；"
                         "v1 的 27000 被实测否证）")
    ap.add_argument("--threshold", type=int, default=9000000)
    ap.add_argument("--out", default=None)
    args = ap.parse_args()
    n = sum(1 for line in open(args.tasks, encoding="utf-8") if line.strip())
    est = n * args.per_task * args.arms
    row = (f"| 预估 | 任务 {n} × {args.per_task}/任务/臂 × {args.arms} 臂 = "
           f"{est/1e6:.1f}M token | 基线：自审 12 批真值（池 827k／下钻 159k） |")
    suggest = "建议 TRIMMED" if est > args.threshold else "可按当前档执行"
    print(row)
    print(f"BUDGET 预估 {est/1e6:.1f}M token；阈值 {args.threshold/1e6:.0f}M → {suggest}")
    if args.out:
        with open(args.out, "a", encoding="utf-8") as f:
            f.write(f"- {row}\n- 判定：{suggest}\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
