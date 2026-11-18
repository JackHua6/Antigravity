#!/usr/bin/env python3
"""
AI Token 工作台看板 · 全自动本地扫描与快照生成器 (Windows / macOS / Linux)

功能说明：
1. 自动探测本机 tokscale CLI（支持全局安装 / npm / pnpm / nvm / npx 自动按需运行）。
2. 并发采集各 AI 软件的每日贡献、分模型用量、月度统计、分软件 24 小时节律与精准活跃时长
   （覆盖全部历史 / 近 30 天 / 本月 / 近 7 天四档预设）。
3. 将每款软件的活跃时长按权重分配写入每日 clientActiveMs，支持前端任意自定义日期区间与多选筛选。
4. Windows 环境自动附加扫描「豆包工作 (DoubaoWork)」本地轨迹；如存在可选的历史归档
   （trae-archive.json 或页面内嵌 trae-archive），自动合并并统一重算 6 级热力深度。
5. 所有数据仅在本地生成并直接内嵌进单文件 token_dashboard.html，不向任何外部服务器上报数据。
"""

from __future__ import annotations

import argparse
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import time
from typing import Any
import webbrowser

BASE_DIR = Path(__file__).resolve().parent
HTML_PATH = BASE_DIR / "token_dashboard.html"
TRAE_ARCHIVE_FILE = BASE_DIR / "trae-archive.json"
LOCAL_TZ = datetime.now().astimezone().tzinfo

CLIENT_LABELS: dict[str, str] = {
    "antigravity-extension": "Antigravity",
    "antigravity": "Antigravity App",
    "antigravity-cli": "Antigravity CLI",
    "claude": "Claude Code",
    "codex": "Codex",
    "cursor": "Cursor",
    "windsurf": "Windsurf",
    "workbuddy": "WorkBuddy",
    "codebuddy": "CodeBuddy",
    "doubaowork": "DouBao",
    "trae": "Trae",
    "trae-cn": "Trae",
    "zcode": "ZCode",
    "qoder": "Qoder",
    "dsh": "DeepSeek Harness",
    "gemini": "Gemini CLI",
    "opencode": "OpenCode",
    "cline": "Cline",
    "roocode": "Roo Code",
    "kilocode": "Kilo Code",
    "copilot": "GitHub Copilot",
    "kiro": "Kiro",
    "zed": "Zed AI",
    "warp": "Warp",
    "amp": "Amp",
    "droid": "Droid",
    "kimi": "Kimi CLI",
    "qwen": "Qwen Code",
    "openclaw": "OpenClaw",
    "hermes": "Hermes",
    "cherrystudio": "Cherry Studio",
    "junie": "Junie",
    "goose": "Goose",
    "lmstudio": "LM Studio",
}

TRAE_ARCHIVE_START = '<script id="trae-archive" type="application/json">'
DATA_START = '<script id="initial-data" type="application/json">'
SCRIPT_END = "</script>"

# DoubaoWork (Volcengine Ark Seed 2.1 Pro) default rates: CNY 6/1.2/30 per 1M @ 7.20 USD/CNY
DOUBAO_INPUT_PER_TOK = 6.0 / 7.2 / 1_000_000
DOUBAO_CACHE_READ_PER_TOK = 1.2 / 7.2 / 1_000_000
DOUBAO_OUTPUT_PER_TOK = 30.0 / 7.2 / 1_000_000

DOUBAO_TIKTOKEN_HELPER = r'''
import json, pathlib, sys
import tiktoken

enc = tiktoken.get_encoding("cl100k_base")

def msg_text(msg):
    parts = [msg.get("role") or ""]
    c = msg.get("content")
    if isinstance(c, str):
        parts.append(c)
    elif isinstance(c, list):
        for b in c:
            parts.append(b if isinstance(b, str) else json.dumps(b, ensure_ascii=False))
    elif c is not None:
        parts.append(json.dumps(c, ensure_ascii=False))
    for call in msg.get("tool_calls") or []:
        fn = call.get("function") or {}
        parts.append(str(fn.get("name") or ""))
        args = fn.get("arguments")
        if isinstance(args, str):
            parts.append(args)
        elif args is not None:
            parts.append(json.dumps(args, ensure_ascii=False))
    return "\n".join(parts)

out = {}
for p_str in sys.argv[1:]:
    p = pathlib.Path(p_str)
    rows = []
    for line in p.read_text("utf-8", errors="replace").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            m = json.loads(line)
        except Exception:
            continue
        rows.append([m.get("role") or "", len(enc.encode(msg_text(m)))])
    out[p_str] = rows
print(json.dumps(out))
'''


def _log(msg: str, quiet: bool = False) -> None:
    if not quiet:
        print(msg, flush=True)


def find_tokscale_command() -> tuple[list[str], bool]:
    """
    Locate native tokscale binary across Windows/macOS/Linux or fall back to npx.
    Returns (cmd_base, uses_npx).
    """
    env_bin = os.environ.get("TOKSCALE_BIN", "").strip()
    if env_bin and os.path.isfile(env_bin):
        return [env_bin], False

    for name in ("tokscale", "tokscale.exe", "tokscale.cmd"):
        found = shutil.which(name)
        if found:
            return [found], False

    user_home = Path.home()
    bin_names = ["tokscale.exe", "tokscale"] if os.name == "nt" else ["tokscale"]

    search_roots: list[Path] = []
    if os.name == "nt":
        localapp = Path(os.environ.get("LOCALAPPDATA", str(user_home / "AppData" / "Local")))
        roaming = Path(os.environ.get("APPDATA", str(user_home / "AppData" / "Roaming")))
        search_roots.extend([
            localapp / "npm-cache" / "_npx",
            roaming / "npm" / "node_modules",
            roaming / "npm",
            user_home / ".npm" / "_npx",
        ])
    else:
        search_roots.extend([
            user_home / ".npm" / "_npx",
            user_home / ".local" / "share",
            user_home / ".nvm" / "versions" / "node",
            Path("/opt/homebrew/bin"),
            Path("/usr/local/bin"),
        ])

    # Check common global npm prefix caches (without assuming personal drive letters)
    npm_cmd = shutil.which("npm") or shutil.which("npm.cmd")
    if npm_cmd:
        try:
            p = subprocess.run(
                [npm_cmd, "config", "get", "cache"],
                stdin=subprocess.DEVNULL,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=5,
            )
            cache_dir = p.stdout.strip()
            if p.returncode == 0 and cache_dir and cache_dir != "undefined":
                search_roots.insert(0, Path(cache_dir) / "_npx")
        except Exception:
            pass

    for root in search_roots:
        if not root.exists():
            continue
        for bname in bin_names:
            direct = root / bname
            if direct.is_file():
                return [str(direct)], False
            for match in root.glob(f"*/node_modules/@tokscale/*/bin/{bname}"):
                if match.is_file():
                    return [str(match)], False
            for match in root.glob(f"**/bin/{bname}"):
                if "@tokscale" in str(match) and match.is_file():
                    return [str(match)], False

    npx_cmd = shutil.which("npx") or shutil.which("npx.cmd")
    if npx_cmd:
        return [npx_cmd, "--yes", "tokscale@latest"], True

    raise RuntimeError(
        "未检测到 tokscale 或 Node.js (npx)。\n"
        "请先安装 Node.js (>=18) 后运行一次：npm install -g tokscale\n"
        "安装完成后重新执行本脚本即可。"
    )


def _run_subprocess(cmd: list[str], timeout: int) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        cmd,
        stdin=subprocess.DEVNULL,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=timeout,
    )


def run_tokscale_json(
    cmd_base: list[str],
    args: list[str],
    timeout: int = 60,
    allow_online_retry: bool = True,
) -> dict[str, Any]:
    """Execute a tokscale subcommand and parse JSON stdout; retry online if offline cache misses."""
    proc = _run_subprocess([*cmd_base, *args], timeout=timeout)
    if proc.returncode != 0 and allow_online_retry and "--offline" in args:
        online_args = [a for a in args if a != "--offline"]
        proc = _run_subprocess([*cmd_base, *online_args], timeout=max(timeout, 90))
    if proc.returncode != 0:
        err_msg = (proc.stderr or proc.stdout or "").strip()
        raise RuntimeError(f"tokscale 执行失败 ({' '.join(args)}): {err_msg}")
    text = proc.stdout.strip()
    start = text.find("{")
    if start == -1:
        return {}
    return json.loads(text[start:])


def run_tokscale_graph(cmd_base: list[str], timeout: int = 60) -> dict[str, Any]:
    """Export tokscale contribution graph JSON via temp output file."""
    temp_file = BASE_DIR / ".tmp_graph.json"
    if temp_file.exists():
        temp_file.unlink()
    args = ["graph", "--offline", "--no-spinner", "--output", str(temp_file)]
    try:
        proc = _run_subprocess([*cmd_base, *args], timeout=timeout)
        if (proc.returncode != 0 or not temp_file.exists()) and "--offline" in args:
            if temp_file.exists():
                temp_file.unlink()
            online_args = [a for a in args if a != "--offline"]
            proc = _run_subprocess([*cmd_base, *online_args], timeout=max(timeout, 90))
        if proc.returncode != 0 or not temp_file.exists():
            err_msg = (proc.stderr or proc.stdout or "").strip()
            raise RuntimeError(f"tokscale graph 执行失败: {err_msg}")
        return json.loads(temp_file.read_text(encoding="utf-8"))
    finally:
        if temp_file.exists():
            temp_file.unlink()


def fetch_time_metrics_map(
    cmd_base: list[str], clients: list[str], extra_args: list[str]
) -> dict[str, dict[str, Any]]:
    """Fetch per-client time-metrics concurrently for a given date filter."""
    results: dict[str, dict[str, Any]] = {}

    def _one(target: str) -> tuple[str, dict[str, Any]]:
        args = ["time-metrics", "--offline", "--no-spinner", "--json", *extra_args]
        if target != "__all__":
            args.extend(["-c", target])
        data = run_tokscale_json(cmd_base, args)
        return target, data.get("metrics", {})

    targets = ["__all__", *clients]
    with ThreadPoolExecutor(max_workers=min(8, max(1, len(targets)))) as pool:
        futures = [pool.submit(_one, t) for t in targets]
        for fut in as_completed(futures):
            try:
                key, metrics = fut.result()
                if metrics:
                    results[key] = metrics
            except Exception:
                pass
    return results


def fetch_per_client_hourly(cmd_base: list[str], clients: list[str]) -> list[dict[str, Any]]:
    """Fetch per-client hourly buckets so single-client filtering has clean 24h rhythm."""
    if not clients:
        return []

    buckets: list[dict[str, Any]] = []

    def _one(cid: str) -> list[dict[str, Any]]:
        data = run_tokscale_json(cmd_base, ["hourly", "--offline", "--no-spinner", "--json", "-c", cid])
        out_rows: list[dict[str, Any]] = []
        for e in data.get("entries", []):
            out_rows.append({
                "h": e["hour"],
                "c": [cid],
                "m": e.get("models", []),
                "i": e.get("input", 0),
                "o": e.get("output", 0),
                "cr": e.get("cacheRead", 0),
                "cw": e.get("cacheWrite", 0),
                "n": e.get("messageCount", 0),
                "cost": round(float(e.get("cost", 0.0)), 6),
            })
        return out_rows

    with ThreadPoolExecutor(max_workers=min(6, max(1, len(clients)))) as pool:
        futures = [pool.submit(_one, cid) for cid in clients]
        for fut in as_completed(futures):
            try:
                buckets.extend(fut.result())
            except Exception:
                pass
    return buckets


def _estimate_tokens_fallback(msg: dict[str, Any]) -> int:
    """Fallback tokenizer calibrated against cl100k_base (~1 CJK char ≈ 1 tok, ~3.8 ASCII ≈ 1 tok)."""
    parts = [msg.get("role") or ""]
    c = msg.get("content")
    if isinstance(c, str):
        parts.append(c)
    elif isinstance(c, list):
        for b in c:
            parts.append(b if isinstance(b, str) else json.dumps(b, ensure_ascii=False))
    elif c is not None:
        parts.append(json.dumps(c, ensure_ascii=False))
    for call in msg.get("tool_calls") or []:
        fn = call.get("function") or {}
        parts.append(str(fn.get("name") or ""))
        args = fn.get("arguments")
        if isinstance(args, str):
            parts.append(args)
        elif args is not None:
            parts.append(json.dumps(args, ensure_ascii=False))
    text = "\n".join(parts)
    cjk = sum(1 for ch in text if "\u4e00" <= ch <= "\u9fff")
    other = len(text) - cjk
    return max(1, round(cjk * 1.0 + other / 3.8))


def _parse_utc_to_local(ts_str: str) -> datetime | None:
    m = re.match(r"^(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2})", ts_str.strip())
    if not m:
        return None
    from datetime import timezone
    return (
        datetime.strptime(m.group(1), "%Y-%m-%dT%H:%M:%S")
        .replace(tzinfo=timezone.utc)
        .astimezone(LOCAL_TZ)
    )


def _tokenize_doubao_trajectories(paths: list[Path], user_data_dir: Path) -> dict[str, list[list[Any]]]:
    """Count per-message tokens using Doubao sandbox tiktoken (cl100k_base), or fallback."""
    sand_pys = sorted(user_data_dir.glob("sandbox_runtime/bases/*/python/python.exe"))
    if sand_pys:
        try:
            proc = subprocess.run(
                [str(sand_pys[0]), "-B", "-X", "utf8", "-c", DOUBAO_TIKTOKEN_HELPER, *[str(p) for p in paths]],
                stdin=subprocess.DEVNULL,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=30,
            )
            if proc.returncode == 0 and proc.stdout.strip().startswith("{"):
                return json.loads(proc.stdout.strip())
        except Exception:
            pass

    fallback: dict[str, list[list[Any]]] = {}
    for p in paths:
        rows: list[list[Any]] = []
        for line in p.read_text("utf-8", errors="replace").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                m = json.loads(line)
            except Exception:
                continue
            rows.append([m.get("role") or "", _estimate_tokens_fallback(m)])
        fallback[str(p)] = rows
    return fallback


def collect_doubaowork_source() -> dict[str, Any] | None:
    """Scan local DoubaoWork trajectory.jsonl traces (Windows) and convert to unified client source."""
    if os.name != "nt":
        return None
    localapp = Path(os.environ.get("LOCALAPPDATA", str(Path.home() / "AppData" / "Local")))
    user_data_dir = localapp / "DoubaoWork" / "User Data"
    dw_ws = user_data_dir / "Default" / ".doubaowork" / "agent_mode" / "workspace"
    sessions_root = dw_ws / ".sessions"
    if not sessions_root.exists():
        return None

    session_dirs = [d for d in sorted(sessions_root.iterdir()) if d.is_dir()]
    traj_jobs: list[tuple[Path, Path]] = []
    for sdir in session_dirs:
        for tpath in sorted(sdir.glob("agents/*/system/trajectory.jsonl")):
            traj_jobs.append((sdir, tpath))
    if not traj_jobs:
        return None

    tokenized_map = _tokenize_doubao_trajectories([t for _, t in traj_jobs], user_data_dir)
    entries: list[dict[str, Any]] = []
    bursts: list[dict[str, Any]] = []
    seen_sessions: set[str] = set()

    for sdir, tpath in traj_jobs:
        rows = tokenized_map.get(str(tpath)) or []
        if not rows:
            continue
        sess_id = sdir.name
        seen_sessions.add(sess_id)

        stamps: list[datetime] = []
        apath = tpath.parent / "assignment.md"
        if apath.exists():
            atxt = apath.read_text("utf-8", errors="replace")
            raw_stamps = re.findall(r"## \[([^\]]+)\] 需求", atxt) or re.findall(r"- Created:\s*(\S+)", atxt)
            stamps = [dt for dt in (_parse_utc_to_local(s) for s in raw_stamps) if dt is not None]
        if not stamps:
            stamps = [datetime.fromtimestamp(tpath.stat().st_ctime, tz=LOCAL_TZ)]

        pts: list[int] = [int(dt.timestamp()) for dt in stamps]
        for extra_root in [sdir, dw_ws / "conversation" / sess_id]:
            if extra_root.exists():
                for f in extra_root.rglob("*"):
                    if f.is_file() and f.stat().st_size > 0:
                        st = f.stat()
                        pts.extend([int(st.st_ctime), int(st.st_mtime)])
        snap_root = user_data_dir / "coding" / "snapshot"
        if snap_root.exists():
            for f in snap_root.rglob(f"*/{sess_id}/*"):
                if f.is_file() and f.stat().st_size > 0:
                    st = f.stat()
                    pts.extend([int(st.st_ctime), int(st.st_mtime)])

        sess_bursts: list[list[int]] = []
        for t in sorted(set(pts)):
            if not sess_bursts or t - sess_bursts[-1][1] > 900:
                sess_bursts.append([t, t])
            else:
                sess_bursts[-1][1] = t
        for a, b in sess_bursts:
            bursts.append({
                "session": sess_id,
                "date": datetime.fromtimestamp(a, tz=LOCAL_TZ).strftime("%Y-%m-%d"),
                "activeMs": (b - a) * 1000 + 120_000,
            })

        cur_dt = stamps[0]
        u_ptr = 0
        pref_sum = 0
        running_sum = 0
        for role, tk in rows:
            if role == "user":
                if u_ptr + 1 < len(stamps):
                    cur_dt = stamps[u_ptr + 1]
                u_ptr += 1
            elif role == "assistant":
                new_in = running_sum - pref_sum
                cr = pref_sum
                out = tk
                cost = (
                    new_in * DOUBAO_INPUT_PER_TOK
                    + cr * DOUBAO_CACHE_READ_PER_TOK
                    + out * DOUBAO_OUTPUT_PER_TOK
                )
                entries.append({
                    "date": cur_dt.strftime("%Y-%m-%d"),
                    "hour": cur_dt.strftime("%Y-%m-%d %H:00"),
                    "ts": cur_dt.strftime("%Y-%m-%d %H:%M"),
                    "model": "doubao-agent",
                    "workspaceKey": f"doubaowork-{sess_id}",
                    "workspaceLabel": f"DouBao · 会话 {sess_id}",
                    "input": new_in,
                    "output": out,
                    "cacheRead": cr,
                    "cacheWrite": 0,
                    "cost": cost,
                    "messages": 1,
                    "activeMs": 0,
                })
                pref_sum = running_sum
            running_sum += tk

    if not entries:
        return None

    return {
        "client": "doubaowork",
        "provider": "bytedance",
        "sessionCount": len(seen_sessions),
        "totalActiveTimeMs": sum(b["activeMs"] for b in bursts),
        "longestContinuousMs": max((b["activeMs"] for b in bursts), default=0),
        "bursts": bursts,
        "entries": entries,
    }


def extract_optional_trae_archive(html_text: str) -> dict[str, Any] | None:
    """Load optional frozen Trae archive from trae-archive.json or embedded script tag if present."""
    data: dict[str, Any] | None = None
    if TRAE_ARCHIVE_FILE.exists():
        try:
            data = json.loads(TRAE_ARCHIVE_FILE.read_text(encoding="utf-8"))
        except Exception:
            data = None

    if data is None:
        i0 = html_text.find(TRAE_ARCHIVE_START)
        if i0 != -1:
            val_start = i0 + len(TRAE_ARCHIVE_START)
            i1 = html_text.find(SCRIPT_END, val_start)
            if i1 != -1:
                raw = html_text[val_start:i1].strip()
                if raw and raw != "__TRAE_ARCHIVE__":
                    data = json.loads(raw.replace("<\\/script>", "</script>"))

    if not data or not data.get("entries"):
        return None

    norm_entries: list[dict[str, Any]] = []
    for item in data["entries"]:
        product = item.get("product") or "Trae"
        norm_entries.append({
            **item,
            "workspaceKey": f"trae-cn-{product.lower()}",
            "workspaceLabel": f"Trae · {product}",
        })
    return {
        "client": "trae-cn",
        "provider": "trae-cn",
        "sessionCount": int(data.get("sessionCount", len(norm_entries)) or len(norm_entries)),
        "totalActiveTimeMs": int(data.get("totalActiveTimeMs", 0) or 0),
        "longestContinuousMs": int(data.get("longestContinuousMs", 0) or 0),
        "entries": norm_entries,
    }


def _compute_source_range_metrics(
    source_data: dict[str, Any], since: str | None = None, until: str | None = None
) -> dict[str, Any]:
    """Compute time-metrics for a normalized custom client source within [since, until]."""
    entries = source_data.get("entries") or []
    filtered = [
        e
        for e in entries
        if (not since or (e.get("date") or "") >= since)
        and (not until or (e.get("date") or "") <= until)
    ]
    if not filtered:
        return {}

    bursts = source_data.get("bursts")
    if bursts is not None:
        f_bursts = [
            b
            for b in bursts
            if (not since or b["date"] >= since) and (not until or b["date"] <= until)
        ]
        if not f_bursts:
            return {}
        total_ms = sum(int(b["activeMs"]) for b in f_bursts)
        longest_ms = max(int(b["activeMs"]) for b in f_bursts)
        sess_count = len({b["session"] for b in f_bursts})
    elif not since and not until and source_data.get("totalActiveTimeMs"):
        total_ms = int(source_data.get("totalActiveTimeMs", 0) or 0)
        longest_ms = int(source_data.get("longestContinuousMs", 0) or 0)
        sess_count = int(source_data.get("sessionCount", len(filtered)) or len(filtered))
    else:
        total_ms = sum(int(e.get("activeMs", 0) or 0) for e in filtered)
        sess_count = sum(int(e.get("messages", 1) or 1) for e in filtered)
        longest_ms = 0
        parsed_ts: list[datetime] = []
        for e in filtered:
            ts_str = e.get("ts")
            if ts_str:
                try:
                    parsed_ts.append(datetime.strptime(ts_str, "%Y-%m-%d %H:%M"))
                except ValueError:
                    pass
        if parsed_ts:
            parsed_ts.sort()
            cur_start = cur_end = parsed_ts[0]
            for dt in parsed_ts[1:]:
                if (dt - cur_end).total_seconds() <= 300:
                    cur_end = dt
                else:
                    span_ms = int((cur_end - cur_start).total_seconds() * 1000) + 120_000
                    longest_ms = max(longest_ms, span_ms)
                    cur_start = cur_end = dt
            longest_ms = max(longest_ms, int((cur_end - cur_start).total_seconds() * 1000) + 120_000)
        elif total_ms > 0:
            longest_ms = max(int(e.get("activeMs", 0) or 0) for e in filtered)

    return {
        "total_active_time_ms": total_ms,
        "total_wall_time_ms": total_ms,
        "longest_continuous_ms": longest_ms,
        "max_concurrent_sessions": 1,
        "session_count": sess_count,
    }


def _merge_source_into_time_metrics(
    tm_bucket: dict[str, dict[str, Any]],
    source_data: dict[str, Any],
    since: str | None = None,
    until: str | None = None,
) -> None:
    """Inject normalized client active time metrics into a range bucket and __all__ total."""
    m = _compute_source_range_metrics(source_data, since=since, until=until)
    if not m:
        return
    tm_bucket[source_data["client"]] = m
    if "__all__" not in tm_bucket:
        tm_bucket["__all__"] = {
            "total_active_time_ms": 0,
            "total_wall_time_ms": 0,
            "longest_continuous_ms": 0,
            "max_concurrent_sessions": 1,
            "session_count": 0,
        }
    all_m = tm_bucket["__all__"]
    all_m["total_active_time_ms"] = int(all_m.get("total_active_time_ms", 0) or 0) + m["total_active_time_ms"]
    all_m["total_wall_time_ms"] = int(all_m.get("total_wall_time_ms", 0) or 0) + m["total_wall_time_ms"]
    all_m["session_count"] = int(all_m.get("session_count", 0) or 0) + m["session_count"]
    all_m["longest_continuous_ms"] = max(
        int(all_m.get("longest_continuous_ms", 0) or 0),
        m["longest_continuous_ms"],
    )


def merge_custom_client_into_snapshot(
    snapshot: dict[str, Any],
    source_data: dict[str, Any] | None,
    since_30: str | None = None,
    since_month: str | None = None,
    since_7: str | None = None,
) -> None:
    """Merge a normalized non-tokscale client source into all snapshot views."""
    if not source_data or not source_data.get("entries"):
        return

    client_id = source_data["client"]
    provider_id = source_data.get("provider") or client_id
    if client_id not in snapshot["summary"]["clients"]:
        snapshot["summary"]["clients"].append(client_id)

    by_date: dict[str, dict[str, Any]] = {c["date"]: c for c in snapshot["contributions"]}
    day_client_agg: dict[tuple[str, str], dict[str, Any]] = {}
    model_agg: dict[str, dict[str, Any]] = {}
    monthly_add: dict[str, dict[str, Any]] = {}
    hourly_agg: dict[str, dict[str, Any]] = {}
    ws_agg: dict[tuple[str, str], dict[str, Any]] = {}

    def _ensure_day(dstr: str) -> dict[str, Any]:
        if dstr not in by_date:
            by_date[dstr] = {
                "date": dstr,
                "totals": {"tokens": 0, "cost": 0.0, "messages": 0},
                "intensity": 0,
                "tokenBreakdown": {"input": 0, "output": 0, "cacheRead": 0, "cacheWrite": 0, "reasoning": 0},
                "clients": [],
                "activeTimeMs": 0,
            }
        return by_date[dstr]

    for item in source_data["entries"]:
        date_str = item.get("date") or datetime.now(LOCAL_TZ).strftime("%Y-%m-%d")
        hour_str = item.get("hour") or f"{date_str} 00:00"
        model = item.get("model") or f"{client_id}-unknown"
        ws_key_id = item.get("workspaceKey") or client_id
        ws_label = item.get("workspaceLabel") or client_id
        inp = int(item.get("input", 0) or 0)
        out = int(item.get("output", 0) or 0)
        cr = int(item.get("cacheRead", 0) or 0)
        cw = int(item.get("cacheWrite", 0) or 0)
        cost = float(item.get("cost", 0.0) or 0.0)
        msgs = int(item.get("messages", 1) or 1)
        active_ms = int(item.get("activeMs", 0) or 0)
        tot = inp + out + cr + cw

        if model not in snapshot["summary"]["models"]:
            snapshot["summary"]["models"].append(model)
        snapshot["summary"]["totalTokens"] += tot
        snapshot["summary"]["totalCost"] += cost

        day_obj = _ensure_day(date_str)
        day_obj["totals"]["tokens"] += tot
        day_obj["totals"]["cost"] += cost
        day_obj["totals"]["messages"] += msgs
        day_obj["tokenBreakdown"]["input"] += inp
        day_obj["tokenBreakdown"]["output"] += out
        day_obj["tokenBreakdown"]["cacheRead"] += cr
        day_obj["tokenBreakdown"]["cacheWrite"] += cw
        day_obj["activeTimeMs"] = int(day_obj.get("activeTimeMs", 0) or 0) + active_ms

        dc_key = (date_str, model)
        if dc_key not in day_client_agg:
            day_client_agg[dc_key] = {
                "client": client_id,
                "modelId": model,
                "providerId": provider_id,
                "tokens": {"input": 0, "output": 0, "cacheRead": 0, "cacheWrite": 0, "reasoning": 0},
                "cost": 0.0,
                "messages": 0,
            }
        dc = day_client_agg[dc_key]
        dc["tokens"]["input"] += inp
        dc["tokens"]["output"] += out
        dc["tokens"]["cacheRead"] += cr
        dc["tokens"]["cacheWrite"] += cw
        dc["cost"] += cost
        dc["messages"] += msgs

        mkey = f"{client_id}::{model}"
        if mkey not in model_agg:
            model_agg[mkey] = {
                "client": client_id,
                "model": model,
                "provider": provider_id,
                "input": 0,
                "output": 0,
                "cacheRead": 0,
                "cacheWrite": 0,
                "reasoning": 0,
                "messageCount": 0,
                "cost": 0.0,
                "performance": None,
            }
        mobj = model_agg[mkey]
        mobj["input"] += inp
        mobj["output"] += out
        mobj["cacheRead"] += cr
        mobj["cacheWrite"] += cw
        mobj["messageCount"] += msgs
        mobj["cost"] += cost

        ym = date_str[:7]
        if ym not in monthly_add:
            monthly_add[ym] = {"input": 0, "output": 0, "cacheRead": 0, "cacheWrite": 0, "messageCount": 0, "cost": 0.0, "models": set()}
        mo = monthly_add[ym]
        mo["input"] += inp
        mo["output"] += out
        mo["cacheRead"] += cr
        mo["cacheWrite"] += cw
        mo["messageCount"] += msgs
        mo["cost"] += cost
        mo["models"].add(model)

        if hour_str not in hourly_agg:
            hourly_agg[hour_str] = {
                "h": hour_str,
                "c": [client_id],
                "m": set(),
                "i": 0,
                "o": 0,
                "cr": 0,
                "cw": 0,
                "n": 0,
                "cost": 0.0,
            }
        hobj = hourly_agg[hour_str]
        hobj["m"].add(model)
        hobj["i"] += inp
        hobj["o"] += out
        hobj["cr"] += cr
        hobj["cw"] += cw
        hobj["n"] += msgs
        hobj["cost"] += cost

        ws_key = (ws_key_id, model)
        if ws_key not in ws_agg:
            ws_agg[ws_key] = {
                "client": client_id,
                "mergedClients": client_id,
                "workspaceKey": ws_key_id,
                "workspaceLabel": ws_label,
                "model": model,
                "provider": provider_id,
                "input": 0,
                "output": 0,
                "cacheRead": 0,
                "cacheWrite": 0,
                "reasoning": 0,
                "messageCount": 0,
                "cost": 0.0,
                "performance": None,
            }
        wobj = ws_agg[ws_key]
        wobj["input"] += inp
        wobj["output"] += out
        wobj["cacheRead"] += cr
        wobj["cacheWrite"] += cw
        wobj["messageCount"] += msgs
        wobj["cost"] += cost

    for b in source_data.get("bursts") or []:
        day_obj = _ensure_day(b["date"])
        day_obj["activeTimeMs"] = int(day_obj.get("activeTimeMs", 0) or 0) + int(b["activeMs"])

    for (date_str, _model), dc in day_client_agg.items():
        by_date[date_str]["clients"].append(dc)

    snapshot["contributions"] = sorted(by_date.values(), key=lambda x: x["date"])
    snapshot["models"].extend(model_agg.values())

    for hobj in hourly_agg.values():
        hobj["m"] = sorted(hobj["m"])
        hobj["cost"] = round(hobj["cost"], 6)
    snapshot["hourly"].extend(hourly_agg.values())
    snapshot["hourly"] = sorted(snapshot["hourly"], key=lambda x: x["h"])

    snapshot["workspaces"].extend(ws_agg.values())
    snapshot["workspaces"] = sorted(
        snapshot["workspaces"],
        key=lambda x: (x.get("cost", 0.0), x.get("input", 0) + x.get("cacheRead", 0)),
        reverse=True,
    )[:200]

    _merge_source_into_time_metrics(snapshot["timeMetricsByRange"]["all"], source_data)
    if since_30:
        _merge_source_into_time_metrics(snapshot["timeMetricsByRange"]["30d"], source_data, since=since_30)
    if since_month:
        _merge_source_into_time_metrics(snapshot["timeMetricsByRange"]["month"], source_data, since=since_month)
    if since_7:
        _merge_source_into_time_metrics(snapshot["timeMetricsByRange"]["7d"], source_data, since=since_7)

    by_month = {m["month"]: m for m in snapshot["monthly"]}
    for ym, add in monthly_add.items():
        if ym not in by_month:
            by_month[ym] = {
                "month": ym,
                "models": [],
                "input": 0,
                "output": 0,
                "cacheRead": 0,
                "cacheWrite": 0,
                "reasoning": 0,
                "messageCount": 0,
                "cost": 0.0,
            }
        target = by_month[ym]
        target["input"] += add["input"]
        target["output"] += add["output"]
        target["cacheRead"] += add["cacheRead"]
        target["cacheWrite"] += add["cacheWrite"]
        target["messageCount"] += add["messageCount"]
        target["cost"] += add["cost"]
        for mod in add["models"]:
            if mod not in target["models"]:
                target["models"].append(mod)
    snapshot["monthly"] = sorted(by_month.values(), key=lambda x: x["month"])


def finalize_snapshot_metrics(snapshot: dict[str, Any]) -> None:
    """
    1. Recompute 6-level heatmap intensity (L0..L6) uniformly across merged contributions.
    2. Compute accurate per-day clientActiveMs & meta.clientMsgPerSess for arbitrary custom date filters.
    """
    contributions = snapshot.get("contributions") or []
    nz = sorted(int(d.get("totals", {}).get("tokens", 0) or 0) for d in contributions if (d.get("totals", {}).get("tokens", 0) or 0) > 0)
    if nz:
        qs = [nz[min(len(nz) - 1, int(len(nz) * r))] for r in (0.16, 0.34, 0.52, 0.70, 0.87)]
    else:
        qs = [1, 2, 3, 4, 5]

    client_day_weights: dict[str, list[tuple[dict[str, Any], float]]] = defaultdict(list)
    client_msgs_tot: dict[str, int] = defaultdict(int)

    for day in contributions:
        tot = int(day.get("totals", {}).get("tokens", 0) or 0)
        if tot <= 0:
            day["intensity"] = 0
        elif tot <= qs[0]:
            day["intensity"] = 1
        elif tot <= qs[1]:
            day["intensity"] = 2
        elif tot <= qs[2]:
            day["intensity"] = 3
        elif tot <= qs[3]:
            day["intensity"] = 4
        elif tot <= qs[4]:
            day["intensity"] = 5
        else:
            day["intensity"] = 6

        by_c_tok: dict[str, int] = defaultdict(int)
        by_c_msg: dict[str, int] = defaultdict(int)
        for it in day.get("clients") or []:
            cid = it.get("client")
            if not cid:
                continue
            tk = it.get("tokens") or {}
            it_tok = int(tk.get("input", 0)) + int(tk.get("cacheWrite", 0)) + int(tk.get("output", 0)) + int(tk.get("cacheRead", 0))
            it_msg = int(it.get("messages", 0) or 0)
            by_c_tok[cid] += it_tok
            by_c_msg[cid] += it_msg
            client_msgs_tot[cid] += it_msg

        for cid in by_c_tok:
            w = by_c_msg[cid] * 1.0 + (by_c_tok[cid] / 1_000_000.0) * 0.5
            client_day_weights[cid].append((day, max(0.01, w)))

    tm_all = (snapshot.get("timeMetricsByRange") or {}).get("all") or {}
    client_msg_per_sess: dict[str, float] = {}
    for cid, pairs in client_day_weights.items():
        cm = tm_all.get(cid) or {}
        total_ms = int(cm.get("total_active_time_ms", 0) or 0)
        sess_cnt = int(cm.get("session_count", 0) or 0)
        if sess_cnt > 0 and client_msgs_tot[cid] > 0:
            client_msg_per_sess[cid] = round(max(1.0, client_msgs_tot[cid] / sess_cnt), 2)
        else:
            client_msg_per_sess[cid] = 10.0

        w_sum = sum(w for _, w in pairs)
        if total_ms > 0 and w_sum > 0:
            rem = total_ms
            for idx, (day, w) in enumerate(pairs):
                if "clientActiveMs" not in day:
                    day["clientActiveMs"] = {}
                if idx == len(pairs) - 1:
                    alloc = max(0, rem)
                else:
                    alloc = int(round(total_ms * (w / w_sum)))
                    rem -= alloc
                day["clientActiveMs"][cid] = alloc

    for day in contributions:
        cam = day.get("clientActiveMs")
        if cam:
            day["activeTimeMs"] = sum(cam.values())

    snapshot["meta"]["clientMsgPerSess"] = client_msg_per_sess
    all_dates = sorted(d["date"] for d in contributions if d.get("date"))
    if all_dates:
        snapshot["meta"]["dateRange"] = {"start": all_dates[0], "end": all_dates[-1]}


def refresh_html(open_browser: bool = False, quiet: bool = False) -> None:
    """Scan local AI logs + DoubaoWork traces, merge optional archives, and write HTML."""
    if not HTML_PATH.exists():
        raise FileNotFoundError(f"未找到看板文件：{HTML_PATH}")

    t_start = time.time()
    html_text = HTML_PATH.read_text(encoding="utf-8")
    trae_source = extract_optional_trae_archive(html_text)

    _log("正在检测本机 AI 工具与 tokscale 引擎...", quiet=quiet)
    doubao_source = collect_doubaowork_source()

    d_start_idx = html_text.find(DATA_START)
    if d_start_idx == -1:
        raise RuntimeError("看板 HTML 内缺少 initial-data 数据槽位")
    d0 = d_start_idx + len(DATA_START)
    d1 = html_text.find(SCRIPT_END, d0)
    if d1 == -1:
        raise RuntimeError("看板 HTML 内 initial-data 标签未正常闭合")

    cmd_base, uses_npx = find_tokscale_command()
    if uses_npx:
        _log("首次使用将通过 npx 拉取 tokscale（约需 15~45 秒）...", quiet=quiet)
    else:
        _log(f"使用本机 tokscale：{cmd_base[0]}", quiet=quiet)

    base_timeout = 120 if uses_npx else 60

    with ThreadPoolExecutor(max_workers=5) as pool:
        f_graph = pool.submit(run_tokscale_graph, cmd_base, base_timeout)
        f_models = pool.submit(run_tokscale_json, cmd_base, ["models", "--offline", "--no-spinner", "--json"], base_timeout)
        f_monthly = pool.submit(run_tokscale_json, cmd_base, ["monthly", "--offline", "--no-spinner", "--json"], base_timeout)
        f_ws = pool.submit(
            run_tokscale_json,
            cmd_base,
            ["models", "--offline", "--no-spinner", "--json", "--group-by", "workspace,model"],
            base_timeout,
        )

        graph_data = f_graph.result()
        models_data = f_models.result()
        monthly_data = f_monthly.result()
        ws_data = f_ws.result()

    clients = (graph_data.get("summary") or {}).get("clients", []) or []
    now_local = datetime.now(LOCAL_TZ).date()
    since_30 = (now_local - timedelta(days=29)).strftime("%Y-%m-%d")
    since_month = now_local.strftime("%Y-%m-01")
    since_7 = (now_local - timedelta(days=6)).strftime("%Y-%m-%d")

    _log(f"正在并发采集分软件活跃时长与 24h 节律（共 {len(clients)} 款）...", quiet=quiet)
    with ThreadPoolExecutor(max_workers=5) as pool:
        f_tm_all = pool.submit(fetch_time_metrics_map, cmd_base, clients, [])
        f_tm_30d = pool.submit(fetch_time_metrics_map, cmd_base, clients, ["--since", since_30])
        f_tm_month = pool.submit(fetch_time_metrics_map, cmd_base, clients, ["--since", since_month])
        f_tm_7d = pool.submit(fetch_time_metrics_map, cmd_base, clients, ["--since", since_7])
        f_hourly_per_c = pool.submit(fetch_per_client_hourly, cmd_base, clients)

        tm_all = f_tm_all.result()
        tm_30d = f_tm_30d.result()
        tm_month = f_tm_month.result()
        tm_7d = f_tm_7d.result()
        hourly_compact = f_hourly_per_c.result()

    if not hourly_compact and clients:
        raw_hourly = run_tokscale_json(cmd_base, ["hourly", "--offline", "--no-spinner", "--json"])
        hourly_compact = [
            {
                "h": e["hour"],
                "c": e.get("clients", []),
                "m": e.get("models", []),
                "i": e.get("input", 0),
                "o": e.get("output", 0),
                "cr": e.get("cacheRead", 0),
                "cw": e.get("cacheWrite", 0),
                "n": e.get("messageCount", 0),
                "cost": round(float(e.get("cost", 0.0)), 6),
            }
            for e in raw_hourly.get("entries", [])
        ]

    ws_entries = sorted(
        ws_data.get("entries", []),
        key=lambda x: (x.get("cost", 0.0), x.get("input", 0) + x.get("cacheRead", 0)),
        reverse=True,
    )[:150]

    summary_obj = graph_data.get("summary") or {}
    summary_obj.setdefault("clients", [])
    summary_obj.setdefault("models", [])
    summary_obj.setdefault("totalTokens", 0)
    summary_obj.setdefault("totalCost", 0.0)

    snapshot: dict[str, Any] = {
        "meta": {
            "generatedAt": datetime.now(LOCAL_TZ).isoformat(timespec="seconds"),
            "tokscaleVersion": (graph_data.get("meta") or {}).get("version", "unknown"),
            "dateRange": (graph_data.get("meta") or {}).get("dateRange", {}),
            "buildSeconds": round(time.time() - t_start, 2),
            "clientLabels": CLIENT_LABELS,
        },
        "summary": summary_obj,
        "contributions": graph_data.get("contributions", []),
        "models": models_data.get("entries", []),
        "monthly": monthly_data.get("entries", []),
        "hourly": sorted(hourly_compact, key=lambda x: x["h"]),
        "workspaces": ws_entries,
        "timeMetricsByRange": {
            "all": tm_all,
            "30d": tm_30d,
            "month": tm_month,
            "7d": tm_7d,
        },
    }

    merge_custom_client_into_snapshot(
        snapshot, trae_source, since_30=since_30, since_month=since_month, since_7=since_7
    )
    merge_custom_client_into_snapshot(
        snapshot, doubao_source, since_30=since_30, since_month=since_month, since_7=since_7
    )
    finalize_snapshot_metrics(snapshot)
    snapshot["meta"]["buildSeconds"] = round(time.time() - t_start, 2)

    safe_json = json.dumps(snapshot, ensure_ascii=False, separators=(",", ":")).replace("</script>", "<\\/script>")
    new_html = html_text[:d0] + safe_json + html_text[d1:]
    if "</html>" not in new_html:
        raise RuntimeError("生成的 HTML 校验未通过，已中止覆盖")

    tmp_html = BASE_DIR / ".tmp_token_dashboard.html"
    try:
        tmp_html.write_text(new_html, encoding="utf-8", newline="\n")
        os.replace(tmp_html, HTML_PATH)
    finally:
        if tmp_html.exists():
            tmp_html.unlink()

    _log(
        f"已刷新看板：{HTML_PATH.name} "
        f"({len(snapshot['contributions'])} 天, {len(snapshot['summary']['clients'])} 款软件, "
        f"{len(snapshot['models'])} 条模型记录, 耗时 {snapshot['meta']['buildSeconds']}s)",
        quiet=quiet,
    )

    if open_browser:
        webbrowser.open(HTML_PATH.as_uri())


def main() -> int:
    parser = argparse.ArgumentParser(description="扫描本地 AI 日志并生成单文件可视化 Token 看板")
    parser.add_argument("--no-open", action="store_true", help="刷新后不自动拉起系统浏览器")
    parser.add_argument("--quiet", action="store_true", help="减少控制台输出")
    args = parser.parse_args()
    try:
        refresh_html(open_browser=not args.no_open, quiet=args.quiet)
        return 0
    except KeyboardInterrupt:
        print("\n已取消扫描。", file=sys.stderr)
        return 130
    except Exception as exc:
        print(f"\n[错误] 刷新失败：{exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
