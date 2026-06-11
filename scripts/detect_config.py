#!/usr/bin/env python
"""STM32 项目配置自动检测工具。

从 Keil (.uvprojx)、STM32CubeIDE (.ioc/.project)、IAR (.eww/.ewp) 项目文件中
自动提取芯片型号、编译器、优化设置、源码目录等配置。

用法:
  python detect_config.py --project MDK-ARM/project.uvprojx
  python detect_config.py --project .project --ioc .ioc
  python detect_config.py --scan .  # 自动查找项目文件

输出 JSON 到 stdout，包含标准化的项目配置。
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import xml.etree.ElementTree as ET
from pathlib import Path


# === STM32 芯片数据库 ===

# 从芯片型号推断 Flash/RAM 容量
# 格式: 前缀 -> (flash_kb, ram_kb, ccm_kb, series)
CHIP_DB = {
    # F1 系列
    "STM32F103C6": (32, 10, 0, "F1"), "STM32F103C8": (64, 20, 0, "F1"),
    "STM32F103CB": (128, 20, 0, "F1"), "STM32F103R6": (32, 10, 0, "F1"),
    "STM32F103R8": (64, 20, 0, "F1"), "STM32F103RB": (128, 20, 0, "F1"),
    "STM32F103RC": (256, 48, 0, "F1"), "STM32F103RE": (512, 64, 0, "F1"),
    "STM32F103VE": (512, 64, 0, "F1"), "STM32F103ZE": (512, 64, 0, "F1"),
    "STM32F105R8": (64, 64, 0, "F1"), "STM32F105RB": (128, 64, 0, "F1"),
    "STM32F107RC": (256, 64, 0, "F1"),
    # F2 系列
    "STM32F205RG": (1024, 128, 0, "F2"), "STM32F207IG": (1024, 128, 0, "F2"),
    # F3 系列
    "STM32F303K8": (64, 16, 0, "F3"), "STM32F303RE": (512, 64, 0, "F3"),
    "STM32F303VE": (512, 64, 0, "F3"), "STM32F334R8": (64, 16, 0, "F3"),
    # F4 系列
    "STM32F401CB": (128, 64, 0, "F4"), "STM32F401CC": (256, 64, 0, "F4"),
    "STM32F401CD": (384, 64, 0, "F4"), "STM32F401CE": (512, 96, 0, "F4"),
    "STM32F405RG": (1024, 192, 64, "F4"), "STM32F407VE": (512, 192, 64, "F4"),
    "STM32F407VG": (1024, 192, 64, "F4"), "STM32F407IE": (512, 192, 64, "F4"),
    "STM32F407IG": (1024, 192, 64, "F4"), "STM32F410RB": (128, 32, 0, "F4"),
    "STM32F411CE": (512, 128, 0, "F4"), "STM32F411RE": (512, 128, 0, "F4"),
    "STM32F412RE": (512, 256, 0, "F4"), "STM32F413RH": (1536, 320, 0, "F4"),
    "STM32F415RG": (1024, 192, 64, "F4"), "STM32F417VE": (512, 192, 64, "F4"),
    "STM32F417VG": (1024, 192, 64, "F4"), "STM32F417IE": (512, 192, 64, "F4"),
    "STM32F417IG": (1024, 192, 64, "F4"), "STM32F427IG": (1024, 256, 64, "F4"),
    "STM32F427VG": (1024, 256, 64, "F4"), "STM32F429BI": (2048, 256, 64, "F4"),
    "STM32F429IG": (2048, 256, 64, "F4"), "STM32F429NI": (2048, 256, 64, "F4"),
    "STM32F429VI": (2048, 256, 64, "F4"), "STM32F429ZI": (2048, 256, 64, "F4"),
    "STM32F437IG": (1024, 256, 64, "F4"), "STM32F439BI": (2048, 256, 64, "F4"),
    "STM32F439IG": (2048, 256, 64, "F4"), "STM32F439NI": (2048, 256, 64, "F4"),
    "STM32F439VI": (2048, 256, 64, "F4"), "STM32F439ZI": (2048, 256, 64, "F4"),
    "STM32F446RE": (512, 128, 64, "F4"), "STM32F446RC": (256, 128, 64, "F4"),
    "STM32F446VE": (512, 128, 64, "F4"), "STM32F446ZE": (512, 128, 64, "F4"),
    "STM32F469AI": (2048, 384, 64, "F4"), "STM32F469BI": (2048, 384, 64, "F4"),
    "STM32F469IG": (1024, 384, 64, "F4"), "STM32F469NI": (2048, 384, 64, "F4"),
    # F7 系列
    "STM32F722RE": (512, 256, 0, "F7"), "STM32F723IE": (512, 256, 0, "F7"),
    "STM32F746VE": (512, 320, 0, "F7"), "STM32F746VG": (1024, 320, 0, "F7"),
    "STM32F746ZE": (512, 320, 0, "F7"), "STM32F746ZG": (1024, 320, 0, "F7"),
    "STM32F756VG": (1024, 320, 0, "F7"), "STM32F756ZG": (1024, 320, 0, "F7"),
    "STM32F767IG": (1024, 512, 0, "F7"), "STM32F767NI": (2048, 512, 0, "F7"),
    "STM32F767VG": (1024, 512, 0, "F7"), "STM32F767ZI": (2048, 512, 0, "F7"),
    "STM32F769AI": (2048, 512, 0, "F7"), "STM32F769BI": (2048, 512, 0, "F7"),
    "STM32F769IG": (1024, 512, 0, "F7"), "STM32F769NI": (2048, 512, 0, "F7"),
    # G0 系列
    "STM32G030C6": (32, 8, 0, "G0"), "STM32G030C8": (64, 8, 0, "G0"),
    "STM32G031C6": (32, 8, 0, "G0"), "STM32G031C8": (64, 8, 0, "G0"),
    "STM32G070CB": (128, 36, 0, "G0"), "STM32G071C8": (64, 36, 0, "G0"),
    "STM32G071CB": (128, 36, 0, "G0"), "STM32G0B1RE": (512, 144, 0, "G0"),
    # G4 系列
    "STM32G431C6": (32, 32, 0, "G4"), "STM32G431C8": (64, 32, 0, "G4"),
    "STM32G431CB": (128, 32, 0, "G4"), "STM32G431K8": (64, 32, 0, "G4"),
    "STM32G431M6": (32, 32, 0, "G4"), "STM32G431R6": (32, 32, 0, "G4"),
    "STM32G431R8": (64, 32, 0, "G4"), "STM32G441CB": (128, 32, 0, "G4"),
    "STM32G474CE": (512, 128, 0, "G4"), "STM32G474ME": (512, 128, 0, "G4"),
    "STM32G474PE": (512, 128, 0, "G4"), "STM32G474RE": (512, 128, 0, "G4"),
    "STM32G483CE": (512, 128, 0, "G4"), "STM32G484CE": (512, 128, 0, "G4"),
    # H7 系列
    "STM32H743VI": (2048, 1024, 0, "H7"), "STM32H743ZI": (2048, 1024, 0, "H7"),
    "STM32H743II": (2048, 1024, 0, "H7"), "STM32H743AI": (2048, 1024, 0, "H7"),
    "STM32H743BI": (2048, 1024, 0, "H7"), "STM32H743LI": (2048, 1024, 0, "H7"),
    "STM32H753VI": (2048, 1024, 0, "H7"), "STM32H753ZI": (2048, 1024, 0, "H7"),
    "STM32H750IB": (128, 1024, 0, "H7"), "STM32H750VB": (128, 1024, 0, "H7"),
    "STM32H7A3NI": (2048, 1440, 0, "H7"), "STM32H7A3II": (2048, 1440, 0, "H7"),
    "STM32H7B3LI": (2048, 1440, 0, "H7"), "STM32H7B3NI": (2048, 1440, 0, "H7"),
    "STM32H7B3RI": (2048, 1440, 0, "H7"), "STM32H7B3VI": (2048, 1440, 0, "H7"),
    "STM32H7B3ZI": (2048, 1440, 0, "H7"),
    # L0 系列
    "STM32L010C6": (32, 8, 0, "L0"), "STM32L010C8": (64, 8, 0, "L0"),
    "STM32L010F4": (16, 2, 0, "L0"), "STM32L010K4": (16, 2, 0, "L0"),
    "STM32L010K8": (64, 8, 0, "L0"), "STM32L010R8": (64, 8, 0, "L0"),
    "STM32L011C3": (8, 2, 0, "L0"), "STM32L011C4": (16, 2, 0, "L0"),
    "STM32L011E3": (8, 2, 0, "L0"), "STM32L011E4": (16, 2, 0, "L0"),
    "STM32L011F3": (8, 2, 0, "L0"), "STM32L011F4": (16, 2, 0, "L0"),
    "STM32L011G3": (8, 2, 0, "L0"), "STM32L011G4": (16, 2, 0, "L0"),
    "STM32L011K3": (8, 2, 0, "L0"), "STM32L011K4": (16, 2, 0, "L0"),
    "STM32L021C4": (16, 2, 0, "L0"), "STM32L021D4": (16, 2, 0, "L0"),
    "STM32L021F4": (16, 2, 0, "L0"), "STM32L021G4": (16, 2, 0, "L0"),
    "STM32L021K4": (16, 2, 0, "L0"),
    # L4 系列
    "STM32L412C8": (64, 40, 0, "L4"), "STM32L412CB": (128, 40, 0, "L4"),
    "STM32L412K8": (64, 40, 0, "L4"), "STM32L412KB": (128, 40, 0, "L4"),
    "STM32L412R8": (64, 40, 0, "L4"), "STM32L412RB": (128, 40, 0, "L4"),
    "STM32L412T8": (64, 40, 0, "L4"), "STM32L412TB": (128, 40, 0, "L4"),
    "STM32L431CB": (128, 64, 0, "L4"), "STM32L431CC": (256, 64, 0, "L4"),
    "STM32L431KB": (128, 64, 0, "L4"), "STM32L431KC": (256, 64, 0, "L4"),
    "STM32L431RB": (128, 64, 0, "L4"), "STM32L431RC": (256, 64, 0, "L4"),
    "STM32L432KC": (256, 64, 0, "L4"), "STM32L433CB": (128, 64, 0, "L4"),
    "STM32L433CC": (256, 64, 0, "L4"), "STM32L433RC": (256, 64, 0, "L4"),
    "STM32L433VC": (256, 64, 0, "L4"), "STM32L442KC": (256, 64, 0, "L4"),
    "STM32L443CC": (256, 64, 0, "L4"), "STM32L443RC": (256, 64, 0, "L4"),
    "STM32L443VC": (256, 64, 0, "L4"), "STM32L451CC": (256, 160, 0, "L4"),
    "STM32L451CE": (512, 160, 0, "L4"), "STM32L451RC": (256, 160, 0, "L4"),
    "STM32L451RE": (512, 160, 0, "L4"), "STM32L451VC": (256, 160, 0, "L4"),
    "STM32L451VE": (512, 160, 0, "L4"), "STM32L452CC": (256, 160, 0, "L4"),
    "STM32L452CE": (512, 160, 0, "L4"), "STM32L452RC": (256, 160, 0, "L4"),
    "STM32L452RE": (512, 160, 0, "L4"), "STM32L462CE": (512, 160, 0, "L4"),
    "STM32L471QE": (512, 128, 0, "L4"), "STM32L471QG": (1024, 128, 0, "L4"),
    "STM32L471RE": (512, 128, 0, "L4"), "STM32L471RG": (1024, 128, 0, "L4"),
    "STM32L471VE": (512, 128, 0, "L4"), "STM32L471VG": (1024, 128, 0, "L4"),
    "STM32L471ZE": (512, 128, 0, "L4"), "STM32L471ZG": (1024, 128, 0, "L4"),
    "STM32L475RC": (256, 128, 0, "L4"), "STM32L475RE": (512, 128, 0, "L4"),
    "STM32L475RG": (1024, 128, 0, "L4"), "STM32L475VC": (256, 128, 0, "L4"),
    "STM32L475VE": (512, 128, 0, "L4"), "STM32L475VG": (1024, 128, 0, "L4"),
    "STM32L476JE": (512, 128, 0, "L4"), "STM32L476JG": (1024, 128, 0, "L4"),
    "STM32L476ME": (512, 128, 0, "L4"), "STM32L476MG": (1024, 128, 0, "L4"),
    "STM32L476QE": (512, 128, 0, "L4"), "STM32L476QG": (1024, 128, 0, "L4"),
    "STM32L476RE": (512, 128, 0, "L4"), "STM32L476RG": (1024, 128, 0, "L4"),
    "STM32L476VE": (512, 128, 0, "L4"), "STM32L476VG": (1024, 128, 0, "L4"),
    "STM32L476ZE": (512, 128, 0, "L4"), "STM32L476ZG": (1024, 128, 0, "L4"),
    "STM32L496AE": (512, 320, 0, "L4"), "STM32L496AG": (1024, 320, 0, "L4"),
    "STM32L496QE": (512, 320, 0, "L4"), "STM32L496QG": (1024, 320, 0, "L4"),
    "STM32L496RE": (512, 320, 0, "L4"), "STM32L496RG": (1024, 320, 0, "L4"),
    "STM32L496VE": (512, 320, 0, "L4"), "STM32L496VG": (1024, 320, 0, "L4"),
    "STM32L496ZE": (512, 320, 0, "L4"), "STM32L496ZG": (1024, 320, 0, "L4"),
    "STM32L4A6AG": (1024, 320, 0, "L4"), "STM32L4A6QG": (1024, 320, 0, "L4"),
    "STM32L4A6RG": (1024, 320, 0, "L4"), "STM32L4A6VG": (1024, 320, 0, "L4"),
    "STM32L4A6ZG": (1024, 320, 0, "L4"),
    # L5 系列
    "STM32L552CC": (256, 256, 0, "L5"), "STM32L552CE": (512, 256, 0, "L5"),
    "STM32L552ME": (512, 256, 0, "L5"), "STM32L552QC": (256, 256, 0, "L5"),
    "STM32L552QE": (512, 256, 0, "L5"), "STM32L552RC": (256, 256, 0, "L5"),
    "STM32L552RE": (512, 256, 0, "L5"), "STM32L552TC": (256, 256, 0, "L5"),
    "STM32L552TE": (512, 256, 0, "L5"), "STM32L552VC": (256, 256, 0, "L5"),
    "STM32L552VE": (512, 256, 0, "L5"), "STM32L552ZC": (256, 256, 0, "L5"),
    "STM32L552ZE": (512, 256, 0, "L5"), "STM32L562CE": (512, 256, 0, "L5"),
    "STM32L562ME": (512, 256, 0, "L5"), "STM32L562QE": (512, 256, 0, "L5"),
    "STM32L562RE": (512, 256, 0, "L5"), "STM32L562TE": (512, 256, 0, "L5"),
    "STM32L562VE": (512, 256, 0, "L5"), "STM32L562ZE": (512, 256, 0, "L5"),
    # U5 系列
    "STM32U575CI": (2048, 786, 0, "U5"), "STM32U575OI": (2048, 786, 0, "U5"),
    "STM32U575QI": (2048, 786, 0, "U5"), "STM32U575RI": (2048, 786, 0, "U5"),
    "STM32U575VI": (2048, 786, 0, "U5"), "STM32U575ZI": (2048, 786, 0, "U5"),
    "STM32U585AI": (2048, 786, 0, "U5"), "STM32U585CI": (2048, 786, 0, "U5"),
    "STM32U585OI": (2048, 786, 0, "U5"), "STM32U585QI": (2048, 786, 0, "U5"),
    "STM32U585RI": (2048, 786, 0, "U5"), "STM32U585VI": (2048, 786, 0, "U5"),
    "STM32U585ZI": (2048, 786, 0, "U5"),
    # WB 系列
    "STM32WB10CC": (328, 48, 0, "WB"), "STM32WB15CC": (328, 48, 0, "WB"),
    "STM32WB30CE": (512, 96, 0, "WB"), "STM32WB35CC": (256, 96, 0, "WB"),
    "STM32WB35CE": (512, 96, 0, "WB"), "STM32WB50CG": (1024, 256, 0, "WB"),
    "STM32WB55CC": (256, 256, 0, "WB"), "STM32WB55CE": (512, 256, 0, "WB"),
    "STM32WB55CG": (1024, 256, 0, "WB"), "STM32WB55RG": (1024, 256, 0, "WB"),
    "STM32WB55VC": (256, 256, 0, "WB"), "STM32WB55VE": (512, 256, 0, "WB"),
    "STM32WB55VG": (1024, 256, 0, "WB"), "STM32WB55VY": (1024, 256, 0, "WB"),
    # WL 系列
    "STM32WLE4C8": (64, 64, 0, "WL"), "STM32WLE4CB": (128, 64, 0, "WL"),
    "STM32WLE4CC": (256, 64, 0, "WL"), "STM32WLE4J8": (64, 64, 0, "WL"),
    "STM32WLE4JB": (128, 64, 0, "WL"), "STM32WLE4JC": (256, 64, 0, "WL"),
    "STM32WLE5C8": (64, 64, 0, "WL"), "STM32WLE5CB": (128, 64, 0, "WL"),
    "STM32WLE5CC": (256, 64, 0, "WL"), "STM32WLE5J8": (64, 64, 0, "WL"),
    "STM32WLE5JB": (128, 64, 0, "WL"), "STM32WLE5JC": (256, 64, 0, "WL"),
}


def lookup_chip(device: str) -> dict | None:
    """从芯片型号查找 Flash/RAM 容量。"""
    # 清理型号：去掉尾部的 x/T6/Tx 等封装后缀
    clean = device.upper().strip()
    # 去掉尾部的 x/Tx/T6/6 等
    for suffix in ["X", "TX", "T6", "P", "Y"]:
        if clean.endswith(suffix) and len(clean) > 10:
            clean = clean[:-len(suffix)]

    # 精确匹配
    if clean in CHIP_DB:
        flash, ram, ccm, series = CHIP_DB[clean]
        return {"flash_kb": flash, "ram_kb": ram, "ccm_kb": ccm, "series": series, "matched": clean}

    # 模糊匹配：去掉最后的字母
    for length in [len(clean)-1, len(clean)-2]:
        prefix = clean[:length]
        for key, val in CHIP_DB.items():
            if key.startswith(prefix):
                flash, ram, ccm, series = val
                return {"flash_kb": flash, "ram_kb": ram, "ccm_kb": ccm, "series": series, "matched": key, "fuzzy": True}

    # 从型号字符串推断系列
    m = re.match(r"STM32([A-Z]\d)", clean)
    if m:
        series = m.group(1)
        return {"flash_kb": 0, "ram_kb": 0, "ccm_kb": 0, "series": series, "matched": None, "inferred": True}

    return None


# === Keil .uvprojx 解析 ===

def detect_keil(project_path: Path) -> dict:
    """从 Keil .uvprojx 文件提取配置。"""
    config = {"ide": "keil", "project_file": str(project_path)}

    try:
        tree = ET.parse(project_path)
        root = tree.getroot()
    except (ET.ParseError, OSError) as e:
        config["error"] = f"XML parse error: {e}"
        return config

    # 芯片型号
    for elem in root.iter("Device"):
        if elem.text:
            config["device"] = elem.text.strip()
            break

    # Target 名称
    for elem in root.iter("TargetName"):
        if elem.text:
            config["target_name"] = elem.text.strip()
            break

    # 编译器设置
    for cads in root.iter("Cads"):
        for child in cads:
            if child.tag == "Optim" and child.text:
                config["optim_level"] = int(child.text) if child.text.isdigit() else child.text
            elif child.tag == "oTime" and child.text:
                config["optim_target"] = "time" if child.text == "1" else "size"
            elif child.tag == "OneElfS" and child.text:
                config["one_elf_per_function"] = child.text == "1"
            elif child.tag == "v6Lto" and child.text:
                config["lto_enabled"] = child.text == "1"
            elif child.tag == "wLevel" and child.text:
                config["warning_level"] = int(child.text)
            elif child.tag == "uC99" and child.text:
                config["c_standard"] = "C99" if child.text == "1" else "C90"
            elif child.tag == "uAC6" and child.text:
                config["compiler"] = "ARMClang" if child.text == "1" else "ARMCC"
            elif child.tag == "Define" and child.text:
                config["defines"] = [d.strip() for d in child.text.split(",")]
            elif child.tag == "IncludePath" and child.text:
                config["include_paths"] = [p.strip() for p in child.text.split(";") if p.strip()]
        break

    # 输出目录
    for elem in root.iter("OutputDirectory"):
        if elem.text:
            config["output_dir"] = elem.text.strip()
            break

    # 输出文件名
    for elem in root.iter("OutputName"):
        if elem.text:
            config["output_name"] = elem.text.strip()
            break

    # 源文件列表
    source_files = []
    for elem in root.iter("FilePath"):
        if elem.text and elem.text.strip().endswith((".c", ".s", ".C", ".S")):
            source_files.append(elem.text.strip())
    config["source_files"] = source_files

    # 芯片信息
    if "device" in config:
        chip_info = lookup_chip(config["device"])
        if chip_info:
            config["chip_info"] = chip_info

    return config


# === STM32CubeIDE .ioc 解析 ===

def detect_cubeide(project_dir: Path) -> dict:
    """从 STM32CubeIDE 项目文件提取配置。"""
    config = {"ide": "cubeide"}

    # 查找 .ioc 文件
    ioc_files = list(project_dir.glob("*.ioc"))
    if ioc_files:
        ioc_path = ioc_files[0]
        config["ioc_file"] = str(ioc_path)
        try:
            content = ioc_path.read_text(encoding="utf-8", errors="replace")
            for line in content.split("\n"):
                line = line.strip()
                if line.startswith("ProjectManager.DeviceId="):
                    config["device"] = line.split("=", 1)[1].strip()
                elif line.startswith("ProjectManager.ProjectName="):
                    config["project_name"] = line.split("=", 1)[1].strip()
                elif line.startswith("RCC.HSE_VALUE="):
                    config["hse_value"] = line.split("=", 1)[1].strip()
                elif line.startswith("RCC.PLLM="):
                    config["pll_m"] = line.split("=", 1)[1].strip()
        except OSError:
            pass

    # 查找 .project 文件
    project_file = project_dir / ".project"
    if project_file.exists():
        config["project_file"] = str(project_file)

    # 芯片信息
    if "device" in config:
        chip_info = lookup_chip(config["device"])
        if chip_info:
            config["chip_info"] = chip_info

    return config


# === IAR .ewp 解析 ===

def detect_iar(project_path: Path) -> dict:
    """从 IAR .ewp 文件提取配置。"""
    config = {"ide": "iar", "project_file": str(project_path)}

    try:
        tree = ET.parse(project_path)
        root = tree.getroot()
    except (ET.ParseError, OSError) as e:
        config["error"] = f"XML parse error: {e}"
        return config

    # 芯片型号
    for state in root.iter("state"):
        name = state.find("name")
        if name is not None and name.text and "OGChipSelectEditMenu" in (name.text or ""):
            data = state.find("stateData")
            if data is not None:
                val = data.get("val", "")
                if val:
                    config["device"] = val.split()[-1] if " " in val else val

    # 编译器
    for setting in root.iter("settings"):
        name = setting.find("name")
        if name is not None and name.text == "ICCARM":
            for data in setting.iter("data"):
                for child in data:
                    if "OptimizationLevel" in (child.tag or ""):
                        config["optim_level"] = child.get("val", "")
                    elif "OptimStrategy" in (child.tag or ""):
                        config["optim_strategy"] = child.get("val", "")
            break

    config["compiler"] = "IAR ARM"

    # 芯片信息
    if "device" in config:
        chip_info = lookup_chip(config["device"])
        if chip_info:
            config["chip_info"] = chip_info

    return config


# === 自动扫描 ===

def scan_project(directory: Path) -> dict:
    """自动查找并检测项目文件。"""
    # Keil .uvprojx
    for f in directory.rglob("*.uvprojx"):
        if ".pack" not in str(f):
            return detect_keil(f)

    # IAR .ewp
    for f in directory.rglob("*.ewp"):
        return detect_iar(f)

    # STM32CubeIDE .ioc
    for f in directory.glob("*.ioc"):
        return detect_cubeide(directory)

    return {"error": "No project file found", "scanned": str(directory)}


# === 主函数 ===

def main() -> int:
    parser = argparse.ArgumentParser(description="STM32 项目配置自动检测工具")
    parser.add_argument("--project", help="项目文件路径 (.uvprojx/.ewp/.project)")
    parser.add_argument("--ioc", help="STM32CubeIDE .ioc 文件路径")
    parser.add_argument("--scan", help="自动扫描目录查找项目文件")
    parser.add_argument("--device", help="直接指定芯片型号（跳过项目文件解析）")
    args = parser.parse_args()

    if args.device:
        chip_info = lookup_chip(args.device)
        result = {"device": args.device, "chip_info": chip_info}
    elif args.scan:
        result = scan_project(Path(args.scan))
    elif args.project:
        project_path = Path(args.project)
        if not project_path.exists():
            print(f"Error: Project file not found: {args.project}", file=sys.stderr)
            return 1

        suffix = project_path.suffix.lower()
        if suffix == ".uvprojx":
            result = detect_keil(project_path)
        elif suffix == ".ewp":
            result = detect_iar(project_path)
        elif suffix == ".project":
            ioc_path = Path(args.ioc) if args.ioc else None
            result = detect_cubeide(project_path.parent)
        else:
            result = {"error": f"Unknown project type: {suffix}"}
    elif args.ioc:
        result = detect_cubeide(Path(args.ioc).parent)
    else:
        # 默认扫描当前目录
        result = scan_project(Path("."))

    json.dump(result, sys.stdout, indent=2, ensure_ascii=False)
    print()
    return 0 if "error" not in result else 1


if __name__ == "__main__":
    sys.exit(main())
