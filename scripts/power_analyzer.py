#!/usr/bin/env python
"""STM32 功耗分析工具。

根据 .ioc 配置分析外设时钟使能状态，给出低功耗模式建议。

用法:
  python power_analyzer.py --auto .                          # 分析功耗
  python power_analyzer.py --auto . --mode sleep             # 分析 Sleep 模式
  python power_analyzer.py --auto . --json                   # JSON 输出

功能:
  - 分析当前外设时钟使能状态
  - 识别可以关闭的外设时钟
  - 推荐低功耗模式（Sleep/Stop/Standby）
  - 估算各模式下的功耗
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).parent
from shared import setup_encoding
setup_encoding()


# STM32F4 外设功耗估算（mA，典型值 @3.3V）
PERIPHERAL_POWER = {
    "GPIOA": 0.5, "GPIOB": 0.5, "GPIOC": 0.5, "GPIOD": 0.5, "GPIOE": 0.5,
    "USART1": 2.0, "USART2": 1.5, "USART3": 1.5, "UART4": 1.5, "UART5": 1.5, "USART6": 2.0,
    "TIM1": 1.0, "TIM2": 0.8, "TIM3": 0.8, "TIM4": 0.8, "TIM5": 0.8,
    "TIM6": 0.3, "TIM7": 0.3, "TIM8": 1.0, "TIM9": 0.5, "TIM10": 0.5,
    "TIM11": 0.5, "TIM12": 0.5, "TIM13": 0.5, "TIM14": 0.5,
    "ADC1": 2.0, "ADC2": 2.0, "ADC3": 2.0,
    "DAC": 1.0,
    "SPI1": 2.0, "SPI2": 1.5, "SPI3": 1.5,
    "I2C1": 1.0, "I2C2": 1.0, "I2C3": 1.0,
    "DMA1": 1.0, "DMA2": 1.0,
    "USB_OTG_FS": 10.0, "USB_OTG_HS": 15.0,
    "ETH": 20.0,
    "SDIO": 5.0,
    "FSMC": 3.0,
    "RNG": 0.5,
    "CRC": 0.2,
}

# STM32F4 低功耗模式特性
LOW_POWER_MODES = {
    "sleep": {
        "name": "Sleep",
        "wakeup": "任意中断",
        "wakeup_time": "立即",
        "sram": "保持",
        "peripherals": "全部保持",
        "current_ua": 2000,  # ~2mA @168MHz
        "desc": "CPU 停止，外设继续运行。最简单的低功耗模式。",
    },
    "stop": {
        "name": "Stop",
        "wakeup": "EXTI 中断",
        "wakeup_time": "~5us",
        "sram": "保持",
        "peripherals": "关闭（除 RTC、IWDG）",
        "current_ua": 100,  # ~100uA
        "desc": "所有时钟停止，电压调节器低功耗。适合长时间等待。",
    },
    "standby": {
        "name": "Standby",
        "wakeup": "WKUP 引脚 / RTC / IWDG",
        "wakeup_time": "~50us",
        "sram": "丢失",
        "peripherals": "全部关闭",
        "current_ua": 2,  # ~2uA
        "desc": "最低功耗，但 SRAM 内容丢失。适合超低功耗应用。",
    },
}


def parse_ioc_config(project_dir: str) -> dict:
    """解析 .ioc 文件中的外设配置。"""
    ioc_file = None
    for f in os.listdir(project_dir):
        if f.endswith(".ioc"):
            ioc_file = os.path.join(project_dir, f)
            break

    if not ioc_file:
        return {}

    config = {"peripherals": {}, "pins": {}}

    with open(ioc_file, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue

            if "=" in line:
                key, value = line.split("=", 1)
                key = key.strip()
                value = value.strip()

                # 外设使能
                if key.endswith(".Mode"):
                    periph = key.split(".")[0]
                    config["peripherals"][periph] = value

                # 引脚配置
                if "GPIO" in key and "Signal" in key:
                    config["pins"][key] = value

    return config


def analyze_power(project_dir: str) -> dict:
    """分析项目功耗。"""
    config = parse_ioc_config(project_dir)

    enabled_peripherals = []
    total_power = 0.0

    for periph, mode in config.get("peripherals", {}).items():
        if mode and mode != "Disable" and mode != "disable":
            power = PERIPHERAL_POWER.get(periph, 0.5)
            enabled_peripherals.append({
                "name": periph,
                "mode": mode,
                "power_ma": power,
            })
            total_power += power

    # 基础功耗（CPU、Flash、SRAM）
    base_power = 30.0  # ~30mA @168MHz（CPU + Flash + SRAM）
    total_power += base_power

    # 分析低功耗模式建议
    suggestions = []

    # 检查是否有外设需要持续运行
    has_uart = any("USART" in p["name"] or "UART" in p["name"] for p in enabled_peripherals)
    has_adc = any("ADC" in p["name"] for p in enabled_peripherals)
    has_tim = any("TIM" in p["name"] for p in enabled_peripherals)

    if not has_uart and not has_adc and not has_tim:
        suggestions.append({
            "mode": "stop",
            "reason": "没有需要持续运行的外设，Stop 模式最佳",
            "savings_ma": total_power - 0.1,
        })
    elif has_uart and not has_adc:
        suggestions.append({
            "mode": "sleep",
            "reason": "UART 需要持续接收，Sleep 模式保持外设运行",
            "savings_ma": total_power - 2.0,
        })
    else:
        suggestions.append({
            "mode": "sleep",
            "reason": "有外设需要运行，Sleep 模式最简单",
            "savings_ma": total_power - 2.0,
        })

    # 时钟优化建议
    clock_suggestions = []
    if total_power > 50:
        clock_suggestions.append("考虑降低系统时钟频率（168MHz → 72MHz，功耗减半）")
    if has_adc and not any("DMA" in p["name"] for p in enabled_peripherals):
        clock_suggestions.append("ADC 使用 DMA 可降低 CPU 占用，间接降低功耗")

    return {
        "enabled_peripherals": enabled_peripherals,
        "total_power_ma": total_power,
        "base_power_ma": base_power,
        "peripheral_power_ma": total_power - base_power,
        "low_power_modes": LOW_POWER_MODES,
        "suggestions": suggestions,
        "clock_suggestions": clock_suggestions,
    }


def main():
    parser = argparse.ArgumentParser(description="STM32 功耗分析工具")
    parser.add_argument("--auto", metavar="DIR", default=".", help="项目目录")
    parser.add_argument("--mode", choices=["sleep", "stop", "standby"], help="分析指定低功耗模式")
    parser.add_argument("--json", action="store_true", help="JSON 格式输出")
    args = parser.parse_args()

    project_dir = str(Path(args.auto).resolve())
    result = analyze_power(project_dir)

    if args.json:
        print(json.dumps(result, indent=2, ensure_ascii=False))
    else:
        print(f"⚡ 功耗分析报告")
        print()

        # 已使能外设
        print(f"已使能外设 ({len(result['enabled_peripherals'])} 个):")
        for p in result["enabled_peripherals"]:
            print(f"  {p['name']:<20} {p['mode']:<15} ~{p['power_ma']:.1f} mA")
        print()

        # 功耗汇总
        print(f"功耗估算:")
        print(f"  基础功耗（CPU+Flash+SRAM）: ~{result['base_power_ma']:.0f} mA")
        print(f"  外设功耗:                   ~{result['peripheral_power_ma']:.1f} mA")
        print(f"  总功耗:                     ~{result['total_power_ma']:.1f} mA")
        print()

        # 低功耗模式建议
        print(f"低功耗模式建议:")
        for s in result["suggestions"]:
            mode_info = result["low_power_modes"][s["mode"]]
            print(f"  推荐: {mode_info['name']}")
            print(f"  原因: {s['reason']}")
            print(f"  节省: ~{s['savings_ma']:.1f} mA")
            print(f"  唤醒: {mode_info['wakeup']}")
            print(f"  唤醒时间: {mode_info['wakeup_time']}")
            print()

        # 指定模式详情
        if args.mode:
            mode_info = result["low_power_modes"][args.mode]
            print(f"模式详情: {mode_info['name']}")
            print(f"  {mode_info['desc']}")
            print(f"  电流: ~{mode_info['current_ua']} uA")
            print(f"  SRAM: {mode_info['sram']}")
            print(f"  外设: {mode_info['peripherals']}")
            print()

        # 时钟优化
        if result["clock_suggestions"]:
            print(f"时钟优化建议:")
            for s in result["clock_suggestions"]:
                print(f"  • {s}")


if __name__ == "__main__":
    main()
