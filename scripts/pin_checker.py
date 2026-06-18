#!/usr/bin/env python
"""STM32 引脚冲突检测工具。

检查 .ioc 文件中的引脚配置是否存在冲突。

功能：
- 检测引脚重复配置
- 检测引脚功能冲突
- 检测引脚复用冲突

使用示例：
  python pin_checker.py --ioc project.ioc
  python pin_checker.py --ioc project.ioc --json
"""

from __future__ import annotations

import argparse
import io
import json
import os
import re
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any

# 编码处理
if sys.stdout and hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

# ======================== 引脚配置解析 ========================

def parse_ioc_pins(ioc_path: str) -> dict[str, Any]:
    """解析 .ioc 文件中的引脚配置"""
    result = {
        "pins": {},
        "peripherals": {},
        "error": None
    }

    if not os.path.exists(ioc_path):
        result["error"] = f"IOC file not found: {ioc_path}"
        return result

    try:
        with open(ioc_path, "r", encoding="utf-8", errors="replace") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#"):
                    continue

                if "=" in line:
                    key, value = line.split("=", 1)
                    key = key.strip()
                    value = value.strip()

                    # 解析引脚配置
                    if key.startswith("PA") or key.startswith("PB") or key.startswith("PC") or \
                       key.startswith("PD") or key.startswith("PE") or key.startswith("PF") or \
                       key.startswith("PG") or key.startswith("PH") or key.startswith("PI"):
                        pin_name = key.split(".")[0]
                        param = key.split(".")[1] if "." in key else ""

                        if pin_name not in result["pins"]:
                            result["pins"][pin_name] = {}

                        if param == "Signal":
                            result["pins"][pin_name]["signal"] = value
                        elif param == "Mode":
                            result["pins"][pin_name]["mode"] = value
                        elif param == "GPIO_Label":
                            result["pins"][pin_name]["label"] = value
                        elif param == "GPIO_Mode":
                            result["pins"][pin_name]["gpio_mode"] = value
                        elif param == "GPIO_Speed":
                            result["pins"][pin_name]["gpio_speed"] = value
                        elif param == "GPIO_PuPd":
                            result["pins"][pin_name]["gpio_pupd"] = value

                    # 解析外设配置
                    elif key.startswith("Mcu.IP"):
                        ip_index = key.split("Mcu.IP")[1]
                        if ip_index.isdigit():
                            result["peripherals"][ip_index] = value

    except Exception as e:
        result["error"] = str(e)

    return result

# ======================== 冲突检测 ========================

def check_pin_conflicts(pins: dict[str, Any]) -> list[dict[str, Any]]:
    """检查引脚冲突"""
    conflicts = []

    # 检查引脚重复配置
    pin_usage = defaultdict(list)
    for pin_name, config in pins.items():
        if "signal" in config:
            pin_usage[pin_name].append({
                "signal": config["signal"],
                "mode": config.get("mode", ""),
                "label": config.get("label", "")
            })

    # 检测重复配置
    for pin_name, usages in pin_usage.items():
        if len(usages) > 1:
            signals = [u["signal"] for u in usages]
            conflicts.append({
                "type": "duplicate_pin",
                "pin": pin_name,
                "signals": signals,
                "description": f"引脚 {pin_name} 被多个信号使用: {', '.join(signals)}"
            })

    # 检测功能冲突
    for pin_name, config in pins.items():
        if "signal" in config:
            signal = config["signal"]

            # 检查 GPIO 与外设冲突
            if "GPIO" in signal and ("USART" in signal or "SPI" in signal or "I2C" in signal):
                conflicts.append({
                    "type": "function_conflict",
                    "pin": pin_name,
                    "signal": signal,
                    "description": f"引脚 {pin_name} 同时配置为 GPIO 和外设功能"
                })

    return conflicts

def check_peripheral_conflicts(pins: dict[str, Any]) -> list[dict[str, Any]]:
    """检查外设冲突"""
    conflicts = []

    # 检查 UART 引脚冲突
    uart_pins = {}
    for pin_name, config in pins.items():
        if "signal" in config and "USART" in config["signal"]:
            signal = config["signal"]
            if "TX" in signal:
                uart_name = signal.replace("_TX", "")
                if uart_name in uart_pins:
                    conflicts.append({
                        "type": "uart_conflict",
                        "uart": uart_name,
                        "pins": [uart_pins[uart_name], pin_name],
                        "description": f"UART {uart_name} 有多个 TX 引脚"
                    })
                else:
                    uart_pins[uart_name] = pin_name

    return conflicts

# ======================== CLI ========================

def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="STM32 引脚冲突检测工具",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  %(prog)s --ioc project.ioc                    # 检查引脚冲突
  %(prog)s --ioc project.ioc --json             # JSON 格式输出
        """,
    )

    parser.add_argument("--ioc", required=True, help="IOC 文件路径")
    parser.add_argument("--json", action="store_true", help="输出 JSON 格式")

    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()

    print(f"🔍 检查引脚冲突: {args.ioc}")
    print()

    # 解析 IOC 文件
    ioc_info = parse_ioc_pins(args.ioc)
    if ioc_info["error"]:
        print(f"❌ 错误: {ioc_info['error']}")
        return 1

    # 检查引脚冲突
    pin_conflicts = check_pin_conflicts(ioc_info["pins"])
    peripheral_conflicts = check_peripheral_conflicts(ioc_info["pins"])

    all_conflicts = pin_conflicts + peripheral_conflicts

    # 输出结果
    if args.json:
        result = {
            "pins": ioc_info["pins"],
            "conflicts": all_conflicts
        }
        print(json.dumps(result, indent=2, ensure_ascii=False))
    else:
        print(f"📊 引脚配置:")
        print(f"   总引脚数: {len(ioc_info['pins'])}")
        print()

        if all_conflicts:
            print(f"⚠️ 发现 {len(all_conflicts)} 个冲突:")
            for i, conflict in enumerate(all_conflicts, 1):
                print(f"   {i}. [{conflict['type']}] {conflict['description']}")
        else:
            print("✅ 未发现引脚冲突")

    return 0


if __name__ == "__main__":
    sys.exit(main())
