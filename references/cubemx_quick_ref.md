# CubeMX 配置快速参考

## 交互式配置助手

```bash
python cubemx_guide.py                                    # 显示完整配置指南
python cubemx_guide.py --list                             # 列出所有外设配置指南
python cubemx_guide.py --peripheral ADC1                  # 指定外设配置指南
python cubemx_guide.py --peripheral DAC
python cubemx_guide.py --peripheral USART2
python cubemx_guide.py --peripheral I2C1
python cubemx_guide.py --peripheral TIM5
python cubemx_guide.py --peripheral TIM9
python cubemx_guide.py --template scope_siggen            # 项目模板配置指南
```

## 配置步骤概览

```
1. 项目创建 → 选择芯片 STM32F407VETx
2. 引脚配置 → ADC1(PA6), DAC(PA4), USART2(PA2/PA3), I2C1(PB6/PB7)
3. 时钟配置 → HSE=8MHz, SYSCLK=168MHz, APB1=42MHz, APB2=84MHz
4. 外设配置 → ADC1(12bit, TIM9触发), DAC(TIM5触发), USART2(115200)
5. NVIC 配置 → 优先级: UART(5), TIM(6)
6. 项目管理 → 选择 MDK-ARM V5
7. 代码生成 → 点击 GENERATE CODE
```

## cubemx_config.py 能力

| 功能 | 状态 | 命令 |
|------|------|------|
| **开启外设** | ✅ 可用 | `--add-peripheral ADC1` |
| **配置引脚** | ✅ 可用 | `--add-pin PA6 ADC1_IN6` |
| **配置时钟** | ✅ 可用 | `--set-clock --hse 8 --sysclk 168` |
| **配置 GPIO** | ✅ 可用 | `--config-gpio --gpio-pin PA8 --gpio-mode Output` |
| **配置 NVIC** | ✅ 可用 | `--config-nvic --irq USART1_IRQn --nvic-priority 5` |
| **添加任务** | ✅ 可用 | `--add-task --name MyTask --stack 256` |
| **外设参数** | ⚠️ 部分 | 需要在 CubeMX 中手动配置 |

## 详细配置命令

```bash
# 开启外设和配置引脚
python cubemx_config.py --modify project.ioc --add-peripheral ADC1 --add-pin PA6 ADC1_IN6

# 配置时钟
python cubemx_config.py --modify project.ioc --set-clock --hse 8 --sysclk 168

# 配置 GPIO
python cubemx_config.py --modify project.ioc --config-gpio --gpio-pin PA8 --gpio-mode Output --gpio-label LED

# 配置 NVIC
python cubemx_config.py --modify project.ioc --config-nvic --irq USART1_IRQn --nvic-priority 5

# 添加 FreeRTOS 任务
python cubemx_config.py --modify project.ioc --add-task --name SensorTask --stack 256 --priority High

# 生成代码
python cubemx_config.py --generate project.ioc --toolchain "MDK-ARM V5"
```

## 外设详细配置（部分支持）

| 配置类型 | 命令示例 | 说明 |
|---------|---------|------|
| **ADC** | `--config-adc --channel 6` | 基本配置，详细参数需在 CubeMX 中设置 |
| **DAC** | `--config-dac --dac-channel 1` | 基本配置 |
| **USART** | `--config-usart --baudrate 115200` | 基本配置，格式可能不完美 |
| **I2C** | `--config-i2c --speed 400000` | 基本配置 |
| **TIM** | `--config-tim --prescaler 84 --period 1000` | 基本配置 |
| **GPIO** | `--config-gpio --gpio-pin PA8 --gpio-mode Output` | 完整配置 |
| **NVIC** | `--config-nvic --irq USART1_IRQn --nvic-priority 5` | 完整配置 |

## 限制

| 限制 | 说明 |
|------|------|
| **外设参数** | 无法配置 CubeMX 接受的详细参数格式 |
| **DMA** | 无法配置详细 DMA 参数 |
| **中间件** | 无法配置 FreeRTOS、FatFS 等高级配置 |

## 推荐工作流程

```
1. 用 cubemx_config.py 开启外设和配置引脚（脚本完成）
2. 用 CubeMX 手动配置外设详细参数（手动完成）
3. 用 cubemx_config.py 生成代码（脚本完成）
```

## 配置模板

| 模板 | 说明 | 优化状态 |
|------|------|----------|
| `templates/basic_gpio.json` | LED + 按键 | ✅ 已优化 |
| `templates/uart_comm.json` | 双串口通信 | ✅ 已优化 |
| `templates/scope_siggen.json` | 串口示波器 + 信号发生器 | ✅ 已优化 |
| `templates/i2c_sensor.json` | I2C 传感器 | ⏳ 待优化 |
| `templates/pwm_motor.json` | PWM 电机控制 | ⏳ 待优化 |
| `templates/adc_dma.json` | ADC DMA 采集 | ⏳ 待优化 |
| `templates/freertos_basic.json` | FreeRTOS 基础任务 | ⏳ 待优化 |
| `templates/encoder_motor.json` | 编码器 + 电机控制 | ⏳ 待优化 |
| `templates/sensor_logger.json` | 传感器数据记录器 | ⏳ 待优化 |
