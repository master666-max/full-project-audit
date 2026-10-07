# -*- coding: utf-8 -*-
"""audit.py —— 对账与覆盖断言（子命令制，零第三方依赖）。
LCF 小核纪律：reconcile 小节 ≤150 行、一屏可逐行审。
子命令: reconcile | coverage | sample | rerun | boundary | suspension
MVP 已实现: reconcile / coverage / --self-test（其余四位为占位，exit 2）。
用法:
  py -X utf8 audit.py reconcile --tasks ../tasks.jsonl --enum ../enumeration/files.jsonl
  py -X utf8 audit.py coverage  --tasks ../tasks.jsonl --data ../data/checkpoints.json
  py -X utf8 audit.py --self-test
"""
import argparse
import json
import os
import sys
import tempfile


def load_jsonl(path):
    rows = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


# ================= reconcile 小核（LCF：本函数 ≤150 行，零依赖，可逐行审） =================
def reconcile(tasks, files, reports_dir=None):
    """返回 (PASS: bool, 明细 dict)。规则唯一：底册每个文件必须被 ≥1 任务覆盖。"""
    covered = set()
    for t in tasks:
        tg = t.get("targets", [])
        if "<ALL>" in tg:
            covered |= set(files)
        else:
            covered |= set(tg)
    uncovered = sorted(set(files) - covered)
    detail = {"tasks": len(tasks), "files": len(files), "covered": len(files) - len(uncovered),
              "uncovered": uncovered}
    if reports_dir is not None:
        n_reports = len([x for x in os.listdir(reports_dir)]) if os.path.isdir(reports_dir) else 0
        detail["reports"] = n_reports
        detail["tasks_missing_report"] = max(len(tasks) - n_reports, 0)
    ok = (len(uncovered) == 0) and (len(tasks) > 0)
    return ok, detail


def coverage(tasks, active_ids):
    cid_tasks = {}
    for t in tasks:
        for cid in t.get("checkpoint_ids", []):
            cid_tasks.setdefault(cid, []).append(t.get("task_id"))
    uncovered = sorted(set(active_ids) - set(cid_tasks))
    state_counts = {}
    for cid in active_ids:
        state_counts[len(cid_tasks.get(cid, []))] = state_counts.get(len(cid_tasks.get(cid, [])), 0) + 1
    return (len(uncovered) == 0), {"active": len(active_ids), "uncovered": uncovered,
                                   "by_task_count": state_counts}
# ================= reconcile 小核结束 =================


def cmd_reconcile(args):
    ok, d = reconcile(load_jsonl(args.tasks), [r["key"] for r in load_jsonl(args.enum) if r.get("kind") == "file"],
                      reports_dir=args.reports)
    print(json.dumps(d, ensure_ascii=False, indent=1))
    print("RECONCILE", "PASS" if ok else "FAIL")
    return 0 if ok else 1


def cmd_coverage(args):
    with open(args.data, encoding="utf-8") as f:
        doc = json.load(f)
    active = [c["id"] for c in doc["checkpoints"] if c.get("status") == "active"]
    ok, d = coverage(load_jsonl(args.tasks), active)
    print(json.dumps(d, ensure_ascii=False, indent=1))
    print("COVERAGE", "PASS" if ok else "FAIL")
    return 0 if ok else 1


def cmd_not_implemented(args):
    print(f"`{args.cmd}`：MVP 未实现（设计书 §7 对应项，按需再建——过度工程纪律）。")
    return 2


def self_test():
    """注入测试：人为缺失覆盖 → 必须 FAIL；补齐 → 必须 PASS。"""
    with tempfile.TemporaryDirectory() as td:
        enum = [{"kind": "file", "key": p} for p in ("a.py", "b.py", "c.py")]
        enum_p = os.path.join(td, "files.jsonl")
        with open(enum_p, "w", encoding="utf-8") as f:
            for e in enum:
                f.write(json.dumps(e) + "\n")
        files = [e["key"] for e in enum]
        bad, d1 = reconcile([{"task_id": "t1", "targets": ["./a.py", "b.py"]}], [p.lstrip("./") for p in files])
        bad2, _ = reconcile([{"task_id": "t1", "targets": ["a.py", "b.py"]}], files)
        good, _ = reconcile([{"task_id": "t1", "targets": list(files)}], files)
    ok = (bad2 is False) and (good is True)
    print(f"SELFTEST {'PASS' if ok else 'FAIL'} | 缺覆盖→FAIL={not bad2} 全覆盖→PASS={good}")
    return 0 if ok else 1


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--self-test", action="store_true")
    sub = ap.add_subparsers(dest="cmd")
    p = sub.add_parser("reconcile"); p.add_argument("--tasks", required=True); p.add_argument("--enum", required=True); p.add_argument("--reports", default=None)
    p = sub.add_parser("coverage"); p.add_argument("--tasks", required=True); p.add_argument("--data", required=True)
    for name in ("sample", "rerun", "boundary", "suspension"):
        sub.add_parser(name)
    args = ap.parse_args()
    if args.self_test:
        return self_test()
    if args.cmd == "reconcile":
        return cmd_reconcile(args)
    if args.cmd == "coverage":
        return cmd_coverage(args)
    if args.cmd:
        return cmd_not_implemented(args)
    ap.print_help()
    return 2


if __name__ == "__main__":
    sys.exit(main())
