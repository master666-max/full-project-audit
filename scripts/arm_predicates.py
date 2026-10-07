# -*- coding: utf-8 -*-
"""arm_predicates.py —— 实验臂「激活谓词」判定器 v2（零依赖）。
系统层定位：七臂=条件驻留（非裁撤）——小项目休眠零成本，大项目按谓词自唤醒。
v2 重校（自审 D-B，2026-10-08）：v1 谓词测的是代理指标，被自审标注出 2 假阳（Ricci/K
用「模块数≥3」而工程区 import 图仅 1 边）＋2 假阴（Fuzz/性质测试用文件名信号，看不见
sinks 底册与内置自测）。v2 信号源全部改用可复核的实证面：
  Fuzz      ← sinks 底册（解析/写入/执行面计数）
  性质测试  ← intent 测试行 ＋ --root 内容扫描内置自测标记
  Ricci/K   ← --root 实算 import 图边密度（edges ≥ nodes 才算图有区分度）
  Benford   ← --reports 数字字段计数（≥100；且须为自然多位数值，file:line 类小整数不属域）
  捕获再捕获← --channels ≥2（独立通道数，人工声明）
输入：--enum-dir 枚举底册；可选 --root（源码根，启用内容/图扫描）与 --reports（报告目录）。
用法: py -X utf8 arm_predicates.py --enum-dir <enumeration> [--root <src>] [--reports <dir>] [--out arm-status.md]
"""
import argparse
import json
import os
import re
import sys

NAME_PAT_TLA = re.compile(r"loop|state|scheduler|queue|lock|retry|worker|orchestrat", re.I)
FUZZ_SINK_TYPES = {"exec", "eval", "pickle", "yaml-unsafe", "dynamic-import",
                   "subprocess", "os-system", "file-write"}
SELFTEST_RX = re.compile(r"def\s+self_test|selftest|doctest", re.I)
IMPORT_RX = re.compile(r"^\s*(?:from|import)\s+([\w.]+)", re.M)


def load_rows(p):
    rows = []
    if os.path.exists(p):
        for line in open(p, encoding="utf-8"):
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


def sink_counts(sinks):
    c = {}
    for r in sinks:
        t = str(r.get("meta", {}).get("type", ""))
        c[t] = c.get(t, 0) + 1
    return c


def selftest_units(root):
    n = 0
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in {".git", "__pycache__", "node_modules", ".venv"}]
        for fn in filenames:
            if not fn.endswith(".py"):
                continue
            try:
                with open(os.path.join(dirpath, fn), encoding="utf-8", errors="replace") as f:
                    if SELFTEST_RX.search(f.read()):
                        n += 1
            except OSError:
                pass
    return n


def import_graph(root):
    """repo 内 py 文件互引图：nodes=py 文件数，edges=解析到仓内模块名的 import 边。"""
    pys = []
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in {".git", "__pycache__", "node_modules", ".venv"}]
        pys += [os.path.join(dirpath, fn) for fn in filenames if fn.endswith(".py")]
    stems = {os.path.splitext(fn)[0] for fn in map(os.path.basename, pys)}
    edges = 0
    for p in pys:
        try:
            with open(p, encoding="utf-8", errors="replace") as f:
                for m in IMPORT_RX.finditer(f.read()):
                    top = m.group(1).split(".")[0]
                    if top in stems and top != os.path.splitext(os.path.basename(p))[0]:
                        edges += 1
        except OSError:
            pass
    return len(pys), edges


def report_numeric_fields(reports_dir):
    n = 0
    for fn in os.listdir(reports_dir):
        if not fn.endswith(".md"):
            continue
        try:
            with open(os.path.join(reports_dir, fn), encoding="utf-8", errors="replace") as f:
                n += len(re.findall(r"\b\d{2,}\b", f.read()))
        except OSError:
            pass
    return n


def main():
    ap = argparse.ArgumentParser(allow_abbrev=False,
                                 description="实验臂激活谓词 v2（信号源=可复核实证面，v2 自审重校）")
    ap.add_argument("--enum-dir", required=True)
    ap.add_argument("--out", default=None)
    ap.add_argument("--root", default=None, help="源码根：启用内置自测扫描与 import 图密度")
    ap.add_argument("--reports", default=None, help="batch-reports 目录：Benford 数字字段计数")
    ap.add_argument("--channels", type=int, default=1, help="本轮独立审查通道数（捕获再捕获用）")
    args = ap.parse_args()
    enum = {k: load_rows(os.path.join(args.enum_dir, f"{k}.jsonl"))
            for k in ("files", "entry", "sinks", "intent")}
    files = [r["key"] for r in enum["files"]]
    entries = [str(r.get("key", "")) for r in enum["entry"]]
    tests = [r for r in enum["intent"] if r.get("meta", {}).get("source") == "test"]
    sc = sink_counts(enum["sinks"])
    fuzz_face = sum(n for t, n in sc.items() if t in FUZZ_SINK_TYPES)
    st_units = selftest_units(args.root) if args.root else 0
    nodes = edges = 0
    if args.root:
        nodes, edges = import_graph(args.root)
    benford_n = report_numeric_fields(args.reports) if args.reports else 0

    rows = []
    def add(arm, armed, predicate, evidence, mech):
        rows.append({"arm": arm, "status": "ARMED（激活）" if armed else "DORMANT（休眠）",
                     "predicate": predicate, "evidence": evidence, "mechanism": mech})

    add("Fuzzing+sanitizer", fuzz_face >= 5,
        "sinks 底册解析/执行/写入面 ≥5（v1 文件名信号假阴，废）",
        f"sinks 面计数 {fuzz_face}：{dict((k, v) for k, v in sc.items() if k in FUZZ_SINK_TYPES)}",
        "对装载/解析/执行点喂畸形输入 → 崩溃入 R 类证据")
    add("性质测试", bool(tests) or st_units > 0,
        "存在测试载体：intent 测试行 或 内置自测单元（内容扫描）",
        f"intent 测试行 {len(tests)}；自测单元 {st_units}" + ("（--root 未给，未扫内容）" if not args.root else ""),
        "由测试/自测断言提炼不变量 → 生成器找反例（金集互补腿）")
    tla = [f for f in files if NAME_PAT_TLA.search(f)]
    add("TLA+/模型检查", bool(tla) or any("route" in e for e in entries),
        "存在协议/并发/状态机核心（文件名或路由信号）",
        f"命中 {len(tla)}：{tla[:3]}" if tla else "0 命中 loop/state/scheduler/lock",
        "TLA+ 规约 L5 循环与重试状态机 → 状态空间穷举")
    add("捕获再捕获", args.channels >= 2,
        "同一项目 ≥2 独立通道各自登记检出（人工声明本轮通道数）",
        f"本轮 channels={args.channels}",
        "双通道重叠 → 残余缺陷 N±CI（MUC 下界兜底）")
    add("Ollivier-Ricci 曲率", nodes > 0 and edges >= nodes,
        "import 图边密度 ≥1（edges≥nodes 才有区分度；v1 模块数代理在 1 边图上假阳，废）",
        f"import 图 nodes={nodes} edges={edges}" + ("" if args.root else "（--root 未给，不激活）"),
        "建代码图 → 曲率找接口/交接面 → 第四密度权重（文献空白，试点假设）")
    add("带宽 K 谱估计", nodes > 0 and edges >= nodes,
        "同上：图密度门（带限假设需非退化图）",
        f"import 图 nodes={nodes} edges={edges}",
        "Laplacian top-K 读谱 → 任务数下界")
    add("Benford 数字指纹", benford_n >= 100,
        "报告自然数值字段 ≥100（file:line 类小整数不属首位分布域，判读时须过滤）",
        f"数字字段计数 {benford_n}" + ("（--reports 未给）" if not args.reports else ""),
        "对 batch-report 数字字段做首位分布检验")

    armed = [r for r in rows if r["status"].startswith("ARMED")]
    lines = ["# 实验臂状态（激活谓词 v2 · 条件驻留制 · 信号源=可复核实证面）", "",
             f"- 项目：{args.enum_dir}｜文件 {len(files)}｜sinks 面 {fuzz_face}｜import 图 {nodes} 节点 {edges} 边"
             f"｜自测单元 {st_units}｜报告数字字段 {benford_n}｜通道 {args.channels}",
             f"- **结果：ARMED {len(armed)} / DORMANT {len(rows)-len(armed)}**（休眠=零成本驻留，非裁撤）", "",
             "| 臂 | 状态 | 谓词 | 证据 | 机制形态 |", "|---|---|---|---|---|"]
    for r in rows:
        lines.append(f"| {r['arm']} | {r['status']} | {r['predicate']} | {r['evidence']} | {r['mechanism']} |")
    out = args.out or os.path.join(args.enum_dir, "arm-status.md")
    with open(out, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
    print(f"ARM-PREDICATES: ARMED {len(armed)} / 共 {len(rows)} -> {out}")
    for r in rows:
        print(f"  {r['status'][:7]} {r['arm']}  ({r['evidence'][:60]})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
