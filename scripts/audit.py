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
import hashlib
import json
import math
import os
import re
import shutil as _shutil
import subprocess
import sys
import tempfile


def load_jsonl(path):
    """响亮失败：文件缺失或某行坏 JSON 一律带定位退出（自审 T116/T178：静默返回 [] 会把
    「底册为空」伪装成「一切正常」，下游 reconcile/coverage 全绿地输出废结论）。"""
    if not os.path.exists(path):
        raise SystemExit(f"输入缺失: {path}（若为枚举底册，先跑 enumerate.py 对应子命令）")
    rows = []
    with open(path, encoding="utf-8") as f:
        for i, line in enumerate(f, 1):
            line = line.strip()
            if not line:
                continue
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError as e:
                raise SystemExit(f"{path}:{i}: JSONL 解析失败: {e}")
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
    """检查点覆盖断言。空池=FAIL（自审 T199：空池静默 PASS 会给废任务集盖全绿章）。"""
    if not active_ids:
        return False, {"active": 0, "uncovered": [], "by_task_count": {},
                       "note": "active 集为空——空池不给 PASS"}
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


# ---------- W2-1 池体检（自审 T246/T090 后给真牙：原实现检查下限≥1 恒真） ----------
STATUS_ENUM = {"active", "optional", "deprecated"}


def pool_lint(entries):
    """entries=全部检查点（含非 active）。真检查：重复 id、status 枚举、缺陷类非空、类下限。"""
    seen, dup = set(), []
    illegal_status = []
    for c in entries:
        if c.get("id") in seen:
            dup.append(c.get("id"))
        seen.add(c.get("id"))
        if c.get("status") not in STATUS_ENUM:
            illegal_status.append(f"{c.get('id')}:{c.get('status')}")
    active = [c for c in entries if c.get("status") == "active"]
    by_class = {}
    for c in active:
        by_class.setdefault(c.get("defect_class") or "<空>", 0)
        by_class[c.get("defect_class") or "<空>"] += 1
    d = {"entries": len(entries), "active": len(active), "classes": len(by_class),
         "min_per_class": min(by_class.values()) if by_class else 0,
         "dup_ids": sorted(set(dup)), "illegal_status": illegal_status}
    ok = (not dup) and (not illegal_status) and len(by_class) > 0
    return d, ok


def cmd_pool_lint(args):
    doc, active = _load_pool(args.data)
    d, ok = pool_lint(doc["checkpoints"])
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
    # ok 语义（自审 T246：原硬编码 True 恒真）：至少一组两侧皆有类的登记对才算数；
    # --strict 下未入矩阵的缺陷类（组合盲区）也判 FAIL。
    return {"matrix_rows": len(rows), "rows": rows,
            "uncoupled_classes": len(orphans), "orphan_sample": orphans[:10]}, len(rows) > 0


def cmd_boundary(args):
    doc, active = _load_pool(args.data)
    d, ok = boundary_matrix(active)
    if getattr(args, "strict", False) and d["uncoupled_classes"] > 0:
        ok = False
    print(json.dumps(d["rows"], ensure_ascii=False, indent=1))
    print(f"BOUNDARY 登记对 {d['matrix_rows']} 组；未入耦合矩阵的缺陷类 {d['uncoupled_classes']} 个（空行=组合盲区）")
    print("BOUNDARY", "PASS" if ok else "FAIL" + ("（strict：存在组合盲区）" if getattr(args, "strict", False) else ""))
    return 0 if ok else 1


# ---------- W2-3 漂移检测 ----------
def drift_check(tasks, repo):
    """漂移检测。NO-GIT 快照的任务不可核验——必须响亮列出（自审 T074：
    静默把不可核验当 PASS，等于给未校验的批次盖漂移全绿章）。"""
    try:
        head = subprocess.run(["git", "rev-parse", "HEAD"], cwd=repo,
                              capture_output=True, timeout=15).stdout.decode().strip()
    except Exception:
        head = "NO-GIT"
    drifted, unverifiable = [], []
    for t in tasks:
        snap = t.get("snapshot")
        if not snap or snap == "NO-GIT":
            unverifiable.append(t["task_id"])
        elif snap != head:
            drifted.append(t["task_id"])
    return head, drifted, unverifiable, (len(drifted) == 0)


def cmd_drift(args):
    head, drifted, unverifiable, ok = drift_check(load_jsonl(args.tasks), args.repo)
    print(json.dumps({"head": head, "drifted_tasks": drifted,
                      "unverifiable_tasks": unverifiable}, ensure_ascii=False, indent=1))
    print("DRIFT", "PASS" if ok else "FAIL（漂移任务应作废重排）")
    if unverifiable:
        print(f"DRIFT-UNVERIFIABLE {len(unverifiable)} 任务快照不可核验（NO-GIT）——这批不构成漂移证据",
              file=sys.stderr)
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


CIT_RX = re.compile(r"([\w\-./\\]+\.(?:py|md|json|yml|yaml|toml|bat|sh|ps1|js|ts)):(\d+)")


def _check_citations(txt, repo, broken):
    """引用存在性校验（自审盲法新检出 GROUND-002 的修复：原实现只验格式不验存在，
    虚构 file:line 可穿过全部机械闸）。repo=None 时跳过（无被审根则无从核对）。"""
    if not repo:
        return
    cache = {}
    for m in CIT_RX.finditer(txt):
        rel = m.group(1).replace("\\", "/")
        ln = int(m.group(2))
        key = rel.lower()
        nlines = cache.get(key)
        if nlines is None:
            fp = os.path.join(repo, rel)
            if not os.path.isfile(fp):
                cache[key] = -1
            else:
                with open(fp, "rb") as f:
                    cache[key] = sum(1 for _ in f)
            nlines = cache[key]
        if nlines == -1:
            broken.append(f"{rel}:{ln}（缺文件）")
        elif ln > nlines:
            broken.append(f"{rel}:{ln}（越界，文件仅 {nlines} 行）")


def _check_excerpts(cites, repo, broken):
    """摘录真实性（P2#6）：sidecar citation 带 excerpt 时，摘录去空白后的前 12 字必须
    出现在被引行——格式完美内容编造的"虚构摘录"抓现行。"""
    if not repo:
        return
    for c in cites:
        if not isinstance(c, dict):
            continue
        ex = str(c.get("excerpt", "")).strip()
        rel = str(c.get("file", "")).replace("\\", "/")
        try:
            ln = int(c.get("line", 0) or 0)
        except (TypeError, ValueError):
            continue
        if not ex or not rel or ln < 1:
            continue
        fp = os.path.join(repo, rel)
        if not os.path.isfile(fp):
            continue
        with open(fp, "rb") as f:
            lines = f.read().decode("utf-8", errors="replace").splitlines()
        if ln > len(lines):
            continue
        key = "".join(ex.split())[:12]
        if key and key not in "".join(lines[ln - 1].split()):
            broken.append(f"{rel}:{ln}（摘录与被引行不符）")


def fields_check(reports_dir, repo=None):
    problems, total, fails_no_path = [], 0, 0
    broken = []
    verdict_rx = re.compile(r"PASS|FAIL|N/A|阴性|阳性|命中")
    sev_rx = re.compile(r"严重度|critical|high|medium|low|高危|中危|低危", re.I)
    for p in sorted(_glob.glob(os.path.join(reports_dir, "*.md"))):
        txt = open(p, encoding="utf-8", errors="replace").read()
        name = os.path.basename(p)
        total += 1
        # 结构化 sidecar（<同名>.json）：verdict 非空才权威；空 stub 回退词表扫 .md
        # （P1#2：旧逻辑见 stub 就信，审查员填了 md 忘了 json 会全量误报"缺 verdict"）
        side = os.path.splitext(p)[0] + ".json"
        sc = None
        if os.path.exists(side):
            try:
                with open(side, encoding="utf-8") as f:
                    sc = json.load(f)
            except (json.JSONDecodeError, OSError):
                sc = None
        if sc and sc.get("verdict"):
            if sc["verdict"] in ("FAIL", "命中") and not sc.get("severity"):
                problems.append(f"{name}: sidecar 失败判定缺 severity")
            cites = sc.get("citations", [])
            _check_citations("\n".join(f"{c['file']}:{c.get('line', 0)}" if isinstance(c, dict) else str(c)
                                       for c in cites), repo, broken)
            _check_excerpts(cites, repo, broken)
            continue
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
        _check_citations(txt, repo, broken)
    if broken:
        problems.append(f"引用失效 {len(broken)} 处（缺文件或行号越界）: " + "；".join(sorted(set(broken))[:15]))
    return {"reports": total, "problems": problems, "fails_without_path": fails_no_path,
            "broken_citations": len(broken)}, len(problems) == 0


def cmd_fields(args):
    d, ok = fields_check(args.reports, getattr(args, "repo", None))
    print(json.dumps(d, ensure_ascii=False, indent=1))
    print("FIELDS", "PASS" if ok else "FAIL")
    return 0 if ok else 1


# ---------- W2-5 风险加权抽验 ----------
HIGH_LAYER_MARK = ("AIG·正确性", "AIG·幻觉 API", "LLM·循环控制", "LLM·幻觉接地")


def stratified_sample(tasks, rate_high, rate_rest):
    """稳定抽样：sha256(task_id) 代替内建 hash（自审 T184：PYTHONHASHSEED 随机化令
    抽验清单跨次不可复现，同输入两次运行抽中集合不同）。"""
    picked = []
    for t in tasks:
        rate = rate_high if any(m in t.get("layer", "") for m in HIGH_LAYER_MARK) else rate_rest
        h = int(hashlib.sha256(t["task_id"].encode("utf-8")).hexdigest()[:8], 16)
        if rate > 0 and (h % 100) < int(rate * 100):
            picked.append(t["task_id"])
    return picked


def _check_rate(name, v):
    if not (isinstance(v, float) and math.isfinite(v) and 0 <= v <= 1):
        raise SystemExit(f"--{name} 必须是 0..1 的有限数（自审 T199：inf/nan/负值曾静默抽 0 或崩溃）")


def cmd_sample(args):
    _check_rate("rate-high", args.rate_high)
    _check_rate("rate-rest", args.rate_rest)
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


def rerun_check(exp_dir, confirm, pick="first"):
    """重跑判据（自审 T088/T034 修复）：rc 入判据（rc!=0=FAIL）；bash 不可用=UNVERIFIED
    （绝不静默 PASS，也不崩成 FileNotFoundError）；--pick first|all。"""
    out = []
    dirs = sorted(d for d in _glob.glob(os.path.join(exp_dir, "*")) if os.path.isdir(d))
    complete = []
    for d in dirs:
        missing = [f for f in REQUIRED_5 if not os.path.exists(os.path.join(d, f))]
        out.append({"exp": os.path.basename(d), "missing": missing})
        if not missing:
            complete.append(d)
    ran, unverified = [], None
    if confirm and complete:
        bash = _shutil.which("bash")
        if not bash:
            unverified = "RUNTIME-UNVERIFIED：系统无 bash（Windows 装 Git Bash 后重试）——未执行，不判 PASS"
        else:
            targets = complete if pick == "all" else complete[:1]
            for d in targets:
                r = subprocess.run([bash, "reproduce.sh"], cwd=d, capture_output=True, timeout=600)
                tail = (r.stdout.decode("utf-8", "replace") + r.stderr.decode("utf-8", "replace"))[-400:].strip()
                ran.append({"exp": os.path.basename(d), "rc": r.returncode, "out_tail": tail})
                with open(os.path.join(d, "log"), "a", encoding="utf-8") as f:
                    f.write(f"\n[rerun by audit.py] rc={r.returncode}\n{tail}\n")
    ok = len(complete) > 0 and not unverified and all(r["rc"] == 0 for r in ran)
    return {"experiments": out, "complete": len(complete), "ran": ran,
            "unverified": unverified}, ok


def cmd_rerun(args):
    d, ok = rerun_check(args.experiments, args.confirm, getattr(args, "pick", "first"))
    print(json.dumps(d, ensure_ascii=False, indent=1))
    if d["unverified"]:
        print("RERUN", "UNVERIFIED")
        return 2
    print("RERUN", "PASS" if ok else "FAIL（不完整，或复跑 rc!=0）")
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


# ---------- 自测 ----------
# ---------- W3 终报机械校验（终报规范 v2.0 的执行器） ----------
REQUIRED_SECTIONS = ("档位与等级", "判定分布", "检出率", "组合不确定性", "盲法",
                     "悬置", "评估觉知", "盲区回写")
FORBIDDEN_PHRASES = ("整体没事", "层层都过", "万无一失", "绝对安全", "零风险")


def final_check(report, tasks, reports_dir=None):
    problems = []
    with open(report, encoding="utf-8") as f:
        txt = f.read()
    for s in REQUIRED_SECTIONS:
        if s not in txt:
            problems.append(f"缺必备节：{s}")
    for ph in FORBIDDEN_PHRASES:
        if ph in txt:
            problems.append(f"禁用措辞：{ph}（组合置信度只能声明衰减，不能宣称豁免）")
    if "GOLD" not in txt and "全量跑分" in txt:
        problems.append("非 GOLD 等级不得称「全量跑分」")
    # 快照一致性：任务集快照必须出现在终报里
    try:
        trows = load_jsonl(tasks)
        snaps = {t.get("snapshot") for t in trows if t.get("snapshot") and t.get("snapshot") != "NO-GIT"}
        if snaps and not any(s in txt for s in snaps):
            problems.append("终报未登载任务集快照（可核验性缺失）")
    except SystemExit as e:
        problems.append(f"任务集不可读: {e}")
    # 判定分布对账：终报里的命中数/机械闭环数必须与 batch-reports 聚合一致
    if reports_dir and os.path.isdir(reports_dir):
        hits = pool = closed = 0
        for p in _glob.glob(os.path.join(reports_dir, "*.md")):
            name = os.path.basename(p)
            with open(p, encoding="utf-8", errors="replace") as f:
                t = f.read()
            if name.endswith("POOL.md") and "pool_result" in t:
                pool += 1
            elif "机械关闭（" in t:
                closed += 1
            elif re.search(r"verdict[：:]*\**\s*命中", t):
                hits += 1
        agg = f"命中 {hits}"
        if str(hits) not in txt:
            problems.append(f"终报命中数与报告聚合不符（聚合 {agg}，终报未载该数）")
        if closed and (str(closed) not in txt):
            problems.append(f"终报机械闭环数与聚合不符（聚合 {closed}）")
    # 悬置条款：凡有 RUNTIME-UNVERIFIED，必须附重试条件
    if "RUNTIME-UNVERIFIED" in txt and "重试条件" not in txt and "重试" not in txt:
        problems.append("存在 RUNTIME-UNVERIFIED 但未附重试条件（悬置三态须带出口）")
    # L1 提名条款（W9）：终报载有停机建议，必须载残余敞口计量
    if "L1 提名" in txt and "残余敞口" not in txt:
        problems.append("终报载有 L1 停机建议但未附残余敞口计量（FP1：早停敞口必须被独立计量）")
    d = {"report": os.path.basename(report), "problems": problems}
    return d, len(problems) == 0


def cmd_final_check(args):
    d, ok = final_check(args.report, args.tasks, args.reports)
    print(json.dumps(d, ensure_ascii=False, indent=1))
    print("FINAL-CHECK", "PASS" if ok else "FAIL")
    return 0 if ok else 1


# ---------- D-④ 主张级冲突检测 ----------
def build_facts(tasks_path, enum_dir, data_path, reports_dir=None):
    """机械真值提取器：主张只跟这里的数字对账。"""
    facts = {"tasks_total": sum(1 for l in open(tasks_path, encoding="utf-8") if l.strip())}
    files_path = os.path.join(enum_dir, "files.jsonl")
    facts["files_total"] = sum(1 for l in open(files_path, encoding="utf-8") if l.strip())
    rows = load_jsonl(tasks_path)
    facts["pools"] = sum(1 for t in rows if t.get("task_id", "").endswith("POOL"))
    with open(data_path, encoding="utf-8") as f:
        doc = json.load(f)
    facts["active_checkpoints"] = sum(1 for c in doc["checkpoints"] if c.get("status") == "active")
    facts["template_version"] = doc.get("template_version", "")
    if reports_dir and os.path.isdir(reports_dir):
        facts["reports_total"] = len(_glob.glob(os.path.join(reports_dir, "*.md")))
    return facts


def claims_check(reports_dir, facts):
    """对 batch-reports/*.json sidecar 的 claims 逐条对账：
    同名指标必须相等（数字漂移=FAIL）；facts 没有的指标 record-only；无 claims 的 sidecar 跳过。"""
    mismatches, record_only, checked = [], [], 0
    for p in sorted(_glob.glob(os.path.join(reports_dir, "*.json"))):
        try:
            with open(p, encoding="utf-8") as f:
                sc = json.load(f)
        except (json.JSONDecodeError, OSError):
            continue
        for c in sc.get("claims", []):
            metric, val = c.get("metric"), c.get("value")
            if metric in facts:
                checked += 1
                if facts[metric] != val:
                    mismatches.append(f"{os.path.basename(p)}:{metric} 报告 {val} ≠ 事实 {facts[metric]}")
            else:
                record_only.append(f"{os.path.basename(p)}:{metric}={val}")
    d = {"facts": facts, "claims_checked": checked, "mismatches": mismatches[:20],
         "record_only_n": len(record_only)}
    return d, (len(mismatches) == 0)


def cmd_claims_check(args):
    facts = build_facts(args.tasks, args.enum_dir, args.data, args.reports)
    d, ok = claims_check(args.reports, facts)
    print(json.dumps(d, ensure_ascii=False, indent=1))
    print("CLAIMS-CHECK", "PASS" if ok else "FAIL（报告数字与机械事实不符）")
    return 0 if ok else 1


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
        _, drifted, unver, ok2 = drift_check(tasks, td)
        results.append(("drift 检出漂移", (drifted == ["t1"]) and not ok2))
        results.append(("drift NO-GIT 列不可核验", unver == ["t2"]))
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
            with open(os.path.join(ed, f), "w", encoding="utf-8") as fh:
                fh.write("x")
        rr, okr = rerun_check(os.path.join(td, "exp"), confirm=False)
        results.append(("rerun 缺件→不完整", (rr["complete"] == 0) and not okr))
        open(os.path.join(ed, "reproduce.sh"), "w", encoding="utf-8").write("echo RERUN-OK\n")
        rr2, okr2 = rerun_check(os.path.join(td, "exp"), confirm=True)
        results.append(("rerun 可跑并留 rc", okr2 and rr2["ran"] and rr2["ran"][0]["rc"] == 0))
        with open(os.path.join(ed, "reproduce.sh"), "w", encoding="utf-8") as f:
            f.write("echo BAD >&2\nexit 3\n")
        rr3, okr3 = rerun_check(os.path.join(td, "exp"), confirm=True)
        results.append(("rerun rc!=0 → FAIL", (not okr3) and rr3["ran"][0]["rc"] == 3))
        # coverage 空池
        oke, _ = coverage([{"task_id": "t", "checkpoint_ids": []}], [])
        results.append(("coverage 空池→FAIL", not oke))
        # pool-lint 非法 status
        _, okp = pool_lint([{"id": "Y-1", "defect_class": "c", "status": "actve"}])
        results.append(("pool-lint 非法 status→FAIL", not okp))
        # 抽样稳定：同输入两次一致
        s1 = stratified_sample(tk, 0.2, 0.05)
        s2 = stratified_sample(tk, 0.2, 0.05)
        results.append(("sample 跨进程稳定", s1 == s2 and len(s1) > 0))
        # 引用存在性：真引用过、假引用抓
        rpr = os.path.join(td, "rep_cit"); os.makedirs(rpr)
        srcd = os.path.join(td, "repo"); os.makedirs(srcd)
        with open(os.path.join(srcd, "real.py"), "w", encoding="utf-8") as f:
            f.write("\n".join(f"line{i}" for i in range(1, 21)))
        with open(os.path.join(rpr, "cit.md"), "w", encoding="utf-8") as f:
            f.write("real.py:5 PASS 摘录 严重度 low；real.py:999 FAIL；ghost.py:1 FAIL")
        fdc, _ = fields_check(rpr, repo=srcd)
        results.append(("citation 存在性校验", fdc["broken_citations"] == 2))
        # sidecar 空 stub 回退词表（P1#2）；verdict 非空才权威
        rep_fb = os.path.join(td, "rep_fb"); os.makedirs(rep_fb)
        with open(os.path.join(rep_fb, "T1-SEM.md"), "w", encoding="utf-8") as f:
            f.write("命中 real.py:5 摘录 x 严重度 low")
        with open(os.path.join(rep_fb, "T1-SEM.json"), "w", encoding="utf-8") as f:
            json.dump({"verdict": ""}, f)
        ffb, _ = fields_check(rep_fb, repo=srcd)
        results.append(("sidecar 空 stub→回退词表不误报",
                        all("sidecar" not in p for p in ffb["problems"])))
        rep_sc = os.path.join(td, "rep_sc"); os.makedirs(rep_sc)
        with open(rep_sc and os.path.join(rep_sc, "T2-SEM.md"), "w", encoding="utf-8") as f:
            f.write("占位")
        with open(os.path.join(rep_sc, "T2-SEM.json"), "w", encoding="utf-8") as f:
            json.dump({"verdict": "命中", "severity": "low",
                       "citations": [{"file": "real.py", "line": 5, "excerpt": "line5"},
                                     {"file": "real.py", "line": 6, "excerpt": "凭空捏造的摘录"}]}, f)
        fsc, _ = fields_check(rep_sc, repo=srcd)
        results.append(("摘录真实性校验（真过假抓）", fsc["broken_citations"] == 1))
        # claims-check：数字主张对机械事实（错值 FAIL，真值 PASS）
        ck_rep = os.path.join(td, "rep_ck"); os.makedirs(ck_rep)
        ck_enum = os.path.join(td, "ck_enum"); os.makedirs(ck_enum)
        open(os.path.join(ck_enum, "files.jsonl"), "w", encoding="utf-8").write(
            '{"kind":"file","key":"a.py"}\n')
        ck_pool = os.path.join(td, "ck_pool.json")
        with open(ck_pool, "w", encoding="utf-8") as f:
            json.dump({"checkpoints": [{"id": "Z1", "status": "active"}]}, f)
        ck_tasks = os.path.join(td, "ck_tasks.jsonl")
        with open(ck_tasks, "w", encoding="utf-8") as f:
            f.write(json.dumps({"task_id": "T1-SEM", "checkpoint_ids": ["Z1"]}) + "\n")
        with open(os.path.join(ck_rep, "T1-SEM.json"), "w", encoding="utf-8") as f:
            json.dump({"verdict": "命中", "severity": "low",
                       "claims": [{"metric": "tasks_total", "value": 999}]}, f)
        facts = build_facts(ck_tasks, ck_enum, ck_pool)
        _, okc_bad = claims_check(ck_rep, facts)
        with open(os.path.join(ck_rep, "T1-SEM.json"), "w", encoding="utf-8") as f:
            json.dump({"verdict": "命中", "severity": "low",
                       "claims": [{"metric": "tasks_total", "value": 1},
                                  {"metric": "自定义指标", "value": 42}]}, f)
        d_ck, okc_good = claims_check(ck_rep, facts)
        results.append(("claims 错值→FAIL", (not okc_bad) and facts["tasks_total"] == 1))
        results.append(("claims 真值→PASS＋未知指标 record-only",
                        okc_good and d_ck["record_only_n"] == 1))
        # final-check：全节+快照在载→PASS；禁用措辞→FAIL
        fr = os.path.join(td, "final.md")
        with open(fr, "w", encoding="utf-8") as f:
            f.write("## 1. 档位与等级 SEMI\n## 2. 判定分布 命中 3\n## 3. 检出率\n## 4. 组合不确定性\n"
                    "## 5. 盲法\n## 6. 悬置 RUNTIME-UNVERIFIED 重试条件：补探针后重试\n"
                    "## 7. 评估觉知\n## 8. 盲区回写\n快照 deadbeef 已核验")
        tk2 = os.path.join(td, "t.jsonl")
        with open(tk2, "w", encoding="utf-8") as f:
            f.write(json.dumps({"task_id": "T1", "snapshot": "deadbeef"}) + "\n")
        _, okf = final_check(fr, tk2)
        results.append(("final-check 全节→PASS", okf))
        with open(fr, "a", encoding="utf-8") as f:
            f.write("层层都过，整体没事")
        _, okf2 = final_check(fr, tk2)
        results.append(("final-check 禁语→FAIL", not okf2))
        # L1 条款：载停机建议必附残余敞口（独立夹具——禁语测试的追加会污染同文件）
        fr2 = os.path.join(td, "final_l1.md")
        with open(fr2, "w", encoding="utf-8") as f:
            f.write("## 1. 档位与等级 SEMI\n## 2. 判定分布\n## 3. 检出率\n## 4. 组合不确定性\n"
                    "## 5. 盲法\n## 6. 悬置\n## 7. 评估觉知\n## 8. 盲区回写\n快照 deadbeef\n"
                    "L1 提名：建议停机点 τ=9")
        _, okf3 = final_check(fr2, tk2)
        with open(fr2, "a", encoding="utf-8") as f:
            f.write("\n残余敞口：13%")
        _, okf4 = final_check(fr2, tk2)
        results.append(("final-check L1 条款双向", (not okf3) and okf4))
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
    ap = argparse.ArgumentParser(allow_abbrev=False,
                                 description="对账与审计器 v2（前缀缩写关闭——防 --enum 被静默吞成 --enum-dir，自审 T200）")
    ap.add_argument("--self-test", action="store_true")
    ap.add_argument("--selftest-all", action="store_true")
    sub = ap.add_subparsers(dest="cmd")
    p = sub.add_parser("reconcile", allow_abbrev=False); p.add_argument("--tasks", required=True); p.add_argument("--enum", required=True)
    p.add_argument("--reports", default=None); p.add_argument("--semantic", action="store_true")
    p = sub.add_parser("coverage", allow_abbrev=False); p.add_argument("--tasks", required=True); p.add_argument("--data", required=True)
    p = sub.add_parser("pool-lint", allow_abbrev=False); p.add_argument("--data", required=True)
    p = sub.add_parser("boundary", allow_abbrev=False); p.add_argument("--data", required=True); p.add_argument("--tasks", default=None)
    p.add_argument("--strict", action="store_true", help="存在组合盲区（未入耦合矩阵的缺陷类）即 FAIL")
    p = sub.add_parser("drift", allow_abbrev=False); p.add_argument("--tasks", required=True); p.add_argument("--repo", default=".")
    p = sub.add_parser("fields", allow_abbrev=False); p.add_argument("--reports", required=True)
    p.add_argument("--repo", default=None, help="被审仓根——提供则逐条校验报告引用的 file:line 存在且行号不越界")
    p = sub.add_parser("sample", allow_abbrev=False); p.add_argument("--tasks", required=True)
    p.add_argument("--rate-high", type=float, default=0.2); p.add_argument("--rate-rest", type=float, default=0.05)
    p.add_argument("--out", default=".")
    p = sub.add_parser("rerun", allow_abbrev=False); p.add_argument("--experiments", required=True); p.add_argument("--confirm", action="store_true")
    p.add_argument("--pick", default="first", choices=["first", "all"])
    p = sub.add_parser("metrics", allow_abbrev=False); p.add_argument("--tasks", required=True); p.add_argument("--enum", required=True)
    p = sub.add_parser("final-check", allow_abbrev=False,
                       help="终报机械校验（终报规范 v2.0）：必备节/禁用措辞/快照在载/判定分布对账/悬置出口")
    p.add_argument("--report", required=True)
    p.add_argument("--tasks", required=True)
    p.add_argument("--reports", default=None, help="batch-reports 目录：判定分布交叉对账")
    p = sub.add_parser("claims-check", allow_abbrev=False,
                       help="主张级冲突检测（D-④）：sidecar claims 对机械事实逐条对账")
    p.add_argument("--reports", required=True)
    p.add_argument("--tasks", required=True)
    p.add_argument("--enum-dir", required=True)
    p.add_argument("--data", required=True)
    args = ap.parse_args()
    global _LOGDIR
    _LOGDIR = os.path.dirname(os.path.abspath(getattr(args, "tasks", "") or ".")) or os.getcwd()
    if args.self_test:
        return self_test()
    if args.selftest_all:
        return selftest_all()
    import time as _time
    import runlog
    fn = {"reconcile": cmd_reconcile, "coverage": cmd_coverage, "pool-lint": cmd_pool_lint,
          "boundary": cmd_boundary, "drift": cmd_drift, "fields": cmd_fields,
          "sample": cmd_sample, "rerun": cmd_rerun, "metrics": cmd_metrics,
          "final-check": cmd_final_check, "claims-check": cmd_claims_check}.get(args.cmd)
    if fn is None:
        ap.print_help()
        return 2
    _t0 = _time.time()
    ret = fn(args)
    runlog.append(_LOGDIR, {"script": "audit.py", "argv": sys.argv[1:], "rc": ret,
                            "duration_ms": int((_time.time() - _t0) * 1000),
                            "counts": {"cmd": args.cmd}})
    return ret


_LOGDIR = "."


if __name__ == "__main__":
    try:
        sys.exit(main())
    except SystemExit:
        raise
    except BaseException as e:
        import runlog
        runlog.append(globals().get("_LOGDIR", "."), {"script": "audit.py", "argv": sys.argv[1:], "rc": 1,
                      "error": f"{type(e).__name__}: {e}", "counts": {}})
        raise
