# STM32 模板优化指南

## 优化原则

基于 GitHub 上 STM32 最佳实践，对模板进行以下优化：

### 1. 完整的时钟配置

每个模板都应包含完整的时钟树配置：

```json
"clock": {
  "hse": 8,           // 外部晶振频率 (MHz)
  "sysclk": 168,      // 系统时钟 (MHz)
  "ahb": 168,         // AHB 总线时钟
  "apb1": 42,         // APB1 总线时钟 (最大 42MHz)
  "apb2": 84,         // APB2 总线时钟 (最大 84MHz)
  "pll_m": 8,         // PLL 倍频系数 M
  "pll_n": 336,       // PLL 倍频系数 N
  "pll_p": 2          // PLL 分频系数 P
}
```

### 2. 标准化引脚定义

每个引脚都应包含：

```json
{
  "pin": "PA6",
  "signal": "ADC1_IN6",
  "mode": "ADC1_IN6",
  "label": "SCOPE_IN",
  "description": "示波器 ADC 输入"
}
```

### 3. 完整的 NVIC 配置

包含优先级和子优先级：

```json
"nvic": {
  "TIM5_IRQn": {
    "priority": 6,
    "subpriority": 0,
    "enabled": true
  }
}
```

### 4. 调试接口配置

```json
"debug": {
  "interface": "SWD",
  "frequency": 4000,
  "reset_mode": "UNDER_RESET"
}
```

### 5. 构建配置

```json
"build": {
  "toolchain": "MDK-ARM",
  "compiler": "ARMCC",
  "optimization": "-Og",
  "debug_info": true
}
```

## 模板分类

| 类别 | 模板 | 说明 |
|------|------|------|
| **基础** | basic_gpio.json | LED + 按键 |
| **通信** | uart_comm.json | 双串口通信 |
| **传感器** | i2c_sensor.json | I2C 传感器 |
| **显示** | oled_display.json | OLED 显示 |
| **电机** | pwm_motor.json | PWM 电机控制 |
| **采集** | adc_dma.json | ADC DMA 采集 |
| **工具** | scope_siggen.json | 示波器 + 信号发生器 |

## 最佳实践

### 1. 引脚分配原则

- **避免冲突**：检查引脚复用功能
- **预留调试**：保留 SWD 引脚（PA13/PA14）
- **电源引脚**：确保电源和地线连接正确

### 2. 中断优先级

- **高优先级**：实时控制（电机、传感器）
- **中优先级**：通信（UART、I2C）
- **低优先级**：显示、状态指示

### 3. 时钟配置

- **HSE**：使用外部晶振（更精确）
- **PLL**：正确配置倍频系数
- **APB**：注意总线频率限制

### 4. 调试接口

- **SWD**：推荐使用，只需 2 根线
- **JTAG**：功能更多，但占用引脚

## GitHub 最佳实践

### 1. 版本控制

```
.gitignore 内容：
# 构建产物
*.o
*.d
*.axf
*.hex
*.bin

# IDE 配置
.vscode/
.idea/

# 保留
*.ioc
*.json
```

### 2. 项目结构

```
project/
├── Core/
│   ├── Inc/          # 头文件
│   └── Src/          # 源文件
├── Board/            # 应用模块
├── Drivers/          # HAL 库
├── MDK-ARM/          # Keil 工程
├── template.json     # 模板配置
└── README.md         # 项目说明
```

### 3. 文档

每个模板应包含：
- 功能说明
- 引脚分配表
- 配置参数
- 使用示例

## 模板扩展

### 添加新模板

1. 创建 JSON 文件
2. 遵循标准化格式
3. 添加到 templates 目录
4. 更新 README.md

### 模板继承

```json
{
  "name": "扩展模板",
  "extends": "basic_gpio.json",
  "overrides": {
    "peripherals": ["GPIO", "USART1"]
  }
}
```

## 参考资源

- [STM32CubeF4 示例项目](https://github.com/STMicroelectronics/STM32CubeF4)
- [STM32 HAL 库文档](https://www.st.com/en/embedded-software/stm32cube-cho407.html)
- [FreeRTOS 示例](https://github.com/FreeRTOS/FreeRTOS)
