#!/usr/bin/env python
"""STM32 NVIC 配置检查工具。

检查 .ioc 文件中的 NVIC 中断配置。

功能：
- 检查中断优先级配置
- 检查中断使能状态
- 检查优先级分组

使用示例：
  python nvic_checker.py --ioc project.ioc
  python nvic_checker.py --ioc project.ioc --json
"""

from __future__ import annotations

import argparse
import io
import json
import os
import re
import sys
from pathlib import Path
from typing import Any

# 编码处理
if sys.stdout and hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

# ======================== NVIC 配置解析 ========================

def parse_nvic_config(ioc_path: str) -> dict[str, Any]:
    """解析 .ioc 文件中的 NVIC 配置"""
    result = {
        "interrupts": {},
        "priority_group": "",
        "error": None
    }

    if not os.path.exists(ioc_path):
        result["error"] = f"IOC file not found: {ioc_path}"
        return result

    try:
        with open(ioc_path, "r", encoding="utf-8", errors="replace") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#"):
                    continue

                if "=" in line:
                    key, value = line.split("=", 1)
                    key = key.strip()
                    value = value.strip()

                    # 解析 NVIC 配置
                    if key.startswith("NVIC.") and key.endswith("_IRQn"):
                        irq_name = key.replace("NVIC.", "")
                        # 解析配置值：enabled\:priority\:sub\:...
                        parts = value.replace("\\:", ":").split(":")
                        if len(parts) >= 2:
                            enabled = parts[0] == "true"
                            priority = int(parts[1]) if parts[1].isdigit() else 0
                            result["interrupts"][irq_name] = {
                                "enabled": enabled,
                                "priority": priority,
                                "raw": value
                            }

                    # 解析优先级分组
                    elif key == "NVIC.PriorityGroup":
                        result["priority_group"] = value

    except Exception as e:
        result["error"] = str(e)

    return result

# ======================== NVIC 验证 ========================

def validate_nvic_config(nvic_config: dict[str, Any]) -> list[dict[str, Any]]:
    """验证 NVIC 配置"""
    issues = []

    # 检查优先级分组
    if nvic_config["priority_group"]:
        group = nvic_config["priority_group"]
        if "PRIORITYGROUP_4" in group:
            # 4 位优先级，无子优先级
            pass
        elif "PRIORITYGROUP_3" in group:
            # 3 位优先级，1 位子优先级
            pass
        elif "PRIORITYGROUP_2" in group:
            # 2 位优先级，2 位子优先级
            pass
        elif "PRIORITYGROUP_1" in group:
            # 1 位优先级，3 位子优先级
            pass
        elif "PRIORITYGROUP_0" in group:
            # 无优先级，4 位子优先级
            pass
        else:
            issues.append({
                "type": "invalid_priority_group",
                "description": f"优先级分组无效: {group}"
            })

    # 检查中断优先级
    for irq_name, config in nvic_config["interrupts"].items():
        if config["enabled"]:
            # 检查优先级范围
            if config["priority"] > 15:
                issues.append({
                    "type": "invalid_priority",
                    "interrupt": irq_name,
                    "description": f"{irq_name} 优先级无效: {config['priority']} (应为 0-15)"
                })

    return issues

def analyze_interrupt_usage(nvic_config: dict[str, Any]) -> dict[str, Any]:
    """分析中断使用情况"""
    result = {
        "total": len(nvic_config["interrupts"]),
        "enabled": 0,
        "disabled": 0,
        "by_priority": {}
    }

    for irq_name, config in nvic_config["interrupts"].items():
        if config["enabled"]:
            result["enabled"] += 1

            # 按优先级统计
            priority = config["priority"]
            if priority not in result["by_priority"]:
                result["by_priority"][priority] = []
            result["by_priority"][priority].append(irq_name)
        else:
            result["disabled"] += 1

    return result

# ======================== CLI ========================

def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="STM32 NVIC 配置检查工具",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  %(prog)s --ioc project.ioc                    # 检查 NVIC 配置
  %(prog)s --ioc project.ioc --json             # JSON 格式输出
        """,
    )

    parser.add_argument("--ioc", required=True, help="IOC 文件路径")
    parser.add_argument("--json", action="store_true", help="输出 JSON 格式")

    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()

    print(f"🔍 检查 NVIC 配置: {args.ioc}")
    print()

    # 解析 NVIC 配置
    nvic_config = parse_nvic_config(args.ioc)
    if nvic_config["error"]:
        print(f"❌ 错误: {nvic_config['error']}")
        return 1

    # 验证配置
    issues = validate_nvic_config(nvic_config)

    # 分析使用情况
    usage = analyze_interrupt_usage(nvic_config)

    # 输出结果
    if args.json:
        result = {
            "config": nvic_config,
            "usage": usage,
            "issues": issues
        }
        print(json.dumps(result, indent=2, ensure_ascii=False))
    else:
        print(f"📊 NVIC 配置:")
        print(f"   优先级分组: {nvic_config['priority_group']}")
        print(f"   总中断数: {usage['total']}")
        print(f"   已启用: {usage['enabled']}")
        print(f"   已禁用: {usage['disabled']}")
        print()

        if usage["by_priority"]:
            print(f"📈 按优先级分布:")
            for priority in sorted(usage["by_priority"].keys()):
                irqs = usage["by_priority"][priority]
                print(f"   优先级 {priority}: {', '.join(irqs)}")
            print()

        if issues:
            print(f"⚠️ 发现 {len(issues)} 个问题:")
            for i, issue in enumerate(issues, 1):
                print(f"   {i}. [{issue['type']}] {issue['description']}")
        else:
            print("✅ NVIC 配置检查通过")

    return 0


if __name__ == "__main__":
    sys.exit(main())
