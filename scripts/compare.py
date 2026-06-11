#!/usr/bin/env python
"""STM32 固件回归检测与历史趋势追踪工具。

功能:
  1. 对比两次快照（基线 vs 当前）
  2. 保存历史快照（自动时间戳）
  3. 分析历史趋势（Flash/RAM/符号变化曲线）
  4. 列出所有历史快照

用法:
  python compare.py --save --history-dir history/ --elf-data check_elf.json --sim-data debug_sim.json --opt-data optimize.json
  python compare.py --baseline history/v1/ --current history/v2/ --report diff.md
  python compare.py --trend --history-dir history/ --report trend.md
  python compare.py --list --history-dir history/
"""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from datetime import datetime
from pathlib import Path


def load_json(path: Path) -> dict | None:
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None


def save_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")


def get_git_commit() -> str | None:
    try:
        proc = subprocess.run(["git", "rev-parse", "--short", "HEAD"], capture_output=True, text=True, timeout=5)
        if proc.returncode == 0:
            return proc.stdout.strip()
    except (FileNotFoundError, subprocess.TimeoutExpired):
        pass
    return None


# === 快照管理 ===

def save_snapshot(history_dir: Path, elf_data: dict | None = None, sim_data: dict | None = None,
                  opt_data: dict | None = None, metadata: dict | None = None) -> Path:
    """保存一个历史快照，返回快照目录路径。"""
    timestamp = datetime.now().strftime("%Y-%m-%d_%H%M%S")
    git_commit = get_git_commit() or "unknown"
    snapshot_name = f"{timestamp}_{git_commit}"
    snapshot_dir = history_dir / snapshot_name
    snapshot_dir.mkdir(parents=True, exist_ok=True)

    # 保存数据
    if elf_data:
        save_json(snapshot_dir / "check_elf.json", elf_data)
    if sim_data:
        save_json(snapshot_dir / "debug_sim.json", sim_data)
    if opt_data:
        save_json(snapshot_dir / "optimize.json", opt_data)

    # 保存元数据
    meta = {
        "timestamp": datetime.now().isoformat(),
        "git_commit": git_commit,
        "snapshot_name": snapshot_name,
    }
    if metadata:
        meta.update(metadata)
    save_json(snapshot_dir / "metadata.json", meta)

    # 更新 latest 符号链接（Windows 用文件代替）
    latest_file = history_dir / "latest.txt"
    latest_file.write_text(snapshot_name, encoding="utf-8")

    return snapshot_dir


def load_history(history_dir: Path) -> list[dict]:
    """加载所有历史快照，按时间排序。"""
    if not history_dir.exists():
        return []

    snapshots = []
    for d in sorted(history_dir.iterdir()):
        if d.is_dir() and (d / "metadata.json").exists():
            meta = load_json(d / "metadata.json")
            if meta:
                meta["path"] = str(d)
                meta["dir_name"] = d.name
                snapshots.append(meta)

    return snapshots


def get_latest_snapshot(history_dir: Path) -> Path | None:
    """获取最新的快照目录。"""
    latest_file = history_dir / "latest.txt"
    if latest_file.exists():
        name = latest_file.read_text(encoding="utf-8").strip()
        path = history_dir / name
        if path.exists():
            return path

    # 回退：找最新的目录
    snapshots = load_history(history_dir)
    if snapshots:
        return Path(snapshots[-1]["path"])

    return None


# === 对比功能 ===

def compare_symbols(baseline: dict, current: dict) -> dict:
    base_syms = {}
    for name, info in baseline.get("symbols", {}).items():
        if isinstance(info, dict) and "address" in info:
            addr = int(info["address"], 16) if isinstance(info["address"], str) else info["address"]
            base_syms[name] = {"address": addr, "size": info.get("size", 0)}

    curr_syms = {}
    for name, info in current.get("symbols", {}).items():
        if isinstance(info, dict) and "address" in info:
            addr = int(info["address"], 16) if isinstance(info["address"], str) else info["address"]
            curr_syms[name] = {"address": addr, "size": info.get("size", 0)}

    base_names = set(base_syms.keys())
    curr_names = set(curr_syms.keys())

    added = [{"name": n, "address": f"0x{curr_syms[n]['address']:08x}", "size": curr_syms[n]["size"]}
             for n in sorted(curr_names - base_names)]
    removed = [{"name": n, "address": f"0x{base_syms[n]['address']:08x}", "size": base_syms[n]["size"]}
               for n in sorted(base_names - curr_names)]

    moved, resized = [], []
    for n in sorted(base_names & curr_names):
        d = curr_syms[n]["address"] - base_syms[n]["address"]
        if d != 0:
            moved.append({"name": n, "from": f"0x{base_syms[n]['address']:08x}", "to": f"0x{curr_syms[n]['address']:08x}",
                          "delta": f"+0x{d:x}" if d > 0 else f"-0x{abs(d):x}",
                          "severity": "info" if abs(d) < 0x100 else "warning"})
        sd = curr_syms[n]["size"] - base_syms[n]["size"]
        if sd != 0:
            resized.append({"name": n, "from_bytes": base_syms[n]["size"], "to_bytes": curr_syms[n]["size"],
                            "delta_bytes": sd, "severity": "info" if abs(sd) < 256 else "warning"})

    return {"added": added, "removed": removed, "moved": moved, "resized": resized,
            "summary": {"total_baseline": len(base_names), "total_current": len(curr_names),
                        "added_count": len(added), "removed_count": len(removed),
                        "moved_count": len(moved), "resized_count": len(resized)}}


def compare_sections(baseline: dict, current: dict) -> dict:
    base_s, curr_s = baseline.get("size", {}), current.get("size", {})
    sections = {}
    for key in ["text", "data", "bss", "ro_data"]:
        bv, cv = base_s.get(key, 0), curr_s.get(key, 0)
        d = cv - bv
        pct = round(d / bv * 100, 1) if bv > 0 else 0
        sev = "error" if abs(pct) > 30 else ("warning" if abs(pct) > 10 else "info")
        sections[key] = {"baseline_bytes": bv, "current_bytes": cv, "delta_bytes": d, "delta_pct": pct, "severity": sev}

    return {"sections": sections,
            "flash": {"baseline_kb": baseline.get("flash_usage_kb", 0), "current_kb": current.get("flash_usage_kb", 0),
                      "delta_kb": round(current.get("flash_usage_kb", 0) - baseline.get("flash_usage_kb", 0), 1)},
            "ram": {"baseline_kb": baseline.get("ram_usage_kb", 0), "current_kb": current.get("ram_usage_kb", 0),
                    "delta_kb": round(current.get("ram_usage_kb", 0) - baseline.get("ram_usage_kb", 0), 1)}}


def compare_simulation(baseline: dict, current: dict) -> dict:
    base_boot, curr_boot = baseline.get("boot_test", "N/A"), current.get("boot_test", "N/A")
    base_ev = {e["event"] for e in baseline.get("events", [])}
    curr_ev = {e["event"] for e in current.get("events", [])}
    return {"boot_test": {"baseline": base_boot, "current": curr_boot,
                          "changed": base_boot != curr_boot, "regression": base_boot == "PASS" and curr_boot != "PASS"},
            "events": {"added": sorted(curr_ev - base_ev), "removed": sorted(base_ev - curr_ev)},
            "uart": {"baseline": baseline.get("uart_has_output", False), "current": current.get("uart_has_output", False)}}


def compare_optimization(baseline: dict, current: dict) -> dict:
    base_r = {r["message"] for r in baseline.get("recommendations", [])}
    curr_r = {r["message"] for r in current.get("recommendations", [])}
    return {"new_issues": sorted(curr_r - base_r), "fixed_issues": sorted(base_r - curr_r),
            "baseline_count": len(base_r), "current_count": len(curr_r)}


def run_comparison(baseline_dir: Path, current_dir: Path) -> dict:
    result = {"baseline_dir": str(baseline_dir), "current_dir": str(current_dir),
              "comparisons": {}, "issues": [], "summary": {"status": "PASS", "warnings": 0, "errors": 0}}

    base_meta = load_json(baseline_dir / "metadata.json")
    curr_meta = load_json(current_dir / "metadata.json")
    if base_meta: result["baseline_info"] = base_meta
    if curr_meta: result["current_info"] = curr_meta

    base_elf = load_json(baseline_dir / "check_elf.json")
    curr_elf = load_json(current_dir / "check_elf.json")
    if base_elf and curr_elf:
        sym = compare_symbols(base_elf, curr_elf)
        result["comparisons"]["symbol_diff"] = sym
        for m in sym.get("moved", []):
            if m["severity"] == "warning":
                result["issues"].append({"severity": "warning", "message": f"符号 {m['name']} 地址偏移 {m['delta']}"})
                result["summary"]["warnings"] += 1
        for r in sym.get("resized", []):
            if r["severity"] == "warning":
                result["issues"].append({"severity": "warning", "message": f"符号大小变化: {r['name']} {r['from_bytes']}->{r['to_bytes']} bytes"})
                result["summary"]["warnings"] += 1

        sec = compare_sections(base_elf, curr_elf)
        result["comparisons"]["section_diff"] = sec
        for key, s in sec.get("sections", {}).items():
            if s["severity"] == "error":
                result["issues"].append({"severity": "error", "message": f"段 {key} 大幅变化: {s['delta_pct']}%"})
                result["summary"]["errors"] += 1
            elif s["severity"] == "warning":
                result["issues"].append({"severity": "warning", "message": f"段 {key} 明显变化: {s['delta_pct']}%"})
                result["summary"]["warnings"] += 1

    base_sim = load_json(baseline_dir / "renode_sim.json")
    curr_sim = load_json(current_dir / "renode_sim.json")
    if base_sim and curr_sim:
        sim = compare_simulation(base_sim, curr_sim)
        result["comparisons"]["simulation_diff"] = sim
        if sim.get("boot_test", {}).get("regression"):
            result["issues"].append({"severity": "error", "message": "仿真启动测试回归: PASS -> FAIL"})
            result["summary"]["errors"] += 1

    base_opt = load_json(baseline_dir / "optimize.json")
    curr_opt = load_json(current_dir / "optimize.json")
    if base_opt and curr_opt:
        opt = compare_optimization(base_opt, curr_opt)
        result["comparisons"]["optimization_diff"] = opt
        for i in opt.get("new_issues", []):
            result["issues"].append({"severity": "info", "message": f"新优化建议: {i}"})
        for i in opt.get("fixed_issues", []):
            result["issues"].append({"severity": "info", "message": f"已修复: {i}"})

    if result["summary"]["errors"] > 0:
        result["summary"]["status"] = "FAIL"
    elif result["summary"]["warnings"] > 0:
        result["summary"]["status"] = "WARN"

    return result


# === 趋势分析 ===

def analyze_trend(history_dir: Path) -> dict:
    """分析历史趋势。"""
    snapshots = load_history(history_dir)
    if len(snapshots) < 2:
        return {"error": "至少需要 2 个快照才能分析趋势", "count": len(snapshots)}

    trend = {
        "snapshot_count": len(snapshots),
        "snapshots": [],
        "flash_trend": [],
        "ram_trend": [],
        "symbol_count_trend": [],
        "recommendation_trend": [],
        "issues": [],
    }

    prev_elf = None
    for meta in snapshots:
        snap_dir = Path(meta["path"])
        snap_info = {
            "name": meta.get("dir_name", ""),
            "timestamp": meta.get("timestamp", ""),
            "git_commit": meta.get("git_commit", ""),
        }

        # ELF 数据
        elf_data = load_json(snap_dir / "check_elf.json")
        if elf_data:
            flash_kb = elf_data.get("flash_usage_kb", 0)
            ram_kb = elf_data.get("ram_usage_kb", 0)
            snap_info["flash_kb"] = flash_kb
            snap_info["ram_kb"] = ram_kb
            trend["flash_trend"].append({"timestamp": meta.get("timestamp", ""), "value": flash_kb})
            trend["ram_trend"].append({"timestamp": meta.get("timestamp", ""), "value": ram_kb})

            # 符号数量
            sym_count = len(elf_data.get("symbols", {}))
            snap_info["symbol_count"] = sym_count
            trend["symbol_count_trend"].append({"timestamp": meta.get("timestamp", ""), "value": sym_count})

            # 与前一个快照对比
            if prev_elf:
                sec_diff = compare_sections(prev_elf, elf_data)
                for key, s in sec_diff.get("sections", {}).items():
                    if s["severity"] in ["warning", "error"]:
                        trend["issues"].append({
                            "snapshot": meta.get("dir_name", ""),
                            "severity": s["severity"],
                            "message": f"段 {key} 变化 {s['delta_pct']}%",
                        })

            prev_elf = elf_data

        # 优化数据
        opt_data = load_json(snap_dir / "optimize.json")
        if opt_data:
            rec_count = len(opt_data.get("recommendations", []))
            snap_info["recommendation_count"] = rec_count
            trend["recommendation_trend"].append({"timestamp": meta.get("timestamp", ""), "value": rec_count})

        trend["snapshots"].append(snap_info)

    # 汇总
    if trend["flash_trend"]:
        flash_values = [t["value"] for t in trend["flash_trend"]]
        trend["flash_summary"] = {
            "min": min(flash_values),
            "max": max(flash_values),
            "latest": flash_values[-1],
            "delta": round(flash_values[-1] - flash_values[0], 1),
        }

    if trend["ram_trend"]:
        ram_values = [t["value"] for t in trend["ram_trend"]]
        trend["ram_summary"] = {
            "min": min(ram_values),
            "max": max(ram_values),
            "latest": ram_values[-1],
            "delta": round(ram_values[-1] - ram_values[0], 1),
        }

    return trend


def generate_trend_report(trend: dict) -> str:
    """生成趋势报告 Markdown。"""
    lines = ["# 固件历史趋势报告", ""]
    lines.append(f"> 快照数量: {trend.get('snapshot_count', 0)}")
    lines.append("")

    # Flash 趋势
    flash_summary = trend.get("flash_summary", {})
    if flash_summary:
        lines.append("## Flash 使用趋势")
        lines.append(f"- 最小: {flash_summary['min']} KB")
        lines.append(f"- 最大: {flash_summary['max']} KB")
        lines.append(f"- 最新: {flash_summary['latest']} KB")
        delta = flash_summary['delta']
        emoji = "📈" if delta > 0 else ("📉" if delta < 0 else "➡️")
        lines.append(f"- 变化: {emoji} {delta:+.1f} KB")
        lines.append("")
        lines.append("| 时间 | Flash (KB) |")
        lines.append("|------|-----------|")
        for t in trend.get("flash_trend", []):
            lines.append(f"| {t['timestamp'][:19]} | {t['value']} |")
        lines.append("")

    # RAM 趋势
    ram_summary = trend.get("ram_summary", {})
    if ram_summary:
        lines.append("## RAM 使用趋势")
        lines.append(f"- 最小: {ram_summary['min']} KB")
        lines.append(f"- 最大: {ram_summary['max']} KB")
        lines.append(f"- 最新: {ram_summary['latest']} KB")
        delta = ram_summary['delta']
        emoji = "📈" if delta > 0 else ("📉" if delta < 0 else "➡️")
        lines.append(f"- 变化: {emoji} {delta:+.1f} KB")
        lines.append("")

    # 符号数量趋势
    sym_trend = trend.get("symbol_count_trend", [])
    if sym_trend:
        lines.append("## 符号数量趋势")
        lines.append("| 时间 | 符号数 |")
        lines.append("|------|--------|")
        for t in sym_trend:
            lines.append(f"| {t['timestamp'][:19]} | {t['value']} |")
        lines.append("")

    # 优化建议趋势
    rec_trend = trend.get("recommendation_trend", [])
    if rec_trend:
        lines.append("## 优化建议趋势")
        lines.append("| 时间 | 建议数 |")
        lines.append("|------|--------|")
        for t in rec_trend:
            lines.append(f"| {t['timestamp'][:19]} | {t['value']} |")
        lines.append("")

    # 问题列表
    issues = trend.get("issues", [])
    if issues:
        lines.append("## 趋势中的问题")
        for i in issues:
            e = "❌" if i["severity"] == "error" else "⚠️"
            lines.append(f"- {e} [{i['snapshot']}] {i['message']}")

    return "\n".join(lines)


def generate_markdown_report(result: dict) -> str:
    lines = ["# 固件回归检测报告", ""]
    base_info = result.get("baseline_info", {})
    curr_info = result.get("current_info", {})
    lines.append(f"> **基线:** {base_info.get('timestamp', 'N/A')} (commit: {base_info.get('git_commit', 'N/A')})")
    lines.append(f"> **当前:** {curr_info.get('timestamp', 'N/A')} (commit: {curr_info.get('git_commit', 'N/A')})")
    lines.append("")

    summary = result.get("summary", {})
    emoji = {"PASS": "✅", "WARN": "⚠️", "FAIL": "❌"}.get(summary.get("status"), "❓")
    lines.append(f"## 总体状态: {emoji} {summary.get('status', 'N/A')}")
    lines.append(f"- 错误: {summary.get('errors', 0)}")
    lines.append(f"- 警告: {summary.get('warnings', 0)}")
    lines.append("")

    sec_diff = result.get("comparisons", {}).get("section_diff", {})
    if sec_diff:
        lines.append("## 段大小对比")
        lines.append("| 段 | 基线 | 当前 | 变化 | 状态 |")
        lines.append("|------|------|------|------|------|")
        for key, s in sec_diff.get("sections", {}).items():
            e = {"info": "✅", "warning": "⚠️", "error": "❌"}.get(s["severity"], "❓")
            lines.append(f"| {key} | {s['baseline_bytes']} | {s['current_bytes']} | {s['delta_bytes']:+d} ({s['delta_pct']:+.1f}%) | {e} |")
        lines.append("")

    sym_diff = result.get("comparisons", {}).get("symbol_diff", {})
    if sym_diff:
        has_changes = any(sym_diff.get(k) for k in ["added", "removed", "moved", "resized"])
        if has_changes:
            lines.append("## 符号变化")
            for label, key, emoji in [("新增", "added", "🆕"), ("消失", "removed", "🗑️"), ("地址偏移", "moved", "📍"), ("大小变化", "resized", "📏")]:
                items = sym_diff.get(key, [])
                if items:
                    lines.append(f"### {label} ({len(items)})")
                    for s in items[:10]:
                        if key == "added":
                            lines.append(f"- {emoji} `{s['name']}` @ {s['address']} ({s['size']} bytes)")
                        elif key == "removed":
                            lines.append(f"- {emoji} `{s['name']}` @ {s['address']} ({s['size']} bytes)")
                        elif key == "moved":
                            e = "⚠️" if s["severity"] == "warning" else "ℹ️"
                            lines.append(f"- {e} `{s['name']}`: {s['from']} -> {s['to']} ({s['delta']})")
                        elif key == "resized":
                            e = "⚠️" if s["severity"] == "warning" else "ℹ️"
                            lines.append(f"- {e} `{s['name']}`: {s['from_bytes']} -> {s['to_bytes']} bytes ({s['delta_bytes']:+d})")
                    lines.append("")

    sim_diff = result.get("comparisons", {}).get("simulation_diff", {})
    if sim_diff:
        lines.append("## 仿真行为对比")
        boot = sim_diff.get("boot_test", {})
        if boot:
            e = "❌" if boot.get("regression") else "✅"
            lines.append(f"- 启动测试: {boot.get('baseline', 'N/A')} -> {boot.get('current', 'N/A')} {e}")
        lines.append("")

    opt_diff = result.get("comparisons", {}).get("optimization_diff", {})
    if opt_diff:
        lines.append("## 优化建议对比")
        lines.append(f"- 基线: {opt_diff.get('baseline_count', 0)} 条 | 当前: {opt_diff.get('current_count', 0)} 条")
        for i in opt_diff.get("new_issues", []): lines.append(f"- 🆕 {i}")
        for i in opt_diff.get("fixed_issues", []): lines.append(f"- ✅ 已修复: {i}")
        lines.append("")

    issues = result.get("issues", [])
    if issues:
        lines.append("## 问题列表")
        for i in issues:
            e = {"error": "❌", "warning": "⚠️", "info": "ℹ️"}.get(i["severity"], "❓")
            lines.append(f"- {e} [{i['severity'].upper()}] {i['message']}")

    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="STM32 固件回归检测与历史趋势追踪工具",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""示例:
  %(prog)s --save --history-dir history/ --elf-data check_elf.json
  %(prog)s --baseline history/v1/ --current history/v2/ --report diff.md
  %(prog)s --trend --history-dir history/ --report trend.md
  %(prog)s --list --history-dir history/
""",
    )

    # 模式选择
    parser.add_argument("--save", action="store_true", help="保存快照到历史目录")
    parser.add_argument("--trend", action="store_true", help="分析历史趋势")
    parser.add_argument("--list", action="store_true", help="列出所有历史快照")

    # 对比模式参数
    parser.add_argument("--baseline", help="基线快照目录")
    parser.add_argument("--current", help="当前快照目录")

    # 保存模式参数
    parser.add_argument("--history-dir", default="history", help="历史快照目录 (默认: history)")
    parser.add_argument("--elf-data", help="check_elf.py 输出 JSON 文件")
    parser.add_argument("--sim-data", help="debug_sim.py 输出 JSON 文件")
    parser.add_argument("--opt-data", help="optimize.py 输出 JSON 文件")

    # 输出
    parser.add_argument("--report", help="输出 Markdown 报告路径")

    args = parser.parse_args()

    # 列出快照
    if args.list:
        history_dir = Path(args.history_dir)
        snapshots = load_history(history_dir)
        if not snapshots:
            print("没有历史快照", file=sys.stderr)
            return 0
        print(f"历史快照 ({len(snapshots)} 个):")
        for s in snapshots:
            print(f"  {s.get('dir_name', '')} | {s.get('timestamp', '')[:19]} | commit: {s.get('git_commit', '')}")
        return 0

    # 保存快照
    if args.save:
        history_dir = Path(args.history_dir)
        elf_data = load_json(Path(args.elf_data)) if args.elf_data else None
        sim_data = load_json(Path(args.sim_data)) if args.sim_data else None
        opt_data = load_json(Path(args.opt_data)) if args.opt_data else None

        snapshot_dir = save_snapshot(history_dir, elf_data, sim_data, opt_data)
        print(f"快照已保存: {snapshot_dir}", file=sys.stderr)
        return 0

    # 趋势分析
    if args.trend:
        history_dir = Path(args.history_dir)
        trend = analyze_trend(history_dir)
        if "error" in trend:
            print(f"错误: {trend['error']}", file=sys.stderr)
            return 1

        json.dump(trend, sys.stdout, indent=2, ensure_ascii=False)
        print()

        if args.report:
            Path(args.report).write_text(generate_trend_report(trend), encoding="utf-8")
            print(f"趋势报告已保存: {args.report}", file=sys.stderr)
        return 0

    # 对比模式
    if args.baseline and args.current:
        baseline_dir, current_dir = Path(args.baseline), Path(args.current)
        if not baseline_dir.exists():
            print(f"错误: 基线目录不存在: {args.baseline}", file=sys.stderr)
            return 1
        if not current_dir.exists():
            print(f"错误: 当前目录不存在: {args.current}", file=sys.stderr)
            return 1

        result = run_comparison(baseline_dir, current_dir)
        json.dump(result, sys.stdout, indent=2, ensure_ascii=False)
        print()

        if args.report:
            Path(args.report).write_text(generate_markdown_report(result), encoding="utf-8")
            print(f"报告已保存: {args.report}", file=sys.stderr)
        return 0 if result["summary"]["status"] != "FAIL" else 1

    # 默认：显示帮助
    parser.print_help()
    return 1


if __name__ == "__main__":
    sys.exit(main())
