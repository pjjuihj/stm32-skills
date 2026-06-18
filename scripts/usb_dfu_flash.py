#!/usr/bin/env python
"""USB DFU 烧录工具。

为 STM32F407 项目提供 USB DFU 烧录支持，配合 ROM 内置 DFU 引导程序使用。

功能：
- 检测 USB DFU 设备（STM32 BOOTLOADER）
- 通过串口命令触发应用进入 DFU 模式
- 使用 STM32_Programmer_CLI 通过 USB DFU 烧录固件
- 完整流程：发送 DFU 命令 → 等待设备枚举 → 烧录 → 验证

依赖：
- STM32_Programmer_CLI（ST 官方工具）
- pyserial（串口通信）

使用示例：
  python usb_dfu_flash.py --detect
  python usb_dfu_flash.py --flash --firmware project_led.hex
  python usb_dfu_flash.py --enter-dfu --port COM3
  python usb_dfu_flash.py --full --port COM3 --firmware project_led.hex
"""

from __future__ import annotations

import argparse
import io
import os
import re
import subprocess
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path

# 编码处理
if sys.stdout and hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
elif sys.stdout:
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

# ======================== 常量 ========================

DFU_CMD_HEADER = 0xAA
DFU_CMD_TAIL = 0x55
DFU_CMD_ID = 0x05  # SCOPE_CMD_DFU

# STM32 DFU 设备 USB VID:PID
STM32_DFU_VID_PID = "0483:df11"

# STM32_Programmer_CLI 默认路径搜索
DEFAULT_CLI_PATHS = [
    r"C:\Program Files\STMicroelectronics\STM32Cube\STM32CubeProgrammer\bin\STM32_Programmer_CLI.exe",
    r"C:\Program Files (x86)\STMicroelectronics\STM32Cube\STM32CubeProgrammer\bin\STM32_Programmer_CLI.exe",
]


@dataclass
class DFUResult:
    status: str  # success, failure, timeout
    summary: str
    step: str = ""
    evidence: list[str] = field(default_factory=list)


# ======================== 工具函数 ========================

def find_stm32_programmer_cli(cli_path: str | None = None) -> str | None:
    """查找 STM32_Programmer_CLI 可执行文件路径。"""
    if cli_path and Path(cli_path).exists():
        return cli_path

    # 检查 PATH
    try:
        result = subprocess.run(
            ["where", "STM32_Programmer_CLI.exe"],
            capture_output=True, text=True, timeout=10
        )
        if result.returncode == 0:
            return result.stdout.strip().split("\n")[0].strip()
    except (FileNotFoundError, subprocess.TimeoutExpired):
        pass

    # 搜索默认路径
    for path in DEFAULT_CLI_PATHS:
        if Path(path).exists():
            return path

    return None


def list_usb_devices() -> list[str]:
    """列出所有 USB 设备（调用 STM32_Programmer_CLI -l usb）。"""
    cli = find_stm32_programmer_cli()
    if not cli:
        return []

    try:
        result = subprocess.run(
            [cli, "-l", "usb"],
            capture_output=True, text=True, timeout=15
        )
        lines = result.stdout.strip().split("\n")
        return [line.strip() for line in lines if line.strip()]
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return []


def is_dfu_device_connected() -> bool:
    """检查是否有 STM32 DFU 设备连接。"""
    devices = list_usb_devices()
    for line in devices:
        if STM32_DFU_VID_PID in line.lower():
            return True
    return False


def send_dfu_command(port: str, baudrate: int = 115200) -> DFUResult:
    """通过串口发送 DFU 进入命令。

    命令帧格式：0xAA 0x55 0x05 XOR 0x55
    其中 XOR = 0x05（只有命令字节，无数据域）
    """
    try:
        import serial
    except ImportError:
        return DFUResult("failure", "需要安装 pyserial: pip install pyserial", step="导入")

    xor_val = DFU_CMD_ID  # XOR = CMD（无数据）
    cmd_frame = bytes([
        DFU_CMD_HEADER,  # 0xAA
        DFU_CMD_TAIL,    # 0x55
        DFU_CMD_ID,      # 0x05 (SCOPE_CMD_DFU)
        xor_val,         # XOR 校验
        DFU_CMD_TAIL,    # 0x55
    ])

    try:
        ser = serial.Serial(port, baudrate, timeout=2)
        ser.write(cmd_frame)
        ser.flush()
        time.sleep(0.1)
        ser.close()
        return DFUResult("success", f"DFU 命令已发送到 {port}", step="发送命令",
                         evidence=[f"发送帧: {cmd_frame.hex(' ').upper()}"])
    except serial.SerialException as e:
        return DFUResult("failure", f"串口错误: {e}", step="发送命令")


def wait_for_dfu_device(timeout: int = 10) -> DFUResult:
    """等待 STM32 DFU 设备枚举。"""
    print(f"⏳ 等待 DFU 设备枚举（超时 {timeout} 秒）...")
    start = time.time()

    while time.time() - start < timeout:
        if is_dfu_device_connected():
            elapsed = time.time() - start
            return DFUResult("success", f"DFU 设备已检测到（{elapsed:.1f}秒）", step="等待设备")
        time.sleep(0.5)

    return DFUResult("timeout", f"等待 DFU 设备超时（{timeout}秒）", step="等待设备")


def flash_via_dfu(firmware_path: str, cli_path: str | None = None,
                  verify: bool = True, reset: bool = True) -> DFUResult:
    """通过 USB DFU 烧录固件。

    Args:
        firmware_path: 固件文件路径（.hex 或 .bin）
        cli_path: STM32_Programmer_CLI 路径
        verify: 是否验证
        reset: 烧录后是否复位
    """
    cli = find_stm32_programmer_cli(cli_path)
    if not cli:
        return DFUResult("failure", "未找到 STM32_Programmer_CLI", step="环境检查",
                         evidence=["请安装 STM32CubeProgrammer 或通过 --cli 指定路径"])

    fw = Path(firmware_path)
    if not fw.exists():
        return DFUResult("failure", f"固件文件不存在: {firmware_path}", step="文件检查")

    # 构建命令
    cmd = [cli, "-c", "port=USB"]
    cmd.extend(["-w", str(fw.resolve())])

    if verify:
        cmd.append("-v")

    if reset:
        cmd.append("-rst")

    cmd_str = " ".join(cmd)
    print(f"🔥 烧录命令: {cmd_str}")

    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
    except subprocess.TimeoutExpired:
        return DFUResult("failure", "烧录超时（60秒）", step="烧录",
                         evidence=["STM32_Programmer_CLI 执行超时"])
    except FileNotFoundError:
        return DFUResult("failure", f"未找到 STM32_Programmer_CLI: {cli}", step="烧录")

    output = result.stdout + result.stderr
    evidence = [line.strip() for line in output.split("\n") if line.strip()]

    if result.returncode == 0:
        # 检查成功标志
        if "verified" in output.lower() or "download verified" in output.lower():
            return DFUResult("success", "USB DFU 烧录成功", step="烧录", evidence=evidence)
        elif "error" not in output.lower():
            return DFUResult("success", "USB DFU 烧录完成", step="烧录", evidence=evidence)

    return DFUResult("failure", "USB DFU 烧录失败", step="烧录",
                     evidence=evidence[:20])


# ======================== 组合流程 ========================

def full_dfu_workflow(port: str, firmware_path: str, baudrate: int = 115200,
                      timeout: int = 10, cli_path: str | None = None) -> DFUResult:
    """完整 DFU 烧录流程：发送命令 → 等待设备 → 烧录 → 验证。"""
    print("=" * 50)
    print("🚀 USB DFU 完整烧录流程")
    print("=" * 50)

    # 步骤 1：检查固件文件
    fw = Path(firmware_path)
    if not fw.exists():
        return DFUResult("failure", f"固件文件不存在: {firmware_path}", step="文件检查")

    print(f"\n📦 固件: {fw.name} ({fw.stat().st_size / 1024:.1f} KB)")

    # 步骤 2：检查当前是否有 DFU 设备
    if is_dfu_device_connected():
        print("✅ 已检测到 DFU 设备，直接烧录")
    else:
        print("📡 未检测到 DFU 设备，尝试通过串口进入 DFU 模式...")

        # 步骤 3：发送 DFU 命令
        result = send_dfu_command(port, baudrate)
        if result.status != "success":
            return result
        print(f"✅ {result.summary}")

        # 步骤 4：等待设备枚举
        result = wait_for_dfu_device(timeout)
        if result.status != "success":
            return result
        print(f"✅ {result.summary}")

    # 步骤 5：烧录
    print("\n🔥 开始烧录...")
    result = flash_via_dfu(firmware_path, cli_path)
    if result.status == "success":
        print(f"✅ {result.summary}")
    else:
        print(f"❌ {result.summary}")

    return result


# ======================== 报告 ========================

def print_detect_report() -> None:
    """打印 DFU 设备检测报告。"""
    print("\n📊 USB DFU 设备检测：")

    cli = find_stm32_programmer_cli()
    if cli:
        print(f"  ✅ STM32_Programmer_CLI: {cli}")
    else:
        print("  ❌ 未找到 STM32_Programmer_CLI")
        print("     请安装 STM32CubeProgrammer: https://www.st.com/en/development-tools/stm32cubeprog.html")
        return

    devices = list_usb_devices()
    if not devices:
        print("  ⚠️ 未检测到 USB DFU 设备")
        print("     提示：需要先将 MCU 进入 DFU 模式")
        return

    print("  📱 USB 设备列表:")
    for dev in devices:
        if STM32_DFU_VID_PID in dev.lower():
            print(f"    ✅ {dev}")
        else:
            print(f"    📎 {dev}")


def print_flash_report(result: DFUResult) -> None:
    """打印烧录结果报告。"""
    icon = "✅" if result.status == "success" else "❌" if result.status == "failure" else "⏰"
    print(f"\n📊 烧录结果: {icon} {result.summary}")
    if result.step:
        print(f"  失败阶段: {result.step}")
    if result.evidence:
        print("\n📝 详细信息:")
        for line in result.evidence[:15]:
            print(f"  {line}")


# ======================== CLI ========================

def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="USB DFU 烧录工具",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  %(prog)s --detect                           # 检测 DFU 设备
  %(prog)s --enter-dfu --port COM3            # 通过串口进入 DFU
  %(prog)s --flash --firmware app.hex         # 烧录固件（需已处于 DFU 模式）
  %(prog)s --full --port COM3 --firmware app.hex  # 完整流程
        """,
    )
    parser.add_argument("--detect", action="store_true", help="检测 USB DFU 设备")
    parser.add_argument("--enter-dfu", action="store_true", help="通过串口发送 DFU 进入命令")
    parser.add_argument("--flash", action="store_true", help="通过 USB DFU 烧录固件")
    parser.add_argument("--full", action="store_true", help="完整流程（进入 DFU → 烧录）")
    parser.add_argument("--port", help="串口号（如 COM3）")
    parser.add_argument("--baudrate", type=int, default=115200, help="串口波特率（默认 115200）")
    parser.add_argument("--firmware", help="固件文件路径（.hex 或 .bin）")
    parser.add_argument("--cli", help="STM32_Programmer_CLI 路径")
    parser.add_argument("--timeout", type=int, default=10, help="等待 DFU 设备超时（秒）")
    parser.add_argument("--no-verify", action="store_true", help="不验证烧录")
    parser.add_argument("--no-reset", action="store_true", help="烧录后不复位")
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()

    if not any([args.detect, args.enter_dfu, args.flash, args.full]):
        print("❌ 请指定操作：--detect / --enter-dfu / --flash / --full")
        return 1

    # 检测模式
    if args.detect:
        print_detect_report()
        return 0

    # 进入 DFU 模式
    if args.enter_dfu:
        if not args.port:
            print("❌ --enter-dfu 需要指定 --port")
            return 1
        result = send_dfu_command(args.port, args.baudrate)
        print(f"{'✅' if result.status == 'success' else '❌'} {result.summary}")
        return 0 if result.status == "success" else 1

    # 烧录模式
    if args.flash:
        if not args.firmware:
            print("❌ --flash 需要指定 --firmware")
            return 1
        result = flash_via_dfu(args.firmware, args.cli,
                               verify=not args.no_verify,
                               reset=not args.no_reset)
        print_flash_report(result)
        return 0 if result.status == "success" else 1

    # 完整流程
    if args.full:
        if not args.port:
            print("❌ --full 需要指定 --port")
            return 1
        if not args.firmware:
            print("❌ --full 需要指定 --firmware")
            return 1
        result = full_dfu_workflow(
            args.port, args.firmware, args.baudrate,
            args.timeout, args.cli
        )
        print_flash_report(result)
        return 0 if result.status == "success" else 1

    return 1


if __name__ == "__main__":
    sys.exit(main())
