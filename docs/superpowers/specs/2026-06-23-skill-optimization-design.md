# STM32 Keil Workflow 技能优化设计文档

**日期**: 2026-06-23
**状态**: 已批准
**范围**: 大范围优化（代码质量 + 输出格式 + 模板整理 + 测试目录）

---

## 1. 目标

消除代码重复、统一输出格式、整理项目结构，提升技能的可维护性和一致性。

## 2. 架构概览

```
scripts/
├── shared.py              ← 新增：共享模块
├── workflow.py            ← 修改：使用 shared.py
├── check_elf.py           ← 修改：使用 shared.find_fromelf()
├── debug_sim.py           ← 修改：使用 shared.find_fromelf()
├── optimize.py            ← 修改：使用 shared.CHIP_DB, 统一输出
├── auto_fix.py            ← 修改：统一输出格式
├── health_check.py        ← 修改：统一输出格式
├── code_gen.py            ← 修改：统一输出格式
├── serial_monitor.py      ← 修改：使用 shared.setup_encoding()
├── serial_debug.py        ← 不变
├── detect_config.py       ← 修改：使用 shared.CHIP_DB
├── tests/                 ← 新增：测试目录
│   ├── test_full_skill.py
│   ├── test_20_iterations.py
│   └── ...
└── ...其他脚本

templates/
├── _base/                 ← 新增：参数化基础模板
├── pwm_servo_smooth.json  ← 保留：代表模板
├── sensor_i2c.json        ← 保留
└── ...（从 120+ 精简到 ~20 个）
```

## 3. 共享模块 `shared.py`

### 3.1 职责

| 函数 | 来源 | 用途 |
|------|------|------|
| `find_fromelf(uv4_path)` | check_elf.py, debug_sim.py | 查找 fromelf 工具 |
| `find_programmer(path)` | debug_sim.py | 查找 STM32_Programmer_CLI |
| `CHIP_DB` | detect_config.py + optimize.py | 统一芯片数据库（180+ 条目） |
| `lookup_chip(device)` | detect_config.py | 查找芯片信息 |
| `output_result(data, args)` | 新增 | 统一输出格式化 |
| `setup_encoding()` | serial_monitor.py | 终端编码处理 |
| `run_script(name, args, timeout)` | workflow.py | 子进程调用 |

### 3.2 芯片数据库合并

```python
# detect_config.py 的 CHIP_DB 格式：
"STM32F407VE": (512, 192, 64, "F4")

# optimize.py 的 CHIP_MEMORY 格式：
"STM32F407VETx": {"flash_kb": 512, "ram_kb": 112, "ccm_kb": 64}

# 统一为：
"STM32F407VE": {"flash_kb": 512, "ram_kb": 192, "ccm_kb": 64, "series": "F4"}
```

## 4. 统一输出格式

### 4.1 原则

- 所有脚本默认输出 JSON
- 使用 `--text` 切换人类可读格式
- 交互式脚本（serial_monitor, serial_debug）保持文本默认

### 4.2 统一 JSON 结构

```json
{
  "success": true,
  "data": { ... },
  "warnings": [],
  "errors": [],
  "timestamp": "2026-06-23T12:00:00"
}
```

### 4.3 受影响的脚本

| 脚本 | 当前默认 | 改为 |
|------|---------|------|
| auto_fix.py | 文本 | JSON |
| health_check.py | 文本 | JSON |
| code_gen.py | 文本 | JSON |
| workflow.py | 文本 | JSON |
| serial_monitor.py | 文本 | 文本（不变） |
| serial_debug.py | 文本 | 文本（不变） |

### 4.4 实现

在 `shared.py` 中提供：
```python
def output_result(data: dict, args):
    """统一输出格式化。根据 --text 参数选择格式。"""
    if hasattr(args, 'text') and args.text:
        output_text(data)
    else:
        output_json(data)
```

## 5. 模板目录整理

### 5.1 分组精选

| 分组 | 保留的代表模板 | 删除数量 |
|------|--------------|---------|
| PWM/舵机 | pwm_servo_smooth.json, pwm_servo_pid.json | ~33 |
| 传感器 | sensor_i2c.json, sensor_adc.json, sensor_dht11.json | ~15 |
| 通信 | uart_comm.json, i2c_sensor.json, spi_sensor.json | ~10 |
| 显示 | oled_display.json, tft_st7735.json | ~5 |
| 电机 | pwm_motor.json, stepper_motor.json, encoder_motor.json | ~5 |
| 无线 | nrf24l01_wireless.json, lora_sx1278.json | ~3 |
| 其他 | freertos_basic.json, scope_siggen.json, usb_cdc.json | ~5 |

### 5.2 参数化基础模板

新增 `templates/_base/` 目录，包含参数化模板：

```json
{
  "name": "PWM Servo Control",
  "variables": {
    "SERVO_TYPE": "SG90",
    "PWM_TIM": "TIM2",
    "PWM_CHANNEL": "CH1",
    "PWM_PIN": "PA0"
  }
}
```

## 6. 测试目录整理

### 6.1 移动测试文件

```
scripts/test_full_skill.py       → scripts/tests/test_full_skill.py
scripts/test_20_iterations.py    → scripts/tests/test_20_iterations.py
scripts/test_auto_fix_iterations.py → scripts/tests/test_auto_fix_iterations.py
scripts/test_cubemx_config.py    → scripts/tests/test_cubemx_config.py
scripts/test_logic_validation.py → scripts/tests/test_logic_validation.py
```

### 6.2 增加测试用例

在 `evals/evals.json` 中增加测试场景：
- 编译成功场景
- 编译失败 + 自动修复场景
- 分析结果验证
- 输出格式验证
- 错误处理验证

## 7. 实施顺序

1. **创建 `shared.py`** — 提取共享模块
2. **修改脚本使用 shared.py** — 消除重复代码
3. **统一输出格式** — 添加 `--text` 参数
4. **整理模板目录** — 分组精选 + 参数化基础模板
5. **整理测试目录** — 移动文件 + 增加测试用例
6. **更新 SKILL.md** — 反映新结构

## 8. 风险与缓解

| 风险 | 缓解措施 |
|------|---------|
| 删除模板破坏兼容性 | 保留分组代表模板，不删除基础模板 |
| 输出格式改变影响现有脚本 | 保持交互式脚本文本默认 |
| shared.py 导入路径问题 | 使用相对导入，测试所有脚本 |
