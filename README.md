# STM32 Firmware Workflow

STM32 固件开发全流程自动化：编译 → 分析 → 烧录 → 调试 → 文档

支持全系列 STM32（F0/F1/F4/F7/G0/G4/L0/L4/H7）+ 多 IDE（Keil/CubeIDE/IAR）

## 功能特性

| 功能 | 说明 |
|------|------|
| 🔨 编译 | 自动编译，失败自动修复重编（最多 3 轮） |
| 📊 分析 | ELF 检查、静态分析、Flash/RAM 优化 |
| 🔥 烧录 | ST-LINK / USB DFU，7 种复位方法 |
| 🔄 开发循环 | 文件变化自动编译烧录（dev_loop.py） |
| 📡 串口调试 | 监控、交互、协议解析（VOFA+） |
| 🧪 串口测试 | JSON 测试用例，自动验证（serial_test.py） |
| 🐛 错误追踪 | 记录/搜索/导出，auto_fix 自动记录 |
| 📋 文档生成 | 技术规范、错误总结、开发日志 |
| 🛡️ 死机预防 | 烧录前检查时钟/NVIC/DMA/固件 |
| 🔧 嵌入式守则 | 13 条实战教训 + 14 节调试方法论 |
| 📖 文档读写 | 读/写/自动生成 Markdown 文档 |

## 快速开始

```bash
# 开发模式：改了就烧（推荐）
python dev_loop.py --auto . --port COM3

# 一键工作流：编译 + 分析
python workflow.py --auto . --steps compile,analyze

# 完整验证：编译 + 分析 + 优化 + 报告
python workflow.py --auto . --steps compile,analyze,optimize,report

# 烧录 + 复位
python workflow.py --auto . --steps flash,reset --port COM3
```

## 工具脚本

### 核心（每次开发必用）

| 脚本 | 功能 | 常用命令 |
|------|------|---------|
| `workflow.py` | 一键工作流 | `--auto . --steps compile,analyze` |
| `dev_loop.py` | 开发模式循环 | `--auto . --port COM3` |
| `serial_debug.py` | 串口调试 | `--port COM3 --proto printf --listen 30` |
| `serial_test.py` | 串口测试 | `--port COM3 --test tests.json` |
| `error_tracker.py` | 错误追踪 | `--record --error "xxx" --fix "xxx"` |
| `dev_log.py` | 开发日志 | `--auto . --add "功能完成"` |
| `version.py` | 版本管理 | `--auto . --status` / `--diff` / `--rollback` / `--tag` |
| `tech_spec.py` | 技术规范 | `--auto . --text` |

### 分析（按需使用）

| 脚本 | 功能 | 常用命令 |
|------|------|---------|
| `check_elf.py` | ELF 检查 | `--auto .` |
| `debug_sim.py` | 静态分析 | `--auto . --mode sim` |
| `optimize.py` | 优化分析 | `--auto .` |
| `auto_fix.py` | 编译错误修复 | `--auto . --auto-fix` |
| `brick_prevention.py` | 死机预防 | `--auto .` |

### 配置（偶尔使用）

| 脚本 | 功能 | 常用命令 |
|------|------|---------|
| `cubemx_config.py` | CubeMX 配置 | `--modify project.ioc --add-peripheral ADC1` |
| `pin_checker.py` | 引脚冲突 | `--ioc project.ioc` |
| `clock_validator.py` | 时钟验证 | `--ioc project.ioc` |
| `i2c_scanner.py` | I2C 总线扫描 | `--port COM3` |
| `reg_dump.py` | 外设寄存器转储 | `--auto . --peripheral GPIO,TIM` |
| `unit_test.py` | 单元测试 | `--auto . --generate` / `--run` |
| `power_analyzer.py` | 功耗分析 | `--auto .` |
| `isr_analyzer.py` | 中断延迟分析 | `--auto .` |
| `dma_analyzer.py` | DMA 性能分析 | `--auto .` |
| `adc_analyzer.py` | ADC 噪声分析 | `--auto . --data samples.bin` |

## 嵌入式工程师守则

### 硬约束（违反 = 必出问题）

| # | 守则 | 后果 |
|---|------|------|
| 1 | 时钟配置不能碰 | PLL/HSE/SYSCLK 代码中动了就死机 |
| 2 | Error_Handler 不能空死循环 | 必须有串口输出 |
| 3 | CubeMX 配置是基准 | 代码适配配置，不是反过来 |
| 4 | CubeMX 重新生成会覆盖 | 手动配置写在 USER CODE 区 |
| 5 | HAL 和寄存器不能混用 | 混用 = 两套状态机互相覆盖 |

### 最佳实践（不做 = 浪费时间）

| # | 守则 | 节省 |
|---|------|------|
| 6 | 先读文档，再动代码 | 避免重复踩坑 |
| 7 | 先搜，再试 | 搜 5 分钟省几天 |
| 8 | 碰到障碍要换路 | 死磕同一条路最贵 |
| 9 | 写完寄存器要读回来确认 | 不读 = 没写 |
| 10 | 烧录后先确认是新代码 | 先怀疑旧代码 |
| 11 | 选外设前查参考手册 | 不查手册 = 赌博 |
| 12 | 全量编译是最后手段 | 增量编译省 20 秒 |
| 13 | 每次修 bug 都记录 | 下次 5 秒解决 |

## 调试方法论

14 节调试方法论，覆盖嵌入式开发全场景：

① 修改前检查清单 → ② STM32 系列差异 → ③ 寄存器速查 → ④ 网上找资料 → ⑤ HardFault 诊断 → ⑥ 栈溢出检测 → ⑦ 中断优先级 → ⑧ 外设初始化顺序 → ⑨ Error_Handler 改进 → ⑩ 烧录后验证 → ⑪ 选外设前查参考手册 → ⑫ CubeMX 重新生成会覆盖 → ⑬ DBG 调试宏 → ⑭ 编译报错要读

## 自动化流程

### 开发模式（快速迭代）

```bash
python dev_loop.py --auto . --port COM3
# 改代码 → 自动编译 → 自动烧录 → 继续监控
```

### 串口测试（自动化验证）

```bash
python serial_test.py --port COM3 --test tests.json --report result.json
```

测试用例 JSON：
```json
{
  "name": "LED 控制测试",
  "tests": [
    {"name": "开灯", "send": "@LED_ON", "expect": "OK"},
    {"name": "查状态", "send": "@STATUS", "expect_contains": "LED:ON"}
  ]
}
```

### 文档自动生成

```bash
python dev_log.py --auto . --from-git                  # git → 日志
python dev_log.py --auto . --from-errors               # 错误 → 日志
python error_tracker.py --export solutions-log.md      # 导出问题解决记录
python tech_spec.py --auto . --output tech-spec.md     # 生成技术规范
```

## 版本管理

```bash
# 版本状态概览
python version.py --auto . --status

# 自动打版本标签
python version.py --auto . --tag -m "ADC DMA 正常工作"

# 对比版本差异
python version.py --auto . --diff

# 一键回退
python version.py --auto . --rollback

# 保存编译产物快照
python version.py --auto . --snapshot
```

## 安装依赖

### 必需
- Python 3.8+
- Keil MDK-ARM 或 STM32CubeIDE 或 IAR

### 可选
- [STM32CubeProgrammer](https://www.st.com/en/development-tools/stm32cubeprog.html) - 烧录
- [Renode](https://renode.io/) - 无硬件仿真
- [STM32CubeMX](https://www.st.com/en/development-tools/stm32cubemx.html) - 代码生成
- pyserial - 串口通信 (`pip install pyserial`)

## 许可证

MIT License
