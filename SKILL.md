---
name: stm32-keil-workflow
description: >
  STM32 firmware development automation for Keil MDK-ARM projects. Handles compilation, static analysis,
  optimization, simulation, flashing (ST-LINK/USB DFU), CubeMX configuration, serial monitoring, and
  regression detection. Use this skill when working with STM32 microcontrollers (F0/F1/F2/F3/F4/F7/H7),
  Keil uVision projects (.uvprojx), Cortex-M development, FreeRTOS, STM32CubeMX, or embedded firmware.
  Triggers on: STM32 compile/build/flash/debug, firmware analysis, code optimization, serial port testing,
  CubeMX configuration, .uvprojx projects, ST-LINK/SWD, USB DFU, ELF/AXF analysis, "full analysis",
  "add task", "configure peripheral", ADC/DAC, I2C/SPI/UART, PWM, encoder, motor control.
  Also handles: STM32 project initialization, health checks, code generation, memory analysis,
  pin conflict detection, clock validation, peripheral validation, NVIC configuration.
---

# STM32 Keil Workflow

STM32 固件开发全流程自动化：编译 → 分析 → 优化 → 仿真 → 烧录 → 验证

## 快速参考

### 一行命令

```bash
# 编译
UV4.exe -b "project.uvprojx" -t "project_led" -o build.log -j0

# 完整分析
python check_elf.py --elf project.axf --uv4 D:/k5/UV4/UV4.exe
python debug_sim.py --elf project.axf --mode sim --uv4 D:/k5/UV4/UV4.exe
python optimize.py --elf project.axf --uv4 D:/k5/UV4/UV4.exe --project project.uvprojx

# USB DFU 烧录
python usb_dfu_flash.py --full --port COM3 --firmware project.hex

# CubeMX 配置
python cubemx_config.py --modify project.ioc --config-scope --channel 6
```

### 核心流程

```
① 编译 → ② 静态分析 → ③ 优化分析 → ④ 仿真 → ⑤ 烧录 → ⑥ 串口验证
     ↑          ↓
     └── 修复 ←─┘
```

## 工具脚本

| 脚本 | 功能 | 常用命令 |
|------|------|---------|
| `check_elf.py` | ELF 检查 | `--elf project.axf --uv4 D:/k5/UV4/UV4.exe` |
| `debug_sim.py` | 静态分析 | `--elf project.axf --mode sim --uv4 D:/k5/UV4/UV4.exe` |
| `optimize.py` | 优化分析 | `--elf project.axf --uv4 D:/k5/UV4/UV4.exe --project project.uvprojx` |
| `renode_sim.py` | Renode 仿真 | `--elf project.axf --mode boot --timeout 5` |
| `serial_monitor.py` | 串口监控 | `--port COM3 --baud 115200 --mode monitor --duration 10` |
| `compare.py` | 回归检测 | `--baseline history/v1/ --current history/v2/ --report diff.md` |
| `usb_dfu_flash.py` | USB DFU 烧录 | `--full --port COM3 --firmware app.hex` |
| `cubemx_config.py` | CubeMX 配置 | `--modify project.ioc --config-scope --channel 6` |
| `auto_fix.py` | 编译错误修复 | `--log build.log --project . --auto-fix` |
| `project_init.py` | 项目初始化 | `--name my_project --mcu STM32F407VETx` |
| `health_check.py` | 项目健康检查 | `--project . --fix` |
| `code_gen.py` | 代码生成 | `--type uart --name USART1 --output Core/Src` |
| `memory_analyzer.py` | 内存分析 | `--elf project.axf --uv4 D:/k5/UV4/UV4.exe` |
| `pin_checker.py` | 引脚冲突检测 | `--ioc project.ioc` |
| `clock_validator.py` | 时钟配置验证 | `--ioc project.ioc` |
| `peripheral_validator.py` | 外设配置验证 | `--ioc project.ioc` |
| `nvic_checker.py` | NVIC 配置检查 | `--ioc project.ioc` |

## 编译流程

```bash
cd <MDK-ARM目录> && UV4.exe -b <.uvprojx> -t <Target> -o build.log -j0
```

**成功**：返回码 0，进入静态分析  
**失败**：解析 build.log，修复错误，重新编译

### 编译错误处理

| 错误类型 | 修复方式 |
|---------|---------|
| `undefined reference` | 添加头文件/声明/链接 |
| `undeclared identifier` | 添加声明/修复拼写 |
| `file not found` | 检查文件路径和 include 路径 |
| `type mismatch` | 类型转换/修复签名 |

## 静态分析

```bash
python check_elf.py --elf project.axf --uv4 D:/k5/UV4/UV4.exe --symbols "main,HAL_Init"
python debug_sim.py --elf project.axf --mode sim --uv4 D:/k5/UV4/UV4.exe
```

**检查项**：中断向量表、栈堆大小、关键符号、段大小

## 优化分析

```bash
python optimize.py --elf project.axf --uv4 D:/k5/UV4/UV4.exe --project project.uvprojx --src-dir ../Core/Src
```

**分析维度**：Flash/RAM 使用率、Top-20 最大函数、编译器设置、代码质量

## Renode 仿真

```bash
python renode_sim.py --elf project.axf --mode boot --timeout 5
python renode_sim.py --elf project.axf --mode uart --timeout 10
```

**验证项**：固件启动、UART 输出、无 HardFault

## 烧录流程

### ST-LINK 烧录

```bash
UV4.exe -f project.uvprojx -t project_led -o flash.log
# 或
STM32_Programmer_CLI.exe -c port=SWD mode=UR freq=4000 -w project.axf -v -rst
```

### USB DFU 烧录

```bash
# 检测设备
python usb_dfu_flash.py --detect

# 进入 DFU 模式
python usb_dfu_flash.py --enter-dfu --port COM3

# 完整流程
python usb_dfu_flash.py --full --port COM3 --firmware project.hex
```

**安全约束**：不全片擦除、不写 Option Bytes、不改读保护

## CubeMX 配置

### 能力说明

| 功能 | 状态 | 命令 |
|------|------|------|
| **开启外设** | ✅ 可用 | `--add-peripheral ADC1` |
| **配置引脚** | ✅ 可用 | `--add-pin PA6 ADC1_IN6` |
| **配置时钟** | ✅ 可用 | `--set-clock --hse 8 --sysclk 168` |
| **配置 GPIO** | ✅ 可用 | `--config-gpio --gpio-pin PA8 --gpio-mode Output` |
| **配置 NVIC** | ✅ 可用 | `--config-nvic --irq USART1_IRQn --nvic-priority 5` |
| **添加任务** | ✅ 可用 | `--add-task --name MyTask --stack 256` |
| **外设参数** | ⚠️ 部分 | 需要在 CubeMX 中手动配置 |

### 使用方法

```bash
# 1. 开启外设和配置引脚
python cubemx_config.py --modify project.ioc --add-peripheral ADC1 --add-pin PA6 ADC1_IN6

# 2. 配置时钟
python cubemx_config.py --modify project.ioc --set-clock --hse 8 --sysclk 168

# 3. 配置 GPIO
python cubemx_config.py --modify project.ioc --config-gpio --gpio-pin PA8 --gpio-mode Output --gpio-label LED

# 4. 配置 NVIC
python cubemx_config.py --modify project.ioc --config-nvic --irq USART1_IRQn --nvic-priority 5

# 5. 添加 FreeRTOS 任务
python cubemx_config.py --modify project.ioc --add-task --name SensorTask --stack 256 --priority High

# 6. 在 CubeMX 中配置外设详细参数
#    打开 CubeMX → 配置 ADC、DAC、USART 等

# 7. 生成代码
python cubemx_config.py --generate project.ioc --toolchain "MDK-ARM V5"
```

### 详细配置命令（部分支持）

| 配置类型 | 命令示例 | 说明 |
|---------|---------|------|
| **ADC** | `--config-adc --channel 6` | 基本配置，详细参数需在 CubeMX 中设置 |
| **DAC** | `--config-dac --dac-channel 1` | 基本配置 |
| **USART** | `--config-usart --baudrate 115200` | 基本配置，格式可能不完美 |
| **I2C** | `--config-i2c --speed 400000` | 基本配置 |
| **TIM** | `--config-tim --prescaler 84 --period 1000` | 基本配置 |
| **GPIO** | `--config-gpio --gpio-pin PA8 --gpio-mode Output` | 完整配置 |
| **NVIC** | `--config-nvic --irq USART1_IRQn --nvic-priority 5` | 完整配置 |

### 限制

| 限制 | 说明 |
|------|------|
| **外设参数** | 无法配置 CubeMX 接受的详细参数格式 |
| **DMA** | 无法配置详细 DMA 参数 |
| **中间件** | 无法配置 FreeRTOS、FatFS 等高级配置 |

### 推荐工作流程

```
1. 用 cubemx_config.py 开启外设和配置引脚（脚本完成）
2. 用 CubeMX 手动配置外设详细参数（手动完成）
3. 用 cubemx_config.py 生成代码（脚本完成）
```

### 配置模板

| 模板 | 说明 |
|------|------|
| `templates/basic_gpio.json` | LED + 按键 |
| `templates/uart_comm.json` | 双串口通信 |
| `templates/i2c_sensor.json` | I2C 传感器 |
| `templates/pwm_motor.json` | PWM 电机控制 |
| `templates/adc_dma.json` | ADC DMA 采集 |
| `templates/freertos_basic.json` | FreeRTOS 基础任务 |
| `templates/scope_siggen.json` | 串口示波器 + 信号发生器 |
| `templates/encoder_motor.json` | 编码器 + 电机控制 |
| `templates/sensor_logger.json` | 传感器数据记录器 |
| `templates/freertos_config.h` | FreeRTOS 配置文件模板 |
| `templates/bootloader/` | USB DFU Bootloader 模板 |

## 串口验证

```bash
# 列出串口
python serial_monitor.py --list

# 数据监听
python serial_monitor.py --port COM3 --baud 115200 --mode monitor --duration 10

# 命令发送
python serial_monitor.py --port COM3 --baud 115200 --mode send --send "T\r" --wait 2

# VOFA+ 协议解析
python serial_monitor.py --port COM3 --baud 115200 --mode parse --protocol vofa-firewater --duration 10
```

## 回归检测

```bash
# 保存快照
python compare.py --save --history-dir history/ --elf-data check_elf.json --sim-data debug_sim.json

# 对比快照
python compare.py --baseline history/v1/ --current history/v2/ --report diff.md

# 分析趋势
python compare.py --trend --history-dir history/ --report trend.md
```

## 一键全自动流程

```bash
# 编译
UV4.exe -b project.uvprojx -t project_led -o build.log -j0

# 分析
python check_elf.py --elf project.axf --uv4 D:/k5/UV4/UV4.exe --symbols "main,HAL_Init"
python debug_sim.py --elf project.axf --mode sim --uv4 D:/k5/UV4/UV4.exe
python optimize.py --elf project.axf --uv4 D:/k5/UV4/UV4.exe --project project.uvprojx

# 仿真（可选）
python renode_sim.py --elf project.axf --mode boot --timeout 5

# 烧录（需确认）
python usb_dfu_flash.py --full --port COM3 --firmware project.hex
```

## 调试排查

| 问题 | 排查方法 |
|------|---------|
| ST-LINK 连接失败 | 检查是否有其他程序占用、检查 USB 连接 |
| 固件不运行 | 检查栈溢出、中断向量表、时钟配置 |
| 串口无响应 | 确认 COM 口和波特率、检查 TX/RX 接线 |
| I2C/SPI 通信失败 | 检查上拉电阻、时钟配置、地址设置 |

## 项目记忆

首次使用时，读取项目配置：
- `.vscode/c_cpp_properties.json`：include 路径和宏定义
- `*.uvprojx`：工程文件路径、Target 名称
- `*.ioc`：CubeMX 配置

## 依赖

| 依赖 | 必需 | 说明 |
|------|------|------|
| Python 3.8+ | ✅ | 运行脚本 |
| Keil MDK-ARM | ✅ | 编译工具链 |
| STM32CubeProgrammer | ⚠️ | 烧录工具 |
| Renode | ⚠️ | 无硬件仿真 |
| STM32CubeMX | ⚠️ | 代码生成 |
| pyserial | ⚠️ | 串口通信 |

## 安全约束

- **不全片擦除**（不使用 `-e` 标志）
- **不写 Option Bytes**
- **不改读保护**（RDP）
- **不在用户未确认的情况下烧录到硬件**
- **编译错误修复遵循最小改动原则**
