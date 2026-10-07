# -*- coding: utf-8 -*-
"""probe_runner.py —— 检查点机械探针预执行器（D-A「检索单源」，零依赖）。
对每个检查点按 params 语义解析锚点（复用 generate_tasks.resolve_params_targets），
再把锚点处的**原始命中行**抓出来（sink 行、关键词 grep 行）——把「找」变成「读」。
自审实测依据：池任务（自由检索型）均价 827k vs 锚点直指型 159k，差 5.2×。
产出 probe-pack.jsonl：每检查点一行 {id, anchors, sink_hits, keyword_hits, note}；
审查员只判读证据包，不再全库漫游。
用法:
  py -X utf8 probe_runner.py --data data/checkpoints.json --enum-dir enumeration \
      --root <被审根> --out probe-pack.jsonl [--tasks tasks.jsonl] [--max-keyword-hits 12]
"""
import argparse
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "scripts"))
import generate_tasks as gt  # noqa: E402

SINK_TYPE_ALIAS = gt.SINK_TYPE_ALIAS
KEYWORD_STOP = gt.KW_DROP


def load_jsonl(p):
    if not os.path.exists(p):
        raise SystemExit(f"输入缺失: {p}")
    rows = []
    with open(p, encoding="utf-8") as f:
        for i, line in enumerate(f, 1):
            line = line.strip()
            if line:
                try:
                    rows.append(json.loads(line))
                except json.JSONDecodeError as e:
                    raise SystemExit(f"{p}:{i}: JSONL 解析失败: {e}")
    return rows


def keyword_search(root, keywords, max_hits):
    """仓内文本文件按关键词 grep。返回 (hits, truncated)。
    双编码：utf-8 为主；关键词含非 ASCII 时对每个文件再跑一遍 GBK 解码
    （自审 P2#7：GBK 素材件在 utf-8 解码下中文关键词是盲的）。"""
    kws = [k for k in keywords if k and k not in KEYWORD_STOP]
    if not kws:
        return [], False
    need_gbk = any(not k.isascii() for k in kws)
    hits, truncated = [], False
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in
                       {".git", "__pycache__", "node_modules", ".venv", "venv"}]
        for fn in filenames:
            p = os.path.join(dirpath, fn)
            if os.path.splitext(fn)[1].lower() not in {".py", ".md", ".txt", ".json", ".yaml",
                                                       ".yml", ".toml", ".sh", ".bat", ".ps1", ".js", ".ts"}:
                continue
            try:
                if os.path.getsize(p) > 2 * 1024 * 1024:
                    continue
                with open(p, "rb") as f:
                    raw = f.read()
            except OSError:
                continue
            variants = [raw.decode("utf-8", errors="replace")]
            if need_gbk:
                variants.append(raw.decode("gbk", errors="replace"))
            seen_lines = set()
            for text in variants:
                low = text.lower()
                for i, line in enumerate(text.splitlines(), 1):
                    if (fn, i) in seen_lines:
                        continue
                    ll = line.lower()
                    if any(k in ll for k in kws):
                        seen_lines.add((fn, i))
                        if len(hits) >= max_hits:
                            truncated = True
                            return hits, truncated
                        hits.append({"file": os.path.relpath(p, root).replace("\\", "/"),
                                     "line": i, "excerpt": line.strip()[:160]})
    return hits, truncated


def main():
    ap = argparse.ArgumentParser(allow_abbrev=False,
                                 description="检查点机械探针预执行（D-A 检索单源：审查员读证据包，不做全库漫游）")
    ap.add_argument("--data", required=True)
    ap.add_argument("--enum-dir", required=True)
    ap.add_argument("--root", required=True, help="被审仓根（关键词 grep 用）")
    ap.add_argument("--out", required=True)
    ap.add_argument("--tasks", default=None, help="只探任务集里出现的检查点（默认全 active）")
    ap.add_argument("--max-keyword-hits", type=int, default=12)
    ap.add_argument("--enrich-reports", default=None, metavar="目录",
                    help="把证据包摘要嵌进该目录的报告骨架（配 --tasks 使用；骨架自足的收口）")
    args = ap.parse_args()
    with open(args.data, encoding="utf-8") as f:
        doc = json.load(f)
    active = [c for c in doc["checkpoints"] if c.get("status") == "active"]
    if args.tasks:
        want = {cid for t in load_jsonl(args.tasks) for cid in t.get("checkpoint_ids", [])}
        active = [c for c in active if c["id"] in want]
    enum = {k: load_jsonl(os.path.join(args.enum_dir, f"{k}.jsonl"))
            for k in ("files", "entry", "env", "tools", "prompts", "deps", "intent", "sinks")}
    sink_rows = enum["sinks"]

    n_anch = n_sink = n_kw = 0
    with open(args.out, "w", encoding="utf-8") as out:
        for c in active:
            anchors, gate = gt.resolve_params_targets(c.get("params"), enum, 8)
            sink_hits, kw_srcs = [], []
            for p in c.get("params", []):
                p = str(p)
                if p.startswith("sink="):
                    val = p.split("=", 1)[1]
                    types = SINK_TYPE_ALIAS.get(val, (val,))
                    sink_hits += [{"file": r["file"], "line": r.get("line", 0),
                                   "type": r.get("meta", {}).get("type", "")}
                                  for r in sink_rows
                                  if any(k in str(r.get("meta", {}).get("type", "")) for k in types)][:16]
                key, _, _ = p.partition("=")
                spec = gt.PARAM_TARGETS.get(key)
                if spec and spec[1]:
                    kw_srcs += list(spec[1])
                elif not spec and not p.startswith(("sink=", "dep=", "gate:")) and not gt.PARAM_PARAM_RX.search(key):
                    kw_srcs += list(gt.fallback_keywords(key))
            kw_hits, kw_trunc = keyword_search(args.root, kw_srcs, args.max_keyword_hits)
            n_anch += len(anchors); n_sink += len(sink_hits); n_kw += len(kw_hits)
            out.write(json.dumps({"id": c["id"], "layer": c["layer"],
                                  "note": gate or "",
                                  "anchors": anchors, "sink_hits": sink_hits,
                                  "keyword_hits": kw_hits, "truncated": kw_trunc,
                                  "keywords": sorted(set(kw_srcs))}, ensure_ascii=False) + "\n")
    print(f"probe-pack: {len(active)} 检查点｜锚点 {n_anch}｜sink 命中 {n_sink}｜关键词命中 {n_kw} -> {args.out}")
    if args.enrich_reports and args.tasks:
        enrich(args.enrich_reports, args.tasks, args.out)
    import runlog
    runlog.append(os.path.dirname(os.path.abspath(args.out)),
                  {"script": "probe_runner.py", "argv": sys.argv[1:], "rc": 0,
                   "counts": {"checkpoints": len(active), "anchors": n_anch,
                              "sink_hits": n_sink, "keyword_hits": n_kw,
                              "enriched": 1 if args.enrich_reports else 0}})
    return 0


def enrich(reports_dir, tasks_path, pack_path):
    """把证据包摘要嵌进报告骨架（自审 P1#1 的另一半：审查员连 pack 都不用开）。"""
    pack = {}
    with open(pack_path, encoding="utf-8") as f:
        for line in f:
            if line.strip():
                r = json.loads(line)
                pack[r["id"]] = r
    n = 0
    for line in open(tasks_path, encoding="utf-8"):
        if not line.strip():
            continue
        t = json.loads(line)
        path = os.path.join(reports_dir, f"{t['task_id']}.md")
        if not os.path.exists(path):
            continue
        with open(path, encoding="utf-8") as f:
            txt = f.read()
        if "## 证据包" in txt:      # 已嵌入不重复
            continue
        rows = []
        for cid in t["checkpoint_ids"]:
            r = pack.get(cid)
            if not r:
                continue
            head = (f"- **{cid}**：锚点 {len(r['anchors'])}｜sink 命中 {len(r['sink_hits'])}｜"
                    f"关键词命中 {len(r['keyword_hits'])}{'（截断！）' if r.get('truncated') else ''}"
                    f"{'｜' + r['note'] if r['note'] else ''}")
            rows.append(head)
            for h in (r["keyword_hits"][:4] + [{"file": s["file"], "line": s.get("line", 0),
                                                "excerpt": "sink:" + s.get("type", "")}
                                               for s in r["sink_hits"][:4]]):
                rows.append(f"    - {h['file']}:{h['line']}  {h.get('excerpt', '')[:120]}")
        if rows:
            section = "## 证据包（probe_runner 预检索——判读为主，按需补查）\n" + "\n".join(rows) + "\n"
            marker = "\n## 五元组（命中项）"
            txt = txt.replace(marker, "\n" + section + marker, 1) if marker in txt else txt + "\n" + section
            with open(path, "w", encoding="utf-8", newline="\n") as f:
                f.write(txt)
            n += 1
    print(f"enrich: {n} 份骨架已嵌证据包")


if __name__ == "__main__":
    sys.exit(main())
