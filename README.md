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
| ⚙️ CubeMX 配置 | 开启外设、配置引脚、配置时钟 |
| 📡 串口调试 | 监控串口数据，数据分析，协议解析 |
| 🔄 回归检测 | 对比修改前后的分析结果，检测问题 |
| 🐛 错误追踪 | 记录错误和修复方法，自动匹配相似错误 |
| 📋 技术规范 | 生成项目技术规范文档 |
| 🛡️ 死机预防 | 烧录前检查固件和配置，防止芯片死机 |
| 🤖 AI 工作流 | 遇到错误读错误总结，开发功能读技术规范 |

## 快速开始

### 一键工作流（推荐）

```bash
# 自动检测项目，编译 + 分析 + 优化
python workflow.py --auto .

# 编译 + 分析 + 优化 + 报告
python workflow.py --auto . --steps compile,analyze,optimize,report

# 完整流程（含烧录和串口验证）
python workflow.py --auto . --steps compile,analyze,flash,serial,report --port COM3
```

### 单独使用

```bash
# 编译
UV4.exe -b "project.uvprojx" -t "project_led" -o build.log -j0

# 分析
python check_elf.py --auto .
python debug_sim.py --auto . --mode sim
python optimize.py --auto .

# 烧录
python usb_dfu_flash.py --full --port COM3 --firmware project.hex

# 串口调试
python serial_debug.py --port COM3 --mode analyze --duration 10
```

## 核心脚本

| 脚本 | 功能 | 常用命令 |
|------|------|---------|
| `workflow.py` | **一键工作流** | `--auto . --steps compile,analyze` |
| `shared.py` | **共享模块** | `from shared import find_fromelf, CHIP_DB` |
| `check_elf.py` | ELF 文件检查 | `--auto .` |
| `debug_sim.py` | 静态分析 | `--auto . --mode sim` |
| `optimize.py` | 代码优化分析 | `--auto .` |
| `auto_fix.py` | 编译错误修复 | `--auto . --auto-fix` |
| `renode_sim.py` | Renode 仿真 | `--auto . --mode boot` |
| `serial_debug.py` | **串口调试助手** | `--port COM3 --mode analyze` |
| `serial_monitor.py` | 串口监控 | `--port COM3 --mode monitor` |
| `error_tracker.py` | **错误追踪** | `--record --error "xxx" --fix "xxx"` |
| `error_summary.py` | **错误总结** | `--auto . --text` |
| `tech_spec.py` | **技术规范** | `--auto . --text` |
| `brick_prevention.py` | **死机预防** | `--auto .` |
| `compare.py` | 回归检测 | `--baseline history/v1/ --current history/v2/` |
| `usb_dfu_flash.py` | USB DFU 烧录 | `--full --port COM3 --firmware app.hex` |
| `cubemx_config.py` | CubeMX 配置 | `--modify project.ioc --add-peripheral ADC1` |
| `health_check.py` | 项目健康检查 | `--project . --fix` |
| `code_gen.py` | 代码生成 | `--type uart --name USART1 --output Core/Src` |
| `memory_analyzer.py` | 内存分析 | `--elf project.axf --uv4 D:/k5/UV4/UV4.exe` |
| `pin_checker.py` | 引脚冲突检测 | `--ioc project.ioc` |
| `clock_validator.py` | 时钟配置验证 | `--ioc project.ioc` |
| `peripheral_validator.py` | 外设配置验证 | `--ioc project.ioc` |
| `nvic_checker.py` | NVIC 配置检查 | `--ioc project.ioc` |

## AI 工作流

> **遇到错误时读错误总结，开发功能时读技术规范。**

### 遇到错误时

```bash
# 1. 查错误历史
python error_tracker.py --search "错误关键词" --text

# 2. 获取修复建议
python error_tracker.py --suggest "错误信息" --text

# 3. 修复后记录
python error_tracker.py --record --error "xxx" --fix "xxx" --file main.c
```

### 开发功能时

```bash
# 1. 读技术规范
python tech_spec.py --auto . --text

# 2. 检查外设配置
# 查看技术规范中的"外设详细配置"章节

# 3. 遵循 CubeMX 配置
# 代码适配配置，不修改配置
```

## 死机锁死预防

> **时钟配置绝对不能修改！修改时钟配置会导致系统死机、锁死！**

### 烧录前检查

```bash
# 完整检查（推荐）
python brick_prevention.py --auto .

# 检查时钟配置
python brick_prevention.py --ioc project.ioc --check clock

# 检查固件
python brick_prevention.py --elf project.axf --check firmware
```

### 检查项目

- ✅ 时钟配置（PLL、HSE、SYSCLK）
- ✅ NVIC 优先级配置
- ✅ DMA 冲突检测
- ✅ 固件大小和格式
- ✅ 向量表有效性
- ✅ 栈堆配置
- ✅ 内存重叠检测
- ✅ 读保护状态
- ✅ Flash 写保护状态
- ✅ Option Bytes 配置

## 串口调试

### 数据分析模式

```bash
# 基本分析
python serial_debug.py --port COM3 --mode analyze --duration 10

# 范围检查
python serial_debug.py --port COM3 --mode analyze --duration 10 --min-val 0 --max-val 100

# 跳变检测
python serial_debug.py --port COM3 --mode analyze --duration 10 --jump-threshold 10

# 连续性检查
python serial_debug.py --port COM3 --mode analyze --duration 10 --expected-interval 1
```

### 协议支持

| 协议 | 说明 |
|------|------|
| `text` | 文本命令（自动附加 \r\n） |
| `hex` | HEX 数据包（自动加帧头帧尾） |
| `printf` | 被动监听 printf 输出 |

## 技术规范

### 生成功能

```bash
# 自动模式
python tech_spec.py --auto . --text

# 从 IOC 文件
python tech_spec.py --ioc project.ioc --text

# 输出到文件
python tech_spec.py --auto . --output tech_spec.md
```

### 包含内容

- 项目信息（工具链、Target、优化级别）
- 芯片信息（型号、系列、内核、频率、电压）
- 内存布局（Flash、RAM、CCM）
- 外设配置（USART、I2C、SPI、TIM、ADC、DAC）
- GPIO 配置（引脚、模式、速度、上拉/下拉）
- 时钟配置（时钟树可视化、频率计算）
- NVIC 配置（中断优先级）
- CubeMX 配置指南

## 错误追踪

### 记录错误

```bash
# 记录错误和修复方法
python error_tracker.py --record --error "undefined reference to 'HAL_GPIO_Init'" --fix "添加 #include 'stm32f4xx_hal_gpio.h'" --file main.c
```

### 查询历史

```bash
# 搜索错误
python error_tracker.py --search "undefined reference" --text

# 获取修复建议
python error_tracker.py --suggest "undefined reference to 'xxx'" --text

# 生成统计报告
python error_tracker.py --report --text
```

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
5. **串口调试** - 监控固件输出，数据分析，协议解析
6. **固件烧录** - 支持 ST-LINK 和 USB DFU 两种方式
7. **CubeMX 配置** - 自动化配置外设、引脚、时钟、中断
8. **错误追踪** - 记录错误和修复方法，自动匹配相似错误
9. **技术规范** - 生成项目技术规范文档
10. **死机预防** - 烧录前检查固件和配置，防止芯片死机

## 核心原则

### CubeMX 配置为基准

> **CubeMX 生成的配置文件是项目基准，代码必须适配配置，而不是反过来。**

- 不修改 CubeMX 生成的 `MX_*` 函数
- 代码适配配置，不修改配置
- 配置错误在 CubeMX 中修改

### 时钟配置保护

> **时钟配置绝对不能修改！修改时钟配置会导致系统死机、锁死！**

- 不修改 PLL 配置
- 不修改 HSE/HSI 配置
- 不修改 SYSCLK 源
- 不修改 AHB/APB 分频

## 注意事项

- 编译错误修复遵循**最小改动原则**
- 烧录前必须先进行**静态分析验证**
- 不会执行全片擦除或修改 Option Bytes
- 支持 VOFA+ 等串口协议解析
- 时钟配置绝对不能修改

## 许可证

MIT License
