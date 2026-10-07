# -*- coding: utf-8 -*-
"""arm_predicates.py —— 实验臂「激活谓词」判定器（零依赖）。
系统层定位：七臂=条件驻留（非裁撤）——小项目休眠零成本，大项目按谓词自唤醒。
输入：枚举底册（enum-dir）；输出：每臂 armed/dormant + 机械证据。
用法: py -X utf8 arm_predicates.py --enum-dir <enumeration> [--out arm-status.md]
"""
import argparse
import json
import os
import re
import sys

NAME_PAT = {
    "fuzz": re.compile(r"parse|decod|server|handler|api|input|proto|msgpack|toml|yaml", re.I),
    "tla": re.compile(r"loop|state|scheduler|queue|lock|retry|worker|orchestrat", re.I),
}


def load_rows(p):
    rows = []
    if os.path.exists(p):
        for line in open(p, encoding="utf-8"):
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--enum-dir", required=True)
    ap.add_argument("--out", default=None)
    ap.add_argument("--modules", type=int, default=None, help="一级模块数（默认=1）")
    args = ap.parse_args()
    enum = {k: load_rows(os.path.join(args.enum_dir, f"{k}.jsonl"))
            for k in ("files", "entry", "sinks", "intent", "deps")}
    files = [r["key"] for r in enum["files"]]
    entries = [str(r.get("key", "")) for r in enum["entry"]]
    sinks = [str(r.get("meta", {}).get("type", "")) for r in enum["sinks"]]
    tests = [r for r in enum["intent"] if r.get("meta", {}).get("source") == "test"]
    modules = args.modules if args.modules is not None else (1 if files else 0)

    rows = []
    def add(arm, armed, predicate, evidence, mech):
        rows.append({"arm": arm, "status": "ARMED（激活）" if armed else "DORMANT（休眠）",
                     "predicate": predicate, "evidence": evidence, "mechanism": mech})

    fz = [f for f in files if NAME_PAT["fuzz"].search(f)]
    add("Fuzzing+sanitizer", bool(fz),
        "存在解析/网络/服务输入面（文件名信号）",
        f"命中 {len(fz)}：{fz[:3]}" if fz else "0 命中 parse/decod/server/handler/api",
        "建 fuzz harness → 崩溃/内存错误入 R 类证据")
    add("性质测试", bool(tests),
        "存在测试（不变量载体）", f"intent 底册 test 行 {len(tests)}",
        "由测试断言提炼不变量 → 生成器找反例（金集互补腿）")
    tla = [f for f in files if NAME_PAT["tla"].search(f)]
    add("TLA+/模型检查", bool(tla) or any("route" in e for e in entries),
        "存在协议/并发/状态机核心（文件名或路由信号）",
        f"命中 {len(tla)}：{tla[:3]}" if tla else "0 命中 loop/state/scheduler/lock",
        "TLA+ 规约 L5 循环与重试状态机 → 状态空间穷举")
    add("捕获再捕获", False, "流程条件（每轮判定）：同一项目 ≥2 独立通道各自登记检出",
        "本轮单通道" if True else "", "双通道重叠 → 残余缺陷 N±CI（MUC 下界兜底）")
    add("Ollivier-Ricci 曲率", modules >= 3, "一级模块数 ≥3（图基建有区分度）",
        f"modules={modules}", "建代码图 → 曲率找接口/交接面 → 第四密度权重（文献空白，试点假设）")
    add("带宽 K 谱估计", modules >= 3, "一级模块数 ≥3 且带限假设未证伪（§12#10）",
        f"modules={modules}", "Laplacian top-K 读谱 → 任务数下界")
    add("Benford 数字指纹", False, "流程条件（评审后判定）：报告数字字段 ≥100",
        "本轮 <30（估值）", "对 batch-report 数字字段做首位分布检验")

    armed = [r for r in rows if r["status"].startswith("ARMED")]
    lines = ["# 实验臂状态（激活谓词判定 · 条件驻留制）", "",
             f"- 项目：{args.enum_dir}｜模块数 {modules}｜文件 {len(files)}",
             f"- **结果：ARMED {len(armed)} / DORMANT {len(rows)-len(armed)}**（休眠=零成本驻留，非裁撤）", "",
             "| 臂 | 状态 | 谓词 | 证据 | 机制形态 |", "|---|---|---|---|---|"]
    for r in rows:
        lines.append(f"| {r['arm']} | {r['status']} | {r['predicate']} | {r['evidence']} | {r['mechanism']} |")
    out = args.out or os.path.join(args.enum_dir, "arm-status.md")
    open(out, "w", encoding="utf-8").write("\n".join(lines) + "\n")
    print(f"ARM-PREDICATES: ARMED {len(armed)} / 共 {len(rows)} -> {out}")
    for r in rows:
        print(f"  {r['status'][:7]} {r['arm']}  ({r['evidence'][:60]})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
