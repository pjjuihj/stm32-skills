#!/usr/bin/env python
"""STM32 开发日志工具。

自动记录开发过程：git 提交、错误修复、功能完成。

用法:
  python dev_log.py --auto . --add "ADC DMA 循环采集正常工作"        # 添加日志条目
  python dev_log.py --auto . --from-git                              # 从 git log 生成
  python dev_log.py --auto . --from-errors                          # 从 error_tracker 生成
  python dev_log.py --auto . --today                                 # 今日摘要
  python dev_log.py --auto . --list                                  # 列出所有日志
  python dev_log.py --auto . --export solutions-log.md               # 导出为 Markdown

功能:
  - 手动添加开发日志条目
  - 从 git log 自动生成日志
  - 从 error_tracker 自动生成问题解决记录
  - 按日期汇总
  - 导出为 Markdown 格式（兼容 solutions-log.md）
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from datetime import datetime, timedelta
from pathlib import Path

# 脚本目录
SCRIPT_DIR = Path(__file__).parent

from shared import setup_encoding, read_json_file, write_json_file

setup_encoding()

# 日志文件路径
DEFAULT_LOG_FILE = os.path.join(SCRIPT_DIR, "data", "dev_log.json")


def load_log(log_file: str = None) -> dict:
    """加载日志数据库。"""
    log_file = log_file or DEFAULT_LOG_FILE
    db = read_json_file(log_file)
    if not db:
        db = {"entries": [], "created": datetime.now().isoformat()}
    return db


def save_log(db: dict, log_file: str = None) -> bool:
    """保存日志数据库。"""
    log_file = log_file or DEFAULT_LOG_FILE
    os.makedirs(os.path.dirname(log_file), exist_ok=True)
    return write_json_file(log_file, db)


def add_entry(message: str, category: str = "note", project_dir: str = None,
              log_file: str = None) -> dict:
    """添加日志条目。"""
    db = load_log(log_file)

    entry = {
        "id": len(db["entries"]) + 1,
        "timestamp": datetime.now().isoformat(),
        "date": datetime.now().strftime("%Y-%m-%d"),
        "message": message,
        "category": category,  # note, fix, feature, debug, config
        "project_dir": project_dir,
    }

    db["entries"].append(entry)
    save_log(db, log_file)
    return entry


def get_git_log(project_dir: str, since: str = None, limit: int = 50) -> list[dict]:
    """获取 git 提交历史。"""
    if not os.path.isdir(os.path.join(project_dir, ".git")):
        return []

    cmd = ["git", "log", "--oneline", "--no-merges", f"-{limit}",
           "--format=%H|%s|%ai|%an"]

    if since:
        cmd.extend(["--since", since])

    try:
        proc = subprocess.run(cmd, capture_output=True, text=True,
                              cwd=project_dir, timeout=10)
        if proc.returncode != 0:
            return []

        entries = []
        for line in proc.stdout.strip().split("\n"):
            if not line:
                continue
            parts = line.split("|", 3)
            if len(parts) >= 3:
                entries.append({
                    "hash": parts[0][:8],
                    "message": parts[1],
                    "date": parts[2][:10],
                    "author": parts[3] if len(parts) > 3 else "",
                })
        return entries
    except Exception:
        return []


def get_error_tracker_entries(since: str = None) -> list[dict]:
    """从 error_tracker 获取错误修复记录。"""
    db_file = os.path.join(SCRIPT_DIR, "data", "error_tracker.json")
    db = read_json_file(db_file)
    if not db:
        return []

    entries = []
    for record in db.get("records", []):
        if not record.get("fixed"):
            continue
        ts = record.get("timestamp", "")
        if since and ts < since:
            continue
        entries.append({
            "error": record.get("error", ""),
            "fix": record.get("fix", ""),
            "category": record.get("category", ""),
            "date": ts[:10],
        })
    return entries


def generate_from_git(project_dir: str, since: str = None, log_file: str = None) -> list[dict]:
    """从 git log 生成开发日志。"""
    git_entries = get_git_log(project_dir, since)
    entries = []

    for ge in git_entries:
        msg = ge["message"]

        # 自动分类
        category = "note"
        if msg.startswith("fix"):
            category = "fix"
        elif msg.startswith("feat"):
            category = "feature"
        elif msg.startswith("refactor"):
            category = "refactor"
        elif msg.startswith("doc"):
            category = "doc"

        entry = add_entry(
            message=f"[git:{ge['hash']}] {msg}",
            category=category,
            project_dir=project_dir,
            log_file=log_file,
        )
        entries.append(entry)

    return entries


def generate_from_errors(project_dir: str = None, since: str = None,
                         log_file: str = None) -> list[dict]:
    """从 error_tracker 生成问题解决日志。"""
    error_entries = get_error_tracker_entries(since)
    entries = []

    for ee in error_entries:
        entry = add_entry(
            message=f"[解决] {ee['error']} → {ee['fix']}",
            category="fix",
            project_dir=project_dir,
            log_file=log_file,
        )
        entries.append(entry)

    return entries


def get_today_summary(log_file: str = None) -> list[dict]:
    """获取今日日志。"""
    db = load_log(log_file)
    today = datetime.now().strftime("%Y-%m-%d")
    return [e for e in db["entries"] if e.get("date") == today]


def list_entries(log_file: str = None, limit: int = 20) -> list[dict]:
    """列出最近的日志条目。"""
    db = load_log(log_file)
    return db["entries"][-limit:]


def export_markdown(output_file: str, log_file: str = None,
                    since: str = None) -> str:
    """导出为 Markdown 格式。"""
    db = load_log(log_file)
    entries = db["entries"]

    if since:
        entries = [e for e in entries if e.get("date", "") >= since]

    # 按日期分组
    by_date = {}
    for e in entries:
        date = e.get("date", "unknown")
        if date not in by_date:
            by_date[date] = []
        by_date[date].append(e)

    # 生成 Markdown
    lines = [
        "# 开发日志",
        "",
        f"生成时间: {datetime.now().strftime('%Y-%m-%d %H:%M')}",
        f"总条目: {len(entries)}",
        "",
        "---",
        "",
    ]

    category_icons = {
        "note": "📝",
        "fix": "🔧",
        "feature": "✨",
        "debug": "🔍",
        "config": "⚙️",
        "refactor": "♻️",
        "doc": "📄",
    }

    for date in sorted(by_date.keys(), reverse=True):
        lines.append(f"## {date}")
        lines.append("")
        for e in by_date[date]:
            icon = category_icons.get(e.get("category", ""), "•")
            lines.append(f"- {icon} {e['message']}")
        lines.append("")

    markdown = "\n".join(lines)

    if output_file:
        os.makedirs(os.path.dirname(output_file) if os.path.dirname(output_file) else ".", exist_ok=True)
        with open(output_file, "w", encoding="utf-8") as f:
            f.write(markdown)

    return markdown


def main():
    parser = argparse.ArgumentParser(description="STM32 开发日志工具")
    parser.add_argument("--auto", metavar="DIR", default=".", help="项目目录")
    parser.add_argument("--add", help="添加日志条目")
    parser.add_argument("--category", default="note",
                        choices=["note", "fix", "feature", "debug", "config"],
                        help="条目分类")
    parser.add_argument("--from-git", action="store_true", help="从 git log 生成")
    parser.add_argument("--from-errors", action="store_true", help="从 error_tracker 生成")
    parser.add_argument("--today", action="store_true", help="今日摘要")
    parser.add_argument("--list", action="store_true", help="列出最近日志")
    parser.add_argument("--export", metavar="FILE", help="导出为 Markdown 文件")
    parser.add_argument("--since", help="起始日期（YYYY-MM-DD）")
    parser.add_argument("--limit", type=int, default=20, help="列出条目数")
    parser.add_argument("--log-file", help="日志文件路径")
    parser.add_argument("--json", action="store_true", help="JSON 格式输出")
    args = parser.parse_args()

    project_dir = str(Path(args.auto).resolve())
    log_file = args.log_file

    if args.add:
        entry = add_entry(args.add, args.category, project_dir, log_file)
        if args.json:
            print(json.dumps(entry, indent=2, ensure_ascii=False))
        else:
            print(f"✅ 日志已记录 (ID: {entry['id']})")
            print(f"  {entry['message']}")

    elif args.from_git:
        entries = generate_from_git(project_dir, args.since, log_file)
        if args.json:
            print(json.dumps(entries, indent=2, ensure_ascii=False))
        else:
            print(f"✅ 从 git log 生成 {len(entries)} 条日志")

    elif args.from_errors:
        entries = generate_from_errors(project_dir, args.since, log_file)
        if args.json:
            print(json.dumps(entries, indent=2, ensure_ascii=False))
        else:
            print(f"✅ 从 error_tracker 生成 {len(entries)} 条日志")

    elif args.today:
        entries = get_today_summary(log_file)
        if args.json:
            print(json.dumps(entries, indent=2, ensure_ascii=False))
        else:
            print(f"📋 今日日志 ({len(entries)} 条):")
            for e in entries:
                category_icons = {"note": "📝", "fix": "🔧", "feature": "✨",
                                  "debug": "🔍", "config": "⚙️"}
                icon = category_icons.get(e.get("category", ""), "•")
                print(f"  {icon} {e['message']}")

    elif args.list:
        entries = list_entries(log_file, args.limit)
        if args.json:
            print(json.dumps(entries, indent=2, ensure_ascii=False))
        else:
            print(f"📋 最近日志 ({len(entries)} 条):")
            for e in entries:
                category_icons = {"note": "📝", "fix": "🔧", "feature": "✨",
                                  "debug": "🔍", "config": "⚙️"}
                icon = category_icons.get(e.get("category", ""), "•")
                print(f"  [{e.get('date', '')}] {icon} {e['message']}")

    elif args.export:
        markdown = export_markdown(args.export, log_file, args.since)
        if not args.json:
            print(f"✅ 已导出到: {args.export}")
            print(f"  条目数: {markdown.count(chr(10)) - 10}")

    else:
        parser.print_help()


if __name__ == "__main__":
    main()
