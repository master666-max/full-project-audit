# -*- coding: utf-8 -*-
"""scaffold.py —— review-{date} 产出树脚手架（W3-1/W3-2，零依赖，幂等）。
用法: py -X utf8 scaffold.py --out <项目目录> --date 2026-10-07 --mode FULL --grade SEMI
生成: review-{date}/{meta,enumeration,batch-reports,runtime-lab/experiments,audit} 全树。
已有文件不覆盖（skip 并提示）。
"""
import argparse
import os
import re
import shutil
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
TPL = os.path.join(os.path.dirname(HERE), "templates")

SUBDIRS = ["meta", "enumeration", "batch-reports", "runtime-lab/experiments", "audit"]
AUDIT_STUBS = ["reconciliation.md", "sampling.md", "rerun.md", "cross-layer.md",
               "severity-consistency.md", "suspension-ledger.md", "blindspot-writeback.md"]


def write_if_absent(path, content):
    if os.path.exists(path):
        return "skip"
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        f.write(content)
    return "wrote"


def main():
    ap = argparse.ArgumentParser(allow_abbrev=False)
    ap.add_argument("--out", required=True)
    ap.add_argument("--date", required=True)
    ap.add_argument("--mode", default="FULL", choices=["FULL", "TRIMMED", "CUSTOM"])
    ap.add_argument("--grade", default="SEMI", choices=["GOLD", "SEMI", "REGRESSION", "SMOKE"])
    ap.add_argument("--template-version", default="read from pool")
    args = ap.parse_args()
    # 日期硬校验（自审 T240：--date 无格式校验曾直接拼路径造出目录错置）
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", args.date):
        raise SystemExit(f"--date 必须是 YYYY-MM-DD（实参不安全: {args.date!r}）")

    root = os.path.join(args.out, f"review-{args.date}")
    for d in SUBDIRS:
        os.makedirs(os.path.join(root, d), exist_ok=True)
    acted = []
    # meta 三件
    acted.append(("meta/mode.txt", write_if_absent(
        os.path.join(root, "meta", "mode.txt"),
        f"mode={args.mode}\n集等级={args.grade}\n（非 GOLD 等级不得在报告中称「全量跑分」）\n")))
    acted.append(("meta/template-version.txt", write_if_absent(
        os.path.join(root, "meta", "template-version.txt"), f"{args.template_version}\n")))
    acted.append(("meta/budget.md", write_if_absent(
        os.path.join(root, "meta", "budget.md"), "# 预算预估行（由 budget.py 生成）\n\n# 实际消耗行（回填）\n")))
    # audit 子报告存根
    for s in AUDIT_STUBS:
        acted.append((f"audit/{s}", write_if_absent(
            os.path.join(root, "audit", s), f"# {s[:-3]}（待填）\n")))
    # 终报模板
    tpl_final = os.path.join(TPL, "final-report.md")
    if os.path.exists(tpl_final) and not os.path.exists(os.path.join(root, "audit", "final-report.md")):
        shutil.copy2(tpl_final, os.path.join(root, "audit", "final-report.md"))
        acted.append(("audit/final-report.md", "wrote(from template)"))
    # 空档占位
    acted.append(("atomic-tasks.md", write_if_absent(
        os.path.join(root, "atomic-tasks.md"), "# 原子任务全集（由 generate_tasks.py 生成）\n")))
    for name, st in acted:
        print(f"  {st:22s} {name}")
    print(f"SCAFFOLD OK -> {root}")
    import runlog
    runlog.append(root, {"script": "scaffold.py", "argv": sys.argv[1:], "rc": 0,
                         "counts": {"tree": root, "wrote": sum(1 for _, st in acted if st.startswith("wrote"))}})
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except SystemExit:
        raise
    except BaseException as e:
        import runlog, os
        runlog.append(os.getcwd(), {"script": "scaffold.py", "argv": sys.argv[1:], "rc": 1,
                                    "error": f"{type(e).__name__}: {e}", "counts": {}})
        raise
