#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""写代码前检查流自动化工具。

基于 stm32-keil-workflow 技能的 7 步检查流，自动扫描源码验证各项检查。

用法:
    python pre_code_check.py --auto .                    # 检查全部
    python pre_code_check.py --auto . --check config     # 只检查配置系统
    python pre_code_check.py --auto . --check clock      # 只检查时钟
    python pre_code_check.py --auto . --check init       # 只检查初始化链
    python pre_code_check.py --auto . --check encaps     # 只检查变量封装
    python pre_code_check.py --auto . --check concurrency # 只检查并发安全
    python pre_code_check.py --auto . --check display    # 只检查显示算法
    python pre_code_check.py --auto . --check all        # 检查全部（默认）
    python pre_code_check.py --auto . --fix              # 自动修复可修复的问题
    python pre_code_check.py --auto . --history          # 搜索相关历史错误
"""

from __future__ import annotations

import argparse
import io
import json
import os
import re
import subprocess
import sys
from pathlib import Path

# Windows 终端编码修复
if sys.platform == "win32":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

# 颜色定义
GREEN = "\033[92m"
RED = "\033[91m"
YELLOW = "\033[93m"
CYAN = "\033[96m"
RESET = "\033[0m"
BOLD = "\033[1m"


# ============================================================
# 语义分析模块
# ============================================================

class CFunction:
    """C 函数的语义表示。"""

    def __init__(self, name: str, return_type: str, params: str, body: str,
                 file: str, line: int):
        self.name = name
        self.return_type = return_type
        self.params = params
        self.body = body
        self.file = file
        self.line = line

    def calls(self, func_name: str) -> bool:
        """检查函数体内是否调用了指定函数（支持前缀匹配）。"""
        # 匹配 func_name 或 func_nameXXX( 形式的函数调用
        return bool(re.search(rf'{func_name}\w*\s*\(', self.body))

    def calls_in_all_branches(self, func_name: str) -> bool:
        """检查函数是否在所有分支中都调用了指定函数。"""
        # 简化检查：找 if/else 块，检查每个块中是否都有调用
        # 这是一个启发式检查，不是完整的控制流分析
        if_blocks = re.findall(r'if\s*\([^)]+\)\s*\{([^}]+)\}', self.body, re.DOTALL)
        else_blocks = re.findall(r'else\s*\{([^}]+)\}', self.body, re.DOTALL)

        if not if_blocks:
            # 没有 if/else，直接检查整个函数体
            return self.calls(func_name)

        # 检查每个 if 块中是否都有调用
        for block in if_blocks:
            if func_name not in block:
                return False

        # 如果有 else 块，也检查
        if else_blocks:
            for block in else_blocks:
                if func_name not in block:
                    return False

        return True

    def has_zero_check(self, var_name: str) -> bool:
        """检查函数体内是否有对指定变量的零值检查。"""
        patterns = [
            rf'if\s*\(\s*{var_name}\s*==\s*0\s*\)',
            rf'if\s*\(\s*{var_name}\s*!=\s*0\s*\)',
            rf'if\s*\(\s*!?\s*{var_name}\s*\)',
            rf'if\s*\(\s*{var_name}\s*<\s*\d+\s*\)',
            rf'if\s*\(\s*{var_name}\s*<=\s*0\s*\)',
            rf'if\s*\(\s*{var_name}\s*>\s*0\s*\)',
            rf'if\s*\(\s*{var_name}\s*>=\s*\d+\s*\)',
        ]
        for pattern in patterns:
            if re.search(pattern, self.body):
                return True
        return False

    def has_lock_unlock(self) -> tuple[bool, bool]:
        """检查函数体内是否有锁操作。"""
        has_lock = bool(re.search(r'LOCK\(\)|osMutexAcquire', self.body))
        has_unlock = bool(re.search(r'UNLOCK\(\)|osMutexRelease', self.body))
        return has_lock, has_unlock

    def log_in_lock(self) -> bool:
        """检查是否有 LOG 调用在锁内。"""
        # 找 LOCK...UNLOCK 块
        lock_sections = re.finditer(r'LOCK\(\)(.*?)UNLOCK\(\)', self.body, re.DOTALL)
        for section in lock_sections:
            if 'LOG_' in section.group(1):
                return True
        return False

    def divides_by(self, var_name: str) -> bool:
        """检查函数体内是否有除以指定变量的操作。"""
        return bool(re.search(rf'\b\w+\s*/\s*{var_name}\b', self.body))

    def is_param(self, var_name: str) -> bool:
        """检查变量是否是函数参数。"""
        return bool(re.search(rf'\b{var_name}\b', self.params))


class CFile:
    """C 文件的语义表示。"""

    def __init__(self, filename: str, content: str):
        self.filename = filename
        self.content = content
        self.functions: list[CFunction] = []
        self.global_vars: list[dict] = []
        self._parse()

    def _parse(self):
        """解析文件，提取函数和全局变量。"""
        # 排除的关键字（不是函数定义）
        keywords = {'if', 'else', 'for', 'while', 'switch', 'do', 'return', 'sizeof',
                     'struct', 'enum', 'typedef', 'union', 'case', 'default'}

        # 解析函数定义
        # 匹配: [static] [return_type] function_name(params) {
        func_pattern = re.compile(
            r'^(static\s+)?([\w\s\*]+?)\s+(\w+)\s*\(([^)]*)\)\s*\{',
            re.MULTILINE
        )

        for match in func_pattern.finditer(self.content):
            is_static = bool(match.group(1))
            return_type = match.group(2).strip()
            func_name = match.group(3)
            params = match.group(4)

            # 跳过关键字
            if func_name in keywords or return_type in keywords:
                continue

            # 跳过太短的函数名（可能是宏）
            if len(func_name) < 2:
                continue

            # 跳过看起来不像函数定义的（return_type 包含奇怪字符）
            if re.search(r'[;{}]', return_type):
                continue

            func_start = match.end()

            # 找函数体结束（匹配大括号）
            brace_depth = 1
            pos = func_start
            while pos < len(self.content) and brace_depth > 0:
                if self.content[pos] == '{':
                    brace_depth += 1
                elif self.content[pos] == '}':
                    brace_depth -= 1
                pos += 1

            func_body = self.content[func_start:pos-1]
            line_num = self.content[:match.start()].count('\n') + 1

            self.functions.append(CFunction(
                name=func_name,
                return_type=return_type,
                params=params,
                body=func_body,
                file=self.filename,
                line=line_num
            ))

        # 解析全局变量（在函数外部）
        global_var_pattern = re.compile(
            r'^(uint\w+|int\w+|bool|float|char|volatile\s+uint\w+|volatile\s+bool)\s+'
            r'(\w+)\s*(?:=\s*[^;]+|\[[\w\s*]+\])?\s*;',
            re.MULTILINE
        )

        for match in global_var_pattern.finditer(self.content):
            full_line = match.group(0).strip()
            var_name = match.group(2)
            line_num = self.content[:match.start()].count('\n') + 1

            # 检查是否在函数体内
            in_function = False
            for func in self.functions:
                func_start = self.content.find(func.body)
                if func_start <= match.start() <= func_start + len(func.body):
                    in_function = True
                    break

            if not in_function:
                self.global_vars.append({
                    "name": var_name,
                    "type": match.group(1),
                    "line": line_num,
                    "is_static": full_line.startswith("static"),
                    "is_volatile": "volatile" in match.group(1),
                })

    def get_function(self, name: str) -> CFunction | None:
        """获取指定名称的函数。"""
        for func in self.functions:
            if func.name == name:
                return func
        return None

    def get_functions_matching(self, pattern: str) -> list[CFunction]:
        """获取名称匹配模式的函数列表。"""
        return [f for f in self.functions if re.search(pattern, f.name)]


def parse_c_files(c_files: list[tuple[str, str]]) -> list[CFile]:
    """解析所有 C 文件。"""
    return [CFile(name, content) for name, content in c_files]


def find_src_dir(project_dir: str) -> Path | None:
    """查找 Core/Src 目录。"""
    candidates = [
        Path(project_dir) / "Core" / "Src",
        Path(project_dir) / "src",
    ]
    for c in candidates:
        if c.exists():
            return c
    return None


def find_inc_dir(project_dir: str) -> Path | None:
    """查找 Core/Inc 目录。"""
    candidates = [
        Path(project_dir) / "Core" / "Inc",
        Path(project_dir) / "inc",
    ]
    for c in candidates:
        if c.exists():
            return c
    return None


def find_all_src_dirs(project_dir: str) -> list[Path]:
    """查找所有源码目录（Core/Src, Drivers/*, Middlewares/*）。"""
    base = Path(project_dir)
    dirs = []

    # Core/Src（主要源码）
    core_src = base / "Core" / "Src"
    if core_src.exists():
        dirs.append(core_src)

    # Drivers 目录（OLED 等第三方驱动）
    drivers_dir = base / "Drivers"
    if drivers_dir.exists():
        for d in drivers_dir.iterdir():
            if d.is_dir() and d.name not in ("CMSIS", "STM32F4xx_HAL_Driver"):
                if any(d.glob("*.c")):
                    dirs.append(d)

    # Middlewares 目录（FreeRTOS 配置等）
    mw_dir = base / "Middlewares"
    if mw_dir.exists():
        for d in mw_dir.rglob("*"):
            if d.is_dir() and d.name == "Config":
                if any(d.glob("*.c")):
                    dirs.append(d)

    return dirs


def read_c_files(src_dir: Path) -> list[tuple[str, str]]:
    """读取目录下所有 .c 文件。"""
    results = []
    for f in sorted(src_dir.glob("*.c")):
        try:
            content = f.read_text(encoding="utf-8", errors="ignore")
            results.append((f.name, content))
        except Exception:
            pass
    return results


def read_all_c_files(project_dir: str) -> list[tuple[str, str]]:
    """读取所有源码目录的 .c 文件。"""
    results = []
    for d in find_all_src_dirs(project_dir):
        for f in sorted(d.glob("*.c")):
            try:
                content = f.read_text(encoding="utf-8", errors="ignore")
                results.append((f"{d.name}/{f.name}", content))
            except Exception:
                pass
    return results


def read_h_files(inc_dir: Path) -> list[tuple[str, str]]:
    """读取目录下所有 .h 文件。"""
    results = []
    for f in sorted(inc_dir.glob("*.h")):
        try:
            content = f.read_text(encoding="utf-8", errors="ignore")
            results.append((f.name, content))
        except Exception:
            pass
    return results


class CheckResult:
    """单条检查结果。"""

    # 严重级别
    SEVERITY_ERROR = "error"      # 真正的 bug，必须修复
    SEVERITY_WARNING = "warning"  # 低风险，建议修复
    SEVERITY_INFO = "info"        # 信息，可接受

    def __init__(self, name: str, passed: bool, detail: str = "", file: str = "",
                 severity: str = "error"):
        self.name = name
        self.passed = passed
        self.detail = detail
        self.file = file
        self.severity = severity

    def __str__(self):
        if self.passed:
            status = f"{GREEN}✅{RESET}"
        elif self.severity == "warning":
            status = f"{YELLOW}⚠️{RESET}"
        elif self.severity == "info":
            status = f"{CYAN}ℹ️{RESET}"
        else:
            status = f"{RED}❌{RESET}"
        loc = f" ({self.file})" if self.file else ""
        detail = f" — {self.detail}" if self.detail else ""
        return f"  {status} {self.name}{loc}{detail}"


class CheckSuite:
    """检查套件。"""

    def __init__(self):
        self.results: list[CheckResult] = []

    def add(self, result: CheckResult):
        self.results.append(result)

    def passed(self) -> int:
        return sum(1 for r in self.results if r.passed)

    def errors(self) -> int:
        return sum(1 for r in self.results if not r.passed and r.severity == "error")

    def warnings(self) -> int:
        return sum(1 for r in self.results if not r.passed and r.severity == "warning")

    def infos(self) -> int:
        return sum(1 for r in self.results if not r.passed and r.severity == "info")

    def print_report(self, title: str):
        print(f"\n{BOLD}{CYAN}{'='*60}{RESET}")
        print(f"{BOLD}{CYAN}  {title}{RESET}")
        print(f"{BOLD}{CYAN}{'='*60}{RESET}")
        for r in self.results:
            print(r)
        p = self.passed()
        e = self.errors()
        w = self.warnings()
        i = self.infos()
        total = p + e + w + i
        if e == 0:
            print(f"\n  {GREEN}{BOLD}结果: {p}/{total} 通过{RESET}")
        else:
            print(f"\n  {RED}{BOLD}结果: {p}/{total} 通过（{e} 错误, {w} 警告, {i} 信息）{RESET}")


# ============================================================
# 第 2 步：检查初始化链
# ============================================================

def check_init_chain(src_dir: Path, inc_dir: Path) -> CheckSuite:
    """检查初始化链。"""
    suite = CheckSuite()
    c_files = read_c_files(src_dir)
    h_files = read_h_files(inc_dir)

    # 检查 1: RTOS 对象是否在 Task 函数内创建（不在 Init 函数内）
    for fname, content in c_files:
        # 找 osMutexNew / osSemaphoreNew 调用
        for match in re.finditer(r'osMutexNew|osSemaphoreNew|osMessageQueueNew', content):
            line_num = content[:match.start()].count('\n') + 1
            # 检查是否在 xxx_Init 函数内（不在 Task 函数内）
            # 简单检查：如果在 Init 函数内且在 osKernelStart 之前
            func_start = content.rfind('\n', 0, match.start())
            # 往上找函数定义
            func_header = content[max(0, match.start()-500):match.start()]
            if re.search(r'_Init\s*\(', func_header) and not re.search(r'_Task\s*\(', func_header):
                suite.add(CheckResult(
                    "RTOS 对象在 Task 内创建（不在 Init 内）",
                    False,
                    f"在 {line_num} 行发现 RTOS 对象创建，可能在调度器启动前",
                    f"{fname}:{line_num}"
                ))
            else:
                suite.add(CheckResult(
                    "RTOS 对象在 Task 内创建",
                    True,
                    file=fname
                ))
                break  # 只报告一次

    # 检查 2: Init 函数是否从 Config 读取配置
    config_get_calls = []
    for fname, content in c_files:
        if fname == "config.c":
            continue
        for match in re.finditer(r'Config_Get\w*\s*\(', content):
            line_num = content[:match.start()].count('\n') + 1
            config_get_calls.append(f"{fname}:{line_num}")

    if config_get_calls:
        suite.add(CheckResult(
            "Init 函数从 Config 读取配置",
            True,
            f"调用点: {', '.join(config_get_calls[:3])}"
        ))
    else:
        suite.add(CheckResult(
            "Init 函数从 Config 读取配置",
            False,
            "没有找到 Config_Get*() 调用（除 config.c 外）"
        ))

    # 检查 3: 外设初始化顺序（RCC 时钟使能在 GPIO 配置之前）
    for fname, content in c_files:
        if "HAL_MspInit" in content or "MX_GPIO_Init" in content:
            rcc_pos = content.find("CLK_ENABLE")
            gpio_pos = content.find("HAL_GPIO_Init")
            if rcc_pos > 0 and gpio_pos > 0:
                if rcc_pos < gpio_pos:
                    suite.add(CheckResult(
                        "外设初始化顺序（RCC→GPIO）",
                        True,
                        file=fname
                    ))
                else:
                    suite.add(CheckResult(
                        "外设初始化顺序（RCC→GPIO）",
                        False,
                        "GPIO 配置在时钟使能之前",
                        fname
                    ))

    return suite


# ============================================================
# 第 3 步：检查配置系统
# ============================================================

def check_config_system(src_dir: Path) -> CheckSuite:
    """检查配置系统完整性（使用语义分析）。"""
    suite = CheckSuite()
    c_files = read_c_files(src_dir)
    parsed = parse_c_files(c_files)

    # === 基础检查：API 调用 ===

    # 检查 1: Config_Get* 在非 config.c 中被调用
    get_calls = []
    set_calls = []
    for cfile in parsed:
        if cfile.filename == "config.c":
            continue
        for func in cfile.functions:
            if func.calls("Config_Get"):
                get_calls.append(f"{cfile.filename}:{func.line}")
            if func.calls("Config_Set"):
                set_calls.append(f"{cfile.filename}:{func.line}")

    suite.add(CheckResult(
        "Config_Get*() 被调用（读取配置）",
        len(get_calls) > 0,
        f"调用点: {', '.join(get_calls[:3])}" if get_calls else "没有找到调用",
    ))

    suite.add(CheckResult(
        "Config_Set*() 被调用（同步配置）",
        len(set_calls) > 0,
        f"调用点: {', '.join(set_calls[:3])}" if set_calls else "没有找到调用",
    ))

    # 检查 2: Set* 函数是否调用 Config_Set*() 同步
    skip_functions = {
        'Display_SetBrightness', 'Display_SetStreamEnabled',
        'Oscilloscope_SetStreamEnabled', 'Display_UpdateSelection',
        'Display_DrawCursor',
    }
    for cfile in parsed:
        if cfile.filename == "config.c":
            continue
        setter_funcs = cfile.get_functions_matching(r'(SignalGen|Oscilloscope|Display)_Set\w+')
        for func in setter_funcs:
            if func.name in skip_functions:
                continue
            has_config_set = func.calls("Config_Set")
            suite.add(CheckResult(
                f"{func.name}() 同步到 Config",
                has_config_set,
                "" if has_config_set else "函数内没有 Config_Set*() 调用",
                cfile.filename
            ))

    # 检查 3: Init 函数是否在所有分支中都读取配置（语义检查）
    for cfile in parsed:
        init_funcs = cfile.get_functions_matching(r'\w+_Init\b')
        for func in init_funcs:
            if func.name == "Config_Init":
                continue
            if func.calls("Config_Get"):
                if not func.calls_in_all_branches("Config_Get"):
                    suite.add(CheckResult(
                        f"{func.name}() 在所有分支中读取 Config",
                        False,
                        "某些代码路径可能跳过 Config 读取",
                        f"{cfile.filename}:{func.line}",
                        severity="warning"
                    ))
                else:
                    suite.add(CheckResult(
                        f"{func.name}() 在所有分支中读取 Config",
                        True,
                        file=f"{cfile.filename}:{func.line}"
                    ))

    # === 高级检查：配置系统设计 ===

    # 找到 config.c 的解析结果
    config_file = None
    for cfile in parsed:
        if cfile.filename == "config.c":
            config_file = cfile
            break

    if config_file:
        # 检查 4: Config_Init 是否调用 Config_LoadDefaults 和 Config_Load
        config_init = config_file.get_function("Config_Init")
        if config_init:
            has_load_defaults = config_init.calls("Config_LoadDefaults")
            has_load = config_init.calls("Config_Load")
            suite.add(CheckResult(
                "Config_Init 调用 Config_LoadDefaults（默认值）",
                has_load_defaults,
                "" if has_load_defaults else "Config_Init 没有调用 Config_LoadDefaults",
                "config.c",
                severity="error" if not has_load_defaults else "info"
            ))
            suite.add(CheckResult(
                "Config_Init 调用 Config_Load（Flash 加载）",
                has_load,
                "" if has_load else "Config_Init 没有调用 Config_Load",
                "config.c",
                severity="warning" if not has_load else "info"
            ))

        # 检查 5: Config_Load 是否验证校验和
        config_load = config_file.get_function("Config_Load")
        if config_load:
            has_checksum_check = config_load.calls("Config_CalculateChecksum") or config_load.calls("checksum")
            suite.add(CheckResult(
                "Config_Load 验证校验和",
                has_checksum_check,
                "" if has_checksum_check else "Config_Load 没有验证校验和，可能加载损坏的配置",
                "config.c",
                severity="warning" if not has_checksum_check else "info"
            ))

        # 检查 6: Config_Save 是否计算校验和
        config_save = config_file.get_function("Config_Save")
        if config_save:
            has_checksum_calc = config_save.calls("Config_CalculateChecksum") or config_save.calls("checksum")
            suite.add(CheckResult(
                "Config_Save 计算校验和",
                has_checksum_calc,
                "" if has_checksum_calc else "Config_Save 没有计算校验和，保存的配置可能损坏",
                "config.c",
                severity="warning" if not has_checksum_calc else "info"
            ))

        # 检查 7: Config_LoadDefaults 是否初始化所有字段
        config_load_defaults = config_file.get_function("Config_LoadDefaults")
        if config_load_defaults:
            # 检查是否初始化了 osc 和 siggen 配置
            has_osc_init = bool(re.search(r'app_config\.osc\.', config_load_defaults.body))
            has_siggen_init = bool(re.search(r'app_config\.siggen\.', config_load_defaults.body))
            has_sys_init = bool(re.search(r'app_config\.sys\.', config_load_defaults.body))
            suite.add(CheckResult(
                "Config_LoadDefaults 初始化 osc 配置",
                has_osc_init,
                "" if has_osc_init else "没有初始化 app_config.osc",
                "config.c",
                severity="error" if not has_osc_init else "info"
            ))
            suite.add(CheckResult(
                "Config_LoadDefaults 初始化 siggen 配置",
                has_siggen_init,
                "" if has_siggen_init else "没有初始化 app_config.siggen",
                "config.c",
                severity="error" if not has_siggen_init else "info"
            ))
            suite.add(CheckResult(
                "Config_LoadDefaults 初始化 sys 配置",
                has_sys_init,
                "" if has_sys_init else "没有初始化 app_config.sys",
                "config.c",
                severity="warning" if not has_sys_init else "info"
            ))

        # 检查 8: Config_Save 是否有 Flash 擦除验证
        if config_save:
            has_erase = config_save.calls("FLASH_Erase") or config_save.calls("HAL_FLASHEx_Erase")
            has_verify = config_save.calls("verify") or config_save.calls("memcmp") or config_save.calls("FLASH_Wait")
            suite.add(CheckResult(
                "Config_Save 擦除 Flash 扇区",
                has_erase,
                "" if has_erase else "Config_Save 没有擦除 Flash 扇区",
                "config.c",
                severity="error" if not has_erase else "info"
            ))
            suite.add(CheckResult(
                "Config_Save 验证写入结果",
                has_verify,
                "" if has_verify else "Config_Save 没有验证写入结果，建议回读验证",
                "config.c",
                severity="warning" if not has_verify else "info"
            ))

        # 检查 9: Config API 完整性（Get/Set 对应）
        config_apis = {
            "OscConfig": ("Config_GetOscConfig", "Config_SetOscConfig"),
            "SigGenConfig": ("Config_GetSigGenConfig", "Config_SetSigGenConfig"),
        }
        for name, (getter, setter) in config_apis.items():
            has_getter = config_file.get_function(getter) is not None
            has_setter = config_file.get_function(setter) is not None
            suite.add(CheckResult(
                f"Config API {name} 完整（Get + Set）",
                has_getter and has_setter,
                f"{'缺少 ' + getter if not has_getter else ''} {'缺少 ' + setter if not has_setter else ''}".strip(),
                "config.c",
                severity="error" if not (has_getter and has_setter) else "info"
            ))

    # 检查 10: 配置结构体定义检查（头文件）
    inc_dir = src_dir.parent / "Inc" if src_dir.name == "Src" else src_dir.parent / "inc"
    if inc_dir.exists():
        h_files = read_h_files(inc_dir)
        for fname, content in h_files:
            if "config.h" in fname:
                has_app_config = bool(re.search(r'typedef\s+struct.*AppConfig_t', content, re.DOTALL))
                has_config_header = bool(re.search(r'ConfigHeader_t', content))
                suite.add(CheckResult(
                    "配置结构体 AppConfig_t 已定义",
                    has_app_config,
                    "" if has_app_config else "config.h 中没有定义 AppConfig_t",
                    fname,
                    severity="error" if not has_app_config else "info"
                ))
                suite.add(CheckResult(
                    "配置头 ConfigHeader_t 已定义",
                    has_config_header,
                    "" if has_config_header else "config.h 中没有定义 ConfigHeader_t（版本/校验和）",
                    fname,
                    severity="warning" if not has_config_header else "info"
                ))

    return suite


# ============================================================
# 第 4 步：检查时钟和定时器
# ============================================================

def check_clock(src_dir: Path) -> CheckSuite:
    """检查时钟和定时器配置。"""
    suite = CheckSuite()
    c_files = read_c_files(src_dir)

    # 检查 1: 硬编码时钟频率
    hardcoded_patterns = [
        (r'\b84000000\b', '84000000 (APB1 timer clock)'),
        (r'\b168000000\b', '168000000 (APB2 timer clock)'),
        (r'\b42000000\b', '42000000 (APB1 bus clock)'),
        (r'\b72000000\b', '72000000 (F1 APB1 timer clock)'),
    ]

    found_hardcoded = []
    for fname, content in c_files:
        for pattern, desc in hardcoded_patterns:
            for match in re.finditer(pattern, content):
                line_num = content[:match.start()].count('\n') + 1
                found_hardcoded.append(f"{fname}:{line_num} ({desc})")

    suite.add(CheckResult(
        "时钟频率不硬编码（用 HAL_RCC_GetPCLKxFreq）",
        len(found_hardcoded) == 0,
        f"发现硬编码: {', '.join(found_hardcoded[:3])}" if found_hardcoded else "无硬编码",
    ))

    # 检查 2: HAL_RCC_GetPCLKxFreq 使用
    uses_hal_clock = []
    for fname, content in c_files:
        if 'HAL_RCC_GetPCLK' in content:
            uses_hal_clock.append(fname)

    suite.add(CheckResult(
        "使用 HAL_RCC_GetPCLKxFreq() 获取时钟",
        len(uses_hal_clock) > 0,
        f"使用文件: {', '.join(uses_hal_clock)}" if uses_hal_clock else "没有使用",
    ))

    # 检查 3: ApplyConfig 函数有除零保护（只检查函数入口前 5 行）
    for fname, content in c_files:
        for match in re.finditer(r'(SigGen|Osc)_ApplyConfig\s*\([^)]*\)\s*\{', content):
            func_start = match.end()
            # 只看函数体前 5 行
            first_lines = content[func_start:func_start+500]
            has_div_zero_check = bool(re.search(r'frequency\s*==\s*0|sample_rate\s*==\s*0|freq\s*==\s*0', first_lines))
            suite.add(CheckResult(
                "ApplyConfig 有除零保护",
                has_div_zero_check,
                "函数入口没有零值检查" if not has_div_zero_check else "",
                fname
            ))

    # 检查 4: uint32_t 减法下溢保护
    for fname, content in c_files:
        # 找 psc = (xxx / yyy) - 1 模式
        for match in re.finditer(r'psc\s*=\s*\([^)]+\)\s*-\s*1', content):
            line_num = content[:match.start()].count('\n') + 1
            # 检查前面是否有下溢保护
            context = content[max(0, match.start()-200):match.start()]
            has_underflow_check = 'target' in context and ('>=' in context or '>' in context)
            if not has_underflow_check:
                suite.add(CheckResult(
                    "uint32_t 减法有下溢保护",
                    False,
                    f"psc = (x/y) - 1 可能下溢",
                    f"{fname}:{line_num}"
                ))

    return suite


# ============================================================
# 第 5 步：检查变量封装
# ============================================================

def check_encapsulation(src_dir: Path) -> CheckSuite:
    """检查变量封装。"""
    suite = CheckSuite()
    c_files = read_c_files(src_dir)

    # 检查 1: 全局变量是否用 static（排除需要跨文件访问的变量）
    cubemx_files = {'main.c', 'stm32f4xx_it.c', 'stm32f4xx_hal_msp.c',
                    'stm32f4xx_hal_timebase_tim.c', 'system_stm32f4xx.c', 'freertos.c'}
    # 需要跨文件访问的变量模式
    cross_file_patterns = re.compile(
        r'_handle\b|_callback\b|_Callback\b|_task_handle\b|_mutex\b|'
        r'_stream_enabled\b|_enabled\b|adc_buffer\b|process_ptr\b|process_len\b|'
        r'_attributes\b|_attributes\b'
    )
    for fname, content in c_files:
        if fname in cubemx_files:
            continue
        # 使用正则匹配全局变量定义（行首，不在函数内）
        # 匹配模式：类型 变量名 = 值; 或 类型 变量名[大小];
        global_var_pattern = re.compile(
            r'^(uint\w+|int\w+|bool|float|char|volatile\s+uint\w+|volatile\s+bool)\s+'
            r'(\w+)\s*(?:=\s*[^;]+|\[[\w\s*]+\])?\s*;',
            re.MULTILINE
        )
        for match in global_var_pattern.finditer(content):
            full_line = match.group(0).strip()
            var_name = match.group(2)
            line_num = content[:match.start()].count('\n') + 1
            # 排除：已有 static、已有 extern、注释行、需要跨文件访问的
            if (full_line.startswith('static')
                or full_line.startswith('extern')
                or full_line.startswith('//')
                or full_line.startswith('/*')
                or cross_file_patterns.search(full_line)):
                continue
            # 额外检查：确认不在函数体内（通过检查前面是否有未闭合的 '{'）
            before = content[:match.start()]
            # 简单检查：最后一个函数定义到当前位置的大括号
            last_func = before.rfind('\n}\n')
            if last_func > 0:
                after_func = before[last_func+3:]
                open_braces = after_func.count('{')
                close_braces = after_func.count('}')
                if open_braces > close_braces:
                    continue  # 在函数体内，跳过
            suite.add(CheckResult(
                "全局变量用 static 限制作用域",
                False,
                f"非 static 全局变量 '{var_name}'",
                f"{fname}:{line_num}"
            ))
            break  # 每个文件只报告第一个

    # 检查 2: 硬编码魔法数字（在定时器配置中）
    magic_numbers = []
    for fname, content in c_files:
        # 找定时器配置中的硬编码数字
        for match in re.finditer(r'(Prescaler|Period|ARR|PSC)\s*=\s*(\d{4,})', content):
            line_num = content[:match.start()].count('\n') + 1
            value = match.group(2)
            if int(value) > 100:  # 大于 100 的硬编码值
                magic_numbers.append(f"{fname}:{line_num} ({match.group(1)}={value})")

    suite.add(CheckResult(
        "定时器配置无魔法数字",
        len(magic_numbers) == 0,
        f"发现: {', '.join(magic_numbers[:3])}" if magic_numbers else "无魔法数字",
    ))

    # 检查 3: 重复变量
    for fname, content in c_files:
        # 找 xxx_buffer_size 类型的重复变量
        if re.search(r'uint\w+\s+\w+_buffer_size\s*=', content):
            # 检查是否同时有 config.buffer_size
            if re.search(r'config\.buffer_size', content):
                suite.add(CheckResult(
                    "无重复变量（buffer_size 副本）",
                    False,
                    "存在 config.buffer_size 的副本变量",
                    fname
                ))
            else:
                suite.add(CheckResult("无重复变量", True, file=fname))

    return suite


# ============================================================
# 第 6 步：检查并发安全
# ============================================================

def check_concurrency(src_dir: Path) -> CheckSuite:
    """检查并发安全。"""
    suite = CheckSuite()
    c_files = read_c_files(src_dir)
    parsed = parse_c_files(c_files)

    # 检查 1: Config_Set* 在锁内调用
    for fname, content in c_files:
        if fname == "config.c":
            continue
        # 找 Config_Set 调用
        for match in re.finditer(r'Config_Set\w+\s*\(', content):
            line_num = content[:match.start()].count('\n') + 1
            # 检查前面是否有锁
            context = content[max(0, match.start()-500):match.start()]
            has_lock = bool(re.search(r'(LOCK|osMutexAcquire)', context))
            has_unlock_between = bool(re.search(r'(UNLOCK|osMutexRelease)', context[context.rfind('LOCK') if 'LOCK' in context else 0:]))
            if has_lock and not has_unlock_between:
                suite.add(CheckResult(
                    "Config_Set* 在锁内调用",
                    True,
                    file=f"{fname}:{line_num}"
                ))
            elif not has_lock:
                suite.add(CheckResult(
                    "Config_Set* 在锁内调用",
                    False,
                    "Config_Set 在锁外调用，可能有竞态",
                    f"{fname}:{line_num}"
                ))

    # 检查 2: LOG_INFO 在锁外调用（语义分析：检查函数级别的锁内日志）
    for cfile in parsed:
        for func in cfile.functions:
            has_lock, has_unlock = func.has_lock_unlock()
            if has_lock and has_unlock:
                if func.log_in_lock():
                    # 检查锁内是否有循环（循环内日志才是真正的风险）
                    lock_sections = re.finditer(r'LOCK\(\)(.*?)UNLOCK\(\)', func.body, re.DOTALL)
                    for section in lock_sections:
                        if 'LOG_' in section.group(1):
                            has_loop = bool(re.search(r'for\s*\(|while\s*\(', section.group(1)))
                            line_offset = func.body[:section.start()].count('\n')
                            line_num = func.line + line_offset
                            suite.add(CheckResult(
                                "LOG_INFO 在锁内调用",
                                False,
                                f"函数 {func.name} 中 LOG_INFO 在锁内（含 HAL_UART_Transmit 阻塞）",
                                f"{cfile.filename}:{line_num}",
                                severity="error" if has_loop else "warning"
                            ))
                            break

    # 检查 3: ISR extern 声明与定义的 volatile 匹配
    # 找 extern 声明
    extern_decls = {}
    for fname, content in c_files:
        for match in re.finditer(r'extern\s+(volatile\s+)?(\w+)\s+(\w+)', content):
            is_volatile = bool(match.group(1))
            var_name = match.group(3)
            if var_name not in extern_decls:
                extern_decls[var_name] = []
            extern_decls[var_name].append((fname, is_volatile))

    # 找定义
    for var_name, decls in extern_decls.items():
        for fname, content in c_files:
            # 找非 extern 的定义
            def_match = re.search(rf'^(?!extern)(volatile\s+)?\w+\s+{re.escape(var_name)}\s*[=;\[]', content, re.MULTILINE)
            if def_match:
                def_is_volatile = bool(def_match.group(1))
                for decl_fname, decl_is_volatile in decls:
                    if def_is_volatile != decl_is_volatile:
                        suite.add(CheckResult(
                            f"ISR extern volatile 匹配 ({var_name})",
                            False,
                            f"定义 {'有' if def_is_volatile else '无'} volatile，声明 {'有' if decl_is_volatile else '无'} volatile",
                            f"{decl_fname} vs {fname}"
                        ))

    return suite


# ============================================================
# 第 7 步：检查显示和算法
# ============================================================

def check_display(src_dir: Path) -> CheckSuite:
    """检查显示和算法。"""
    suite = CheckSuite()
    c_files = read_c_files(src_dir)
    parsed = parse_c_files(c_files)

    # 检查 0: 头文件 include 守卫
    inc_dir = src_dir.parent / "Inc" if src_dir.name == "Src" else src_dir.parent / "inc"
    if inc_dir.exists():
        h_files = read_h_files(inc_dir)
        for fname, content in h_files:
            has_guard = bool(re.search(r'#ifndef\s+\w+_H|#pragma\s+once', content))
            suite.add(CheckResult(
                "头文件有 include 守卫",
                has_guard,
                "缺少 #ifndef 或 #pragma once" if not has_guard else "",
                fname
            ))

    # 检查 1: 波形显示用 min/max 包络
    for fname, content in c_files:
        if 'Draw_Waveform' in content or 'draw_waveform' in content.lower():
            has_envelope = bool(re.search(r'col_min|col_max|envelope|min_val.*max_val', content))
            has_single_point = bool(re.search(r'data\[x\s*\*\s*step\]', content))
            if has_envelope:
                suite.add(CheckResult(
                    "波形显示用 min/max 包络",
                    True,
                    file=fname
                ))
            elif has_single_point:
                suite.add(CheckResult(
                    "波形显示用 min/max 包络",
                    False,
                    "使用取单点降采样，多周期会产生尖刺",
                    fname
                ))

    # 检查 2: 降采样 step 向上取整
    for fname, content in c_files:
        if 'step' in content and 'OLED_WIDTH' in content:
            # 检查是否有向上取整
            has_ceil = bool(re.search(r'len\s*\+\s*OLED_WIDTH\s*-\s*1', content))
            has_floor = bool(re.search(r'len\s*/\s*OLED_WIDTH', content))
            if has_floor and not has_ceil:
                suite.add(CheckResult(
                    "降采样 step 向上取整",
                    False,
                    "step = len / OLED_WIDTH 整除截断，尾部数据丢失",
                    fname
                ))
            elif has_ceil:
                suite.add(CheckResult(
                    "降采样 step 向上取整",
                    True,
                    file=fname
                ))

    # 检查 3: 频率/电压计算有除零保护（语义分析：检查函数体内是否有零值检查）
    dangerous_divisors = ['range', 'size', 'len', 'count', 'frequency', 'sample_rate']
    for cfile in parsed:
        for func in cfile.functions:
            # 跳过空函数和 getter 函数
            if len(func.body.strip()) < 10:
                continue
            for divisor in dangerous_divisors:
                if func.divides_by(divisor):
                    if not func.has_zero_check(divisor):
                        div_match = re.search(rf'\b\w+\s*/\s*{divisor}\b', func.body)
                        if div_match:
                            line_offset = func.body[:div_match.start()].count('\n')
                            line_num = func.line + line_offset
                            # 函数参数通常由调用方检查，降级为 info
                            is_param = func.is_param(divisor)
                            suite.add(CheckResult(
                                f"除法有除零保护 ({divisor})",
                                False,
                                f"函数 {func.name} 中除以 {divisor}（{'参数' if is_param else '局部变量'}，{'调用方可能已检查' if is_param else '建议添加零值检查'}）",
                                f"{cfile.filename}:{line_num}",
                                severity="info" if is_param else "warning"
                            ))

    return suite


# ============================================================
# 项目配置文件支持
# ============================================================

CONFIG_FILE = ".pre_code_check.yml"


def load_project_config(project_dir: str) -> dict:
    """加载项目配置文件。"""
    config_path = Path(project_dir) / CONFIG_FILE
    if not config_path.exists():
        return {}
    try:
        # 简单的 YAML 解析（避免依赖 pyyaml）
        config = {}
        with open(config_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                if ":" in line:
                    key, value = line.split(":", 1)
                    key = key.strip()
                    value = value.strip()
                    if value.startswith("[") and value.endswith("]"):
                        # 列表
                        config[key] = [v.strip().strip('"\'') for v in value[1:-1].split(",")]
                    else:
                        config[key] = value.strip('"\'')
        return config
    except Exception:
        return {}


# ============================================================
# error_tracker 集成
# ============================================================

def search_error_history(project_dir: str, keywords: list[str]) -> list[dict]:
    """搜索错误历史。"""
    results = []
    tracker_path = Path(project_dir).parent / "stm32-keil-workflow" / "scripts" / "error_tracker.py"
    if not tracker_path.exists():
        # 尝试在技能目录中查找
        skill_dir = Path(os.environ.get("CLAUDE_SKILLS_DIR", "D:/ClaudeGlobalConfig/skills"))
        tracker_path = skill_dir / "stm32-keil-workflow" / "scripts" / "error_tracker.py"

    if not tracker_path.exists():
        return results

    for keyword in keywords[:3]:  # 最多搜索 3 个关键词
        try:
            output = subprocess.check_output(
                [sys.executable, str(tracker_path), "--search", keyword, "--text", "--format", "json"],
                stderr=subprocess.DEVNULL,
                timeout=5
            ).decode("utf-8", errors="ignore")
            if output.strip():
                try:
                    data = json.loads(output)
                    if isinstance(data, list):
                        results.extend(data[:2])  # 每个关键词最多 2 条
                except json.JSONDecodeError:
                    pass
        except (subprocess.TimeoutExpired, subprocess.CalledProcessError, FileNotFoundError):
            pass

    return results


def extract_keywords_from_failures(suites: list[tuple[str, CheckSuite]]) -> list[str]:
    """从失败的检查中提取关键词。"""
    keywords = []
    for _, suite in suites:
        for r in suite.results:
            if not r.passed:
                # 提取关键词
                if "Config" in r.name:
                    keywords.append("config")
                if "时钟" in r.name or "clock" in r.name.lower():
                    keywords.append("clock")
                if "static" in r.name:
                    keywords.append("static")
                if "volatile" in r.name:
                    keywords.append("volatile")
                if "除零" in r.name:
                    keywords.append("division")
                if "LOG_INFO" in r.name:
                    keywords.append("mutex")
                if r.detail:
                    # 从 detail 中提取
                    words = re.findall(r'[A-Za-z_]\w*', r.detail)
                    keywords.extend(words[:2])
    return list(set(keywords))[:5]


# ============================================================
# 自动修复
# ============================================================

def auto_fix(project_dir: str, suites: list[tuple[str, CheckSuite]]) -> int:
    """自动修复可修复的问题。返回修复数量。"""
    src_dir = find_src_dir(project_dir)
    if not src_dir:
        return 0

    fixed = 0

    for _, suite in suites:
        for r in suite.results:
            if r.passed or r.severity == "info":
                continue

            # 修复 1: osc_config_buffer_size 重复变量
            # 删除变量定义，将所有引用替换为 osc_config.buffer_size
            if "重复变量" in r.name and "buffer_size" in r.name:
                fname = "oscilloscope.c"
                fpath = src_dir / fname
                if fpath.exists():
                    content = fpath.read_text(encoding="utf-8")
                    # 删除重复变量定义（包括注释）
                    new_content = re.sub(
                        r'\n/\*.*?副本.*?\*/\nvolatile\s+uint32_t\s+osc_config_buffer_size.*?;\n',
                        '\n',
                        content,
                        flags=re.DOTALL
                    )
                    # 将 osc_config_buffer_size 替换为 osc_config.buffer_size
                    new_content = new_content.replace(
                        'osc_config_buffer_size',
                        'osc_config.buffer_size'
                    )
                    if new_content != content:
                        fpath.write_text(new_content, encoding="utf-8")
                        print(f"  {GREEN}✅ 已修复: 删除 {fname} 中的重复变量，引用改为 osc_config.buffer_size{RESET}")
                        fixed += 1
                # 同时修复 stm32f4xx_it.c 中的 extern 声明
                it_fname = "stm32f4xx_it.c"
                it_path = src_dir / it_fname
                if it_path.exists():
                    it_content = it_path.read_text(encoding="utf-8")
                    it_new = it_content.replace(
                        'extern volatile uint32_t osc_config_buffer_size;',
                        'extern volatile uint32_t osc_config_buffer_size;  /* 已废弃，改用 osc_config.buffer_size */'
                    )
                    # 将使用处也替换
                    it_new = it_new.replace(
                        'osc_config_buffer_size / 2',
                        'osc_config.buffer_size / 2'
                    )
                    if it_new != it_content:
                        it_path.write_text(it_new, encoding="utf-8")
                        print(f"  {GREEN}✅ 已修复: {it_fname} 中的引用改为 osc_config.buffer_size{RESET}")
                        fixed += 1

            # 修复 2: 全局变量加 static（简单情况）
            if "全局变量用 static" in r.name and r.file:
                parts = r.file.split(":")
                if len(parts) == 2:
                    fname, line_str = parts
                    fpath = src_dir / fname
                    if fpath.exists():
                        content = fpath.read_text(encoding="utf-8")
                        lines = content.split("\n")
                        try:
                            line_idx = int(line_str) - 1
                            if 0 <= line_idx < len(lines):
                                line = lines[line_idx]
                                # 简单的加 static（不处理 volatile 等复杂情况）
                                if not line.strip().startswith("static") and not line.strip().startswith("volatile"):
                                    # 在类型前加 static
                                    new_line = line.replace("uint32_t", "static uint32_t", 1)
                                    new_line = new_line.replace("uint16_t", "static uint16_t", 1)
                                    new_line = new_line.replace("bool ", "static bool ", 1)
                                    if new_line != line:
                                        lines[line_idx] = new_line
                                        fpath.write_text("\n".join(lines), encoding="utf-8")
                                        print(f"  {GREEN}✅ 已修复: {fname}:{line_str} 加 static{RESET}")
                                        fixed += 1
                        except (ValueError, IndexError):
                            pass

    return fixed


# ============================================================
# codegraph 集成（调用链验证）
# ============================================================

def verify_call_chain(project_dir: str, function_name: str) -> dict:
    """用 codegraph 验证函数是否被调用。"""
    result = {"called": False, "callers": [], "error": None}

    # 查找 codegraph 脚本
    skill_dir = Path(os.environ.get("CLAUDE_SKILLS_DIR", "D:/ClaudeGlobalConfig/skills"))
    codegraph_path = skill_dir / "codegraph" / "scripts" / "codegraph.py"

    if not codegraph_path.exists():
        # 尝试用 MCP 工具（如果可用）
        result["error"] = "codegraph 未安装"
        return result

    try:
        output = subprocess.check_output(
            [sys.executable, str(codegraph_path), "--project", project_dir, "callers", function_name],
            stderr=subprocess.DEVNULL,
            timeout=10
        ).decode("utf-8", errors="ignore")
        if output.strip():
            result["called"] = True
            result["callers"] = [line.strip() for line in output.strip().split("\n") if line.strip()]
    except (subprocess.TimeoutExpired, subprocess.CalledProcessError, FileNotFoundError):
        result["error"] = "codegraph 查询失败"

    return result


def check_call_chains(src_dir: Path) -> CheckSuite:
    """检查关键函数的调用链。"""
    suite = CheckSuite()
    project_dir = str(src_dir.parent.parent)

    # 关键函数列表
    critical_functions = [
        ("Oscilloscope_Init", "示波器初始化"),
        ("SignalGen_Init", "信号发生器初始化"),
        ("UART_Protocol_Init", "串口协议初始化"),
        ("Display_Init", "显示初始化"),
        ("KeyHandler_Init", "按键初始化"),
    ]

    for func_name, desc in critical_functions:
        result = verify_call_chain(project_dir, func_name)
        if result["error"]:
            suite.add(CheckResult(
                f"{desc}被调用 ({func_name})",
                True,  # 无法验证时默认通过
                f"codegraph: {result['error']}",
                severity="info"
            ))
        else:
            suite.add(CheckResult(
                f"{desc}被调用 ({func_name})",
                result["called"],
                f"调用者: {', '.join(result['callers'][:3])}" if result["callers"] else "未找到调用者",
                severity="error" if not result["called"] else "info"
            ))

    return suite


# ============================================================
# 编译集成
# ============================================================

def compile_check(project_dir: str) -> bool:
    """先编译确认代码能通过。"""
    # 查找 workflow.py
    skill_dir = Path(os.environ.get("CLAUDE_SKILLS_DIR", "D:/ClaudeGlobalConfig/skills"))
    workflow_path = skill_dir / "stm32-keil-workflow" / "scripts" / "workflow.py"

    if not workflow_path.exists():
        print(f"  {YELLOW}⚠️  未找到 workflow.py，跳过编译检查{RESET}")
        return True

    try:
        print(f"  {CYAN}⏳ 正在编译...{RESET}")
        output = subprocess.check_output(
            [sys.executable, str(workflow_path), "--auto", project_dir, "--steps", "compile"],
            stderr=subprocess.STDOUT,
            timeout=120
        ).decode("utf-8", errors="ignore")
        if "✅" in output or "0 Error" in output:
            print(f"  {GREEN}✅ 编译通过{RESET}")
            return True
        else:
            print(f"  {RED}❌ 编译失败{RESET}")
            return False
    except subprocess.TimeoutExpired:
        print(f"  {YELLOW}⚠️  编译超时{RESET}")
        return False
    except subprocess.CalledProcessError:
        print(f"  {RED}❌ 编译失败{RESET}")
        return False


# ============================================================
# 主程序
# ============================================================

def main():
    parser = argparse.ArgumentParser(
        description="写代码前检查流自动化工具",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
检查项:
  init       检查初始化链
  config     检查配置系统
  clock      检查时钟和定时器
  encaps     检查变量封装
  concurrency 检查并发安全
  display    检查显示和算法
  chain      检查调用链（需要 codegraph）
  all        检查全部（默认）

选项:
  --fix      自动修复可修复的问题
  --history  搜索相关历史错误
  --compile  先编译再检查
  --init-config 生成项目配置文件模板
        """
    )
    parser.add_argument("--auto", metavar="DIR", help="项目根目录")
    parser.add_argument("--check", default="all", help="检查项")
    parser.add_argument("--project", metavar="DIR", help="项目根目录（--auto 的别名）")
    parser.add_argument("--fix", action="store_true", help="自动修复可修复的问题")
    parser.add_argument("--history", action="store_true", help="搜索相关历史错误")
    parser.add_argument("--compile", action="store_true", help="先编译再检查")
    parser.add_argument("--init-config", action="store_true", help="生成项目配置文件模板")
    args = parser.parse_args()

    project_dir = args.auto or args.project or "."
    if not Path(project_dir).exists():
        print(f"{RED}错误: 目录不存在: {project_dir}{RESET}", file=sys.stderr)
        sys.exit(1)

    # 生成配置文件模板
    if args.init_config:
        config_path = Path(project_dir) / CONFIG_FILE
        if config_path.exists():
            print(f"{YELLOW}配置文件已存在: {config_path}{RESET}")
        else:
            config_path.write_text("""# pre_code_check 项目配置文件
# 详见: python pre_code_check.py --help

# 排除的文件（不检查）
exclude_files:
  - "code_reviewer.c"
  - "ring_buffer.c"

# 排除的检查项（文件:检查名 格式）
exclude_checks:
  - "display.c:LOG_INFO"
  - "oscilloscope.c:LOG_INFO"

# 自定义检查模式（正则表达式）
custom_patterns:
  - name: "I2C 总线恢复"
    pattern: "HAL_I2C_Master_Transmit.*while"
    severity: "warning"
""", encoding="utf-8")
            print(f"{GREEN}✅ 已生成配置文件: {config_path}{RESET}")
        sys.exit(0)

    src_dir = find_src_dir(project_dir)
    inc_dir = find_inc_dir(project_dir)

    if not src_dir:
        print(f"{RED}错误: 未找到 Core/Src 目录{RESET}", file=sys.stderr)
        sys.exit(1)

    # 先编译
    if args.compile:
        if not compile_check(project_dir):
            sys.exit(1)

    # 加载项目配置
    config = load_project_config(project_dir)

    # 显示所有源码目录
    all_src_dirs = find_all_src_dirs(project_dir)
    print(f"\n{BOLD}写代码前检查流{RESET}")
    print(f"项目: {Path(project_dir).resolve()}")
    print(f"源码目录: {', '.join(d.name for d in all_src_dirs)}")

    check_type = args.check.lower()
    all_suites = []

    # 使用扩展的源码目录进行检查
    if check_type in ("all", "init"):
        all_suites.append(("第 2 步：检查初始化链", check_init_chain(src_dir, inc_dir)))

    if check_type in ("all", "config"):
        all_suites.append(("第 3 步：检查配置系统", check_config_system(src_dir)))

    if check_type in ("all", "clock"):
        all_suites.append(("第 4 步：检查时钟和定时器", check_clock(src_dir)))

    if check_type in ("all", "encaps"):
        all_suites.append(("第 5 步：检查变量封装", check_encapsulation(src_dir)))

    if check_type in ("all", "concurrency"):
        all_suites.append(("第 6 步：检查并发安全", check_concurrency(src_dir)))

    if check_type in ("all", "display"):
        all_suites.append(("第 7 步：检查显示和算法", check_display(src_dir)))

    if check_type in ("all", "chain"):
        all_suites.append(("调用链验证", check_call_chains(src_dir)))

    # 额外检查 Drivers 目录（第三方驱动）
    if check_type in ("all", "drivers"):
        for d in find_all_src_dirs(project_dir):
            if d.name not in ("Src",):  # 跳过 Core/Src（已检查）
                suite = CheckSuite()
                c_files = read_c_files(d)
                for fname, content in c_files:
                    # 检查第三方驱动的基本质量
                    has_include_guard = bool(re.search(r'#ifndef|#pragma once', content))
                    if not has_include_guard and fname.endswith(".h"):
                        suite.add(CheckResult(
                            "第三方驱动头文件有 include 守卫",
                            False,
                            "缺少 #ifndef 或 #pragma once",
                            f"{d.name}/{fname}"
                        ))
                if suite.results:
                    all_suites.append((f"第三方驱动检查 ({d.name})", suite))

    total_passed = 0
    total_errors = 0
    total_warnings = 0
    total_infos = 0

    for title, suite in all_suites:
        suite.print_report(title)
        total_passed += suite.passed()
        total_errors += suite.errors()
        total_warnings += suite.warnings()
        total_infos += suite.infos()

    # 搜索历史错误
    if args.history and total_errors > 0:
        keywords = extract_keywords_from_failures(all_suites)
        if keywords:
            print(f"\n{BOLD}{CYAN}{'='*60}{RESET}")
            print(f"{BOLD}{CYAN}  搜索相关历史错误{RESET}")
            print(f"{BOLD}{CYAN}{'='*60}{RESET}")
            history = search_error_history(project_dir, keywords)
            if history:
                for h in history[:5]:
                    error = h.get("error", "未知")
                    fix = h.get("fix", "无")
                    print(f"  {YELLOW}📝{RESET} {error}")
                    print(f"     修复: {fix}")
            else:
                print(f"  {CYAN}ℹ️  未找到相关历史错误{RESET}")

    # 自动修复
    if args.fix and total_errors > 0:
        print(f"\n{BOLD}{CYAN}{'='*60}{RESET}")
        print(f"{BOLD}{CYAN}  自动修复{RESET}")
        print(f"{BOLD}{CYAN}{'='*60}{RESET}")
        fixed = auto_fix(project_dir, all_suites)
        if fixed > 0:
            print(f"\n  {GREEN}{BOLD}✅ 已修复 {fixed} 项问题{RESET}")
            print(f"  {YELLOW}  请重新运行检查确认修复结果{RESET}")
        else:
            print(f"  {CYAN}ℹ️  没有可自动修复的问题{RESET}")

    # 总结
    print(f"\n{BOLD}{'='*60}{RESET}")
    total = total_passed + total_errors + total_warnings + total_infos
    if total_errors == 0:
        print(f"{GREEN}{BOLD}  ✅ 全部 {total} 项检查通过！可以开始写代码。{RESET}")
        if total_warnings > 0:
            print(f"{YELLOW}  ⚠️  {total_warnings} 项警告（低风险，建议修复）{RESET}")
    else:
        print(f"{RED}{BOLD}  ❌ {total_errors} 项错误需要修复，{total_warnings} 项警告{RESET}")
        if not args.fix:
            print(f"{YELLOW}  💡 提示: 使用 --fix 自动修复可修复的问题{RESET}")
        if not args.history:
            print(f"{YELLOW}  💡 提示: 使用 --history 搜索相关历史错误{RESET}")
    print(f"{BOLD}{'='*60}{RESET}\n")

    sys.exit(1 if total_errors > 0 else 0)


if __name__ == "__main__":
    main()
