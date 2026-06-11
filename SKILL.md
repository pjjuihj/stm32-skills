---
name: stm32-keil-workflow
description: >
  STM32 firmware development automation: build, flash, analyze, optimize, simulate, generate code.
  Trigger when user mentions: Keil, UV4, uVision, STM32 compile/build/flash/debug,
  firmware analysis, code optimization, FreeRTOS, serial port testing, regression detection.
  Also trigger for: .uvprojx projects, Cortex-M development, ST-LINK/SWD,
  ELF/AXF/HEX analysis, "full analysis", Renode simulation, serial protocol debugging,
  "write code for STM32", "implement function", "add task", "add feature".
  Capabilities: build (UV4), static analysis (vector table/stack/heap/symbols),
  optimization (Flash/RAM/compiler/quality/cppcheck/stack/complexity/Cortex-M),
  Renode sim (boot/UART), regression detection (symbol/section/behavior diff + history trend),
  serial verify (5 modes/5 protocols), flash (ST-LINK/SWD), code generation + compile verification.
---

# STM32 Keil Workflow

让 AI Agent 自动处理 Keil MDK-ARM + STM32 固件工程的全流程。

## 目录

- [快速开始](#快速开始)
- [工具一览](#已有技能复用)
- [① 读取项目记忆](#第一优先级读取项目记忆)
- [② 编译流程](#编译流程)
- [③ 静态分析验证](#静态分析验证流程)
- [④ 代码优化分析](#代码优化分析流程)
- [⑤ Renode 仿真](#renode-仿真流程)
- [⑥ 烧录流程](#烧录流程)
- [⑦ 串口验证](#串口验证流程)
- [⑧ 回归检测](#回归检测流程)
- [⑨ 逻辑验证](#逻辑验证流程)
- [一键全自动流程](#一键全自动流程)
- [调试排查](#调试排查)

## 快速开始

**一行命令编译：**
```bash
UV4.exe -b "project.uvprojx" -t "project_led" -o build.log -j0
```

**一行命令完整分析：**
```bash
# 先编译，然后依次运行
python check_elf.py --elf project.axf --uv4 D:/k5/UV4/UV4.exe
python debug_sim.py --elf project.axf --mode sim --uv4 D:/k5/UV4/UV4.exe
python optimize.py --elf project.axf --uv4 D:/k5/UV4/UV4.exe --project project.uvprojx
python renode_sim.py --elf project.axf --mode boot --timeout 5
```

**一行命令串口测试：**
```bash
python serial_monitor.py --port COM3 --baud 115200 --mode monitor --duration 10
```

**核心流程：** 读项目记忆 → 编译 → 解析错误/修复 → 静态分析验证 → 代码优化分析 → Renode 仿真 → 烧录 → 串口验证 → 逻辑检查

```
① 读取项目记忆 → ② 编译 → ③ 解析错误/修复 → ④ 静态分析验证 → ⑤ 代码优化分析 → ⑥ Renode 仿真 → ⑦ 烧录 → ⑧ 串口验证 → ⑨ 逻辑检查
     ↑                    ↓                                                                  ↓
     └──── 修复后重新编译 ───┘              ← 如果逻辑偏移，修改代码重来 ←──────────────────────┘
```

## 代码生成与验证流程

当用户提出功能需求时，按以下流程编写代码并编译验证。

### 步骤 1：理解需求

- 功能描述：用户想要什么功能
- 输入输出：数据从哪来，输出到哪
- 约束：实时性、内存、引脚、协议等
- 优先级：必须/应该/可以

### 步骤 2：分析现有代码

- 读取相关源文件，了解现有架构
- 确定修改位置（哪个文件、哪个函数）
- 检查依赖关系（头文件、外设配置）

### 步骤 3：编写/修改代码

- 遵循项目现有代码风格
- 最小改动原则：只改必须改的
- 添加必要的注释
- 如果需要新文件，在正确的目录创建

### 步骤 4：编译验证

```bash
cd <MDK-ARM目录> && <UV4> -b <.uvprojx> -t <Target> -o build.log -j0
```

### 步骤 5：处理编译错误

如果编译失败：
1. 读取 build.log，提取 error 行
2. 分析错误类型（参考"编译错误处理策略"）
3. 修复错误
4. 重新编译
5. 重复直到成功或超过 3 次

### 步骤 6：静态分析验证

```bash
python <skill-path>/scripts/check_elf.py --elf <.axf> --uv4 <UV4>
python <skill-path>/scripts/debug_sim.py --elf <.axf> --mode sim --uv4 <UV4>
```

### 步骤 7：输出结果

- 报告修改了哪些文件
- 编译结果（错误/警告数）
- 静态分析结果
- 如果有优化建议，一并报告

### 示例

用户需求：添加一个 LED 闪烁任务

```
1. 读取 Core/Src/freertos.c，了解现有任务结构
2. 在 freertos.c 中添加 LED_BlinkTask 函数
3. 在 MX_FREERTOS_Init() 中创建任务
4. 编译验证
5. 静态分析验证
6. 输出：新增 LED_BlinkTask，栈 256 字节，优先级 Low，编译 0 Error
```

## 已有技能复用

| 任务 | 技能 | 脚本 |
|------|------|------|
| 编译 | `build-keil` | `scripts/keil_builder.py` |
| 烧录 | `flash-keil` | `scripts/keil_flasher.py` |
| 串口 | `serial-monitor` | `scripts/serial_monitor.py` |
| ELF 检查 | 本技能 | `scripts/check_elf.py` |
| 静态分析 | 本技能 | `scripts/debug_sim.py` |
| 代码优化 | 本技能 | `scripts/optimize.py` |
| Renode 仿真 | 本技能 | `scripts/renode_sim.py` |
| 回归检测 | 本技能 | `scripts/compare.py` |
| 串口验证 | 本技能 | `scripts/serial_monitor.py` |
| 配置检测 | 本技能 | `scripts/detect_config.py` |

### 脚本速查

| 脚本 | 常用命令 |
|------|---------|
| `check_elf.py` | `--elf project.axf --uv4 D:/k5/UV4/UV4.exe --symbols "main,HAL_Init"` |
| `debug_sim.py` | `--elf project.axf --mode sim --uv4 D:/k5/UV4/UV4.exe` |
| `optimize.py` | `--elf project.axf --uv4 D:/k5/UV4/UV4.exe --project project.uvprojx --src-dir ../Core/Src` |
| `renode_sim.py` | `--elf project.axf --mode boot --timeout 5 --renode C:/Renode/renode.exe` |
| `compare.py` | `--baseline snapshots/baseline/ --current snapshots/current/ --report diff.md` |
| `serial_monitor.py` | `--port COM3 --baud 115200 --mode monitor --duration 10` |

## 第一优先级：读取项目记忆

在执行任何操作前，必须先读取项目本地配置：

1. 查找项目记忆文件（按优先级）：
   - `CLAUDE.md`
   - `.claude/memory/MEMORY.md`
   - 项目根目录下的 `project-memory.md`（参考 `references/project-memory-template.md`）
   - `docs/superpowers/specs/` 和 `docs/superpowers/plans/`
   - `.vscode/c_cpp_properties.json`（获取 include 路径和宏定义）

2. 从中提取：
   - UV4.exe 路径、STM32_Programmer_CLI 路径
   - 项目 .uvprojx 文件路径、Target 名称（Debug/Release）
   - 芯片型号、ST-LINK 连接模式、SWD 频率
   - 串口号、波特率
   - 需要保护的 Flash 区域

3. 如果项目没有记忆文件，提示用户创建（参考 `references/project-memory-template.md`）

4. 路径回退：如果记忆中的路径不存在，尝试 `where` 命令查找，或提示用户

## 编译流程

1. 使用 UV4.exe 编译：
   ```bash
   cd <MDK-ARM目录> && <UV4> -b <.uvprojx> -t <Target> -o build.log -j0
   ```

2. 如果编译成功（返回码 0）→ 进入静态分析验证

3. 如果编译失败 → 解析错误并尝试修复（参考"编译错误处理策略"）

## 编译错误处理策略

### 自动修复流程

```
编译失败 → 解析错误 → 修复前逻辑快照 → 执行修复 → 编译验证 → 修复后逻辑检查 → 成功/失败
```

### 步骤 1：解析错误

从 build.log 中提取 error 行（格式：`file.c(line): error: message`）。

### 步骤 2：修复前逻辑快照

在修改代码前，记录关键信息（用于后续逻辑检查）：
- 修改位置的上下文（前后 5 行）
- 函数签名、变量类型、控制流结构
- 与修改相关的逻辑关系

### 步骤 3：执行修复

按错误类型选择修复策略：

| 错误类型 | 修复方式 | 逻辑保护要点 |
|---------|---------|-------------|
| `undefined reference` | 添加头文件/声明/链接 | 不改变函数调用关系 |
| `undeclared identifier` | 添加声明/修复拼写 | 不引入新变量 |
| `implicit declaration` | 添加函数声明 | 声明必须匹配实际定义 |
| `expected ';'` 等语法 | 定位行号修复语法 | 不改变语句逻辑 |
| `multiple definition` | 改 `extern` 或加 `static` | 不改变变量可见性语义 |
| `type mismatch` | 类型转换/修复签名 | 不改变数据语义 |
| `armclang error` | 检查编译器兼容性 | 不改变功能行为 |
| `portmacro.h not found` | 用 GCC port 替代 RVDS | 不改变 RTOS 行为 |

### 步骤 4：逻辑保护检查

修复后，验证代码逻辑未被改变：

1. **结构检查**：控制流（if/else/for/while）结构未改变
2. **接口检查**：函数签名、参数类型、返回值未改变
3. **语义检查**：变量赋值、计算逻辑、条件判断未改变
4. **依赖检查**：头文件包含、extern 声明未引入冲突

### 步骤 5：逻辑错误检测

在修复过程中，同时检测以下逻辑错误：

| 逻辑错误类型 | 检测方式 |
|-------------|---------|
| 死代码 | 修复后检查是否有不可达代码 |
| 未使用变量 | 修复后检查是否有未使用的声明 |
| 类型溢出 | 检查赋值是否超出变量类型范围 |
| 空指针风险 | 检查指针使用前是否有 NULL 检查 |
| 数组越界 | 检查数组访问是否在边界内 |
| 栈溢出风险 | 检查局部变量是否过大（>1KB） |
| 中断安全 | 检查共享变量是否有 volatile 或临界区保护 |

### 步骤 6：重新编译

修复后重新编译验证。重复直到成功或超过 3 次。

### 修复原则

- **最小改动**：只改必须改的，不顺手重构
- **逻辑不变**：修复必须保持原有逻辑行为
- **一次一个**：一次只修一个错误，重新编译验证
- **记录完整**：每次修复记录：改了哪个文件、哪一行、为什么改、逻辑是否改变
- **全部修复**：持续修复直到所有编译错误消除，不设上限
- **循环保护**：如果同一个错误反复出现（修复后又报错），分析根因并报告用户

## 静态分析验证流程

编译成功后，在烧录到硬件之前，通过静态分析验证固件正确性。

**为什么叫"静态分析"而不是"仿真"：** Keil UV4 命令行模式只支持编译（`-b`），不支持交互式仿真调试。真正的 CPU 仿真需要在 Keil IDE 中启动 Debug Session。因此本步骤使用 fromelf 工具和代码审查进行静态验证，这比"伪仿真"更诚实也更实用。

### 步骤 1：ELF 产物检查

```bash
python <skill-path>/scripts/check_elf.py --elf <.axf路径> --uv4 <UV4路径> [--symbols "main,HAL_Init"]
```

- 确认 ELF 生成正确（文件存在、格式有效）
- 检查段大小是否合理（text/data/bss）
- Flash/RAM 使用率是否在安全范围内
- 记录关键符号地址作为基线

### 步骤 2：深度静态分析

```bash
python <skill-path>/scripts/debug_sim.py --elf <.axf路径> --mode sim --uv4 <UV4路径>
```

自动检查以下项目：

| 检查项 | 说明 | 判定标准 |
|--------|------|---------|
| 中断向量表 | 检查前 16 个 Cortex-M 异常向量是否有效 | 所有向量必须指向 Flash 区间 (0x08xxxxxx) |
| 栈大小 | 检查 Stack_Size 符号 | 应 ≥ 0x400 (1KB)，FreeRTOS 项目应 ≥ 0x800 |
| 堆大小 | 检查 Heap_Size 符号 | 应 ≥ 0x200 (512B) |
| HardFault_Handler | 是否存在硬故障处理函数 | 必须存在且地址有效 |
| main 入口 | main 函数是否存在且地址合理 | 应在 Flash 区间内 |
| FreeRTOS port | 使用 GCC port 而非 RVDS port | ARMClang 不兼容 RVDS 语法 |

### 步骤 3：代码逻辑审查（按需）

如果项目有特定需求（如外设初始化、任务创建），读取关键源文件进行审查：

- `main.c`：初始化顺序、外设配置、时钟配置
- `freertos.c`：任务栈大小、优先级分配
- 中断处理函数：是否有未处理的中断

### 步骤 4：判定

- 所有检查通过 → 进入代码优化分析
- 发现异常 → 定位问题，修改代码，重新编译

## 代码优化分析流程

静态分析通过后，分析固件的资源使用和代码质量，给出可操作的优化建议。

```bash
python <skill-path>/scripts/optimize.py --elf <.axf路径> --uv4 <UV4路径> --project <.uvprojx路径> [--src-dir <源码目录>]
```

### 分析维度

| 维度 | 检查项 | 说明 |
|------|--------|------|
| **memory** | Flash/RAM 使用率 | 计算百分比，超过 80% 告警 |
| | Top-20 最大函数 | 按 size 排序，>4KB 的函数给出优化建议 |
| | LTO 状态 | 检查链接时优化是否启用 |
| | CCM RAM 利用 | 检查 64KB 快速 RAM 是否被使用 |
| **compiler** | 优化级别 | -O0 到 -Omax，给出级别建议 |
| | 优化目标 | size vs time |
| | LTO 开关 | 启用可减少 5-15% 代码体积 |
| | 警告级别 | 建议 ≥ 3 |
| **quality** | cppcheck 扫描 | 自动检测（如果已安装） |
| | extern 声明位置 | 函数体内的 extern 应移到头文件 |
| | Magic numbers | 未命名的数字常量 |
| **performance** | FreeRTOS 栈大小 | 任务栈是否合理 |
| | 共享变量保护 | 临界区使用情况 |
| | ISR 浮点运算 | 中断上下文中的浮点操作 |

### 输出格式

JSON 输出，包含 `recommendations` 数组，按优先级排序：
- **HIGH**: 需要立即处理（Flash/RAM >80%、栈溢出风险）
- **MEDIUM**: 建议优化（LTO 未启用、大函数、cppcheck 问题）
- **LOW**: 代码风格（magic numbers、extern 位置）

### 判定

- 无 HIGH 优先级建议 → 进入 Renode 仿真
- 有 HIGH 建议 → 评估是否需要修改代码或调整编译设置

## Renode 仿真流程

静态分析通过后，使用 Renode 进行无硬件仿真测试，验证固件实际执行行为。

**为什么需要 Renode 仿真：** 静态分析只能检查 ELF 文件结构，无法验证固件运行时行为。Renode 是开源的嵌入式系统仿真器，支持 STM32F4 外设仿真（UART、GPIO、I2C、定时器等），可以在无硬件情况下验证固件能否正常启动和通信。

**依赖：** 需要安装 Renode（https://renode.io）。如果未安装，跳过此步骤并提示用户。

### 步骤 1：启动验证

```bash
python <skill-path>/scripts/renode_sim.py --elf <.axf路径> --mode boot --timeout 5
```

- 验证固件能否正常启动（CPU PC 寄存器从入口地址推进）
- 检查仿真是否正常完成（无 HardFault、无死循环）
- 如果启动失败 → 检查启动文件、时钟配置、中断向量表

### 步骤 2：UART 输出捕获（按需）

```bash
python <skill-path>/scripts/renode_sim.py --elf <.axf路径> --mode uart --timeout 10
```

- 捕获 USART1 输出（如果固件有 printf/UART 输出）
- 验证输出内容是否符合预期
- 如果无输出 → 检查 UART 初始化、波特率配置

### 步骤 3：判定

- 启动验证通过 → 进入硬件烧录
- 启动失败 → 定位问题（可能是启动代码、时钟配置、栈溢出），修改后重新编译
- UART 有输出 → 验证输出内容是否合理
- Renode 未安装 → 跳过仿真，直接进入烧录（提示用户可安装 Renode 获得仿真能力）

## 烧录流程

仿真验证通过后，烧录到硬件：

1. 调用 `flash-keil` 的烧录脚本：
   ```bash
   python <flash-keil-path>/scripts/keil_flasher.py --detect --flash --project <.uvprojx> --target <Target>
   ```

2. 或使用 STM32_Programmer_CLI 直接烧录：
   ```bash
   STM32_Programmer_CLI.exe -c port=SWD mode=UR freq=4000 -w <.axf> -v -rst
   ```

3. 检查烧录结果：`verified` 或 `Download verified successfully` 表示成功

4. 烧录失败时：
   a. 检查是否有其他程序占用 ST-LINK（STM32CubeIDE debug、CubeProgrammer、OpenOCD）
   b. 检查 USB 连接和目标板供电
   c. 尝试不同连接模式（UR → HotPlug → NORMAL）

### 安全约束

- **不全片擦除**（不使用 `-e` 标志）
- **不写 Option Bytes**
- **不改读保护**（RDP）
- **不擦除校准页或参数页**
- **不在用户未确认的情况下烧录到硬件**（先仿真）
- 编译错误修复遵循最小改动原则

## 串口验证流程

烧录成功后，通过串口验证固件运行。

### 列出可用串口

```bash
python <skill-path>/scripts/serial_monitor.py --list
```

### 模式 1：数据监听

持续接收并显示固件输出：

```bash
python <skill-path>/scripts/serial_monitor.py --port COM3 --baud 115200 --mode monitor --duration 10 --protocol text
```

### 模式 2：命令发送/响应验证

发送命令并验证响应：

```bash
python <skill-path>/scripts/serial_monitor.py --port COM3 --baud 115200 --mode send --send "T\r" --wait 2
```

### 模式 3：协议解析

按 VOFA+ 或自定义协议解析数据：

```bash
# VOFA+ FireWater（逗号分隔浮点数）
python <skill-path>/scripts/serial_monitor.py --port COM3 --baud 115200 --mode parse --protocol vofa-firewater --duration 10

# VOFA+ JustFloat（二进制浮点数帧）
python <skill-path>/scripts/serial_monitor.py --port COM3 --baud 115200 --mode parse --protocol vofa-justfloat --duration 10
```

### 模式 4：自动化测试

从 JSON 文件加载测试用例，自动发送命令并验证响应：

```bash
python <skill-path>/scripts/serial_monitor.py --port COM3 --baud 115200 --mode test --test-file tests.json
```

测试用例格式：
```json
[
  {"name": "查询状态", "send": "S\r", "expect": "OK", "timeout": 2},
  {"name": "触发测试", "send": "T\r", "expect": "PASS", "timeout": 5}
]
```

### 模式 5：稳定性测试

长时间运行，检测丢包、乱码、数据间隔异常：

```bash
python <skill-path>/scripts/serial_monitor.py --port COM3 --baud 115200 --mode stress --duration 60 --protocol text
```

### 支持的协议

| 协议 | 说明 |
|------|------|
| `raw` | 原始字节（十六进制 + ASCII） |
| `text` | 文本行（\r\n 分隔） |
| `vofa-firewater` | VOFA+ FireWater（逗号分隔浮点数） |
| `vofa-justfloat` | VOFA+ JustFloat（二进制浮点数帧） |
| `custom` | 自定义帧格式（`--frame-header`/`--frame-tail`/`--frame-size`） |

## 逻辑验证流程

代码修改后，验证逻辑是否偏移：

1. **编译产物对比**：用 `check_elf.py` 对比符号地址变化
   - 符号地址偏移 < 0x100 → 正常（代码增减导致）
   - 符号地址大幅偏移 → 可能有问题

2. **静态分析对比**：用 `debug_sim.py --mode sim` 检查 ELF 信息
   - 段大小变化是否合理
   - 新增/消失的符号

3. **串口响应对比**：用 `serial-monitor` 发送相同命令，对比响应
   - 响应格式是否一致
   - 数据值是否合理

4. **偏移判定标准**：
   - 变量值变化但符合预期（如修复了 bug）→ 正常
   - 变量值变为 NaN/0xFFFF/异常值 → 问题
   - 新增 crash/hardfault → 严重问题
   - 串口响应格式改变 → 需要确认

## 调试排查

当烧录或运行出现问题时：

### ST-LINK 连接失败

1. 检查是否有其他程序占用（STM32CubeIDE、CubeProgrammer、OpenOCD、pyOCD）
2. 检查 USB 连接和目标板供电
3. 尝试不同连接模式

### 固件不运行

1. 用 `debug_sim.py --mode hw --read-ram 0x20000000 256` 检查 RAM
2. 检查栈是否溢出
3. 检查中断向量表

### 串口无响应

1. 确认 COM 口和波特率
2. 检查 TX/RX 接线
3. 检查固件是否正常启动

### I2C/SPI 通信失败

1. 检查上拉电阻
2. 检查时钟配置
3. 用逻辑分析仪确认波形

## 编辑器说明

本技能与编辑器无关：Zed、Cursor、VS Code、STM32CubeIDE、Keil、纯终端均可使用。

- 编译、烧录、调试是终端/工具链操作，不是编辑器操作
- 避免让编辑器对 `Drivers/`、`.git/`、大型 PDF 做无差别索引
- 使用终端命令精确检查构建产物、ELF 和工具链路径

## 一键全自动流程

当用户说"一键分析"、"full analysis"、"完整分析"或类似请求时，执行以下全自动流程。

### 执行步骤

按顺序执行，每步收集输出用于最终报告：

**步骤 1：读取项目记忆**
- 从 `.vscode/c_cpp_properties.json` 或 `.uvprojx` 提取配置
- 记录：芯片型号、UV4 路径、项目文件、Target、源码目录

**步骤 2：编译**
```bash
cd <项目MDK-ARM目录> && <UV4> -b <.uvprojx> -t <Target> -o build_log.txt -j0
```
- 读取 build_log.txt，提取错误/警告数、程序大小

**步骤 3：ELF 检查**
```bash
python <skill-path>/scripts/check_elf.py --elf <.axf> --uv4 <UV4> --symbols "main,HAL_Init,HardFault_Handler"
```

**步骤 4：静态分析**
```bash
python <skill-path>/scripts/debug_sim.py --elf <.axf> --mode sim --uv4 <UV4>
```

**步骤 5：优化分析**
```bash
python <skill-path>/scripts/optimize.py --elf <.axf> --uv4 <UV4> --project <.uvprojx> --src-dir <源码目录>
```

**步骤 6：Renode 仿真**（如果 Renode 可用）
```bash
python <skill-path>/scripts/renode_sim.py --elf <.axf> --mode boot --timeout 5 --renode <Renode路径>
```

### 报告模板

执行完成后，生成以下 Markdown 报告并保存到项目根目录 `analysis_report.md`：

```markdown
# STM32 固件分析报告
> 项目: <项目名> | 芯片: <芯片型号> | 日期: <日期>

## ① 编译结果
| 项目 | 值 |
|------|-----|
| 状态 | ✅ 成功 / ❌ 失败 |
| 错误数 | X |
| 警告数 | X |
| Code | X bytes |
| RO-data | X bytes |
| RW-data | X bytes |
| ZI-data | X bytes |

## ② ELF 检查
| 段 | 大小 | 状态 |
|----|------|------|
| Flash | X KB | ✅/⚠️/❌ |
| RAM | X KB | ✅/⚠️/❌ |

关键符号：
| 符号 | 地址 | 大小 |
|------|------|------|

## ③ 静态分析
| 检查项 | 结果 |
|--------|------|
| 中断向量表 | ✅/❌ |
| 栈/堆大小 | ✅/❌ |
| 关键符号 | ✅/❌ |
| 符号总数 | X |

## ④ 优化分析
### Flash/RAM 使用率
| 资源 | 已用 | 总量 | 使用率 | 状态 |
|------|------|------|--------|------|

### Top-5 最大函数
| 函数 | 大小 |
|------|------|

### 编译器设置
| 设置 | 值 | 建议 |
|------|-----|------|

### 优化建议
按优先级列出所有建议。

## ⑤ Renode 仿真
| 检查项 | 结果 |
|--------|------|
| CPU 初始化 | ✅/❌ |
| 固件启动 | ✅/❌ |
| 看门狗 | ✅/⚠️ |

## ⑥ 综合评估
- 总体状态: ✅/⚠️/❌
- 关键问题: 列出 HIGH 优先级问题
- 建议: 列出最优先的改进建议
```

## 回归检测流程

修改代码后，对比"修改前"和"修改后"的分析结果，检测是否引入问题。支持历史趋势追踪。

### 保存快照

```bash
# 保存当前分析结果到历史目录（自动时间戳）
python <skill-path>/scripts/compare.py --save --history-dir history/ \
  --elf-data check_elf.json --sim-data debug_sim.json --opt-data optimize.json
```

### 对比两个快照

```bash
# 对比基线和当前
python <skill-path>/scripts/compare.py --baseline history/v1/ --current history/v2/ --report diff.md
```

### 列出历史快照

```bash
python <skill-path>/scripts/compare.py --list --history-dir history/
```

### 分析历史趋势

```bash
# 分析 Flash/RAM/符号数量的历史变化趋势
python <skill-path>/scripts/compare.py --trend --history-dir history/ --report trend.md
```

趋势报告包含：
- Flash 使用趋势（最小/最大/最新/变化量）
- RAM 使用趋势
- 符号数量变化
- 优化建议数量变化
- 段大小异常变化告警

### 对比维度

| 维度 | 检测内容 | 判定标准 |
|------|---------|---------|
| 符号/地址 | 新增/消失/偏移/大小变化 | 偏移 > 0x100 = 警告 |
| 段大小 | Code/RO/RW/ZI 变化 | > 10% = 警告，> 30% = 错误 |
| 仿真行为 | 启动测试、事件变化 | PASS->FAIL = 错误 |
| 优化建议 | 新增/已修复的问题 | 信息级 |

### 输出

- **JSON**：结构化对比数据
- **Markdown 报告**：`regression_report.md`，包含段大小对比表、符号变化列表、问题汇总

## Git 上传说明

### 首次上传到 GitHub

1. **初始化本地仓库**（如果还不是 Git 仓库）：
   ```bash
   cd <skill目录>
   git init
   git add -A
   git commit -m "feat: STM32 Keil Workflow skill"
   ```

2. **在 GitHub 创建仓库**：
   - 打开 https://github.com/new
   - 仓库名：`stm32-skills`（或自定义名称）
   - 选择 Private（推荐）
   - 点击 Create repository

3. **配置 Git 凭据管理器**（避免重复输入 token）：
   ```bash
   git config --global credential.helper store
   ```

4. **添加远程仓库并推送**：
   ```bash
   git remote add origin https://github.com/<用户名>/<仓库名>.git
   git push -u origin main
   ```
   系统会提示输入 Username 和 Password（token），输入一次后自动保存。

### CMD 截断问题解决

Windows CMD 对长命令有字符限制，token 可能被截断。解决方案：

**方案 1：使用 VS Code 终端**（推荐）
- VS Code 终端没有 CMD 截断限制
- 直接在 VS Code 中执行 `git push` 命令

**方案 2：使用 Git 凭据管理器**
```bash
git config --global credential.helper store
git remote set-url origin https://github.com/<用户名>/<仓库名>.git
git push -u origin main
```
输入一次 token 后自动保存。

**方案 3：使用 GitHub Desktop**
- 下载安装：https://desktop.github.com/
- 登录后添加本地仓库
- 点击 Publish Repository

### 安全注意事项

- **不要**将 token 直接写入文件（如 .bat、.sh、.md）
- **不要**将 token 提交到 Git 仓库
- **使用** Git 凭据管理器或 GitHub Desktop 自动管理认证
- **定期**更新 token（GitHub PAT 支持过期时间设置）

### 更新技能

修改技能后，提交并推送更新：
```bash
git add -A
git commit -m "feat: 描述修改内容"
git push
```
