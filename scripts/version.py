#!/usr/bin/env python
"""STM32 项目版本管理工具。

版本对比、回退、快照、自动标签。

用法:
  python version.py --auto . --list                              # 列出所有版本
  python version.py --auto . --diff                              # 对比当前和上一个稳定版本
  python version.py --auto . --diff stable/v1 stable/v2          # 对比两个版本
  python version.py --auto . --rollback                          # 回退到上一个稳定版本
  python version.py --auto . --rollback stable/v1                # 回退到指定版本
  python version.py --auto . --snapshot                          # 保存当前编译产物快照
  python version.py --auto . --tag                               # 自动打版本标签
  python version.py --auto . --tag -m "ADC DMA 正常工作"          # 带消息打标签
  python version.py --auto . --status                            # 版本状态概览

功能:
  - 列出所有版本标签（stable/backup/milestone）
  - 对比两个版本的文件差异
  - 一键回退到上一个稳定版本
  - 保存编译产物快照（.hex/.axf/.map）
  - 自动从 git log 生成版本标签
  - 版本状态概览
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
from datetime import datetime
from pathlib import Path

# 脚本目录
SCRIPT_DIR = Path(__file__).parent

from shared import setup_encoding

setup_encoding()


def run_git(args: list[str], cwd: str = None) -> tuple[int, str]:
    """执行 git 命令。"""
    cmd = ["git"] + args
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True,
                              cwd=cwd, timeout=30)
        return proc.returncode, proc.stdout.strip()
    except Exception as e:
        return -1, str(e)


def get_project_dir(auto_dir: str) -> str:
    """获取项目目录。"""
    return str(Path(auto_dir).resolve())


def list_versions(project_dir: str) -> list[dict]:
    """列出所有版本标签。"""
    code, output = run_git(["tag", "-l"], cwd=project_dir)
    if code != 0:
        return []

    versions = []
    for tag in output.split("\n"):
        if not tag.strip():
            continue

        # 获取标签信息
        code2, msg = run_git(["tag", "-l", "--format=%(contents)", tag], cwd=project_dir)
        code3, date = run_git(["log", "-1", "--format=%ai", tag], cwd=project_dir)
        code4, hash_val = run_git(["rev-parse", "--short", tag], cwd=project_dir)

        # 分类
        category = "other"
        if tag.startswith("stable/"):
            category = "stable"
        elif tag.startswith("backup/"):
            category = "backup"
        elif tag.startswith("milestone/"):
            category = "milestone"
        elif tag.startswith("exp/"):
            category = "experiment"

        versions.append({
            "tag": tag,
            "category": category,
            "message": msg[:100] if msg else "",
            "date": date[:10] if date else "",
            "hash": hash_val if hash_val else "",
        })

    return versions


def diff_versions(project_dir: str, tag1: str = None, tag2: str = None) -> dict:
    """对比两个版本的差异。"""
    # 默认对比当前和上一个稳定版本
    if not tag1:
        code, tags = run_git(["tag", "-l", "stable/*", "--sort=-version:refname"], cwd=project_dir)
        if code == 0 and tags:
            tag1 = tags.split("\n")[0]
        else:
            return {"error": "没有找到稳定版本标签"}

    if not tag2:
        tag2 = "HEAD"

    # 获取差异文件列表
    code, output = run_git(["diff", "--stat", tag1, tag2], cwd=project_dir)
    if code != 0:
        return {"error": f"对比失败: {output}"}

    # 获取详细差异
    code2, detail = run_git(["diff", "--name-status", tag1, tag2], cwd=project_dir)

    files = []
    if code2 == 0 and detail:
        for line in detail.split("\n"):
            if not line.strip():
                continue
            parts = line.split("\t", 1)
            if len(parts) >= 2:
                status = parts[0]
                filepath = parts[1]
                status_map = {"M": "修改", "A": "新增", "D": "删除", "R": "重命名"}
                files.append({
                    "status": status_map.get(status[0], status),
                    "file": filepath,
                })

    # 获取提交历史
    code3, commits = run_git(["log", "--oneline", f"{tag1}..{tag2}"], cwd=project_dir)
    commit_list = []
    if code3 == 0 and commits:
        for line in commits.split("\n"):
            if line.strip():
                commit_list.append(line.strip())

    return {
        "tag1": tag1,
        "tag2": tag2,
        "files": files,
        "file_count": len(files),
        "commits": commit_list,
        "commit_count": len(commit_list),
        "stat": output,
    }


def rollback_version(project_dir: str, tag: str = None, force: bool = False) -> dict:
    """回退到指定版本。"""
    if not tag:
        # 找上一个稳定版本
        code, tags = run_git(["tag", "-l", "stable/*", "--sort=-version:refname"], cwd=project_dir)
        if code == 0 and tags:
            tag = tags.split("\n")[0]
        else:
            return {"error": "没有找到稳定版本标签"}

    # 检查标签是否存在
    code, check = run_git(["rev-parse", tag], cwd=project_dir)
    if code != 0:
        return {"error": f"标签不存在: {tag}"}

    # 检查是否有未提交的更改
    code, status = run_git(["status", "--porcelain"], cwd=project_dir)
    if code == 0 and status and not force:
        return {
            "error": "有未提交的更改，使用 --force 强制回退",
            "changes": status[:500]
        }

    # 先备份当前状态
    backup_tag = f"backup/before-rollback-{datetime.now().strftime('%Y%m%d-%H%M%S')}"
    run_git(["tag", backup_tag], cwd=project_dir)

    # 回退
    code, output = run_git(["reset", "--hard", tag], cwd=project_dir)
    if code != 0:
        return {"error": f"回退失败: {output}"}

    return {
        "success": True,
        "rolled_back_to": tag,
        "backup_tag": backup_tag,
        "message": f"已回退到 {tag}，当前状态已备份到 {backup_tag}"
    }


def save_snapshot(project_dir: str, snapshot_dir: str = None) -> dict:
    """保存当前编译产物快照。"""
    if not snapshot_dir:
        snapshot_dir = os.path.join(project_dir, "snapshots")

    # 查找编译产物
    artifacts = {}
    for ext in [".hex", ".axf", ".map", ".bin"]:
        for root, _, files in os.walk(project_dir):
            for f in files:
                if f.endswith(ext) and "build" not in root.lower():
                    filepath = os.path.join(root, f)
                    # 取最新的
                    if ext not in artifacts or os.path.getmtime(filepath) > os.path.getmtime(artifacts[ext]):
                        artifacts[ext] = filepath

    if not artifacts:
        return {"error": "未找到编译产物（.hex/.axf/.map/.bin）"}

    # 创建快照目录
    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    snap_path = os.path.join(snapshot_dir, timestamp)
    os.makedirs(snap_path, exist_ok=True)

    # 复制文件
    copied = []
    for ext, src in artifacts.items():
        dst = os.path.join(snap_path, os.path.basename(src))
        shutil.copy2(src, dst)
        copied.append(os.path.basename(src))

    # 保存版本信息
    code, git_hash = run_git(["rev-parse", "--short", "HEAD"], cwd=project_dir)
    code2, git_msg = run_git(["log", "-1", "--format=%s"], cwd=project_dir)

    info = {
        "timestamp": timestamp,
        "git_hash": git_hash if code == 0 else "",
        "git_message": git_msg if code2 == 0 else "",
        "files": copied,
    }

    with open(os.path.join(snap_path, "snapshot.json"), "w", encoding="utf-8") as f:
        json.dump(info, f, indent=2, ensure_ascii=False)

    return {
        "success": True,
        "path": snap_path,
        "files": copied,
        "git_hash": git_hash if code == 0 else "",
    }


def auto_tag(project_dir: str, message: str = None) -> dict:
    """自动从 git log 生成版本标签。"""
    # 获取上一个 stable 标签
    code, tags = run_git(["tag", "-l", "stable/*", "--sort=-version:refname"], cwd=project_dir)

    # 生成版本号
    if code == 0 and tags:
        last_tag = tags.split("\n")[0]
        # 提取版本号 v1, v2, ...
        match = re.search(r'v(\d+)$', last_tag)
        if match:
            ver_num = int(match.group(1)) + 1
        else:
            ver_num = 1
    else:
        ver_num = 1

    # 从最近提交生成描述
    code, last_commit = run_git(["log", "-1", "--format=%s"], cwd=project_dir)
    if not message:
        message = last_commit if code == 0 else f"version {ver_num}"

    # 清理消息用于标签名
    tag_name = f"stable/v{ver_num}"

    # 创建标签
    if message:
        code, output = run_git(["tag", "-a", tag_name, "-m", message], cwd=project_dir)
    else:
        code, output = run_git(["tag", tag_name], cwd=project_dir)

    if code != 0:
        return {"error": f"创建标签失败: {output}"}

    return {
        "success": True,
        "tag": tag_name,
        "message": message,
        "command": f"git push origin {tag_name}",
    }


def get_status(project_dir: str) -> dict:
    """获取版本状态概览。"""
    # 当前分支
    code, branch = run_git(["branch", "--show-current"], cwd=project_dir)

    # 最新提交
    code2, last_commit = run_git(["log", "-1", "--oneline"], cwd=project_dir)

    # 最新稳定版本
    code3, stable_tags = run_git(["tag", "-l", "stable/*", "--sort=-version:refname"], cwd=project_dir)
    latest_stable = stable_tags.split("\n")[0] if code3 == 0 and stable_tags else "无"

    # 未提交更改
    code4, status = run_git(["status", "--porcelain"], cwd=project_dir)
    changed_files = len(status.split("\n")) if code4 == 0 and status else 0

    # 标签统计
    code5, all_tags = run_git(["tag", "-l"], cwd=project_dir)
    tag_count = len(all_tags.split("\n")) if code5 == 0 and all_tags else 0

    # 快照列表
    snapshot_dir = os.path.join(project_dir, "snapshots")
    snapshots = []
    if os.path.isdir(snapshot_dir):
        snapshots = sorted(os.listdir(snapshot_dir), reverse=True)[:5]

    return {
        "branch": branch if code == 0 else "unknown",
        "last_commit": last_commit if code2 == 0 else "",
        "latest_stable": latest_stable,
        "changed_files": changed_files,
        "tag_count": tag_count,
        "recent_snapshots": snapshots,
    }


def main():
    parser = argparse.ArgumentParser(description="STM32 项目版本管理工具")
    parser.add_argument("--auto", metavar="DIR", default=".", help="项目目录")
    parser.add_argument("--list", action="store_true", help="列出所有版本")
    parser.add_argument("--diff", nargs="*", help="对比版本（默认对比当前和最新 stable）")
    parser.add_argument("--rollback", nargs="?", const="auto", help="回退版本")
    parser.add_argument("--force", action="store_true", help="强制回退（丢弃未提交更改）")
    parser.add_argument("--snapshot", action="store_true", help="保存编译产物快照")
    parser.add_argument("--tag", action="store_true", help="自动打版本标签")
    parser.add_argument("--message", "-m", help="标签消息")
    parser.add_argument("--status", action="store_true", help="版本状态概览")
    parser.add_argument("--json", action="store_true", help="JSON 格式输出")
    args = parser.parse_args()

    project_dir = get_project_dir(args.auto)

    if args.list:
        versions = list_versions(project_dir)
        if args.json:
            print(json.dumps(versions, indent=2, ensure_ascii=False))
        else:
            print(f"📋 版本列表 ({len(versions)} 个):")
            for v in versions:
                icons = {"stable": "✅", "backup": "💾", "milestone": "🏁",
                         "experiment": "🧪", "other": "•"}
                icon = icons.get(v["category"], "•")
                print(f"  {icon} {v['tag']}  {v['date']}  {v['hash']}  {v['message'][:40]}")

    elif args.diff is not None:
        tag1 = args.diff[0] if len(args.diff) > 0 else None
        tag2 = args.diff[1] if len(args.diff) > 1 else None
        result = diff_versions(project_dir, tag1, tag2)

        if args.json:
            print(json.dumps(result, indent=2, ensure_ascii=False))
        elif "error" in result:
            print(f"❌ {result['error']}")
        else:
            print(f"📊 版本对比: {result['tag1']} → {result['tag2']}")
            print(f"   文件变更: {result['file_count']} 个")
            print(f"   提交数: {result['commit_count']}")
            print()
            if result["files"]:
                print("变更文件:")
                for f in result["files"][:20]:
                    print(f"  {f['status']}  {f['file']}")
                if len(result["files"]) > 20:
                    print(f"  ... 共 {len(result['files'])} 个文件")
            print()
            if result["commits"]:
                print("提交历史:")
                for c in result["commits"][:10]:
                    print(f"  {c}")

    elif args.rollback is not None:
        tag = None if args.rollback == "auto" else args.rollback
        result = rollback_version(project_dir, tag, args.force)

        if args.json:
            print(json.dumps(result, indent=2, ensure_ascii=False))
        elif "error" in result:
            print(f"❌ {result['error']}")
            if "changes" in result:
                print(f"   {result['changes']}")
        else:
            print(f"✅ {result['message']}")

    elif args.snapshot:
        result = save_snapshot(project_dir)

        if args.json:
            print(json.dumps(result, indent=2, ensure_ascii=False))
        elif "error" in result:
            print(f"❌ {result['error']}")
        else:
            print(f"✅ 快照已保存: {result['path']}")
            for f in result["files"]:
                print(f"  📦 {f}")

    elif args.tag:
        result = auto_tag(project_dir, args.message)

        if args.json:
            print(json.dumps(result, indent=2, ensure_ascii=False))
        elif "error" in result:
            print(f"❌ {result['error']}")
        else:
            print(f"✅ 标签已创建: {result['tag']}")
            if result.get("message"):
                print(f"   消息: {result['message']}")
            print(f"   推送到远程: {result['command']}")

    elif args.status:
        result = get_status(project_dir)

        if args.json:
            print(json.dumps(result, indent=2, ensure_ascii=False))
        else:
            print(f"📊 版本状态:")
            print(f"   分支: {result['branch']}")
            print(f"   最新提交: {result['last_commit']}")
            print(f"   最新稳定版本: {result['latest_stable']}")
            print(f"   未提交更改: {result['changed_files']} 个文件")
            print(f"   标签总数: {result['tag_count']}")
            if result["recent_snapshots"]:
                print(f"   最近快照:")
                for s in result["recent_snapshots"]:
                    print(f"     📦 {s}")

    else:
        parser.print_help()


if __name__ == "__main__":
    main()
