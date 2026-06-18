#!/usr/bin/env python
"""STM32 外设配置验证工具。

验证 .ioc 文件中的外设配置是否正确。

功能：
- 验证 UART 配置
- 验证 SPI 配置
- 验证 I2C 配置
- 验证定时器配置

使用示例：
  python peripheral_validator.py --ioc project.ioc
  python peripheral_validator.py --ioc project.ioc --json
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

# ======================== 外设配置解析 ========================

def parse_peripheral_config(ioc_path: str) -> dict[str, Any]:
    """解析 .ioc 文件中的外设配置"""
    result = {
        "usart": {},
        "spi": {},
        "i2c": {},
        "tim": {},
        "adc": {},
        "dac": {},
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

                    # 解析 UART 配置
                    if key.startswith("USART") and "." in key:
                        parts = key.split(".", 1)
                        if len(parts) == 2:
                            usart_name = parts[0]
                            param = parts[1]
                            if usart_name not in result["usart"]:
                                result["usart"][usart_name] = {}
                            result["usart"][usart_name][param] = value

                    # 解析 SPI 配置
                    elif key.startswith("SPI") and "." in key:
                        parts = key.split(".", 1)
                        if len(parts) == 2:
                            spi_name = parts[0]
                            param = parts[1]
                            if spi_name not in result["spi"]:
                                result["spi"][spi_name] = {}
                            result["spi"][spi_name][param] = value

                    # 解析 I2C 配置
                    elif key.startswith("I2C") and "." in key:
                        parts = key.split(".", 1)
                        if len(parts) == 2:
                            i2c_name = parts[0]
                            param = parts[1]
                            if i2c_name not in result["i2c"]:
                                result["i2c"][i2c_name] = {}
                            result["i2c"][i2c_name][param] = value

                    # 解析定时器配置
                    elif key.startswith("TIM") and "." in key:
                        parts = key.split(".", 1)
                        if len(parts) == 2:
                            tim_name = parts[0]
                            param = parts[1]
                            if tim_name not in result["tim"]:
                                result["tim"][tim_name] = {}
                            result["tim"][tim_name][param] = value

                    # 解析 ADC 配置
                    elif key.startswith("ADC") and "." in key:
                        parts = key.split(".", 1)
                        if len(parts) == 2:
                            adc_name = parts[0]
                            param = parts[1]
                            if adc_name not in result["adc"]:
                                result["adc"][adc_name] = {}
                            result["adc"][adc_name][param] = value

                    # 解析 DAC 配置
                    elif key.startswith("DAC") and "." in key:
                        parts = key.split(".", 1)
                        if len(parts) == 2:
                            dac_name = parts[0]
                            param = parts[1]
                            if dac_name not in result["dac"]:
                                result["dac"][dac_name] = {}
                            result["dac"][dac_name][param] = value

    except Exception as e:
        result["error"] = str(e)

    return result

# ======================== 外设验证 ========================

def validate_uart_config(uart_config: dict[str, Any]) -> list[dict[str, Any]]:
    """验证 UART 配置"""
    issues = []

    for uart_name, config in uart_config.items():
        # 检查波特率
        if "BaudRate" in config:
            try:
                baudrate = int(config["BaudRate"])
                if baudrate < 1200 or baudrate > 115200:
                    issues.append({
                        "type": "invalid_baudrate",
                        "peripheral": uart_name,
                        "description": f"{uart_name} 波特率异常: {baudrate}"
                    })
            except ValueError:
                issues.append({
                    "type": "invalid_baudrate",
                    "peripheral": uart_name,
                    "description": f"{uart_name} 波特率格式错误: {config['BaudRate']}"
                })

    return issues

def validate_spi_config(spi_config: dict[str, Any]) -> list[dict[str, Any]]:
    """验证 SPI 配置"""
    issues = []

    for spi_name, config in spi_config.items():
        # 检查数据大小
        if "DataSize" in config:
            if config["DataSize"] not in ["SPI_DATASIZE_8BIT", "SPI_DATASIZE_16BIT"]:
                issues.append({
                    "type": "invalid_datasize",
                    "peripheral": spi_name,
                    "description": f"{spi_name} 数据大小无效: {config['DataSize']}"
                })

    return issues

def validate_i2c_config(i2c_config: dict[str, Any]) -> list[dict[str, Any]]:
    """验证 I2C 配置"""
    issues = []

    for i2c_name, config in i2c_config.items():
        # 检查速度
        if "Speed" in config:
            try:
                speed = int(config["Speed"])
                if speed < 100000 or speed > 400000:
                    issues.append({
                        "type": "invalid_speed",
                        "peripheral": i2c_name,
                        "description": f"{i2c_name} 速度异常: {speed} Hz"
                    })
            except ValueError:
                issues.append({
                    "type": "invalid_speed",
                    "peripheral": i2c_name,
                    "description": f"{i2c_name} 速度格式错误: {config['Speed']}"
                })

    return issues

def validate_tim_config(tim_config: dict[str, Any]) -> list[dict[str, Any]]:
    """验证定时器配置"""
    issues = []

    for tim_name, config in tim_config.items():
        # 检查预分频
        if "Prescaler" in config:
            try:
                prescaler = int(config["Prescaler"].replace("-1", ""))
                if prescaler < 1 or prescaler > 65536:
                    issues.append({
                        "type": "invalid_prescaler",
                        "peripheral": tim_name,
                        "description": f"{tim_name} 预分频无效: {prescaler}"
                    })
            except ValueError:
                issues.append({
                    "type": "invalid_prescaler",
                    "peripheral": tim_name,
                    "description": f"{tim_name} 预分频格式错误: {config['Prescaler']}"
                })

        # 检查周期
        if "Period" in config:
            try:
                period = int(config["Period"].replace("-1", ""))
                if period < 1 or period > 65536:
                    issues.append({
                        "type": "invalid_period",
                        "peripheral": tim_name,
                        "description": f"{tim_name} 周期无效: {period}"
                    })
            except ValueError:
                issues.append({
                    "type": "invalid_period",
                    "peripheral": tim_name,
                    "description": f"{tim_name} 周期格式错误: {config['Period']}"
                })

    return issues

# ======================== CLI ========================

def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="STM32 外设配置验证工具",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  %(prog)s --ioc project.ioc                    # 验证外设配置
  %(prog)s --ioc project.ioc --json             # JSON 格式输出
        """,
    )

    parser.add_argument("--ioc", required=True, help="IOC 文件路径")
    parser.add_argument("--json", action="store_true", help="输出 JSON 格式")

    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()

    print(f"🔍 验证外设配置: {args.ioc}")
    print()

    # 解析外设配置
    peripheral_config = parse_peripheral_config(args.ioc)
    if peripheral_config["error"]:
        print(f"❌ 错误: {peripheral_config['error']}")
        return 1

    # 验证配置
    uart_issues = validate_uart_config(peripheral_config["usart"])
    spi_issues = validate_spi_config(peripheral_config["spi"])
    i2c_issues = validate_i2c_config(peripheral_config["i2c"])
    tim_issues = validate_tim_config(peripheral_config["tim"])

    all_issues = uart_issues + spi_issues + i2c_issues + tim_issues

    # 输出结果
    if args.json:
        result = {
            "config": peripheral_config,
            "issues": all_issues
        }
        print(json.dumps(result, indent=2, ensure_ascii=False))
    else:
        print(f"📊 外设配置:")
        print(f"   UART: {len(peripheral_config['usart'])} 个")
        print(f"   SPI: {len(peripheral_config['spi'])} 个")
        print(f"   I2C: {len(peripheral_config['i2c'])} 个")
        print(f"   TIM: {len(peripheral_config['tim'])} 个")
        print(f"   ADC: {len(peripheral_config['adc'])} 个")
        print(f"   DAC: {len(peripheral_config['dac'])} 个")
        print()

        if all_issues:
            print(f"⚠️ 发现 {len(all_issues)} 个问题:")
            for i, issue in enumerate(all_issues, 1):
                print(f"   {i}. [{issue['type']}] {issue['description']}")
        else:
            print("✅ 外设配置验证通过")

    return 0


if __name__ == "__main__":
    sys.exit(main())
