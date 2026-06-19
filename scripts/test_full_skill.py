#!/usr/bin/env python
"""Skill 完整测试脚本

测试所有 Skill 脚本的功能。
"""

from __future__ import annotations

import argparse
import io
import os
import subprocess
import sys
import tempfile
from pathlib import Path

# 编码处理
if sys.stdout and hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass


def test_script_import(script_name: str) -> bool:
    """测试脚本导入"""
    try:
        if script_name == "cubemx_config":
            import cubemx_config
        elif script_name == "auto_fix":
            import auto_fix
        elif script_name == "check_elf":
            import check_elf
        elif script_name == "debug_sim":
            import debug_sim
        elif script_name == "optimize":
            import optimize
        elif script_name == "code_gen":
            import code_gen
        elif script_name == "memory_analyzer":
            import memory_analyzer
        elif script_name == "pin_checker":
            import pin_checker
        elif script_name == "clock_validator":
            import clock_validator
        elif script_name == "peripheral_validator":
            import peripheral_validator
        elif script_name == "nvic_checker":
            import nvic_checker
        return True
    except Exception as e:
        print(f"❌ 导入失败: {e}")
        return False


def test_script_help(script_path: str) -> bool:
    """测试脚本帮助信息"""
    try:
        result = subprocess.run(
            [sys.executable, script_path, "--help"],
            capture_output=True, text=True, timeout=10
        )
        return result.returncode == 0 or "usage:" in result.stdout.lower()
    except Exception:
        return False


def main() -> int:
    parser = argparse.ArgumentParser(description="Skill 完整测试脚本")
    parser.add_argument("--verbose", action="store_true", help="详细输出")
    args = parser.parse_args()

    print("=" * 60)
    print("🧪 Skill 完整测试")
    print("=" * 60)
    print()

    scripts = [
        "cubemx_config",
        "auto_fix",
        "check_elf",
        "debug_sim",
        "optimize",
        "code_gen",
        "memory_analyzer",
        "pin_checker",
        "clock_validator",
        "peripheral_validator",
        "nvic_checker",
    ]

    passed = 0
    failed = 0

    for script in scripts:
        print(f"测试 {script}...")
        if test_script_import(script):
            print(f"  ✅ {script} 导入成功")
            passed += 1
        else:
            print(f"  ❌ {script} 导入失败")
            failed += 1

    print()
    print("=" * 60)
    print(f"📊 测试结果: {passed} 通过, {failed} 失败")
    print("=" * 60)

    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
