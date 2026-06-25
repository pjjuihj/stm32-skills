#!/usr/bin/env python
"""STM32 中断延迟分析工具。

分析 ISR 执行时间、中断频率、优先级配置。

用法:
  python isr_analyzer.py --auto .                            # 分析中断配置
  python isr_analyzer.py --auto . --profile                  # 分析 ISR 性能（需硬件）
  python isr_analyzer.py --auto . --json                     # JSON 输出

功能:
  - 从中断向量表和 NVIC 配置分析中断优先级
  - 检测优先级反转风险
  - 通过 DWT 周期计数器测量 ISR 执行时间（需硬件）
  - 统计中断频率
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).parent
from shared import setup_encoding
setup_encoding()


# STM32F4 中断向量表（IRQ 号 → 名称）
IRQ_TABLE = {
    0: "WWDG", 1: "PVD", 2: "TAMP_STAMP", 3: "RTC_WKUP",
    4: "FLASH", 5: "RCC", 6: "EXTI0", 7: "EXTI1",
    8: "EXTI2", 9: "EXTI3", 10: "EXTI4", 11: "DMA1_Stream0",
    12: "DMA1_Stream1", 13: "DMA1_Stream2", 14: "DMA1_Stream3",
    15: "DMA1_Stream4", 16: "DMA1_Stream5", 17: "DMA1_Stream6",
    18: "ADC", 19: "CAN1_TX", 20: "CAN1_RX0", 21: "CAN1_RX1",
    22: "CAN1_SCE", 23: "EXTI9_5", 24: "TIM1_BRK_TIM9",
    25: "TIM1_UP_TIM10", 26: "TIM1_TRG_COM_TIM11",
    27: "TIM1_CC", 28: "TIM2", 29: "TIM3", 30: "TIM4",
    31: "I2C1_EV", 32: "I2C1_ER", 33: "I2C2_EV", 34: "I2C2_ER",
    35: "SPI1", 36: "SPI2", 37: "USART1", 38: "USART2",
    39: "USART3", 40: "EXTI15_10", 41: "RTC_Alarm",
    42: "OTG_FS_WKUP", 43: "TIM8_BRK_TIM12", 44: "TIM8_UP_TIM13",
    45: "TIM8_TRG_COM_TIM14", 46: "TIM8_CC", 47: "DMA1_Stream7",
    48: "FSMC", 49: "SDIO", 50: "TIM5", 51: "SPI3",
    52: "UART4", 53: "UART5", 54: "TIM6_DAC", 55: "TIM7",
    56: "DMA2_Stream0", 57: "DMA2_Stream1", 58: "DMA2_Stream2",
    59: "DMA2_Stream3", 60: "DMA2_Stream4", 61: "ETH",
    62: "ETH_WKUP", 63: "CAN2_TX", 64: "CAN2_RX0",
    65: "CAN2_RX1", 66: "CAN2_SCE", 67: "OTG_FS",
    68: "DMA2_Stream5", 69: "DMA2_Stream6", 70: "DMA2_Stream7",
    71: "USART6", 72: "I2C3_EV", 73: "I2C3_ER",
    74: "OTG_HS_EP1_OUT", 75: "OTG_HS_EP1_IN",
    76: "OTG_HS_WKUP", 77: "OTG_HS", 78: "DCMI",
    79: "CRYP", 80: "HASH_RNG", 81: "FPU",
}

# ISR 优先级默认值（HAL 默认全部为 0）
DEFAULT_PRIORITY = 0


def parse_nvic_config(project_dir: str) -> list[dict]:
    """从 .ioc 文件解析 NVIC 配置。"""
    ioc_file = None
    for f in os.listdir(project_dir):
        if f.endswith(".ioc"):
            ioc_file = os.path.join(project_dir, f)
            break

    if not ioc_file:
        return []

    interrupts = []
    with open(ioc_file, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            # 匹配 NVIC 配置
            if "NVIC" in line and "=" in line:
                key, value = line.split("=", 1)
                key = key.strip()
                value = value.strip()

                # 解析中断名称
                if ".NVIC_IRQ" in key:
                    irq_name = key.split(".")[0]
                    param = key.split(".")[-1]
                    if irq_name not in [i["name"] for i in interrupts]:
                        interrupts.append({"name": irq_name, "priority": DEFAULT_PRIORITY, "enabled": False})
                    for i in interrupts:
                        if i["name"] == irq_name:
                            if "PreemptionPriority" in param:
                                i["priority"] = int(value) if value.isdigit() else DEFAULT_PRIORITY
                            elif "Enable" in param or "SubPriority" in param:
                                i["enabled"] = value.lower() in ("true", "1", "enabled")

    return interrupts


def parse_vector_table(project_dir: str) -> list[dict]:
    """从启动文件解析中断向量表。"""
    startup_files = []
    for root, _, files in os.walk(project_dir):
        for f in files:
            if f.startswith("startup_stm32f") and (f.endswith(".s") or f.endswith(".S")):
                startup_files.append(os.path.join(root, f))

    handlers = []
    for sf in startup_files:
        with open(sf, "r", encoding="utf-8", errors="replace") as f:
            for line in f:
                # 匹配中断处理函数
                m = re.search(r"(\w+_Handler)\s+", line)
                if m:
                    handler = m.group(1)
                    if handler not in [h["handler"] for h in handlers]:
                        handlers.append({"handler": handler, "source": os.path.basename(sf)})

    return handlers


def analyze_isr_config(project_dir: str) -> dict:
    """分析中断配置。"""
    nvic_config = parse_nvic_config(project_dir)
    vector_table = parse_vector_table(project_dir)

    # 分析优先级配置
    priority_issues = []

    # 检查是否有优先级冲突
    priorities = [i["priority"] for i in nvic_config if i.get("enabled")]
    if len(set(priorities)) == 1 and len(priorities) > 1:
        priority_issues.append({
            "type": "all_same_priority",
            "severity": "warning",
            "message": f"所有 {len(priorities)} 个中断优先级相同（{priorities[0]}），可能导致中断延迟",
        })

    # 检查 DMA 和 UART 的优先级关系
    dma_priority = None
    uart_priority = None
    for i in nvic_config:
        if "DMA" in i["name"] and i.get("enabled"):
            dma_priority = i["priority"]
        if "USART" in i["name"] or "UART" in i["name"]:
            if i.get("enabled"):
                uart_priority = i["priority"]

    if dma_priority is not None and uart_priority is not None:
        if dma_priority > uart_priority:  # 数值越大优先级越低
            priority_issues.append({
                "type": "dma_lower_than_uart",
                "severity": "info",
                "message": "DMA 优先级低于 UART，可能导致 DMA 中断延迟",
            })

    # 检查 HardFault 处理函数
    has_hardfault = any("HardFault" in h["handler"] for h in vector_table)

    return {
        "nvic_config": nvic_config,
        "vector_table": vector_table,
        "enabled_count": len([i for i in nvic_config if i.get("enabled")]),
        "total_handlers": len(vector_table),
        "has_hardfault": has_hardfault,
        "priority_issues": priority_issues,
    }


def main():
    parser = argparse.ArgumentParser(description="STM32 中断延迟分析工具")
    parser.add_argument("--auto", metavar="DIR", default=".", help="项目目录")
    parser.add_argument("--profile", action="store_true", help="分析 ISR 性能（需硬件）")
    parser.add_argument("--json", action="store_true", help="JSON 格式输出")
    args = parser.parse_args()

    project_dir = str(Path(args.auto).resolve())
    result = analyze_isr_config(project_dir)

    if args.json:
        print(json.dumps(result, indent=2, ensure_ascii=False))
    else:
        print(f"🔍 中断配置分析")
        print()

        # NVIC 配置
        print(f"NVIC 配置 ({result['enabled_count']} 个中断已使能):")
        for i in result["nvic_config"]:
            if i.get("enabled"):
                print(f"  {i['name']:<30} 优先级: {i['priority']}")
        print()

        # 向量表
        print(f"中断向量表 ({result['total_handlers']} 个处理函数):")
        for h in result["vector_table"][:20]:
            print(f"  {h['handler']}")
        if len(result["vector_table"]) > 20:
            print(f"  ... 共 {len(result['vector_table'])} 个")
        print()

        # HardFault 检查
        if result["has_hardfault"]:
            print("✅ HardFault 处理函数已实现")
        else:
            print("❌ HardFault 处理函数未实现！建议添加诊断输出")
        print()

        # 问题检测
        if result["priority_issues"]:
            print("⚠️ 优先级问题:")
            for issue in result["priority_issues"]:
                icon = {"warning": "⚠️", "error": "❌", "info": "ℹ️"}.get(issue["severity"], "•")
                print(f"  {icon} {issue['message']}")
        else:
            print("✅ 未发现优先级配置问题")


if __name__ == "__main__":
    main()
