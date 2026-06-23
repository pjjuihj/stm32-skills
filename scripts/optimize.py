#!/usr/bin/env python
"""STM32 代码优化分析工具。

一站式分析固件的内存使用、编译器设置、代码质量和实时性能，
给出可操作的优化建议。

用法:
  python optimize.py --elf project.axf --uv4 D:/k5/UV4/UV4.exe --project project.uvprojx
  python optimize.py --elf project.axf --uv4 D:/k5/UV4/UV4.exe --check memory
  python optimize.py --elf project.axf --uv4 D:/k5/UV4/UV4.exe --check compiler --project project.uvprojx
  python optimize.py --elf project.axf --uv4 D:/k5/UV4/UV4.exe --check quality --src-dir ../Core/Src

分析维度:
  memory    - Flash/RAM 使用率、Top-N 最大函数、LTO 状态
  compiler  - 优化级别、警告级别、LTO、OneElfS
  quality   - cppcheck 扫描、magic numbers、extern 声明
  performance - FreeRTOS 栈大小、共享变量保护、ISR 浮点运算
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

# 使用共享模块
from shared import find_fromelf, lookup_chip, CHIP_DB


# ARMClang 优化级别映射
OPTIM_LEVELS = {
    "0": {"flag": "-O0", "name": "None", "desc": "无优化，适合调试"},
    "1": {"flag": "-O1", "name": "Basic", "desc": "基本优化"},
    "2": {"flag": "-O2", "name": "Balanced", "desc": "平衡优化，推荐 Release"},
    "3": {"flag": "-O3", "name": "Aggressive", "desc": "积极优化"},
    "4": {"flag": "-Omax", "name": "Maximum", "desc": "最大优化（含 -O3 + 额外优化）"},
}


# === 工具函数 ===


def run_cmd(cmd: list[str], timeout: int = 30) -> tuple[str, str, int]:
    """运行命令，返回 (stdout, stderr, returncode)。"""
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        return proc.stdout, proc.stderr, proc.returncode
    except FileNotFoundError:
        return "", f"Command not found: {cmd[0]}", -1
    except subprocess.TimeoutExpired:
        return "", "Timeout", -2


# === 维度 1：内存/体积优化 ===

def analyze_memory(elf_path: Path, fromelf_path: str, chip: str | None = None) -> dict:
    """分析 Flash/RAM 使用情况和最大函数。"""
    result = {"flash": {}, "ram": {}, "top_functions": [], "lto_enabled": None, "ccm_used": False}

    # 获取段大小
    stdout, _, rc = run_cmd([fromelf_path, "-z", str(elf_path)])
    if rc == 0:
        for line in stdout.split("\n"):
            if "ROM Totals" in line:
                parts = line.split()
                if len(parts) >= 5:
                    code = int(parts[0])
                    ro_data = int(parts[2])
                    rw_data = int(parts[3])
                    result["flash"] = {
                        "code_bytes": code,
                        "ro_data_bytes": ro_data,
                        "rw_data_bytes": rw_data,
                        "total_bytes": code + ro_data + rw_data,
                        "total_kb": round((code + ro_data + rw_data) / 1024, 1),
                    }
            elif ".axf" in line or ".elf" in line:
                parts = line.split()
                if len(parts) >= 5:
                    try:
                        zi_data = int(parts[4])
                        rw_data = int(parts[3])
                        result["ram"] = {
                            "rw_data_bytes": rw_data,
                            "zi_data_bytes": zi_data,
                            "total_bytes": rw_data + zi_data,
                            "total_kb": round((rw_data + zi_data) / 1024, 1),
                        }
                    except ValueError:
                        pass

    # 获取 Top-N 最大函数
    stdout, _, rc = run_cmd([fromelf_path, "-s", str(elf_path)])
    if rc == 0:
        functions = []
        for line in stdout.split("\n"):
            line = line.strip()
            match = re.match(r"\d+\s+(\w+)\s+(0x[0-9a-fA-F]{8})\s+\w+\s+\S+\s+Code\s+\S+\s+(0x[0-9a-fA-F]+)", line)
            if match:
                name = match.group(1)
                addr = int(match.group(2), 16)
                size = int(match.group(3), 16)
                if size > 0:
                    functions.append({"name": name, "address": f"0x{addr:08x}", "size_bytes": size})
        functions.sort(key=lambda x: x["size_bytes"], reverse=True)
        result["top_functions"] = functions[:20]

    # 芯片容量和使用率
    if chip:
        mem = lookup_chip(chip)
        if mem:
            if result["flash"]:
                result["flash"]["total_chip_kb"] = mem["flash_kb"]
                result["flash"]["usage_pct"] = round(result["flash"]["total_kb"] / mem["flash_kb"] * 100, 1)
                result["flash"]["remaining_kb"] = round(mem["flash_kb"] - result["flash"]["total_kb"], 1)
            if result["ram"]:
                result["ram"]["total_chip_kb"] = mem["ram_kb"]
                result["ram"]["usage_pct"] = round(result["ram"]["total_kb"] / mem["ram_kb"] * 100, 1)
                result["ram"]["remaining_kb"] = round(mem["ram_kb"] - result["ram"]["total_kb"], 1)
            result["ccm_kb"] = mem.get("ccm_kb", 0)

    return result


# === 维度 2：编译器优化设置 ===

def analyze_compiler(uvprojx_path: Path) -> dict:
    """解析 .uvprojx 文件，提取编译器优化设置。"""
    result = {
        "optim_level": None,
        "optim_flag": None,
        "optim_target": None,
        "lto_enabled": None,
        "warning_level": None,
        "one_elf_per_function": None,
        "c_standard": None,
        "issues": [],
    }

    if not uvprojx_path.exists():
        result["issues"].append({"severity": "error", "message": f"项目文件不存在: {uvprojx_path}"})
        return result

    try:
        tree = ET.parse(uvprojx_path)
        root = tree.getroot()
    except ET.ParseError as e:
        result["issues"].append({"severity": "error", "message": f"XML 解析失败: {e}"})
        return result

    # 查找 Target 下的 Cads 设置
    for cads in root.iter("Cads"):
        optim = cads.find("Optim")
        if optim is not None and optim.text:
            level = optim.text
            result["optim_level"] = int(level) if level.isdigit() else level
            opt_info = OPTIM_LEVELS.get(level, {})
            result["optim_flag"] = opt_info.get("flag", f"Unknown({level})")
            result["optim_name"] = opt_info.get("name", "Unknown")
            result["optim_desc"] = opt_info.get("desc", "")

        otime = cads.find("oTime")
        if otime is not None and otime.text:
            result["optim_target"] = "time" if otime.text == "1" else "size"

        wlevel = cads.find("wLevel")
        if wlevel is not None and wlevel.text:
            result["warning_level"] = int(wlevel.text)

        oneelf = cads.find("OneElfS")
        if oneelf is not None and oneelf.text:
            result["one_elf_per_function"] = oneelf.text == "1"

        v6lto = cads.find("v6Lto")
        if v6lto is not None and v6lto.text:
            result["lto_enabled"] = v6lto.text == "1"

        uc99 = cads.find("uC99")
        if uc99 is not None and uc99.text:
            result["c_standard"] = "C99" if uc99.text == "1" else "C90"

        break  # 只取第一个（全局设置）

    # 生成建议
    if result["optim_level"] is not None:
        level = result["optim_level"]
        if level == 0:
            result["issues"].append({
                "severity": "warning",
                "category": "compiler",
                "message": "优化级别 -O0（无优化），适合调试但代码体积大、速度慢。Release 构建建议使用 -O2 或 -Os。",
            })

    if result["lto_enabled"] is False:
        result["issues"].append({
            "severity": "info",
            "category": "compiler",
            "message": "LTO（链接时优化）未启用。启用 LTO 可减少代码体积 5-15%，改善跨模块内联。在 .uvprojx 中设置 <v6Lto>1</v6Lto>。",
        })

    if result["warning_level"] is not None and result["warning_level"] < 3:
        result["issues"].append({
            "severity": "info",
            "category": "compiler",
            "message": f"警告级别为 {result['warning_level']}（偏低）。建议使用级别 3 或 4 以捕获更多潜在问题。",
        })

    return result


# === 维度 3：代码质量分析 ===

def analyze_quality(src_dir: Path | None = None) -> dict:
    """代码质量分析：cppcheck 扫描 + 源码检查。"""
    result = {"cppcheck_available": False, "issues": [], "file_count": 0}

    # 检查 cppcheck
    cppcheck_path = shutil.which("cppcheck")
    if cppcheck_path:
        result["cppcheck_available"] = True
        if src_dir and src_dir.exists():
            stdout, stderr, rc = run_cmd([
                cppcheck_path,
                "--enable=warning,style,performance",
                "--language=c",
                "--std=c99",
                "--template={file}:{line}: {severity}: {message}",
                "--quiet",
                str(src_dir),
            ], timeout=60)
            if stdout:
                for line in stdout.strip().split("\n"):
                    if ":" in line and ("warning" in line.lower() or "style" in line.lower() or "performance" in line.lower()):
                        result["issues"].append({"source": "cppcheck", "message": line.strip()})

    # 源码扫描（无需 cppcheck）
    if src_dir and src_dir.exists():
        c_files = list(src_dir.glob("**/*.c"))
        result["file_count"] = len(c_files)

        for c_file in c_files:
            try:
                content = c_file.read_text(encoding="utf-8", errors="replace")
                lines = content.split("\n")
            except OSError:
                continue

            for i, line in enumerate(lines, 1):
                stripped = line.strip()

                # 检查函数体内的 extern 声明
                if re.match(r"extern\s+\w+", stripped) and not stripped.startswith("//"):
                    # 排除头文件中的正常声明
                    if c_file.suffix == ".c":
                        result["issues"].append({
                            "source": "static_check",
                            "severity": "style",
                            "file": str(c_file),
                            "line": i,
                            "message": f"函数体内的 extern 声明应移到头文件: {stripped[:80]}",
                        })

                # 检查 magic numbers（排除常见值 0, 1, -1, 2, 10, 100, 1000 等）
                if "//" not in stripped and "/*" not in stripped:
                    # 查找数字字面量（排除十六进制、行号、常见值）
                    nums = re.findall(r"(?<!\w)(\d{4,})(?!\w)", stripped)
                    for num_str in nums:
                        num = int(num_str)
                        if num not in (0, 1, 10, 100, 1000, 10000, 65535, 0xFFFF):
                            result["issues"].append({
                                "source": "static_check",
                                "severity": "style",
                                "file": str(c_file),
                                "line": i,
                                "message": f"Magic number: {num_str}（建议定义为命名常量）",
                            })

    return result


# === 维度 4：性能/实时性分析 ===

def analyze_performance(fromelf_path: str, elf_path: Path) -> dict:
    """分析 FreeRTOS 任务栈、共享变量保护、ISR 浮点运算。"""
    result = {
        "task_stacks": [],
        "shared_vars": [],
        "isr_float_ops": [],
        "issues": [],
    }

    # 从符号表提取栈和堆信息
    stdout, _, rc = run_cmd([fromelf_path, "-s", str(elf_path)])
    if rc != 0:
        return result

    symbols = {}
    for line in stdout.split("\n"):
        line = line.strip()
        match = re.match(r"\d+\s+(\w+)\s+(0x[0-9a-fA-F]{8})\s+\w+\s+(\S+)\s+(\w+)(?:\s+\S+\s+(0x[0-9a-fA-F]+))?", line)
        if match:
            name = match.group(1)
            addr = int(match.group(2), 16)
            sec = match.group(3)
            sym_type = match.group(4)
            size = int(match.group(5), 16) if match.group(5) else 0
            symbols[name] = {"address": addr, "section": sec, "type": sym_type, "size": size}

    # 检查 FreeRTOS 堆大小
    for sym_name in ["ucHeap", "configTOTAL_HEAP_SIZE", "ucHeap1", "ucHeap2"]:
        if sym_name in symbols:
            sym = symbols[sym_name]
            if sym["size"] > 0:
                result["issues"].append({
                    "severity": "info",
                    "category": "rtos",
                    "message": f"FreeRTOS 堆: {sym['size']} bytes ({sym['size']//1024} KB)",
                })

    # 检查栈大小
    for sym_name in ["Stack_Size", "__stack_size__"]:
        if sym_name in symbols:
            sym = symbols[sym_name]
            val = sym["address"] if sym["address"] > 0 else sym["size"]
            if val > 0:
                result["issues"].append({
                    "severity": "info",
                    "category": "stack",
                    "message": f"主栈大小: {val} bytes ({val//1024} KB)",
                })
                if val < 1024:
                    result["issues"].append({
                        "severity": "warning",
                        "category": "stack",
                        "message": f"主栈过小 ({val} bytes)，建议 >= 1024 bytes",
                    })

    # 检查堆大小
    for sym_name in ["Heap_Size", "__heap_size__"]:
        if sym_name in symbols:
            sym = symbols[sym_name]
            val = sym["address"] if sym["address"] > 0 else sym["size"]
            if val > 0:
                result["issues"].append({
                    "severity": "info",
                    "category": "heap",
                    "message": f"堆大小: {val} bytes ({val//1024} KB)",
                })

    # 检查关键性能符号
    perf_symbols = [
        ("__disable_irq", "禁用中断（检查是否在临界区过长）"),
        ("__enable_irq", "启用中断"),
        ("taskENTER_CRITICAL", "进入 FreeRTOS 临界区"),
        ("taskEXIT_CRITICAL", "退出 FreeRTOS 临界区"),
        ("vTaskDelay", "任务延迟"),
        ("osDelay", "CMSIS 延迟"),
    ]
    for sym_name, desc in perf_symbols:
        if sym_name in symbols:
            result["shared_vars"].append({"symbol": sym_name, "note": desc})

    return result


# === 新增分析维度 ===

def analyze_cppcheck(src_dir: Path | None = None) -> dict:
    """cppcheck 集成：自动运行 cppcheck 扫描源码。"""
    result = {"available": False, "issues": [], "stats": {}}

    cppcheck_path = shutil.which("cppcheck")
    if not cppcheck_path:
        result["error"] = "cppcheck not found in PATH"
        return result

    result["available"] = True
    result["path"] = cppcheck_path

    if not src_dir or not src_dir.exists():
        return result

    # 运行 cppcheck
    stdout, stderr, rc = run_cmd([
        cppcheck_path,
        "--enable=warning,style,performance,portability",
        "--language=c",
        "--std=c99",
        "--template={file}:{line}:{column}: {severity}: {id}: {message}",
        "--quiet",
        "--suppress=missingIncludeSystem",
        str(src_dir),
    ], timeout=120)

    issues = []
    if stdout:
        for line in stdout.strip().split("\n"):
            if ":" in line and ("warning" in line.lower() or "style" in line.lower() or
                                "performance" in line.lower() or "portability" in line.lower() or
                                "error" in line.lower()):
                issues.append({"source": "cppcheck", "message": line.strip()})

    if stderr:
        # cppcheck 有时输出到 stderr
        for line in stderr.strip().split("\n"):
            if ":" in line and ("warning" in line.lower() or "style" in line.lower() or
                                "performance" in line.lower() or "error" in line.lower()):
                issues.append({"source": "cppcheck", "message": line.strip()})

    result["issues"] = issues
    result["stats"] = {
        "total": len(issues),
        "errors": sum(1 for i in issues if "error" in i["message"].lower()),
        "warnings": sum(1 for i in issues if "warning" in i["message"].lower()),
        "style": sum(1 for i in issues if "style" in i["message"].lower()),
        "performance": sum(1 for i in issues if "performance" in i["message"].lower()),
    }

    return result


def analyze_freertos_stack(src_dir: Path | None = None, fromelf_path: str | None = None, elf_path: Path | None = None) -> dict:
    """FreeRTOS 栈深度分析：检查任务栈大小配置。"""
    result = {"tasks": [], "issues": []}

    # 从源码中提取任务栈配置
    if src_dir and src_dir.exists():
        for c_file in src_dir.glob("**/*.c"):
            try:
                content = c_file.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue

            # 查找 osThreadAttr_t 定义
            # 格式: .stack_size = 256 * 4,
            for match in re.finditer(r'\.stack_size\s*=\s*(\d+)\s*\*\s*(\d+)', content):
                words = int(match.group(1))
                multiplier = int(match.group(2))
                stack_bytes = words * multiplier

                # 查找任务名
                name_match = re.search(r'\.name\s*=\s*"([^"]+)"', content[max(0, match.start()-200):match.start()+50])
                task_name = name_match.group(1) if name_match else "unknown"

                # 查找优先级
                prio_match = re.search(r'\.priority\s*=\s*\(osPriority_t\)\s*(\w+)', content[max(0, match.start()-200):match.start()+200])
                priority = prio_match.group(1) if prio_match else "unknown"

                result["tasks"].append({
                    "name": task_name,
                    "stack_words": words,
                    "stack_bytes": stack_bytes,
                    "priority": priority,
                    "file": str(c_file),
                })

            # 查找 xTaskCreate 调用
            for match in re.finditer(r'xTaskCreate\s*\([^,]+,\s*"([^"]+)"\s*,\s*(\d+)\s*,', content):
                task_name = match.group(1)
                stack_words = int(match.group(2))
                result["tasks"].append({
                    "name": task_name,
                    "stack_words": stack_words,
                    "stack_bytes": stack_words * 4,  # Cortex-M 32-bit
                    "priority": "unknown",
                    "file": str(c_file),
                })

    # 分析栈大小是否合理
    for task in result["tasks"]:
        stack_kb = task["stack_bytes"] / 1024
        if stack_kb < 1:
            result["issues"].append({
                "severity": "warning",
                "category": "freertos_stack",
                "message": f"任务 {task['name']} 栈过小: {task['stack_bytes']} bytes ({stack_kb:.1f} KB)，建议 >= 1KB",
            })
        elif stack_kb > 8:
            result["issues"].append({
                "severity": "info",
                "category": "freertos_stack",
                "message": f"任务 {task['name']} 栈较大: {task['stack_bytes']} bytes ({stack_kb:.1f} KB)，可考虑优化",
            })

    return result


def analyze_complexity(src_dir: Path | None = None) -> dict:
    """代码复杂度分析：计算圈复杂度、代码行数、嵌套深度。"""
    result = {"files": [], "summary": {}, "issues": []}

    if not src_dir or not src_dir.exists():
        return result

    total_lines = 0
    total_functions = 0
    high_complexity = []

    for c_file in sorted(src_dir.glob("**/*.c")):
        try:
            content = c_file.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue

        lines = content.split("\n")
        code_lines = [l for l in lines if l.strip() and not l.strip().startswith("//") and not l.strip().startswith("/*") and not l.strip().startswith("*")]
        total_lines += len(code_lines)

        # 简单的函数检测和圈复杂度估算
        func_count = 0
        for i, line in enumerate(lines):
            # 检测函数定义（简化版）
            if re.match(r'^[a-zA-Z_]\w*\s+[a-zA-Z_]\w*\s*\([^)]*\)\s*\{', line.strip()):
                func_count += 1
                total_functions += 1

                # 计算圈复杂度（简化版：统计分支语句）
                complexity = 1  # 基础复杂度
                brace_depth = 0
                for j in range(i, min(i + 500, len(lines))):
                    l = lines[j].strip()
                    brace_depth += l.count('{') - l.count('}')
                    if brace_depth <= 0 and j > i:
                        break
                    # 统计分支语句
                    complexity += len(re.findall(r'\b(if|else\s+if|for|while|switch|case|catch|\?)\b', l))

                if complexity > 15:
                    high_complexity.append({
                        "function": f"function_at_line_{i+1}",
                        "file": str(c_file),
                        "line": i + 1,
                        "complexity": complexity,
                    })

        file_info = {
            "file": str(c_file),
            "lines": len(lines),
            "code_lines": len(code_lines),
            "functions": func_count,
        }
        result["files"].append(file_info)

    result["summary"] = {
        "total_files": len(result["files"]),
        "total_lines": total_lines,
        "total_functions": total_functions,
        "avg_lines_per_file": round(total_lines / max(len(result["files"]), 1)),
    }

    # 高复杂度函数
    for func in high_complexity:
        result["issues"].append({
            "severity": "warning",
            "category": "complexity",
            "message": f"高复杂度函数 (CC={func['complexity']}): {func['file']}:{func['line']}",
        })

    return result


def analyze_cortex_m(fromelf_path: str, elf_path: Path) -> dict:
    """Cortex-M 专项检查：NVIC 优先级、中断配置、栈对齐。"""
    result = {"checks": [], "issues": []}

    # 提取符号表
    stdout, _, rc = run_cmd([fromelf_path, "-s", str(elf_path)])
    if rc != 0:
        return result

    symbols = {}
    for line in stdout.split("\n"):
        line = line.strip()
        match = re.match(r"\d+\s+(\w+)\s+(0x[0-9a-fA-F]{8})", line)
        if match:
            name = match.group(1)
            addr = int(match.group(2), 16)
            symbols[name] = addr

    # 检查 NVIC 优先级位数
    # STM32F4 使用 4 位优先级（16 级）
    if "__NVIC_PRIO_BITS" in symbols:
        val = symbols["__NVIC_PRIO_BITS"]
        result["checks"].append({"name": "NVIC_PRIO_BITS", "value": val, "status": "found"})
        if val != 4:
            result["issues"].append({
                "severity": "warning",
                "category": "cortex_m",
                "message": f"NVIC 优先级位数 = {val}，STM32F4 通常为 4",
            })

    # 检查中断向量表位置
    if "__Vectors" in symbols or "_Vectors" in symbols:
        vec_addr = symbols.get("__Vectors") or symbols.get("_Vectors")
        result["checks"].append({"name": "vector_table", "address": f"0x{vec_addr:08x}", "status": "found"})
        if vec_addr != 0x08000000:
            result["issues"].append({
                "severity": "info",
                "category": "cortex_m",
                "message": f"向量表地址 = 0x{vec_addr:08x}（非默认 0x08000000，可能是 bootloader 配置）",
            })

    # 检查栈对齐
    if "__stack_size__" in symbols:
        stack_size = symbols["__stack_size__"]
        if stack_size % 8 != 0:
            result["issues"].append({
                "severity": "warning",
                "category": "cortex_m",
                "message": f"栈大小 {stack_size} bytes 未 8 字节对齐，Cortex-M 要求 8 字节对齐",
            })

    # 检查是否使用 FPU
    fpu_syms = ["__hardfp_sin", "__hardfp_cos", "__hardfp_asin", "__hardfp_atan", "__hardfp_sqrt"]
    fpu_used = [s for s in fpu_syms if s in symbols]
    if fpu_used:
        result["checks"].append({"name": "FPU", "status": "used", "symbols": fpu_used})
        result["issues"].append({
            "severity": "info",
            "category": "cortex_m",
            "message": f"检测到硬件 FPU 使用: {', '.join(fpu_used[:3])}",
        })

    # 检查 FreeRTOS 中断优先级配置
    freertos_syms = [
        "configLIBRARY_MAX_SYSCALL_INTERRUPT_PRIORITY",
        "configMAX_SYSCALL_INTERRUPT_PRIORITY",
        "configKERNEL_INTERRUPT_PRIORITY",
    ]
    for sym in freertos_syms:
        if sym in symbols:
            val = symbols[sym]
            result["checks"].append({"name": sym, "value": val, "status": "found"})

    return result


# === 汇总和建议生成 ===

def generate_recommendations(memory: dict, compiler: dict, quality: dict, performance: dict,
                             cppcheck: dict | None = None, freertos_stack: dict | None = None,
                             complexity: dict | None = None, cortex_m: dict | None = None) -> list[dict]:
    """基于分析结果生成优化建议。"""
    recs = []

    # 内存建议
    if memory.get("flash", {}).get("usage_pct", 0) > 80:
        recs.append({
            "priority": "HIGH",
            "category": "memory",
            "message": f"Flash 使用率 {memory['flash']['usage_pct']}%，接近上限。考虑启用 LTO、删除未使用代码、优化数据结构。",
        })
    if memory.get("ram", {}).get("usage_pct", 0) > 80:
        recs.append({
            "priority": "HIGH",
            "category": "memory",
            "message": f"RAM 使用率 {memory['ram']['usage_pct']}%，接近上限。考虑减少任务栈大小、使用 CCM RAM。",
        })

    # 编译器建议
    for issue in compiler.get("issues", []):
        recs.append({
            "priority": "MEDIUM" if issue["severity"] == "warning" else "LOW",
            "category": "compiler",
            "message": issue["message"],
        })

    # 代码质量建议
    cppcheck_issues = [i for i in quality.get("issues", []) if i.get("source") == "cppcheck"]
    if len(cppcheck_issues) > 5:
        recs.append({
            "priority": "MEDIUM",
            "category": "quality",
            "message": f"cppcheck 发现 {len(cppcheck_issues)} 个问题，建议逐一检查并修复。",
        })
    extern_issues = [i for i in quality.get("issues", []) if "extern" in i.get("message", "").lower()]
    if extern_issues:
        recs.append({
            "priority": "LOW",
            "category": "quality",
            "message": f"发现 {len(extern_issues)} 个函数体内的 extern 声明，应移到头文件。",
        })
    magic_issues = [i for i in quality.get("issues", []) if "magic number" in i.get("message", "").lower()]
    if magic_issues:
        recs.append({
            "priority": "LOW",
            "category": "quality",
            "message": f"发现 {len(magic_issues)} 个 magic number，建议定义为命名常量。",
        })

    # 性能建议
    for issue in performance.get("issues", []):
        if issue.get("severity") == "warning":
            recs.append({
                "priority": "HIGH",
                "category": "performance",
                "message": issue["message"],
            })

    # Top 函数建议
    top = memory.get("top_functions", [])
    if top and top[0]["size_bytes"] > 4096:
        recs.append({
            "priority": "MEDIUM",
            "category": "memory",
            "message": f"最大函数 {top[0]['name']} 占用 {top[0]['size_bytes']} bytes，考虑拆分或优化。",
        })

    # cppcheck 建议
    if cppcheck and cppcheck.get("available"):
        stats = cppcheck.get("stats", {})
        if stats.get("errors", 0) > 0:
            recs.append({
                "priority": "HIGH",
                "category": "cppcheck",
                "message": f"cppcheck 发现 {stats['errors']} 个错误，需要修复。",
            })
        if stats.get("warnings", 0) > 3:
            recs.append({
                "priority": "MEDIUM",
                "category": "cppcheck",
                "message": f"cppcheck 发现 {stats['warnings']} 个警告，建议检查。",
            })

    # FreeRTOS 栈建议
    if freertos_stack:
        for issue in freertos_stack.get("issues", []):
            recs.append({
                "priority": "HIGH" if issue["severity"] == "warning" else "LOW",
                "category": "freertos_stack",
                "message": issue["message"],
            })

    # 复杂度建议
    if complexity:
        for issue in complexity.get("issues", []):
            recs.append({
                "priority": "MEDIUM",
                "category": "complexity",
                "message": issue["message"],
            })

    # Cortex-M 建议
    if cortex_m:
        for issue in cortex_m.get("issues", []):
            if issue["severity"] == "warning":
                recs.append({
                    "priority": "MEDIUM",
                    "category": "cortex_m",
                    "message": issue["message"],
                })

    return recs


# === 主函数 ===

def run_optimization_analysis(
    elf_path: str,
    uv4_path: str | None = None,
    uvprojx_path: str | None = None,
    src_dir: str | None = None,
    chip: str | None = None,
    checks: list[str] | None = None,
) -> dict:
    """主分析函数。"""
    elf = Path(elf_path)
    if not elf.exists():
        return {"error": f"ELF 文件不存在: {elf_path}"}

    fromelf_path = find_fromelf(uv4_path)
    if not fromelf_path:
        return {"error": "未找到 fromelf 工具。请指定 --uv4 路径。"}

    all_checks = ["memory", "compiler", "quality", "performance", "cppcheck", "freertos_stack", "complexity", "cortex_m"]
    if checks:
        all_checks = [c for c in all_checks if c in checks]

    result = {"elf_path": str(elf), "checks_performed": all_checks}

    # 维度 1：内存分析
    if "memory" in all_checks:
        chip_name = chip
        if not chip_name and uvprojx_path:
            # 从 .uvprojx 提取芯片型号
            try:
                tree = ET.parse(uvprojx_path)
                for elem in tree.getroot().iter("Device"):
                    if elem.text:
                        chip_name = elem.text
                        break
            except (ET.ParseError, OSError):
                pass
        result["memory"] = analyze_memory(elf, fromelf_path, chip_name)

    # 维度 2：编译器设置
    if "compiler" in all_checks and uvprojx_path:
        result["compiler"] = analyze_compiler(Path(uvprojx_path))
    elif "compiler" in all_checks:
        result["compiler"] = {"issues": [{"severity": "info", "message": "未指定 --project，跳过编译器设置分析"}]}

    # 维度 3：代码质量
    if "quality" in all_checks:
        result["quality"] = analyze_quality(Path(src_dir) if src_dir else None)

    # 维度 4：性能分析
    if "performance" in all_checks:
        result["performance"] = analyze_performance(fromelf_path, elf)

    # 维度 5：cppcheck 集成
    if "cppcheck" in all_checks:
        result["cppcheck"] = analyze_cppcheck(Path(src_dir) if src_dir else None)

    # 维度 6：FreeRTOS 栈分析
    if "freertos_stack" in all_checks:
        result["freertos_stack"] = analyze_freertos_stack(
            Path(src_dir) if src_dir else None, fromelf_path, elf
        )

    # 维度 7：代码复杂度
    if "complexity" in all_checks:
        result["complexity"] = analyze_complexity(Path(src_dir) if src_dir else None)

    # 维度 8：Cortex-M 专项检查
    if "cortex_m" in all_checks:
        result["cortex_m"] = analyze_cortex_m(fromelf_path, elf)

    # 汇总建议
    result["recommendations"] = generate_recommendations(
        result.get("memory", {}),
        result.get("compiler", {}),
        result.get("quality", {}),
        result.get("performance", {}),
        result.get("cppcheck"),
        result.get("freertos_stack"),
        result.get("complexity"),
        result.get("cortex_m"),
    )

    return result


def main() -> int:
    parser = argparse.ArgumentParser(
        description="STM32 代码优化分析工具",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""示例:
  %(prog)s --elf project.axf --uv4 D:/k5/UV4/UV4.exe --project project.uvprojx
  %(prog)s --elf project.axf --uv4 D:/k5/UV4/UV4.exe --check memory
  %(prog)s --elf project.axf --uv4 D:/k5/UV4/UV4.exe --check quality --src-dir ../Core/Src
""",
    )
    parser.add_argument("--elf", help="ELF/AXF 文件路径")
    parser.add_argument("--uv4", help="UV4.exe 路径（用于定位 fromelf）")
    parser.add_argument("--project", help=".uvprojx 项目文件路径")
    parser.add_argument("--src-dir", help="源码目录（用于 quality 检查）")
    parser.add_argument("--chip", help="芯片型号（如 STM32F407VETx，自动从 .uvprojx 提取）")
    parser.add_argument("--check", help="指定检查维度，逗号分隔: memory,compiler,quality,performance")
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

    checks = [c.strip() for c in args.check.split(",")] if args.check else None

    result = run_optimization_analysis(
        args.elf,
        uv4_path=args.uv4,
        uvprojx_path=args.project,
        src_dir=args.src_dir,
        chip=args.chip,
        checks=checks,
    )

    json.dump(result, sys.stdout, indent=2, ensure_ascii=False)
    print()
    return 0 if "error" not in result else 1


if __name__ == "__main__":
    sys.exit(main())
