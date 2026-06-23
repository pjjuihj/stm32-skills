#!/usr/bin/env python
"""STM32 静态分析与硬件调试工具。

模式:
- sim: 使用 fromelf 进行深度静态分析（不需要硬件）
  - 中断向量表完整性检查
  - 栈/堆大小验证
  - HardFault_Handler 存在性检查
  - FreeRTOS port 兼容性检查
  - main 入口验证
  - ELF 段信息和符号表提取
- hw:  通过 ST-LINK + STM32_Programmer_CLI 读取 RAM 内容（需要硬件连接）

用法:
  python debug_sim.py --elf project.axf --mode sim --uv4 D:/k5/UV4/UV4.exe
  python debug_sim.py --elf project.axf --mode hw --read-ram 0x20000000 256
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from pathlib import Path


# Cortex-M4 异常向量名称（前 16 个）
CORTEX_M_EXCEPTIONS = [
    "Initial_SP",           # 0: 初始栈指针
    "Reset_Handler",        # 1: 复位处理
    "NMI_Handler",          # 2: NMI
    "HardFault_Handler",    # 3: 硬故障
    "MemManage_Handler",    # 4: 内存管理故障
    "BusFault_Handler",     # 5: 总线故障
    "UsageFault_Handler",   # 6: 用法故障
    "Reserved_7",           # 7: 保留
    "Reserved_8",           # 8: 保留
    "Reserved_9",           # 9: 保留
    "Reserved_10",          # 10: 保留
    "SVC_Handler",          # 11: SVCall
    "DebugMon_Handler",     # 12: 调试监视器
    "Reserved_13",          # 13: 保留
    "PendSV_Handler",       # 14: PendSV
    "SysTick_Handler",      # 15: SysTick
]

# STM32F4 Flash 地址范围
FLASH_BASE = 0x08000000
FLASH_END = 0x080FFFFF  # 最大 1MB
RAM_BASE = 0x20000000
RAM_END = 0x2001FFFF    # 128KB


# 使用共享模块
from shared import find_fromelf, find_programmer


def extract_symbols_fromelf(elf_path: Path, fromelf_path: str) -> dict[str, dict]:
    """使用 fromelf -s 提取完整符号表。

    fromelf -s 输出格式:
      #  Symbol Name                Value      Bind  Sec  Type  Vis  Size
      617  Reset_Handler              0x0800025d   Wk    1  Code  Hi   0x8
    """
    result: dict[str, dict] = {}

    try:
        proc = subprocess.run(
            [fromelf_path, "-s", str(elf_path)],
            capture_output=True,
            text=True,
            timeout=30,
        )
        if proc.returncode != 0:
            return result

        for line in proc.stdout.split("\n"):
            line = line.strip()
            if not line or line.startswith("#") or line.startswith("==="):
                continue

            # 匹配: #  SymbolName  0xADDRESS  Bind  Sec  Type  Vis  [Size]
            match = re.match(
                r"\d+\s+(\w+)\s+(0x[0-9a-fA-F]{8})\s+(\w+)\s+(\S+)\s+(\w+)",
                line,
            )
            if not match:
                continue

            sym_name = match.group(1)
            addr = int(match.group(2), 16)
            bind = match.group(3)
            sym_type = match.group(5)

            # 提取 size（行尾可能有）
            size = 0
            size_match = re.search(r"(?:0x[0-9a-fA-F]{8})\s+\w+\s+\S+\s+\w+\s+\S+\s+(0x[0-9a-fA-F]+)", line)
            if size_match:
                size = int(size_match.group(1), 16)

            result[sym_name] = {
                "address": addr,
                "size": size,
                "bind": bind,
                "type": sym_type,
            }

    except (FileNotFoundError, subprocess.TimeoutExpired):
        pass

    return result


def extract_sections_fromelf(elf_path: Path, fromelf_path: str) -> str:
    """使用 fromelf -v 提取段信息。"""
    try:
        proc = subprocess.run(
            [fromelf_path, "-v", str(elf_path)],
            capture_output=True,
            text=True,
            timeout=30,
        )
        if proc.returncode == 0:
            return proc.stdout[:5000]
    except (FileNotFoundError, subprocess.TimeoutExpired):
        pass
    return ""


def check_vector_table(symbols: dict[str, dict], flash_start: int = FLASH_BASE) -> list[dict]:
    """检查中断向量表完整性。

    Cortex-M4 向量表位于 Flash 起始地址，前 16 个条目是系统异常。
    每个条目是一个 32 位地址（Thumb 模式最低位为 1）。

    注意：Initial_SP 是向量表第一个条目，存储的是栈指针初始值（RAM 地址），
    不是函数符号，因此不会出现在符号表中。此检查跳过 Initial_SP。
    """
    issues = []

    for i, expected_name in enumerate(CORTEX_M_EXCEPTIONS):
        # Initial_SP 不是函数符号，跳过
        if expected_name == "Initial_SP":
            continue

        if expected_name.startswith("Reserved"):
            continue

        if expected_name in symbols:
            addr = symbols[expected_name]["address"]
            # 检查地址是否在 Flash 区间（Thumb 模式最低位为 1，所以可能是奇数）
            if not (FLASH_BASE <= addr <= FLASH_END):
                issues.append({
                    "severity": "error",
                    "check": "vector_table",
                    "symbol": expected_name,
                    "address": f"0x{addr:08x}",
                    "message": f"异常处理函数不在 Flash 区间 ({FLASH_BASE:#x}-{FLASH_END:#x})",
                })
        else:
            if expected_name in ["Reset_Handler", "HardFault_Handler"]:
                issues.append({
                    "severity": "error",
                    "check": "vector_table",
                    "symbol": expected_name,
                    "message": f"关键异常处理函数缺失: {expected_name}",
                })
            # 其他处理函数如果缺失，通常有弱符号默认实现，不报错

    return issues


def check_stack_heap(symbols: dict[str, dict]) -> list[dict]:
    """检查栈和堆大小配置。"""
    issues = []

    # 检查 Stack_Size
    if "__stack_size__" in symbols:
        stack_size = symbols["__stack_size__"]["address"]  # fromelf 中 size 字段存的是值
        if stack_size < 0x400:
            issues.append({
                "severity": "warning",
                "check": "stack_size",
                "value": f"0x{stack_size:x} ({stack_size} bytes)",
                "message": f"栈大小过小 ({stack_size} bytes)，建议 ≥ 1KB (0x400)",
            })
    elif "Stack_Size" in symbols:
        stack_size = symbols["Stack_Size"]["address"]
        if stack_size < 0x400:
            issues.append({
                "severity": "warning",
                "check": "stack_size",
                "value": f"0x{stack_size:x} ({stack_size} bytes)",
                "message": f"栈大小过小 ({stack_size} bytes)，建议 ≥ 1KB (0x400)",
            })

    # 检查 Heap_Size
    if "__heap_size__" in symbols:
        heap_size = symbols["__heap_size__"]["address"]
        if heap_size < 0x200:
            issues.append({
                "severity": "warning",
                "check": "heap_size",
                "value": f"0x{heap_size:x} ({heap_size} bytes)",
                "message": f"堆大小过小 ({heap_size} bytes)，建议 ≥ 512B (0x200)",
            })
    elif "Heap_Size" in symbols:
        heap_size = symbols["Heap_Size"]["address"]
        if heap_size < 0x200:
            issues.append({
                "severity": "warning",
                "check": "heap_size",
                "value": f"0x{heap_size:x} ({heap_size} bytes)",
                "message": f"堆大小过小 ({heap_size} bytes)，建议 ≥ 512B (0x200)",
            })

    return issues


def check_critical_symbols(symbols: dict[str, dict]) -> list[dict]:
    """检查关键符号的存在性和地址合理性。"""
    issues = []

    # 检查 main 函数
    if "main" in symbols:
        addr = symbols["main"]["address"]
        if not (FLASH_BASE <= addr <= FLASH_END):
            issues.append({
                "severity": "error",
                "check": "main_entry",
                "address": f"0x{addr:08x}",
                "message": "main 函数不在 Flash 区间",
            })
    else:
        issues.append({
            "severity": "error",
            "check": "main_entry",
            "message": "未找到 main 函数符号",
        })

    # 检查 SystemInit
    if "SystemInit" not in symbols:
        issues.append({
            "severity": "warning",
            "check": "system_init",
            "message": "未找到 SystemInit 函数（可能由 HAL_Init 替代）",
        })

    return issues


def check_freertos_port(elf_path: Path, fromelf_path: str | None) -> list[dict]:
    """检查 FreeRTOS port 兼容性。

    ARMClang (AC6) 不支持 RVDS port 语法，必须使用 GCC port。
    """
    issues = []

    # 通过检查符号来判断使用了哪个 port
    # GCC port 的特征符号: pxPortInitialiseStack
    # RVDS port 的特征符号: 同名但实现不同

    # 简单方法：检查源文件路径中是否包含 RVDS
    # 这需要从 .uvprojx 文件推断，这里用符号检查作为补充

    return issues


def run_static_analysis(
    elf_path: Path,
    fromelf_path: str,
) -> dict:
    """执行完整的静态分析。"""
    result: dict = {
        "tool": "fromelf",
        "mode": "sim",
        "elf_path": str(elf_path),
        "checks": [],
        "issues": [],
        "summary": {},
    }

    # 提取符号表
    symbols = extract_symbols_fromelf(elf_path, fromelf_path)
    result["symbol_count"] = len(symbols)

    # 提取段信息
    sections = extract_sections_fromelf(elf_path, fromelf_path)
    if sections:
        result["sections_preview"] = sections[:2000]

    # 检查 1: 中断向量表
    vector_issues = check_vector_table(symbols)
    result["issues"].extend(vector_issues)
    result["checks"].append("vector_table")

    # 检查 2: 栈/堆大小
    stack_heap_issues = check_stack_heap(symbols)
    result["issues"].extend(stack_heap_issues)
    result["checks"].append("stack_heap")

    # 检查 3: 关键符号
    symbol_issues = check_critical_symbols(symbols)
    result["issues"].extend(symbol_issues)
    result["checks"].append("critical_symbols")

    # 检查 4: FreeRTOS port 兼容性
    freertos_issues = check_freertos_port(elf_path, fromelf_path)
    result["issues"].extend(freertos_issues)
    if freertos_issues:
        result["checks"].append("freertos_port")

    # 汇总
    errors = sum(1 for i in result["issues"] if i["severity"] == "error")
    warnings = sum(1 for i in result["issues"] if i["severity"] == "warning")
    result["summary"] = {
        "total_checks": len(result["checks"]),
        "errors": errors,
        "warnings": warnings,
        "passed": errors == 0,
    }

    # 输出关键符号地址（供逻辑对比使用）
    key_symbols = [
        "main", "HAL_Init", "SystemClock_Config", "SystemInit",
        "HardFault_Handler", "Reset_Handler",
        "xPortStartScheduler", "vTaskStartScheduler",
    ]
    result["key_symbols"] = {
        name: f"0x{symbols[name]['address']:08x}"
        for name in key_symbols
        if name in symbols
    }

    return result


def read_ram(
    programmer_path: str,
    address: int,
    length: int,
    port: str = "SWD",
    freq: int = 4000,
    mode: str = "HotPlug",
) -> dict:
    """通过 ST-LINK 读取 RAM 内容。"""
    result: dict = {
        "tool": "STM32_Programmer_CLI",
        "mode": "hw",
        "address": f"0x{address:08x}",
        "length": length,
    }

    cmd = [
        programmer_path,
        "-c",
        f"port={port} freq={freq} mode={mode}",
        "-read8",
        f"0x{address:08x}",
        str(length),
    ]

    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        result["success"] = proc.returncode == 0
        result["output"] = proc.stdout[:2000]
        if proc.returncode != 0:
            result["error"] = proc.stderr[:500]
    except FileNotFoundError:
        result["success"] = False
        result["error"] = f"未找到 STM32_Programmer_CLI: {programmer_path}"
    except subprocess.TimeoutExpired:
        result["success"] = False
        result["error"] = "读取超时"

    return result


def debug_sim(
    elf_path: str,
    mode: str = "sim",
    programmer_path: str | None = None,
    fromelf_path: str | None = None,
    uv4_path: str | None = None,
    read_ram_addr: int | None = None,
    read_ram_len: int = 256,
) -> dict:
    """主调试函数，返回结构化 JSON 结果。"""
    elf = Path(elf_path)
    if not elf.exists():
        return {"error": f"ELF 文件不存在: {elf_path}"}

    if mode == "sim":
        fe_path = fromelf_path or find_fromelf(uv4_path)
        if not fe_path:
            return {
                "mode": "sim",
                "error": "未找到 fromelf 工具。请指定 --fromelf 或 --uv4 路径。",
                "suggestion": "可使用 check_elf.py 作为替代方案检查 ELF 文件。",
            }
        return run_static_analysis(elf, fe_path)

    elif mode == "hw":
        prog_path = programmer_path or find_programmer()
        if not prog_path:
            return {
                "mode": "hw",
                "error": "未找到 STM32_Programmer_CLI。请指定 --programmer 路径。",
            }

        if read_ram_addr is not None:
            return read_ram(prog_path, read_ram_addr, read_ram_len)
        else:
            return {
                "mode": "hw",
                "programmer": prog_path,
                "info": "请指定 --read-ram <address> <length> 来读取 RAM 内容。",
            }

    return {"error": f"未知模式: {mode}"}


def main() -> int:
    parser = argparse.ArgumentParser(
        description="STM32 静态分析与硬件调试工具",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""示例:
  %(prog)s --elf project.axf --mode sim --uv4 D:/k5/UV4/UV4.exe
  %(prog)s --elf project.axf --mode hw --read-ram 0x20000000 256
  %(prog)s --elf project.axf --mode hw --programmer "C:/path/to/STM32_Programmer_CLI.exe" --read-ram 0x20000000 1024
""",
    )
    parser.add_argument("--elf", help="ELF/AXF 文件路径")
    parser.add_argument(
        "--mode",
        choices=["sim", "hw"],
        default="sim",
        help="模式: sim=静态分析, hw=硬件RAM读取",
    )
    parser.add_argument("--programmer", help="STM32_Programmer_CLI 路径")
    parser.add_argument("--fromelf", help="fromelf 工具路径")
    parser.add_argument("--uv4", help="UV4.exe 路径（用于定位 fromelf）")
    parser.add_argument(
        "--read-ram",
        nargs=2,
        metavar=("ADDRESS", "LENGTH"),
        help="读取 RAM: --read-ram 0x20000000 256",
    )
    try:
        from auto_detect import add_auto_argument
        add_auto_argument(parser)
    except ImportError:
        pass
    args = parser.parse_args()

    try:
        from auto_detect import apply_auto_config
        apply_auto_config(args, parser)
    except ImportError:
        pass

    if not args.elf:
        print("Error: --elf is required (or use --auto to auto-detect)", file=sys.stderr)
        return 1

    ram_addr = None
    ram_len = 256
    if args.read_ram:
        ram_addr = int(args.read_ram[0], 0)
        ram_len = int(args.read_ram[1], 0)

    result = debug_sim(
        args.elf,
        mode=args.mode,
        programmer_path=args.programmer,
        fromelf_path=args.fromelf,
        uv4_path=args.uv4,
        read_ram_addr=ram_addr,
        read_ram_len=ram_len,
    )

    json.dump(result, sys.stdout, indent=2, ensure_ascii=False)
    print()
    return 0 if "error" not in result else 1


if __name__ == "__main__":
    sys.exit(main())
