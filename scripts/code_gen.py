#!/usr/bin/env python
"""STM32 代码生成工具。

生成常用的代码模板，包括外设驱动、任务函数等。

功能：
- 生成外设驱动代码
- 生成 FreeRTOS 任务代码
- 生成中断处理代码

使用示例：
  python code_gen.py --type uart --name USART1 --output uart1.c
  python code_gen.py --type task --name SensorTask --output sensor_task.c
  python code_gen.py --type gpio --name LED --pin PA8 --output led.c
"""

from __future__ import annotations

import argparse
import io
import os
import sys
from pathlib import Path

# 编码处理
if sys.stdout and hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

# ======================== 代码模板 ========================

UART_DRIVER_TEMPLATE = """/**
 * @file    {filename}
 * @brief   {name} 驱动实现
 */

#include "{header}"
#include "usart.h"

/* 接收缓冲区 */
static uint8_t rx_buffer[256];
static volatile uint16_t rx_index = 0;

/* 发送缓冲区 */
static uint8_t tx_buffer[256];

/**
 * @brief  {name} 初始化
 */
void {name_upper}_Init(void)
{{
    /* 初始化已在 MX_{name_upper}_Init() 中完成 */
}}

/**
 * @brief  {name} 发送数据
 * @param  data: 数据指针
 * @param  len: 数据长度
 * @retval HAL 状态
 */
HAL_StatusTypeDef {name_upper}_Send(uint8_t *data, uint16_t len)
{{
    return HAL_UART_Transmit(&{name_lower}, data, len, 100);
}}

/**
 * @brief  {name} 发送字符串
 * @param  str: 字符串指针
 * @retval HAL 状态
 */
HAL_StatusTypeDef {name_upper}_SendString(const char *str)
{{
    return {name_upper}_Send((uint8_t *)str, strlen(str));
}}

/**
 * @brief  {name} 接收完成回调
 * @param  huart: UART 句柄
 */
void {name_upper}_RxCpltCallback(UART_HandleTypeDef *huart)
{{
    if (huart->Instance == {name_upper}_INSTANCE)
    {{
        /* 处理接收到的数据 */
        rx_index++;

        /* 重新启动接收 */
        HAL_UART_Receive_IT(&{name_lower}, &rx_buffer[rx_index], 1);
    }}
}}

/**
 * @brief  获取接收缓冲区数据
 * @retval 接收到的数据
 */
uint8_t {name_upper}_GetRxData(void)
{{
    return rx_buffer[rx_index - 1];
}}

/**
 * @brief  检查是否有新数据
 * @retval 1: 有新数据, 0: 无新数据
 */
uint8_t {name_upper}_HasData(void)
{{
    return rx_index > 0;
}}

/**
 * @brief  清除接收缓冲区
 */
void {name_upper}_ClearRxBuffer(void)
{{
    rx_index = 0;
}}
"""

UART_HEADER_TEMPLATE = """/**
 * @file    {filename}
 * @brief   {name} 驱动头文件
 */

#ifndef __{name_upper}_H
#define __{name_upper}_H

#include "main.h"

/* 函数声明 */
void {name_upper}_Init(void);
HAL_StatusTypeDef {name_upper}_Send(uint8_t *data, uint16_t len);
HAL_StatusTypeDef {name_upper}_SendString(const char *str);
uint8_t {name_upper}_GetRxData(void);
uint8_t {name_upper}_HasData(void);
void {name_upper}_ClearRxBuffer(void);

#endif /* __{name_upper}_H */
"""

TASK_TEMPLATE = """/**
 * @file    {filename}
 * @brief   {name} 任务实现
 */

#include "FreeRTOS.h"
#include "task.h"
#include "main.h"

/* 任务句柄 */
osThreadId_t {name}Handle;

/* 任务属性 */
const osThreadAttr_t {name}_attributes = {{
    .name = "{name}",
    .stack_size = {stack_size} * 4,
    .priority = (osPriority_t) osPriority{priority},
}};

/**
 * @brief  {name} 初始化
 */
static void {name}_Init(void)
{{
    /* 初始化代码 */
    // TODO: 添加初始化代码
}}

/**
 * @brief  {name} 主循环
 */
static void {name}_Process(void)
{{
    /* 任务代码 */
    // TODO: 添加任务代码
}}

/**
 * @brief  {name} 任务函数
 * @param  argument: 任务参数
 */
void {name}(void *argument)
{{
    (void)argument;

    /* 初始化 */
    {name}_Init();

    /* 主循环 */
    for (;;)
    {{
        /* 处理 */
        {name}_Process();

        /* 延时 */
        osDelay({delay_ms});
    }}
}}
"""

GPIO_TEMPLATE = """/**
 * @file    {filename}
 * @brief   {name} GPIO 驱动实现
 */

#include "{header}"

/**
 * @brief  {name} 初始化
 */
void {name_upper}_Init(void)
{{
    GPIO_InitTypeDef GPIO_InitStruct = {{0}};

    /* GPIO 时钟使能 */
    __HAL_RCC_{port}_CLK_ENABLE();

    /* 配置 GPIO 引脚 */
    GPIO_InitStruct.Pin = {pin};
    GPIO_InitStruct.Mode = {mode};
    GPIO_InitStruct.Pull = {pull};
    GPIO_InitStruct.Speed = {speed};
    HAL_GPIO_Init({port}, &GPIO_InitStruct);
}}

/**
 * @brief  设置 {name} 状态
 * @param  state: 0=低电平, 1=高电平
 */
void {name_upper}_Set(uint8_t state)
{{
    if (state)
    {{
        HAL_GPIO_WritePin({port}, {pin}, GPIO_PIN_SET);
    }}
    else
    {{
        HAL_GPIO_WritePin({port}, {pin}, GPIO_PIN_RESET);
    }}
}}

/**
 * @brief  切换 {name} 状态
 */
void {name_upper}_Toggle(void)
{{
    HAL_GPIO_TogglePin({port}, {pin});
}}

/**
 * @brief  读取 {name} 状态
 * @retval 引脚状态
 */
uint8_t {name_upper}_Read(void)
{{
    return HAL_GPIO_ReadPin({port}, {pin}) == GPIO_PIN_SET ? 1 : 0;
}}
"""

GPIO_HEADER_TEMPLATE = """/**
 * @file    {filename}
 * @brief   {name} GPIO 驱动头文件
 */

#ifndef __{name_upper}_H
#define __{name_upper}_H

#include "main.h"

/* 函数声明 */
void {name_upper}_Init(void);
void {name_upper}_Set(uint8_t state);
void {name_upper}_Toggle(void);
uint8_t {name_upper}_Read(void);

#endif /* __{name_upper}_H */
"""

# ======================== 代码生成函数 ========================

def generate_uart_code(name: str, output_dir: str) -> None:
    """生成 UART 驱动代码"""
    name_lower = name.lower()
    name_upper = name.upper()

    # 生成源文件
    filename = f"{name_lower}.c"
    content = UART_DRIVER_TEMPLATE.format(
        filename=filename,
        name=name,
        name_lower=name_lower,
        name_upper=name_upper,
        header=f"{name_lower}.h"
    )

    output_path = os.path.join(output_dir, filename)
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(content)
    print(f"✅ 生成文件: {filename}")

    # 生成头文件
    filename = f"{name_lower}.h"
    content = UART_HEADER_TEMPLATE.format(
        filename=filename,
        name=name,
        name_upper=name_upper
    )

    output_path = os.path.join(output_dir, filename)
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(content)
    print(f"✅ 生成文件: {filename}")

def generate_task_code(name: str, output_dir: str, stack_size: int = 256,
                       priority: str = "Normal", delay_ms: int = 100) -> None:
    """生成 FreeRTOS 任务代码"""
    filename = f"{name.lower()}.c"
    content = TASK_TEMPLATE.format(
        filename=filename,
        name=name,
        stack_size=stack_size,
        priority=priority,
        delay_ms=delay_ms
    )

    output_path = os.path.join(output_dir, filename)
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(content)
    print(f"✅ 生成文件: {filename}")

def generate_gpio_code(name: str, pin: str, port: str, output_dir: str,
                       mode: str = "GPIO_MODE_OUTPUT_PP", pull: str = "GPIO_NOPULL",
                       speed: str = "GPIO_SPEED_FREQ_LOW") -> None:
    """生成 GPIO 驱动代码"""
    name_lower = name.lower()
    name_upper = name.upper()

    # 生成源文件
    filename = f"{name_lower}.c"
    content = GPIO_TEMPLATE.format(
        filename=filename,
        name=name,
        name_lower=name_lower,
        name_upper=name_upper,
        header=f"{name_lower}.h",
        pin=pin,
        port=port,
        mode=mode,
        pull=pull,
        speed=speed
    )

    output_path = os.path.join(output_dir, filename)
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(content)
    print(f"✅ 生成文件: {filename}")

    # 生成头文件
    filename = f"{name_lower}.h"
    content = GPIO_HEADER_TEMPLATE.format(
        filename=filename,
        name=name,
        name_upper=name_upper
    )

    output_path = os.path.join(output_dir, filename)
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(content)
    print(f"✅ 生成文件: {filename}")

# ======================== CLI ========================

def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="STM32 代码生成工具",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  %(prog)s --type uart --name USART1 --output Core/Src        # 生成 UART 驱动
  %(prog)s --type task --name SensorTask --output Core/Src    # 生成任务代码
  %(prog)s --type gpio --name LED --pin PA8 --port GPIOA --output Core/Src  # 生成 GPIO 驱动
        """,
    )

    parser.add_argument("--type", required=True, choices=["uart", "task", "gpio", "spi", "i2c", "adc", "dac"],
                        help="代码类型")
    parser.add_argument("--name", required=True, help="名称")
    parser.add_argument("--output", default=".", help="输出目录")
    parser.add_argument("--pin", help="GPIO 引脚 (仅 gpio 类型)")
    parser.add_argument("--port", help="GPIO 端口 (仅 gpio 类型)")
    parser.add_argument("--stack-size", type=int, default=256, help="任务栈大小 (仅 task 类型)")
    parser.add_argument("--priority", default="Normal", help="任务优先级 (仅 task 类型)")
    parser.add_argument("--delay", type=int, default=100, help="任务延时 (仅 task 类型)")

    return parser


SPI_DRIVER_TEMPLATE = """/**
 * @file    {filename}
 * @brief   {name} SPI 驱动实现
 */

#include "{header}"
#include "spi.h"

/* 接收缓冲区 */
static uint8_t rx_buffer[256];
static volatile uint16_t rx_index = 0;

/* 发送缓冲区 */
static uint8_t tx_buffer[256];

/**
 * @brief  {name} 初始化
 */
void {name_upper}_Init(void)
{{
    /* 初始化已在 MX_{name_upper}_Init() 中完成 */
}}

/**
 * @brief  {name} 发送数据
 * @param  data: 数据指针
 * @param  len: 数据长度
 * @retval HAL 状态
 */
HAL_StatusTypeDef {name_upper}_Send(uint8_t *data, uint16_t len)
{{
    return HAL_SPI_Transmit(&{name_lower}, data, len, 100);
}}

/**
 * @brief  {name} 接收数据
 * @param  data: 数据指针
 * @param  len: 数据长度
 * @retval HAL 状态
 */
HAL_StatusTypeDef {name_upper}_Receive(uint8_t *data, uint16_t len)
{{
    return HAL_SPI_Receive(&{name_lower}, data, len, 100);
}}

/**
 * @brief  {name} 发送接收数据
 * @param  tx_data: 发送数据指针
 * @param  rx_data: 接收数据指针
 * @param  len: 数据长度
 * @retval HAL 状态
 */
HAL_StatusTypeDef {name_upper}_TransmitReceive(uint8_t *tx_data, uint8_t *rx_data, uint16_t len)
{{
    return HAL_SPI_TransmitReceive(&{name_lower}, tx_data, rx_data, len, 100);
}}
"""

SPI_HEADER_TEMPLATE = """/**
 * @file    {filename}
 * @brief   {name} SPI 驱动头文件
 */

#ifndef __{name_upper}_H
#define __{name_upper}_H

#include "main.h"

/* 函数声明 */
void {name_upper}_Init(void);
HAL_StatusTypeDef {name_upper}_Send(uint8_t *data, uint16_t len);
HAL_StatusTypeDef {name_upper}_Receive(uint8_t *data, uint16_t len);
HAL_StatusTypeDef {name_upper}_TransmitReceive(uint8_t *tx_data, uint8_t *rx_data, uint16_t len);

#endif /* __{name_upper}_H */
"""

I2C_DRIVER_TEMPLATE = """/**
 * @file    {filename}
 * @brief   {name} I2C 驱动实现
 */

#include "{header}"
#include "i2c.h"

/**
 * @brief  {name} 初始化
 */
void {name_upper}_Init(void)
{{
    /* 初始化已在 MX_{name_upper}_Init() 中完成 */
}}

/**
 * @brief  {name} 发送数据
 * @param  dev_addr: 设备地址
 * @param  data: 数据指针
 * @param  len: 数据长度
 * @retval HAL 状态
 */
HAL_StatusTypeDef {name_upper}_Send(uint16_t dev_addr, uint8_t *data, uint16_t len)
{{
    return HAL_I2C_Master_Transmit(&{name_lower}, dev_addr, data, len, 100);
}}

/**
 * @brief  {name} 接收数据
 * @param  dev_addr: 设备地址
 * @param  data: 数据指针
 * @param  len: 数据长度
 * @retval HAL 状态
 */
HAL_StatusTypeDef {name_upper}_Receive(uint16_t dev_addr, uint8_t *data, uint16_t len)
{{
    return HAL_I2C_Master_Receive(&{name_lower}, dev_addr, data, len, 100);
}}

/**
 * @brief  {name} 写寄存器
 * @param  dev_addr: 设备地址
 * @param  reg_addr: 寄存器地址
 * @param  data: 数据指针
 * @param  len: 数据长度
 * @retval HAL 状态
 */
HAL_StatusTypeDef {name_upper}_WriteRegister(uint16_t dev_addr, uint16_t reg_addr, uint8_t *data, uint16_t len)
{{
    return HAL_I2C_Mem_Write(&{name_lower}, dev_addr, reg_addr, I2C_MEMADD_SIZE_8BIT, data, len, 100);
}}

/**
 * @brief  {name} 读寄存器
 * @param  dev_addr: 设备地址
 * @param  reg_addr: 寄存器地址
 * @param  data: 数据指针
 * @param  len: 数据长度
 * @retval HAL 状态
 */
HAL_StatusTypeDef {name_upper}_ReadRegister(uint16_t dev_addr, uint16_t reg_addr, uint8_t *data, uint16_t len)
{{
    return HAL_I2C_Mem_Read(&{name_lower}, dev_addr, reg_addr, I2C_MEMADD_SIZE_8BIT, data, len, 100);
}}
"""

I2C_HEADER_TEMPLATE = """/**
 * @file    {filename}
 * @brief   {name} I2C 驱动头文件
 */

#ifndef __{name_upper}_H
#define __{name_upper}_H

#include "main.h"

/* 函数声明 */
void {name_upper}_Init(void);
HAL_StatusTypeDef {name_upper}_Send(uint16_t dev_addr, uint8_t *data, uint16_t len);
HAL_StatusTypeDef {name_upper}_Receive(uint16_t dev_addr, uint8_t *data, uint16_t len);
HAL_StatusTypeDef {name_upper}_WriteRegister(uint16_t dev_addr, uint16_t reg_addr, uint8_t *data, uint16_t len);
HAL_StatusTypeDef {name_upper}_ReadRegister(uint16_t dev_addr, uint16_t reg_addr, uint8_t *data, uint16_t len);

#endif /* __{name_upper}_H */
"""

def generate_spi_code(name: str, output_dir: str) -> None:
    """生成 SPI 驱动代码"""
    name_lower = name.lower()
    name_upper = name.upper()

    # 生成源文件
    filename = f"{name_lower}.c"
    content = SPI_DRIVER_TEMPLATE.format(
        filename=filename,
        name=name,
        name_lower=name_lower,
        name_upper=name_upper,
        header=f"{name_lower}.h"
    )

    output_path = os.path.join(output_dir, filename)
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(content)
    print(f"✅ 生成文件: {filename}")

    # 生成头文件
    filename = f"{name_lower}.h"
    content = SPI_HEADER_TEMPLATE.format(
        filename=filename,
        name=name,
        name_upper=name_upper
    )

    output_path = os.path.join(output_dir, filename)
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(content)
    print(f"✅ 生成文件: {filename}")

def generate_i2c_code(name: str, output_dir: str) -> None:
    """生成 I2C 驱动代码"""
    name_lower = name.lower()
    name_upper = name.upper()

    # 生成源文件
    filename = f"{name_lower}.c"
    content = I2C_DRIVER_TEMPLATE.format(
        filename=filename,
        name=name,
        name_lower=name_lower,
        name_upper=name_upper,
        header=f"{name_lower}.h"
    )

    output_path = os.path.join(output_dir, filename)
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(content)
    print(f"✅ 生成文件: {filename}")

    # 生成头文件
    filename = f"{name_lower}.h"
    content = I2C_HEADER_TEMPLATE.format(
        filename=filename,
        name=name,
        name_upper=name_upper
    )

    output_path = os.path.join(output_dir, filename)
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(content)
    print(f"✅ 生成文件: {filename}")

ADC_DRIVER_TEMPLATE = """/**
 * @file    {filename}
 * @brief   {name} ADC 驱动实现
 */

#include "{header}"
#include "adc.h"

/**
 * @brief  {name} 初始化
 */
void {name_upper}_Init(void)
{{
    /* 初始化已在 MX_{name_upper}_Init() 中完成 */
}}

/**
 * @brief  {name} 读取单次转换
 * @retval ADC 值 (0-4095)
 */
uint16_t {name_upper}_Read(void)
{{
    HAL_ADC_Start(&{name_lower});
    HAL_ADC_PollForConversion(&{name_lower}, 100);
    uint16_t value = HAL_ADC_GetValue(&{name_lower});
    HAL_ADC_Stop(&{name_lower});
    return value;
}}

/**
 * @brief  {name} 读取电压值
 * @retval 电压值 (0-3.3V)
 */
float {name_upper}_ReadVoltage(void)
{{
    uint16_t adc_value = {name_upper}_Read();
    return (float)adc_value * 3.3f / 4095.0f;
}}

/**
 * @brief  {name} 多次采样取平均
 * @param  samples: 采样次数
 * @retval 平均 ADC 值
 */
uint16_t {name_upper}_ReadAverage(uint16_t samples)
{{
    uint32_t sum = 0;
    for (uint16_t i = 0; i < samples; i++)
    {{
        sum += {name_upper}_Read();
    }}
    return (uint16_t)(sum / samples);
}}
"""

ADC_HEADER_TEMPLATE = """/**
 * @file    {filename}
 * @brief   {name} ADC 驱动头文件
 */

#ifndef __{name_upper}_H
#define __{name_upper}_H

#include "main.h"

/* 函数声明 */
void {name_upper}_Init(void);
uint16_t {name_upper}_Read(void);
float {name_upper}_ReadVoltage(void);
uint16_t {name_upper}_ReadAverage(uint16_t samples);

#endif /* __{name_upper}_H */
"""

DAC_DRIVER_TEMPLATE = """/**
 * @file    {filename}
 * @brief   {name} DAC 驱动实现
 */

#include "{header}"
#include "dac.h"

/**
 * @brief  {name} 初始化
 */
void {name_upper}_Init(void)
{{
    /* 初始化已在 MX_{name_upper}_Init() 中完成 */
}}

/**
 * @brief  {name} 设置输出值
 * @param  value: DAC 值 (0-4095)
 */
void {name_upper}_SetValue(uint16_t value)
{{
    if (value > 4095) value = 4095;
    HAL_DAC_SetValue(&{name_lower}, DAC_CHANNEL_1, DAC_ALIGN_12B_R, value);
}}

/**
 * @brief  {name} 设置电压值
 * @param  voltage: 电压值 (0-3.3V)
 */
void {name_upper}_SetVoltage(float voltage)
{{
    if (voltage < 0.0f) voltage = 0.0f;
    if (voltage > 3.3f) voltage = 3.3f;
    uint16_t value = (uint16_t)(voltage * 4095.0f / 3.3f);
    {name_upper}_SetValue(value);
}}

/**
 * @brief  {name} 启动输出
 */
void {name_upper}_Start(void)
{{
    HAL_DAC_Start(&{name_lower}, DAC_CHANNEL_1);
}}

/**
 * @brief  {name} 停止输出
 */
void {name_upper}_Stop(void)
{{
    HAL_DAC_Stop(&{name_lower}, DAC_CHANNEL_1);
}}
"""

DAC_HEADER_TEMPLATE = """/**
 * @file    {filename}
 * @brief   {name} DAC 驱动头文件
 */

#ifndef __{name_upper}_H
#define __{name_upper}_H

#include "main.h"

/* 函数声明 */
void {name_upper}_Init(void);
void {name_upper}_SetValue(uint16_t value);
void {name_upper}_SetVoltage(float voltage);
void {name_upper}_Start(void);
void {name_upper}_Stop(void);

#endif /* __{name_upper}_H */
"""

def generate_adc_code(name: str, output_dir: str) -> None:
    """生成 ADC 驱动代码"""
    name_lower = name.lower()
    name_upper = name.upper()

    # 生成源文件
    filename = f"{name_lower}.c"
    content = ADC_DRIVER_TEMPLATE.format(
        filename=filename,
        name=name,
        name_lower=name_lower,
        name_upper=name_upper,
        header=f"{name_lower}.h"
    )

    output_path = os.path.join(output_dir, filename)
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(content)
    print(f"✅ 生成文件: {filename}")

    # 生成头文件
    filename = f"{name_lower}.h"
    content = ADC_HEADER_TEMPLATE.format(
        filename=filename,
        name=name,
        name_upper=name_upper
    )

    output_path = os.path.join(output_dir, filename)
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(content)
    print(f"✅ 生成文件: {filename}")

def generate_dac_code(name: str, output_dir: str) -> None:
    """生成 DAC 驱动代码"""
    name_lower = name.lower()
    name_upper = name.upper()

    # 生成源文件
    filename = f"{name_lower}.c"
    content = DAC_DRIVER_TEMPLATE.format(
        filename=filename,
        name=name,
        name_lower=name_lower,
        name_upper=name_upper,
        header=f"{name_lower}.h"
    )

    output_path = os.path.join(output_dir, filename)
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(content)
    print(f"✅ 生成文件: {filename}")

    # 生成头文件
    filename = f"{name_lower}.h"
    content = DAC_HEADER_TEMPLATE.format(
        filename=filename,
        name=name,
        name_upper=name_upper
    )

    output_path = os.path.join(output_dir, filename)
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(content)
    print(f"✅ 生成文件: {filename}")

def main() -> int:
    parser = build_parser()
    args = parser.parse_args()

    print(f"🔧 生成代码: {args.type}")
    print(f"   名称: {args.name}")
    print(f"   输出目录: {args.output}")
    print()

    # 确保输出目录存在
    os.makedirs(args.output, exist_ok=True)

    # 生成代码
    if args.type == "uart":
        generate_uart_code(args.name, args.output)
    elif args.type == "task":
        generate_task_code(args.name, args.output, args.stack_size, args.priority, args.delay)
    elif args.type == "gpio":
        if not args.pin or not args.port:
            print("❌ GPIO 类型需要指定 --pin 和 --port")
            return 1
        generate_gpio_code(args.name, args.pin, args.port, args.output)
    elif args.type == "spi":
        generate_spi_code(args.name, args.output)
    elif args.type == "i2c":
        generate_i2c_code(args.name, args.output)
    elif args.type == "adc":
        generate_adc_code(args.name, args.output)
    elif args.type == "dac":
        generate_dac_code(args.name, args.output)

    print()
    print("✅ 代码生成完成")

    return 0


if __name__ == "__main__":
    sys.exit(main())
