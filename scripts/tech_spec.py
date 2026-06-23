#!/usr/bin/env python
"""STM32 技术规范生成工具。

从项目配置、编译结果、CubeMX 配置中提取信息，生成结构化技术规范文档。

用法:
  # 自动模式（推荐）
  python tech_spec.py --auto . --text

  # 从工作流结果生成
  python tech_spec.py --workflow workflow_result.json --text

  # 从多个来源生成
  python tech_spec.py --elf project.axf --ioc project.ioc --text

  # 输出到文件
  python tech_spec.py --auto . --output tech_spec.md
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

# 使用共享模块
try:
    from shared import (
        setup_encoding, print_json, read_json_file, read_text_file,
        CHIP_DB, lookup_chip
    )
except ImportError:
    def setup_encoding():
        if sys.stdout and hasattr(sys.stdout, "reconfigure"):
            try:
                sys.stdout.reconfigure(encoding="utf-8", errors="replace")
            except Exception:
                pass

    def read_json_file(file_path):
        try:
            return json.loads(Path(file_path).read_text(encoding="utf-8"))
        except:
            return None

    def read_text_file(file_path):
        try:
            return Path(file_path).read_text(encoding="utf-8", errors="replace")
        except:
            return None

    CHIP_DB = {}
    def lookup_chip(chip_name):
        return None


# === IOC 解析器 ===

def parse_ioc_file(ioc_path: str) -> dict:
    """解析 CubeMX .ioc 文件。"""
    content = read_text_file(ioc_path)
    if not content:
        return {}

    config = {
        "pins": [],
        "peripherals": [],
        "clock": {},
        "nvic": [],
        "freertos": {},
        "dma": [],
        "gpio": [],
    }

    # 临时存储引脚信息
    pin_info = {}  # pin -> {mode, label, speed, pull, ...}

    for line in content.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue

        if "=" not in line:
            continue

        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip()

        # GPIO 配置
        if key.startswith("P") and len(key) >= 3:
            pin = key.split(".")[0]

            # 初始化引脚信息
            if pin not in pin_info:
                pin_info[pin] = {"pin": pin}

            # 提取各种属性
            if ".Mode" in key:
                pin_info[pin]["mode"] = value
            elif ".GPIO_Label" in key or ".Signal" in key:
                pin_info[pin]["label"] = value
            elif ".GPIO_PuPd" in key:
                pin_info[pin]["pull"] = value
            elif ".GPIO_Speed" in key:
                pin_info[pin]["speed"] = value
            elif ".GPIO_OutputType" in key:
                pin_info[pin]["output_type"] = value
            elif ".GPIO_Parameters" not in key and ".Mode" not in key:
                # 其他属性
                attr = key.split(".")[-1]
                pin_info[pin][attr] = value

        # 外设配置
        if ".Mode" in key and not key.startswith("P"):
            periph = key.split(".")[0]
            if periph not in [p["name"] for p in config["peripherals"]]:
                config["peripherals"].append({
                    "name": periph,
                    "mode": value,
                })

        # 外设参数
        if "." in key and not key.startswith("P") and not key.startswith("RCC"):
            parts = key.split(".", 1)
            if len(parts) == 2:
                periph, param = parts
                if param != "Mode" and param != "NVIC":
                    # 查找已有外设
                    for p in config["peripherals"]:
                        if p["name"] == periph:
                            if "params" not in p:
                                p["params"] = {}
                            p["params"][param] = value
                            break

        # 时钟配置
        if key.startswith("RCC."):
            clock_key = key.replace("RCC.", "")
            config["clock"][clock_key] = value

        # NVIC 配置
        if ".NVIC" in key and ".Enable" in key and value.lower() == "true":
            irq = key.split(".")[0]
            config["nvic"].append({"irq": irq, "enabled": True})

        # NVIC 优先级
        if ".NVIC" in key and ".PreemptionPriority" in key:
            irq = key.split(".")[0]
            for nvic in config["nvic"]:
                if nvic["irq"] == irq:
                    nvic["preemption_priority"] = int(value)
                    break

        if ".NVIC" in key and ".SubPriority" in key:
            irq = key.split(".")[0]
            for nvic in config["nvic"]:
                if nvic["irq"] == irq:
                    nvic["sub_priority"] = int(value)
                    break

        # FreeRTOS 配置
        if key.startswith("FREERTOS."):
            rtos_key = key.replace("FREERTOS.", "")
            config["freertos"][rtos_key] = value

        # DMA 配置
        if "DMA" in key and ".Request" in key:
            dma_match = re.match(r"(.+?)\.DMA_.*", key)
            if dma_match:
                dma_name = dma_match.group(1)
                if dma_name not in [d["name"] for d in config["dma"]]:
                    config["dma"].append({"name": dma_name, "request": value})

    # 转换引脚信息
    for pin, info in pin_info.items():
        config["pins"].append(info)

    return config


# === ELF 信息提取 ===

def extract_elf_info(elf_path: str, uv4_path: str = None) -> dict:
    """从 ELF 文件提取信息。"""
    info = {
        "file": elf_path,
        "size_bytes": 0,
        "sections": {},
        "symbols": [],
    }

    path = Path(elf_path)
    if path.exists():
        info["size_bytes"] = path.stat().st_size

    # 尝试使用 fromelf 获取段信息
    if uv4_path:
        try:
            import subprocess
            from shared import find_fromelf
            fromelf = find_fromelf(uv4_path)
            if fromelf:
                proc = subprocess.run(
                    [fromelf, "-z", elf_path],
                    capture_output=True, text=True, timeout=30,
                )
                if proc.returncode == 0:
                    info["sections_raw"] = proc.stdout
        except Exception:
            pass

    return info


# === 技术规范生成 ===

# 芯片系列特征数据库
CHIP_FEATURES = {
    "F1": {
        "core": "Cortex-M3",
        "max_freq": "72 MHz",
        "voltage": "2.0V - 3.6V",
        "features": ["GPIO", "USART", "SPI", "I2C", "ADC", "TIM", "DMA", "USB"],
        "flash_start": "0x08000000",
        "ram_start": "0x20000000",
    },
    "F2": {
        "core": "Cortex-M3",
        "max_freq": "120 MHz",
        "voltage": "1.8V - 3.6V",
        "features": ["GPIO", "USART", "SPI", "I2C", "ADC", "TIM", "DMA", "USB", "ETH"],
        "flash_start": "0x08000000",
        "ram_start": "0x20000000",
    },
    "F3": {
        "core": "Cortex-M4F",
        "max_freq": "72 MHz",
        "voltage": "2.0V - 3.6V",
        "features": ["GPIO", "USART", "SPI", "I2C", "ADC", "DAC", "TIM", "DMA", "USB"],
        "flash_start": "0x08000000",
        "ram_start": "0x20000000",
    },
    "F4": {
        "core": "Cortex-M4F",
        "max_freq": "168 MHz",
        "voltage": "1.8V - 3.6V",
        "features": ["GPIO", "USART", "SPI", "I2C", "ADC", "DAC", "TIM", "DMA", "USB", "ETH", "SDIO", "DCMI"],
        "flash_start": "0x08000000",
        "ram_start": "0x20000000",
        "ccm_start": "0x10000000",
    },
    "F7": {
        "core": "Cortex-M7F",
        "max_freq": "216 MHz",
        "voltage": "1.7V - 3.6V",
        "features": ["GPIO", "USART", "SPI", "I2C", "ADC", "DAC", "TIM", "DMA", "USB", "ETH", "SDIO", "DCMI", "QSPI"],
        "flash_start": "0x08000000",
        "ram_start": "0x20000000",
        "dtcm_start": "0x20000000",
    },
    "G0": {
        "core": "Cortex-M0+",
        "max_freq": "64 MHz",
        "voltage": "1.7V - 3.6V",
        "features": ["GPIO", "USART", "SPI", "I2C", "ADC", "TIM", "DMA"],
        "flash_start": "0x08000000",
        "ram_start": "0x20000000",
    },
    "G4": {
        "core": "Cortex-M4F",
        "max_freq": "170 MHz",
        "voltage": "1.71V - 3.6V",
        "features": ["GPIO", "USART", "SPI", "I2C", "ADC", "DAC", "TIM", "DMA", "USB", "CORDIC"],
        "flash_start": "0x08000000",
        "ram_start": "0x20000000",
    },
    "H7": {
        "core": "Cortex-M7F",
        "max_freq": "480 MHz",
        "voltage": "1.62V - 3.6V",
        "features": ["GPIO", "USART", "SPI", "I2C", "ADC", "DAC", "TIM", "DMA", "USB", "ETH", "SDIO", "QSPI", "JPEG", "MDMA"],
        "flash_start": "0x08000000",
        "ram_start": "0x20000000",
        "dtcm_start": "0x20000000",
        "axi_start": "0x24000000",
    },
    "L0": {
        "core": "Cortex-M0+",
        "max_freq": "32 MHz",
        "voltage": "1.65V - 3.6V",
        "features": ["GPIO", "USART", "SPI", "I2C", "ADC", "TIM", "DMA", "LCD"],
        "flash_start": "0x08000000",
        "ram_start": "0x20000000",
    },
    "L4": {
        "core": "Cortex-M4F",
        "max_freq": "80 MHz",
        "voltage": "1.71V - 3.6V",
        "features": ["GPIO", "USART", "SPI", "I2C", "ADC", "DAC", "TIM", "DMA", "USB", "SDIO", "QSPI"],
        "flash_start": "0x08000000",
        "ram_start": "0x20000000",
    },
}


def generate_tech_spec(project_info: dict, ioc_config: dict = None,
                       elf_info: dict = None, workflow_data: dict = None) -> dict:
    """生成技术规范数据。"""
    spec = {
        "project": {},
        "chip": {},
        "memory": {},
        "features": [],
        "peripherals": [],
        "pins": [],
        "clock": {},
        "nvic": [],
        "rtos": None,
        "build": {},
        "timestamp": datetime.now().isoformat(),
    }

    # 项目信息
    spec["project"] = {
        "name": project_info.get("project_name", "Unknown"),
        "directory": project_info.get("project_dir", ""),
        "toolchain": "Keil MDK-ARM V5",
        "target": project_info.get("target_name", project_info.get("target", "")),
        "optimization": project_info.get("optim_level", ""),
        "c_standard": project_info.get("c_standard", ""),
    }

    # 芯片信息
    chip_name = project_info.get("device", project_info.get("chip", ""))
    series = project_info.get("series", "")

    # 从芯片名称推断系列
    if not series and chip_name:
        import re
        m = re.match(r"STM32([A-Z]\d)", chip_name)
        if m:
            series = m.group(1)

    spec["chip"] = {
        "name": chip_name,
        "series": series,
        "flash_kb": project_info.get("flash_kb", 0) or 0,
        "ram_kb": project_info.get("ram_kb", 0) or 0,
        "ccm_kb": project_info.get("ccm_kb", 0) or 0,
    }

    # 从芯片数据库补充信息
    if chip_name:
        chip_data = lookup_chip(chip_name)
        if chip_data:
            spec["chip"].update({
                "flash_kb": chip_data.get("flash_kb", spec["chip"]["flash_kb"]),
                "ram_kb": chip_data.get("ram_kb", spec["chip"]["ram_kb"]),
                "ccm_kb": chip_data.get("ccm_kb", spec["chip"]["ccm_kb"]),
            })

    # 从系列特征数据库补充信息
    if series and series in CHIP_FEATURES:
        features = CHIP_FEATURES[series]
        spec["chip"]["core"] = features["core"]
        spec["chip"]["max_freq"] = features["max_freq"]
        spec["chip"]["voltage"] = features["voltage"]
        spec["features"] = features["features"]

        # 内存布局
        spec["memory"]["flash"] = {
            "size_kb": spec["chip"]["flash_kb"],
            "start": features["flash_start"],
        }
        spec["memory"]["ram"] = {
            "size_kb": spec["chip"]["ram_kb"],
            "start": features["ram_start"],
        }
        if spec["chip"]["ccm_kb"] > 0 and "ccm_start" in features:
            spec["memory"]["ccm"] = {
                "size_kb": spec["chip"]["ccm_kb"],
                "start": features["ccm_start"],
            }
    else:
        # 默认内存布局
        spec["memory"]["flash"] = {
            "size_kb": spec["chip"]["flash_kb"],
            "start": "0x08000000",
        }
        spec["memory"]["ram"] = {
            "size_kb": spec["chip"]["ram_kb"],
            "start": "0x20000000",
        }

    # IOC 配置
    if ioc_config:
        spec["pins"] = ioc_config.get("pins", [])
        spec["peripherals"] = ioc_config.get("peripherals", [])
        spec["clock"] = ioc_config.get("clock", {})
        spec["nvic"] = ioc_config.get("nvic", [])
        if ioc_config.get("freertos"):
            spec["rtos"] = ioc_config["freertos"]

    # ELF 信息
    if elf_info:
        spec["build"]["elf_size"] = elf_info.get("size_bytes", 0)
        if "sections" in elf_info:
            spec["build"]["sections"] = elf_info["sections"]

    # 工作流数据
    if workflow_data:
        steps = workflow_data.get("steps", {})
        if "analyze" in steps:
            analyze = steps["analyze"]
            if "check_elf" in analyze:
                elf_data = analyze["check_elf"]
                if "size" in elf_data:
                    spec["build"]["flash_used"] = (
                        elf_data["size"].get("text", 0) +
                        elf_data["size"].get("ro_data", 0)
                    )
                    spec["build"]["ram_used"] = (
                        elf_data["size"].get("data", 0) +
                        elf_data["size"].get("bss", 0)
                    )
            if "debug_sim" in analyze:
                sim_data = analyze["debug_sim"]
                if "stack_heap" in sim_data:
                    spec["build"]["stack_size"] = sim_data["stack_heap"].get("stack_size", 0)
                    spec["build"]["heap_size"] = sim_data["stack_heap"].get("heap_size", 0)

        if "optimize" in steps:
            opt_data = steps["optimize"]
            if "compiler_settings" in opt_data:
                spec["build"]["optimization"] = opt_data["compiler_settings"].get("optimization_level", "")

    return spec


# === 文本输出 ===

def format_tech_spec_markdown(spec: dict) -> str:
    """生成 Markdown 格式的技术规范。"""
    lines = []

    # 标题
    lines.append(f"# {spec['project'].get('name', 'STM32')} 技术规范")
    lines.append("")
    lines.append(f"> 生成时间: {spec.get('timestamp', 'N/A')}")
    lines.append("")

    # 目录
    lines.append("## 目录")
    lines.append("")
    lines.append("1. [项目信息](#项目信息)")
    lines.append("2. [芯片信息](#芯片信息)")
    lines.append("3. [内存布局](#内存布局)")
    lines.append("4. [构建信息](#构建信息)")
    lines.append("5. [外设配置](#外设配置)")
    lines.append("6. [GPIO 配置](#gpio-配置)")
    lines.append("7. [时钟配置](#时钟配置)")
    lines.append("8. [NVIC 配置](#nvic-配置)")
    lines.append("")

    # 项目信息
    lines.append("## 项目信息")
    lines.append("")
    lines.append(f"| 项目 | 值 |")
    lines.append(f"|------|-----|")
    lines.append(f"| 项目名 | {spec['project'].get('name', 'N/A')} |")
    lines.append(f"| 工具链 | {spec['project'].get('toolchain', 'N/A')} |")
    lines.append(f"| Target | {spec['project'].get('target', 'N/A')} |")
    if spec['project'].get('optimization'):
        lines.append(f"| 优化级别 | {spec['project']['optimization']} |")
    if spec['project'].get('c_standard'):
        lines.append(f"| C 标准 | {spec['project']['c_standard']} |")
    lines.append("")

    # 芯片信息
    lines.append("## 芯片信息")
    lines.append("")
    lines.append(f"| 参数 | 值 |")
    lines.append(f"|------|-----|")
    lines.append(f"| 型号 | {spec['chip'].get('name', 'N/A')} |")
    lines.append(f"| 系列 | {spec['chip'].get('series', 'N/A')} |")
    lines.append(f"| 内核 | {spec['chip'].get('core', 'Cortex-M')} |")
    if spec['chip'].get('max_freq'):
        lines.append(f"| 最高频率 | {spec['chip']['max_freq']} |")
    if spec['chip'].get('voltage'):
        lines.append(f"| 工作电压 | {spec['chip']['voltage']} |")
    lines.append(f"| Flash | {spec['chip'].get('flash_kb', 0)} KB |")
    lines.append(f"| RAM | {spec['chip'].get('ram_kb', 0)} KB |")
    if spec['chip'].get('ccm_kb', 0) > 0:
        lines.append(f"| CCM RAM | {spec['chip']['ccm_kb']} KB |")
    lines.append("")

    # 支持的外设特性
    if spec.get("features"):
        lines.append("### 支持的外设特性")
        lines.append("")
        lines.append(", ".join(spec["features"]))
        lines.append("")

    # 内存布局
    lines.append("## 内存布局")
    lines.append("")
    lines.append(f"| 区域 | 起始地址 | 大小 |")
    lines.append(f"|------|----------|------|")
    for mem_name, mem_info in spec.get("memory", {}).items():
        size_kb = mem_info.get('size_kb', 0)
        size_str = f"{size_kb} KB" if size_kb < 1024 else f"{size_kb/1024:.1f} MB"
        lines.append(f"| {mem_name.upper()} | {mem_info.get('start', 'N/A')} | {size_str} |")
    lines.append("")

    # 内存映射可视化
    memory = spec.get("memory", {})
    if memory:
        lines.append("### 内存映射")
        lines.append("")
        lines.append("```")
        lines.append("内存映射:")
        lines.append("")

        # 计算内存区域
        flash = memory.get("flash", {})
        ram = memory.get("ram", {})
        ccm = memory.get("ccm", {})

        flash_start = flash.get("start", "0x08000000")
        flash_size = flash.get("size_kb", 0)
        ram_start = ram.get("start", "0x20000000")
        ram_size = ram.get("size_kb", 0)
        ccm_start = ccm.get("start", "0x10000000")
        ccm_size = ccm.get("size_kb", 0)

        # 计算结束地址
        flash_end = int(flash_start, 16) + flash_size * 1024 - 1
        ram_end = int(ram_start, 16) + ram_size * 1024 - 1

        lines.append(f"  FLASH ({flash_size} KB):")
        lines.append(f"    {flash_start} ───────────────────── {flash_end:08X}")
        lines.append(f"    │                                         │")
        lines.append(f"    │  .text (代码)                            │")
        lines.append(f"    │  .rodata (只读数据)                      │")
        lines.append(f"    │  .data (初始化数据)                      │")
        lines.append(f"    └─────────────────────────────────────────┘")
        lines.append("")

        lines.append(f"  RAM ({ram_size} KB):")
        lines.append(f"    {ram_start} ───────────────────── {ram_end:08X}")
        lines.append(f"    │                                         │")
        lines.append(f"    │  .data (从 Flash 复制)                   │")
        lines.append(f"    │  .bss (零初始化)                         │")
        lines.append(f"    │  .heap (动态分配)                        │")
        lines.append(f"    │  .stack (栈)                             │")
        lines.append(f"    └─────────────────────────────────────────┘")
        lines.append("")

        if ccm_size > 0:
            ccm_end = int(ccm_start, 16) + ccm_size * 1024 - 1
            lines.append(f"  CCM RAM ({ccm_size} KB):")
            lines.append(f"    {ccm_start} ───────────────────── {ccm_end:08X}")
            lines.append(f"    │                                         │")
            lines.append(f"    │  仅 CPU 可访问，DMA 不可用               │")
            lines.append(f"    └─────────────────────────────────────────┘")
            lines.append("")

        lines.append("```")
        lines.append("")

    # 构建信息
    if spec.get("build"):
        lines.append("## 构建信息")
        lines.append("")
        build = spec["build"]
        lines.append(f"| 指标 | 值 |")
        lines.append(f"|------|-----|")
        if "flash_used" in build:
            flash_kb = spec["chip"].get("flash_kb", 0)
            used_kb = build["flash_used"] / 1024
            percent = (used_kb / flash_kb * 100) if flash_kb > 0 else 0
            lines.append(f"| Flash 使用 | {used_kb:.1f} KB / {flash_kb} KB ({percent:.1f}%) |")
        if "ram_used" in build:
            ram_kb = spec["chip"].get("ram_kb", 0)
            used_kb = build["ram_used"] / 1024
            percent = (used_kb / ram_kb * 100) if ram_kb > 0 else 0
            lines.append(f"| RAM 使用 | {used_kb:.1f} KB / {ram_kb} KB ({percent:.1f}%) |")
        if "stack_size" in build:
            lines.append(f"| 栈大小 | {build['stack_size']} bytes |")
        if "heap_size" in build:
            lines.append(f"| 堆大小 | {build['heap_size']} bytes |")
        if "optimization" in build:
            lines.append(f"| 优化级别 | {build['optimization']} |")
        lines.append("")

    # 外设配置
    if spec.get("peripherals"):
        lines.append("## 外设配置")
        lines.append("")
        lines.append(f"| 外设 | 模式 | 参数 |")
        lines.append(f"|------|------|------|")
        for periph in spec["peripherals"]:
            params = ""
            if "params" in periph:
                params = ", ".join(f"{k}={v}" for k, v in periph["params"].items() if v)
            lines.append(f"| {periph.get('name', 'N/A')} | {periph.get('mode', 'N/A')} | {params} |")
        lines.append("")

    # GPIO 配置
    if spec.get("pins"):
        lines.append("## GPIO 配置")
        lines.append("")
        lines.append(f"| 引脚 | 模式 | 标签 | 速度 | 上拉/下拉 |")
        lines.append(f"|------|------|------|------|-----------|")
        for pin in spec["pins"]:
            lines.append(f"| {pin.get('pin', 'N/A')} | {pin.get('mode', 'N/A')} | {pin.get('label', '')} | {pin.get('speed', '')} | {pin.get('pull', '')} |")
        lines.append("")

    # 时钟配置
    if spec.get("clock"):
        lines.append("## 时钟配置")
        lines.append("")

        # 时钟树可视化
        clock = spec["clock"]
        lines.append("```")
        lines.append("时钟树:")
        lines.append("")

        # 提取关键时钟参数
        hse = clock.get("HSE_VALUE", clock.get("RCC_HSE_VALUE", "8"))
        lse = clock.get("LSE_VALUE", clock.get("RCC_LSE_VALUE", "32.768"))
        sysclk_src = clock.get("RCC_SYSCLKSource", "PLLCLK")
        pll_src = clock.get("RCC_PLLSource", "HSE")
        pll_mul = clock.get("RCC_PLLMUL", "x9")
        hclk = clock.get("RCC_HCLK", "SYSCLK/1")
        pclk1 = clock.get("RCC_PCLK1", "HCLK/2")
        pclk2 = clock.get("RCC_PCLK2", "HCLK/1")

        lines.append(f"  HSE ({hse} MHz) ───┐")
        lines.append(f"                    │")
        lines.append(f"  LSI (40 KHz) ───┼──→ PLL ({pll_src} × {pll_mul}) ──→ SYSCLK ({sysclk_src})")
        lines.append(f"                    │           │")
        lines.append(f"  LSE ({lse} KHz) ─┘           │")
        lines.append(f"                               │")
        lines.append(f"  ┌────────────────────────────┘")
        lines.append(f"  │")
        lines.append(f"  ├─→ HCLK ({hclk}) ──→ AHB 总线、Core、DMA")
        lines.append(f"  │")
        lines.append(f"  ├─→ PCLK1 ({pclk1}) ──→ APB1 总线（USART2/3/4/5, TIM2-7, I2C1/2, SPI2/3）")
        lines.append(f"  │")
        lines.append(f"  └─→ PCLK2 ({pclk2}) ──→ APB2 总线（USART1, TIM1/8, SPI1, ADC1/2/3）")
        lines.append("```")
        lines.append("")

        # 时钟参数表
        lines.append("| 参数 | 值 |")
        lines.append("|------|-----|")
        for key, value in clock.items():
            if value and value != "0":
                lines.append(f"| {key} | {value} |")
        lines.append("")

    # NVIC 配置
    if spec.get("nvic"):
        lines.append("## NVIC 配置")
        lines.append("")
        lines.append(f"| 中断 | 状态 | 优先级 |")
        lines.append(f"|------|------|--------|")
        for nvic in spec["nvic"]:
            status = "✅ 启用" if nvic.get("enabled") else "❌ 禁用"
            priority = ""
            if "preemption_priority" in nvic:
                priority = f"{nvic['preemption_priority']}.{nvic.get('sub_priority', 0)}"
            lines.append(f"| {nvic.get('irq', 'N/A')} | {status} | {priority} |")
        lines.append("")

    # FreeRTOS 配置
    if spec.get("rtos"):
        lines.append("## FreeRTOS 配置")
        lines.append("")
        lines.append(f"| 参数 | 值 |")
        lines.append(f"|------|-----|")
        for key, value in spec["rtos"].items():
            lines.append(f"| {key} | {value} |")
        lines.append("")

    return "\n".join(lines)


# === CLI ===

def main() -> int:
    parser = argparse.ArgumentParser(
        description="STM32 技术规范生成工具",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  %(prog)s --auto . --text                          # 自动模式
  %(prog)s --workflow workflow_result.json --text    # 从工作流结果
  %(prog)s --ioc project.ioc --text                 # 从 CubeMX 配置
  %(prog)s --auto . --output tech_spec.md           # 输出到文件
        """,
    )

    parser.add_argument("--auto", metavar="PROJECT_DIR",
                        help="自动检测项目配置")
    parser.add_argument("--workflow", help="工作流结果 JSON 文件")
    parser.add_argument("--ioc", help="CubeMX .ioc 文件")
    parser.add_argument("--elf", help="ELF/AXF 文件")
    parser.add_argument("--uv4", help="UV4.exe 路径")
    parser.add_argument("--text", action="store_true", help="文本格式输出")
    parser.add_argument("--output", help="输出文件路径")

    args = parser.parse_args()

    setup_encoding()

    project_info = {}
    ioc_config = None
    elf_info = None
    workflow_data = None

    # 自动模式
    if args.auto:
        try:
            from auto_detect import auto_detect_config
            config = auto_detect_config(args.auto)
            if config:
                project_info = config
                if not args.uv4 and "uv4_path" in config:
                    args.uv4 = config["uv4_path"]
                if not args.elf and "elf_path" in config:
                    args.elf = config["elf_path"]
                if not args.ioc:
                    # 查找 .ioc 文件
                    ioc_files = list(Path(args.auto).glob("*.ioc"))
                    if ioc_files:
                        args.ioc = str(ioc_files[0])
        except ImportError:
            pass

    # 读取工作流数据
    if args.workflow:
        workflow_data = read_json_file(args.workflow)

    # 解析 IOC 文件
    if args.ioc:
        ioc_config = parse_ioc_file(args.ioc)

    # 提取 ELF 信息
    if args.elf:
        elf_info = extract_elf_info(args.elf, args.uv4)

    # 生成技术规范
    spec = generate_tech_spec(project_info, ioc_config, elf_info, workflow_data)

    # 输出
    if args.text:
        report = format_tech_spec_markdown(spec)
        print(report)
    else:
        print_json(spec)

    # 保存到文件
    if args.output:
        if args.text or args.output.endswith(".md"):
            report = format_tech_spec_markdown(spec)
            Path(args.output).write_text(report, encoding="utf-8")
        else:
            Path(args.output).write_text(
                json.dumps(spec, indent=2, ensure_ascii=False),
                encoding="utf-8"
            )
        print(f"\n技术规范已保存: {args.output}", file=sys.stderr)

    return 0


if __name__ == "__main__":
    sys.exit(main())
