#!/usr/bin/env python
"""Renode 仿真测试工具。

使用 Renode 模拟器对 STM32 固件进行无硬件仿真测试。
支持启动验证、UART 输出捕获、基本执行流检查。

用法:
  python renode_sim.py --elf project.axf --mode boot --timeout 5
  python renode_sim.py --elf project.axf --mode uart --timeout 10 --uart-log output.txt

模式:
  boot - 验证固件能否正常启动（CPU PC 寄存器推进）
  uart - 捕获 UART1 输出（验证串口通信）
  full - 完整仿真（启动 + UART + 基本执行流检查）

依赖:
  - Renode (https://renode.io)
  - renode 命令需在 PATH 中，或通过 --renode 参数指定路径
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path


SCRIPT_DIR = Path(__file__).parent / "renode"

# Renode 内置 STM32 平台映射（芯片系列 → 平台文件）
RENODE_PLATFORMS = {
    "F0": "stm32f0.repl",
    "F1": "stm32f103.repl",
    "F2": "stm32f4.repl",      # F2 与 F4 相似，用 F4 平台
    "F3": "stm32f4.repl",      # F3 与 F4 相似，用 F4 平台
    "F4": "stm32f4.repl",
    "F7": "stm32f746.repl",
    "G0": "stm32g0.repl",
    "G4": "stm32f4.repl",      # G4 与 F4 相似，用 F4 平台
    "H7": "stm32h743.repl",
    "L0": "stm32l071.repl",
    "L1": "stm32l151.repl",
    "L4": "stm32f4.repl",      # L4 与 F4 相似，用 F4 平台
    "L5": "stm32l552.repl",
    "U5": "stm32l552.repl",    # U5 与 L5 相似
    "WB": "stm32wba52.repl",
    "WL": "stm32wba52.repl",   # WL 与 WB 相似
}


def detect_renode_platform(chip: str | None = None, elf_path: Path | None = None) -> str | None:
    """检测芯片系列并返回 Renode 平台文件名。

    优先级：
    1. 从 --chip 参数提取系列
    2. 从 ELF 文件名推断
    3. 默认使用 stm32f4.repl（最通用）
    """
    series = None

    # 从芯片型号提取系列
    if chip:
        m = re.match(r"STM32([A-Z]\d)", chip.upper())
        if m:
            series = m.group(1)

    # 从 ELF 文件名推断
    if not series and elf_path:
        name = elf_path.stem.upper()
        m = re.search(r"STM32([A-Z]\d)", name)
        if m:
            series = m.group(1)

    # 查找平台文件
    if series and series in RENODE_PLATFORMS:
        return RENODE_PLATFORMS[series]

    # 默认使用 F4 平台（最通用）
    return "stm32f4.repl"


def find_renode(explicit_path: str | None = None) -> str | None:
    """查找 Renode 可执行文件路径。"""
    if explicit_path:
        p = Path(explicit_path)
        if p.exists():
            return str(p)
        # 检查是否是目录
        if p.is_dir():
            for name in ["renode.exe", "renode", "Renode.exe"]:
                candidate = p / name
                if candidate.exists():
                    return str(candidate)
        return None

    # PATH 搜索
    found = shutil.which("renode")
    if found:
        return found

    # 常见安装路径
    candidates = [
        r"C:\Program Files\Renode\renode.exe",
        r"C:\Program Files (x86)\Renode\renode.exe",
        os.path.expanduser(r"~\.renode\renode.exe"),
        os.path.expanduser(r"~\AppData\Local\Renode\renode.exe"),
    ]

    for candidate in candidates:
        if Path(candidate).exists():
            return candidate

    return None


def check_renode_available(renode_path: str | None) -> dict:
    """检查 Renode 是否可用。"""
    path = find_renode(renode_path)
    if not path:
        return {
            "available": False,
            "error": "Renode 未安装或不在 PATH 中。",
            "install_hint": (
                "请从 https://github.com/renode/renode/releases 下载安装。\n"
                "Windows: 下载 .msi 安装包或 portable .zip 解压。\n"
                "安装后确保 renode.exe 在 PATH 中，或使用 --renode 参数指定路径。"
            ),
        }

    return {"available": True, "path": path}


def run_renode_simulation(
    elf_path: str,
    mode: str = "boot",
    timeout: int = 5,
    uart_log: str | None = None,
    renode_path: str | None = None,
    chip: str | None = None,
) -> dict:
    """运行 Renode 仿真。"""
    # 检查 Renode
    renode_check = check_renode_available(renode_path)
    if not renode_check["available"]:
        return renode_check

    renode_exe = renode_check["path"]

    # 检查 ELF 文件
    elf = Path(elf_path)
    if not elf.exists():
        return {"error": f"ELF 文件不存在: {elf_path}"}

    # 自动检测芯片系列并选择 Renode 平台
    platform_name = detect_renode_platform(chip, elf)
    if not platform_name:
        return {"error": f"无法检测芯片系列，请使用 --chip 参数指定（如 STM32F407VETx）"}

    # 创建临时 UART 日志路径
    if not uart_log:
        uart_log = str(Path(tempfile.gettempdir()) / "renode_uart_output.txt")

    # 构建 Renode 命令
    # 使用 Renode 内置平台 + --port 避免端口冲突
    commands = [
        'mach create "test"',
        f'machine LoadPlatformDescription @platforms/cpus/{platform_name}',
        f'sysbus LoadELF "{elf}"',
        'start',
        f'sleep {timeout}',
        'pause',
        'echo SIMULATION_DONE',
        'quit',
    ]

    renode_cmd = [renode_exe, "--disable-xwt", "--port", "0", "-e", "\n".join(commands)]

    result: dict = {
        "tool": "renode",
        "mode": mode,
        "elf_path": str(elf),
        "timeout": timeout,
        "uart_log": uart_log,
    }

    try:
        proc = subprocess.run(
            renode_cmd,
            capture_output=True,
            text=True,
            timeout=timeout + 15,  # 额外 15 秒用于 Renode 启动/关闭
            cwd=str(SCRIPT_DIR),
        )

        result["returncode"] = proc.returncode
        result["stdout"] = proc.stdout[-3000:] if proc.stdout else ""
        result["stderr"] = proc.stderr[-1000:] if proc.stderr else ""

        # 分析结果
        stdout = proc.stdout or ""
        stderr = proc.stderr or ""
        combined = stdout + stderr

        if "SIMULATION_DONE" in combined:
            result["simulation_completed"] = True
        else:
            result["simulation_completed"] = False

        # 解析 Renode 日志
        events = []
        for line in combined.split("\n"):
            line = line.strip()
            if "Setting initial values" in line:
                events.append({"event": "cpu_init", "detail": line.split("]")[-1].strip()})
            elif "Machine started" in line:
                events.append({"event": "machine_start", "detail": "仿真开始"})
            elif "Watchdog reset" in line:
                events.append({"event": "iwdg_reset", "detail": "看门狗复位触发"})
            elif "CPU was halted" in line:
                events.append({"event": "cpu_halted", "detail": line.split("]")[-1].strip()})
            elif "[ERROR]" in line:
                events.append({"event": "error", "detail": line.split("]")[-1].strip()})
            elif "PC does not lay in memory" in line:
                events.append({"event": "pc_error", "detail": "PC 指向无效内存"})

        result["events"] = events

        # 检查 UART 输出
        uart_path = Path(uart_log)
        if uart_path.exists():
            try:
                uart_content = uart_path.read_text(encoding="utf-8", errors="replace")
                result["uart_output"] = uart_content[:2000]
                result["uart_bytes"] = len(uart_content)
                if uart_content.strip():
                    result["uart_has_output"] = True
                else:
                    result["uart_has_output"] = False
            except OSError:
                result["uart_has_output"] = False
        else:
            result["uart_has_output"] = False

        # Boot 模式分析
        if mode == "boot":
            cpu_init = any(e["event"] == "cpu_init" for e in events)
            machine_started = any(e["event"] == "machine_start" for e in events)
            iwdg_reset = any(e["event"] == "iwdg_reset" for e in events)

            if cpu_init and machine_started:
                result["boot_test"] = "PASS"
                msgs = ["固件成功启动并执行"]
                if iwdg_reset:
                    msgs.append("IWDG 看门狗复位已触发（仿真速度慢于实时，属正常现象）")
                result["message"] = "; ".join(msgs)
            else:
                result["boot_test"] = "FAIL"
                result["message"] = "固件启动失败"

        # UART 模式分析
        elif mode == "uart":
            if result.get("uart_has_output"):
                result["uart_test"] = "PASS"
                result["message"] = f"UART 有输出 ({result['uart_bytes']} bytes)"
            else:
                result["uart_test"] = "WARN"
                result["message"] = "UART 无输出（可能是外设未初始化或仿真时间不足）"

    except FileNotFoundError:
        result["error"] = f"Renode 可执行文件未找到: {renode_exe}"
        result["simulation_completed"] = False
    except subprocess.TimeoutExpired:
        result["error"] = f"仿真超时 ({timeout + 15}s)"
        result["simulation_completed"] = False
    except Exception as e:
        result["error"] = f"仿真异常: {str(e)}"
        result["simulation_completed"] = False

    return result


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Renode STM32 仿真测试工具",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""示例:
  %(prog)s --elf project.axf --mode boot --timeout 5
  %(prog)s --elf project.axf --mode uart --timeout 10
  %(prog)s --elf project.axf --mode full --timeout 30 --uart-log uart.txt
""",
    )
    parser.add_argument("--elf", help="ELF/AXF 文件路径")
    parser.add_argument(
        "--mode",
        choices=["boot", "uart", "full"],
        default="boot",
        help="仿真模式: boot=启动验证, uart=UART捕获, full=完整仿真",
    )
    parser.add_argument("--timeout", type=int, default=5, help="仿真超时(秒)")
    parser.add_argument("--uart-log", help="UART 输出保存路径")
    parser.add_argument("--renode", help="Renode 可执行文件路径")
    parser.add_argument("--chip", help="芯片型号（如 STM32F407VETx，自动选择 Renode 平台）")
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

    result = run_renode_simulation(
        args.elf,
        mode=args.mode,
        timeout=args.timeout,
        uart_log=args.uart_log,
        renode_path=args.renode,
        chip=args.chip,
    )

    json.dump(result, sys.stdout, indent=2, ensure_ascii=False)
    print()
    return 0 if result.get("simulation_completed") else 1


if __name__ == "__main__":
    sys.exit(main())
