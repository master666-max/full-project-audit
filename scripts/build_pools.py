# -*- coding: utf-8 -*-
"""build_pools.py —— 从全量池机械派生出池家族（零依赖，可重复执行）。
派生规则唯一事实源在本文件；产物 schema 与全量池完全一致（可直接 --data 互换）。
用法: py -X utf8 build_pools.py
产物: data/pools/{quick,security,llm-app,agentic,ai-code}.json
"""
import hashlib
import json
import os
import sys
from collections import Counter
from datetime import datetime, timezone

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FULL = os.path.join(ROOT, "data", "checkpoints.json")
OUTDIR = os.path.join(ROOT, "data", "pools")


def load_json(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def prefix(cid):
    """SEC-002 -> SEC ; GEN-ERR-001 -> GEN-ERR"""
    return cid.rsplit("-", 1)[0]


RULES = {
    "micro": {
        "title": "微池（进门级快速体检）",
        "desc": "最小可用集：全部 critical ＋ AI 幻觉 API／agent 循环控制两族（最高频致死面）。适用于「先看一眼」的 30 分钟级体检或预算极紧时。",
        "pred": lambda c: (
            c["severity_default"] == "critical"
            or prefix(c["id"]) in {"AIG-HALL", "LLM-LOOP"}
        ),
    },
    "quick": {
        "title": "快速通用审查（TRIMMED 档池）",
        "desc": "全量池的横切高收益子集：全部 critical ＋ 通用卫生层（错误/配置/依赖/可靠性）＋ AI 生成代码全家族 ＋ 安全全家族（散点/通用/AI/LLM/MCP/Agent）＋ LLM 关键韧性与接地层。适用于快速全项目体检。",
        "pred": lambda c: (
            c["severity_default"] == "critical"
            or prefix(c["id"]) in {
                "PER-REPRO", "PER-VER", "MIG-REPLAY",
                "AIG-CORR", "AIG-HALL", "AIG-DEFE", "AIG-SEC", "AIG-DRIFT", "AIG-DEP",
                "GEN-SEC", "SEC",
                "LLM-LOOP", "LLM-ROBUST", "LLM-SEC", "LLM-MCP", "LLM-AGENT", "LLM-GROUND", "LLM-TOOL",
            }
            or c["layer"] in {"通用·错误", "通用·配置", "通用·依赖", "通用·可靠性"}
        ),
    },
    "security": {
        "title": "安全专项池",
        "desc": "安全散点全量（CWE 对齐）＋通用/AI/LLM 安全层＋MCP 与 agentic 安全面（含致命三要素）。适用于发布前安全快检或安全聚焦复审。",
        "pred": lambda c: (
            c["layer"] == "安全散点"
            or prefix(c["id"]) in {"GEN-SEC", "AIG-SEC", "LLM-SEC", "LLM-MCP"}
            or c["defect_class"].startswith(("security-", "mcp-", "lethal-"))
            or c["id"] in {"LLM-AGENT-001", "LLM-AGENT-003"}
        ),
    },
    "llm-app": {
        "title": "LLM 应用专项池",
        "desc": "LLM 应用 14 层全量（prompt/上下文/结构输出/工具/循环/接地/RAG/评估/记忆/成本/观测/韧性/安全/延迟）。适用于 LLM 应用类项目的专项审查。",
        "pred": lambda c: c["layer"].startswith("LLM·"),
    },
    "agentic": {
        "title": "Agentic 专项池",
        "desc": "多代理与工具编排面：代理身份信任链/工具供应链/级联失败与失控/工具调用/循环控制/韧性/记忆与索引投毒/MCP 四面。适用于 agent 系统与 MCP 集成审查。",
        "pred": lambda c: prefix(c["id"]) in {
            "LLM-AGENT", "LLM-MCP", "LLM-TOOL", "LLM-LOOP", "LLM-ROBUST", "LLM-POISON",
        } or c["defect_class"] in {"llm-memory-poisoning", "llm-rag-poisoning"},
    },
    "ai-code": {
        "title": "AI 生成代码专项池",
        "desc": "AI 生成代码 6 层＋个人工程 3 层（正确性/幻觉 API/防御缺失/安全幻觉/重复漂移/依赖失控＋可维护/复现/版本）。适用于 AI 大量产码的项目审查。",
        "pred": lambda c: prefix(c["id"]) in {
            "AIG-CORR", "AIG-HALL", "AIG-DEFE", "AIG-SEC", "AIG-DRIFT", "AIG-DEP",
            "PER-MAINT", "PER-REPRO", "PER-VER",
        },
    },
}


def main():
    full = load_json(FULL)
    with open(FULL, "rb") as f:
        sha_full = hashlib.sha256(f.read()).hexdigest()[:16]
    os.makedirs(OUTDIR, exist_ok=True)
    ids_all = {c["id"] for c in full["checkpoints"]}
    print(f"全量池: {full['template_version']} / {len(ids_all)} 条 / sha={sha_full}")
    for pool_id, spec in RULES.items():
        picked = [c for c in full["checkpoints"] if spec["pred"](c)]
        # 完整性自检：每条被选中的 id 必须在全量池中（防规则笔误造出幽灵条目）
        assert all(c["id"] in ids_all for c in picked), pool_id
        out = {
            "_pool": {
                "pool_id": pool_id,
                "title": spec["title"],
                "desc": spec["desc"],
                "derived_from": {"file": "data/checkpoints.json",
                                 "template_version": full["template_version"],
                                 "sha16": sha_full},
                "selection_rule": "见 audit/build_pools.py RULES（唯一事实源；重新生成即重放）",
                "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
                "count": len(picked),
                "by_severity": dict(Counter(c["severity_default"] for c in picked)),
                "by_verification": dict(Counter(c["verification"] for c in picked)),
            },
            "template_version": full["template_version"],
            "layer_history": full.get("layer_history", ""),
            "checkpoints": picked,
        }
        path = os.path.join(OUTDIR, f"{pool_id}.json")
        with open(path, "w", encoding="utf-8") as f:
            json.dump(out, f, ensure_ascii=False, indent=1)
        print(f"  {pool_id:9s} -> {len(picked):3d} 条  {out['_pool']['by_severity']}")
    # 回读校验
    for pool_id in RULES:
        d = load_json(os.path.join(OUTDIR, f"{pool_id}.json"))
        assert len(d["checkpoints"]) == d["_pool"]["count"]
        assert all(c["id"] in ids_all for c in d["checkpoints"])
    violations = []
    # 不变式：security ⊆ quick（安全专项必须是快速档的子集，否则快速档漏安全面）
    sec = {c["id"] for c in load_json(os.path.join(OUTDIR, "security.json"))["checkpoints"]}
    qk = {c["id"] for c in load_json(os.path.join(OUTDIR, "quick.json"))["checkpoints"]}
    viol = sorted(sec - qk)
    print(f"不变式 security⊆quick: {'OK' if not viol else 'VIOLATION ' + str(viol)}")
    if viol:
        violations.append(("security⊆quick", viol))
    # 不变式：micro ⊆ quick
    mi = {c["id"] for c in load_json(os.path.join(OUTDIR, "micro.json"))["checkpoints"]}
    viol2 = sorted(mi - qk)
    print(f"不变式 micro⊆quick: {'OK' if not viol2 else 'VIOLATION ' + str(viol2)}")
    if viol2:
        violations.append(("micro⊆quick", viol2))
    # 自审 T251 修复：不变式违约必须退出非零——旧版打印 VIOLATION 后仍 exit 0、
    # 收尾照打"全部回读校验 OK"，违约被静默放行
    if violations:
        print(f"失败：{len(violations)} 条池不变式违约——退出码 1")
        return 1
    print("全部回读校验 OK（不变式零违约）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
