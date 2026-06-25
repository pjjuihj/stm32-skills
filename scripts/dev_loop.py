#!/usr/bin/env python
"""STM32 开发模式循环。

监控源文件变化 → 自动编译 → 自动烧录 → 串口监听。
实现"改了就烧，烧了就看"的快速迭代。

用法:
  python dev_loop.py --auto . --port COM3                    # 开发模式
  python dev_loop.py --auto . --port COM3 --no-flash         # 只编译不烧录
  python dev_loop.py --auto . --port COM3 --interval 2       # 2 秒检查一次

功能:
  - 监控 Core/Src/ 和 Core/Inc/ 下的 .c/.h 文件变化
  - 文件变化后自动编译
  - 编译成功后自动烧录（可选）
  - 烧录后自动输出编译时间戳确认
  - Ctrl+C 退出
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

# 脚本目录
SCRIPT_DIR = Path(__file__).parent

# 使用共享模块
from shared import setup_encoding, run_script, find_uv4

setup_encoding()


def detect_project(project_dir: str) -> dict:
    """检测项目配置。"""
    try:
        from auto_detect import auto_detect_config, resolve_paths
        config = auto_detect_config(project_dir)
        if config:
            return resolve_paths(config, project_dir)
    except ImportError:
        pass
    return {"project_dir": str(Path(project_dir).resolve())}


def get_source_files(project_dir: str, extra_dirs: list[str] = None) -> list[Path]:
    """获取需要监控的源文件列表。"""
    dirs_to_watch = [
        os.path.join(project_dir, "Core", "Src"),
        os.path.join(project_dir, "Core", "Inc"),
        os.path.join(project_dir, "Drivers"),
    ]
    if extra_dirs:
        dirs_to_watch.extend(extra_dirs)

    files = []
    for d in dirs_to_watch:
        if not os.path.isdir(d):
            continue
        for root, _, filenames in os.walk(d):
            for f in filenames:
                if f.endswith(('.c', '.h', '.s')):
                    files.append(Path(root) / f)
    return files


def file_hash(filepath: Path) -> str:
    """计算文件内容的哈希值。"""
    try:
        return hashlib.md5(filepath.read_bytes()).hexdigest()
    except (OSError, IOError):
        return ""


def scan_files(files: list[Path]) -> dict[str, str]:
    """扫描所有文件，返回 {路径: 哈希} 字典。"""
    return {str(f): file_hash(f) for f in files}


def find_changes(old: dict[str, str], new: dict[str, str]) -> list[str]:
    """找出变化的文件。"""
    changed = []
    for path, hash_val in new.items():
        if old.get(path) != hash_val:
            changed.append(path)
    return changed


def compile_project(paths: dict) -> bool:
    """编译项目。"""
    project_file = paths.get("project_file")
    uv4_path = paths.get("uv4_path")
    target = paths.get("target")
    project_dir = paths["project_dir"]

    if not project_file or not uv4_path:
        print("  ❌ 缺少项目文件或 UV4.exe")
        return False

    build_log = os.path.join(project_dir, "build.log")
    cmd = [uv4_path, "-b", project_file, "-o", build_log, "-j0"]
    if target:
        cmd.extend(["-t", target])

    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
        if proc.returncode <= 1:
            print(f"  ✅ 编译成功")
            return True
        else:
            print(f"  ❌ 编译失败（返回码: {proc.returncode}）")
            # 显示错误摘要
            if os.path.exists(build_log):
                with open(build_log, "r", encoding="utf-8", errors="replace") as f:
                    lines = f.readlines()
                error_lines = [l.strip() for l in lines if "error:" in l.lower()]
                for err in error_lines[:3]:
                    print(f"    • {err[:120]}")
            return False
    except subprocess.TimeoutExpired:
        print("  ❌ 编译超时")
        return False


def flash_device(paths: dict, port: str) -> bool:
    """烧录到设备。"""
    project_file = paths.get("project_file")
    uv4_path = paths.get("uv4_path")
    target = paths.get("target")

    if not project_file or not uv4_path:
        print("  ❌ 缺少项目文件或 UV4.exe")
        return False

    cmd = [uv4_path, "-f", project_file, "-o", os.path.join(paths["project_dir"], "flash.log"), "-j0"]
    if target:
        cmd.extend(["-t", target])

    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
        if proc.returncode == 0:
            print(f"  ✅ 烧录成功")
            return True
        else:
            print(f"  ❌ 烧录失败（返回码: {proc.returncode}）")
            return False
    except subprocess.TimeoutExpired:
        print("  ❌ 烧录超时")
        return False


def auto_fix(paths: dict) -> bool:
    """尝试自动修复编译错误。"""
    project_dir = paths["project_dir"]
    result = run_script("auto_fix.py", ["--auto", project_dir, "--auto-fix"], timeout=60)
    if result["success"]:
        print(f"  🔧 自动修复完成")
        return True
    return False


def record_error(error: str, fix: str):
    """记录错误到 error_tracker。"""
    try:
        run_script("error_tracker.py", [
            "--record", "--error", error, "--fix", fix
        ], timeout=10)
    except Exception:
        pass  # 记录失败不影响主流程


def main():
    parser = argparse.ArgumentParser(description="STM32 开发模式循环")
    parser.add_argument("--auto", metavar="DIR", default=".", help="项目目录")
    parser.add_argument("--port", help="串口端口（如 COM3）")
    parser.add_argument("--no-flash", action="store_true", help="只编译不烧录")
    parser.add_argument("--no-fix", action="store_true", help="编译失败不自动修复")
    parser.add_argument("--interval", type=float, default=1.0, help="文件检查间隔（秒）")
    parser.add_argument("--watch-dir", action="append", help="额外监控目录")
    parser.add_argument("--max-fix", type=int, default=3, help="最大自动修复轮数")
    args = parser.parse_args()

    project_dir = str(Path(args.auto).resolve())
    print(f"STM32 开发模式循环")
    print(f"  项目: {project_dir}")
    print(f"  端口: {args.port or '未指定（只编译）'}")
    print(f"  模式: {'编译+烧录' if args.port and not args.no_flash else '只编译'}")
    print(f"  检查间隔: {args.interval} 秒")
    print(f"  按 Ctrl+C 退出")
    print()

    # 检测项目
    paths = detect_project(project_dir)
    if not paths.get("project_file"):
        print("❌ 未找到项目文件 (.uvprojx)")
        sys.exit(1)

    # 获取监控文件列表
    files = get_source_files(project_dir, args.watch_dir)
    if not files:
        print("❌ 未找到源文件")
        sys.exit(1)

    print(f"  监控 {len(files)} 个文件")
    print()

    # 初始扫描
    last_hashes = scan_files(files)
    compile_count = 0
    error_count = 0

    try:
        while True:
            time.sleep(args.interval)

            # 扫描文件变化
            current_hashes = scan_files(files)
            changed = find_changes(last_hashes, current_hashes)

            if not changed:
                continue

            # 显示变化的文件
            print(f"\n{'='*60}")
            print(f"[{datetime.now().strftime('%H:%M:%S')}] 检测到文件变化:")
            for f in changed[:5]:
                print(f"  • {os.path.basename(f)}")
            if len(changed) > 5:
                print(f"  ... 共 {len(changed)} 个文件")
            print(f"{'='*60}")

            # 更新哈希（在编译前更新，避免编译期间的文件变化被重复检测）
            last_hashes = current_hashes

            # 编译
            print(f"\n📦 编译中...")
            compile_ok = compile_project(paths)

            if not compile_ok and not args.no_fix:
                # 尝试自动修复
                for fix_round in range(args.max_fix):
                    print(f"\n🔧 尝试自动修复（第 {fix_round + 1} 轮）...")
                    if not auto_fix(paths):
                        break
                    print(f"\n📦 重新编译...")
                    compile_ok = compile_project(paths)
                    if compile_ok:
                        record_error("编译失败", "auto_fix 自动修复")
                        break

            compile_count += 1

            if not compile_ok:
                error_count += 1
                print(f"\n⚠️ 编译失败，继续监控文件变化...")
                continue

            # 烧录
            if args.port and not args.no_flash:
                print(f"\n🔥 烧录中...")
                flash_ok = flash_device(paths, args.port)
                if not flash_ok:
                    error_count += 1
                    print(f"\n⚠️ 烧录失败，继续监控文件变化...")
                    continue

            print(f"\n✅ 完成（编译 {compile_count} 次，失败 {error_count} 次）")
            print(f"   等待文件变化...")

    except KeyboardInterrupt:
        print(f"\n\n退出开发循环")
        print(f"  编译次数: {compile_count}")
        print(f"  失败次数: {error_count}")
        print(f"  成功率: {(compile_count - error_count) / max(compile_count, 1) * 100:.0f}%")


if __name__ == "__main__":
    main()
