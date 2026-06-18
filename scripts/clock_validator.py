#!/usr/bin/env python
"""STM32 时钟配置验证工具。

验证 .ioc 文件中的时钟配置是否正确。

功能：
- 验证 PLL 配置
- 验证时钟分频
- 验证外设时钟

使用示例：
  python clock_validator.py --ioc project.ioc
  python clock_validator.py --ioc project.ioc --json
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

# ======================== 时钟配置解析 ========================

def parse_clock_config(ioc_path: str) -> dict[str, Any]:
    """解析 .ioc 文件中的时钟配置"""
    result = {
        "hse": 0,
        "hsi": 0,
        "pll": {},
        "sysclk": 0,
        "hclk": 0,
        "apb1": 0,
        "apb2": 0,
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

                    # 解析时钟配置
                    if key == "RCC.HSE_VALUE":
                        result["hse"] = int(value)
                    elif key == "RCC.HSI_VALUE":
                        result["hsi"] = int(value)
                    elif key == "RCC.PLLM":
                        result["pll"]["pllm"] = int(value)
                    elif key == "RCC.PLLN":
                        result["pll"]["plln"] = int(value)
                    elif key == "RCC.PLLP":
                        result["pll"]["pllp"] = int(value)
                    elif key == "RCC.PLLQ":
                        result["pll"]["pllq"] = int(value)
                    elif key == "RCC.SYSCLKFreq_VALUE":
                        result["sysclk"] = int(value)
                    elif key == "RCC.HCLKFreq_Value":
                        result["hclk"] = int(value)
                    elif key == "RCC.APB1Freq_Value":
                        result["apb1"] = int(value)
                    elif key == "RCC.APB2Freq_Value":
                        result["apb2"] = int(value)

    except Exception as e:
        result["error"] = str(e)

    return result

# ======================== 时钟验证 ========================

def validate_pll_config(pll: dict[str, int], hse: int) -> list[dict[str, Any]]:
    """验证 PLL 配置"""
    issues = []

    if not pll:
        issues.append({
            "type": "missing_pll",
            "description": "PLL 配置缺失"
        })
        return issues

    # 检查 PLLM
    if "pllm" in pll:
        pllm = pll["pllm"]
        if pllm < 2 or pllm > 63:
            issues.append({
                "type": "invalid_pllm",
                "description": f"PLLM 值无效: {pllm} (应为 2-63)"
            })

    # 检查 PLLN
    if "plln" in pll:
        plln = pll["plln"]
        if plln < 50 or plln > 432:
            issues.append({
                "type": "invalid_plln",
                "description": f"PLLN 值无效: {plln} (应为 50-432)"
            })

    # 检查 PLLP
    if "pllp" in pll:
        pllp = pll["pllp"]
        if pllp not in [2, 4, 6, 8]:
            issues.append({
                "type": "invalid_pllp",
                "description": f"PLLP 值无效: {pllp} (应为 2, 4, 6, 8)"
            })

    # 检查 VCO 输入频率
    if "pllm" in pll and hse > 0:
        vco_input = hse / pll["pllm"]
        if vco_input < 1000000 or vco_input > 2000000:
            issues.append({
                "type": "invalid_vco_input",
                "description": f"VCO 输入频率无效: {vco_input/1e6:.1f} MHz (应为 1-2 MHz)"
            })

    return issues

def validate_clock_tree(config: dict[str, Any]) -> list[dict[str, Any]]:
    """验证时钟树配置"""
    issues = []

    # 检查 SYSCLK
    if config["sysclk"] > 0:
        if config["sysclk"] > 168000000:
            issues.append({
                "type": "excessive_sysclk",
                "description": f"SYSCLK 频率过高: {config['sysclk']/1e6:.1f} MHz (最大 168 MHz)"
            })

    # 检查 APB1
    if config["apb1"] > 0:
        if config["apb1"] > 42000000:
            issues.append({
                "type": "excessive_apb1",
                "description": f"APB1 频率过高: {config['apb1']/1e6:.1f} MHz (最大 42 MHz)"
            })

    # 检查 APB2
    if config["apb2"] > 0:
        if config["apb2"] > 84000000:
            issues.append({
                "type": "excessive_apb2",
                "description": f"APB2 频率过高: {config['apb2']/1e6:.1f} MHz (最大 84 MHz)"
            })

    return issues

# ======================== CLI ========================

def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="STM32 时钟配置验证工具",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  %(prog)s --ioc project.ioc                    # 验证时钟配置
  %(prog)s --ioc project.ioc --json             # JSON 格式输出
        """,
    )

    parser.add_argument("--ioc", required=True, help="IOC 文件路径")
    parser.add_argument("--json", action="store_true", help="输出 JSON 格式")

    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()

    print(f"🔍 验证时钟配置: {args.ioc}")
    print()

    # 解析时钟配置
    clock_config = parse_clock_config(args.ioc)
    if clock_config["error"]:
        print(f"❌ 错误: {clock_config['error']}")
        return 1

    # 验证 PLL 配置
    pll_issues = validate_pll_config(clock_config["pll"], clock_config["hse"])

    # 验证时钟树
    tree_issues = validate_clock_tree(clock_config)

    all_issues = pll_issues + tree_issues

    # 输出结果
    if args.json:
        result = {
            "config": clock_config,
            "issues": all_issues
        }
        print(json.dumps(result, indent=2, ensure_ascii=False))
    else:
        print(f"📊 时钟配置:")
        print(f"   HSE: {clock_config['hse']/1e6:.1f} MHz")
        print(f"   HSI: {clock_config['hsi']/1e6:.1f} MHz")
        print(f"   SYSCLK: {clock_config['sysclk']/1e6:.1f} MHz")
        print(f"   HCLK: {clock_config['hclk']/1e6:.1f} MHz")
        print(f"   APB1: {clock_config['apb1']/1e6:.1f} MHz")
        print(f"   APB2: {clock_config['apb2']/1e6:.1f} MHz")
        print()

        if clock_config["pll"]:
            print(f"📈 PLL 配置:")
            print(f"   PLLM: {clock_config['pll'].get('pllm', 'N/A')}")
            print(f"   PLLN: {clock_config['pll'].get('plln', 'N/A')}")
            print(f"   PLLP: {clock_config['pll'].get('pllp', 'N/A')}")
            print(f"   PLLQ: {clock_config['pll'].get('pllq', 'N/A')}")
            print()

        if all_issues:
            print(f"⚠️ 发现 {len(all_issues)} 个问题:")
            for i, issue in enumerate(all_issues, 1):
                print(f"   {i}. [{issue['type']}] {issue['description']}")
        else:
            print("✅ 时钟配置验证通过")

    return 0


if __name__ == "__main__":
    sys.exit(main())
