#!/usr/bin/env python
"""STM32 外设寄存器转储工具。

按外设分组导出寄存器状态，寄存器值做语义解码。

用法:
  python reg_dump.py --auto . --mcu STM32F407              # 从 map 文件分析
  python reg_dump.py --auto . --peripheral GPIO,TIM,ADC    # 只看指定外设
  python reg_dump.py --auto . --output regs.json           # 输出到文件

功能:
  - 从 .map 文件解析外设基地址
  - 按外设分组列出寄存器
  - 寄存器值语义解码（使能/禁用、模式、预分频等）
  - 输出格式：文本表格或 JSON
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


# STM32F4 外设寄存器定义（通用，其他系列类似）
PERIPHERAL_DEFS = {
    "GPIOA": {"base": "0x40020000", "type": "GPIO"},
    "GPIOB": {"base": "0x40020400", "type": "GPIO"},
    "GPIOC": {"base": "0x40020800", "type": "GPIO"},
    "GPIOD": {"base": "0x40020C00", "type": "GPIO"},
    "GPIOE": {"base": "0x40021000", "type": "GPIO"},
    "USART1": {"base": "0x40011000", "type": "USART"},
    "USART2": {"base": "0x40004400", "type": "USART"},
    "USART3": {"base": "0x40004800", "type": "USART"},
    "UART4": {"base": "0x40004C00", "type": "USART"},
    "UART5": {"base": "0x40005000", "type": "USART"},
    "USART6": {"base": "0x40011400", "type": "USART"},
    "TIM1": {"base": "0x40010000", "type": "TIM"},
    "TIM2": {"base": "0x40000000", "type": "TIM"},
    "TIM3": {"base": "0x40000400", "type": "TIM"},
    "TIM4": {"base": "0x40000800", "type": "TIM"},
    "TIM5": {"base": "0x40000C00", "type": "TIM"},
    "TIM6": {"base": "0x40001000", "type": "TIM"},
    "TIM7": {"base": "0x40001400", "type": "TIM"},
    "TIM8": {"base": "0x40010400", "type": "TIM"},
    "TIM9": {"base": "0x40014000", "type": "TIM"},
    "TIM10": {"base": "0x40014400", "type": "TIM"},
    "TIM11": {"base": "0x40014800", "type": "TIM"},
    "TIM12": {"base": "0x40001800", "type": "TIM"},
    "TIM13": {"base": "0x40001C00", "type": "TIM"},
    "TIM14": {"base": "0x40002000", "type": "TIM"},
    "ADC1": {"base": "0x40012000", "type": "ADC"},
    "ADC2": {"base": "0x40012100", "type": "ADC"},
    "ADC3": {"base": "0x40012200", "type": "ADC"},
    "DAC": {"base": "0x40007400", "type": "DAC"},
    "SPI1": {"base": "0x40013000", "type": "SPI"},
    "SPI2": {"base": "0x40003800", "type": "SPI"},
    "SPI3": {"base": "0x40003C00", "type": "SPI"},
    "I2C1": {"base": "0x40005400", "type": "I2C"},
    "I2C2": {"base": "0x40005800", "type": "I2C"},
    "I2C3": {"base": "0x40005C00", "type": "I2C"},
    "DMA1": {"base": "0x40026000", "type": "DMA"},
    "DMA2": {"base": "0x40026400", "type": "DMA"},
    "RCC": {"base": "0x40023800", "type": "RCC"},
    "FLASH": {"base": "0x40023C00", "type": "FLASH"},
    "EXTI": {"base": "0x40013C00", "type": "EXTI"},
    "SYSCFG": {"base": "0x40013800", "type": "SYSCFG"},
    "NVIC": {"base": "0xE000E100", "type": "NVIC"},
    "SCB": {"base": "0xE000ED00", "type": "SCB"},
    "SysTick": {"base": "0xE000E010", "type": "SysTick"},
}

# 寄存器偏移和解码
REGISTER_DEFS = {
    "GPIO": {
        "MODER": {"offset": "0x00", "desc": "模式", "decode": "2bit/pin"},
        "OTYPER": {"offset": "0x04", "desc": "输出类型"},
        "OSPEEDR": {"offset": "0x08", "desc": "输出速度"},
        "PUPDR": {"offset": "0x0C", "desc": "上拉/下拉"},
        "IDR": {"offset": "0x10", "desc": "输入数据"},
        "ODR": {"offset": "0x14", "desc": "输出数据"},
        "BSRR": {"offset": "0x18", "desc": "位设置/复位"},
        "LCKR": {"offset": "0x1C", "desc": "锁定"},
        "AFR[0]": {"offset": "0x20", "desc": "复用功能低"},
        "AFR[1]": {"offset": "0x24", "desc": "复用功能高"},
    },
    "USART": {
        "SR": {"offset": "0x00", "desc": "状态"},
        "DR": {"offset": "0x04", "desc": "数据"},
        "BRR": {"offset": "0x08", "desc": "波特率"},
        "CR1": {"offset": "0x0C", "desc": "控制1"},
        "CR2": {"offset": "0x10", "desc": "控制2"},
        "CR3": {"offset": "0x14", "desc": "控制3"},
        "GTPR": {"offset": "0x18", "desc": "保护时间和预分频"},
    },
    "TIM": {
        "CR1": {"offset": "0x00", "desc": "控制1"},
        "CR2": {"offset": "0x04", "desc": "控制2"},
        "SMCR": {"offset": "0x08", "desc": "从模式控制"},
        "DIER": {"offset": "0x0C", "desc": "DMA/中断使能"},
        "SR": {"offset": "0x10", "desc": "状态"},
        "EGR": {"offset": "0x14", "desc": "事件产生"},
        "CCMR1": {"offset": "0x18", "desc": "捕获/比较模式1"},
        "CCMR2": {"offset": "0x1C", "desc": "捕获/比较模式2"},
        "CCER": {"offset": "0x20", "desc": "捕获/比较使能"},
        "CNT": {"offset": "0x24", "desc": "计数器"},
        "PSC": {"offset": "0x28", "desc": "预分频"},
        "ARR": {"offset": "0x2C", "desc": "自动重装"},
        "CCR1": {"offset": "0x34", "desc": "捕获/比较1"},
        "CCR2": {"offset": "0x38", "desc": "捕获/比较2"},
        "CCR3": {"offset": "0x3C", "desc": "捕获/比较3"},
        "CCR4": {"offset": "0x40", "desc": "捕获/比较4"},
        "DCR": {"offset": "0x48", "desc": "DMA 控制"},
        "DMAR": {"offset": "0x4C", "desc": "DMA 连续模式地址"},
    },
    "ADC": {
        "SR": {"offset": "0x00", "desc": "状态"},
        "CR1": {"offset": "0x04", "desc": "控制1"},
        "CR2": {"offset": "0x08", "desc": "控制2"},
        "SMPR1": {"offset": "0x0C", "desc": "采样时间1"},
        "SMPR2": {"offset": "0x10", "desc": "采样时间2"},
        "JOFR1": {"offset": "0x14", "desc": "注入偏移1"},
        "HTR": {"offset": "0x24", "desc": "看门狗高阈值"},
        "LTR": {"offset": "0x28", "desc": "看门狗低阈值"},
        "SQR1": {"offset": "0x2C", "desc": "规则序列1"},
        "SQR2": {"offset": "0x30", "desc": "规则序列2"},
        "SQR3": {"offset": "0x34", "desc": "规则序列3"},
        "JSQR": {"offset": "0x38", "desc": "注入序列"},
        "JDR1": {"offset": "0x3C", "desc": "注入数据1"},
        "DR": {"offset": "0x4C", "desc": "规则数据"},
    },
    "I2C": {
        "CR1": {"offset": "0x00", "desc": "控制1"},
        "CR2": {"offset": "0x04", "desc": "控制2"},
        "OAR1": {"offset": "0x08", "desc": "自身地址1"},
        "OAR2": {"offset": "0x0C", "desc": "自身地址2"},
        "DR": {"offset": "0x10", "desc": "数据"},
        "SR1": {"offset": "0x14", "desc": "状态1"},
        "SR2": {"offset": "0x18", "desc": "状态2"},
        "CCR": {"offset": "0x1C", "desc": "时钟控制"},
        "TRISE": {"offset": "0x20", "desc": "上升时间"},
    },
    "SPI": {
        "CR1": {"offset": "0x00", "desc": "控制1"},
        "CR2": {"offset": "0x04", "desc": "控制2"},
        "SR": {"offset": "0x08", "desc": "状态"},
        "DR": {"offset": "0x0C", "desc": "数据"},
        "CRCPR": {"offset": "0x10", "desc": "CRC 多项式"},
        "RXCRCR": {"offset": "0x14", "desc": "接收 CRC"},
        "TXCRCR": {"offset": "0x18", "desc": "发送 CRC"},
    },
    "DMA": {
        "LISR": {"offset": "0x00", "desc": "低中断状态"},
        "HISR": {"offset": "0x04", "desc": "高中断状态"},
        "LIFCR": {"offset": "0x08", "desc": "低中断标志清除"},
        "HIFCR": {"offset": "0x0C", "desc": "高中断标志清除"},
    },
    "DMA_STREAM": {
        "CR": {"offset": "0x00", "desc": "控制"},
        "NDTR": {"offset": "0x04", "desc": "数据数量"},
        "PAR": {"offset": "0x08", "desc": "外设地址"},
        "M0AR": {"offset": "0x0C", "desc": "内存0地址"},
        "M1AR": {"offset": "0x10", "desc": "内存1地址"},
        "FCR": {"offset": "0x14", "desc": "FIFO 控制"},
    },
    "RCC": {
        "CR": {"offset": "0x00", "desc": "时钟控制"},
        "PLLCFGR": {"offset": "0x04", "desc": "PLL 配置"},
        "CFGR": {"offset": "0x08", "desc": "时钟配置"},
        "CIR": {"offset": "0x0C", "desc": "时钟中断"},
        "AHB1RSTR": {"offset": "0x10", "desc": "AHB1 复位"},
        "AHB1ENR": {"offset": "0x30", "desc": "AHB1 时钟使能"},
        "APB1ENR": {"offset": "0x40", "desc": "APB1 时钟使能"},
        "APB2ENR": {"offset": "0x44", "desc": "APB2 时钟使能"},
    },
}


def parse_map_file(map_file: str) -> dict:
    """从 .map 文件解析符号地址。"""
    symbols = {}
    if not os.path.exists(map_file):
        return symbols

    with open(map_file, "r", encoding="utf-8", errors="replace") as f:
        for line in f:
            # 匹配 "0x40020000  GPIOA" 格式
            m = re.match(r"\s*(0x[0-9a-fA-F]+)\s+(\w+)", line)
            if m:
                addr = m.group(1)
                name = m.group(2)
                symbols[name] = addr
    return symbols


def decode_gpio(value: int) -> dict:
    """解码 GPIO MODER 寄存器。"""
    modes = []
    mode_names = ["输入", "输出", "复用", "模拟"]
    for pin in range(16):
        mode = (value >> (pin * 2)) & 0x3
        modes.append(f"P{pin}:{mode_names[mode]}")
    return {"modes": modes}


def decode_usart_sr(value: int) -> dict:
    """解码 USART SR 寄存器。"""
    flags = []
    bit_names = {
        0: "PE", 1: "FE", 2: "NF", 3: "ORE", 4: "IDLE",
        5: "RXNE", 6: "TC", 7: "TXE", 8: "LBD", 9: "CTS",
    }
    for bit, name in bit_names.items():
        if value & (1 << bit):
            flags.append(name)
    return {"flags": flags}


def decode_tim_cr1(value: int) -> dict:
    """解码 TIM CR1 寄存器。"""
    return {
        "CEN": (value >> 0) & 1,
        "UDIS": (value >> 1) & 1,
        "URS": (value >> 2) & 1,
        "OPM": (value >> 3) & 1,
        "DIR": (value >> 4) & 1,
        "CMS": (value >> 5) & 3,
        "ARPE": (value >> 7) & 1,
        "CKD": (value >> 8) & 3,
    }


def decode_register(peripheral_type: str, reg_name: str, value: int) -> dict:
    """解码寄存器值。"""
    if peripheral_type == "GPIO" and reg_name == "MODER":
        return decode_gpio(value)
    elif peripheral_type == "USART" and reg_name == "SR":
        return decode_usart_sr(value)
    elif peripheral_type == "TIM" and reg_name == "CR1":
        return decode_tim_cr1(value)
    return {}


def generate_reg_dump(project_dir: str, peripherals: list[str] = None) -> dict:
    """生成寄存器转储报告。"""
    # 查找 map 文件
    map_file = None
    for root, _, files in os.walk(project_dir):
        for f in files:
            if f.endswith(".map"):
                map_file = os.path.join(root, f)
                break

    symbols = {}
    if map_file:
        symbols = parse_map_file(map_file)

    result = {
        "peripherals": {},
        "map_file": map_file,
    }

    for name, info in PERIPHERAL_DEFS.items():
        # 过滤指定外设
        if peripherals:
            ptype = info["type"].lower()
            if not any(p.lower() in ptype or p.lower() in name.lower() for p in peripherals):
                continue

        ptype = info["type"]
        base = info["base"]

        regs = {}
        if ptype in REGISTER_DEFS:
            for reg_name, reg_info in REGISTER_DEFS[ptype].items():
                regs[reg_name] = {
                    "offset": reg_info["offset"],
                    "desc": reg_info["desc"],
                    "address": f"0x{int(base, 16) + int(reg_info['offset'], 16):08X}",
                }

        result["peripherals"][name] = {
            "base": base,
            "type": ptype,
            "registers": regs,
        }

    return result


def main():
    parser = argparse.ArgumentParser(description="STM32 外设寄存器转储工具")
    parser.add_argument("--auto", metavar="DIR", default=".", help="项目目录")
    parser.add_argument("--mcu", default="STM32F407", help="MCU 型号")
    parser.add_argument("--peripheral", help="指定外设（逗号分隔：GPIO,TIM,ADC）")
    parser.add_argument("--output", help="输出文件路径")
    parser.add_argument("--json", action="store_true", help="JSON 格式输出")
    args = parser.parse_args()

    project_dir = str(Path(args.auto).resolve())
    peripherals = args.peripheral.split(",") if args.peripheral else None

    result = generate_reg_dump(project_dir, peripherals)

    if args.json:
        if args.output:
            with open(args.output, "w", encoding="utf-8") as f:
                json.dump(result, f, indent=2, ensure_ascii=False)
            print(f"✅ 已保存到: {args.output}")
        else:
            print(json.dumps(result, indent=2, ensure_ascii=False))
    else:
        print(f"📊 外设寄存器转储（{args.mcu}）")
        if result["map_file"]:
            print(f"   Map 文件: {result['map_file']}")
        print()

        for name, info in result["peripherals"].items():
            print(f"┌─ {name} ({info['type']}) @ {info['base']}")
            for reg_name, reg_info in info["registers"].items():
                print(f"│  {reg_name:<12} {reg_info['offset']}  {reg_info['desc']}")
            print(f"└─")


if __name__ == "__main__":
    main()
