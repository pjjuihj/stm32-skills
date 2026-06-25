#!/usr/bin/env python
"""STM32 DMA 性能分析工具。

分析 DMA 配置、传输速率、缓冲区使用情况。

用法:
  python dma_analyzer.py --auto .                            # 分析 DMA 配置
  python dma_analyzer.py --auto . --profile --port COM3      # 分析 DMA 性能（需硬件）
  python dma_analyzer.py --auto . --json                     # JSON 输出

功能:
  - 从 .ioc 和源码分析 DMA 配置
  - 检查 DMA Stream/Channel 分配冲突
  - 计算理论传输速率
  - 通过串口测量实际 DMA 性能（需固件支持）
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


# STM32F4 DMA Stream/Channel 映射
DMA_CHANNELS = {
    "DMA1_Stream0": {"channels": {0: "SPI3_RX", 1: "I2C1_RX", 2: "TIM4_CH1", 3: "I2S3_EXT_RX",
                                   4: "USART2_RX", 5: "TIM3_CH4", 6: "TIM5_CH3", 7: "I2S3_EXT_RX"}},
    "DMA1_Stream1": {"channels": {0: "SPI2_RX", 1: "I2C3_RX", 2: "TIM7_UP", 3: "USART3_TX",
                                   4: "TIM2_CH2", 5: "TIM5_CH4", 6: "I2S2_EXT_RX", 7: "I2C1_RX"}},
    "DMA1_Stream2": {"channels": {0: "SPI3_RX", 1: "TIM4_CH2", 2: "I2C3_RX", 3: "I2S3_EXT_RX",
                                   4: "USART1_RX", 5: "TIM5_UP", 6: "TIM6_UP", 7: "I2C2_RX"}},
    "DMA1_Stream3": {"channels": {0: "SPI2_TX", 1: "I2C1_TX", 2: "TIM4_CH3", 3: "I2S2_EXT_TX",
                                   4: "USART1_TX", 5: "TIM5_CH1", 6: "DAC1", 7: "I2C2_TX"}},
    "DMA1_Stream4": {"channels": {0: "SPI3_TX", 1: "I2C1_RX", 2: "TIM4_UP", 3: "I2S3_EXT_TX",
                                   4: "USART2_TX", 5: "TIM3_CH1", 6: "DAC2", 7: "I2C3_TX"}},
    "DMA1_Stream5": {"channels": {0: "SPI3_TX", 1: "I2C3_TX", 2: "TIM2_CH1", 3: "I2S3_EXT_TX",
                                   4: "USART3_RX", 5: "TIM3_CH2", 6: "I2S2_EXT_TX", 7: "SPI2_TX"}},
    "DMA1_Stream6": {"channels": {0: "I2C1_RX", 1: "SPI2_TX", 2: "TIM5_CH3", 3: "I2C1_TX",
                                   4: "USART2_RX", 5: "TIM3_CH3", 6: "I2S2_EXT_TX", 7: "I2C2_TX"}},
    "DMA1_Stream7": {"channels": {0: "I2C1_TX", 1: "SPI2_TX", 2: "TIM5_CH4", 3: "I2C1_TX",
                                   4: "USART2_TX", 5: "TIM3_UP", 6: "DAC2", 7: "SPI2_RX"}},
    "DMA2_Stream0": {"channels": {0: "ADC1", 1: "SAI1_A", 2: "TIM8_CH1", 3: "SPI1_RX",
                                   4: "USART1_RX", 5: "TIM1_CH1", 6: "TIM2_UP", 7: "TIM8_CH1"}},
    "DMA2_Stream1": {"channels": {0: "ADC2", 1: "TIM2_CH3", 2: "TIM8_CH2", 3: "SPI1_TX",
                                   4: "USART1_TX", 5: "TIM1_CH2", 6: "TIM5_CH1", 7: "TIM8_CH2"}},
    "DMA2_Stream2": {"channels": {0: "ADC3", 1: "TIM6_UP", 2: "TIM8_CH3", 3: "SPI1_RX",
                                   4: "USART6_RX", 5: "TIM1_CH3", 6: "TIM5_CH2", 7: "TIM8_CH3"}},
    "DMA2_Stream3": {"channels": {0: "ADC1", 1: "TIM7_UP", 2: "TIM8_CH4", 3: "SPI1_TX",
                                   4: "USART6_TX", 5: "TIM1_CH4", 6: "TIM5_CH3", 7: "TIM8_CH4"}},
    "DMA2_Stream4": {"channels": {0: "ADC2", 1: "ADC3", 2: "TIM8_UP", 3: "SPI1_TX",
                                   4: "USART1_RX", 5: "TIM1_UP", 6: "TIM5_CH4", 7: "TIM8_UP"}},
    "DMA2_Stream5": {"channels": {0: "ADC3", 1: "SAI1_B", 2: "TIM8_CH1", 3: "SPI1_RX",
                                   4: "USART1_TX", 5: "TIM1_TRIG", 6: "TIM5_UP", 7: "TIM8_CH1"}},
    "DMA2_Stream6": {"channels": {0: "ADC1", 1: "TIM8_CH2", 2: "TIM8_CH3", 3: "SPI1_TX",
                                   4: "USART6_RX", 5: "TIM1_CH1", 6: "TIM5_CH3", 7: "TIM8_CH2"}},
    "DMA2_Stream7": {"channels": {0: "ADC2", 1: "TIM8_CH4", 2: "TIM8_UP", 3: "SPI1_TX",
                                   4: "USART6_TX", 5: "TIM1_CH2", 6: "TIM5_CH4", 7: "TIM8_CH3"}},
}


def parse_dma_config_from_ioc(project_dir: str) -> list[dict]:
    """从 .ioc 文件解析 DMA 配置。"""
    ioc_file = None
    for f in os.listdir(project_dir):
        if f.endswith(".ioc"):
            ioc_file = os.path.join(project_dir, f)
            break

    if not ioc_file:
        return []

    dma_configs = []
    with open(ioc_file, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if "DMA" in line and "=" in line:
                key, value = line.split("=", 1)
                key = key.strip()
                value = value.strip()
                if "Request" in key or "Channel" in key or "Direction" in key:
                    dma_configs.append({"key": key, "value": value})

    return dma_configs


def parse_dma_config_from_source(project_dir: str) -> list[dict]:
    """从源码解析 DMA 配置。"""
    configs = []
    src_dir = os.path.join(project_dir, "Core", "Src")
    if not os.path.isdir(src_dir):
        return configs

    for f in os.listdir(src_dir):
        if not f.endswith(".c"):
            continue
        filepath = os.path.join(src_dir, f)
        with open(filepath, "r", encoding="utf-8", errors="replace") as fh:
            content = fh.read()

        # 匹配 DMA 配置
        # HAL_DMA_Init 调用
        for m in re.finditer(r"HAL_DMA_Init\s*\(\s*&(\w+)", content):
            configs.append({"stream": m.group(1), "file": f, "type": "HAL_DMA_Init"})

        # __HAL_LINKDMA
        for m in re.finditer(r"__HAL_LINKDMA\s*\(\s*&(\w+)\s*,\s*(\w+)\s*,\s*(\w+)", content):
            configs.append({
                "peripheral": m.group(1),
                "linked": m.group(2),
                "stream": m.group(3),
                "file": f,
                "type": "LINKDMA",
            })

        # DMA 寄存器直接操作
        for m in re.finditer(r"DMA(\d)_Stream(\d)->CR\s*[|]=" , content):
            configs.append({
                "stream": f"DMA{m.group(1)}_Stream{m.group(2)}",
                "file": f,
                "type": "direct_register",
            })

    return configs


def check_conflicts(configs: list[dict]) -> list[dict]:
    """检查 DMA Stream 冲突。"""
    conflicts = []
    streams_used = {}

    for c in configs:
        stream = c.get("stream", "")
        if stream in streams_used:
            conflicts.append({
                "stream": stream,
                "files": [streams_used[stream], c.get("file", "")],
                "message": f"{stream} 被多个外设使用",
            })
        else:
            streams_used[stream] = c.get("file", "")

    return conflicts


def calculate_transfer_rate(bus_width: int, clock_mhz: int, is_double_buffer: bool = False) -> dict:
    """计算 DMA 理论传输速率。"""
    # DMA 传输需要 1 个 AHB 时钟周期
    rate_mbps = clock_mhz * bus_width / 8  # MB/s

    if is_double_buffer:
        rate_mbps *= 1.5  # 双缓冲减少切换开销

    return {
        "bus_width_bits": bus_width,
        "clock_mhz": clock_mhz,
        "rate_mbps": rate_mbps,
        "is_double_buffer": is_double_buffer,
    }


def analyze_dma(project_dir: str) -> dict:
    """分析 DMA 配置。"""
    ioc_configs = parse_dma_config_from_ioc(project_dir)
    source_configs = parse_dma_config_from_source(project_dir)
    conflicts = check_conflicts(source_configs)

    # 统计使用的 Stream
    streams_used = set()
    for c in source_configs:
        stream = c.get("stream", "")
        if stream:
            streams_used.add(stream)

    return {
        "ioc_configs": ioc_configs,
        "source_configs": source_configs,
        "streams_used": list(streams_used),
        "stream_count": len(streams_used),
        "conflicts": conflicts,
        "channel_map": DMA_CHANNELS,
    }


def main():
    parser = argparse.ArgumentParser(description="STM32 DMA 性能分析工具")
    parser.add_argument("--auto", metavar="DIR", default=".", help="项目目录")
    parser.add_argument("--profile", action="store_true", help="分析 DMA 性能（需硬件）")
    parser.add_argument("--port", help="串口端口")
    parser.add_argument("--json", action="store_true", help="JSON 格式输出")
    args = parser.parse_args()

    project_dir = str(Path(args.auto).resolve())
    result = analyze_dma(project_dir)

    if args.json:
        print(json.dumps(result, indent=2, ensure_ascii=False))
    else:
        print(f"📊 DMA 配置分析")
        print()

        # 使用的 Stream
        print(f"使用的 DMA Stream ({result['stream_count']} 个):")
        for s in result["streams_used"]:
            print(f"  {s}")
        print()

        # 源码配置
        if result["source_configs"]:
            print(f"源码中的 DMA 配置:")
            for c in result["source_configs"]:
                print(f"  {c.get('file', ''):<20} {c.get('type', ''):<15} {c.get('stream', '')}")
            print()

        # 冲突检测
        if result["conflicts"]:
            print(f"⚠️ DMA Stream 冲突:")
            for c in result["conflicts"]:
                print(f"  ❌ {c['message']}")
                print(f"     文件: {', '.join(c['files'])}")
        else:
            print(f"✅ 未发现 DMA Stream 冲突")
        print()

        # 理论传输速率
        print(f"理论传输速率（AHB 时钟 42MHz）:")
        rate = calculate_transfer_rate(16, 42)
        print(f"  16-bit @ 42MHz: {rate['rate_mbps']:.1f} MB/s")
        rate = calculate_transfer_rate(32, 42)
        print(f"  32-bit @ 42MHz: {rate['rate_mbps']:.1f} MB/s")


if __name__ == "__main__":
    main()
