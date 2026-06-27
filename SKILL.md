---
name: stm32-keil-workflow
description: >
  STM32 firmware development automation for Keil MDK-ARM projects. Handles compilation, static analysis,
  optimization, simulation, flashing (ST-LINK/USB DFU), CubeMX configuration, serial monitoring, and
  regression detection. Use this skill when working with STM32 microcontrollers (F0/F1/F2/F3/F4/F7/G0/G4/L0/L4/H7),
  Keil uVision projects (.uvprojx), Cortex-M development, FreeRTOS, STM32CubeMX, or embedded firmware.
  Triggers on: STM32 compile/build/flash/debug, firmware analysis, code optimization, serial port testing,
  CubeMX configuration, .uvprojx projects, ST-LINK/SWD, USB DFU, ELF/AXF analysis, "full analysis",
  "add task", "configure peripheral", ADC/DAC, I2C/SPI/UART, PWM, encoder, motor control.
  Also handles: STM32 project initialization, health checks, code generation, memory analysis,
  pin conflict detection, clock validation, peripheral validation, NVIC configuration.
  Design review triggers: config system verification, Config_Get/Config_Set not called,
  Init function not reading config, hardcoded clock frequency, timer prescaler calculation,
  mutex usage pattern, race condition in shared data, waveform display aliasing,
  min/max envelope downsampling, division by zero in timer config.
  Debug triggers: HAL behavior unexpected, DMA not working, callback not firing, firmware hangs,
  flash but no effect, Error_Handler stuck, register debugging, HAL source code lookup,
  "搜一下HAL"、"DMA不循环"、"回调没触发"、"烧了没反应"、"固件卡死"、"寄存器状态",
  "编译失败"、"烧录没效果"、"跑的是旧代码"、"I2C不通"、"SPI没数据"、"ADC值不对",
  "串口没输出"、"HardFault"、"栈溢出"、"中断不响应"、"定时器不准",
  "版本回退"、"恢复上一个版本"、"硬件不工作"、"电源问题"、"示波器",
  "配置没生效"、"Config没读到"、"定时器频率不对"、"采样率不对"、"波形是尖刺".
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

# 可用步骤: compile, analyze, optimize, simulate, flash, reset, serial, health, report, brick_check
```

`--auto .` 会自动检测 `.uvprojx` 项目文件、`.axf` 编译产物、UV4.exe 路径，无需手动指定任何参数。

> 工具脚本路径：`D:\ClaudeGlobalConfig\skills\stm32-keil-workflow\scripts\`（本技能目录下）

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

# 烧录 + 复位
python workflow.py --auto . --steps flash,reset --port COM3

# 烧录 + 复位 + 验证
python workflow.py --auto . --steps flash,reset --port COM3 --reset-method dtr_rts --reset-verify

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

### 核心（每次开发必用）

| 脚本 | 功能 | 常用命令 |
|------|------|---------|
| `workflow.py` | **一键工作流** | `--auto . --steps compile,analyze` |
| `dev_loop.py` | **开发模式循环** | `--auto . --port COM3`（文件变化自动编译烧录） |
| `dev_log.py` | **开发日志** | `--auto . --add "xxx"` / `--from-git` / `--export log.md` |
| `version.py` | **版本管理** | `--auto . --status` / `--diff` / `--rollback` / `--snapshot` / `--tag` |
| `serial_debug.py` | **串口调试助手** | `--port COM3 --proto text --send "@LED_ON"` |
| `serial_test.py` | **串口测试框架** | `--port COM3 --test tests.json` |
| `error_tracker.py` | **错误追踪** | `--record --error "xxx" --fix "xxx"` / `--export solutions.md` |
| `tech_spec.py` | **技术规范生成** | `--auto . --text` |
| `error_summary.py` | **错误总结** | `--auto . --text` |

### 分析（按需使用）

| 脚本 | 功能 | 常用命令 |
|------|------|---------|
| `check_elf.py` | ELF 检查 | `--auto .` |
| `debug_sim.py` | 静态分析 | `--auto . --mode sim` |
| `optimize.py` | 优化分析 | `--auto .` |
| `auto_fix.py` | 编译错误修复 | `--auto . --auto-fix` |
| `memory_analyzer.py` | 内存分析 | `--auto .` |
| `compare.py` | 回归检测 | `--baseline history/v1/ --current history/v2/` |
| `brick_prevention.py` | **死机预防** | `--auto .` |

### 配置（偶尔使用）

| 脚本 | 功能 | 常用命令 |
|------|------|---------|
| `cubemx_config.py` | CubeMX 配置 | `--modify project.ioc --add-peripheral ADC1` |
| `pin_checker.py` | 引脚冲突检测 | `--ioc project.ioc` |
| `clock_validator.py` | 时钟配置验证 | `--ioc project.ioc` |
| `peripheral_validator.py` | 外设配置验证 | `--ioc project.ioc` |
| `nvic_checker.py` | NVIC 配置检查 | `--ioc project.ioc` |
| `health_check.py` | 项目健康检查 | `--project . --fix` |
| `code_gen.py` | 代码生成 | `--type uart --name USART1 --output Core/Src` |
| `detect_config.py` | 项目配置检测 | `--scan .` |
| `i2c_scanner.py` | I2C 总线扫描 | `--port COM3`（扫描设备地址） |
| `reg_dump.py` | 外设寄存器转储 | `--auto . --peripheral GPIO,TIM,ADC` |
| `unit_test.py` | 单元测试框架 | `--auto . --generate` / `--run` |
| `power_analyzer.py` | 功耗分析 | `--auto .`（低功耗模式建议） |
| `isr_analyzer.py` | 中断延迟分析 | `--auto .`（优先级配置检查） |
| `dma_analyzer.py` | DMA 性能分析 | `--auto .`（Stream 冲突检测） |
| `adc_analyzer.py` | ADC 噪声分析 | `--auto . --data samples.bin`（ENOB/SNR） |

### 烧录 / 仿真

| 脚本 | 功能 | 常用命令 |
|------|------|---------|
| `renode_sim.py` | Renode 仿真 | `--auto . --mode boot --timeout 5` |
| `serial_monitor.py` | 串口监控 | `--port COM3 --mode interactive` |
| `usb_dfu_flash.py` | USB DFU 烧录 | `--full --port COM3 --firmware app.hex` |

## 编译流程

```bash
# 自动模式（推荐）
python workflow.py --auto . --steps compile

# Keil 手动模式
cd <MDK-ARM目录> && UV4.exe -b <.uvprojx> -t <Target> -o build.log -j0

# STM32CubeIDE（如果用 Eclipse 系）
cd <项目目录> && arm-none-eabi-gcc -c ... -o build.elf

# IAR
cd <项目目录> && IarBuild.exe project.ewp -build Debug -log errors
```

> 工具脚本默认检测 Keil UV4.exe。如果用 STM32CubeIDE 或 IAR，需要手动指定编译器路径。

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
# 或 --toolchain "STM32CubeIDE" / --toolchain "SW4STM32" / --toolchain "Makefile"
```

详细配置参考：`references/cubemx_quick_ref.md`

## 烧录后复位

```bash
# 烧录 + 复位
python workflow.py --auto . --steps flash,reset --port COM3

# 烧录 + DTR+RTS 复位
python workflow.py --auto . --steps flash,reset --port COM3 --reset-method dtr_rts

# 烧录 + 复位 + 验证
python workflow.py --auto . --steps flash,reset --port COM3 --reset-method dtr_rts --reset-verify

# 复位 + 串口验证
python workflow.py --auto . --steps reset,serial --port COM3 --reset-verify

# 进入 bootloader 模式
python workflow.py --auto . --steps reset --port COM3 --reset-method bootloader

# 复位重试
python workflow.py --auto . --steps reset --port COM3 --reset-retry 3
```

| 复位方法 | 说明 |
|---------|------|
| `dtr` | DTR → NRST |
| `rts` | RTS → NRST |
| `dtr_rts` | DTR+RTS 组合（CH340/CP2102） |
| `break` | BREAK 信号 |
| `break_dtr` | BREAK + DTR |
| `custom` | DTR+RTS 同时操作 |
| `bootloader` | 进入 STM32 bootloader（0x7F 握手） |

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

| 场景 | 第一步 | 命令 |
|------|--------|------|
| 快速迭代 | 开发模式 | `python dev_loop.py --auto . --port COM3` |
| 首次编译 | 健康检查 + 编译 | `python workflow.py --auto . --steps health,compile,analyze` |
| 烧录前验证 | 完整分析 | `python workflow.py --auto . --steps compile,analyze,optimize,report` |
| 串口调试 | 监听 printf | `python serial_debug.py --port COM3 --proto printf --listen 30` |
| 串口测试 | 自动化验证 | `python serial_test.py --port COM3 --test tests.json` |
| 发送命令 | 文本协议 | `python serial_debug.py --port COM3 --proto text --send "@LED_ON"` |
| 遇到错误 | 查历史错误 | `python error_tracker.py --search "关键词" --text` |
| 开发功能 | 读技术规范 | `python tech_spec.py --auto . --text` |
| 配置外设 | 查 CubeMX 指南 | `python cubemx_guide.py --peripheral USART1` |
| 回归测试 | 保存快照对比 | `python compare.py --baseline history/v1/ --current history/v2/` |
| 错误总结 | 从工作流生成 | `python error_summary.py --auto . --text` |
| 技术规范 | 自动生成 | `python tech_spec.py --auto . --output tech_spec.md` |

## 自动化流程

### 开发模式（快速迭代）

文件变化 → 自动编译 → 自动烧录 → 继续监控。`Ctrl+C` 退出。

```bash
# 最常用：改了就烧
python dev_loop.py --auto . --port COM3

# 只编译不烧录
python dev_loop.py --auto . --no-flash

# 2 秒检查一次（减少 CPU 占用）
python dev_loop.py --auto . --port COM3 --interval 2
```

### 验证模式（完整检查）

编译 → 分析 → 优化 → 报告。烧录前用这个。

```bash
python workflow.py --auto . --steps compile,analyze,optimize,report
```

### 串口测试（自动化验证）

JSON 定义测试用例，自动发命令检查响应。

```bash
# 运行测试套件
python serial_test.py --port COM3 --test tests.json

# 生成报告
python serial_test.py --port COM3 --test tests.json --report result.json

# 单条测试
python serial_test.py --port COM3 --send "@LED_ON" --expect "OK"
```

**测试用例 JSON 格式：**
```json
{
  "name": "LED 控制测试",
  "baudrate": 115200,
  "tests": [
    {"name": "开灯", "send": "@LED_ON", "expect": "OK", "timeout": 2},
    {"name": "查状态", "send": "@STATUS", "expect_contains": "LED:ON"},
    {"name": "关灯", "send": "@LED_OFF", "expect": "OK"}
  ]
}
```

### 完整 CI 流程

```bash
# 1. 编译 + 分析
python workflow.py --auto . --steps compile,analyze

# 2. 烧录
python workflow.py --auto . --steps flash --port COM3

# 3. 串口测试
python serial_test.py --port COM3 --test tests.json --report result.json

# 4. 记录结果
python error_tracker.py --record --error "CI 通过" --fix "N/A"
```

### auto_fix 自动记录

auto_fix.py 修复编译错误后，自动调用 error_tracker.py 记录错误和修复方法。下次遇到同样的错误，`error_tracker.py --search` 就能找到。

## 文档读写

### 读文档

| 读什么 | 命令 | 说明 |
|--------|------|------|
| 技术规范 | `python tech_spec.py --auto . --text` | 从 CubeMX 和编译产物提取 |
| 错误总结 | `python error_summary.py --auto . --text` | 从 build.log 提取 |
| 错误历史 | `python error_tracker.py --search "关键词" --text` | 搜索历史错误 |
| 开发日志 | `python dev_log.py --auto . --today` | 今日开发记录 |
| 项目文档 | Glob 搜 `**/*spec*`、`**/*log*`、`**/*solution*` | 定位项目文档 |
| HAL 源码 | `Drivers/*HAL_Driver/Src/*hal_<外设>.c` | 读 HAL 实现 |

### 写文档

| 写什么 | 命令 | 说明 |
|--------|------|------|
| 技术规范 | `python tech_spec.py --auto . --output tech_spec.md` | 生成到文件 |
| 开发日志 | `python dev_log.py --auto . --add "功能描述"` | 手动记录 |
| 从 git 生成日志 | `python dev_log.py --auto . --from-git` | 自动从提交记录生成 |
| 从错误生成日志 | `python dev_log.py --auto . --from-errors` | 自动从 error_tracker 生成 |
| 导出日志 | `python dev_log.py --auto . --export dev-log.md` | 导出为 Markdown |
| 问题解决记录 | `python error_tracker.py --export solutions-log.md` | 导出为 solutions-log 格式 |
| 错误记录 | `python error_tracker.py --record --error "xxx" --fix "xxx"` | 记录单条错误 |
| 串口测试报告 | `python serial_test.py --port COM3 --test tests.json --report result.json` | 生成测试报告 |

### 文档自动化

```bash
# 每日开发结束时，自动生成所有文档
python dev_log.py --auto . --from-git                  # 从 git 生成日志
python dev_log.py --auto . --from-errors               # 从错误生成日志
python dev_log.py --auto . --export docs/dev-log.md    # 导出开发日志
python error_tracker.py --export docs/solutions-log.md # 导出问题解决记录
python tech_spec.py --auto . --output docs/tech-spec.md # 生成技术规范
```

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
| **自动分类** | 编译、链接、运行时、配置、设计缺陷、CubeMX/HAL、串口、I2C、SPI、ADC |
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

> **遇到错误时读错误总结，开发功能时读技术规范。** 详细工作流参考：`references/ai_workflow.md`

### 写代码前检查流（必须逐条完成）

写任何代码之前，按此清单逐条检查。跳过任何一条都可能引入难以调试的 bug。

```
┌─────────────────────────────────────────────────────────────┐
│  第 1 步：理解上下文                                          │
│  □ 读技术规范 → python tech_spec.py --auto . --text          │
│  □ 搜错误历史 → python error_tracker.py --search "关键词"    │
│  □ 读项目文档 → Glob 搜 **/*spec*、**/*log*、**/*solution*   │
├─────────────────────────────────────────────────────────────┤
│  第 2 步：检查初始化链                                        │
│  □ 所需模块是否已 Init？（调用前必须先初始化）                 │
│  □ RTOS 对象（mutex/semaphore/queue）是否在调度器启动后创建？ │
│  □ Init 函数是否从 Config 读取配置（不是只用硬编码默认值）？   │
│  □ 外设初始化顺序是否正确？                                    │
│    RCC时钟 → GPIO → DMA → 外设配置 → 外设使能 → NVIC         │
│  □ 快速验证 → grep -rn "osMutexNew\|osSemaphoreNew" Core/Src/│
│    （确认在 Task 函数内而非 Init 函数内创建）                  │
├─────────────────────────────────────────────────────────────┤
│  第 3 步：检查配置系统                                        │
│  □ Config_Get*() 是否在 Init 中被调用？                       │
│  □ Set*() 函数是否调用 Config_Set*() 同步回 Config？          │
│  □ 快速验证 → grep -rn "Config_Get\|Config_Set" Core/Src/   │
│    （如果只有 config.c 有调用，说明配置系统没接通）             │
├─────────────────────────────────────────────────────────────┤
│  第 4 步：检查时钟和定时器                                    │
│  □ 定时器时钟是否用 HAL_RCC_GetPCLKxFreq()？                 │
│  □ 快速扫描 → grep -rn "84000000\|168000000" Core/Src/      │
│  □ ApplyConfig 类函数是否有除零保护？                         │
│  □ uint32_t 减法是否可能下溢？(psc = x/y - 1)                │
├─────────────────────────────────────────────────────────────┤
│  第 5 步：检查变量封装                                        │
│  □ 全局变量是否用 static 限制作用域？（只在本文件用就加 static）│
│  □ 跨文件访问是否通过 getter/setter 函数？（不直接 extern）    │
│  □ 硬编码数值是否定义为宏或常量？（不用魔法数字）               │
│  □ 配置值是否通过 Config API 访问？（不直接读写 app_config）   │
│  □ 重复变量是否消除？（如 osc_config_buffer_size 是多余的）    │
│  □ ISR 共享变量是否只通过 volatile 指针/函数访问？             │
├─────────────────────────────────────────────────────────────┤
│  第 6 步：检查并发安全                                        │
│  □ 共享数据是否在互斥锁内修改？                               │
│  □ Config_Set*() 等 memcpy 操作是否在锁内拷贝？              │
│  □ LOG_INFO（含 HAL_UART_Transmit）是否在锁外调用？           │
│  □ ISR extern 声明是否与定义的 volatile 修饰匹配？            │
├─────────────────────────────────────────────────────────────┤
│  第 7 步：检查显示和算法                                      │
│  □ 波形显示是否用 min/max 包络（不是取单点）？                │
│  □ 降采样 step 是否向上取整（避免尾部数据丢失）？             │
│  □ 频率/电压计算是否有除零保护？                              │
└─────────────────────────────────────────────────────────────┘
```

**为什么这个清单重要**：本项目 8 个初始 bug + 7 个后续问题，全部是这些检查项的遗漏。跳过任何一条 = 赌博。

### 变量封装规则

写代码时必须按以下规则封装变量，违反任何一条都是代码质量问题：

#### 规则 1：结构体组织相关数据

```c
// ❌ 散落的变量
static uint32_t frequency;
static uint32_t amplitude;
static WaveformType_t waveform;

// ✅ 结构体封装
typedef struct {
    uint32_t frequency;
    uint32_t amplitude;
    WaveformType_t waveform;
    uint16_t duty_cycle;
    uint8_t enabled;
} SigGenConfig_t;

static SigGenConfig_t siggen_config = {
    .frequency = SIGGEN_DEFAULT_FREQUENCY,
    .amplitude = SIGGEN_DEFAULT_AMPLITUDE,
};
```

#### 规则 2：static 限制作用域

```c
// ❌ 全局可见，任何文件都能 extern 访问
uint16_t adc_buffer[1024];

// ✅ 只在本文件使用
static uint16_t waveform_buffer[256];

// ✅ 需要跨文件访问时，用非 static + getter
uint16_t adc_buffer[1024];  // 非 static，但通过 getter 访问
const uint16_t *Oscilloscope_GetAdcBuffer(void) { return adc_buffer; }
```

#### 规则 3：getter/setter 封装访问

```c
// ❌ 直接 extern 变量
extern volatile uint16_t *process_ptr;

// ✅ 通过函数访问
bool Osc_GetProcessBuffer(const uint16_t **buf, uint16_t *len);

// ✅ setter 可以带校验和副作用
ErrorCode_t SignalGen_SetFrequency(uint32_t freq_hz) {
    if (freq_hz == 0 || freq_hz > 1000000) return ERR_INVALID_PARAM;
    SIGGEN_LOCK();
    siggen_config.frequency = freq_hz;
    SigGen_ApplyConfig();           // 同步更新硬件
    SigGenConfig_t cfg = siggen_config;
    SIGGEN_UNLOCK();
    Config_SetSigGenConfig(&cfg);   // 同步到 Config
    return ERR_OK;
}
```

#### 规则 4：宏/函数替代魔法数字

```c
// ❌ 硬编码
uint32_t psc = (84000000 / target) - 1;

// ✅ 宏
#define APB1_TIMER_CLK  84000000

// ✅ 更好：函数动态获取
static uint32_t SigGen_GetTimerClock(void) {
    uint32_t pclk1 = HAL_RCC_GetPCLK1Freq();
    if ((RCC->CFGR & RCC_CFGR_PPRE1) != RCC_CFGR_PPRE1_DIV1)
        return pclk1 * 2;
    return pclk1;
}
```

#### 规则 5：消除重复变量

```c
// ❌ osc_config.buffer_size 的重复副本
uint32_t osc_config_buffer_size = OSC_DEFAULT_BUFFER_SIZE;

// ✅ 直接用 getter
uint32_t Oscilloscope_GetAdcBufferSize(void) {
    return osc_config.buffer_size;
}
```

#### 规则 6：volatile + 临界区保护 ISR 共享变量

```c
// ❌ ISR 共享但无保护
uint32_t tick_count;

// ✅ volatile + 原子读取
static volatile uint32_t tick_count = 0;
uint32_t System_GetTick(void) {
    __disable_irq();
    uint32_t t = tick_count;
    __enable_irq();
    return t;
}
```

#### 封装检查清单

```
□ 散落的相关变量是否组织成结构体？
□ 只在本文件用的变量/函数是否加了 static？
□ 跨文件访问是否通过 getter/setter？
□ 硬编码数值是否用宏或函数替代？
□ 是否存在重复变量（如 buffer_size 副本）？
□ ISR 共享变量是否 volatile + 临界区保护？
□ setter 是否带校验（范围检查、除零保护）？
□ setter 是否带副作用（同步硬件、同步 Config）？
```

### AI 修改代码前必须做

1. **读项目文档** — Glob 搜 `**/*spec*`、`**/*log*`、`**/*solution*`，看有没有相关记录
2. **读技术规范** — `python tech_spec.py --auto . --text`，了解外设配置和时钟布局
3. **搜错误历史** — `python error_tracker.py --search "关键词" --text`，看有没有踩过同样的坑
4. **完成检查流** — 逐条确认上面的 5 步检查清单

### AI 调试时必须做

1. **不猜** — 先读寄存器确认实际状态，再下结论
2. **先搜** — 搜 ST Community / Stack Overflow，HAL 被几十万人用过
3. **读源码** — 搜不到就读 `Drivers/*HAL_Driver/Src/*hal_<外设>.c`
4. **最小改动** — 一次只改一处，验证后才改下一处
5. **确认新代码** — 烧录后看 BUILD 时间戳，排除旧代码

### AI 修复后必须做

1. **记录错误** — `python error_tracker.py --record --error "xxx" --fix "xxx"`
2. **验证修复** — 编译通过 + 串口确认功能正常
3. **版本标记** — 功能完成后 `git tag stable/xxx`

### AI 不能做的事

| 禁止 | 原因 |
|------|------|
| 修改时钟配置 | PLL/HSE/SYSCLK 代码中动了就死机 |
| 硬编码时钟频率 | APBx 分频器变更时静默失效，必须用 `HAL_RCC_GetPCLKxFreq()` |
| 修改 CubeMX 生成的 MX_* 函数 | CubeMX 重新生成会覆盖 |
| 混用 HAL 和寄存器操作同一外设 | 两套状态机互相覆盖 |
| 空 Error_Handler | 板子卡死无法定位 |
| 全片擦除（-e） | 除非用户明确要求或死机恢复 |
| 不读错误信息就猜 | 编译器告诉你问题在哪，就读 |
| Init 函数不读 Config | 配置系统形同虚设，Flash 保存的配置永远不会生效 |
| 锁外写共享数据 | 竞态条件导致 Config 存入脏数据 |
| 波形显示取单点降采样 | 多周期时混叠产生尖刺，必须用 min/max 包络 |

### AI 开发新功能的流程

```
1. 读技术规范 → 了解外设配置和已知问题
2. 搜错误历史 → 看有没有类似功能的踩坑记录
3. 查参考手册 → 确认外设能力（触发源、DMA 通道等）
4. 写代码 → 在 USER CODE 区写，不改 CubeMX 生成的代码
5. 编译验证 → python workflow.py --auto . --steps compile
6. 烧录测试 → python dev_loop.py --auto . --port COM3
7. 记录结果 → python dev_log.py --auto . --add "功能完成"
8. 版本标记 → git tag stable/xxx
```

## 嵌入式工程师守则

### 硬约束（违反 = 必出问题）

| # | 守则 | 后果 |
|---|------|------|
| 1 | 时钟配置不能碰 | PLL/HSE/SYSCLK 代码中动了就死机，只能在 CubeMX 改 |
| 2 | 时钟频率不能硬编码 | APBx 分频器变更时静默失效，必须用 `HAL_RCC_GetPCLKxFreq()` |
| 3 | Error_Handler 不能空死循环 | 必须有串口输出，否则"板子卡死"无法定位 |
| 4 | CubeMX 配置是基准 | 代码适配配置，不是反过来。配置错误在 CubeMX 中改，不在代码中绕过 |
| 5 | CubeMX 重新生成会覆盖 | 手动配置必须写在 USER CODE 区，生成后对照验证 |
| 6 | HAL 和寄存器不能混用 | 混用 = 两套状态机互相覆盖，回调失效 |
| 7 | Config API 必须两头接通 | Init 读 Config + Set* 写回 Config，否则配置系统形同虚设 |
| 8 | 互斥锁内外要分清 | Config_Set* 等 memcpy 操作在锁内拷贝、锁外写入，避免竞态 |

### 最佳实践（不做 = 浪费时间）

| # | 守则 | 节省 |
|---|------|------|
| 6 | 先读文档，再动代码 | 技术规范和问题日志是事前检查清单，避免重复踩坑 |
| 7 | 先搜，再试 | HAL 被几十万人用过，搜 5 分钟省几天 |
| 8 | 碰到障碍要换路 | 死磕同一条路是最贵的错误 |
| 9 | 写完寄存器要读回来确认 | 写→读→确认，不读回来 = 没写 |
| 10 | 烧录后先确认是新代码 | 改了没效果？先怀疑旧代码，不要怀疑逻辑 |
| 11 | 选外设前查参考手册 | ADC 触发源、DMA 能力 — 不查手册就选型 = 赌博 |
| 12 | 全量编译是最后手段 | 增量编译每次省 20 秒 |
| 13 | 每次修 bug 都记录 | `error_tracker.py --record`，下次 5 秒解决 |

> 详细执行步骤见下方"调试方法论"对应章节。

---

## 解决问题的流程

嵌入式问题的本质是**信息不对称**——你不知道硬件/固件的实际状态。流程目标：用最少的烧录次数获取最多的信息。

```
发现问题
  │
  ├─→ ① 查已知问题（2min）
  │     查项目文档 + 搜错误历史
  │     → 有答案 → 直接修复 → 验证 → 记录
  │
  ├─→ ② 确认硬件状态（1min）
  │     读寄存器：TIM->CNT 在变？DMA->CR EN 位？USART->SR TXE？
  │     → 硬件没工作 → 问题在驱动层
  │     → 硬件正常 → 问题在数据/算法层
  │
  ├─→ ③ 分层定位（5min）
  │     从②确认的起点开始，逐层向上排查
  │     硬件→驱动→数据→算法→显示
  │
  ├─→ ④ 搜网上（5min）
  │     ST Community / Stack Overflow
  │
  └─→ ⑤ 读 HAL 源码（5min）
        最终手段
```

**为什么这样排序**：先查已知问题（最快避免重复劳动），再确认硬件状态（寄存器不骗人），再系统排查（有方向），最后求助外部（耗时最长）。

**时间预算：15 分钟内找到根因。超过 15 分钟还在猜，说明流程没执行到位。**

**示例：DMA 只跑一轮**
```
问题：ADC DMA 采集一轮就停
  ├→ 查文档：solutions-log 搜 "DMA" → 没找到
  ├→ 搜网上：HAL_ADC_Start_DMA circular mode → ST Community 说 HAL 会覆盖 DMA 配置
  ├→ 读寄存器：DMA2_Stream0->CR = 0x00000000（CIRC 位没置位）
  ├→ 读源码：stm32f4xx_hal_adc.c 第 1461 行，HAL_DMA_Start_IT 重新初始化 DMA
  └→ 修复：在 HAL_ADC_Start_DMA 之后手动重新设置 CIRC 位 → 解决 → 记录
```

> 每一步的详细操作 → 见"调试方法论"对应章节

### 分层验证策略

当问题涉及多个模块时，不要从顶层猜——逐层验证，每层确认后再往上走：

```
1. 硬件层：寄存器值是否正确？（TIM->CNT 在变吗？DMA->CR EN 位？）
2. 驱动层：DMA 是否在搬数据？回调是否触发？
3. 数据层：缓冲区数据是否合理？（范围、频率、噪声）
4. 算法层：处理逻辑是否正确？（测量值、变换结果）
5. 显示层：渲染结果是否符合预期？（波形、文字、菜单）
```

**案例**：波形显示为尖刺 → 不是显示模块的 bug，是数据层的问题（多周期降采样混叠）。从数据层排查比从显示层猜快 10 倍。

---

## 调试方法论

### ① 修改前检查清单

修改 DMA/定时器/中断相关代码前，必须先读项目文档：

1. **技术规范**（`technical-spec.md`、`tech_spec` 等）→ 已知问题、外设配置
2. **开发日志 / 问题解决记录**（`solutions-log.md`、`dev-log.md` 等）→ 搜关键词
3. **死锁预防清单**（`deadlock-prevention.md`）→ 检查清单

> 文件名因项目而异，用 Glob 搜 `**/*spec*`、`**/*log*`、`**/*solution*` 定位。

#### 配置系统完整性检查

配置系统是最容易出问题的地方——设计了 API 但没有接通。每次修改配置相关代码时检查：

```
□ 每个 Config_Get*() 是否在 Init 中被调用？
□ 每个 Set*() 函数是否调用 Config_Set*() 同步回 Config？
□ Init 函数是否从 Config 读取而不是只用硬编码默认值？
□ Config_Set*() 是否在互斥锁内完成（或锁内拷贝）？
□ 定时器预分频是否使用 HAL_RCC_GetPCLKxFreq() 而不是硬编码？
```

**快速验证**：`grep -rn "Config_Get\|Config_Set" Core/Src/` — 如果只有 config.c 有调用，说明配置系统没接通。

#### 时钟频率硬编码扫描

```bash
# 搜索硬编码的时钟频率（应该用 HAL_RCC_GetPCLKxFreq() 替代）
grep -rn "84000000\|168000000\|42000000\|72000000" Core/Src/
```

如果找到硬编码值，说明定时器频率计算在时钟配置变更时会静默失效。

### ② STM32 系列差异

不同系列的寄存器名和 DMA 模型不同，用 HAL 宏（如 `DMA_SxCR_CIRC`）而不是硬编码地址。

| 系列 | DMA 模型 | GPIO 配置 | RCC 时钟门控 | 参考手册 |
|------|---------|-----------|-------------|---------|
| **F0/L0/G0** | Channel（无 Stream） | CRL/CRH | AHBENR/APBxENR | RM0360/RM0377/RM0444 |
| **F1** | Channel（无 Stream） | CRL/CRH | AHBENR/APBxENR | RM0008 |
| **F4/F7** | Stream + Channel | MODER | AHB1ENR/APBxENR | RM0090/RM0385 |
| **G4/L4** | Channel（无 Stream） | MODER | AHBxENR/APBxENR | RM0440/RM0351 |
| **H7** | Stream + Channel（DMA1/2 + BDMA） | MODER | AHBxENR/APBxENR | RM0433 |

**判断系列：** 看芯片型号第二位——`STM32F407` = F4 系列，`STM32L476` = L4 系列。或看 CubeMX 生成的 `stm32f4xx.h` 等头文件名。

### ③ 寄存器速查

调试时先读寄存器确认外设实际状态，不要猜。

| 外设 | 关键寄存器 | 看什么 |
|------|-----------|--------|
| **DMA** | CCR, CNDTR, CPAR, CMAR (F1/L0/G0) 或 CR, NDTR, PAR, M0AR (F4/F7/H7) | EN 位、传输计数、地址配置 |
| **TIM** | CR1, CR2, SMCR, ARR, PSC | 使能状态、主从模式、重装值 |
| **ADC** | SR/ISR, CR1/CR, CR2 | EOC/EOCS 标志、使能状态 |
| **USART** | SR/ISR, DR/RDR/TDR, BRR | TXE/RXNE 标志、波特率分频 |
| **I2C** | CR1, CR2, SR1/ISR, SR2/ISR | BUSY/AF 标志、时钟配置 |
| **SPI** | CR1, CR2, SR | BaudRate、CPOL/CPHA、TXE/RXNE |
| **RCC** | CR, CFGR, AHBENR/APBxENR (F0/L0) 或 AHB1ENR/APBxENR (F4/F7) | 时钟源使能、外设时钟使能 |
| **DAC** | CR, SWTRIGR, DHR12R1/2 | 使能、触发、数据保持 |
| **GPIO** | MODER/CRH+CRL, ODR, IDR, BSRR | 模式、输出/输入状态 |
| **NVIC** | ISER, ICER, IP | 中断使能、优先级 |

> **寄存器名因芯片系列而异。** 用 CubeMX 生成的代码中的宏名（如 `DMA_SxCR_CIRC`）而不是硬编码地址。HAL 头文件 `stm32f4xx.h`（或对应系列）里有完整定义。

```c
// 写完寄存器必须读回来确认（用 HAL 宏，跨系列兼容）
DMA2_Stream0->CR |= DMA_SxCR_CIRC;
if (!(DMA2_Stream0->CR & DMA_SxCR_CIRC)) {
    DBG("ERR: CIRC bit not set!");
}
// F1/L0 系列用 DMA_Channel_TypeDef:
// DMA1_Channel1->CCR |= DMA_CCR_CIRC;
```

**不读回来的后果：** HAL 可能覆盖、时钟没使能写入无效（不报错）、寄存器有写保护、硬件不响应。

### ④ 网上找资料

STM32 HAL 被全球几十万人用，你踩的坑大概率有人踩过。先搜 5 分钟，能省几天。

**搜索源优先级：**

| 优先级 | 来源 | 适用场景 |
|--------|------|---------|
| 1 | ST Community (community.st.com) | HAL bug、已知问题、Workaround |
| 2 | Stack Overflow | 代码级问题、配置方法 |
| 3 | GitHub Issues | 确认是否是 HAL bug |
| 4 | CSDN / 博客园 | CubeMX 配置、中文教程 |
| 5 | 项目里的 HAL 源码 | 最终真相来源 |

**关键词公式：** `HAL_<外设>_<函数名> <症状词>`

| 症状 | 关键词示例 |
|------|-----------|
| DMA 只跑一轮 | `HAL_ADC_Start_DMA circular mode` |
| DAC 欠载中断 | `HAL_DAC_Start_DMA underrun` |
| 回调不触发 | `HAL DMA callback not called` |
| I2C 总线锁死 | `stm32 I2C busy flag stuck` |
| UART 丢数据 | `stm32 UART RX overrun` |
| ADC 值跳动 | `stm32 ADC noisy reading` |
| 定时器不准 | `stm32 TIM period wrong` |
| 栈溢出 | `stm32 FreeRTOS stack overflow` |
| HardFault | `stm32 HardFault CFSR diagnosis` |
| Flash 写入失败 | `stm32 HAL_FLASH_Program error` |

**GitHub 无法访问时：** 镜像站 `github.moeyy.xyz`、`ghproxy.com`；或直接读项目里的 HAL 源码（不需要网络）。

**读 HAL 源码路径：**
```
Drivers/STM32F4xx_HAL_Driver/Src/stm32f4xx_hal_<外设>.c   ← F4 系列
Drivers/STM32F1xx_HAL_Driver/Src/stm32f1xx_hal_<外设>.c   ← F1 系列
Drivers/STM32L4xx_HAL_Driver/Src/stm32l4xx_hal_<外设>.c   ← L4 系列
```
> 路径中的 `F4xx` 随芯片系列变化。用 Glob 搜 `Drivers/*HAL_Driver/Src/*hal_<外设>.c` 定位。

- 从你调用的函数入口开始，跟踪底层调用
- 看它操作了哪些寄存器、回调何时触发
- 示例：`HAL_ADC_Start_DMA` 在 F4 源码第 1461 行调用了 `HAL_DMA_Start_IT`，会覆盖你手动配置的 DMA

### ⑤ HardFault 诊断

不要猜原因，读 Fault Status Register：

```c
// SCB 寄存器在所有 Cortex-M 上通用（M0/M0+/M3/M4/M7/M33）
void HardFault_Handler(void) {
    char buf[64];
    snprintf(buf, sizeof(buf), "HF CFSR:0x%lX HFSR:0x%lX\r\n", SCB->CFSR, SCB->HFSR);
    HAL_UART_Transmit(&huart1, (uint8_t*)buf, strlen(buf), 10);  // 改为你的串口句柄
    if (SCB->CFSR & 0x00800000) {  // MMARVALID
        snprintf(buf, sizeof(buf), "MMFAR:0x%lX\r\n", SCB->MMFAR);
        HAL_UART_Transmit(&huart1, (uint8_t*)buf, strlen(buf), 10);
    }
    if (SCB->CFSR & 0x00008000) {  // BFARVALID
        snprintf(buf, sizeof(buf), "BFAR:0x%lX\r\n", SCB->BFAR);
        HAL_UART_Transmit(&huart1, (uint8_t*)buf, strlen(buf), 10);
    }
    while (1);
}
```

| CFSR 位 | 含义 | 常见原因 |
|---------|------|---------|
| bit 1 DACCVIOL | 数据访问违规 | 空指针解引用、访问未映射地址 |
| bit 4 MSTKERR | 入栈错误 | 栈溢出 |
| bit 8 IBUSERR | 总线指令错误 | Flash 损坏、时钟未使能 |
| bit 9 PRECISERR | 精确数据总线错误 | 读 BFAR 获取故障地址 |
| bit 25 UNDEFINSTR | 未定义指令 | 函数指针损坏、栈溢出覆盖返回地址 |
| bit 30 FORCED | 强制 HardFault | 其他 Fault 处理函数未实现 |

**HardFault 调试步骤：**
1. 看串口输出的 CFSR 值
2. 查上表确定是哪种 Fault
3. 如果有 MMFAR/BFAR，用 map 文件定位代码位置
4. 常见根因：空指针、栈溢出、数组越界、未初始化函数指针

### ⑥ 栈溢出检测

**裸机：** 启动时在栈底填入 `0xDEADBEEF`，周期性检查是否被覆盖。

**FreeRTOS：** `configCHECK_FOR_STACK_OVERFLOW = 2`，实现 `vApplicationStackOverflowHook` 回调。

### ⑦ 中断优先级

- 数值越小 = 优先级越高
- HAL 默认所有中断优先级为 0（最高）——这是陷阱
- FreeRTOS 中调用 `FromISR` API 的中断必须 ≤ `configLIBRARY_MAX_SYSCALL_INTERRUPT_PRIORITY`

### ⑧ 外设初始化顺序

```
RCC 时钟使能 → GPIO 配置 → DMA 配置 → 外设配置 → 外设使能 → NVIC 中断使能
```

```c
// 以 ADC + DMA 为例
__HAL_RCC_ADC1_CLK_ENABLE();      // 1. 时钟使能
__HAL_RCC_DMA2_CLK_ENABLE();
HAL_GPIO_Init(GPIOA, &gpio_init); // 2. GPIO 配置
HAL_DMA_Init(&hdma_adc);          // 3. DMA 配置
__HAL_LINKDMA(&hadc1, DMA_Handle, hdma_adc); // 4. 关联 DMA
HAL_ADC_Init(&hadc1);             // 5. 外设配置
HAL_ADC_Start_DMA(&hadc1, buf, n); // 6. 启动
HAL_NVIC_EnableIRQ(DMA1_Stream5_IRQn); // 7. 中断使能
```

顺序错误不报错，但外设不工作。

### ⑧-b 互斥锁使用模式

FreeRTOS 项目中，共享资源必须用互斥锁保护。但锁的使用方式也有讲究：

**正确模式：锁内拷贝，锁外写入**
```c
// ✅ Config_Set*() 在锁外调用，但数据在锁内拷贝
SIGGEN_LOCK();
siggen_config.frequency = freq;
SigGen_ApplyConfig();
SigGenConfig_t cfg_copy = siggen_config;  // 锁内拷贝
SIGGEN_UNLOCK();
Config_SetSigGenConfig(&cfg_copy);  // 锁外写入（memcpy 很快）
```

**错误模式：锁外读取共享数据**
```c
// ❌ 另一个任务可能正在修改 siggen_config
SIGGEN_LOCK();
siggen_config.frequency = freq;
SIGGEN_UNLOCK();
Config_SetSigGenConfig(&siggen_config);  // 竞态！可能读到脏数据
```

**锁内避免阻塞操作**：`LOG_INFO` 最终调用 `HAL_UART_Transmit`（阻塞），不要在锁内调用。

### ⑧-c 低分辨率波形显示

OLED/小屏幕显示波形时，降采样算法决定显示质量：

**错误：取单点降采样**
```c
// ❌ 每像素列取 1 个采样点，多周期时不同相位连成尖刺
uint16_t y = data[x * step];
OLED_DrawLine(x, y, x+1, data[(x+1) * step], 1);
```

**正确：min/max 包络**
```c
// ✅ 每像素列找最小值和最大值，画竖线
uint16_t col_min = data[x * step], col_max = col_min;
for (uint16_t i = x * step + 1; i < (x+1) * step; i++) {
    if (data[i] < col_min) col_min = data[i];
    if (data[i] > col_max) col_max = data[i];
}
OLED_DrawLine(x, col_min, x, col_max, 1);
```

这是数字示波器的标准做法，无论波形有多少周期都能正确显示轮廓。

### ⑨ Error_Handler 改进

CubeMX 生成的是空死循环。替换为：

```c
// ⚠️ 方案 B 中 HAL_Delay 依赖 SysTick，时钟未初始化时用方案 A
// ⚠️ 把 &huart1 改为你的串口句柄（CubeMX 生成的那个）
void Error_Handler_File(uint32_t line) {
    char buf[32];
    snprintf(buf, sizeof(buf), "ERR:%lu\r\n", line);
    HAL_UART_Transmit(&huart1, (uint8_t*)buf, strlen(buf), 10);  // 改为你的串口
    while (1) { __NOP(); }  // 方案 A：纯串口
    // while (1) { HAL_GPIO_TogglePin(GPIOA, GPIO_PIN_5); HAL_Delay(100); }  // 方案 B：串口+LED
}
#define Error_Handler() Error_Handler_File(__LINE__)
```

### ⑩ 烧录后验证

| 检查项 | 方法 |
|--------|------|
| 编译时间戳 | main() 开头输出 `__DATE__` `__TIME__` |
| 增量编译问题 | 改了没效果时 Clean → Rebuild All |
| 复位是否生效 | 手动按复位键或串口看启动标记 |

**为什么需要复位：** Flash 编程时 CPU 暂停，写完后从暂停位置继续，不是从头开始。复位把 PC 拉到 Reset_Handler。

**复位不生效：** 看门狗使能、NRST 被拉低、Boot0 错误、SWD 复位被禁用。

**Keil：** Project → Options → Debug → ST-Link Settings → 勾选 "Reset after Download"
**STM32CubeIDE：** Run → Debug Configurations → Debugger → 勾选 "Reset board after programming"
**STM32CubeProgrammer：** 命令行加 `-rst` 参数

### ⑪ 选外设前查参考手册

嵌入式不能"先做再改"。选外设前查 RM0090 的：功能复用表、触发源列表、DMA 请求表、引脚复用表。

**案例：** TIM9 不能触发 ADC — RM0090 第 13 章明确写了。不查手册浪费两天。

### ⑫ CubeMX 重新生成会覆盖

手动配置写在 `USER CODE BEGIN/END` 之间。`.ioc` 是配置的唯一真相来源——不管用 Keil、STM32CubeIDE 还是 Makefile。生成后对照验证：DMA CIRC 位、MasterSlaveMode、UART 超时。

### ⑬ DBG 调试宏

```c
// ⚠️ 把 &huart1 改为你的串口句柄
#ifdef DEBUG_EN
    #define DBG(fmt, ...) do { \
        char _b[64]; snprintf(_b, sizeof(_b), fmt "\r\n", ##__VA_ARGS__); \
        HAL_UART_Transmit(&huart1, (uint8_t*)_b, strlen(_b), 10); \
    } while(0)
#else
    #define DBG(fmt, ...) ((void)0)
#endif
```

启动时输出：
```c
int main(void) {
    HAL_Init();
    SystemClock_Config();
    MX_GPIO_Init();
    MX_USART1_UART_Init();  // 串口必须先初始化
    // ↓ 第一行输出，确认是新代码
    DBG("BUILD: %s %s", __DATE__, __TIME__);
    DBG("SYSCLK: %lu Hz", HAL_RCC_GetSysClockFreq());
    // ... 其他初始化
}
```

### ⑭ 编译报错要读

编译器告诉你问题在哪，就读。`main.c(275): error: #20` → 直接打开第 275 行。

---

## 硬件调试基础

固件调试到尽头，可能是硬件问题。

### 电源问题

| 症状 | 可能原因 | 排查方法 |
|------|---------|---------|
| 芯片不工作 | LDO 输出不稳 | 万用表量 VCC 引脚电压 |
| ADC 值跳动 | 电源纹波大 | 示波器看 VCC 波形，加 100nF 去耦电容 |
| 偶发复位 | 瞬间掉电 | 示波器触发 VCC 下降沿 |
| 发热严重 | 短路或过载 | 红外测温或手摸，检查焊接 |

### 信号问题

| 接口 | 常见硬件问题 | 排查方法 |
|------|------------|---------|
| **I2C** | 缺上拉电阻、地址错误 | 示波器看 SDA/SCL 波形，逻辑分析仪抓地址 |
| **SPI** | CPOL/CPHA 不匹配、线太长 | 示波器看 CLK 和 MOSI 相位关系 |
| **UART** | TX/RX 接反、波特率偏差 | 示波器量 TX 波形测波特率 |
| **ADC** | 输入阻抗不匹配、参考电压不稳 | 万用表量 VREF，示波器看输入波形 |

### 焊接问题

| 症状 | 可能原因 | 排查方法 |
|------|---------|---------|
| 某个外设完全不工作 | 引脚虚焊 | 万用表测通断 |
| 随机 HardFault | BGA 空焊 | X 光检查（工厂级） |
| 电流异常 | 焊锡短路 | 放大镜检查 + 万用表测阻值 |

**何时用硬件工具：**
- 万用表：电压、通断、电阻
- 示波器：波形、时序、频率、信号完整性
- 逻辑分析仪：协议解码（I2C/SPI/UART 数据包）

**电源检查第一步（万用表）：**
1. 量 VCC 引脚：3.3V ±5%（3.14V ~ 3.47V）
2. 量 GND 引脚：确认接地通断
3. 量 VDDA（模拟电源）：和 VCC 一致
4. 量 BOOT0 引脚：必须拉低（GND），否则从 bootloader 启动

**I2C 不通排查：**
1. 万用表量 SDA/SCL 是否有上拉到 VCC（~3.3V）
2. 示波器看 SCL 有没有时钟输出
3. 逻辑分析仪抓地址，确认 7 位地址是否正确（注意左移 1 位）

## ⚠️ 时钟与死机预防

### 时钟配置验证（只读，不修改）

```bash
python clock_validator.py --ioc project.ioc
python tech_spec.py --auto . --text
```

### 死机/锁机预防

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

## 项目版本管理与恢复

嵌入式开发改错一步就可能死机。用 `version.py` 管理版本，出问题能秒回上一个正常版本。

### 版本状态概览

```bash
python version.py --auto . --status
# 显示：当前分支、最新提交、最新稳定版本、未提交更改、标签数、快照列表
```

### 自动打版本标签

```bash
# 功能完成后自动打标签（自动递增版本号）
python version.py --auto . --tag

# 带消息
python version.py --auto . --tag -m "ADC DMA 循环采集正常工作"

# 推送到远程
git push origin stable/v2
```

### 版本对比

```bash
# 对比当前和最新稳定版本
python version.py --auto . --diff

# 对比两个版本
python version.py --auto . --diff stable/v1 stable/v2

# 显示：变更文件列表、提交历史、差异统计
```

### 一键回退

```bash
# 回退到上一个稳定版本（自动备份当前状态）
python version.py --auto . --rollback

# 回退到指定版本
python version.py --auto . --rollback stable/v1

# 强制回退（丢弃未提交更改）
python version.py --auto . --rollback stable/v1 --force
```

### 保存编译产物快照

```bash
# 保存当前 .hex/.axf/.map 到 snapshots/ 目录
python version.py --auto . --snapshot

# 快照包含：编译产物 + 版本信息（git hash、提交消息）
```

### 列出所有版本

```bash
python version.py --auto . --list
# 显示：stable/backup/milestone/experiment 分类，日期，hash，消息
```

### 版本命名规范

| 类型 | 前缀 | 示例 | 用途 |
|------|------|------|------|
| 稳定版本 | `stable/` | `stable/v1` | 功能验证通过 |
| 改动前备份 | `backup/` | `backup/before-dac-dma` | 大改动前 |
| 里程碑 | `milestone/` | `milestone/all-peripherals-ok` | 阶段性成果 |
| 实验性 | `exp/` | `exp/double-buffer-try1` | 实验代码 |

### CubeMX 回退

```bash
# 回退 CubeMX 生成的文件（保留 USER CODE 区）
git checkout HEAD -- Core/Src/main.c Core/Inc/main.h
```

---

## 安全约束

| 约束 | 正常情况 | 死机恢复时 |
|------|---------|-----------|
| 全片擦除 | ❌ 不用 `-e`，用 sector erase | ✅ 可用 `-e all` |
| 写 Option Bytes | ❌ 除非用户明确要求 | ✅ 解除 RDP 需要 |
| 改读保护 RDP | ❌ 不动 | ✅ 需先解除（会擦除全片） |
| 烧录到硬件 | 需用户确认 | 需用户确认 |
| 代码修改 | 最小改动原则 | 最小改动原则 |

**判断条件：芯片能连上 SWD → 正常烧录（sector erase）。芯片完全锁死 → 先检查 RDP，再决定是否全片擦除。**
