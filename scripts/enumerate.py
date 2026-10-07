# -*- coding: utf-8 -*-
"""enumerate.py —— 前置解剖枚举器（八子命令合一，零第三方依赖）。
用法示例:
  py -X utf8 enumerate.py files  --root . --out enumeration/files.jsonl
  py -X utf8 enumerate.py sinks  --root . --out enumeration/sinks.jsonl
子命令: files | entry | env | tools | prompts | deps | intent | sinks
输出: JSONL，每行 {kind,key,file,line,meta}
"""
import argparse
import hashlib
import json
import os
import re
import subprocess
import sys

SKIP_DIRS = {".git", "__pycache__", "node_modules", ".venv", "venv", "dist", "build",
             ".mypy_cache", ".pytest_cache", ".idea", ".vscode", "attic"}
TEXT_EXT = {".py", ".md", ".txt", ".json", ".yaml", ".yml", ".toml", ".ini", ".cfg",
            ".sh", ".js", ".ts", ".tsx", ".jsx", ".html", ".css", ".sql", ".env", ".example"}
READ_LIMIT = 2 * 1024 * 1024   # 字节；文本读入上限（防巨文件拖爆扫描）
GIT_LS_TIMEOUT = 30
GIT_LOG_TIMEOUT = 60


def iter_files(root):
    """git（含未跟踪）优先，空结果或失败退化为 os.walk——未跟踪的 AI 新文件是审查重点。
    降级必须响亮（自审 T197/T094：静默换口径会改写枚举面的完备性含义）。"""
    try:
        out = subprocess.run(["git", "ls-files", "-z", "--cached", "--others", "--exclude-standard"],
                             cwd=root, capture_output=True, timeout=GIT_LS_TIMEOUT)
        if out.returncode == 0:
            # -z：禁 core.quotepath 把中文路径转义为八进制串——转义串 isfile 判否→静默丢件（自审实录）
            names = [l for l in out.stdout.decode("utf-8", "replace").split("\0") if l.strip()]
            if names:
                for line in names:
                    p = os.path.join(root, line)
                    if os.path.isfile(p):
                        yield line.replace("\\", "/")
                return
        print(f"[enumerate] git ls-files 失败(rc={out.returncode})——降级 os.walk，"
              f"被 .gitignore 排除的面不进底册（完备性口径已变）", file=sys.stderr)
    except Exception as e:
        print(f"[enumerate] git 不可用（{e}）——降级 os.walk，枚举面口径已变", file=sys.stderr)
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS]
        for fn in filenames:
            full = os.path.join(dirpath, fn)
            rel = os.path.relpath(full, root).replace("\\", "/")
            yield rel


def read_text(path, limit=READ_LIMIT):
    try:
        if os.path.getsize(path) > limit:
            return None
        with open(path, encoding="utf-8", errors="replace") as f:
            return f.read()
    except Exception:
        return None


def churn_map(root, depth=200):
    """近 depth 次提交的文件改动频次。"""
    try:
        out = subprocess.run(["git", "-c", "core.quotepath=false", "log", "--name-only", "--pretty=format:", "-n", str(depth)],
                             cwd=root, capture_output=True, timeout=GIT_LOG_TIMEOUT)
        counts = {}
        for line in out.stdout.decode("utf-8", "replace").splitlines():
            line = line.strip()
            if line:
                counts[line.replace("\\", "/")] = counts.get(line, 0) + 1
        return counts
    except Exception:
        return {}


def cmd_files(args, root):
    churn = churn_map(root)
    n = oversize = 0
    for rel in iter_files(root):
        full = os.path.join(root, rel)
        text = read_text(full)
        big = text is None and os.path.isfile(full) and os.path.getsize(full) > READ_LIMIT
        loc = (text.count("\n") + 1) if text is not None else (-2 if big else -1)
        sha = ""
        try:
            with open(full, "rb") as f:
                sha = hashlib.sha256(f.read(1 << 20)).hexdigest()[:12]
        except Exception:
            pass
        # 超限文件必须留在底册（自审 T074：3MiB 文件曾对六类底册静默失明）——
        # oversize 标记=内容未被扫描，文件本身在账（对账/覆盖仍认它）
        if big:
            oversize += 1
            print(f"[enumerate] 超限未扫（>{READ_LIMIT//1024//1024}MiB）: {rel}", file=sys.stderr)
        yield {"kind": "file", "key": rel, "file": rel, "line": 0,
               "meta": {"loc": loc, "sha": sha, "churn": churn.get(rel, 0),
                        **({"oversize": True} if big else {})}}
        n += 1
    if oversize:
        print(f"files: {n}（含超限 {oversize} 件——已入底册、内容未扫）")
    else:
        print(f"files: {n}")


def _scan_lines(root, yield_fn):
    for rel in iter_files(root):
        if os.path.splitext(rel)[1].lower() not in TEXT_EXT:
            continue
        text = read_text(os.path.join(root, rel))
        if text is None:
            continue
        for i, line in enumerate(text.splitlines(), 1):
            r = yield_fn(rel, i, line)
            if r:
                yield r


ENTRY_PATTERNS = [
    (re.compile(r'if\s+__name__\s*==\s*[\'"]__main__[\'"]'), "main-guard"),
    (re.compile(r'^(?:async\s+)?def\s+main\s*\('), "def-main"),
    (re.compile(r'@app\.(?:route|get|post|put|delete)\s*\('), "http-route"),
    (re.compile(r'@(?:router|bp)\.(?:get|post|put|delete|route)\s*\('), "http-route"),
    (re.compile(r'FastAPI\s*\(|Flask\s*\(|argparse\.ArgumentParser\s*\('), "framework-init"),
]
ENV_PATTERNS = [
    re.compile(r'os\.environ(?:\.get)?\s*[\[\(]\s*[\'"]([A-Za-z0-9_]+)[\'"]'),
    re.compile(r'os\.getenv\s*\(\s*[\'"]([A-Za-z0-9_]+)[\'"]'),
]
SINK_PATTERNS = [
    (re.compile(r'\bexec\s*\('), "exec"),
    (re.compile(r'\beval\s*\('), "eval"),
    (re.compile(r'pickle\.loads?\s*\('), "pickle"),
    (re.compile(r'yaml\.load\s*\((?![^)]*Loader)'), "yaml-unsafe"),
    (re.compile(r'\bsubprocess\.(?:run|Popen|call|check_output)\s*\('), "subprocess"),
    (re.compile(r'\bos\.system\s*\('), "os-system"),
    (re.compile(r'__import__\s*\(|importlib\.import_module\s*\('), "dynamic-import"),
    (re.compile(r'innerHTML|dangerouslySetInnerHTML|v-html'), "html-inject"),
    (re.compile(r'open\s*\([^)]*[\'"]w'), "file-write"),
]
TOOL_PATTERNS = [
    (re.compile(r'@(?:mcp\.)?tool\b'), "tool-decorator"),
    (re.compile(r'\badd_tool\b|Tool\s*\(|\btools\s*=\s*\['), "tool-registry"),
]


def cmd_entry(args, root):
    for row in _scan_lines(root, _match_entry):
        yield row


def _match_entry(rel, i, line):
    for pat, name in ENTRY_PATTERNS:
        if pat.search(line):
            return {"kind": "entry", "key": name, "file": rel, "line": i, "meta": {"symbol": name}}
    return None


def cmd_env(args, root):
    for row in _scan_lines(root, _match_env):
        yield row


def _match_env(rel, i, line):
    for pat in ENV_PATTERNS:
        m = pat.search(line)
        if m:
            return {"kind": "env", "key": m.group(1), "file": rel, "line": i, "meta": {}}
    return None


def cmd_sinks(args, root):
    for row in _scan_lines(root, _match_sink):
        yield row


def _match_sink(rel, i, line):
    for pat, name in SINK_PATTERNS:
        if pat.search(line):
            return {"kind": "sink", "key": name, "file": rel, "line": i, "meta": {"type": name}}
    return None


def cmd_tools(args, root):
    for row in _scan_lines(root, _match_tool):
        yield row


def _match_tool(rel, i, line):
    for pat, name in TOOL_PATTERNS:
        if pat.search(line):
            return {"kind": "tool", "key": name, "file": rel, "line": i, "meta": {"type": name}}
    return None


def cmd_prompts(args, root):
    n = 0
    for rel in iter_files(root):
        base = os.path.basename(rel).lower()
        if ("prompt" in base or "instruction" in base) and os.path.splitext(rel)[1] in (".md", ".txt", ".prompt", ".jinja"):
            yield {"kind": "prompt", "key": rel, "file": rel, "line": 0, "meta": {"source": "file"}}
            n += 1
        elif os.path.splitext(rel)[1].lower() in TEXT_EXT:
            text = read_text(os.path.join(root, rel))
            if not text:
                continue
            for i, line in enumerate(text.splitlines(), 1):
                if re.search(r'^\s*(?:prompt|system_prompt|instruction)\s*=\s*[\'"]', line):
                    yield {"kind": "prompt", "key": rel, "file": rel, "line": i, "meta": {"source": "inline"}}
                    n += 1
    print(f"prompts: {n}")


DEPS_FILES = ("requirements.txt", "pyproject.toml", "package.json", "Pipfile", "environment.yml")


def cmd_deps(args, root):
    n = 0
    for rel in iter_files(root):
        if os.path.basename(rel) in DEPS_FILES:
            text = read_text(os.path.join(root, rel)) or ""
            for i, line in enumerate(text.splitlines(), 1):
                s = line.strip()
                if rel.endswith("requirements.txt") and s and not s.startswith("#"):
                    yield {"kind": "dep", "key": s.split("=")[0].split(">")[0].split("<")[0].strip(),
                           "file": rel, "line": i, "meta": {"spec": s, "locked": "==" in s}}
                    n += 1
                elif s and not s.startswith("#") and ("=" in s or '"' in s):
                    m = re.search(r'[\'"]([A-Za-z0-9_.\-]+)[\'"]\s*[:=]', s)
                    if m and re.search(r'[\'"][\^~>=<0-9]', s):
                        yield {"kind": "dep", "key": m.group(1), "file": rel, "line": i,
                               "meta": {"spec": s, "locked": False}}
                        n += 1
    print(f"deps: {n}")


def cmd_intent(args, root):
    n = 0
    for rel in iter_files(root):
        base = os.path.basename(rel).lower()
        if base.startswith("readme"):
            yield {"kind": "intent", "key": "readme", "file": rel, "line": 0, "meta": {"source": "readme"}}
            n += 1
        elif re.match(r'(?:^|/)(?:test_[^/]*\.py|[^/]*_tests?\.py)$', rel) or "/tests/" in f"/{rel}" or "/test/" in f"/{rel}":
            yield {"kind": "intent", "key": "test", "file": rel, "line": 0, "meta": {"source": "test"}}
            n += 1
    print(f"intent: {n}")


CMDS = {"files": cmd_files, "entry": cmd_entry, "env": cmd_env, "tools": cmd_tools,
        "prompts": cmd_prompts, "deps": cmd_deps, "intent": cmd_intent, "sinks": cmd_sinks}


def main():
    ap = argparse.ArgumentParser(description="枚举器八子命令（前置解剖机械臂）")
    ap.add_argument("cmd", choices=sorted(CMDS.keys()))
    ap.add_argument("--root", default=".")
    ap.add_argument("--out", required=True)
    args = ap.parse_args()
    root = os.path.abspath(args.root)
    os.makedirs(os.path.dirname(os.path.abspath(args.out)), exist_ok=True)
    gen = CMDS[args.cmd](args, root)
    n = 0
    with open(args.out, "w", encoding="utf-8") as f:
        for row in gen:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
            n += 1
    print(f"{args.cmd}: wrote {n} rows -> {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
