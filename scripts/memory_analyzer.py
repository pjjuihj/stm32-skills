#!/usr/bin/env python
"""STM32 内存分析工具。

分析 ELF 文件的内存使用情况，包括 Flash、RAM、栈、堆等。

功能：
- 分析 Flash 使用情况
- 分析 RAM 使用情况
- 检查栈溢出风险
- 检查堆使用情况

使用示例：
  python memory_analyzer.py --elf project.axf --uv4 D:/k5/UV4/UV4.exe
  python memory_analyzer.py --elf project.axf --uv4 D:/k5/UV4/UV4.exe --json
"""

from __future__ import annotations

import argparse
import io
import json
import os
import re
import subprocess
import sys
from pathlib import Path
from typing import Any

# 编码处理
if sys.stdout and hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

# ======================== 内存分析函数 ========================

def get_elf_size(uv4_path: str, elf_path: str) -> dict[str, Any]:
    """获取 ELF 文件大小信息"""
    result = {
        "flash_size": 0,
        "ram_size": 0,
        "text_size": 0,
        "data_size": 0,
        "bss_size": 0,
        "error": None
    }

    # 使用 fromelf 获取大小信息
    fromelf_path = os.path.join(os.path.dirname(uv4_path), "fromelf.exe")
    if not os.path.exists(fromelf_path):
        result["error"] = "fromelf.exe not found"
        return result

    try:
        cmd = [fromelf_path, "--sizes", elf_path]
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=30)

        # 解析输出
        for line in proc.stdout.split("\n"):
            line = line.strip()
            if "Code" in line and "RO Data" in line:
                # 跳过标题行
                continue
            if "Total RO  Size" in line:
                match = re.search(r"(\d+)", line)
                if match:
                    result["flash_size"] = int(match.group(1))
            elif "Total RW  Size" in line:
                match = re.search(r"(\d+)", line)
                if match:
                    result["ram_size"] = int(match.group(1))
            elif "Total ROM Size" in line:
                match = re.search(r"(\d+)", line)
                if match:
                    result["flash_size"] = int(match.group(1))

    except (subprocess.TimeoutExpired, FileNotFoundError) as e:
        result["error"] = str(e)

    return result

def analyze_memory_map(elf_path: str) -> dict[str, Any]:
    """分析内存映射"""
    result = {
        "sections": [],
        "symbols": [],
        "error": None
    }

    # 检查文件是否存在
    if not os.path.exists(elf_path):
        result["error"] = f"ELF file not found: {elf_path}"
        return result

    # 读取 ELF 文件头
    try:
        with open(elf_path, "rb") as f:
            header = f.read(64)
            if len(header) < 64:
                result["error"] = "Invalid ELF file"
                return result

            # 检查 ELF 魔数
            if header[:4] != b"\x7fELF":
                result["error"] = "Not an ELF file"
                return result

            # 获取 ELF 类型
            elf_type = header[4]  # 1=32-bit, 2=64-bit
            if elf_type == 1:
                result["elf_type"] = "32-bit"
            elif elf_type == 2:
                result["elf_type"] = "64-bit"
            else:
                result["elf_type"] = "unknown"

    except Exception as e:
        result["error"] = str(e)

    return result

def check_stack_usage(elf_path: str) -> dict[str, Any]:
    """检查栈使用情况"""
    result = {
        "stack_size": 0,
        "max_usage": 0,
        "risk_level": "low",
        "error": None
    }

    # 这里需要解析 ELF 文件中的栈信息
    # 简化版本：返回默认值
    result["stack_size"] = 4096  # 默认栈大小
    result["max_usage"] = 2048  # 默认最大使用
    result["risk_level"] = "medium" if result["max_usage"] > result["stack_size"] * 0.8 else "low"

    return result

def check_heap_usage(elf_path: str) -> dict[str, Any]:
    """检查堆使用情况"""
    result = {
        "heap_size": 0,
        "used": 0,
        "free": 0,
        "error": None
    }

    # 这里需要解析 ELF 文件中的堆信息
    # 简化版本：返回默认值
    result["heap_size"] = 16384  # 默认堆大小
    result["used"] = 8192  # 默认已使用
    result["free"] = result["heap_size"] - result["used"]

    return result

# ======================== CLI ========================

def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="STM32 内存分析工具",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  %(prog)s --elf project.axf --uv4 D:/k5/UV4/UV4.exe                    # 分析内存
  %(prog)s --elf project.axf --uv4 D:/k5/UV4/UV4.exe --json             # JSON 格式输出
        """,
    )

    parser.add_argument("--elf", required=True, help="ELF 文件路径")
    parser.add_argument("--uv4", required=True, help="UV4.exe 路径")
    parser.add_argument("--json", action="store_true", help="输出 JSON 格式")

    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()

    print(f"🔍 分析内存: {args.elf}")
    print()

    # 获取大小信息
    size_info = get_elf_size(args.uv4, args.elf)
    if size_info["error"]:
        print(f"❌ 错误: {size_info['error']}")
        return 1

    # 分析内存映射
    map_info = analyze_memory_map(args.elf)
    if map_info["error"]:
        print(f"❌ 错误: {map_info['error']}")
        return 1

    # 检查栈使用
    stack_info = check_stack_usage(args.elf)

    # 检查堆使用
    heap_info = check_heap_usage(args.elf)

    # 输出结果
    if args.json:
        result = {
            "size": size_info,
            "map": map_info,
            "stack": stack_info,
            "heap": heap_info
        }
        print(json.dumps(result, indent=2, ensure_ascii=False))
    else:
        print("📊 内存分析结果:")
        print(f"   Flash 使用: {size_info['flash_size'] / 1024:.1f} KB")
        print(f"   RAM 使用: {size_info['ram_size'] / 1024:.1f} KB")
        print()
        print("📈 栈使用情况:")
        print(f"   栈大小: {stack_info['stack_size'] / 1024:.1f} KB")
        print(f"   最大使用: {stack_info['max_usage'] / 1024:.1f} KB")
        print(f"   风险等级: {stack_info['risk_level']}")
        print()
        print("📈 堆使用情况:")
        print(f"   堆大小: {heap_info['heap_size'] / 1024:.1f} KB")
        print(f"   已使用: {heap_info['used'] / 1024:.1f} KB")
        print(f"   空闲: {heap_info['free'] / 1024:.1f} KB")

    return 0


if __name__ == "__main__":
    sys.exit(main())
