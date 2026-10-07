# -*- coding: utf-8 -*-
"""runlog.py —— 运行日志内核（零依赖；默认产出，无需开关）。
每次 CLI 运行向 <输出目录>/run-log.jsonl 追加一行事件：
  {"ts", "script", "argv", "rc", "duration_ms", "counts"}
渲染成 run-report.md 用 audit/make_run_report.py。设计纪律：
  - 只追加、带 UTC 时戳、坏行不致命（日志永远不能反过来弄死主流程）；
  - 失败也记（rc!=0 的事故 lines 正是运行报告的原料）。
用法（脚本内）:
  import runlog
  with runlog.span(__file__, sys.argv[1:], out_dir) as span:
      ... ; span["counts"]["rows"] = n
"""
import json
import os
import sys
import time
from datetime import datetime, timezone


def append(out_dir, event):
    """追加一行事件；任何失败静默吞（日志不得反噬主流程）。"""
    try:
        os.makedirs(out_dir, exist_ok=True)
        event = dict(event)
        event.setdefault("ts", datetime.now(timezone.utc).isoformat(timespec="seconds"))
        with open(os.path.join(out_dir, "run-log.jsonl"), "a", encoding="utf-8") as f:
            f.write(json.dumps(event, ensure_ascii=False) + "\n")
    except OSError:
        pass


class span:
    """with runlog.span(__file__, argv, out_dir) as s: ... s["counts"]["x"]=1
    正常退出记 rc=0，异常记 rc=1＋error 后原样重抛。"""

    def __init__(self, script_path, argv, out_dir):
        self.event = {"script": os.path.basename(script_path),
                      "argv": [str(a) for a in argv],
                      "rc": 0, "duration_ms": 0, "counts": {}}
        self.out_dir = out_dir
        self._t0 = time.time()

    def __enter__(self):
        return self.event

    def __exit__(self, exc_type, exc, tb):
        self.event["duration_ms"] = int((time.time() - self._t0) * 1000)
        if exc_type is not None:
            self.event["rc"] = 1
            self.event["error"] = f"{exc_type.__name__}: {exc}"
        append(self.out_dir, self.event)
        return False


def render(log_path, ledger_path=None):
    """run-log.jsonl (+ 可选批次账本) -> markdown 运行报告骨架。"""
    if not os.path.exists(log_path):
        raise SystemExit(f"运行日志缺失: {log_path}")
    rows = []
    with open(log_path, encoding="utf-8") as f:
        for i, line in enumerate(f, 1):
            line = line.strip()
            if not line:
                continue
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError as e:
                rows.append({"ts": "?", "script": f"<坏行 {i}>", "error": str(e), "rc": 1, "counts": {}})
    lines = ["# 运行报告（run-report · 由 run-log.jsonl 机械渲染）", "",
             f"- 事件 {len(rows)} 条；非零退出 {sum(1 for r in rows if r.get('rc'))} 条", "",
             "| 时戳(UTC) | 脚本 | rc | 耗时ms | 计数 | 备注 |", "|---|---|---|---|---|---|"]
    for r in rows:
        note = r.get("error") or ""
        lines.append(f"| {r.get('ts','')} | {r.get('script','')} | {r.get('rc','')} | "
                     f"{r.get('duration_ms',0)} | {json.dumps(r.get('counts',{}), ensure_ascii=False)} | {note} |")
    if ledger_path and os.path.exists(ledger_path):
        with open(ledger_path, encoding="utf-8") as f:
            led = [json.loads(l) for l in f if l.strip()]
        tok = sum(x.get("tokens", 0) for x in led)
        lines += ["", "## 批次账本（真值口径）", "",
                  "| 批 | 任务 | tokens | 工具调用 | 耗时ms |", "|---|---|---|---|---|"]
        for x in led:
            lines.append(f"| {x.get('batch_id')} | {x.get('tasks')} | {x.get('tokens',0):,} | "
                         f"{x.get('tool_uses','')} | {x.get('duration_ms','')} |")
        lines += ["", f"- 合计 token：**{tok:,}**（{tok/1e6:.1f}M）"]
    incidents = [r for r in rows if r.get("rc")]
    lines += ["", "## 事故登记（非零退出）",
              "（逐条填：现象/根因/处置/教训——没有就写\"无\"）" if not incidents else ""]
    for r in incidents:
        lines.append(f"- {r.get('ts')} {r.get('script')}：{r.get('error','rc!=0')}")
    return "\n".join(lines) + "\n"


if __name__ == "__main__":
    ap = sys.argv
    if len(ap) >= 2 and ap[1] == "render":
        print(render(ap[2], ap[3] if len(ap) > 3 else None), end="")
    else:
        print("用法: runlog.py render <run-log.jsonl> [batch-ledger.jsonl]", file=sys.stderr)
        sys.exit(2)
