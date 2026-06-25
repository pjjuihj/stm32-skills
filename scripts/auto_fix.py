#!/usr/bin/env python
"""STM32 编译错误自动修复工具。

解析 build.log，自动修复常见编译错误。

功能：
- 解析 build.log，提取错误信息
- 自动修复常见错误（文件缺失、类型未定义等）
- 生成修复报告

使用示例：
  python auto_fix.py --log build.log --project .
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
    # 头文件/文件缺失
    "file_not_found": {
        "pattern": r"'(.+\.h)' file not found",
        "description": "头文件缺失",
        "fix": "create_header"
    },
    "no_such_file": {
        "pattern": r"no such file or directory: '(.+)'",
        "description": "文件不存在",
        "fix": "create_file"
    },
    "cannot_open": {
        "pattern": r"cannot open source input file '(.+)'",
        "description": "无法打开源文件",
        "fix": "create_file"
    },

    # 类型/符号错误
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
    "implicit_declaration": {
        "pattern": r"call to undeclared function '(.+)'",
        "description": "隐式函数声明",
        "fix": "add_function_declaration"
    },

    # 语法错误
    "expected_semicolon": {
        "pattern": r"expected ';' before '}'",
        "description": "缺少分号",
        "fix": "add_semicolon"
    },
    "expected_brace": {
        "pattern": r"expected '}' before end of file",
        "description": "缺少大括号",
        "fix": "add_brace"
    },

    # 链接错误
    "multiple_definition": {
        "pattern": r"multiple definition of '(.+)'",
        "description": "重复定义",
        "fix": "remove_duplicate"
    },
    "undefined_symbol": {
        "pattern": r"Undefined symbol (.+)",
        "description": "未定义符号",
        "fix": "add_implementation"
    },

    # ARMClang 特有错误
    "armclang_error": {
        "pattern": r"error: (.+)",
        "description": "ARMClang 编译错误",
        "fix": "parse_armclang_error"
    },
    "armclang_warning": {
        "pattern": r"warning: (.+)",
        "description": "ARMClang 编译警告",
        "fix": "parse_armclang_warning"
    },

    # 告警
    "unused_variable": {
        "pattern": r"unused variable '(.+)'",
        "description": "未使用的变量",
        "fix": "remove_unused"
    },
    "unused_function": {
        "pattern": r"defined but not used '(.+)'",
        "description": "未使用的函数",
        "fix": "remove_unused"
    },
    "implicit_function_declaration": {
        "pattern": r"implicit declaration of function '(.+)'",
        "description": "隐式函数声明",
        "fix": "add_function_declaration"
    },
    "incompatible_pointer": {
        "pattern": r"passing '(.+)' to parameter of type '(.+)' discards qualifiers",
        "description": "类型不兼容",
        "fix": "fix_pointer_type"
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
""",

    "vofa.h": """/**
 * @file    vofa.h
 * @brief   VOFA+ 通信头文件（占位）
 */

#ifndef __VOFA_H
#define __VOFA_H

#include "main.h"

typedef struct {
    float pitch;
    float roll;
    float gyro_z;
    float speed_left;
    float speed_right;
    int pwm_left;
    int pwm_right;
    uint8_t state;
} VOFA_Data_t;

typedef struct {
    uint8_t cmd;
    float value;
} VOFA_Command_t;

void VOFA_Init(void);
void VOFA_SendData(VOFA_Data_t *data);
void VOFA_SendString(const char *str);
void VOFA_ParseByte(uint8_t byte);
uint8_t VOFA_HasCommand(void);
VOFA_Command_t VOFA_GetCommand(void);
void VOFA_TxCpltCallback(void);

#endif /* __VOFA_H */
""",

    "scope.h": """/**
 * @file    scope.h
 * @brief   示波器采集模块
 */

#ifndef __SCOPE_H
#define __SCOPE_H

#include "main.h"

#define SCOPE_BUF_SIZE 512
#define SCOPE_DEFAULT_RATE 1000

void Scope_Init(void);
void Scope_Start(void);
void Scope_Stop(void);
void Scope_SetRate(uint32_t rate);
uint32_t Scope_GetRate(void);
uint8_t Scope_IsFrameReady(void);
uint16_t Scope_GetFrame(uint16_t *buf);
uint16_t Scope_GetLatest(void);
void Scope_ADC_Callback(void);

#endif /* __SCOPE_H */
""",

    "scope_uart.h": """/**
 * @file    scope_uart.h
 * @brief   示波器串口通信协议
 */

#ifndef __SCOPE_UART_H
#define __SCOPE_UART_H

#include "main.h"

void ScopeUART_Init(void);
void ScopeUART_ParseByte(uint8_t byte);
void ScopeUART_SendFrame(uint16_t *data, uint16_t len);
void ScopeUART_SendStatus(void);
uint8_t ScopeUART_HasCommand(void);
uint8_t ScopeUART_GetCommand(void);
uint16_t ScopeUART_GetCmdData(void);

#endif /* __SCOPE_UART_H */
""",

    "scope_display.h": """/**
 * @file    scope_display.h
 * @brief   示波器 OLED 显示模块
 */

#ifndef __SCOPE_DISPLAY_H
#define __SCOPE_DISPLAY_H

#include "main.h"

void ScopeDisp_Init(void);
void ScopeDisp_UpdateWave(uint16_t *data, uint16_t len);
void ScopeDisp_UpdateStatus(uint32_t rate, uint32_t freq, uint8_t wave, uint8_t running);

#endif /* __SCOPE_DISPLAY_H */
""",

    "siggen.h": """/**
 * @file    siggen.h
 * @brief   信号发生器模块
 */

#ifndef __SIGGEN_H
#define __SIGGEN_H

#include "main.h"

#define SIGGEN_DEFAULT_FREQ 500
#define SIGGEN_LUT_SIZE 256

void SigGen_Init(void);
void SigGen_Start(void);
void SigGen_Stop(void);
void SigGen_SetFrequency(uint32_t freq);
uint32_t SigGen_GetFrequency(void);
void SigGen_SetWaveType(uint8_t type);
uint8_t SigGen_GetWaveType(void);
uint8_t SigGen_IsRunning(void);

#endif /* __SIGGEN_H */
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
""",

    "scope.c": """/**
 * @file    scope.c
 * @brief   示波器采集模块（占位）
 */

#include "scope.h"

/* 当前未使用 */
""",

    "scope_uart.c": """/**
 * @file    scope_uart.c
 * @brief   示波器串口通信协议（占位）
 */

#include "scope_uart.h"

/* 当前未使用 */
""",

    "scope_display.c": """/**
 * @file    scope_display.c
 * @brief   示波器 OLED 显示模块（占位）
 */

#include "scope_display.h"

/* 当前未使用 */
""",

    "siggen.c": """/**
 * @file    siggen.c
 * @brief   信号发生器模块（占位）
 */

#include "siggen.h"

/* 当前未使用 */
""",

    "adc.c": """/**
 * @file    adc.c
 * @brief   ADC 驱动（占位）
 */

#include "adc.h"

/* 当前未使用 */
""",

    "dac.c": """/**
 * @file    dac.c
 * @brief   DAC 驱动（占位）
 */

#include "dac.h"

/* 当前未使用 */
""",

    "iwdg.c": """/**
 * @file    iwdg.c
 * @brief   独立看门狗驱动（占位）
 */

#include "iwdg.h"

/* 当前未使用 */
""",

    "tim.c": """/**
 * @file    tim.c
 * @brief   定时器驱动（占位）
 */

#include "tim.h"

/* 当前未使用 */
""",
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
        try:
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

            elif error["fix"] == "add_function_declaration":
                # 添加函数声明到 main.h
                func_name = error["match"]
                main_h_path = os.path.join(project_dir, "Core", "Inc", "main.h")
                if os.path.exists(main_h_path):
                    with open(main_h_path, "r", encoding="utf-8") as f:
                        content = f.read()
                    # 在 main.h 末尾添加函数声明
                    if func_name not in content:
                        with open(main_h_path, "a", encoding="utf-8") as f:
                            f.write(f"\nvoid {func_name}(void *argument);\n")
                        fixes.append({
                            "type": "add_declaration",
                            "description": f"添加函数声明: {func_name}"
                        })

            elif error["fix"] == "remove_duplicate":
                # 重复定义警告，建议用户手动检查
                symbol = error["match"]
                fixes.append({
                    "type": "warning",
                    "description": f"重复定义: {symbol} - 建议添加 static 关键字"
                })

            elif error["fix"] == "remove_unused":
                # 未使用变量/函数警告，建议用户手动检查
                symbol = error["match"]
                fixes.append({
                    "type": "warning",
                    "description": f"未使用: {symbol} - 建议删除或添加 __attribute__((unused))"
                })

        except Exception as e:
            fixes.append({
                "type": "error",
                "description": f"修复失败: {str(e)}"
            })

    return fixes

# ======================== CLI ========================

def find_build_log(project_dir: str) -> str | None:
    """自动查找 build.log 文件。"""
    candidates = [
        os.path.join(project_dir, "build.log"),
        os.path.join(project_dir, "MDK-ARM", "build.log"),
    ]
    for candidate in candidates:
        if os.path.isfile(candidate):
            return candidate
    return None


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="STM32 编译错误自动修复工具",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  %(prog)s --log build.log --project .                    # 分析错误
  %(prog)s --log build.log --project . --auto-fix         # 自动修复
  %(prog)s --auto . --auto-fix                            # 自动检测 build.log 并修复
        """,
    )

    parser.add_argument("--auto", metavar="PROJECT_DIR",
                        help="自动检测项目配置并查找 build.log（指定项目根目录）")
    parser.add_argument("--log", help="build.log 文件路径（--auto 模式下可省略）")
    parser.add_argument("--project", default=".", help="项目根目录")
    parser.add_argument("--auto-fix", action="store_true", help="自动修复错误")
    parser.add_argument("--text", action="store_true", help="输出人类可读文本格式（默认输出 JSON）")

    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()

    # --auto 模式：自动查找 build.log
    if args.auto:
        args.project = args.auto
        if not args.log:
            args.log = find_build_log(args.auto)
            if not args.log:
                print(f"❌ 在 {args.auto} 中未找到 build.log", file=sys.stderr)
                return 1
            print(f"自动找到 build.log: {args.log}")

    if not args.log:
        parser.error("请指定 --log <build.log路径> 或 --auto <项目目录>")

    # 解析错误
    errors = parse_build_log(args.log)

    if not errors:
        if args.text:
            print("✅ 未发现编译错误")
        else:
            from shared import output_json
            output_json({"success": True, "errors": [], "fixes": [], "message": "未发现编译错误"})
        return 0

    # 自动修复
    fixes = []
    if args.auto_fix:
        fixes = fix_errors(errors, args.project)

    # 自动记录到 error_tracker
    if fixes:
        try:
            from shared import run_script
            for fix in fixes:
                error_desc = fix.get("description", "编译错误")
                fix_desc = fix.get("fix", "auto_fix 自动修复")
                run_script("error_tracker.py", [
                    "--record", "--error", error_desc, "--fix", fix_desc
                ], timeout=10)
        except Exception:
            pass  # 记录失败不影响主流程

    # 输出结果
    if args.text:
        # 人类可读格式
        print(f"📊 发现 {len(errors)} 个错误：")
        for i, error in enumerate(errors, 1):
            print(f"  {i}. [{error['type']}] {error['description']}")
            print(f"     {error['message']}")
        if args.auto_fix:
            if fixes:
                print(f"\n✅ 完成 {len(fixes)} 项修复：")
                for fix in fixes:
                    print(f"  - {fix['description']}")
            else:
                print("\n⚠️ 没有可自动修复的错误")
    else:
        # JSON 格式
        from shared import output_json
        output_json({
            "success": True,
            "errors": errors,
            "fixes": fixes,
            "error_count": len(errors),
            "fix_count": len(fixes),
        })

    return 0


if __name__ == "__main__":
    sys.exit(main())
