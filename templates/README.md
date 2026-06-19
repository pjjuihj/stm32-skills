# STM32 项目模板

这些模板可以用于快速创建 STM32 项目。

## 使用方法

### 本地使用

```bash
python project_init.py --name my_project --template scope_siggen
```

### 从 GitHub 加载

```bash
# 使用仓库中的模板
python project_init.py --name my_project --template scope_siggen

# 使用完整 URL
python project_init.py --name my_project --template https://github.com/your-username/stm32-project-templates/raw/main/templates/scope_siggen.json
```

## 模板列表

| 模板 | 说明 |
|------|------|
| `scope_siggen.json` | 串口示波器 + 信号发生器 |
| `basic_gpio.json` | LED + 按键 |
| `uart_comm.json` | 双串口通信 |
| `i2c_sensor.json` | I2C 传感器 |
| `pwm_motor.json` | PWM 电机控制 |
| `adc_dma.json` | ADC DMA 采集 |
| `freertos_basic.json` | FreeRTOS 基础任务 |

## 迁移到 GitHub

1. 创建 GitHub 仓库：`stm32-project-templates`
2. 上传所有 `.json` 文件
3. 修改 `project_init.py` 中的 `GITHUB_REPO` 配置

## 模板格式

```json
{
  "name": "模板名称",
  "description": "模板描述",
  "mcu": "STM32F407VETx",
  "peripherals": ["ADC1", "DAC", "USART2"],
  "pins": [
    {"pin": "PA6", "signal": "ADC1_IN6", "label": "SCOPE_IN"}
  ],
  "config": {
    "ADC1": {"Resolution": "ADC_RESOLUTION_12B"}
  }
}
```
