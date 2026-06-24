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

## 快速开始（推荐）

### 一键工作流

```bash
# 自动检测项目，编译 + 分析 + 优化（最常用）
python workflow.py --auto .

# 只编译（失败自动修复，最多 3 轮）
python workflow.py --auto . --steps compile

# 编译 + 分析
python workflow.py --auto . --steps compile,analyze

# 全流程 + 烧录
python workflow.py --auto . --steps compile,analyze,flash --port COM3

# 健康检查
python workflow.py --auto . --steps health

# 死机锁死预防检查
python workflow.py --auto . --steps brick_check

# 可用步骤: compile, analyze, optimize, simulate, flash, serial, health, report, brick_check
```

`--auto .` 会自动检测 `.uvprojx` 项目文件、`.axf` 编译产物、UV4.exe 路径，无需手动指定任何参数。

### 核心脚本支持 --auto

```bash
python check_elf.py --auto .                    # 自动检测 ELF 并检查
python debug_sim.py --auto . --mode sim         # 自动检测并静态分析
python optimize.py --auto .                     # 自动检测并优化分析
python auto_fix.py --auto . --auto-fix          # 自动查找 build.log 并修复
python renode_sim.py --auto . --mode boot       # 自动检测并仿真
python serial_monitor.py --auto .               # 列出串口并显示项目信息
```

> `--auto` 会自动检测 `.uvprojx`、`.axf`、UV4.exe 等路径。仅分析类脚本支持，配置类脚本（cubemx_config、pin_checker 等）需要手动指定 `--ioc`。

## 核心流程

```
① 编译 → ② 静态分析 → ③ 优化分析 → ④ 仿真 → ⑤ 烧录 → ⑥ 串口验证 → ⑦ 报告生成
     ↑          ↓                                                    ↓
     └── 修复 ←─┘                                    error_summary + tech_spec
```

### 一键工作流

```bash
# 全流程（编译 → 分析 → 优化 → 报告）
python workflow.py --auto . --steps compile,analyze,optimize,report

# 完整流程（含烧录和串口验证）
python workflow.py --auto . --steps compile,analyze,optimize,flash,serial,report --port COM3

# 只编译
python workflow.py --auto . --steps compile

# 只分析（已编译过）
python workflow.py --auto . --steps analyze,optimize,report

# 串口验证（带测试命令）
python workflow.py --auto . --steps serial --port COM3 --serial-cmd "@LED_ON,@LED_OFF,@STATUS"

# 串口验证（带批量命令文件）
python workflow.py --auto . --steps serial --port COM3 --serial-batch commands.txt
```

### 脚本联动

```bash
# 1. 运行工作流（自动生成 workflow_result.json）
python workflow.py --auto . --steps compile,analyze,optimize,report

# 2. 错误总结（自动读取 workflow_result.json）
python error_summary.py --workflow workflow_result.json --text

# 3. 技术规范（自动读取 workflow_result.json）
python tech_spec.py --workflow workflow_result.json --text

# 4. 单独使用（自动查找项目）
python error_summary.py --auto . --text
python tech_spec.py --auto . --text
```

## 工具脚本

| 脚本 | 功能 | 常用命令 |
|------|------|---------|
| `shared.py` | **共享模块** | `from shared import find_fromelf, CHIP_DB, output_result` |
| `workflow.py` | **一键工作流** | `--auto . --steps compile,analyze` |
| `check_elf.py` | ELF 检查 | `--auto .` 或 `--elf project.axf --uv4 D:/k5/UV4/UV4.exe` |
| `debug_sim.py` | 静态分析 | `--auto . --mode sim` |
| `optimize.py` | 优化分析 | `--auto .` |
| `auto_fix.py` | 编译错误修复 | `--auto . --auto-fix` |
| `renode_sim.py` | Renode 仿真 | `--auto . --mode boot --timeout 5` |
| `serial_monitor.py` | 串口监控 | `--port COM3 --mode interactive` 或 `--mode monitor --log-file log.txt` |
| `serial_debug.py` | **串口调试助手** | `--port COM3 --mode analyze --duration 10` |
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
| `detect_config.py` | 项目配置检测 | `--scan .` |
| `error_summary.py` | **错误总结** | `--auto . --text` |
| `error_tracker.py` | **错误追踪** | `--record --error "xxx" --fix "xxx"` |
| `brick_prevention.py` | **死机预防** | `--auto .` 或 `--ioc project.ioc --check clock` |
| `tech_spec.py` | **技术规范生成** | `--auto . --text` 或 `--ioc project.ioc --text` |

## 编译流程

```bash
# 自动模式（推荐）
python workflow.py --auto . --steps compile

# 手动模式
cd <MDK-ARM目录> && UV4.exe -b <.uvprojx> -t <Target> -o build.log -j0
```

**成功**：返回码 0，进入静态分析
**失败**：`workflow.py` 自动调用 `auto_fix.py` 修复并重编（最多 3 轮）

### 编译错误处理

| 错误类型 | 修复方式 |
|---------|---------|
| `undefined reference` | 添加头文件/声明/链接 |
| `undeclared identifier` | 添加声明/修复拼写 |
| `file not found` | 检查文件路径和 include 路径 |
| `type mismatch` | 类型转换/修复签名 |

## 静态分析

```bash
python workflow.py --auto . --steps analyze
# 或单独运行
python check_elf.py --auto . --symbols "main,HAL_Init"
python debug_sim.py --auto . --mode sim
```

**检查项**：中断向量表、栈堆大小、关键符号、段大小

## 优化分析

```bash
python workflow.py --auto . --steps optimize
# 或单独运行
python optimize.py --auto . --src-dir ../Core/Src
```

**分析维度**：Flash/RAM 使用率、Top-20 最大函数、编译器设置、代码质量

## Renode 仿真

```bash
python renode_sim.py --auto . --mode boot --timeout 5
python renode_sim.py --auto . --mode uart --timeout 10
```

**验证项**：固件启动、UART 输出、无 HardFault

## 烧录流程

### ST-LINK 烧录（通过工作流）

```bash
python workflow.py --auto . --steps flash
# 或手动
UV4.exe -f project.uvprojx -t project_led -o flash.log
```

### USB DFU 烧录

```bash
python usb_dfu_flash.py --detect                    # 检测设备
python usb_dfu_flash.py --enter-dfu --port COM3     # 进入 DFU 模式
python usb_dfu_flash.py --full --port COM3 --firmware project.hex  # 完整流程
```

**安全约束**：不全片擦除、不写 Option Bytes、不改读保护

## CubeMX 配置

```bash
python cubemx_config.py --modify project.ioc --add-peripheral ADC1 --add-pin PA6 ADC1_IN6
python cubemx_config.py --modify project.ioc --set-clock --hse 8 --sysclk 168
python cubemx_config.py --modify project.ioc --config-gpio --gpio-pin PA8 --gpio-mode Output
python cubemx_config.py --modify project.ioc --config-nvic --irq USART1_IRQn --nvic-priority 5
python cubemx_config.py --generate project.ioc --toolchain "MDK-ARM V5"
```

详细配置参考：`references/cubemx_quick_ref.md`

## 串口验证

```bash
python serial_monitor.py --list                                                  # 列出串口
python serial_monitor.py --port COM3 --mode interactive                          # 交互模式（边收边发）
python serial_monitor.py --port COM3 --mode monitor --duration 10                # 监听
python serial_monitor.py --port COM3 --mode monitor --log-file uart.log          # 监听+实时写入日志
python serial_monitor.py --port COM3 --mode monitor --filter "error"             # 过滤显示
python serial_monitor.py --port COM3 --mode send --send "T\r"                    # 发送
python serial_monitor.py --port COM3 --mode parse --protocol vofa-firewater      # VOFA+
```

**交互模式命令**：
- 文本输入直接发送（自动附加 `\r\n`）
- `/hex FF 01 02` 发送十六进制字节
- `/baud 9600` 切换波特率
- `/filter <keyword>` 设置过滤关键字
- `/quit` 退出

## 串口调试助手（AI 调试专用）

### 自动模式（读取项目配置）

```bash
# 自动读取项目配置（波特率、协议等）
python serial_debug.py --auto . --port COM3 --proto text --send "@LED_ON"

# 读取工作流结果
python serial_debug.py --workflow workflow_result.json --port COM3 --proto printf --listen 30
```

### 基本用法

```bash
# 文本命令（自动附加 \r\n）
python serial_debug.py --port COM3 --proto text --send "@LED_ON"

# HEX 数据包（自动加帧头 0xFF 帧尾 0xFE）
python serial_debug.py --port COM3 --proto hex --send "01 02 03 04"

# printf 监听（被动接收）
python serial_debug.py --port COM3 --proto printf --listen 10
python serial_debug.py --port COM3 --proto printf --listen 10 --filter "temp"

# 批量命令
python serial_debug.py --port COM3 --proto text --batch commands.txt

# 交互模式（支持协议切换）
python serial_debug.py --port COM3 --mode interactive
```

**协议说明**：
- `text` — 发送 `@LED_ON\r\n`，接收文本行
- `hex` — 发送 `FF 01 02 03 04 FE`（自动加帧头帧尾），接收 HEX 包
- `printf` — 只接收，不发送，按行显示

## 回归检测

```bash
python compare.py --save --history-dir history/ --elf-data check_elf.json --sim-data debug_sim.json
python compare.py --baseline history/v1/ --current history/v2/ --report diff.md
python compare.py --trend --history-dir history/ --report trend.md
```

## 常见使用场景

### 场景 1：首次编译新项目

```bash
# 1. 检查项目健康状态
python workflow.py --auto . --steps health

# 2. 编译 + 分析
python workflow.py --auto . --steps compile,analyze

# 3. 如果编译失败，查看错误详情
python auto_fix.py --auto . --text
```

### 场景 2：烧录前验证

```bash
# 完整验证流程
python workflow.py --auto . --steps compile,analyze,optimize,simulate

# 只看优化建议
python optimize.py --auto . --text
```

### 场景 3：串口调试

```bash
# 监听 printf 输出
python serial_debug.py --port COM3 --proto printf --listen 30 --filter "error"

# 发送命令测试
python serial_debug.py --port COM3 --proto text --send "@LED_ON"

# HEX 数据包测试
python serial_debug.py --port COM3 --proto hex --send "01 02 03 04"
```

### 场景 4：回归测试

```bash
# 保存当前版本快照
python compare.py --save --history-dir history/ --elf-data check_elf.json --sim-data debug_sim.json

# 修改代码后对比
python compare.py --baseline history/v1/ --current history/v2/ --report diff.md
```

### 场景 5：错误总结

```bash
# 从工作流结果总结错误
python error_summary.py --workflow workflow_result.json --text

# 从编译日志总结
python error_summary.py --build-log build.log --text

# 自动模式
python error_summary.py --auto . --text
```

### 场景 6：生成技术规范

```bash
# 自动模式（推荐）
python tech_spec.py --auto . --text

# 从 CubeMX 配置生成
python tech_spec.py --ioc project.ioc --text

# 输出到 Markdown 文件
python tech_spec.py --auto . --output tech_spec.md
```

## 错误总结

```bash
# 从工作流结果总结
python error_summary.py --workflow workflow_result.json --text

# 从编译日志总结
python error_summary.py --build-log build.log --text

# 多个来源汇总
python error_summary.py --build-log build.log --elf-data check_elf.json --sim-data debug_sim.json --text
```

**输出内容**：
- 错误统计（按严重程度、来源、分类）
- 详细错误列表（文件、行号、消息）
- 修复建议（按优先级排序）

## 技术规范生成

```bash
# 自动模式
python tech_spec.py --auto . --text

# 从工作流结果生成
python tech_spec.py --workflow workflow_result.json --text

# 输出到文件
python tech_spec.py --auto . --output tech_spec.md
```

**生成内容**：
- 项目信息（名称、工具链、Target）
- 芯片信息（型号、内核、Flash/RAM）
- 内存布局（Flash、RAM、CCM 地址）
- 外设配置（从 CubeMX 提取）
- GPIO 配置（引脚、模式、标签）
- 时钟配置（HSE、SYSCLK、APB）
- NVIC 配置（中断使能状态）
- FreeRTOS 配置（任务、栈、优先级）
- 构建信息（Flash/RAM 使用率、栈堆大小）

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

## 错误追踪

### 记录错误修复

```bash
# 记录错误和修复方法
python error_tracker.py --record --error "undefined reference to 'HAL_GPIO_Init'" --fix "添加 #include 'stm32f4xx_hal_gpio.h'" --file main.c

# 记录错误（自动分类）
python error_tracker.py --record --error "region FLASH overflowed by 1024 bytes" --fix "优化代码大小或更换芯片"

# 记录错误（带备注）
python error_tracker.py --record --error "HardFault" --fix "增加栈大小到 1024 bytes" --notes "FreeRTOS 项目"
```

### 查询历史错误

```bash
# 搜索错误
python error_tracker.py --search "undefined reference" --text

# 获取修复建议（包含 CubeMX 修复建议）
python error_tracker.py --suggest "undefined reference to 'xxx'" --text

# 列出所有记录
python error_tracker.py --list --text

# 生成统计报告
python error_tracker.py --report --text
```

### 与工作流集成

```bash
# 完整流程（包含错误追踪）
python workflow.py --auto . --steps compile,analyze,optimize,report

# 错误追踪报告会自动包含在 report 步骤中
```

### 功能特性

| 功能 | 说明 |
|------|------|
| **自动分类** | 编译、链接、运行时、配置、CubeMX/HAL、串口、I2C、SPI、ADC |
| **相似匹配** | 自动查找相似历史错误 |
| **CubeMX 建议** | 配置错误时建议在 CubeMX 中修改 |
| **错误趋势** | 按日期和分类分析错误趋势 |
| **预防建议** | 基于历史错误提供预防建议 |

## 维护约定

> **每次解决错误/bug 时，使用 `error_tracker.py --record` 记录错误和修复方法。**

## 文档

| 文档 | 说明 |
|------|------|
| `references/error_summary_guide.md` | 错误总结工具使用指南 |
| `references/error_patterns.md` | 编译错误模式库 |
| `references/cubemx_configuration_guide.md` | CubeMX 配置指南 |
| `references/cubemx_quick_ref.md` | CubeMX 快速参考 |
| `references/troubleshooting.md` | 故障排除指南 |

## 依赖

| 依赖 | 必需 | 说明 |
|------|------|------|
| Python 3.8+ | ✅ | 运行脚本 |
| Keil MDK-ARM | ✅ | 编译工具链 |
| STM32CubeProgrammer | ⚠️ | 烧录工具 |
| Renode | ⚠️ | 无硬件仿真 |
| STM32CubeMX | ⚠️ | 代码生成 |
| pyserial | ⚠️ | 串口通信 |

## AI 工作流约定

> **遇到错误时读错误总结，开发功能时读技术规范。**

详细工作流请参考：`references/ai_workflow.md`

### 快速参考

| 场景 | 第一步 | 命令 |
|------|--------|------|
| 遇到错误 | 查错误总结 | `python error_tracker.py --search "关键词" --text` |
| 开发功能 | 读技术规范 | `python tech_spec.py --auto . --text` |
| 配置外设 | 查 CubeMX 指南 | `python cubemx_guide.py --peripheral USART1` |
| 编译测试 | 运行工作流 | `python workflow.py --auto . --steps compile` |

## ⚠️ 时钟配置保护规则

> **时钟配置绝对不能修改！修改时钟配置会导致系统死机、锁死！**

### 禁止操作

| 禁止 | 说明 |
|------|------|
| ❌ 修改 PLL 配置 | PLL 倍频、分频系数 |
| ❌ 修改 HSE/HSI | 外部/内部高速时钟源 |
| ❌ 修改 SYSCLK | 系统时钟源选择 |
| ❌ 修改 AHB/APB 分频 | 总线时钟分频系数 |
| ❌ 修改 CubeMX 时钟 | Clock Configuration 中的任何参数 |

### 允许操作

| 允许 | 说明 |
|------|------|
| ✅ 读取时钟配置 | 查看当前配置 |
| ✅ 验证时钟配置 | 检查配置是否正确 |
| ✅ 在 CubeMX 中修改 | 用户手动在 CubeMX 中修改 |

### 时钟配置验证

```bash
# 检查时钟配置（只读）
python clock_validator.py --ioc project.ioc

# 查看技术规范中的时钟配置
python tech_spec.py --auto . --text
```

### 如果时钟配置有问题

```
❌ 错误做法：
  发现时钟配置不对 → 在代码中修改时钟配置

✅ 正确做法：
  发现时钟配置不对 → 告诉用户在 CubeMX 中修改：
  1. 打开 project.ioc
  2. Clock Configuration
  3. 检查 HSE/HSI 配置
  4. 检查 PLL 配置
  5. 检查 SYSCLK 源
  6. 重新生成代码
```

### ⚠️ 死机/锁机预防

在烧录前检查固件和配置，防止芯片死机或锁死：

```bash
# 完整检查（推荐）
python brick_prevention.py --auto .

# 检查时钟配置
python brick_prevention.py --ioc project.ioc --check clock

# 检查固件
python brick_prevention.py --elf project.axf --check firmware

# 检查读保护
python brick_prevention.py --check rdp
```

**检查项目**：
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

### ⚠️ 死机/锁机恢复

如果芯片死机或锁死，按以下步骤恢复：

```bash
# 1. 检查读保护状态
STM32_Programmer_CLI.exe -c port=SWD mode=UR

# 2. 如果有读保护(RDP)，需要先解除
# ⚠️ 解除读保护会擦除整个芯片！
STM32_Programmer_CLI.exe -c port=SWD mode=UR -ob RDP=0

# 3. 如果没有读保护，直接擦除
STM32_Programmer_CLI.exe -c port=SWD mode=UR -e all

# 4. 重新烧录
STM32_Programmer_CLI.exe -c port=SWD mode=UR -w project.axf -v -rst
```

**恢复顺序**：
1. 先检查是否有读保护（RDP）
2. 如果有读保护，先解除（会擦除芯片）
3. 如果没有读保护，直接擦除
4. 重新烧录固件

**注意**：
- 解除读保护会擦除整个芯片（包括 Flash 和 Option Bytes）
- 如果芯片完全锁死，可能需要使用 BOOT0 引脚进入系统引导模式
- 某些情况下可能需要使用 ST-LINK 的 NRST 引脚手动复位

## 核心原则：CubeMX 配置为基准

> **CubeMX 生成的配置文件是项目基准，代码必须适配配置，而不是反过来。**

### 规则

1. **不修改 CubeMX 生成的文件**
   - `MX_*` 函数（如 `MX_GPIO_Init`, `MX_USART1_Init`）
   - `*.ioc` 配置文件
   - CubeMX 生成的初始化代码

2. **代码适配配置**
   - 如果 CubeMX 配置了 USART1 115200，代码中使用相同的配置
   - 如果 CubeMX 配置了 GPIO PA5 输出，代码中使用 PA5
   - 不要在代码中覆盖 CubeMX 的配置

3. **配置错误处理**
   - 如果发现配置错误（如时钟不对、引脚冲突）
   - **不要在代码中绕过**
   - **告诉用户在 CubeMX 中重新配置**
   - 提供具体的配置步骤

### 示例

```
❌ 错误做法：
  发现 USART1 波特率不对 → 在代码中手动修改波特率

✅ 正确做法：
  发现 USART1 波特率不对 → 告诉用户在 CubeMX 中修改：
  1. 打开 project.ioc
  2. Connectivity → USART1
  3. 修改 Baud Rate 为 115200
  4. 重新生成代码
```

### CubeMX 配置指南

```bash
# 查看 CubeMX 配置指南
python cubemx_guide.py --peripheral ADC1
python cubemx_guide.py --peripheral USART1
python cubemx_guide.py --peripheral I2C1

# 检查配置冲突
python pin_checker.py --ioc project.ioc
python clock_validator.py --ioc project.ioc
python peripheral_validator.py --ioc project.ioc
```

## 安全约束

- **不全片擦除**（不使用 `-e` 标志）
- **不写 Option Bytes**
- **不改读保护**（RDP）
- **不在用户未确认的情况下烧录到硬件**
- **编译错误修复遵循最小改动原则**
