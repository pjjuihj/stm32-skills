#!/usr/bin/env python
"""CubeMX 交互式配置助手。

提供详细的 CubeMX 配置步骤指导，帮助用户正确配置外设。

使用示例：
  python cubemx_guide.py --project my_project
  python cubemx_guide.py --project my_project --peripheral ADC1
  python cubemx_guide.py --project my_project --list
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

# 编码处理
if sys.stdout and hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

# ======================== 配置指南 ========================

PROJECT_CREATION_GUIDE = """
========================================
  CubeMX 项目创建指南
========================================

步骤 1：启动 CubeMX
  - 双击 STM32CubeMX 图标
  - 或从开始菜单启动

步骤 2：新建项目
  - 点击 File → New Project
  - 在搜索框输入：STM32F407VETx
  - 选择 LQFP100 封装
  - 点击 Start Project

步骤 3：确认芯片信息
  - 型号：STM32F407VETx
  - Flash：512 KB
  - RAM：128 KB
  - 主频：168 MHz
"""

PIN_CONFIGURATION_GUIDE = """
========================================
  引脚配置指南
========================================

ADC 引脚（PA6）：
  1. 找到芯片图上的 PA6
  2. 左键点击 → 选择 ADC1_IN6
  3. 设置参数：
     - GPIO mode：ADC1_IN6
     - Pull-up/Pull-down：No pull-up and no pull-down
     - User Label：SCOPE_IN

DAC 引脚（PA4）：
  1. 找到芯片图上的 PA4
  2. 左键点击 → 选择 DAC_OUT1
  3. 设置参数：
     - GPIO mode：DAC_OUT1
     - User Label：SIGGEN_OUT

USART2 引脚（PA2/PA3）：
  PA2：USART2_TX
  PA3：USART2_RX
  模式：Asynchronous

I2C1 引脚（PB6/PB7）：
  PB6：I2C1_SCL
  PB7：I2C1_SDA
  模式：I2C

调试引脚（PA13/PA14）：
  PA13：SYS_JTMS-SWDIO
  PA14：SYS_JTCK-SWCLK
  模式：Serial_Wire
"""

CLOCK_CONFIGURATION_GUIDE = """
========================================
  时钟配置指南
========================================

步骤 1：进入时钟配置页面
  - 点击左侧 "Clock Configuration" 标签

步骤 2：配置时钟树
  1. HSE 选择：Crystal/Ceramic Resonator
  2. PLL 配置：
     - PLL Source：HSE
     - PLLM：8
     - PLLN：336
     - PLLP：2
  3. 系统时钟：PLLCLK
  4. AHB 分频：/1 → 168 MHz
  5. APB1 分频：/4 → 42 MHz
  6. APB2 分频：/2 → 84 MHz

时钟参数表：
  HSE：8 MHz（外部晶振）
  PLLM：8（PLL 输入分频）
  PLLN：336（PLL 倍频）
  PLLP：2（PLL 输出分频）
  SYSCLK：168 MHz（系统时钟）
  AHB：168 MHz（AHB 总线）
  APB1：42 MHz（APB1 总线）
  APB2：84 MHz（APB2 总线）
"""

ADC_CONFIGURATION_GUIDE = """
========================================
  ADC1 配置指南
========================================

步骤 1：进入 ADC 配置页面
  - 点击左侧 Analog → ADC1

步骤 2：基本设置
  Mode：Independent mode（单通道）
  Resolution：12 Bits
  Data Alignment：Right alignment
  Scan Conversion Mode：Disabled
  Continuous Conversion Mode：Disabled
  Discontinuous Conversion Mode：Disabled
  Number of Conversion：1

步骤 3：通道配置（Rank 1）
  Channel：IN6
  Sampling Time：84 Cycles

步骤 4：触发配置
  External Trigger Conversion Source：Timer 9 Trigger Out Event
  External Trigger Conversion Edge：Rising Edge

ADC 采样时间选择：
  3 Cycles：最快，精度低
  15 Cycles：常用
  28 Cycles：中等
  56 Cycles：较高精度
  84 Cycles：高精度（推荐）
  112 Cycles：很高精度
  144 Cycles：很高精度
  480 Cycles：最高精度
"""

DAC_CONFIGURATION_GUIDE = """
========================================
  DAC 配置指南
========================================

步骤 1：进入 DAC 配置页面
  - 点击左侧 Analog → DAC

步骤 2：基本设置
  DAC Out1 Output Buffer：Enable
  Trigger：Timer 5 Trigger Out Event
  Wave Generation Mode：Disabled

DAC 输出缓冲：
  Enable：增加驱动能力，推荐开启
  Disable：降低功耗，驱动能力弱

DAC 触发源：
  Timer 5 Trigger Out Event：用于波形输出
  Software Trigger：软件触发
"""

USART_CONFIGURATION_GUIDE = """
========================================
  USART2 配置指南
========================================

步骤 1：进入 USART 配置页面
  - 点击左侧 Connectivity → USART2

步骤 2：基本设置
  Mode：Asynchronous
  Baud Rate：115200 Bits/s
  Word Length：8 Bits
  Stop Bits：1
  Parity：None
  Data Direction：Receive and Transmit
  Over Sampling：16 Samples

波特率选择：
  9600：低速，抗干扰强
  19200：低速
  38400：中速
  57600：中速
  115200：常用（推荐）
  230400：高速
  460800：高速
  921600：高速
"""

I2C_CONFIGURATION_GUIDE = """
========================================
  I2C1 配置指南
========================================

步骤 1：进入 I2C 配置页面
  - 点击左侧 Connectivity → I2C1

步骤 2：基本设置
  Mode：I2C
  Clock Speed：400000 Hz
  Duty Cycle：Duty Cycle 2
  Own Address 1：0
  Addressing Mode：7-bit
  Dual Address Mode：Disabled
  General Call Mode：Disabled
  No Stretch Mode：Disabled

I2C 速度选择：
  100000 Hz（100kHz）：标准模式
  400000 Hz（400kHz）：快速模式（推荐）
  1000000 Hz（1MHz）：高速模式
"""

TIM5_CONFIGURATION_GUIDE = """
========================================
  TIM5 配置指南（DAC 触发）
========================================

步骤 1：进入定时器配置页面
  - 点击左侧 Timers → TIM5

步骤 2：基本设置
  Clock Source：Internal Clock
  Channel1：Disabled
  Prescaler：84-1
  Counter Mode：Up
  Counter Period：2000-1
  Internal Clock Division：No Division
  auto-reload preload：Enable

步骤 3：触发输出
  Trigger Event Selection：Update Event

定时器计算：
  定时器时钟 = APB1 时钟 × 2 = 84 MHz
  预分频 = 84-1 → 1 MHz
  周期 = 2000-1 → 500 Hz
  触发频率 = 1 MHz / 2000 = 500 Hz
"""

TIM9_CONFIGURATION_GUIDE = """
========================================
  TIM9 配置指南（ADC 触发）
========================================

步骤 1：进入定时器配置页面
  - 点击左侧 Timers → TIM9

步骤 2：基本设置
  Clock Source：Internal Clock
  Channel1：Disabled
  Prescaler：84-1
  Counter Mode：Up
  Counter Period：1000-1
  Internal Clock Division：No Division
  auto-reload preload：Enable

步骤 3：触发输出
  Trigger Event Selection：Update Event

定时器计算：
  定时器时钟 = APB2 时钟 = 84 MHz
  预分频 = 84-1 → 1 MHz
  周期 = 1000-1 → 1 kHz
  触发频率 = 1 MHz / 1000 = 1 kHz
"""

NVIC_CONFIGURATION_GUIDE = """
========================================
  NVIC 配置指南
========================================

步骤 1：进入 NVIC 配置页面
  - 点击左侧 NVIC 标签

步骤 2：配置中断优先级

  中断名称                    优先级    子优先级    使能
  ─────────────────────────────────────────────────
  TIM5_IRQn                   6        0          ✅
  TIM1_BRK_TIM9_IRQn          6        0          ✅
  USART2_IRQn                 5        0          ✅
  I2C1_ER_IRQn                5        0          ✅
  I2C1_EV_IRQn                5        0          ✅

优先级说明：
  优先级 0：最高（系统异常）
  优先级 5：通信（UART、I2C）
  优先级 6：定时器（TIM）
  优先级 15：最低（SysTick）

注意：
  - 数值越小，优先级越高
  - 相同优先级不能嵌套
  - 中断服务函数中不要使用 HAL_Delay
"""

PROJECT_MANAGER_GUIDE = """
========================================
  项目管理配置指南
========================================

步骤 1：进入项目管理页面
  - 点击左侧 Project Manager 标签

步骤 2：项目设置
  Project Name：my_project
  Project Location：选择保存路径
  Toolchain/IDE：MDK-ARM V5

步骤 3：代码生成设置
  ✅ Copy all used libraries into the project folder
  ✅ Generate peripheral initialization as a pair of '.c/.h' files
  ✅ Keep User Code when re-generating
  ✅ Delete previously generated files when not re-generated

步骤 4：高级设置
  ✅ Generate a function to initialize the MSP (HAL_Init)
  ✅ Assert enabled
"""

CODE_GENERATION_GUIDE = """
========================================
  代码生成指南
========================================

步骤 1：生成代码
  - 点击 "GENERATE CODE" 按钮
  - 等待生成完成

步骤 2：生成的文件结构
  project_led/
  ├── Core/
  │   ├── Inc/          # 头文件
  │   │   ├── main.h
  │   │   ├── adc.h
  │   │   ├── dac.h
  │   │   ├── tim.h
  │   │   ├── usart.h
  │   │   └── i2c.h
  │   └── Src/          # 源文件
  │       ├── main.c
  │       ├── adc.c
  │       ├── dac.c
  │       ├── tim.c
  │       ├── usart.c
  │       └── i2c.c
  ├── Drivers/          # HAL 库
  └── MDK-ARM/          # Keil 工程

步骤 3：在 USER CODE 区域编写代码

  /* USER CODE BEGIN Includes */
  #include "your_header.h"
  /* USER CODE END Includes */

  /* USER CODE BEGIN 2 */
  // 初始化代码
  /* USER CODE END 2 */

  /* USER CODE BEGIN 3 */
  // 主循环代码
  /* USER CODE END 3 */
"""

TROUBLESHOOTING_GUIDE = """
========================================
  常见问题排查
========================================

Q1：引脚冲突怎么办？
  A1：检查 Pinout 视图中的红色标记
      重新分配冲突引脚
      参考芯片数据手册确认引脚功能

Q2：时钟配置错误？
  A2：检查 HSE 晶振频率（通常 8MHz）
      验证 PLL 参数
      确保 APB 总线频率不超限

Q3：生成代码后编译失败？
  A3：检查 Include 路径
      验证 HAL 库版本
      检查启动文件是否存在

Q4：如何修改已生成的配置？
  A4：重新打开 .ioc 文件
      在 CubeMX 中修改配置
      重新生成代码
      保留 USER CODE 区域的代码

Q5：NVIC 优先级配置错误？
  A5：检查 NVIC 配置页面
      确保中断优先级不冲突
      验证中断服务函数名称

Q6：I2C 通信失败？
  A6：检查上拉电阻（4.7kΩ）
      验证 I2C 地址
      检查时钟配置
"""

# ======================== 外设配置映射 ========================

PERIPHERAL_GUIDES = {
    "ADC1": ADC_CONFIGURATION_GUIDE,
    "DAC": DAC_CONFIGURATION_GUIDE,
    "USART2": USART_CONFIGURATION_GUIDE,
    "I2C1": I2C_CONFIGURATION_GUIDE,
    "TIM5": TIM5_CONFIGURATION_GUIDE,
    "TIM9": TIM9_CONFIGURATION_GUIDE,
}

# ======================== 项目模板 ========================

PROJECT_TEMPLATES = {
    "scope_siggen": {
        "name": "串口示波器 + 信号发生器",
        "peripherals": ["ADC1", "DAC", "USART2", "I2C1", "TIM5", "TIM9"],
        "guide": "scope_siggen",
    },
    "basic_gpio": {
        "name": "基础 GPIO 配置",
        "peripherals": ["GPIO"],
        "guide": "basic_gpio",
    },
    "uart_comm": {
        "name": "UART 通信配置",
        "peripherals": ["USART1", "USART2"],
        "guide": "uart_comm",
    },
}

# ======================== 辅助函数 ========================

def print_section(title: str) -> None:
    """打印章节标题"""
    print()
    print("=" * 50)
    print(f"  {title}")
    print("=" * 50)

def print_guide(guide: str) -> None:
    """打印配置指南"""
    print(guide)

def list_peripherals() -> None:
    """列出所有可用的外设配置指南"""
    print_section("可用的外设配置指南")
    print()
    for name, guide in PERIPHERAL_GUIDES.items():
        print(f"  {name:10} - 外设配置指南")
    print()
    print("使用方法：python cubemx_guide.py --peripheral <外设名>")

def list_templates() -> None:
    """列出所有项目模板"""
    print_section("可用的项目模板")
    print()
    for name, template in PROJECT_TEMPLATES.items():
        print(f"  {name:15} - {template['name']}")
        print(f"                外设：{', '.join(template['peripherals'])}")
    print()

def show_full_guide() -> None:
    """显示完整配置指南"""
    print_section("CubeMX 完整配置指南")
    print()
    print("配置顺序：")
    print("  1. 项目创建")
    print("  2. 芯片选型")
    print("  3. 引脚配置")
    print("  4. 时钟配置")
    print("  5. 外设配置")
    print("  6. NVIC 配置")
    print("  7. 项目管理")
    print("  8. 代码生成")
    print()
    print_guide(PROJECT_CREATION_GUIDE)
    print_guide(PIN_CONFIGURATION_GUIDE)
    print_guide(CLOCK_CONFIGURATION_GUIDE)
    print_guide(ADC_CONFIGURATION_GUIDE)
    print_guide(DAC_CONFIGURATION_GUIDE)
    print_guide(USART_CONFIGURATION_GUIDE)
    print_guide(I2C_CONFIGURATION_GUIDE)
    print_guide(TIM5_CONFIGURATION_GUIDE)
    print_guide(TIM9_CONFIGURATION_GUIDE)
    print_guide(NVIC_CONFIGURATION_GUIDE)
    print_guide(PROJECT_MANAGER_GUIDE)
    print_guide(CODE_GENERATION_GUIDE)
    print_guide(TROUBLESHOOTING_GUIDE)

def show_peripheral_guide(peripheral: str) -> None:
    """显示指定外设的配置指南"""
    if peripheral in PERIPHERAL_GUIDES:
        print_guide(PERIPHERAL_GUIDES[peripheral])
    else:
        print(f"❌ 未找到外设 '{peripheral}' 的配置指南")
        print("可用的外设：")
        for name in PERIPHERAL_GUIDES.keys():
            print(f"  - {name}")

# ======================== 主函数 ========================

def build_parser() -> argparse.ArgumentParser:
    """构建命令行参数解析器"""
    parser = argparse.ArgumentParser(
        description="CubeMX 交互式配置助手",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例：
  %(prog)s                                    # 显示完整配置指南
  %(prog)s --list                             # 列出所有外设
  %(prog)s --peripheral ADC1                  # 显示 ADC1 配置指南
  %(prog)s --template scope_siggen            # 显示项目模板指南
        """,
    )

    parser.add_argument("--list", action="store_true",
                        help="列出所有可用的外设配置指南")
    parser.add_argument("--peripheral", type=str,
                        help="显示指定外设的配置指南")
    parser.add_argument("--template", type=str,
                        help="显示指定项目模板的配置指南")
    parser.add_argument("--full", action="store_true",
                        help="显示完整配置指南")

    return parser

def main() -> int:
    parser = build_parser()
    args = parser.parse_args()

    # 如果没有参数，显示完整指南
    if not args.list and not args.peripheral and not args.template and not args.full:
        show_full_guide()
        return 0

    if args.list:
        list_peripherals()
        return 0

    if args.peripheral:
        show_peripheral_guide(args.peripheral)
        return 0

    if args.template:
        if args.template in PROJECT_TEMPLATES:
            template = PROJECT_TEMPLATES[args.template]
            print_section(f"项目模板：{template['name']}")
            print(f"外设：{', '.join(template['peripherals'])}")
            print()
            # 显示相关外设的配置指南
            for peripheral in template['peripherals']:
                if peripheral in PERIPHERAL_GUIDES:
                    print_guide(PERIPHERAL_GUIDES[peripheral])
        else:
            print(f"❌ 未找到模板 '{args.template}'")
            list_templates()
        return 0

    if args.full:
        show_full_guide()
        return 0

    return 0

if __name__ == "__main__":
    sys.exit(main())
