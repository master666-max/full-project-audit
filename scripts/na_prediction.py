# -*- coding: utf-8 -*-
"""na_prediction.py —— N/A 机械预判 v1（D-09，零依赖）。
读取枚举底册，产出 na-prediction.json：**机械可核验**的 N/A 候选（附底册证据）。
规则仅限"可脚本判定主体不存在"的面；预判之外的 N/A 一律走 JUDGMENT-NA 人工池。
用法: py -X utf8 na_prediction.py --enum-dir <enumeration> [--out <na-prediction.json>]
"""
import argparse
import json
import os
import sys

FRONT_EXT = (".html", ".css", ".scss", ".vue", ".jsx", ".tsx")
DB_MARK = ("sql", "db", "migration", "alembic", "schema", "models")
CI_MARK = (".github/workflows", ".gitlab-ci", "jenkins", "azure-pipelines")


def load_jsonl(p):
    rows = []
    if p and os.path.exists(p):
        for line in open(p, encoding="utf-8"):
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--enum-dir", required=True)
    ap.add_argument("--out", default=None)
    args = ap.parse_args()
    enum = {k: load_jsonl(os.path.join(args.enum_dir, f"{k}.jsonl"))
            for k in ("files", "entry", "env", "tools", "prompts", "deps", "intent", "sinks")}
    files = [r["key"] for r in enum["files"]]
    preds = []

    def add(layer, reason, evidence):
        preds.append({"na_class": "NA-MECHANICAL", "layer": layer,
                      "reason": reason, "evidence": evidence})

    if not any(f.lower().endswith(FRONT_EXT) for f in files):
        add("通用·前端", "无任何前端资产文件", f"files={len(files)}，0 个 {FRONT_EXT}")
    if not any(any(m in f.lower() for m in DB_MARK) for f in files):
        add("通用·数据库", "无数据库/迁移/schema 文件", "文件名扫描 0 命中 sql/db/migration")
    if not any(any(m in f.lower() for m in CI_MARK) for f in files):
        add("通用·CI/CD", "无 CI 配置文件", "0 命中 .github/workflows|.gitlab-ci|jenkins")
    if not enum["deps"]:
        add("通用·依赖", "零依赖面（无依赖清单或全标准库）", "deps.jsonl=0 行")
    if not enum["prompts"]:
        add("LLM·prompt 系", "无 prompt 文件/内嵌 prompt 常量", "prompts.jsonl=0 行")
    if not enum["tools"]:
        add("LLM·工具调用", "无工具/schema 注册点", "tools.jsonl=0 行")

    payload = {"generated_by": "na_prediction.py v1", "enum_dir": args.enum_dir,
               "predictions": preds,
               "note": "预判表内的 N/A 直接采信（附底册证据）；表外 N/A 一律 JUDGMENT-NA 入人工抽验池"}
    out = args.out or os.path.join(args.enum_dir, "na-prediction.json")
    json.dump(payload, open(out, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print(f"NA-PREDICTION: {len(preds)} 条机械预判 -> {out}")
    for p in preds:
        print(f"  - {p['layer']}: {p['reason']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
