#!/usr/bin/env python
"""STM32 项目健康检查工具。

检查项目配置、依赖、编译环境等是否正常。

功能：
- 检查项目结构
- 检查依赖文件
- 检查编译环境
- 检查配置一致性

使用示例：
  python health_check.py --project .
  python health_check.py --project . --fix
"""

from __future__ import annotations

import argparse
import io
import os
import sys
from pathlib import Path
from typing import Any

# 编码处理
if sys.stdout and hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

# ======================== 检查项定义 ========================

REQUIRED_DIRS = [
    "Core/Inc",
    "Core/Src",
    "Board",
    "Drivers",
    "MDK-ARM"
]

REQUIRED_FILES = [
    "Core/Inc/main.h",
    "Core/Src/main.c",
    "Core/Inc/gpio.h",
    "Core/Src/gpio.c"
]

OPTIONAL_FILES = [
    "Core/Inc/FreeRTOSConfig.h",
    "Core/Inc/stm32f4xx_hal_conf.h",
    "Board/config.h"
]

# ======================== 检查函数 ========================

def check_project_structure(project_dir: str) -> list[dict[str, Any]]:
    """检查项目结构"""
    issues = []

    # 检查必需目录
    for dir_path in REQUIRED_DIRS:
        full_path = os.path.join(project_dir, dir_path)
        if not os.path.isdir(full_path):
            issues.append({
                "type": "missing_directory",
                "severity": "error",
                "message": f"缺少目录: {dir_path}",
                "fix": f"创建目录: {dir_path}"
            })

    # 检查必需文件
    for file_path in REQUIRED_FILES:
        full_path = os.path.join(project_dir, file_path)
        if not os.path.isfile(full_path):
            issues.append({
                "type": "missing_file",
                "severity": "error",
                "message": f"缺少文件: {file_path}",
                "fix": f"创建文件: {file_path}"
            })

    # 检查可选文件
    for file_path in OPTIONAL_FILES:
        full_path = os.path.join(project_dir, file_path)
        if not os.path.isfile(full_path):
            issues.append({
                "type": "missing_optional_file",
                "severity": "warning",
                "message": f"缺少可选文件: {file_path}",
                "fix": f"建议创建文件: {file_path}"
            })

    return issues

def check_keil_project(project_dir: str) -> list[dict[str, Any]]:
    """检查 Keil 工程文件"""
    issues = []

    # 查找 .uvprojx 文件
    uvprojx_files = list(Path(project_dir).glob("MDK-ARM/*.uvprojx"))
    if not uvprojx_files:
        issues.append({
            "type": "missing_keil_project",
            "severity": "error",
            "message": "未找到 Keil 工程文件 (.uvprojx)",
            "fix": "创建 Keil 工程文件"
        })
    else:
        # 检查工程文件是否存在
        for uvprojx in uvprojx_files:
            if not uvprojx.exists():
                issues.append({
                    "type": "missing_keil_project",
                    "severity": "error",
                    "message": f"Keil 工程文件不存在: {uvprojx.name}",
                    "fix": f"创建工程文件: {uvprojx.name}"
                })

    return issues

def check_hal_config(project_dir: str) -> list[dict[str, Any]]:
    """检查 HAL 配置"""
    issues = []

    hal_conf_path = os.path.join(project_dir, "Core", "Inc", "stm32f4xx_hal_conf.h")
    if os.path.isfile(hal_conf_path):
        with open(hal_conf_path, "r", encoding="utf-8", errors="replace") as f:
            content = f.read()

        # 检查必要的 HAL 模块
        required_modules = [
            "HAL_GPIO_MODULE_ENABLED",
            "HAL_RCC_MODULE_ENABLED",
            "HAL_TIM_MODULE_ENABLED",
            "HAL_UART_MODULE_ENABLED"
        ]

        for module in required_modules:
            if module not in content:
                issues.append({
                    "type": "missing_hal_module",
                    "severity": "warning",
                    "message": f"HAL 模块未启用: {module}",
                    "fix": f"在 stm32f4xx_hal_conf.h 中启用 {module}"
                })

    return issues

def check_freertos_config(project_dir: str) -> list[dict[str, Any]]:
    """检查 FreeRTOS 配置"""
    issues = []

    freertos_config_path = os.path.join(project_dir, "Core", "Inc", "FreeRTOSConfig.h")
    if os.path.isfile(freertos_config_path):
        with open(freertos_config_path, "r", encoding="utf-8", errors="replace") as f:
            content = f.read()

        # 检查必要的 FreeRTOS 配置
        required_configs = [
            "configUSE_PREEMPTION",
            "configMAX_PRIORITIES",
            "configTOTAL_HEAP_SIZE",
            "configCHECK_FOR_STACK_OVERFLOW"
        ]

        for config in required_configs:
            if config not in content:
                issues.append({
                    "type": "missing_freertos_config",
                    "severity": "warning",
                    "message": f"FreeRTOS 配置缺失: {config}",
                    "fix": f"在 FreeRTOSConfig.h 中添加 {config}"
                })

    return issues

def check_include_paths(project_dir: str) -> list[dict[str, Any]]:
    """检查 include 路径"""
    issues = []

    # 检查 .vscode/c_cpp_properties.json
    c_cpp_properties_path = os.path.join(project_dir, ".vscode", "c_cpp_properties.json")
    if os.path.isfile(c_cpp_properties_path):
        import json
        with open(c_cpp_properties_path, "r", encoding="utf-8") as f:
            try:
                config = json.load(f)
                include_paths = config.get("configurations", [{}])[0].get("includePath", [])

                # 检查必要的 include 路径
                required_paths = [
                    "${workspaceFolder}/Core/Inc",
                    "${workspaceFolder}/Drivers/STM32F4xx_HAL_Driver/Inc"
                ]

                for path in required_paths:
                    if path not in include_paths:
                        issues.append({
                            "type": "missing_include_path",
                            "severity": "warning",
                            "message": f"缺少 include 路径: {path}",
                            "fix": f"在 .vscode/c_cpp_properties.json 中添加 {path}"
                        })
            except json.JSONDecodeError:
                issues.append({
                    "type": "invalid_json",
                    "severity": "error",
                    "message": ".vscode/c_cpp_properties.json 格式错误",
                    "fix": "修复 JSON 格式"
                })

    return issues

def fix_issues(project_dir: str, issues: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """修复问题"""
    fixes = []

    for issue in issues:
        if issue["type"] == "missing_directory":
            dir_path = os.path.join(project_dir, issue["message"].split(": ")[1])
            os.makedirs(dir_path, exist_ok=True)
            fixes.append({
                "type": "create_directory",
                "description": f"创建目录: {issue['message'].split(': ')[1]}"
            })

        elif issue["type"] == "missing_file":
            file_path = issue["message"].split(": ")[1]
            full_path = os.path.join(project_dir, file_path)

            # 创建目录
            os.makedirs(os.path.dirname(full_path), exist_ok=True)

            # 创建空文件
            with open(full_path, "w", encoding="utf-8") as f:
                f.write(f"/* {os.path.basename(file_path)} - 自动生成 */\n")

            fixes.append({
                "type": "create_file",
                "description": f"创建文件: {file_path}"
            })

    return fixes

# ======================== CLI ========================

def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="STM32 项目健康检查工具",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  %(prog)s --project .                    # 检查项目
  %(prog)s --project . --fix              # 检查并修复
        """,
    )

    parser.add_argument("--project", default=".", help="项目目录")
    parser.add_argument("--fix", action="store_true", help="自动修复问题")
    parser.add_argument("--json", action="store_true", help="输出 JSON 格式")

    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()

    print(f"🔍 检查项目: {args.project}")
    print()

    # 执行检查
    all_issues = []
    all_issues.extend(check_project_structure(args.project))
    all_issues.extend(check_keil_project(args.project))
    all_issues.extend(check_hal_config(args.project))
    all_issues.extend(check_freertos_config(args.project))
    all_issues.extend(check_include_paths(args.project))

    # 统计问题
    errors = [i for i in all_issues if i["severity"] == "error"]
    warnings = [i for i in all_issues if i["severity"] == "warning"]

    print(f"📊 检查结果:")
    print(f"   错误: {len(errors)}")
    print(f"   警告: {len(warnings)}")
    print()

    # 显示问题
    if all_issues:
        print("📋 问题列表:")
        for i, issue in enumerate(all_issues, 1):
            severity_icon = "❌" if issue["severity"] == "error" else "⚠️"
            print(f"   {i}. {severity_icon} [{issue['type']}] {issue['message']}")
            print(f"      修复: {issue['fix']}")
        print()

    # 自动修复
    if args.fix and all_issues:
        print("🔧 开始自动修复...")
        fixes = fix_issues(args.project, all_issues)

        if fixes:
            print(f"\n✅ 完成 {len(fixes)} 项修复:")
            for fix in fixes:
                print(f"   - {fix['description']}")
        else:
            print("\n⚠️ 没有可自动修复的问题")

    # 总结
    if not all_issues:
        print("✅ 项目检查通过，未发现问题")
        return 0
    elif errors:
        print("❌ 项目检查失败，存在错误")
        return 1
    else:
        print("⚠️ 项目检查完成，存在警告")
        return 0


if __name__ == "__main__":
    sys.exit(main())
