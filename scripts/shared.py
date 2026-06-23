"""STM32 Keil Workflow 共享模块。

提供所有脚本共用的工具函数和数据。

用法:
  from shared import find_fromelf, CHIP_DB, lookup_chip, output_result, setup_encoding
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
from datetime import datetime
from pathlib import Path


# === 编码处理 ===

def setup_encoding():
    """设置终端编码，防止中文环境下的 UnicodeEncodeError。"""
    if sys.stdout and hasattr(sys.stdout, "reconfigure"):
        try:
            sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass
    if sys.stderr and hasattr(sys.stderr, "reconfigure"):
        try:
            sys.stderr.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass


# === 工具查找 ===

def find_fromelf(uv4_path: str | None = None) -> str | None:
    """查找 fromelf 工具路径（优先 Keil 自带）。"""
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


def find_programmer(explicit_path: str | None = None) -> str | None:
    """查找 STM32_Programmer_CLI 路径。"""
    if explicit_path:
        p = Path(explicit_path)
        if p.exists():
            return str(p)
        return None

    # 检查 PATH
    cli = shutil.which("STM32_Programmer_CLI")
    if cli:
        return cli

    # 检查常见安装路径
    for candidate in [
        "C:/Program Files/STMicroelectronics/STM32Cube/STM32CubeProgrammer/bin/STM32_Programmer_CLI.exe",
        "C:/Program Files (x86)/STMicroelectronics/STM32Cube/STM32CubeProgrammer/bin/STM32_Programmer_CLI.exe",
    ]:
        if Path(candidate).exists():
            return candidate

    return None


def find_uv4() -> str | None:
    """查找 UV4.exe 路径。"""
    uv4 = shutil.which("UV4") or shutil.which("UV4.exe")
    if uv4:
        return uv4

    for candidate in [
        "D:/k5/UV4/UV4.exe",
        "C:/Keil_v5/UV4/UV4.exe",
        "C:/Keil/UV4/UV4.exe",
    ]:
        if Path(candidate).exists():
            return candidate

    return None


# === 芯片数据库 ===

# 统一格式: {model: {flash_kb, ram_kb, ccm_kb, series}}
# 合并自 detect_config.py 的 CHIP_DB (180+ 条目) 和 optimize.py 的 CHIP_MEMORY (9 条目)
CHIP_DB = {
    # F1 系列
    "STM32F103C6": {"flash_kb": 32, "ram_kb": 10, "ccm_kb": 0, "series": "F1"},
    "STM32F103C8": {"flash_kb": 64, "ram_kb": 20, "ccm_kb": 0, "series": "F1"},
    "STM32F103CB": {"flash_kb": 128, "ram_kb": 20, "ccm_kb": 0, "series": "F1"},
    "STM32F103R6": {"flash_kb": 32, "ram_kb": 10, "ccm_kb": 0, "series": "F1"},
    "STM32F103R8": {"flash_kb": 64, "ram_kb": 20, "ccm_kb": 0, "series": "F1"},
    "STM32F103RB": {"flash_kb": 128, "ram_kb": 20, "ccm_kb": 0, "series": "F1"},
    "STM32F103RC": {"flash_kb": 256, "ram_kb": 48, "ccm_kb": 0, "series": "F1"},
    "STM32F103RE": {"flash_kb": 512, "ram_kb": 64, "ccm_kb": 0, "series": "F1"},
    "STM32F103VE": {"flash_kb": 512, "ram_kb": 64, "ccm_kb": 0, "series": "F1"},
    "STM32F103ZE": {"flash_kb": 512, "ram_kb": 64, "ccm_kb": 0, "series": "F1"},
    "STM32F105R8": {"flash_kb": 64, "ram_kb": 64, "ccm_kb": 0, "series": "F1"},
    "STM32F105RB": {"flash_kb": 128, "ram_kb": 64, "ccm_kb": 0, "series": "F1"},
    "STM32F107RC": {"flash_kb": 256, "ram_kb": 64, "ccm_kb": 0, "series": "F1"},
    # F2 系列
    "STM32F205RG": {"flash_kb": 1024, "ram_kb": 128, "ccm_kb": 0, "series": "F2"},
    "STM32F207IG": {"flash_kb": 1024, "ram_kb": 128, "ccm_kb": 0, "series": "F2"},
    # F3 系列
    "STM32F303K8": {"flash_kb": 64, "ram_kb": 16, "ccm_kb": 0, "series": "F3"},
    "STM32F303RE": {"flash_kb": 512, "ram_kb": 64, "ccm_kb": 0, "series": "F3"},
    "STM32F303VE": {"flash_kb": 512, "ram_kb": 64, "ccm_kb": 0, "series": "F3"},
    "STM32F334R8": {"flash_kb": 64, "ram_kb": 16, "ccm_kb": 0, "series": "F3"},
    # F4 系列
    "STM32F401CB": {"flash_kb": 128, "ram_kb": 64, "ccm_kb": 0, "series": "F4"},
    "STM32F401CC": {"flash_kb": 256, "ram_kb": 64, "ccm_kb": 0, "series": "F4"},
    "STM32F401CD": {"flash_kb": 384, "ram_kb": 64, "ccm_kb": 0, "series": "F4"},
    "STM32F401CE": {"flash_kb": 512, "ram_kb": 96, "ccm_kb": 0, "series": "F4"},
    "STM32F405RG": {"flash_kb": 1024, "ram_kb": 192, "ccm_kb": 64, "series": "F4"},
    "STM32F407VE": {"flash_kb": 512, "ram_kb": 192, "ccm_kb": 64, "series": "F4"},
    "STM32F407VG": {"flash_kb": 1024, "ram_kb": 192, "ccm_kb": 64, "series": "F4"},
    "STM32F407IE": {"flash_kb": 512, "ram_kb": 192, "ccm_kb": 64, "series": "F4"},
    "STM32F407IG": {"flash_kb": 1024, "ram_kb": 192, "ccm_kb": 64, "series": "F4"},
    "STM32F410RB": {"flash_kb": 128, "ram_kb": 32, "ccm_kb": 0, "series": "F4"},
    "STM32F411CE": {"flash_kb": 512, "ram_kb": 128, "ccm_kb": 0, "series": "F4"},
    "STM32F411RE": {"flash_kb": 512, "ram_kb": 128, "ccm_kb": 0, "series": "F4"},
    "STM32F412RE": {"flash_kb": 512, "ram_kb": 256, "ccm_kb": 0, "series": "F4"},
    "STM32F413RH": {"flash_kb": 1536, "ram_kb": 320, "ccm_kb": 0, "series": "F4"},
    "STM32F415RG": {"flash_kb": 1024, "ram_kb": 192, "ccm_kb": 64, "series": "F4"},
    "STM32F417VE": {"flash_kb": 512, "ram_kb": 192, "ccm_kb": 64, "series": "F4"},
    "STM32F417VG": {"flash_kb": 1024, "ram_kb": 192, "ccm_kb": 64, "series": "F4"},
    "STM32F417IE": {"flash_kb": 512, "ram_kb": 192, "ccm_kb": 64, "series": "F4"},
    "STM32F417IG": {"flash_kb": 1024, "ram_kb": 192, "ccm_kb": 64, "series": "F4"},
    "STM32F427IG": {"flash_kb": 1024, "ram_kb": 256, "ccm_kb": 64, "series": "F4"},
    "STM32F427VG": {"flash_kb": 1024, "ram_kb": 256, "ccm_kb": 64, "series": "F4"},
    "STM32F429BI": {"flash_kb": 2048, "ram_kb": 256, "ccm_kb": 64, "series": "F4"},
    "STM32F429IG": {"flash_kb": 2048, "ram_kb": 256, "ccm_kb": 64, "series": "F4"},
    "STM32F429NI": {"flash_kb": 2048, "ram_kb": 256, "ccm_kb": 64, "series": "F4"},
    "STM32F429VI": {"flash_kb": 2048, "ram_kb": 256, "ccm_kb": 64, "series": "F4"},
    "STM32F429ZI": {"flash_kb": 2048, "ram_kb": 256, "ccm_kb": 64, "series": "F4"},
    "STM32F437IG": {"flash_kb": 1024, "ram_kb": 256, "ccm_kb": 64, "series": "F4"},
    "STM32F439BI": {"flash_kb": 2048, "ram_kb": 256, "ccm_kb": 64, "series": "F4"},
    "STM32F439IG": {"flash_kb": 2048, "ram_kb": 256, "ccm_kb": 64, "series": "F4"},
    "STM32F439NI": {"flash_kb": 2048, "ram_kb": 256, "ccm_kb": 64, "series": "F4"},
    "STM32F439VI": {"flash_kb": 2048, "ram_kb": 256, "ccm_kb": 64, "series": "F4"},
    "STM32F439ZI": {"flash_kb": 2048, "ram_kb": 256, "ccm_kb": 64, "series": "F4"},
    "STM32F446RE": {"flash_kb": 512, "ram_kb": 128, "ccm_kb": 64, "series": "F4"},
    "STM32F446RC": {"flash_kb": 256, "ram_kb": 128, "ccm_kb": 64, "series": "F4"},
    "STM32F446VE": {"flash_kb": 512, "ram_kb": 128, "ccm_kb": 64, "series": "F4"},
    "STM32F446ZE": {"flash_kb": 512, "ram_kb": 128, "ccm_kb": 64, "series": "F4"},
    "STM32F469AI": {"flash_kb": 2048, "ram_kb": 384, "ccm_kb": 64, "series": "F4"},
    "STM32F469BI": {"flash_kb": 2048, "ram_kb": 384, "ccm_kb": 64, "series": "F4"},
    "STM32F469IG": {"flash_kb": 1024, "ram_kb": 384, "ccm_kb": 64, "series": "F4"},
    "STM32F469NI": {"flash_kb": 2048, "ram_kb": 384, "ccm_kb": 64, "series": "F4"},
    # F7 系列
    "STM32F722RE": {"flash_kb": 512, "ram_kb": 256, "ccm_kb": 0, "series": "F7"},
    "STM32F723IE": {"flash_kb": 512, "ram_kb": 256, "ccm_kb": 0, "series": "F7"},
    "STM32F746VE": {"flash_kb": 512, "ram_kb": 320, "ccm_kb": 0, "series": "F7"},
    "STM32F746VG": {"flash_kb": 1024, "ram_kb": 320, "ccm_kb": 0, "series": "F7"},
    "STM32F746ZE": {"flash_kb": 512, "ram_kb": 320, "ccm_kb": 0, "series": "F7"},
    "STM32F746ZG": {"flash_kb": 1024, "ram_kb": 320, "ccm_kb": 0, "series": "F7"},
    "STM32F756VG": {"flash_kb": 1024, "ram_kb": 320, "ccm_kb": 0, "series": "F7"},
    "STM32F756ZG": {"flash_kb": 1024, "ram_kb": 320, "ccm_kb": 0, "series": "F7"},
    "STM32F767IG": {"flash_kb": 1024, "ram_kb": 512, "ccm_kb": 0, "series": "F7"},
    "STM32F767NI": {"flash_kb": 2048, "ram_kb": 512, "ccm_kb": 0, "series": "F7"},
    "STM32F767VG": {"flash_kb": 1024, "ram_kb": 512, "ccm_kb": 0, "series": "F7"},
    "STM32F767ZI": {"flash_kb": 2048, "ram_kb": 512, "ccm_kb": 0, "series": "F7"},
    "STM32F769AI": {"flash_kb": 2048, "ram_kb": 512, "ccm_kb": 0, "series": "F7"},
    "STM32F769BI": {"flash_kb": 2048, "ram_kb": 512, "ccm_kb": 0, "series": "F7"},
    "STM32F769IG": {"flash_kb": 1024, "ram_kb": 512, "ccm_kb": 0, "series": "F7"},
    "STM32F769NI": {"flash_kb": 2048, "ram_kb": 512, "ccm_kb": 0, "series": "F7"},
    # G0 系列
    "STM32G030C6": {"flash_kb": 32, "ram_kb": 8, "ccm_kb": 0, "series": "G0"},
    "STM32G030C8": {"flash_kb": 64, "ram_kb": 8, "ccm_kb": 0, "series": "G0"},
    "STM32G031C6": {"flash_kb": 32, "ram_kb": 8, "ccm_kb": 0, "series": "G0"},
    "STM32G031C8": {"flash_kb": 64, "ram_kb": 8, "ccm_kb": 0, "series": "G0"},
    "STM32G070CB": {"flash_kb": 128, "ram_kb": 36, "ccm_kb": 0, "series": "G0"},
    "STM32G071C8": {"flash_kb": 64, "ram_kb": 36, "ccm_kb": 0, "series": "G0"},
    "STM32G071CB": {"flash_kb": 128, "ram_kb": 36, "ccm_kb": 0, "series": "G0"},
    "STM32G0B1RE": {"flash_kb": 512, "ram_kb": 144, "ccm_kb": 0, "series": "G0"},
    # G4 系列
    "STM32G431C6": {"flash_kb": 32, "ram_kb": 32, "ccm_kb": 0, "series": "G4"},
    "STM32G431C8": {"flash_kb": 64, "ram_kb": 32, "ccm_kb": 0, "series": "G4"},
    "STM32G431CB": {"flash_kb": 128, "ram_kb": 32, "ccm_kb": 0, "series": "G4"},
    "STM32G431K8": {"flash_kb": 64, "ram_kb": 32, "ccm_kb": 0, "series": "G4"},
    "STM32G431M6": {"flash_kb": 32, "ram_kb": 32, "ccm_kb": 0, "series": "G4"},
    "STM32G431R6": {"flash_kb": 32, "ram_kb": 32, "ccm_kb": 0, "series": "G4"},
    "STM32G431R8": {"flash_kb": 64, "ram_kb": 32, "ccm_kb": 0, "series": "G4"},
    "STM32G441CB": {"flash_kb": 128, "ram_kb": 32, "ccm_kb": 0, "series": "G4"},
    "STM32G474CE": {"flash_kb": 512, "ram_kb": 128, "ccm_kb": 0, "series": "G4"},
    "STM32G474ME": {"flash_kb": 512, "ram_kb": 128, "ccm_kb": 0, "series": "G4"},
    "STM32G474PE": {"flash_kb": 512, "ram_kb": 128, "ccm_kb": 0, "series": "G4"},
    "STM32G474RE": {"flash_kb": 512, "ram_kb": 128, "ccm_kb": 0, "series": "G4"},
    "STM32G483CE": {"flash_kb": 512, "ram_kb": 128, "ccm_kb": 0, "series": "G4"},
    "STM32G484CE": {"flash_kb": 512, "ram_kb": 128, "ccm_kb": 0, "series": "G4"},
    # H7 系列
    "STM32H743VI": {"flash_kb": 2048, "ram_kb": 1024, "ccm_kb": 0, "series": "H7"},
    "STM32H743ZI": {"flash_kb": 2048, "ram_kb": 1024, "ccm_kb": 0, "series": "H7"},
    "STM32H743II": {"flash_kb": 2048, "ram_kb": 1024, "ccm_kb": 0, "series": "H7"},
    "STM32H743AI": {"flash_kb": 2048, "ram_kb": 1024, "ccm_kb": 0, "series": "H7"},
    "STM32H743BI": {"flash_kb": 2048, "ram_kb": 1024, "ccm_kb": 0, "series": "H7"},
    "STM32H743LI": {"flash_kb": 2048, "ram_kb": 1024, "ccm_kb": 0, "series": "H7"},
    "STM32H753VI": {"flash_kb": 2048, "ram_kb": 1024, "ccm_kb": 0, "series": "H7"},
    "STM32H753ZI": {"flash_kb": 2048, "ram_kb": 1024, "ccm_kb": 0, "series": "H7"},
    "STM32H750IB": {"flash_kb": 128, "ram_kb": 1024, "ccm_kb": 0, "series": "H7"},
    "STM32H750VB": {"flash_kb": 128, "ram_kb": 1024, "ccm_kb": 0, "series": "H7"},
    "STM32H7A3NI": {"flash_kb": 2048, "ram_kb": 1440, "ccm_kb": 0, "series": "H7"},
    "STM32H7A3II": {"flash_kb": 2048, "ram_kb": 1440, "ccm_kb": 0, "series": "H7"},
    "STM32H7B3LI": {"flash_kb": 2048, "ram_kb": 1440, "ccm_kb": 0, "series": "H7"},
    "STM32H7B3NI": {"flash_kb": 2048, "ram_kb": 1440, "ccm_kb": 0, "series": "H7"},
    "STM32H7B3RI": {"flash_kb": 2048, "ram_kb": 1440, "ccm_kb": 0, "series": "H7"},
    "STM32H7B3VI": {"flash_kb": 2048, "ram_kb": 1440, "ccm_kb": 0, "series": "H7"},
    "STM32H7B3ZI": {"flash_kb": 2048, "ram_kb": 1440, "ccm_kb": 0, "series": "H7"},
    # L0 系列
    "STM32L010C6": {"flash_kb": 32, "ram_kb": 8, "ccm_kb": 0, "series": "L0"},
    "STM32L010C8": {"flash_kb": 64, "ram_kb": 8, "ccm_kb": 0, "series": "L0"},
    "STM32L010F4": {"flash_kb": 16, "ram_kb": 2, "ccm_kb": 0, "series": "L0"},
    "STM32L010K4": {"flash_kb": 16, "ram_kb": 2, "ccm_kb": 0, "series": "L0"},
    "STM32L010K8": {"flash_kb": 64, "ram_kb": 8, "ccm_kb": 0, "series": "L0"},
    "STM32L010R8": {"flash_kb": 64, "ram_kb": 8, "ccm_kb": 0, "series": "L0"},
    # L4 系列
    "STM32L412C8": {"flash_kb": 64, "ram_kb": 40, "ccm_kb": 0, "series": "L4"},
    "STM32L412CB": {"flash_kb": 128, "ram_kb": 40, "ccm_kb": 0, "series": "L4"},
    "STM32L476RE": {"flash_kb": 512, "ram_kb": 128, "ccm_kb": 0, "series": "L4"},
    "STM32L476RG": {"flash_kb": 1024, "ram_kb": 128, "ccm_kb": 0, "series": "L4"},
    "STM32L496RE": {"flash_kb": 512, "ram_kb": 320, "ccm_kb": 0, "series": "L4"},
    "STM32L496RG": {"flash_kb": 1024, "ram_kb": 320, "ccm_kb": 0, "series": "L4"},
    # U5 系列
    "STM32U575CI": {"flash_kb": 2048, "ram_kb": 786, "ccm_kb": 0, "series": "U5"},
    "STM32U575RI": {"flash_kb": 2048, "ram_kb": 786, "ccm_kb": 0, "series": "U5"},
    "STM32U585AI": {"flash_kb": 2048, "ram_kb": 786, "ccm_kb": 0, "series": "U5"},
    "STM32U585RI": {"flash_kb": 2048, "ram_kb": 786, "ccm_kb": 0, "series": "U5"},
    # WB 系列
    "STM32WB55CC": {"flash_kb": 256, "ram_kb": 256, "ccm_kb": 0, "series": "WB"},
    "STM32WB55CE": {"flash_kb": 512, "ram_kb": 256, "ccm_kb": 0, "series": "WB"},
    "STM32WB55CG": {"flash_kb": 1024, "ram_kb": 256, "ccm_kb": 0, "series": "WB"},
    "STM32WB55RG": {"flash_kb": 1024, "ram_kb": 256, "ccm_kb": 0, "series": "WB"},
    # WL 系列
    "STM32WLE4C8": {"flash_kb": 64, "ram_kb": 64, "ccm_kb": 0, "series": "WL"},
    "STM32WLE4CB": {"flash_kb": 128, "ram_kb": 64, "ccm_kb": 0, "series": "WL"},
    "STM32WLE4CC": {"flash_kb": 256, "ram_kb": 64, "ccm_kb": 0, "series": "WL"},
    "STM32WLE5C8": {"flash_kb": 64, "ram_kb": 64, "ccm_kb": 0, "series": "WL"},
    "STM32WLE5CB": {"flash_kb": 128, "ram_kb": 64, "ccm_kb": 0, "series": "WL"},
    "STM32WLE5CC": {"flash_kb": 256, "ram_kb": 64, "ccm_kb": 0, "series": "WL"},
}


def lookup_chip(device: str) -> dict | None:
    """从芯片型号查找 Flash/RAM 容量。

    Args:
        device: 芯片型号（如 "STM32F407VETx"）

    Returns:
        芯片信息字典，未找到返回 None
    """
    import re

    # 清理型号：去掉尾部的 x/T6/Tx 等封装后缀
    clean = device.upper().strip()
    for suffix in ["X", "TX", "T6", "P", "Y"]:
        if clean.endswith(suffix) and len(clean) > 10:
            clean = clean[:-len(suffix)]

    # 精确匹配
    if clean in CHIP_DB:
        return {**CHIP_DB[clean], "matched": clean}

    # 模糊匹配：去掉最后的字母
    for length in [len(clean)-1, len(clean)-2]:
        prefix = clean[:length]
        for key, val in CHIP_DB.items():
            if key.startswith(prefix):
                return {**val, "matched": key, "fuzzy": True}

    # 从型号字符串推断系列
    m = re.match(r"STM32([A-Z]\d)", clean)
    if m:
        series = m.group(1)
        return {"flash_kb": 0, "ram_kb": 0, "ccm_kb": 0, "series": series, "matched": None, "inferred": True}

    return None


# === 输出格式化 ===

def output_json(data: dict):
    """输出 JSON 到 stdout。"""
    json.dump(data, sys.stdout, indent=2, ensure_ascii=False)
    print()


def output_text(data: dict, indent: int = 0):
    """输出人类可读的文本格式。"""
    prefix = "  " * indent
    for key, value in data.items():
        if isinstance(value, dict):
            print(f"{prefix}{key}:")
            output_text(value, indent + 1)
        elif isinstance(value, list):
            print(f"{prefix}{key}: [{len(value)} items]")
            for i, item in enumerate(value[:5]):  # 最多显示 5 个
                if isinstance(item, dict):
                    print(f"{prefix}  [{i}]:")
                    output_text(item, indent + 2)
                else:
                    print(f"{prefix}  [{i}]: {item}")
            if len(value) > 5:
                print(f"{prefix}  ... ({len(value) - 5} more)")
        else:
            print(f"{prefix}{key}: {value}")


def output_result(data: dict, args):
    """统一输出格式化。根据 --text 参数选择格式。

    Args:
        data: 要输出的数据
        args: argparse 解析结果（检查 --text 标志）
    """
    if hasattr(args, 'text') and args.text:
        output_text(data)
    else:
        output_json(data)


def add_output_argument(parser):
    """给 argparse 解析器添加 --text 参数。"""
    parser.add_argument(
        "--text",
        action="store_true",
        help="输出人类可读文本格式（默认输出 JSON）",
    )


# === 子进程调用 ===

def run_script(script_name: str, args: list[str], timeout: int = 300,
               script_dir: str | None = None) -> dict:
    """运行子脚本。

    Args:
        script_name: 脚本文件名（如 "check_elf.py"）
        args: 命令行参数列表
        timeout: 超时秒数
        script_dir: 脚本目录（默认为调用者所在目录）

    Returns:
        {"success": bool, "stdout": str, "stderr": str, "returncode": int}
    """
    if script_dir is None:
        script_dir = str(Path(__file__).parent)
    script_path = Path(script_dir) / script_name

    if not script_path.exists():
        return {"success": False, "error": f"{script_name} 不存在"}

    cmd = [sys.executable, str(script_path)] + args

    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        return {
            "success": proc.returncode == 0,
            "stdout": proc.stdout,
            "stderr": proc.stderr,
            "returncode": proc.returncode,
        }
    except subprocess.TimeoutExpired:
        return {"success": False, "error": f"{script_name} 超时 ({timeout}s)"}
    except FileNotFoundError:
        return {"success": False, "error": "Python 未找到"}


def parse_json_output(text: str) -> dict | None:
    """从脚本输出中提取 JSON。

    Args:
        text: 脚本输出文本

    Returns:
        解析后的字典，失败返回 None
    """
    for i, ch in enumerate(text):
        if ch in "{[":
            try:
                return json.loads(text[i:])
            except json.JSONDecodeError:
                continue
    return None


# === 通用参数 ===

def add_uv4_argument(parser):
    """给 argparse 解析器添加 --uv4 参数。"""
    parser.add_argument("--uv4", help="UV4.exe 路径（默认自动查找）")


def add_auto_argument(parser):
    """给 argparse 解析器添加 --auto 参数。"""
    parser.add_argument(
        "--auto",
        metavar="PROJECT_DIR",
        help="自动检测项目配置（指定项目根目录，自动推断 --uv4, --project, --src-dir 等参数）",
    )


def apply_auto_config(args, parser) -> None:
    """应用 --auto 检测到的配置到 args 中（仅填充未指定的参数）。

    Args:
        args: argparse 解析结果
        parser: argparse 解析器
    """
    if not hasattr(args, "auto") or not args.auto:
        return

    try:
        from auto_detect import auto_detect_config, resolve_paths
        config = auto_detect_config(args.auto)
        if not config:
            print(f"Warning: Auto-detect failed for {args.auto}", file=sys.stderr)
            return
        paths = resolve_paths(config, args.auto)
    except ImportError:
        return

    # 仅填充未指定的参数
    if hasattr(args, "uv4") and not args.uv4 and "uv4_path" in paths:
        args.uv4 = paths["uv4_path"]

    if hasattr(args, "project") and not args.project and "project_file" in paths:
        args.project = paths["project_file"]

    if hasattr(args, "elf") and not args.elf and "elf_path" in paths:
        args.elf = paths["elf_path"]

    if hasattr(args, "src_dir") and not args.src_dir and "src_dir" in paths:
        args.src_dir = paths["src_dir"]

    if hasattr(args, "chip") and not args.chip and "chip" in paths:
        args.chip = paths["chip"]

    if hasattr(args, "target") and not args.target and "target" in paths:
        args.target = paths["target"]


# === 工具函数 ===

def format_size(size_bytes: int) -> str:
    """格式化文件大小。

    Args:
        size_bytes: 字节数

    Returns:
        格式化的字符串（如 "1.5 KB", "2.3 MB"）
    """
    for unit in ["B", "KB", "MB", "GB"]:
        if size_bytes < 1024:
            return f"{size_bytes:.1f} {unit}"
        size_bytes /= 1024
    return f"{size_bytes:.1f} TB"


def find_project_root(start_path: str = ".") -> str | None:
    """查找项目根目录（包含 .uvprojx 或 .ioc 文件的目录）。

    Args:
        start_path: 起始路径

    Returns:
        项目根目录路径，未找到返回 None
    """
    path = Path(start_path).resolve()

    # 向上查找
    for parent in [path] + list(path.parents):
        # 检查是否有项目文件
        if list(parent.glob("*.uvprojx")) or list(parent.glob("*.ioc")):
            return str(parent)
        # 检查是否有 MDK-ARM 目录
        if (parent / "MDK-ARM").is_dir():
            return str(parent)

    return None


def check_tool_available(tool_name: str) -> bool:
    """检查工具是否可用。

    Args:
        tool_name: 工具名称（如 "UV4", "fromelf"）

    Returns:
        是否可用
    """
    import shutil
    return shutil.which(tool_name) is not None


def get_timestamp() -> str:
    """获取当前时间戳字符串。

    Returns:
        ISO 格式的时间戳
    """
    from datetime import datetime
    return datetime.now().isoformat()


def create_result(success: bool, data: dict = None, errors: list = None,
                  warnings: list = None) -> dict:
    """创建标准结果字典。

    Args:
        success: 是否成功
        data: 数据
        errors: 错误列表
        warnings: 警告列表

    Returns:
        标准格式的结果字典
    """
    return {
        "success": success,
        "data": data or {},
        "errors": errors or [],
        "warnings": warnings or [],
        "timestamp": get_timestamp(),
    }


# === 验证函数 ===

def validate_elf_path(elf_path: str) -> tuple[bool, str]:
    """验证 ELF 文件路径。

    Args:
        elf_path: ELF 文件路径

    Returns:
        (是否有效, 错误信息)
    """
    if not elf_path:
        return False, "ELF 文件路径为空"

    path = Path(elf_path)
    if not path.exists():
        return False, f"ELF 文件不存在: {elf_path}"

    if not path.suffix.lower() in (".axf", ".elf", ".out"):
        return False, f"文件扩展名不是 .axf/.elf/.out: {path.suffix}"

    if path.stat().st_size == 0:
        return False, f"ELF 文件为空: {elf_path}"

    return True, ""


def validate_uv4_path(uv4_path: str) -> tuple[bool, str]:
    """验证 UV4.exe 路径。

    Args:
        uv4_path: UV4.exe 路径

    Returns:
        (是否有效, 错误信息)
    """
    if not uv4_path:
        return False, "UV4.exe 路径为空"

    path = Path(uv4_path)
    if not path.exists():
        return False, f"UV4.exe 不存在: {uv4_path}"

    if not path.name.lower() in ("uv4.exe", "uv4"):
        return False, f"文件名不是 UV4.exe: {path.name}"

    return True, ""


def validate_project_dir(project_dir: str) -> tuple[bool, str, list[str]]:
    """验证项目目录。

    Args:
        project_dir: 项目目录路径

    Returns:
        (是否有效, 错误信息, 警告列表)
    """
    warnings = []

    if not project_dir:
        return False, "项目目录路径为空", warnings

    path = Path(project_dir)
    if not path.exists():
        return False, f"目录不存在: {project_dir}", warnings

    if not path.is_dir():
        return False, f"不是目录: {project_dir}", warnings

    # 检查是否有项目文件
    uvprojx_files = list(path.glob("*.uvprojx"))
    ioc_files = list(path.glob("*.ioc"))

    if not uvprojx_files and not ioc_files:
        warnings.append("目录中没有 .uvprojx 或 .ioc 文件")

    return True, "", warnings


# === JSON 输出 ===

def print_json(data: any, pretty: bool = True) -> None:
    """输出 JSON 到 stdout。

    Args:
        data: 要输出的数据
        pretty: 是否格式化
    """
    setup_encoding()
    if pretty:
        json.dump(data, sys.stdout, indent=2, ensure_ascii=False)
    else:
        json.dump(data, sys.stdout, ensure_ascii=False)
    print()


def print_result(result: dict, text_mode: bool = False) -> None:
    """输出结果（JSON 或文本格式）。

    Args:
        result: 结果字典
        text_mode: 是否使用文本模式
    """
    setup_encoding()

    if text_mode:
        # 文本模式
        if result.get("success"):
            print("✅ 成功")
        else:
            print("❌ 失败")

        if "error" in result:
            print(f"  错误: {result['error']}")
        if "suggestion" in result:
            print(f"  建议: {result['suggestion']}")
        if "warnings" in result:
            for w in result["warnings"]:
                print(f"  ⚠️ {w}")

        # 输出数据
        if "data" in result and result["data"]:
            print("\n数据:")
            for key, value in result["data"].items():
                print(f"  {key}: {value}")
    else:
        # JSON 模式
        print_json(result)


# === 文件操作 ===

def read_json_file(file_path: str) -> dict | None:
    """读取 JSON 文件。

    Args:
        file_path: 文件路径

    Returns:
        解析后的字典，失败返回 None
    """
    try:
        path = Path(file_path)
        if not path.exists():
            return None
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None


def write_json_file(file_path: str, data: dict, pretty: bool = True) -> bool:
    """写入 JSON 文件。

    Args:
        file_path: 文件路径
        data: 要写入的数据
        pretty: 是否格式化

    Returns:
        是否成功
    """
    try:
        path = Path(file_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            if pretty:
                json.dump(data, f, indent=2, ensure_ascii=False)
            else:
                json.dump(data, f, ensure_ascii=False)
        return True
    except OSError:
        return False


def read_text_file(file_path: str, encoding: str = "utf-8") -> str | None:
    """读取文本文件。

    Args:
        file_path: 文件路径
        encoding: 编码

    Returns:
        文件内容，失败返回 None
    """
    try:
        path = Path(file_path)
        if not path.exists():
            return None
        return path.read_text(encoding=encoding, errors="replace")
    except OSError:
        return None


# === 路径操作 ===

def ensure_dir(dir_path: str) -> bool:
    """确保目录存在。

    Args:
        dir_path: 目录路径

    Returns:
        是否成功
    """
    try:
        Path(dir_path).mkdir(parents=True, exist_ok=True)
        return True
    except OSError:
        return False


def safe_filename(filename: str) -> str:
    """生成安全的文件名（移除特殊字符）。

    Args:
        filename: 原始文件名

    Returns:
        安全的文件名
    """
    import re
    # 替换特殊字符为下划线
    safe = re.sub(r'[<>:"/\\|?*]', '_', filename)
    # 移除前后空格
    safe = safe.strip()
    # 确保不为空
    return safe or "unnamed"


# === 配置验证 ===

def validate_config(config: dict) -> tuple[bool, list[str], list[str]]:
    """验证项目配置。

    Args:
        config: 配置字典

    Returns:
        (是否有效, 错误列表, 警告列表)
    """
    errors = []
    warnings = []

    # 检查必需字段
    required_fields = ["project_dir"]
    for field in required_fields:
        if field not in config:
            errors.append(f"缺少必需字段: {field}")

    # 检查路径字段
    path_fields = ["uv4_path", "project_file", "elf_path"]
    for field in path_fields:
        if field in config and config[field]:
            path = Path(config[field])
            if not path.exists():
                warnings.append(f"{field} 路径不存在: {config[field]}")

    # 检查芯片信息
    if "chip" in config:
        chip = config["chip"]
        if not chip.startswith("STM32"):
            warnings.append(f"芯片名称可能不正确: {chip}")

    return len(errors) == 0, errors, warnings


def get_config_summary(config: dict) -> str:
    """获取配置摘要。

    Args:
        config: 配置字典

    Returns:
        配置摘要字符串
    """
    lines = []
    lines.append(f"项目目录: {config.get('project_dir', 'N/A')}")
    lines.append(f"芯片: {config.get('device', config.get('chip', 'N/A'))}")
    lines.append(f"系列: {config.get('series', 'N/A')}")
    lines.append(f"Flash: {config.get('flash_kb', 'N/A')} KB")
    lines.append(f"RAM: {config.get('ram_kb', 'N/A')} KB")

    if config.get("uv4_path"):
        lines.append(f"UV4: {config['uv4_path']}")
    if config.get("project_file"):
        lines.append(f"项目: {config['project_file']}")
    if config.get("elf_path"):
        lines.append(f"ELF: {config['elf_path']}")

    return "\n".join(lines)
