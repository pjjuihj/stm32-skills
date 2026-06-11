# STM32 Keil Workflow Skill

让 AI Agent 自动处理 Keil MDK-ARM + STM32 固件工程的全流程。

## 功能特性

| 功能 | 说明 |
|------|------|
| 🔨 **编译** | 自动编译 Keil 项目，解析并修复编译错误 |
| 📊 **静态分析** | 检查 ELF 文件、中断向量表、栈堆大小 |
| ⚡ **代码优化** | 分析 Flash/RAM 使用率，给出优化建议 |
| 🎮 **Renode 仿真** | 无硬件仿真验证固件启动和 UART 输出 |
| 🔥 **烧录** | 烧录程序到 STM32 芯片 |
| 📡 **串口验证** | 监控串口数据，验证固件运行 |
| 🔄 **回归检测** | 对比修改前后的分析结果，检测问题 |
| 🚀 **一键分析** | 全自动执行以上所有步骤 |

## 快速开始

### 一行命令编译
```bash
UV4.exe -b "project.uvprojx" -t "project_led" -o build.log -j0
```

### 一行命令完整分析
```bash
python check_elf.py --elf project.axf --uv4 D:/k5/UV4/UV4.exe
python debug_sim.py --elf project.axf --mode sim --uv4 D:/k5/UV4/UV4.exe
python optimize.py --elf project.axf --uv4 D:/k5/UV4/UV4.exe --project project.uvprojx
python renode_sim.py --elf project.axf --mode boot --timeout 5
```

### 一行命令串口测试
```bash
python serial_monitor.py --port COM3 --baud 115200 --mode monitor --duration 10
```

## 核心流程

```
① 读取项目记忆 → ② 编译 → ③ 解析错误/修复 → ④ 静态分析验证 → ⑤ 代码优化分析 → ⑥ Renode 仿真 → ⑦ 烧录 → ⑧ 串口验证 → ⑨ 逻辑检查
     ↑                    ↓                                                                  ↓
     └──── 修复后重新编译 ───┘              ← 如果逻辑偏移，修改代码重来 ←──────────────────────┘
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

## 安装依赖

### 必需
- Python 3.8+
- Keil MDK-ARM (UV4.exe)

### 可选
- [Renode](https://renode.io/) - 无硬件仿真
- [STM32CubeProgrammer](https://www.st.com/en/development-tools/stm32cubeprog.html) - 烧录工具

## 使用场景

1. **新项目验证** - 编译后自动检查固件正确性
2. **代码优化** - 分析 Flash/RAM 使用率，找出大函数
3. **问题排查** - 静态分析检查中断向量表、栈堆配置
4. **回归测试** - 修改代码后对比分析结果
5. **串口调试** - 监控固件输出，验证功能

## 注意事项

- 编译错误修复遵循**最小改动原则**
- 烧录前必须先进行**静态分析验证**
- 不会执行全片擦除或修改 Option Bytes
- 支持 VOFA+ 等串口协议解析

## 许可证

MIT License