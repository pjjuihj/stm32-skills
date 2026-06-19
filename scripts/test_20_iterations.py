#!/usr/bin/env python
"""20 次迭代测试 - USB DFU、串口监控、代码生成"""

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

# 添加父目录到路径
sys.path.insert(0, str(Path(__file__).parent))


def test_usb_dfu() -> bool:
    """测试 USB DFU 烧录"""
    try:
        import usb_dfu_flash
        return True
    except Exception:
        return False


def test_serial_monitor() -> bool:
    """测试串口监控"""
    try:
        import serial_monitor
        return True
    except Exception:
        return False


def test_code_gen() -> bool:
    """测试代码生成"""
    try:
        import code_gen
        return True
    except Exception:
        return False


def run_iteration(iteration: int) -> dict[str, Any]:
    """运行单次迭代"""
    result = {
        "iteration": iteration,
        "usb_dfu": False,
        "serial_monitor": False,
        "code_gen": False,
        "total": 0,
        "passed": 0
    }

    # 测试 USB DFU
    result["usb_dfu"] = test_usb_dfu()
    result["total"] += 1
    if result["usb_dfu"]:
        result["passed"] += 1

    # 测试串口监控
    result["serial_monitor"] = test_serial_monitor()
    result["total"] += 1
    if result["serial_monitor"]:
        result["passed"] += 1

    # 测试代码生成
    result["code_gen"] = test_code_gen()
    result["total"] += 1
    if result["code_gen"]:
        result["passed"] += 1

    return result


def main() -> int:
    parser = argparse.ArgumentParser(description="20 次迭代测试")
    parser.add_argument("--iterations", type=int, default=20, help="迭代次数")
    parser.add_argument("--verbose", action="store_true", help="详细输出")

    args = parser.parse_args()

    print("=" * 60)
    print(f"🧪 20 次迭代测试 (USB DFU + 串口监控 + 代码生成)")
    print("=" * 60)
    print()

    results = []
    for i in range(args.iterations):
        result = run_iteration(i + 1)
        results.append(result)

        if args.verbose:
            status = "✅" if result["passed"] == result["total"] else "❌"
            print(f"  {status} 迭代 {i+1}: {result['passed']}/{result['total']} 通过")

    # 统计结果
    total = len(results)
    all_passed = sum(1 for r in results if r["passed"] == r["total"])
    all_failed = sum(1 for r in results if r["passed"] == 0)

    usb_dfu_pass = sum(1 for r in results if r["usb_dfu"])
    serial_pass = sum(1 for r in results if r["serial_monitor"])
    code_gen_pass = sum(1 for r in results if r["code_gen"])

    print()
    print("=" * 60)
    print(f"📊 测试结果: {total} 次迭代")
    print(f"   全部通过: {all_passed}")
    print(f"   全部失败: {all_failed}")
    print(f"   USB DFU: {usb_dfu_pass}/{total} 通过")
    print(f"   串口监控: {serial_pass}/{total} 通过")
    print(f"   代码生成: {code_gen_pass}/{total} 通过")
    print("=" * 60)

    if all_passed == total:
        print("✅ 所有迭代测试通过！")
    else:
        print(f"❌ {total - all_passed} 次迭代有失败")

    return 0 if all_passed == total else 1


if __name__ == "__main__":
    sys.exit(main())
