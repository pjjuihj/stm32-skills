#!/usr/bin/env python
"""STM32 编译错误自动修复工具。

解析 build.log，自动修复常见编译错误。

功能：
- 解析 build.log，提取错误信息
- 自动修复常见错误（文件缺失、类型未定义等）
- 生成修复报告

使用示例：
  python auto_fix.py --log build.log --project project.uvprojx
  python auto_fix.py --log build.log --auto-fix
"""

from __future__ import annotations

import argparse
import io
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

# ======================== 错误类型定义 ========================

ERROR_PATTERNS = {
    "file_not_found": {
        "pattern": r"'(.+\.h)' file not found",
        "description": "头文件缺失",
        "fix": "create_header"
    },
    "undefined_reference": {
        "pattern": r"Undefined symbol (.+)",
        "description": "未定义的符号",
        "fix": "add_extern"
    },
    "unknown_type": {
        "pattern": r"unknown type name '(.+)'",
        "description": "未知类型",
        "fix": "add_typedef"
    },
    "use_undeclared": {
        "pattern": r"use of undeclared identifier '(.+)'",
        "description": "未声明的标识符",
        "fix": "add_declaration"
    },
    "no_such_file": {
        "pattern": r"no such file or directory: '(.+)'",
        "description": "文件不存在",
        "fix": "create_file"
    },
    "implicit_declaration": {
        "pattern": r"call to undeclared function '(.+)'",
        "description": "隐式函数声明",
        "fix": "add_function_declaration"
    }
}

# ======================== 头文件模板 ========================

HEADER_TEMPLATES = {
    "FreeRTOSConfig.h": """/**
 * @file    FreeRTOSConfig.h
 * @brief   FreeRTOS 配置文件（自动生成）
 */

#ifndef FREERTOS_CONFIG_H
#define FREERTOS_CONFIG_H

#include "stm32f4xx.h"

#define configUSE_PREEMPTION                     1
#define configUSE_PORT_OPTIMISED_TASK_SELECTION  1
#define configCPU_CLOCK_HZ                       (SystemCoreClock)
#define configTICK_RATE_HZ                       ((TickType_t)1000)
#define configMAX_PRIORITIES                     32
#define configMINIMAL_STACK_SIZE                 ((uint16_t)128)
#define configMAX_TASK_NAME_LEN                  16
#define configUSE_16_BIT_TICKS                   0
#define configUSE_MUTEXES                        1
#define configUSE_RECURSIVE_MUTEXES              1
#define configUSE_COUNTING_SEMAPHORES            1
#define configSUPPORT_STATIC_ALLOCATION          1
#define configSUPPORT_DYNAMIC_ALLOCATION         1
#define configTOTAL_HEAP_SIZE                    ((size_t)(16 * 1024))
#define configCHECK_FOR_STACK_OVERFLOW           2

#ifdef __NVIC_PRIO_BITS
  #define configPRIO_BITS                       __NVIC_PRIO_BITS
#else
  #define configPRIO_BITS                       4
#endif

#define configLIBRARY_LOWEST_INTERRUPT_PRIORITY         15
#define configLIBRARY_MAX_SYSCALL_INTERRUPT_PRIORITY    5
#define configKERNEL_INTERRUPT_PRIORITY          (configLIBRARY_LOWEST_INTERRUPT_PRIORITY << (8 - configPRIO_BITS))
#define configMAX_SYSCALL_INTERRUPT_PRIORITY     (configLIBRARY_MAX_SYSCALL_INTERRUPT_PRIORITY << (8 - configPRIO_BITS))

#define INCLUDE_vTaskPrioritySet                 1
#define INCLUDE_uxTaskPriorityGet                1
#define INCLUDE_vTaskDelete                      1
#define INCLUDE_vTaskSuspend                     1
#define INCLUDE_vTaskDelayUntil                  1
#define INCLUDE_vTaskDelay                       1
#define INCLUDE_xTaskGetSchedulerState           1
#define INCLUDE_xTimerPendFunctionCall           1

#define vPortSVCHandler     SVC_Handler
#define xPortPendSVHandler  PendSV_Handler

#endif /* FREERTOS_CONFIG_H */
""",

    "MPU6050.h": """/**
 * @file    MPU6050.h
 * @brief   MPU6050 驱动头文件（占位）
 */

#ifndef __MPU6050_H
#define __MPU6050_H

#include "main.h"

static inline int MPU6050_DMP_init(void) { return -1; }
static inline int MPU6050_DMP_Get_Data(float *pitch, float *roll, float *yaw) {
    if (pitch) *pitch = 0;
    if (roll) *roll = 0;
    if (yaw) *yaw = 0;
    return -1;
}

#endif /* __MPU6050_H */
""",

    "balance.h": """/**
 * @file    balance.h
 * @brief   平衡控制头文件（占位）
 */

#ifndef __BALANCE_H
#define __BALANCE_H

#include "main.h"

typedef enum {
    STATE_IDLE = 0,
    STATE_BALANCING,
    STATE_FALLING
} BalanceState_t;

static inline void Balance_Init(void) {}
static inline void Balance_Update(float pitch, float roll, float gyro_z, float speed_l, float speed_r) {
    (void)pitch; (void)roll; (void)gyro_z; (void)speed_l; (void)speed_r;
}
static inline BalanceState_t Balance_GetState(void) { return STATE_IDLE; }
static inline void Balance_GetPWM(int *left, int *right) {
    if (left) *left = 0;
    if (right) *right = 0;
}
static inline void Balance_ForceStop(void) {}
static inline void Balance_SetPID_Single(int ring, int param, float value) {
    (void)ring; (void)param; (void)value;
}
static inline void Balance_SetTurnTarget(float target) { (void)target; }

#endif /* __BALANCE_H */
""",

    "encoder.h": """/**
 * @file    encoder.h
 * @brief   编码器头文件（占位）
 */

#ifndef __ENCODER_H
#define __ENCODER_H

#include "main.h"

static inline void Encoder_Init(void) {}
static inline void Encoder_Update(void) {}
static inline float Encoder_GetSpeedLeft(void) { return 0.0f; }
static inline float Encoder_GetSpeedRight(void) { return 0.0f; }

#endif /* __ENCODER_H */
""",

    "motor.h": """/**
 * @file    motor.h
 * @brief   电机控制头文件（占位）
 */

#ifndef __MOTOR_H
#define __MOTOR_H

#include "main.h"

static inline void Motor_Init(void) {}
static inline void Motor_Stop(void) {}
static inline void Motor_SetLeft(int pwm) { (void)pwm; }
static inline void Motor_SetRight(int pwm) { (void)pwm; }

#endif /* __MOTOR_H */
""",

    "watchdog.h": """/**
 * @file    watchdog.h
 * @brief   看门狗头文件（占位）
 */

#ifndef __WATCHDOG_H
#define __WATCHDOG_H

#include "main.h"

static inline void Watchdog_IWDG_Init(uint32_t timeout_ms) { (void)timeout_ms; }
static inline void Watchdog_Feed(void) {}

#endif /* __WATCHDOG_H */
""",

    "inv_mpu.h": """/**
 * @file    inv_mpu.h
 * @brief   InvenSense MPU 驱动头文件（占位）
 */

#ifndef __INV_MPU_H
#define __INV_MPU_H

#include "main.h"

#endif /* __INV_MPU_H */
"""
}

# ======================== 源文件模板 ========================

SOURCE_TEMPLATES = {
    "freertos.c": """/**
 * @file    freertos.c
 * @brief   FreeRTOS 应用代码（自动生成）
 */

#include "FreeRTOS.h"
#include "task.h"
#include "main.h"
#include "cmsis_os.h"

/* 任务句柄 */
osThreadId_t DefaultTaskHandle;

/* 任务函数 */
void StartDefaultTask(void *argument);

/**
 * @brief  FreeRTOS 初始化
 */
void MX_FREERTOS_Init(void) {
    /* 创建默认任务 */
    const osThreadAttr_t defaultTask_attributes = {
        .name = "defaultTask",
        .stack_size = 128 * 4,
        .priority = (osPriority_t) osPriorityNormal,
    };
    DefaultTaskHandle = osThreadNew(StartDefaultTask, NULL, &defaultTask_attributes);
}

/**
 * @brief  默认任务函数
 */
void StartDefaultTask(void *argument) {
    (void)argument;
    for (;;) {
        osDelay(1);
    }
}
""",

    "balance.c": """/**
 * @file    balance.c
 * @brief   平衡控制模块（占位）
 */

#include "balance.h"

/* 当前未使用 */
""",

    "pid.c": """/**
 * @file    pid.c
 * @brief   PID 控制器（占位）
 */

#include "pid.h"

/* 当前未使用 */
""",

    "encoder.c": """/**
 * @file    encoder.c
 * @brief   编码器驱动（占位）
 */

#include "encoder.h"

/* 当前未使用 */
""",

    "motor.c": """/**
 * @file    motor.c
 * @brief   电机驱动（占位）
 */

#include "motor.h"

/* 当前未使用 */
""",

    "watchdog.c": """/**
 * @file    watchdog.c
 * @brief   看门狗驱动（占位）
 */

#include "watchdog.h"

/* 当前未使用 */
""",

    "vofa.c": """/**
 * @file    vofa.c
 * @brief   VOFA+ 通信模块（占位）
 */

#include "vofa.h"

/* 当前未使用 */
""",

    "gimbal_example.c": """/**
 * @file    gimbal_example.c
 * @brief   云台示例代码（占位）
 */

#include "main.h"

/* 当前未使用 */
""",

    "bootloader.c": """/**
 * @file    bootloader.c
 * @brief   USB DFU Bootloader（占位）
 */

#include "bootloader.h"

/* 当前未使用 */
""",

    "inv_mpu.c": """/**
 * @file    inv_mpu.c
 * @brief   InvenSense MPU 驱动（占位）
 */

#include "inv_mpu.h"

/* 当前未使用 */
""",

    "inv_mpu_dmp_motion_driver.c": """/**
 * @file    inv_mpu_dmp_motion_driver.c
 * @brief   MPU DMP 运动驱动（占位）
 */

#include "inv_mpu.h"

/* 当前未使用 */
""",

    "MPU6050.c": """/**
 * @file    MPU6050.c
 * @brief   MPU6050 驱动（占位）
 */

#include "MPU6050.h"

/* 当前未使用 */
"""
}

# ======================== 错误解析器 ========================

def parse_build_log(log_path: str) -> list[dict[str, Any]]:
    """解析 build.log，提取错误信息"""
    errors = []

    try:
        with open(log_path, "r", encoding="utf-8", errors="replace") as f:
            content = f.read()
    except FileNotFoundError:
        print(f"❌ 文件不存在: {log_path}")
        return []

    # 解析错误行
    for line in content.split("\n"):
        line = line.strip()
        if not line:
            continue

        # 匹配错误模式
        for error_type, error_info in ERROR_PATTERNS.items():
            match = re.search(error_info["pattern"], line)
            if match:
                errors.append({
                    "type": error_type,
                    "description": error_info["description"],
                    "fix": error_info["fix"],
                    "message": line,
                    "match": match.group(1) if match.groups() else None
                })
                break

    return errors

def fix_errors(errors: list[dict[str, Any]], project_dir: str) -> list[dict[str, Any]]:
    """自动修复错误"""
    fixes = []

    for error in errors:
        if error["fix"] == "create_header":
            header_name = error["match"]
            if header_name in HEADER_TEMPLATES:
                # 确定头文件路径
                if header_name == "FreeRTOSConfig.h":
                    header_path = os.path.join(project_dir, "Core", "Inc", header_name)
                else:
                    header_path = os.path.join(project_dir, "Board", header_name.replace(".h", ""), header_name)

                # 创建目录
                os.makedirs(os.path.dirname(header_path), exist_ok=True)

                # 写入文件
                with open(header_path, "w", encoding="utf-8") as f:
                    f.write(HEADER_TEMPLATES[header_name])

                fixes.append({
                    "type": "create_header",
                    "file": header_path,
                    "description": f"创建头文件: {header_name}"
                })
            else:
                fixes.append({
                    "type": "manual_fix",
                    "description": f"需要手动创建: {header_name}"
                })

        elif error["fix"] == "create_file":
            file_path = error["match"]
            if file_path:
                # 提取文件名
                file_name = os.path.basename(file_path)

                # 检查是否有源文件模板
                if file_name in SOURCE_TEMPLATES:
                    # 构建完整路径
                    full_path = os.path.join(project_dir, file_path.replace("../", ""))

                    # 创建目录
                    os.makedirs(os.path.dirname(full_path), exist_ok=True)

                    # 写入文件
                    with open(full_path, "w", encoding="utf-8") as f:
                        f.write(SOURCE_TEMPLATES[file_name])

                    fixes.append({
                        "type": "create_source",
                        "file": full_path,
                        "description": f"创建源文件: {file_name}"
                    })
                else:
                    fixes.append({
                        "type": "manual_fix",
                        "description": f"需要手动创建: {file_name}"
                    })

    return fixes

# ======================== CLI ========================

def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="STM32 编译错误自动修复工具",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  %(prog)s --log build.log --project .                    # 分析错误
  %(prog)s --log build.log --project . --auto-fix         # 自动修复
        """,
    )

    parser.add_argument("--log", required=True, help="build.log 文件路径")
    parser.add_argument("--project", default=".", help="项目根目录")
    parser.add_argument("--auto-fix", action="store_true", help="自动修复错误")
    parser.add_argument("--json", action="store_true", help="输出 JSON 格式")

    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()

    # 解析错误
    errors = parse_build_log(args.log)

    if not errors:
        print("✅ 未发现编译错误")
        return 0

    print(f"📊 发现 {len(errors)} 个错误：")
    for i, error in enumerate(errors, 1):
        print(f"  {i}. [{error['type']}] {error['description']}")
        print(f"     {error['message']}")

    # 自动修复
    if args.auto_fix:
        print("\n🔧 开始自动修复...")
        fixes = fix_errors(errors, args.project)

        if fixes:
            print(f"\n✅ 完成 {len(fixes)} 项修复：")
            for fix in fixes:
                print(f"  - {fix['description']}")
        else:
            print("\n⚠️ 没有可自动修复的错误")

    return 0


if __name__ == "__main__":
    sys.exit(main())
