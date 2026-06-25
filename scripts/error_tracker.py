#!/usr/bin/env python
"""STM32 错误追踪工具 — 记录和查询错误修复历史。

功能：
  - 记录错误和修复方法
  - 查询历史错误和修复建议
  - 自动匹配相似错误
  - 生成错误模式报告

用法:
  # 记录错误修复
  python error_tracker.py --record --error "undefined reference to 'HAL_GPIO_Init'" --fix "添加 #include 'stm32f4xx_hal_gpio.h'" --file main.c

  # 查询错误
  python error_tracker.py --search "undefined reference"

  # 列出所有记录
  python error_tracker.py --list

  # 生成报告
  python error_tracker.py --report

  # 从工作流结果自动记录
  python error_tracker.py --workflow workflow_result.json --auto-record

安全约束:
  - 所有记录保存在本地 JSON 文件
  - 不自动修改源代码
  - 只提供建议，不强制执行
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime
from difflib import SequenceMatcher
from pathlib import Path

# 使用共享模块
try:
    from shared import setup_encoding, read_json_file, write_json_file
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

    def write_json_file(file_path, data):
        try:
            Path(file_path).write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
            return True
        except:
            return False


# === 常量 ===

# 默认数据库文件
DEFAULT_DB_FILE = Path(__file__).parent.parent / "data" / "error_history.json"

# 错误类型分类
ERROR_CATEGORIES = {
    "compile": {
        "patterns": [
            r"undefined reference to",
            r"multiple definition of",
            r"undeclared identifier",
            r"'.*' file not found",
            r"unknown type name",
            r"expected.*before",
            r"implicit declaration of function",
            r"redefinition of",
            r"conflicting types",
            r"lvalue required",
            r"syntax error",
            r"stray.*in program",
            r"expected.*before.*token",
        ],
        "name": "编译错误",
        "priority": 1,
        "cubemx_related": False,
    },
    "link": {
        "patterns": [
            r"region.*overflowed by",
            r"cannot find -l",
            r"ld returned.*exit status",
            r"undefined symbol",
            r"multiple definition",
            r"undefined reference to",
            r"cannot open linker script",
            r"no such file or directory",
        ],
        "name": "链接错误",
        "priority": 2,
        "cubemx_related": False,
    },
    "runtime": {
        "patterns": [
            r"HardFault",
            r"stack overflow",
            r"heap overflow",
            r"null pointer",
            r"bus error",
            r"data abort",
            r"prefetch abort",
            r"watchdog.*reset",
            r"memory.*fault",
            r"usage.*fault",
        ],
        "name": "运行时错误",
        "priority": 3,
        "cubemx_related": False,
    },
    "config": {
        "patterns": [
            r"PLL configuration error",
            r"clock.*not.*valid",
            r"pin.*already.*configured",
            r"interrupt.*priority",
            r"GPIO.*conflict",
            r"peripheral.*not.*enabled",
            r"DMA.*not.*configured",
            r"NVIC.*priority.*conflict",
            r"clock.*source.*not.*selected",
        ],
        "name": "配置错误",
        "priority": 4,
        "cubemx_related": True,
    },
    "cubemx": {
        "patterns": [
            r"MX_.*_Init.*error",
            r"HAL_.*_Init.*failed",
            r"HAL_.*_Error",
            r"HAL_TIMEOUT",
            r"HAL_BUSY",
            r"HAL_ERROR",
        ],
        "name": "CubeMX/HAL 错误",
        "priority": 4,
        "cubemx_related": True,
    },
    "serial": {
        "patterns": [
            r"serial.*timeout",
            r"baud.*rate.*mismatch",
            r"frame.*error",
            r"parity.*error",
            r"overrun.*error",
            r"noise.*error",
        ],
        "name": "串口错误",
        "priority": 5,
        "cubemx_related": True,
    },
    "i2c": {
        "patterns": [
            r"I2C.*NACK",
            r"I2C.*timeout",
            r"I2C.*bus.*error",
            r"I2C.* arbitration.*lost",
        ],
        "name": "I2C 错误",
        "priority": 5,
        "cubemx_related": True,
    },
    "spi": {
        "patterns": [
            r"SPI.*overrun",
            r"SPI.*underrun",
            r"SPI.*mode.*fault",
            r"SPI.*CRC.*error",
        ],
        "name": "SPI 错误",
        "priority": 5,
        "cubemx_related": True,
    },
    "adc": {
        "patterns": [
            r"ADC.*overrun",
            r"ADC.*underrun",
            r"ADC.*watchdog",
        ],
        "name": "ADC 错误",
        "priority": 5,
        "cubemx_related": True,
    },
}


# === 工具函数 ===

def load_database(db_file: str = None) -> dict:
    """加载错误历史数据库。"""
    db_path = Path(db_file) if db_file else DEFAULT_DB_FILE

    if db_path.exists():
        data = read_json_file(str(db_path))
        if data:
            return data

    return {
        "version": "1.0",
        "records": [],
        "patterns": {},
        "stats": {
            "total_records": 0,
            "total_fixed": 0,
            "last_updated": None,
        },
    }


def save_database(db: dict, db_file: str = None) -> bool:
    """保存错误历史数据库。"""
    db_path = Path(db_file) if db_file else DEFAULT_DB_FILE

    # 确保目录存在
    db_path.parent.mkdir(parents=True, exist_ok=True)

    # 更新统计信息
    db["stats"]["total_records"] = len(db["records"])
    db["stats"]["total_fixed"] = sum(1 for r in db["records"] if r.get("fixed"))
    db["stats"]["last_updated"] = datetime.now().isoformat()

    return write_json_file(str(db_path), db)


def categorize_error(error_msg: str) -> str:
    """根据错误信息分类错误类型。"""
    for category, info in ERROR_CATEGORIES.items():
        for pattern in info["patterns"]:
            if re.search(pattern, error_msg, re.IGNORECASE):
                return category
    return "other"


def is_cubemx_related(error_msg: str) -> bool:
    """检查错误是否与 CubeMX 配置相关。"""
    for category, info in ERROR_CATEGORIES.items():
        if info.get("cubemx_related"):
            for pattern in info["patterns"]:
                if re.search(pattern, error_msg, re.IGNORECASE):
                    return True
    return False


def is_clock_related(error_msg: str) -> bool:
    """检查错误是否与时钟配置相关。

    ⚠️ 时钟配置绝对不能修改！修改时钟配置会导致系统死机、锁死！
    """
    clock_keywords = [
        "PLL", "HSE", "HSI", "LSE", "LSI", "SYSCLK", "AHB", "APB",
        "clock", "RCC", "frequency", "oscillator", "crystal",
        "SystemClock_Config", "Clock Configuration",
    ]
    return any(keyword.lower() in error_msg.lower() for keyword in clock_keywords)


def get_clock_warning() -> str:
    """获取时钟配置警告信息。"""
    return """
⚠️ 警告：时钟配置相关问题！

时钟配置绝对不能在代码中修改！修改时钟配置会导致：
- 系统死机
- 芯片锁死
- 无法调试

正确做法：
1. 在 CubeMX 中修改时钟配置
2. 检查 HSE/HSI 配置
3. 检查 PLL 配置
4. 检查 SYSCLK 源
5. 重新生成代码

不要在代码中修改任何时钟相关配置！
"""


def get_brick_recovery_guide() -> str:
    """获取死机/锁机恢复指南。"""
    return """
⚠️ 芯片死机/锁机恢复指南

如果芯片死机或锁死，按以下步骤恢复：

步骤 1：检查读保护状态
  STM32_Programmer_CLI.exe -c port=SWD mode=UR

步骤 2：如果有读保护(RDP)，需要先解除
  ⚠️ 解除读保护会擦除整个芯片！
  STM32_Programmer_CLI.exe -c port=SWD mode=UR -ob RDP=0

步骤 3：如果没有读保护，直接擦除
  STM32_Programmer_CLI.exe -c port=SWD mode=UR -e all

步骤 4：重新烧录
  STM32_Programmer_CLI.exe -c port=SWD mode=UR -w project.axf -v -rst

恢复顺序：
1. 先检查是否有读保护（RDP）
2. 如果有读保护，先解除（会擦除芯片）
3. 如果没有读保护，直接擦除
4. 重新烧录固件

注意：
- 解除读保护会擦除整个芯片（包括 Flash 和 Option Bytes）
- 如果芯片完全锁死，可能需要使用 BOOT0 引脚进入系统引导模式
- 某些情况下可能需要使用 ST-LINK 的 NRST 引脚手动复位
"""


# 常见错误模式数据库
COMMON_ERROR_PATTERNS = [
    {
        "error": "undefined reference to 'HAL_GPIO_Init'",
        "category": "link",
        "fix": "在 stm32f4xx_hal_conf.h 中启用 HAL_GPIO_MODULE_ENABLED",
        "cubemx_fix": "在 CubeMX 中启用 GPIO 外设",
        "is_cubemx_related": True,
    },
    {
        "error": "undefined reference to 'HAL_UART_Init'",
        "category": "link",
        "fix": "在 stm32f4xx_hal_conf.h 中启用 HAL_UART_MODULE_ENABLED",
        "cubemx_fix": "在 CubeMX 中启用 USART 外设",
        "is_cubemx_related": True,
    },
    {
        "error": "undefined reference to 'HAL_I2C_Init'",
        "category": "link",
        "fix": "在 stm32f4xx_hal_conf.h 中启用 HAL_I2C_MODULE_ENABLED",
        "cubemx_fix": "在 CubeMX 中启用 I2C 外设",
        "is_cubemx_related": True,
    },
    {
        "error": "undefined reference to 'HAL_SPI_Init'",
        "category": "link",
        "fix": "在 stm32f4xx_hal_conf.h 中启用 HAL_SPI_MODULE_ENABLED",
        "cubemx_fix": "在 CubeMX 中启用 SPI 外设",
        "is_cubemx_related": True,
    },
    {
        "error": "undefined reference to 'HAL_TIM_Init'",
        "category": "link",
        "fix": "在 stm32f4xx_hal_conf.h 中启用 HAL_TIM_MODULE_ENABLED",
        "cubemx_fix": "在 CubeMX 中启用 TIM 外设",
        "is_cubemx_related": True,
    },
    {
        "error": "undefined reference to 'HAL_ADC_Init'",
        "category": "link",
        "fix": "在 stm32f4xx_hal_conf.h 中启用 HAL_ADC_MODULE_ENABLED",
        "cubemx_fix": "在 CubeMX 中启用 ADC 外设",
        "is_cubemx_related": True,
    },
    {
        "error": "undefined reference to 'HAL_DAC_Init'",
        "category": "link",
        "fix": "在 stm32f4xx_hal_conf.h 中启用 HAL_DAC_MODULE_ENABLED",
        "cubemx_fix": "在 CubeMX 中启用 DAC 外设",
        "is_cubemx_related": True,
    },
    {
        "error": "region FLASH overflowed by",
        "category": "link",
        "fix": "优化代码大小或更换更大 Flash 的芯片",
        "cubemx_fix": None,
        "is_cubemx_related": False,
    },
    {
        "error": "region RAM overflowed by",
        "category": "link",
        "fix": "减少全局变量或优化数据结构",
        "cubemx_fix": None,
        "is_cubemx_related": False,
    },
    {
        "error": "HardFault",
        "category": "runtime",
        "fix": "检查中断优先级、栈溢出、空指针访问",
        "cubemx_fix": "检查 NVIC 配置和中断优先级",
        "is_cubemx_related": True,
    },
    {
        "error": "stack overflow",
        "category": "runtime",
        "fix": "增加栈大小或减少局部变量",
        "cubemx_fix": "在 CubeMX 中增加栈大小",
        "is_cubemx_related": True,
    },
    {
        "error": "HAL_TIMEOUT",
        "category": "cubemx",
        "fix": "检查外设配置和时钟配置",
        "cubemx_fix": "在 CubeMX 中检查外设配置和时钟配置",
        "is_cubemx_related": True,
    },
    {
        "error": "HAL_BUSY",
        "category": "cubemx",
        "fix": "等待外设空闲或检查外设状态",
        "cubemx_fix": "在 CubeMX 中检查外设配置",
        "is_cubemx_related": True,
    },
    {
        "error": "I2C NACK",
        "category": "i2c",
        "fix": "检查 I2C 地址和上拉电阻",
        "cubemx_fix": "在 CubeMX 中检查 I2C 配置",
        "is_cubemx_related": True,
    },
    {
        "error": "SPI overrun",
        "category": "spi",
        "fix": "检查 SPI 时钟配置和数据速率",
        "cubemx_fix": "在 CubeMX 中检查 SPI 配置",
        "is_cubemx_related": True,
    },
    # FreeRTOS 相关错误
    {
        "error": "FreeRTOSConfig.h file not found",
        "category": "compile",
        "fix": "创建 FreeRTOSConfig.h 文件或添加 include 路径",
        "cubemx_fix": "在 CubeMX 中启用 FreeRTOS 中间件",
        "is_cubemx_related": True,
    },
    {
        "error": "configTOTAL_HEAP_SIZE",
        "category": "config",
        "fix": "增加 configTOTAL_HEAP_SIZE 或优化内存使用",
        "cubemx_fix": "在 CubeMX 中调整 FreeRTOS 堆大小",
        "is_cubemx_related": True,
    },
    # 启动文件相关错误
    {
        "error": "startup_stm32",
        "category": "link",
        "fix": "检查启动文件是否与芯片型号匹配",
        "cubemx_fix": "在 CubeMX 中重新生成代码",
        "is_cubemx_related": True,
    },
    # 时钟配置错误
    {
        "error": "SystemClock_Config",
        "category": "config",
        "fix": "检查时钟配置，确保 HSE/HSI 配置正确",
        "cubemx_fix": "在 CubeMX 中检查 Clock Configuration",
        "is_cubemx_related": True,
    },
    # 中断相关错误
    {
        "error": "NVIC priority",
        "category": "config",
        "fix": "检查中断优先级配置，确保不冲突",
        "cubemx_fix": "在 CubeMX 中检查 NVIC 配置",
        "is_cubemx_related": True,
    },
    # DMA 相关错误
    {
        "error": "DMA not configured",
        "category": "config",
        "fix": "在 CubeMX 中配置 DMA 通道",
        "cubemx_fix": "在 CubeMX 中启用 DMA 并配置通道",
        "is_cubemx_related": True,
    },
    # GPIO 相关错误
    {
        "error": "GPIO pin conflict",
        "category": "config",
        "fix": "检查引脚配置，避免冲突",
        "cubemx_fix": "在 CubeMX 中检查引脚配置",
        "is_cubemx_related": True,
    },
    # HAL 回调函数错误
    {
        "error": "HAL_xxx_Callback",
        "category": "link",
        "fix": "实现 HAL 回调函数",
        "cubemx_fix": "在 CubeMX 中启用对应的外设中断",
        "is_cubemx_related": True,
    },
    # 编译器相关错误
    {
        "error": "arm-none-eabi-gcc: error",
        "category": "compile",
        "fix": "检查编译器路径和版本",
        "cubemx_fix": None,
        "is_cubemx_related": False,
    },
    # 链接脚本相关错误
    {
        "error": "cannot open linker script",
        "category": "link",
        "fix": "检查链接脚本路径",
        "cubemx_fix": "在 CubeMX 中重新生成代码",
        "is_cubemx_related": True,
    },
    # ADC 相关错误
    {
        "error": "ADC overrun",
        "category": "adc",
        "fix": "检查 ADC 采样率和 DMA 配置",
        "cubemx_fix": "在 CubeMX 中检查 ADC 配置",
        "is_cubemx_related": True,
    },
    # DAC 相关错误
    {
        "error": "DAC not working",
        "category": "dac",
        "fix": "检查 DAC 配置和输出引脚",
        "cubemx_fix": "在 CubeMX 中检查 DAC 配置",
        "is_cubemx_related": True,
    },
    # PWM 相关错误
    {
        "error": "PWM not output",
        "category": "tim",
        "fix": "检查定时器配置和 PWM 通道",
        "cubemx_fix": "在 CubeMX 中检查 TIM 配置",
        "is_cubemx_related": True,
    },
    # 看门狗相关错误
    {
        "error": "watchdog reset",
        "category": "runtime",
        "fix": "检查看门狗配置和喂狗时机",
        "cubemx_fix": "在 CubeMX 中检查 IWDG/WWDG 配置",
        "is_cubemx_related": True,
    },
    # USB 相关错误
    {
        "error": "USB not enumerated",
        "category": "usb",
        "fix": "检查 USB 配置和描述符",
        "cubemx_fix": "在 CubeMX 中检查 USB 配置",
        "is_cubemx_related": True,
    },
    # 以太网相关错误
    {
        "error": "ETH not working",
        "category": "eth",
        "fix": "检查以太网配置和 PHY 芯片",
        "cubemx_fix": "在 CubeMX 中检查 ETH 配置",
        "is_cubemx_related": True,
    },
    # 编译器路径错误
    {
        "error": "UV4.exe not found",
        "category": "compile",
        "fix": "检查 Keil MDK-ARM 安装路径",
        "cubemx_fix": None,
        "is_cubemx_related": False,
    },
    # 启动文件错误
    {
        "error": "startup_stm32f1xx.s not found",
        "category": "link",
        "fix": "检查启动文件是否与芯片型号匹配",
        "cubemx_fix": "在 CubeMX 中重新生成代码",
        "is_cubemx_related": True,
    },
    # 链接脚本错误
    {
        "error": "STM32F103C8Tx_FLASH.ld not found",
        "category": "link",
        "fix": "检查链接脚本路径",
        "cubemx_fix": "在 CubeMX 中重新生成代码",
        "is_cubemx_related": True,
    },
    # 头文件路径错误
    {
        "error": "stm32f1xx_hal.h: No such file or directory",
        "category": "compile",
        "fix": "检查 HAL 库路径和 include 路径",
        "cubemx_fix": "在 CubeMX 中重新生成代码",
        "is_cubemx_related": True,
    },
    # 中断处理函数错误
    {
        "error": "undefined reference to 'SysTick_Handler'",
        "category": "link",
        "fix": "实现 SysTick_Handler 中断处理函数",
        "cubemx_fix": "在 CubeMX 中启用 SysTick 中断",
        "is_cubemx_related": True,
    },
    # 内存分配错误
    {
        "error": "malloc failed",
        "category": "runtime",
        "fix": "增加堆大小或减少动态内存分配",
        "cubemx_fix": "在 CubeMX 中增加堆大小",
        "is_cubemx_related": True,
    },
    # 栈溢出错误
    {
        "error": "Stack overflow in task",
        "category": "runtime",
        "fix": "增加任务栈大小或减少局部变量",
        "cubemx_fix": "在 CubeMX 中增加 FreeRTOS 任务栈大小",
        "is_cubemx_related": True,
    },
]


def similarity(a: str, b: str) -> float:
    """计算两个字符串的相似度。"""
    return SequenceMatcher(None, a.lower(), b.lower()).ratio()


def find_similar_errors(db: dict, error_msg: str, threshold: float = 0.6) -> list[dict]:
    """查找相似的历史错误。"""
    similar = []

    for record in db["records"]:
        sim = similarity(error_msg, record.get("error", ""))
        if sim >= threshold:
            similar.append({
                "record": record,
                "similarity": sim,
            })

    # 按相似度排序
    similar.sort(key=lambda x: x["similarity"], reverse=True)
    return similar[:5]  # 返回前 5 个


# === 核心功能 ===

def record_error(error: str, fix: str = None, file: str = None,
                 line: int = None, category: str = None,
                 notes: str = None, db_file: str = None) -> dict:
    """记录错误和修复方法。"""
    db = load_database(db_file)

    # 自动分类
    if not category:
        category = categorize_error(error)

    # 创建记录
    record = {
        "id": len(db["records"]) + 1,
        "timestamp": datetime.now().isoformat(),
        "error": error,
        "fix": fix,
        "file": file,
        "line": line,
        "category": category,
        "fixed": fix is not None,
        "notes": notes,
        "tags": [],
    }

    # 提取标签
    if "undefined reference" in error.lower():
        record["tags"].append("linker")
    if "file not found" in error.lower():
        record["tags"].append("missing-file")
    if "HardFault" in error:
        record["tags"].append("hardfault")

    db["records"].append(record)

    # 更新模式统计
    if category not in db["patterns"]:
        db["patterns"][category] = {
            "count": 0,
            "fixed_count": 0,
            "common_fixes": [],
        }
    db["patterns"][category]["count"] += 1
    if fix:
        db["patterns"][category]["fixed_count"] += 1

    save_database(db, db_file)
    return record


def search_errors(query: str, db_file: str = None, limit: int = 10) -> list[dict]:
    """搜索错误历史。"""
    db = load_database(db_file)
    results = []

    for record in db["records"]:
        # 搜索错误信息
        if query.lower() in record.get("error", "").lower():
            results.append(record)
            continue

        # 搜索修复方法
        if record.get("fix") and query.lower() in record["fix"].lower():
            results.append(record)
            continue

        # 搜索文件名
        if record.get("file") and query.lower() in record["file"].lower():
            results.append(record)
            continue

        # 搜索标签
        if any(query.lower() in tag.lower() for tag in record.get("tags", [])):
            results.append(record)

    return results[:limit]


def get_fix_suggestions(error: str, db_file: str = None) -> list[dict]:
    """获取修复建议。

    注意：如果错误与 CubeMX 配置相关，建议用户在 CubeMX 中修改，而不是在代码中绕过。
    """
    db = load_database(db_file)

    # 查找相似错误
    similar = find_similar_errors(db, error)

    suggestions = []
    for item in similar:
        record = item["record"]
        if record.get("fix"):
            suggestions.append({
                "error": record["error"],
                "fix": record["fix"],
                "file": record.get("file"),
                "similarity": item["similarity"],
                "timestamp": record.get("timestamp"),
            })

    # 从常见错误模式数据库中查找
    for pattern in COMMON_ERROR_PATTERNS:
        sim = similarity(error, pattern["error"])
        if sim >= 0.6:
            suggestion = {
                "error": pattern["error"],
                "fix": pattern["fix"],
                "file": None,
                "similarity": sim,
                "timestamp": None,
                "category": pattern["category"],
            }
            # 添加 CubeMX 修复建议
            if pattern.get("is_cubemx_related") and pattern.get("cubemx_fix"):
                suggestion["cubemx_fix"] = pattern["cubemx_fix"]
                suggestion["is_cubemx_related"] = True
            suggestions.append(suggestion)

    # 检查是否与 CubeMX 配置相关
    if is_cubemx_related(error):
        suggestions.append({
            "error": error,
            "fix": "如果是配置错误，请在 CubeMX 中修改，不要在代码中绕过",
            "file": None,
            "similarity": 0.5,
            "timestamp": None,
            "is_cubemx_suggestion": True,
            "cubemx_fix": "在 CubeMX 中检查并修改相关配置",
        })

    # 检查是否与时钟配置相关（绝对不能修改！）
    if is_clock_related(error):
        suggestions.insert(0, {
            "error": error,
            "fix": "⚠️ 时钟配置绝对不能在代码中修改！修改会导致系统死机、锁死！",
            "file": None,
            "similarity": 1.0,
            "timestamp": None,
            "is_clock_warning": True,
            "clock_warning": get_clock_warning(),
            "cubemx_fix": "在 CubeMX 的 Clock Configuration 中检查并修改",
        })

    # 按相似度排序
    suggestions.sort(key=lambda x: x.get("similarity", 0), reverse=True)

    return suggestions[:10]  # 返回前 10 个建议


def generate_report(db_file: str = None) -> dict:
    """生成错误统计报告。"""
    db = load_database(db_file)

    report = {
        "timestamp": datetime.now().isoformat(),
        "summary": {
            "total_records": db["stats"]["total_records"],
            "total_fixed": db["stats"]["total_fixed"],
            "fix_rate": 0,
            "last_updated": db["stats"]["last_updated"],
        },
        "by_category": {},
        "recent_errors": [],
        "common_fixes": [],
    }

    # 计算修复率
    if report["summary"]["total_records"] > 0:
        report["summary"]["fix_rate"] = round(
            report["summary"]["total_fixed"] / report["summary"]["total_records"] * 100, 1
        )

    # 按分类统计
    for category, info in db.get("patterns", {}).items():
        report["by_category"][category] = {
            "name": ERROR_CATEGORIES.get(category, {}).get("name", category),
            "count": info["count"],
            "fixed_count": info["fixed_count"],
            "fix_rate": round(info["fixed_count"] / info["count"] * 100, 1) if info["count"] > 0 else 0,
        }

    # 最近错误
    recent = sorted(db["records"], key=lambda x: x.get("timestamp", ""), reverse=True)[:10]
    report["recent_errors"] = [{
        "error": r["error"][:80],
        "fixed": r.get("fixed", False),
        "timestamp": r.get("timestamp"),
    } for r in recent]

    # 常见修复方法
    fix_counts = {}
    for record in db["records"]:
        if record.get("fix"):
            fix = record["fix"][:100]
            fix_counts[fix] = fix_counts.get(fix, 0) + 1
    report["common_fixes"] = sorted(
        [{"fix": f, "count": c} for f, c in fix_counts.items()],
        key=lambda x: x["count"],
        reverse=True
    )[:10]

    # 错误趋势分析
    report["trends"] = analyze_error_trends(db)

    return report


def analyze_error_trends(db: dict) -> dict:
    """分析错误趋势。"""
    trends = {
        "by_date": {},
        "by_category": {},
        "fix_rate_trend": [],
    }

    # 按日期统计
    for record in db["records"]:
        date = record.get("timestamp", "")[:10]  # YYYY-MM-DD
        if date:
            if date not in trends["by_date"]:
                trends["by_date"][date] = {"total": 0, "fixed": 0}
            trends["by_date"][date]["total"] += 1
            if record.get("fixed"):
                trends["by_date"][date]["fixed"] += 1

    # 按分类趋势
    for record in db["records"]:
        category = record.get("category", "other")
        if category not in trends["by_category"]:
            trends["by_category"][category] = {"total": 0, "fixed": 0}
        trends["by_category"][category]["total"] += 1
        if record.get("fixed"):
            trends["by_category"][category]["fixed"] += 1

    # 修复率趋势（按日期）
    for date in sorted(trends["by_date"].keys()):
        date_data = trends["by_date"][date]
        fix_rate = round(date_data["fixed"] / date_data["total"] * 100, 1) if date_data["total"] > 0 else 0
        trends["fix_rate_trend"].append({
            "date": date,
            "total": date_data["total"],
            "fixed": date_data["fixed"],
            "fix_rate": fix_rate,
        })

    return trends


def validate_cubemx_config(ioc_path: str) -> dict:
    """验证 CubeMX 配置。

    Args:
        ioc_path: .ioc 文件路径

    Returns:
        验证结果字典
    """
    result = {
        "valid": True,
        "issues": [],
        "suggestions": [],
    }

    # 读取 ioc 文件
    try:
        from pathlib import Path
        content = Path(ioc_path).read_text(encoding="utf-8", errors="replace")
    except Exception as e:
        result["valid"] = False
        result["issues"].append(f"无法读取 ioc 文件: {e}")
        return result

    # 检查常见配置问题
    lines = content.splitlines()
    for line in lines:
        line = line.strip()
        if not line or line.startswith("#"):
            continue

        if "=" not in line:
            continue

        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip()

        # 检查时钟配置
        if "RCC.PLL" in key and value == "0":
            result["issues"].append("PLL 未启用，时钟配置可能不正确")
            result["suggestions"].append("在 CubeMX 中启用 PLL 并配置正确的时钟源")

        # 检查 GPIO 配置
        if key.startswith("P") and ".Mode" in key:
            if value == "GPIO_MODE_ANALOG":
                # 检查是否有 ADC 配置
                pass  # 需要更复杂的逻辑

        # 检查外设配置
        if "USART" in key and ".BaudRate" in key:
            try:
                baud = int(value)
                if baud not in [9600, 19200, 38400, 57600, 115200, 230400, 460800, 921600]:
                    result["suggestions"].append(f"USART 波特率 {baud} 不是标准值，建议使用 115200")
            except ValueError:
                pass

    # 如果没有发现问题，添加一般性建议
    if not result["issues"]:
        result["suggestions"].append("配置看起来正常，如有问题请在 CubeMX 中检查具体外设配置")

    return result


def get_prevention_suggestions(db_file: str = None) -> list[dict]:
    """获取错误预防建议。

    基于历史错误模式，提供预防建议。
    """
    db = load_database(db_file)
    suggestions = []

    # 分析历史错误模式
    category_counts = {}
    for record in db["records"]:
        category = record.get("category", "other")
        category_counts[category] = category_counts.get(category, 0) + 1

    # 基于历史错误提供预防建议
    if category_counts.get("compile", 0) > 3:
        suggestions.append({
            "category": "compile",
            "title": "编译错误预防",
            "suggestion": "历史记录显示编译错误较多，建议：",
            "actions": [
                "在修改代码前先备份",
                "使用 IDE 的语法检查功能",
                "定期编译测试，不要一次修改太多",
            ],
        })

    if category_counts.get("link", 0) > 3:
        suggestions.append({
            "category": "link",
            "title": "链接错误预防",
            "suggestion": "历史记录显示链接错误较多，建议：",
            "actions": [
                "确保所有源文件都添加到项目中",
                "检查头文件中的声明是否正确",
                "在 CubeMX 中启用需要的外设",
            ],
        })

    if category_counts.get("config", 0) > 3:
        suggestions.append({
            "category": "config",
            "title": "配置错误预防",
            "suggestion": "历史记录显示配置错误较多，建议：",
            "actions": [
                "在 CubeMX 中仔细检查配置",
                "使用 pin_checker.py 检查引脚冲突",
                "使用 clock_validator.py 检查时钟配置",
            ],
        })

    if category_counts.get("cubemx", 0) > 3:
        suggestions.append({
            "category": "cubemx",
            "title": "CubeMX/HAL 错误预防",
            "suggestion": "历史记录显示 CubeMX/HAL 错误较多，建议：",
            "actions": [
                "确保 CubeMX 生成的代码不被修改",
                "在 CubeMX 中检查外设配置",
                "检查 HAL 回调函数是否正确实现",
            ],
        })

    # 通用预防建议
    suggestions.append({
        "category": "general",
        "title": "通用预防建议",
        "suggestion": "为了减少错误，建议：",
        "actions": [
            "使用 error_tracker.py 记录每个错误和修复方法",
            "定期运行 workflow.py 检查项目状态",
            "在修改配置后重新生成 CubeMX 代码",
            "使用 health_check.py 检查项目健康状态",
        ],
    })

    return suggestions


def format_report_markdown(report: dict) -> str:
    """格式化报告为 Markdown。"""
    lines = []

    lines.append("# STM32 错误追踪报告")
    lines.append("")
    lines.append(f"> 生成时间: {report['timestamp']}")
    lines.append("")

    # 目录
    lines.append("## 目录")
    lines.append("")
    lines.append("1. [摘要](#摘要)")
    lines.append("2. [按分类统计](#按分类统计)")
    lines.append("3. [最近错误](#最近错误)")
    lines.append("4. [常见修复方法](#常见修复方法)")
    lines.append("5. [CubeMX 相关错误](#cubemx-相关错误)")
    lines.append("")

    # 摘要
    lines.append("## 摘要")
    lines.append("")
    summary = report["summary"]
    lines.append(f"| 指标 | 值 |")
    lines.append(f"|------|-----|")
    lines.append(f"| 总记录数 | {summary['total_records']} |")
    lines.append(f"| 已修复数 | {summary['total_fixed']} |")
    lines.append(f"| 修复率 | {summary['fix_rate']}% |")
    lines.append(f"| 最后更新 | {summary['last_updated'] or 'N/A'} |")
    lines.append("")

    # 按分类统计
    if report["by_category"]:
        lines.append("## 按分类统计")
        lines.append("")
        lines.append("| 分类 | 名称 | 数量 | 已修复 | 修复率 |")
        lines.append("|------|------|------|--------|--------|")
        for category, info in report["by_category"].items():
            lines.append(f"| {category} | {info['name']} | {info['count']} | {info['fixed_count']} | {info['fix_rate']}% |")
        lines.append("")

    # 最近错误
    if report["recent_errors"]:
        lines.append("## 最近错误")
        lines.append("")
        lines.append(f"| 错误 | 已修复 | 时间 |")
        lines.append(f"|------|--------|------|")
        for err in report["recent_errors"]:
            status = "✅" if err["fixed"] else "❌"
            lines.append(f"| {err['error']} | {status} | {err['timestamp'][:10] if err['timestamp'] else 'N/A'} |")
        lines.append("")

    # 常见修复方法
    if report["common_fixes"]:
        lines.append("## 常见修复方法")
        lines.append("")
        for i, fix in enumerate(report["common_fixes"], 1):
            lines.append(f"{i}. {fix['fix']} (使用 {fix['count']} 次)")
        lines.append("")

    # CubeMX 相关错误
    lines.append("## CubeMX 相关错误")
    lines.append("")
    lines.append("> **重要**：CubeMX 配置错误应在 CubeMX 中修改，不要在代码中绕过。")
    lines.append("")
    lines.append("| 错误类型 | 修复方法 | CubeMX 操作 |")
    lines.append("|---------|---------|------------|")
    lines.append("| GPIO 冲突 | 检查引脚配置 | Pinout & Configuration → GPIO |")
    lines.append("| USART 配置错误 | 检查波特率、数据位 | Connectivity → USART |")
    lines.append("| I2C NACK | 检查地址和上拉电阻 | Connectivity → I2C |")
    lines.append("| SPI 错误 | 检查时钟和模式 | Connectivity → SPI |")
    lines.append("| 时钟配置错误 | 检查 PLL 和分频 | Clock Configuration |")
    lines.append("| NVIC 优先级冲突 | 调整中断优先级 | System Core → NVIC |")
    lines.append("| DMA 配置错误 | 检查 DMA 通道 | System Core → DMA |")
    lines.append("| FreeRTOS 配置错误 | 检查堆大小和任务栈 | Middleware → FREERTOS |")
    lines.append("")

    return "\n".join(lines)


# === CLI ===

def main() -> int:
    setup_encoding()

    parser = argparse.ArgumentParser(
        description="STM32 错误追踪工具",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  %(prog)s --record --error "undefined reference to 'HAL_GPIO_Init'" --fix "添加 #include 'stm32f4xx_hal_gpio.h'" --file main.c
  %(prog)s --search "undefined reference"
  %(prog)s --list
  %(prog)s --report
  %(prog)s --suggest "undefined reference to 'xxx'"
        """,
    )

    parser.add_argument("--record", action="store_true", help="记录错误修复")
    parser.add_argument("--search", help="搜索错误历史")
    parser.add_argument("--list", action="store_true", help="列出所有记录")
    parser.add_argument("--report", action="store_true", help="生成统计报告")
    parser.add_argument("--suggest", help="获取修复建议")
    parser.add_argument("--export", metavar="FILE", help="导出为 solutions-log Markdown 文件")
    parser.add_argument("--error", help="错误信息")
    parser.add_argument("--fix", help="修复方法")
    parser.add_argument("--file", help="相关文件")
    parser.add_argument("--line", type=int, help="错误行号")
    parser.add_argument("--category", help="错误分类")
    parser.add_argument("--notes", help="备注")
    parser.add_argument("--db", help="数据库文件路径")
    parser.add_argument("--text", action="store_true", help="文本格式输出")
    parser.add_argument("--output", help="输出文件路径")

    args = parser.parse_args()

    if args.record:
        if not args.error:
            parser.error("--record 需要 --error 参数")

        record = record_error(
            error=args.error,
            fix=args.fix,
            file=args.file,
            line=args.line,
            category=args.category,
            notes=args.notes,
            db_file=args.db,
        )

        if args.text:
            print(f"✅ 错误已记录 (ID: {record['id']})")
            print(f"  错误: {record['error'][:80]}")
            if record.get("fix"):
                print(f"  修复: {record['fix'][:80]}")
            print(f"  分类: {record['category']}")
        else:
            print(json.dumps(record, indent=2, ensure_ascii=False))

    elif args.search:
        results = search_errors(args.search, db_file=args.db)

        if args.text:
            print(f"搜索结果: {len(results)} 条")
            for r in results:
                print(f"\n  [{r['id']}] {r['error'][:60]}")
                if r.get("fix"):
                    print(f"  修复: {r['fix'][:60]}")
        else:
            print(json.dumps(results, indent=2, ensure_ascii=False))

    elif args.list:
        db = load_database(args.db)

        if args.text:
            print(f"错误记录: {len(db['records'])} 条")
            for r in db["records"]:
                status = "✅" if r.get("fixed") else "❌"
                print(f"\n  [{r['id']}] {status} {r['error'][:60]}")
                if r.get("fix"):
                    print(f"  修复: {r['fix'][:60]}")
        else:
            print(json.dumps(db["records"], indent=2, ensure_ascii=False))

    elif args.report:
        report = generate_report(args.db)

        if args.text:
            print(format_report_markdown(report))
        else:
            print(json.dumps(report, indent=2, ensure_ascii=False))

    elif args.suggest:
        suggestions = get_fix_suggestions(args.suggest, db_file=args.db)

        if args.text:
            print(f"修复建议: {len(suggestions)} 条")
            for s in suggestions:
                print(f"\n  相似度: {s['similarity']:.0%}")
                print(f"  错误: {s['error'][:60]}")
                print(f"  修复: {s['fix'][:60]}")
        else:
            print(json.dumps(suggestions, indent=2, ensure_ascii=False))

    elif args.export:
        db = load_database(args.db)
        records = db.get("records", [])

        # 按日期分组
        by_date = {}
        for r in records:
            if not r.get("fixed"):
                continue
            date = r.get("timestamp", "")[:10]
            if date not in by_date:
                by_date[date] = []
            by_date[date].append(r)

        # 生成 Markdown
        lines = [
            "# 问题解决记录 (solutions-log)",
            "",
            f"生成时间: {datetime.now().strftime('%Y-%m-%d %H:%M')}",
            f"总记录: {len(records)} 条（已修复: {sum(1 for r in records if r.get('fixed'))} 条）",
            "",
            "---",
            "",
        ]

        category_icons = {
            "compile": "🔨", "link": "🔗", "runtime": "💥",
            "config": "⚙️", "cubemx": "🧊", "serial": "📡",
            "i2c": "🔌", "spi": "⚡", "adc": "📊", "other": "❓",
        }

        for date in sorted(by_date.keys(), reverse=True):
            lines.append(f"## {date}")
            lines.append("")
            for r in by_date[date]:
                icon = category_icons.get(r.get("category", "other"), "•")
                lines.append(f"### {icon} #{r['id']}: {r['error'][:60]}")
                lines.append("")
                lines.append(f"- **错误**: {r['error']}")
                if r.get("fix"):
                    lines.append(f"- **修复**: {r['fix']}")
                if r.get("file"):
                    lines.append(f"- **文件**: {r['file']}")
                if r.get("notes"):
                    lines.append(f"- **备注**: {r['notes']}")
                lines.append("")

        markdown = "\n".join(lines)

        # 写入文件
        with open(args.export, "w", encoding="utf-8") as f:
            f.write(markdown)

        if args.text:
            print(f"✅ 已导出到: {args.export}")
            print(f"  记录数: {len(records)}")
        else:
            print(json.dumps({"success": True, "file": args.export, "count": len(records)},
                             indent=2, ensure_ascii=False))

    else:
        parser.print_help()

    return 0


if __name__ == "__main__":
    sys.exit(main())
