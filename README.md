# STM32 Keil Workflow

STM32 固件开发全流程自动化技能

## 功能特性

| 功能 | 说明 |
|------|------|
| 🔨 编译 | 自动编译 Keil 项目，解析并修复编译错误 |
| 📊 静态分析 | 检查 ELF 文件、中断向量表、栈堆大小 |
| ⚡ 代码优化 | 分析 Flash/RAM 使用率，给出优化建议 |
| 🎮 Renode 仿真 | 无硬件仿真验证固件启动和 UART 输出 |
| 🔥 烧录 | 支持 ST-LINK 和 USB DFU 两种方式 |
| ⚙️ CubeMX 配置 | 自动化配置 .ioc 文件，生成初始化代码 |
| 📡 串口验证 | 监控串口数据，验证固件运行 |
| 🔄 回归检测 | 对比修改前后的分析结果，检测问题 |

## 快速开始

### 编译

```bash
UV4.exe -b "project.uvprojx" -t "project_led" -o build.log -j0
```

### 分析

```bash
python check_elf.py --elf project.axf --uv4 D:/k5/UV4/UV4.exe
python debug_sim.py --elf project.axf --mode sim --uv4 D:/k5/UV4/UV4.exe
python optimize.py --elf project.axf --uv4 D:/k5/UV4/UV4.exe --project project.uvprojx
```

### 烧录

```bash
# ST-LINK
UV4.exe -f project.uvprojx -t project_led -o flash.log

# USB DFU
python usb_dfu_flash.py --full --port COM3 --firmware project.hex
```

### CubeMX 配置

```bash
# 一键配置示波器+信号发生器
python cubemx_config.py --modify project.ioc --config-scope --channel 6

# 生成代码
python cubemx_config.py --generate project.ioc --toolchain "MDK-ARM V5"
```

### 串口验证

```bash
python serial_monitor.py --port COM3 --baud 115200 --mode monitor --duration 10
```

## 脚本说明

| 脚本 | 功能 | 常用命令 |
|------|------|---------|
| `check_elf.py` | ELF 文件检查 | `--elf project.axf --uv4 D:/k5/UV4/UV4.exe` |
| `debug_sim.py` | 静态分析 | `--elf project.axf --mode sim --uv4 D:/k5/UV4/UV4.exe` |
| `optimize.py` | 代码优化分析 | `--elf project.axf --uv4 D:/k5/UV4/UV4.exe --project project.uvprojx` |
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

## 配置模板

| 模板 | 说明 |
|------|------|
| `basic_gpio.json` | LED 输出 + 按键输入 |
| `uart_comm.json` | USART1 + USART2 双串口 |
| `i2c_sensor.json` | I2C1 + I2C2 双总线 |
| `pwm_motor.json` | TIM3 双通道 PWM |
| `adc_dma.json` | ADC1 单通道采集 |
| `freertos_basic.json` | FreeRTOS 基础任务配置 |

## 安装依赖

### 必需
- Python 3.8+
- Keil MDK-ARM (UV4.exe)

### 可选
- [STM32CubeProgrammer](https://www.st.com/en/development-tools/stm32cubeprog.html) - 烧录工具
- [Renode](https://renode.io/) - 无硬件仿真
- [STM32CubeMX](https://www.st.com/en/development-tools/stm32cubemx.html) - 代码生成
- pyserial - 串口通信 (`pip install pyserial`)

## 使用场景

1. **新项目验证** - 编译后自动检查固件正确性
2. **代码优化** - 分析 Flash/RAM 使用率，找出大函数
3. **问题排查** - 静态分析检查中断向量表、栈堆配置
4. **回归测试** - 修改代码后对比分析结果
5. **串口调试** - 监控固件输出，验证功能
6. **固件烧录** - 支持 ST-LINK 和 USB DFU 两种方式
7. **CubeMX 配置** - 自动化配置外设、引脚、时钟、中断

## 注意事项

- 编译错误修复遵循**最小改动原则**
- 烧录前必须先进行**静态分析验证**
- 不会执行全片擦除或修改 Option Bytes
- 支持 VOFA+ 等串口协议解析

## 许可证

MIT License
