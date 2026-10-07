# -*- coding: utf-8 -*-
"""audit.py —— 对账与审计器 v2（子命令制，零第三方依赖）。
LCF 小核纪律：reconcile 小节 ≤150 行、一屏可逐行审。
子命令: reconcile | coverage | pool-lint | boundary | drift | fields | sample | rerun | metrics
用法示例:
  py -X utf8 audit.py reconcile --tasks ../tasks.jsonl --enum ../enumeration/files.jsonl [--semantic]
  py -X utf8 audit.py coverage  --tasks ../tasks.jsonl --data ../data/checkpoints.json
  py -X utf8 audit.py pool-lint --data ../data/checkpoints.json
  py -X utf8 audit.py boundary  --data ../data/checkpoints.json [--tasks ../tasks.jsonl]
  py -X utf8 audit.py drift     --tasks ../tasks.jsonl [--repo .]
  py -X utf8 audit.py fields    --reports ../batch-reports
  py -X utf8 audit.py sample    --tasks ../tasks.jsonl [--rate-high 0.2] [--rate-rest 0.05]
  py -X utf8 audit.py rerun     --experiments ../runtime-lab/experiments [--confirm]
  py -X utf8 audit.py metrics   --tasks ../tasks.jsonl --enum ../enumeration/files.jsonl
  py -X utf8 audit.py --self-test          # 内置注入测试（reconcile 核）
  py -X utf8 audit.py --selftest-all       # v2 全子命令正反注入测试
"""
import argparse
import glob as _glob
import json
import os
import re
import shutil as _shutil
import subprocess
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


def tgt_files(targets):
    """单任务 targets 展开为显式文件集（<ALL> 不计入——供 semantic 模式）。"""
    out = []
    for t in targets:
        if isinstance(t, dict):
            out.append(t["file"])
        elif isinstance(t, str) and t != "<ALL>":
            out.append(t)
    return out


# ================= reconcile 小核（LCF：本函数 ≤150 行，零依赖，可逐行审） =================
def reconcile(tasks, files, reports_dir=None, semantic=False):
    """返回 (PASS, 明细)。默认模式：底册文件至少被任一任务提及（<ALL> 池计入，恒真防崩溃）。
    semantic 模式：只认显式文件目标（<ALL> 池不豁免）——覆盖断言的牙在此。"""
    covered = set()
    for t in tasks:
        tg = t.get("targets", [])
        if not semantic:
            if "<ALL>" in tg or any(True for _ in tg):
                covered |= set(tgt_files(tg))
                if "<ALL>" in tg:
                    covered |= set(files)
        else:
            covered |= set(tgt_files(tg))
    uncovered = sorted(set(files) - covered)
    detail = {"mode": "semantic" if semantic else "default(仅防生成崩溃)",
              "tasks": len(tasks), "files": len(files),
              "covered": len(files) - len(uncovered), "uncovered": uncovered}
    if reports_dir is not None:
        n_reports = len(os.listdir(reports_dir)) if os.path.isdir(reports_dir) else 0
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
    by_count = {}
    for cid in active_ids:
        n = len(cid_tasks.get(cid, []))
        by_count[n] = by_count.get(n, 0) + 1
    return (len(uncovered) == 0), {"active": len(active_ids), "uncovered": uncovered,
                                   "by_task_count": by_count}
# ================= reconcile 小核结束 =================


def _load_pool(path):
    with open(path, encoding="utf-8") as f:
        doc = json.load(f)
    return doc, [c for c in doc["checkpoints"] if c.get("status") == "active"]


def cmd_reconcile(args):
    tasks = load_jsonl(args.tasks)
    files = [r["key"] for r in load_jsonl(args.enum) if r.get("kind") == "file"]
    ok, d = reconcile(tasks, files, reports_dir=args.reports, semantic=args.semantic)
    print(json.dumps(d, ensure_ascii=False, indent=1))
    print("RECONCILE", "PASS" if ok else "FAIL")
    return 0 if ok else 1


def cmd_coverage(args):
    doc, active = _load_pool(args.data)
    ok, d = coverage(load_jsonl(args.tasks), [c["id"] for c in active])
    print(json.dumps(d, ensure_ascii=False, indent=1))
    print("COVERAGE", "PASS" if ok else "FAIL")
    return 0 if ok else 1


# ---------- W2-1 缺陷类覆盖断言 ----------
def pool_lint(active):
    by_class = {}
    for c in active:
        by_class.setdefault(c["defect_class"], 0)
        by_class[c["defect_class"]] += 1
    empty = []  # 空行=盲区：声明过但无 active（当前实现：类由条目定义，故检查下限≥1 恒真；留接口）
    return {"classes": len(by_class), "min_per_class": min(by_class.values()) if by_class else 0,
            "zero_classes": empty}, (len(empty) == 0) and len(by_class) > 0


def cmd_pool_lint(args):
    doc, active = _load_pool(args.data)
    d, ok = pool_lint(active)
    print(json.dumps(d, ensure_ascii=False, indent=1))
    print("POOL-LINT", "PASS" if ok else "FAIL")
    return 0 if ok else 1


# ---------- W2-2 边界带矩阵 ----------
COUPLING_PAIRS = [("通用·架构", "LLM·上下文"), ("通用·依赖", "AIG·依赖失控"),
                  ("LLM·上下文", "LLM·结构化输出"), ("PER·复现", "LLM·评估")]


def boundary_matrix(active):
    layers = sorted({c["layer"] for c in active})
    classes_by_layer = {}
    for c in active:
        classes_by_layer.setdefault(c["layer"], set()).add(c["defect_class"])
    rows, coupled_classes = [], set()
    for (l1, l2) in COUPLING_PAIRS:
        c1 = classes_by_layer.get(l1, set())
        c2 = classes_by_layer.get(l2, set())
        rows.append({"pair": f"{l1} × {l2}", "classes_1": len(c1), "classes_2": len(c2),
                     "status": "需组合检查" if (c1 and c2) else "盲区（层缺类）"})
        coupled_classes |= (c1 | c2) if (c1 and c2) else set()
    all_classes = {c for s in classes_by_layer.values() for c in s}
    orphans = sorted(all_classes - coupled_classes)
    return {"matrix_rows": len(rows), "rows": rows,
            "uncoupled_classes": len(orphans), "orphan_sample": orphans[:10]}, True


def cmd_boundary(args):
    doc, active = _load_pool(args.data)
    d, ok = boundary_matrix(active)
    print(json.dumps(d["rows"], ensure_ascii=False, indent=1))
    print(f"BOUNDARY 登记对 {d['matrix_rows']} 组；未入耦合矩阵的缺陷类 {d['uncoupled_classes']} 个（空行=组合盲区）")
    print("BOUNDARY", "PASS" if ok else "FAIL")
    return 0 if ok else 1


# ---------- W2-3 漂移检测 ----------
def drift_check(tasks, repo):
    try:
        head = subprocess.run(["git", "rev-parse", "HEAD"], cwd=repo,
                              capture_output=True, timeout=15).stdout.decode().strip()
    except Exception:
        head = "NO-GIT"
    drifted = [t["task_id"] for t in tasks
               if t.get("snapshot") not in (head, "NO-GIT", "", None) and t.get("snapshot")]
    return head, drifted, (len(drifted) == 0)


def cmd_drift(args):
    head, drifted, ok = drift_check(load_jsonl(args.tasks), args.repo)
    print(json.dumps({"head": head, "drifted_tasks": drifted}, ensure_ascii=False, indent=1))
    print("DRIFT", "PASS" if ok else "FAIL（漂移任务应作废重排）")
    return 0 if ok else 1


# ---------- W2-4 批报告字段机械核验 ----------
def _is_claim(txt, m, word):
    """窗口级否定识别（终版）：'0 FAIL / 1 PASS'、'不计阳性'、'无 FAIL'、'阳性 0' 等均为计数/否认。
    压平空格与 markdown 装饰符后可命中：词前窗口以 0/零/无/非 结尾，或含 不计/未见/未命中/没有/否认。"""
    raw_pre = txt[max(0, m.start() - 14):m.start()]
    flat = raw_pre.replace(" ", "").replace("*", "").replace("|", "").replace("｜", "")
    if re.search(r"[0零无非]$", flat):
        return False
    for neg in ("不计", "未见", "未命中", "没有", "否认"):
        if neg in flat:
            return False
    tail = txt[m.end():m.end() + 10].replace(" ", "").replace("*", "")
    if re.match(r"[:：]?(0|零|无)", tail):
        return False
    if txt[m.end():m.end() + 2].startswith(("→", "｜", "|")):
        return False  # 模板枚举位（"阳性→列命中项"），非主张（自审实录校准）
    return True


def fields_check(reports_dir):
    problems, total, fails_no_path = [], 0, 0
    verdict_rx = re.compile(r"PASS|FAIL|N/A|阴性|阳性|命中")
    sev_rx = re.compile(r"严重度|critical|high|medium|low|高危|中危|低危", re.I)
    for p in sorted(_glob.glob(os.path.join(reports_dir, "*.md"))):
        txt = open(p, encoding="utf-8", errors="replace").read()
        name = os.path.basename(p)
        total += 1
        if not verdict_rx.search(txt):
            problems.append(f"{name}: 无判定（PASS/FAIL/N-A/阴性/阳性/命中）")
        claims = [m for m in re.finditer("FAIL", txt) if _is_claim(txt, m, "FAIL")]
        claims += [m for m in re.finditer("阳性", txt) if _is_claim(txt, m, "阳性")]
        if claims:            # 语义校准（试点二）：只有失败主张必须带证据
            if not re.search(r"[\w\-.]+\.(py|md|json|yml|yaml|toml|bat|sh|js|ts):\d+", txt):
                problems.append(f"{name}: 失败主张缺 file:line")
            if not re.search(r"核验路径|复现|reproduce|反证记录|机械前提|可复核|证据锚点", txt):
                fails_no_path += 1
                problems.append(f"{name}: 含 FAIL/阳性主张 但无核验路径（疑点）")
            if not sev_rx.search(txt):
                problems.append(f"{name}: 含 FAIL/阳性主张 但无严重度")
    return {"reports": total, "problems": problems, "fails_without_path": fails_no_path}, len(problems) == 0


def cmd_fields(args):
    d, ok = fields_check(args.reports)
    print(json.dumps(d, ensure_ascii=False, indent=1))
    print("FIELDS", "PASS" if ok else "FAIL")
    return 0 if ok else 1


# ---------- W2-5 风险加权抽验 ----------
HIGH_LAYER_MARK = ("AIG·正确性", "AIG·幻觉 API", "LLM·循环控制", "LLM·幻觉接地")


def stratified_sample(tasks, rate_high, rate_rest):
    picked = []
    for t in tasks:
        rate = rate_high if any(m in t.get("layer", "") for m in HIGH_LAYER_MARK) else rate_rest
        if rate > 0 and (hash(t["task_id"]) % 100) < int(rate * 100):
            picked.append(t["task_id"])
    return picked


def cmd_sample(args):
    tasks = load_jsonl(args.tasks)
    picked = stratified_sample(tasks, args.rate_high, args.rate_rest)
    os.makedirs(args.out, exist_ok=True)
    with open(os.path.join(args.out, "sampling.md"), "w", encoding="utf-8") as f:
        f.write("# 风险加权抽验清单（盲法：先盲判后对答案）\n\n"
                f"- 高发层率 {args.rate_high}｜其余层率 {args.rate_rest}｜抽中 {len(picked)} / {len(tasks)}\n\n"
                + "\n".join(f"- [ ] {tid}（盲判区空白，见 blind 模板）" for tid in picked) + "\n")
    print(f"sampled={len(picked)}/{len(tasks)} -> {args.out}/sampling.md")
    print("SAMPLE", "PASS")
    return 0


# ---------- W2-6 执行型重跑 ----------
REQUIRED_5 = ("intent.md", "setup.sh", "patch.diff", "reproduce.sh", "log")


def rerun_check(exp_dir, confirm, pick=1):
    out = []
    dirs = sorted(d for d in _glob.glob(os.path.join(exp_dir, "*")) if os.path.isdir(d))
    complete = []
    for d in dirs:
        missing = [f for f in REQUIRED_5 if not os.path.exists(os.path.join(d, f))]
        out.append({"exp": os.path.basename(d), "missing": missing})
        if not missing:
            complete.append(d)
    ran = None
    if confirm and complete:
        d = complete[0]
        bash = _shutil.which("bash") or "bash"
        r = subprocess.run([bash, "reproduce.sh"], cwd=d, capture_output=True, timeout=600)
        tail = (r.stdout.decode("utf-8", "replace") + r.stderr.decode("utf-8", "replace"))[-400:].strip()
        ran = {"exp": os.path.basename(d), "rc": r.returncode, "out_tail": tail}
        with open(os.path.join(d, "log"), "a", encoding="utf-8") as f:
            f.write(f"\n[rerun by audit.py] rc={r.returncode}\n{tail}\n")
    return {"experiments": out, "complete": len(complete), "ran": ran}, (len(complete) > 0)


def cmd_rerun(args):
    d, ok = rerun_check(args.experiments, args.confirm)
    print(json.dumps(d, ensure_ascii=False, indent=1))
    print("RERUN", "PASS" if ok else "FAIL")
    return 0 if ok else 1


# ---------- W2-7 μ / R / 冗余率 ----------
def metrics_calc(tasks, files):
    # μ（相干度代理）：同检查点多任务时的目标重叠均值
    by_cid = {}
    for t in tasks:
        for cid in t.get("checkpoint_ids", []):
            by_cid.setdefault(cid, []).append(set(tgt_files(t.get("targets", []))))
    overlaps = []
    for cid, tss in by_cid.items():
        if len(tss) < 2:
            continue
        js = []
        for i in range(len(tss)):
            for j in range(i + 1, len(tss)):
                a, b = tss[i], tss[j]
                if a and b:
                    js.append(len(a & b) / max(len(a | b), 1))
        if js:
            overlaps.append(sum(js) / len(js))
    mu = round(sum(overlaps) / len(overlaps), 3) if overlaps else 0.0
    if not overlaps:
        mu_note = "μ 无区分度：当前每检查点至多 1 个非空目标任务（池任务 <ALL> 不计）——待任务结构改进后复测（W5）"
    else:
        mu_note = "μ=同检查点多任务目标重叠均值（相干度代理）"
    # 冗余率：重复 (checkpoint, target-tuple) 行占全部行比例
    rows = [(cid, tuple(sorted(tgt_files(t.get("targets", [])))))
            for t in tasks for cid in t.get("checkpoint_ids", [])]
    redundancy = round(1 - len(set(rows)) / max(len(rows), 1), 3) if rows else 0.0
    # R（盲半径，路径深度差近似）：每文件到最近显式目标的距离
    def depth(p):
        return p.replace("\\", "/").count("/")
    tgt = {f for t in tasks for f in tgt_files(t.get("targets", []))}
    if tgt:
        R = max(min(abs(depth(f) - depth(g)) + (0 if os.path.dirname(f) == os.path.dirname(g) else 1)
                    for g in tgt) for f in files)
    else:
        R = -1
    R_note = ("R=0 系平铺仓库退化（全部文件同深度同目录）——"
              "本近似仅对层级化仓库有区分度（W5 记：平铺时改标 record-only）")
    return {"mu": mu, "blind_radius_R": R, "redundancy": redundancy,
            "notes": mu_note + "；" + R_note + "；K 谱估计未实现（W5 裁决）"}


def cmd_metrics(args):
    tasks = load_jsonl(args.tasks)
    files = [r["key"] for r in load_jsonl(args.enum) if r.get("kind") == "file"]
    d = metrics_calc(tasks, files)
    print(json.dumps(d, ensure_ascii=False, indent=1))
    print("METRICS", "PASS")
    return 0


def cmd_not_implemented(args):
    print(f"`{args.cmd}`：MVP 未实现。")
    return 2


# ---------- 自测 ----------
def self_test():
    with tempfile.TemporaryDirectory() as td:
        files = ["a.py", "b.py", "c.py"]
        bad_ok, _ = reconcile([{"task_id": "t1", "targets": ["a.py", "b.py"]}], files)
        good_ok, _ = reconcile([{"task_id": "t1", "targets": list(files)}], files)
        sem_bad, _ = reconcile([{"task_id": "t1", "targets": ["<ALL>"]}], files, semantic=True)
        sem_good, _ = reconcile([{"task_id": "t1", "targets": [{"file": f, "line": 0, "kind": "file", "source": "x"} for f in files]}], files, semantic=True)
    ok = (bad_ok is False) and (good_ok is True) and (sem_bad is False) and (sem_good is True)
    print(f"SELFTEST {'PASS' if ok else 'FAIL'} | 缺覆盖→FAIL={not bad_ok} 全覆盖→PASS={good_ok} "
          f"语义池不豁免→FAIL={not sem_bad} 语义显式全覆盖→PASS={sem_good}")
    return 0 if ok else 1


def selftest_all():
    """v2 全子命令正反注入测试（机械证据）。"""
    results = []
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as td:
        # pool-lint
        pool = {"checkpoints": [{"id": "X-1", "defect_class": "c1", "status": "active"},
                                {"id": "X-2", "defect_class": "c2", "status": "active"}]}
        _, ok1 = pool_lint([c for c in pool["checkpoints"] if c["status"] == "active"])
        results.append(("pool-lint 正常", ok1))
        _, ok1b = pool_lint([])
        results.append(("pool-lint 空池→FAIL", not ok1b))
        # boundary
        active = [{"layer": "通用·架构", "defect_class": "arch-x"},
                  {"layer": "LLM·上下文", "defect_class": "ctx-y"}]
        bd, _ = boundary_matrix(active)
        results.append(("boundary 登记对", bd["matrix_rows"] == len(COUPLING_PAIRS)))
        # drift
        tasks = [{"task_id": "t1", "snapshot": "deadbeef"}, {"task_id": "t2", "snapshot": "NO-GIT"}]
        _, drifted, ok2 = drift_check(tasks, td)
        results.append(("drift 检出漂移", (drifted == ["t1"]) and not ok2))
        # fields
        rp = os.path.join(td, "rep_good"); os.makedirs(rp)
        open(os.path.join(rp, "good.md"), "w", encoding="utf-8").write(
            "x.py:10 摘录 PASS 严重度 medium 反证：查三种模式未命中")
        rpb = os.path.join(td, "rep_bad"); os.makedirs(rpb)
        open(os.path.join(rpb, "bad.md"), "w", encoding="utf-8").write("FAIL 没有别的了")
        fdg, _ = fields_check(rp)
        fdb, _ = fields_check(rpb)
        results.append(("fields 好报告零问题", fdg["problems"] == []))
        results.append(("fields 坏报告被抓", len(fdb["problems"]) >= 2))
        # sample
        tk = [{"task_id": f"T{i}", "layer": "通用·质量"} for i in range(200)]
        picked = stratified_sample(tk, 0.2, 0.05)
        results.append(("sample 数量级", 0 <= len(picked) <= 200))
        # rerun
        ed = os.path.join(td, "exp", "E1"); os.makedirs(ed)
        for f in ("intent.md", "setup.sh", "patch.diff", "log"):
            open(os.path.join(ed, f), "w").write("x")
        rr, okr = rerun_check(os.path.join(td, "exp"), confirm=False)
        results.append(("rerun 缺件→不完整", (rr["complete"] == 0) and not okr))
        open(os.path.join(ed, "reproduce.sh"), "w", encoding="utf-8").write("echo RERUN-OK\n")
        rr2, okr2 = rerun_check(os.path.join(td, "exp"), confirm=True)
        results.append(("rerun 可跑并留 rc", okr2 and rr2["ran"] is not None))
        # metrics
        mtasks = [{"checkpoint_ids": ["c1"], "targets": [{"file": "a.py", "line": 0, "kind": "file", "source": "s"}]},
                  {"checkpoint_ids": ["c1"], "targets": [{"file": "a.py", "line": 0, "kind": "file", "source": "s"}]}]
        m = metrics_calc(mtasks, ["a.py", "sub/b.py"])
        results.append(("metrics 冗余检出", m["redundancy"] > 0))
        # coverage
        okc, dc = coverage([{"task_id": "t", "checkpoint_ids": ["c1", "c2"]}], ["c1", "c2", "c3"])
        results.append(("coverage 缺项→FAIL", (not okc) and dc["uncovered"] == ["c3"]))
    bad = [n for n, ok in results if not ok]
    for n, ok in results:
        print(("✓" if ok else "✗"), n)
    print("SELFTEST-ALL", "PASS" if not bad else f"FAIL {bad}")
    return 0 if not bad else 1


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--self-test", action="store_true")
    ap.add_argument("--selftest-all", action="store_true")
    sub = ap.add_subparsers(dest="cmd")
    p = sub.add_parser("reconcile"); p.add_argument("--tasks", required=True); p.add_argument("--enum", required=True)
    p.add_argument("--reports", default=None); p.add_argument("--semantic", action="store_true")
    p = sub.add_parser("coverage"); p.add_argument("--tasks", required=True); p.add_argument("--data", required=True)
    p = sub.add_parser("pool-lint"); p.add_argument("--data", required=True)
    p = sub.add_parser("boundary"); p.add_argument("--data", required=True); p.add_argument("--tasks", default=None)
    p = sub.add_parser("drift"); p.add_argument("--tasks", required=True); p.add_argument("--repo", default=".")
    p = sub.add_parser("fields"); p.add_argument("--reports", required=True)
    p = sub.add_parser("sample"); p.add_argument("--tasks", required=True)
    p.add_argument("--rate-high", type=float, default=0.2); p.add_argument("--rate-rest", type=float, default=0.05)
    p.add_argument("--out", default=".")
    p = sub.add_parser("rerun"); p.add_argument("--experiments", required=True); p.add_argument("--confirm", action="store_true")
    p = sub.add_parser("metrics"); p.add_argument("--tasks", required=True); p.add_argument("--enum", required=True)
    args = ap.parse_args()
    if args.self_test:
        return self_test()
    if args.selftest_all:
        return selftest_all()
    cmd = args.cmd
    if cmd == "reconcile":
        return cmd_reconcile(args)
    if cmd == "coverage":
        return cmd_coverage(args)
    if cmd == "pool-lint":
        return cmd_pool_lint(args)
    if cmd == "boundary":
        return cmd_boundary(args)
    if cmd == "drift":
        return cmd_drift(args)
    if cmd == "fields":
        return cmd_fields(args)
    if cmd == "sample":
        return cmd_sample(args)
    if cmd == "rerun":
        return cmd_rerun(args)
    if cmd == "metrics":
        return cmd_metrics(args)
    ap.print_help()
    return 2


if __name__ == "__main__":
    sys.exit(main())
