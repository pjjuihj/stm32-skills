#!/usr/bin/env python
"""ELF/AXF 文件检查工具。

检查编译产物的大小、关键符号地址、时间戳。
用于编译后验证和逻辑偏移检测。

工具链优先级：fromelf (Keil 自带) > arm-none-eabi-size/nm

用法:
  python check_elf.py --elf <path> --uv4 <UV4.exe路径>
  python check_elf.py --elf <path> --symbols "main,HAL_Init" --uv4 D:/k5/UV4/UV4.exe
  python check_elf.py --elf <path> --symbols "main" --map <path>

输出 JSON 到 stdout，包含:
- 文件基本信息（路径、大小、时间戳）
- 段大小（text/data/bss/ro_data）
- 指定符号的地址和类型
- Flash/RAM 使用量估算
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from datetime import datetime
from pathlib import Path


def find_fromelf(uv4_path: str | None = None) -> str | None:
    """查找 fromelf 工具路径（优先 Keil 自带）。"""
    import shutil

    if uv4_path:
        keil_root = Path(uv4_path).parent.parent
        for pattern in [
            "ARM/ARMCLANG/bin/fromelf.exe",
            "ARM/ARMCC/bin/fromelf.exe",
        ]:
            for candidate in keil_root.glob(pattern):
                if candidate.exists():
                    return str(candidate)

    return shutil.which("fromelf")


def find_arm_tools() -> dict[str, str | None]:
    """查找 arm-none-eabi 工具链。"""
    import shutil

    return {
        "size": shutil.which("arm-none-eabi-size"),
        "nm": shutil.which("arm-none-eabi-nm"),
    }


def get_file_info(elf_path: Path) -> dict:
    """获取文件基本信息。"""
    stat = elf_path.stat()
    return {
        "path": str(elf_path),
        "name": elf_path.name,
        "size_bytes": stat.st_size,
        "timestamp": datetime.fromtimestamp(stat.st_mtime).isoformat(),
    }


def get_size_fromelf(elf_path: Path, fromelf_path: str) -> dict | None:
    """使用 fromelf -z 获取 ELF 段大小。

    fromelf -z 输出格式:
      Code (inc. data)   RO Data    RW Data    ZI Data      Debug   Object Name
       54760       1136      10696         64      23464     531917   project.axf
       54760       1136      10696         64          0          0   ROM Totals
    """
    try:
        proc = subprocess.run(
            [fromelf_path, "-z", str(elf_path)],
            capture_output=True,
            text=True,
            timeout=30,
        )
        if proc.returncode != 0:
            return None

        # 解析 ROM Totals 行（最准确的汇总）
        for line in proc.stdout.split("\n"):
            if "ROM Totals" in line:
                parts = line.split()
                if len(parts) >= 5:
                    try:
                        code = int(parts[0])
                        ro_data = int(parts[2])
                        rw_data = int(parts[3])
                        # ROM Totals 的 ZI Data 为 0，需要从 Image 行获取
                        return {
                            "text": code,
                            "data": rw_data,
                            "bss": 0,  # ROM Totals 不含 ZI
                            "ro_data": ro_data,
                            "dec": code + rw_data,
                            "tool": "fromelf -z (ROM Totals)",
                        }
                    except ValueError:
                        continue

        # 回退：解析 Image 行（包含 ZI Data）
        for line in proc.stdout.split("\n"):
            if ".axf" in line or ".elf" in line:
                parts = line.split()
                if len(parts) >= 5:
                    try:
                        code = int(parts[0])
                        ro_data = int(parts[2])
                        rw_data = int(parts[3])
                        zi_data = int(parts[4])
                        return {
                            "text": code,
                            "data": rw_data,
                            "bss": zi_data,
                            "ro_data": ro_data,
                            "dec": code + rw_data + zi_data,
                            "tool": "fromelf -z",
                        }
                    except ValueError:
                        continue

        return None
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return None


def get_size_arm(elf_path: Path, tool_path: str | None = None) -> dict | None:
    """使用 arm-none-eabi-size 获取 ELF 段大小。"""
    size_cmd = tool_path or "arm-none-eabi-size"
    try:
        result = subprocess.run(
            [size_cmd, str(elf_path)],
            capture_output=True, text=True, timeout=10,
        )
        if result.returncode == 0:
            return parse_size_output(result.stdout)
    except (FileNotFoundError, subprocess.TimeoutExpired):
        pass
    return None


def parse_size_output(output: str) -> dict | None:
    """解析 arm-none-eabi-size 输出。"""
    for line in output.strip().split("\n"):
        line = line.strip()
        if not line or line.startswith("text") or line.startswith("filename"):
            continue
        parts = line.split()
        if len(parts) >= 6:
            try:
                return {
                    "text": int(parts[0]),
                    "data": int(parts[1]),
                    "bss": int(parts[2]),
                    "dec": int(parts[3]),
                    "tool": "arm-none-eabi-size",
                }
            except ValueError:
                continue
    return None


def get_symbols_fromelf(
    elf_path: Path, symbols: list[str], fromelf_path: str
) -> dict:
    """使用 fromelf -s 获取指定符号的地址和类型。

    fromelf -s 输出格式:
      #  Symbol Name                Value      Bind  Sec  Type  Vis  Size
      617  Reset_Handler              0x0800025d   Wk    1  Code  Hi   0x8
      779  HAL_Init                   0x08002295   Gb    1  Code  Hi   0x36
    """
    result_dict: dict[str, dict] = {}

    try:
        proc = subprocess.run(
            [fromelf_path, "-s", str(elf_path)],
            capture_output=True,
            text=True,
            timeout=30,
        )
        if proc.returncode != 0:
            return result_dict

        # 解析 fromelf 符号表
        for line in proc.stdout.split("\n"):
            line = line.strip()
            if not line or line.startswith("#") or line.startswith("==="):
                continue

            # 格式: #  SymbolName  0xADDRESS  Bind  Sec  Type  Vis  [Size]
            # 用正则匹配：数字开头，然后是符号名，然后是 0x 地址
            match = re.match(
                r"\d+\s+(\w+)\s+(0x[0-9a-fA-F]{8})\s+(\w+)\s+(\S+)\s+(\w+)",
                line,
            )
            if not match:
                continue

            sym_name = match.group(1)
            addr_str = match.group(2)
            bind = match.group(3)
            sym_type = match.group(5)

            if sym_name in symbols and sym_name not in result_dict:
                result_dict[sym_name] = {
                    "address": addr_str,
                    "size": 0,
                    "type": f"fromelf ({bind} {sym_type})",
                }

                # 尝试获取 size
                size_match = re.search(r"(?:0x[0-9a-fA-F]{8})\s+\w+\s+\S+\s+\w+\s+\S+\s+(0x[0-9a-fA-F]+)", line)
                if size_match:
                    result_dict[sym_name]["size"] = int(size_match.group(1), 16)

    except (FileNotFoundError, subprocess.TimeoutExpired):
        pass

    return result_dict


def get_symbols_arm(
    elf_path: Path, symbols: list[str], tool_path: str | None = None
) -> dict:
    """使用 arm-none-eabi-nm 获取指定符号的地址和类型。"""
    nm_cmd = tool_path or "arm-none-eabi-nm"
    result_dict: dict[str, dict] = {}

    try:
        result = subprocess.run(
            [nm_cmd, "--print-size", "--size-sort", str(elf_path)],
            capture_output=True, text=True, timeout=30,
        )
        if result.returncode != 0:
            return result_dict

        for line in result.stdout.strip().split("\n"):
            parts = line.split()
            if len(parts) < 4:
                continue
            addr, size, sym_type, name = parts[0], parts[1], parts[2], parts[3]
            if name in symbols:
                result_dict[name] = {
                    "address": f"0x{addr}",
                    "size": int(size, 16) if size else 0,
                    "type": sym_type,
                }
    except (FileNotFoundError, subprocess.TimeoutExpired):
        pass

    return result_dict


def parse_map_symbols(map_path: Path, symbols: list[str]) -> dict:
    """从 .map 文件解析符号地址（回退方案）。"""
    result_dict: dict[str, dict] = {}

    if not map_path.exists():
        return result_dict

    try:
        content = map_path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return result_dict

    for line in content.split("\n"):
        line = line.strip()
        if not line:
            continue
        parts = line.split()
        if len(parts) >= 2:
            name = parts[0]
            if name in symbols and name not in result_dict:
                try:
                    addr = int(parts[1], 16)
                    result_dict[name] = {
                        "address": f"0x{addr:08x}",
                        "size": 0,
                        "type": "map",
                    }
                except ValueError:
                    continue

    return result_dict


def check_elf(
    elf_path: str,
    symbols: list[str] | None = None,
    map_path: str | None = None,
    uv4_path: str | None = None,
    fromelf_path: str | None = None,
    size_tool: str | None = None,
    nm_tool: str | None = None,
) -> dict:
    """主检查函数，返回结构化 JSON 结果。"""
    elf = Path(elf_path)

    if not elf.exists():
        return {"error": f"ELF 文件不存在: {elf_path}"}

    result = get_file_info(elf)

    # 查找工具链
    fe_path = fromelf_path or find_fromelf(uv4_path)
    arm_tools = find_arm_tools()

    # 获取段大小（优先 fromelf）
    size_info = None
    if fe_path:
        size_info = get_size_fromelf(elf, fe_path)
    if not size_info and arm_tools.get("size"):
        size_info = get_size_arm(elf, arm_tools["size"])
    if not size_info and size_tool:
        size_info = get_size_arm(elf, size_tool)

    if size_info:
        result["size"] = size_info
        flash = size_info.get("text", 0) + size_info.get("data", 0)
        ram = size_info.get("data", 0) + size_info.get("bss", 0)
        result["flash_usage_kb"] = round(flash / 1024, 1)
        result["ram_usage_kb"] = round(ram / 1024, 1)

    # 获取符号信息（优先 fromelf）
    if symbols:
        sym_info = {}
        if fe_path:
            sym_info = get_symbols_fromelf(elf, symbols, fe_path)
        if not sym_info and arm_tools.get("nm"):
            sym_info = get_symbols_arm(elf, symbols, arm_tools["nm"])
        if not sym_info and nm_tool:
            sym_info = get_symbols_arm(elf, symbols, nm_tool)
        if not sym_info and map_path:
            sym_info = parse_map_symbols(Path(map_path), symbols)
        if sym_info:
            result["symbols"] = sym_info

    # 工具链信息
    result["tools"] = {
        "fromelf": fe_path,
        "arm_size": arm_tools.get("size"),
        "arm_nm": arm_tools.get("nm"),
    }

    return result


def main() -> int:
    parser = argparse.ArgumentParser(
        description="ELF/AXF 文件检查工具",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""示例:
  %(prog)s --elf project.axf --uv4 D:/k5/UV4/UV4.exe
  %(prog)s --elf project.axf --symbols "main,Gimbal_t" --uv4 D:/k5/UV4/UV4.exe
  %(prog)s --elf project.axf --map project.map --symbols "main"
  %(prog)s --auto d:/project  # 自动检测项目配置
""",
    )
    parser.add_argument("--elf", help="ELF/AXF 文件路径")
    parser.add_argument("--symbols", help="要检查的符号，逗号分隔")
    parser.add_argument("--map", help=".map 文件路径（回退方案）")
    parser.add_argument("--uv4", help="UV4.exe 路径（用于定位 fromelf）")
    parser.add_argument("--fromelf", help="fromelf 工具路径（直接指定）")
    parser.add_argument("--size-tool", help="arm-none-eabi-size 路径")
    parser.add_argument("--nm-tool", help="arm-none-eabi-nm 路径")
    try:
        from auto_detect import add_auto_argument, apply_auto_config
        add_auto_argument(parser)
    except ImportError:
        pass
    args = parser.parse_args()

    # 应用自动检测
    try:
        from auto_detect import apply_auto_config
        apply_auto_config(args, parser)
    except ImportError:
        pass

    if not args.elf:
        print("Error: --elf is required (or use --auto to auto-detect)", file=sys.stderr)
        return 1

    symbols = [s.strip() for s in args.symbols.split(",")] if args.symbols else None

    result = check_elf(
        args.elf,
        symbols=symbols,
        map_path=args.map,
        uv4_path=args.uv4,
        fromelf_path=args.fromelf,
        size_tool=args.size_tool,
        nm_tool=args.nm_tool,
    )

    json.dump(result, sys.stdout, indent=2, ensure_ascii=False)
    print()
    return 0 if "error" not in result else 1


if __name__ == "__main__":
    sys.exit(main())
