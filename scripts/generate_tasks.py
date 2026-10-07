# -*- coding: utf-8 -*-
"""generate_tasks.py —— 原子任务生成 v1.5（语义接线版，零依赖）。
v1.5（落地工单 W1-2）：
  - 目标三级优先：①语义（params×枚举底册）②意图对照物 ③热区 fallback；
  - 目标格式升级为 {file,line,kind,source} 锚点（兼容 <ALL> 池目标）；
  - 池形态 v1.5：一级模块数>1 时按（层×模块）分池；池任务带 pool_result=未跑 待填；
  - 台账列：target_source（语义/意图/热区/池化）、intent_refs。
用法:
  py -X utf8 generate_tasks.py --data ../data/checkpoints.json --enum-dir enumeration \\
      --out-dir . [--max-tasks 300（下钻）] [--max-pools 0（池）] [--max-targets 8]
上限分层（自审 T072 修正）：--max-tasks 只约束语义下钻；池=粗筛强制层不受它截断，池数用 --max-pools 管。
"""
import argparse
import glob as _glob
import json
import os
import re
import subprocess
import sys

# ---------- W1-1 params↔枚举器对照（唯一事实源；check_params_map.py 校验全覆盖） ----------
PARAM_TARGETS = {
    # params 词 -> (枚举 kind | "files", 关键词过滤 or None)；"files" 走 glob/关键词 fallback
    "file_glob": ("files", None),
    "entrypoint": ("entry", None),
    "env_key": ("env", None),
    "tool_name": ("tools", None),
    "prompt_path": ("prompts", None),
    "sink_type": ("sinks", None),
    "schema_path": ("files", ("schema",)),
    "index_path": ("files", ("index", "vector", "faiss", "chroma", "store")),
    "memory_store": ("files", ("memory", "mem0", "recall")),
    "session_store": ("files", ("session",)),
    "trace_store": ("files", ("trace", "telemetry", "langfuse")),
    "model_config": ("files", ("model", "llm", "infer")),
    "retry_config": ("files", ("retry", "backoff")),
    "timeout_config": ("files", ("timeout",)),
    "budget_config": ("files", ("budget", "cost", "token")),
    "cache_config": ("files", ("cache",)),
    "log_config": ("files", ("log",)),
    "concurrency_config": ("files", ("concurren", "async", "thread", "queue")),
    "stream_path": ("files", ("stream",)),
    "render_path": ("files", ("render", "template", "html")),
    "api_endpoint": ("files", ("api", "route", "endpoint", "client")),
}
SINK_TYPE_ALIAS = {  # sink= 取值 -> sinks.jsonl 的 meta.type 关键词
    "eval-exec": ("eval", "exec", "dynamic-import"),
    "file-write": ("file-write",),
    "network": ("subprocess",),          # 近似：命令执行面
    "html": ("html-inject",),
    "yaml": ("yaml-unsafe", "pickle"),
    "cmd": ("subprocess", "os-system"),
}
GATE_LANG_EXT = {"c-cpp-rust-unsafe": (".c", ".h", ".cpp", ".cc", ".hpp", ".rs")}

# 参数词（阈值/规模类）——不作为目标，仅提示；机械识别，显式登记
PARAM_PARAM_RX = re.compile(
    r"(threshold|_level$|_count$|_size$|duration|_range$|iterations|tokens|length"
    r"|styles|occurrences|_mb$|window|_points$|crossing|merge_window|default_branch$)")
# fallback 关键词派生的停止词（结构词，不承载定位信息）
KW_DROP = {"patterns", "pattern", "glob", "dir", "path", "list", "set", "sources",
           "source", "config", "spec", "map", "names", "call", "api", "file",
           "candidate", "public", "runtime", "doc", "ghost", "points"}


def fallback_keywords(word):
    parts = [p for p in word.split("_") if p and p not in KW_DROP]
    return tuple(parts) if parts else (word,)


def load_jsonl(p):
    """响亮失败：底册文件缺失=SystemExit（自审 T074：静默返回 [] 曾产出 175 个零锚点任务
    且 exit 0——「空底册」被伪装成「一切正常」）。空文件合法（该面无命中）。"""
    if not os.path.exists(p):
        raise SystemExit(f"枚举底册缺失: {p}——先跑 enumerate.py 对应子命令（八器全集见 README）")
    rows = []
    with open(p, encoding="utf-8") as f:
        for i, line in enumerate(f, 1):
            line = line.strip()
            if not line:
                continue
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError as e:
                raise SystemExit(f"{p}:{i}: JSONL 解析失败: {e}")
    return rows


def load_pool(path):
    with open(path, encoding="utf-8") as f:
        doc = json.load(f)
    return doc, [c for c in doc["checkpoints"] if c.get("status") == "active"]


CODE_EXT = (".py", ".js", ".ts", ".tsx", ".jsx", ".go", ".rs", ".java", ".c", ".cpp",
            ".h", ".hpp", ".rb", ".php", ".sh", ".bat", ".ps1", ".sql")


def pick_rows(kind, kw, rows, max_targets):
    """v1.5.1 锚点适配修复：files 类优先取代码文件（试点二教训：按字母序取前 8 个
    全是配置文件与文档，导致 SEC/性能类语义任务锚点不含主体代码）。"""
    if kw is None:
        picked = rows
    else:
        picked = [r for r in rows if any(k in (r.get("key") or "").lower() for k in kw)]
    if kind == "files" and picked:
        code = [r for r in picked if str(r.get("key", "")).lower().endswith(CODE_EXT)]
        if code:
            picked = code + [r for r in picked if r not in code]
    return picked[:max_targets]


def resolve_params_targets(params, enum, max_targets):
    """按对照表把 params 解析为语义目标锚点。返回 (targets, gate_note)。"""
    targets, gate_note = [], None
    for p in params or []:
        p = str(p)
        if p.startswith("gate:"):
            lang = p.split("=", 1)[1] if "=" in p else ""
            exts = GATE_LANG_EXT.get(lang, ())
            files = [r["key"] for r in enum.get("files", [])]
            if exts and not any(f.lower().endswith(exts) for f in files):
                gate_note = f"gated:语言面不存在（{lang}）"
            continue
        key, _, val = p.partition("=")
        if key == "sink" and val:
            types = SINK_TYPE_ALIAS.get(val, (val,))
            for r in enum.get("sinks", []):
                t = str(r.get("meta", {}).get("type", ""))
                if any(k in t for k in types):
                    targets.append({"file": r["file"], "line": r.get("line", 0),
                                    "kind": "sink", "source": f"params:sink={val}"})
            continue
        if key == "dep" and val == "registry-check":
            for r in enum.get("deps", [])[:max_targets]:
                targets.append({"file": r["file"], "line": r.get("line", 0),
                                "kind": "dep", "source": "params:dep-registry"})
            continue
        spec = PARAM_TARGETS.get(key)
        if not spec:
            if PARAM_PARAM_RX.search(key):
                continue  # 参数词：非目标（阈值/规模），显式跳过
            spec = ("files", fallback_keywords(key))  # fallback：关键词派生，来源标注
            src_tag = f"params:{key}(fallback)"
        else:
            src_tag = f"params:{key}"
        kind, kw = spec
        rows = enum.get(kind, []) if kind != "files" else enum.get("files", [])
        picked = pick_rows(kind, kw, rows, max_targets)
        for r in picked:
            targets.append({"file": r["file"], "line": r.get("line", 0),
                            "kind": kind, "source": src_tag})
    # 去重
    seen, uniq = set(), []
    for t in targets:
        k = (t["file"], t["line"], t["kind"])
        if k not in seen:
            seen.add(k)
            uniq.append(t)
    return uniq[:max_targets], gate_note


def main():
    ap = argparse.ArgumentParser(allow_abbrev=False,
                                 description="原子任务生成 v1.5（前缀缩写关闭——README 曾因 --enum 被吞进 --enum-dir 静默产出空底册，自审 T200）")
    ap.add_argument("--data", required=True)
    ap.add_argument("--enum-dir", required=True)
    ap.add_argument("--out-dir", required=True)
    ap.add_argument("--max-tasks", type=int, default=300,
                    help="下钻任务上限（只管 Tier2；池为粗筛强制层，不受此限——自审 T072 修正）")
    ap.add_argument("--max-pools", type=int, default=0, help="池任务上限（0=不限；多模块大库防池爆炸）")
    ap.add_argument("--max-targets", type=int, default=8)
    ap.add_argument("--churn-topk", type=int, default=3)
    ap.add_argument("--repo", default=None, help="快照来源目录（默认=out-dir；被审项目与产出目录分离时必填）")
    ap.add_argument("--pool-mode", default="module", choices=["module", "single"],
                    help="池粒度：module=层×模块（默认，多模块大库）；single=层×全库（目录即模块的工具型项目，防池爆炸）")
    ap.add_argument("--report-skeletons", action="store_true",
                    help="预生成每任务报告骨架＋sidecar stub 到 <out-dir>/batch-reports/（D-A 词表单源）")
    args = ap.parse_args()

    doc, active = load_pool(args.data)
    cps = {c["id"]: c for c in doc["checkpoints"]}
    enum = {}
    for kind in ("files", "entry", "env", "tools", "prompts", "deps", "intent", "sinks"):
        enum[kind] = load_jsonl(os.path.join(args.enum_dir, f"{kind}.jsonl"))
    files = [r["key"] for r in enum["files"]]
    churn = {r["key"]: r.get("meta", {}).get("churn", 0) for r in enum["files"]}
    intent_refs = [r["file"] for r in enum.get("intent", [])][:8]
    try:
        snap = subprocess.run(["git", "rev-parse", "HEAD"], cwd=args.repo or args.out_dir,
                              capture_output=True, timeout=GIT_SNAP_TIMEOUT)
        snapshot = snap.stdout.decode().strip() if snap.returncode == 0 else "NO-GIT"
    except Exception:
        snapshot = "NO-GIT"
    os.makedirs(args.out_dir, exist_ok=True)

    def module_of(path):
        parts = path.replace("\\", "/").split("/")
        return parts[0] if len(parts) > 1 else "ROOT"

    modules = sorted({module_of(f) for f in files})
    by_layer = {}
    for c in active:
        by_layer.setdefault(c["layer"], []).append(c["id"])

    tasks, t_next = [], 0

    def add(task):
        nonlocal t_next
        t_next += 1
        task["task_id"] = f"T{t_next:03d}-{task.pop('_tag')}"
        task["snapshot"] = snapshot
        task["intent_refs"] = intent_refs
        tasks.append(task)

    # Tier1+Tier2 构建（分层上限：--max-tasks 只管下钻；池数由 --max-pools 管——
    # 自审 T072：旧版池段吃满 cap 把下钻半边静默切到 0）
    use_modules = (len(modules) > 1) and args.pool_mode == "module"
    pool_tasks, pools_trunc = build_pool_tasks(by_layer, files, modules, module_of, use_modules, args.max_pools)
    drill_tasks, drills = build_drill_tasks(active, enum, files, churn,
                                            args.max_targets, args.churn_topk, args.max_tasks)
    for t in pool_tasks + drill_tasks:
        add(t)

    cid_tasks = {}
    for t in tasks:
        for cid in t["checkpoint_ids"]:
            cid_tasks.setdefault(cid, []).append(t["task_id"])
    uncovered = [c["id"] for c in active if c["id"] not in cid_tasks]

    with open(os.path.join(args.out_dir, "tasks.jsonl"), "w", encoding="utf-8") as f:
        for t in tasks:
            f.write(json.dumps(t, ensure_ascii=False) + "\n")
    src_count = {}
    for t in tasks:
        src_count[t["target_source"]] = src_count.get(t["target_source"], 0) + 1
    md = ["# atomic-tasks v1.5（语义接线版·快照 %s·模块 %s）" % (snapshot, modules), "",
          f"- 总任务 {len(tasks)}；来源分布 {src_count}；active 检查点 {len(active)}；未覆盖 {len(uncovered)}",
          f"- 池阴性率台账：填入各 POOL 任务的 pool_result（阴性一次排除=池化有效性的直接度量）", ""]
    with open(os.path.join(args.out_dir, "atomic-tasks.md"), "w", encoding="utf-8") as f:
        f.write("\n".join(md) + "\n")

    # 报告骨架预生成（D-A 词表单源：判定枚举由代码给出，代理只填空——消灭「派发词 vs 审计器词表」漂移）
    if args.report_skeletons:
        rep_dir = os.path.join(args.out_dir, "batch-reports")
        os.makedirs(rep_dir, exist_ok=True)
        na_path = os.path.join(args.enum_dir, "na-prediction.json")
        na_layers = {}
        if os.path.exists(na_path):
            with open(na_path, encoding="utf-8") as f:
                na_layers = {p["layer"]: p["reason"]
                             for p in json.load(f).get("predictions", [])}
        run_claims = [{"metric": "tasks_total", "value": len(tasks)},
                      {"metric": "files_total", "value": len(files)},
                      {"metric": "pools", "value": len(pool_tasks)},
                      {"metric": "active_checkpoints", "value": len(active)}]
        for t in tasks:
            write_report_skeleton(rep_dir, t, cps, na_layers, run_claims)

    print(f"tasks={len(tasks)} pools={len(pool_tasks)}{'(截断!)' if pools_trunc else ''} drills={drills} "
          f"src={src_count} active={len(active)} uncovered={len(uncovered)} modules={modules}")
    import runlog
    runlog.append(args.out_dir, {"script": "generate_tasks.py", "argv": sys.argv[1:], "rc": 0,
                                 "counts": {"tasks": len(tasks), "pools": len(pool_tasks),
                                            "drills": drills, "uncovered": len(uncovered),
                                            "skeletons": 1 if args.report_skeletons else 0}})
    return 1 if uncovered else 0


GIT_SNAP_TIMEOUT = 15  # 秒；快照读取上限


def build_pool_tasks(by_layer, files, modules, module_of, use_modules, max_pools):
    """Tier1 池化任务（不含 task_id）。返回 (tasks, truncated)。"""
    out, n = [], 0
    for layer, cids in sorted(by_layer.items()):
        if use_modules:
            for m in modules:
                if max_pools and n >= max_pools:
                    return out, True
                mf = [f for f in files if module_of(f) == m]
                out.append({"_tag": "POOL", "tier": 1, "layer": layer, "module": m,
                            "checkpoint_ids": cids,
                            "targets": [{"file": f, "line": 0, "kind": "file", "source": "pool-module"} for f in mf],
                            "target_source": "池化", "pool_result": "未跑",
                            "expected_format": "五元组+反证记录（池化筛查：本模块阴性一次排除→标阴性；阳性→列命中项）"})
                n += 1
        else:
            # single 模式定位中小仓：落显式文件目标，semantic 完备性断言才有牙（<ALL> 会让断言失明，自审实录）
            if max_pools and n >= max_pools:
                return out, True
            out.append({"_tag": "POOL", "tier": 1, "layer": layer, "module": modules[0] if modules else "ROOT",
                        "checkpoint_ids": cids,
                        "targets": [{"file": f, "line": 0, "kind": "file", "source": "pool-all"} for f in files],
                        "target_source": "池化", "pool_result": "未跑",
                        "expected_format": "五元组+反证记录（池化筛查：阴性一次排除→标阴性；阳性→列命中项）"})
            n += 1
    return out, False


def build_drill_tasks(active, enum, files, churn, max_targets, churn_topk, max_drills):
    """Tier2 语义下钻＋热区 fallback（不含 task_id）。max_drills 只约束下钻半边。"""
    out = []
    order = {"critical": 0, "high": 1, "medium": 2, "low": 3}
    drills = 0
    for c in sorted(active, key=lambda x: order.get(x["severity_default"], 4)):
        if drills >= max_drills:
            break
        sem, gate = resolve_params_targets(c.get("params"), enum, max_targets)
        if gate:
            continue  # gated：语言面不存在，任务整体跳过（理由可查）
        if sem:
            for i in range(0, len(sem), max_targets):
                chunk = sem[i:i + max_targets]
                out.append({"_tag": "SEM", "tier": 2, "layer": c["layer"], "module": "ROOT",
                            "checkpoint_ids": [c["id"]], "targets": chunk,
                            "target_source": "语义", "pool_result": "",
                            "expected_format": "五元组+反证记录（语义下钻：单检查点对语义锚点逐行判）"})
                drills += 1
                if drills >= max_drills:
                    break
            continue
        # fallback：热区
        if c["severity_default"] in ("critical", "high"):
            top = sorted(files, key=lambda p: churn.get(p, 0), reverse=True)[:churn_topk]
            out.append({"_tag": "HOT", "tier": 2, "layer": c["layer"], "module": "ROOT",
                        "checkpoint_ids": [c["id"]],
                        "targets": [{"file": f, "line": 0, "kind": "file", "source": "hot-fallback"} for f in top],
                        "target_source": "热区", "pool_result": "",
                        "expected_format": "五元组+反证记录（热区 fallback：本检查点无语义锚点，按变更热区判）"})
    return out, drills


def write_report_skeleton(rep_dir, task, cps, na_layers=frozenset(), claims=()):
    """D-A 报告骨架 v2：**自足**——probe 文本/验法/默认严重度/语义锚点/G10 预判全部嵌入，
    审查员每任务只开这一件（v1 曾只写 id，逼三文件交叉引用——注意力扫描 P1#1）。
    判定词表由代码给死（四选一删未用项）；同名 sidecar stub 同步落盘。"""
    tid = task["task_id"]
    cids = task["checkpoint_ids"]
    na = na_layers.get(task["layer"]) if isinstance(na_layers, dict) else None
    na_note = ""
    if na:
        na_note = (f"**G10 机械预判：本层 N/A——{na}。** 如实复核即可；若推翻预判，"
                   f"必须附反证记录（预判依据见 enumeration/na-prediction.json）。\n\n")
    parts = [f"# {tid} ｜ {task['layer']} ｜ ckpt={','.join(cids)}\n"]
    if na_note:
        parts.append(na_note)
    for c in cids:
        cp = cps.get(c, {})
        parts.append(f"## 检查点 {c}\n\n- **{cp.get('title', '')}**\n"
                     f"- 验法 {cp.get('verification', '?')}｜默认严重度 {cp.get('severity_default', '?')}\n"
                     f"- probe：{cp.get('probe', '')}\n")
    if task["target_source"] == "池化":
        parts.append("**pool_result：** （阴性（n/m N/A 或反证）｜阳性（k 命中）｜混合——三选一，删未用项）\n")
        parts.append("\n## 机械前提（可复核）\n\n全库粗筛（目标=全部底册文件）；检索可自定 grep，"
                     "语义锚点不适用。\n")
    else:
        v = "命中｜未命中（反证）｜N/A｜JUDGMENT-NA"
        parts.append(f"**verdict：** （{v}——四选一，删未用项）\n")
        parts.append("**severity：** （critical｜high｜medium｜low——判级先对 data/severity-anchors.json 同型例）\n")
        parts.append("\n## 锚点核验（逐 target：file:line ＋ 整块摘录 ＋ 判定）\n")
        for a in task.get("targets", []):
            parts.append(f"- {a['file']}:{a.get('line', 0)}（{a.get('source', '')}）\n")
    parts.append("\n## 五元组（命中项）/ 反证记录（未命中项）\n\n"
                 "## 证据级别：（断言级｜执行级｜复现级——三选一保留）\n\n"
                 "## 邻域观察\n\n"
                 "## 证据锚点（file:line 清单）\n")
    with open(os.path.join(rep_dir, f"{tid}.md"), "w", encoding="utf-8", newline="\n") as f:
        f.write("".join(parts))
    side = {"task_id": tid, "layer": task["layer"], "checkpoint_ids": cids,
            "verdict": "", "severity": "", "citations": [],
            "pool_result": "",
            # D-④ 主张级冲突检测：运行级事实在生成时已知，预填进每份 stub——
            # claims-check 拿它们对审计期重算的 facts，报告数字漂移即 FAIL
            "claims": list(claims)}
    with open(os.path.join(rep_dir, f"{tid}.json"), "w", encoding="utf-8", newline="\n") as f:
        json.dump(side, f, ensure_ascii=False, indent=1)


if __name__ == "__main__":
    try:
        sys.exit(main())
    except SystemExit:
        raise
    except BaseException as e:  # 事故也入运行日志（默认产出，含失败）
        import runlog
        runlog.append(os.getcwd(), {"script": "generate_tasks.py", "argv": sys.argv[1:], "rc": 1,
                                    "error": f"{type(e).__name__}: {e}", "counts": {}})
        raise
