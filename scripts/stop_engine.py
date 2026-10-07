# -*- coding: utf-8 -*-
"""stop_engine.py —— Weitzman σ 停机引擎 v1（工单 v3-W8；L0 影子——本件不驱动停机，FP5）。
预算化信息收集的预约价值贪心（实核锚 Weitzman 1979, DOI 10.2307/1910412）：
每批＝一盒（开盒价＝批 token 成本，奖赏＝批加权价值）；σ＝预约价值（每 token 价值单位），
二分求解 mean(max(r_j−σ,0)) = 1（归一化开盒成本）。判据：当前运行最新批的每 token 价值
r_cur < θ·max_k σ_k ⇒ 建议停机。**全部输出为 L0 影子建议。**
在线口径：--at N 只读运行台账前 N 行——防前视 self-test 断言全量与截断在 N 处输出一致。
用法:
  py -X utf8 stop_engine.py --ledger <历史v2账本> --run-ledger <当前运行已批次.jsonl> \
      [--arm pool] [--theta 1.0] [--at N] [--out stop-advice.md] [--self-test]
"""
import argparse
import json
import os
import sys


def read_rows(path):
    if not os.path.exists(path):
        raise SystemExit(f"输入缺失: {path}")
    return [json.loads(l) for l in open(path, encoding="utf-8") if l.strip()]


def batch_value(row, w):
    s = row.get("sev", {})
    return w.get("critical", 0) * s.get("critical", 0) + w.get("high", 0) * s.get("high", 0) \
        + w.get("other", 0) * s.get("other", 0)


def solve_sigma(rewards, cost=1.0, lo=0.0, hi=None):
    """二分解 mean(max(r_j−σ,0)) = cost；rewards 为每 token 价值样本。"""
    if not rewards:
        return None
    if hi is None:
        hi = max(rewards)
    for _ in range(80):
        mid = (lo + hi) / 2
        excess = sum(max(r - mid, 0.0) for r in rewards) / len(rewards)
        if excess > cost:
            lo = mid
        else:
            hi = mid
    return (lo + hi) / 2


def collect(ledger_rows, arm, weights, upto=None):
    """按 arm 聚类收集每 token 价值样本；upto=只取前 N 行（防前视口径）。"""
    by_class = {}
    for r in ledger_rows:
        if upto is not None:
            seq = [i for i, x in enumerate(ledger_rows) if x is r]
            if seq and seq[0] >= upto:
                continue
        cls = "run" if r.get("arm", "").startswith("wave") is False and "post" not in r.get("arm", "") \
            else r.get("arm", "run")
        a = r.get("arm", "")
        key = "drill" if "drill" in a or "w2" in str(r.get("batch_id", "")) else "pool"
        if arm in ("pool", "drill") and key != arm:
            continue
        v = batch_value(r, weights)
        c = max(float(r.get("tokens", 0)), 1.0)
        by_class.setdefault(key, []).append(v / c * 1e6)   # 每百万 token 价值
    return by_class


def advice(ledger_rows, run_rows, arm, theta, weights, at=None):
    hist = collect(ledger_rows, arm, weights)
    run = collect(run_rows[:at] if at is not None else run_rows, arm, weights)
    sigmas = {}
    for k, samples in hist.items():
        if len(samples) >= 3:
            sigmas[k] = solve_sigma(samples)
    sigma_max = max(sigmas.values()) if sigmas else None
    cur = None
    for k, samples in run.items():
        if samples:
            cur = samples[-1]
    stop = sigma_max is not None and cur is not None and cur < theta * sigma_max
    return {"arm": arm, "theta": theta, "sigmas": {k: round(v, 2) for k, v in sigmas.items()},
            "run_last_per_token_value": (round(cur, 2) if cur is not None else None),
            "sigma_max": (round(sigma_max, 2) if sigma_max is not None else None),
            "suggest_stop": bool(stop),
            "level": "L0 影子——本件不驱动停机（FP5）"}


def self_test():
    """①σ 二分残差；②防前视：全量账本在 --at 处的输出与截断账本一致；③L0 标记。"""
    synth = [{"batch_id": f"b{i}", "tasks": 5, "sev": {"critical": 0, "high": h, "other": o},
              "tokens": tk, "arm": "pool"}
             for i, (h, o, tk) in enumerate([(10, 20, 1_000_000), (8, 18, 1_100_000),
                                             (6, 15, 1_200_000), (3, 10, 1_300_000)], 1)]
    w = {"critical": 100.0, "high": 30.0, "other": 5.0}
    rs = [batch_value(r, w) / r["tokens"] * 1e6 for r in synth]
    sg = solve_sigma(rs)
    excess = sum(max(r - sg, 0.0) for r in rs) / len(rs)
    ok1 = abs(excess - 1.0) < 1e-6 and 0 <= sg <= max(rs)
    full = advice(synth, synth, "pool", 1.0, w, at=2)
    trunc = advice(synth, synth[:2], "pool", 1.0, w, at=None)
    ok2 = full["sigmas"] == trunc["sigmas"] and full["run_last_per_token_value"] == trunc["run_last_per_token_value"]
    ok3 = "不驱动停机" in full["level"]
    print(f"self-test: σ二分残差={'PASS' if ok1 else 'FAIL'}｜防前视一致={'PASS' if ok2 else 'FAIL'}｜L0标记={'PASS' if ok3 else 'FAIL'}")
    return 0 if (ok1 and ok2 and ok3) else 1


def main():
    ap = argparse.ArgumentParser(allow_abbrev=False,
                                 description="Weitzman σ 停机引擎 v1（L0 影子——不驱动停机）")
    ap.add_argument("--ledger", help="历史 batch-ledger v2（同类批次经验分布）")
    ap.add_argument("--run-ledger", help="当前运行已批次台账（同 schema；在线口径）")
    ap.add_argument("--arm", default="pool", choices=["pool", "drill"])
    ap.add_argument("--theta", type=float, default=1.0, help="停机灵敏度（r_cur < θ·σ_max 建议停）")
    ap.add_argument("--at", type=int, default=None, help="只读运行台账前 N 行（防前视口径）")
    ap.add_argument("--weights", default=None, help="E1 拟合参数.json（缺省用基线 w₀）")
    ap.add_argument("--out", default=None)
    ap.add_argument("--self-test", action="store_true")
    args = ap.parse_args()
    if args.self_test:
        return self_test()
    if not args.ledger or not args.run_ledger:
        ap.error("--ledger 与 --run-ledger 必填（或用 --self-test）")
    params = {}
    if args.weights and os.path.exists(args.weights):
        with open(args.weights, encoding="utf-8") as f:
            params = json.load(f)
        pts = params.get("passing_points") or []
        if pts:
            w0 = pts[0]["w"]
            weights = {"critical": w0[0], "high": w0[1], "other": w0[2]}
        else:
            weights = dict((k, 0) for k in ("critical", "high", "other"))
    else:
        weights = {"critical": 100.0, "high": 30.0, "other": 5.0}
    d = advice(read_rows(args.ledger), read_rows(args.run_ledger), args.arm, args.theta, weights, args.at)
    md = ["# 停机建议（stop_engine v1 · L0 影子）", "",
          f"- **{d['level']}**", f"- 类：{d['arm']}｜θ={d['theta']}｜σ_max={d['sigma_max']}｜"
          f"运行最新批每 M-token 价值={d['run_last_per_token_value']}",
          f"- 建议停机：**{d['suggest_stop']}**（建议≠停机，L0 不驱动任何流程；L2 前提见设计书 §7.2）", "",
          "## 敞口说明", "",
          "- 敞口第一版估计器：历史同层每 token 价值均值 − 当前值，×运行已耗 token（粗估，残差估计以捕获再捕获臂为准）。"]
    out = args.out or "stop-advice.md"
    with open(out, "w", encoding="utf-8", newline="\n") as f:
        f.write("\n".join(md) + "\n")
    with open(os.path.splitext(out)[0] + ".json", "w", encoding="utf-8", newline="\n") as f:
        json.dump(d, f, ensure_ascii=False, indent=1)
    print(f"STOP-ENGINE: 建议停机={d['suggest_stop']}（L0 影子）-> {out}")
    import runlog
    runlog.append(os.path.dirname(os.path.abspath(out)),
                  {"script": "stop_engine.py", "argv": sys.argv[1:], "rc": 0,
                   "counts": {"suggest_stop": d["suggest_stop"], "sigma_max": d["sigma_max"]}})
    return 0


if __name__ == "__main__":
    sys.exit(main())
