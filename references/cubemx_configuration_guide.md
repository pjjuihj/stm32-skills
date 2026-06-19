# STM32CubeMX 详细配置指南

## 目录

1. [项目创建](#1-项目创建)
2. [芯片选型](#2-芯片选型)
3. [引脚配置](#3-引脚配置)
4. [时钟配置](#4-时钟配置)
5. [外设配置](#5-外设配置)
6. [NVIC 配置](#6-nvic-配置)
7. [项目管理](#7-项目管理)
8. [代码生成](#8-代码生成)

---

## 1. 项目创建

### 步骤 1.1：启动 CubeMX

```
双击 STM32CubeMX 图标
或从开始菜单启动
```

### 步骤 1.2：新建项目

```
File → New Project
```

**界面说明：**
- 左侧：MCU 选择器
- 右侧：MCU 信息面板

### 步骤 1.3：搜索芯片

```
在搜索框输入：STM32F407VETx
```

**筛选选项：**
- Package：LQFP100
- Flash：512 KB
- RAM：128 KB

### 步骤 1.4：确认选择

```
点击 Start Project
```

---

## 2. 芯片选型

### 2.1：MCU 信息确认

| 参数 | 值 | 说明 |
|------|-----|------|
| 型号 | STM32F407VETx | MCU 型号 |
| 封装 | LQFP100 | 100 引脚 |
| Flash | 512 KB | 程序存储器 |
| RAM | 128 KB | 数据存储器 |
| 主频 | 168 MHz | 最高系统时钟 |

### 2.2：引脚视图

```
在 Pinout 视图中查看所有引脚
- 绿色：已配置
- 灰色：未配置
- 红色：冲突
```

---

## 3. 引脚配置

### 3.1：ADC 引脚配置（PA6）

**步骤：**
1. 在芯片图上找到 **PA6**
2. 左键点击 PA6
3. 选择 **ADC1_IN6**

**参数设置：**
```
GPIO mode：ADC1_IN6
GPIO Pull-up/Pull-down：No pull-up and no pull-down
Maximum output speed：Low
User Label：SCOPE_IN
```

### 3.2：DAC 引脚配置（PA4）

**步骤：**
1. 在芯片图上找到 **PA4**
2. 左键点击 PA4
3. 选择 **DAC_OUT1**

**参数设置：**
```
GPIO mode：DAC_OUT1
GPIO Pull-up/Pull-down：No pull-up and no pull-down
User Label：SIGGEN_OUT
```

### 3.3：USART2 引脚配置（PA2/PA3）

**PA2 配置：**
```
引脚：PA2
功能：USART2_TX
模式：Asynchronous
```

**PA3 配置：**
```
引脚：PA3
功能：USART2_RX
模式：Asynchronous
```

### 3.4：I2C1 引脚配置（PB6/PB7）

**PB6 配置：**
```
引脚：PB6
功能：I2C1_SCL
模式：I2C
```

**PB7 配置：**
```
引脚：PB7
功能：I2C1_SDA
模式：I2C
```

### 3.5：调试引脚配置（PA13/PA14）

**PA13 配置：**
```
引脚：PA13
功能：SYS_JTMS-SWDIO
模式：Serial_Wire
```

**PA14 配置：**
```
引脚：PA14
功能：SYS_JTCK-SWCLK
模式：Serial_Wire
```

### 3.6：LED 引脚配置（PA8）

**PA8 配置：**
```
引脚：PA8
功能：GPIO_Output
模式：Output Push-Pull
Pull-up/Pull-down：No pull-up and no pull-down
Maximum output speed：Low
User Label：LED
```

---

## 4. 时钟配置

### 4.1：进入时钟配置页面

```
点击左侧 "Clock Configuration" 标签
```

### 4.2：配置时钟树

**步骤：**
1. **HSE 选择**：Crystal/Ceramic Resonator
2. **PLL 配置**：
   - PLL Source：HSE
   - PLLM：8
   - PLLN：336
   - PLLP：2
3. **系统时钟**：PLLCLK
4. **AHB 分频**：/1 → 168 MHz
5. **APB1 分频**：/4 → 42 MHz
6. **APB2 分频**：/2 → 84 MHz

### 4.3：时钟参数表

| 参数 | 值 | 说明 |
|------|-----|------|
| HSE | 8 MHz | 外部晶振 |
| PLLM | 8 | PLL 输入分频 |
| PLLN | 336 | PLL 倍频 |
| PLLP | 2 | PLL 输出分频 |
| SYSCLK | 168 MHz | 系统时钟 |
| AHB | 168 MHz | AHB 总线 |
| APB1 | 42 MHz | APB1 总线（最大 42MHz） |
| APB2 | 84 MHz | APB2 总线（最大 84MHz） |

### 4.4：验证时钟配置

```
检查所有外设时钟是否在允许范围内
- APB1 定时器：84 MHz（42 MHz × 2）
- APB2 定时器：168 MHz（84 MHz × 2）
```

---

## 5. 外设配置

### 5.1：ADC1 配置

**步骤：**
1. 点击左侧 **Analog → ADC1**
2. 配置参数：

**基本设置：**
```
Mode：Independent mode（单通道）
Resolution：12 Bits
Data Alignment：Right alignment
Scan Conversion Mode：Disabled
Continuous Conversion Mode：Disabled
Discontinuous Conversion Mode：Disabled
Number of Conversion：1
```

**通道配置（Rank 1）：**
```
Channel：IN6
Sampling Time：84 Cycles
```

**触发配置：**
```
External Trigger Conversion Source：Timer 9 Trigger Out Event
External Trigger Conversion Edge：Rising Edge
```

### 5.2：DAC 配置

**步骤：**
1. 点击左侧 **Analog → DAC**
2. 配置参数：

**基本设置：**
```
DAC Out1 Output Buffer：Enable
Trigger：Timer 5 Trigger Out Event
Wave Generation Mode：Disabled
```

### 5.3：USART2 配置

**步骤：**
1. 点击左侧 **Connectivity → USART2**
2. 配置参数：

**基本设置：**
```
Mode：Asynchronous
Baud Rate：115200 Bits/s
Word Length：8 Bits
Stop Bits：1
Parity：None
Data Direction：Receive and Transmit
Over Sampling：16 Samples
```

### 5.4：I2C1 配置

**步骤：**
1. 点击左侧 **Connectivity → I2C1**
2. 配置参数：

**基本设置：**
```
Mode：I2C
Clock Speed：400000 Hz
Duty Cycle：Duty Cycle 2
Own Address 1：0
Addressing Mode：7-bit
Dual Address Mode：Disabled
General Call Mode：Disabled
No Stretch Mode：Disabled
```

### 5.5：TIM5 配置（DAC 触发）

**步骤：**
1. 点击左侧 **Timers → TIM5**
2. 配置参数：

**基本设置：**
```
Clock Source：Internal Clock
Channel1：Disabled
Prescaler：84-1
Counter Mode：Up
Counter Period：2000-1
Internal Clock Division：No Division
auto-reload preload：Enable
```

**触发输出：**
```
Trigger Event Selection：Update Event
```

### 5.6：TIM9 配置（ADC 触发）

**步骤：**
1. 点击左侧 **Timers → TIM9**
2. 配置参数：

**基本设置：**
```
Clock Source：Internal Clock
Channel1：Disabled
Prescaler：84-1
Counter Mode：Up
Counter Period：1000-1
Internal Clock Division：No Division
auto-reload preload：Enable
```

**触发输出：**
```
Trigger Event Selection：Update Event
```

---

## 6. NVIC 配置

### 6.1：进入 NVIC 配置页面

```
点击左侧 "NVIC" 标签
```

### 6.2：配置中断优先级

| 中断 | 优先级 | 子优先级 | 使能 |
|------|--------|----------|------|
| TIM5_IRQn | 6 | 0 | ✅ |
| TIM1_BRK_TIM9_IRQn | 6 | 0 | ✅ |
| USART2_IRQn | 5 | 0 | ✅ |
| I2C1_ER_IRQn | 5 | 0 | ✅ |
| I2C1_EV_IRQn | 5 | 0 | ✅ |

### 6.3：优先级说明

```
优先级 0：最高（系统异常）
优先级 5：通信（UART、I2C）
优先级 6：定时器（TIM）
优先级 15：最低（SysTick）
```

---

## 7. 项目管理

### 7.1：进入项目管理页面

```
点击左侧 "Project Manager" 标签
```

### 7.2：项目设置

**基本设置：**
```
Project Name：my_project
Project Location：选择保存路径
Toolchain/IDE：MDK-ARM V5
```

### 7.3：代码生成设置

**Code Generator 选项：**
```
✅ Copy all used libraries into the project folder
✅ Generate peripheral initialization as a pair of '.c/.h' files
✅ Keep User Code when re-generating
✅ Delete previously generated files when not re-generated
```

### 7.4：高级设置

**Advanced Settings：**
```
✅ Generate a function to initialize the MSP (HAL_Init)
✅ Assert enabled
```

---

## 8. 代码生成

### 8.1：生成代码

```
点击 "GENERATE CODE" 按钮
```

**等待生成完成：**
- 生成初始化代码
- 创建项目文件
- 配置 Keil 工程

### 8.2：生成的文件结构

```
project_led/
├── Core/
│   ├── Inc/
│   │   ├── main.h
│   │   ├── stm32f4xx_hal_conf.h
│   │   ├── stm32f4xx_it.h
│   │   ├── gpio.h
│   │   ├── adc.h
│   │   ├── dac.h
│   │   ├── tim.h
│   │   ├── usart.h
│   │   └── i2c.h
│   └── Src/
│       ├── main.c
│       ├── stm32f4xx_it.c
│       ├── stm32f4xx_hal_msp.c
│       ├── gpio.c
│       ├── adc.c
│       ├── dac.c
│       ├── tim.c
│       ├── usart.c
│       └── i2c.c
├── Drivers/
│   └── STM32F4xx_HAL_Driver/
└── MDK-ARM/
    └── project_led.uvprojx
```

### 8.3：验证生成结果

**检查项：**
- [ ] 所有引脚配置正确
- [ ] 时钟配置正确
- [ ] 外设初始化代码生成
- [ ] 中断处理函数生成
- [ ] Keil 工程文件生成

---

## 常见问题

### Q1：引脚冲突怎么办？

**解决方法：**
1. 检查引脚复用功能
2. 重新分配引脚
3. 在 Pinout 视图中查看冲突提示

### Q2：时钟配置错误？

**解决方法：**
1. 检查 HSE 晶振频率
2. 验证 PLL 参数
3. 确保 APB 总线频率不超限

### Q3：生成代码后编译失败？

**解决方法：**
1. 检查 Include 路径
2. 验证 HAL 库版本
3. 检查启动文件

### Q4：如何修改已生成的配置？

**解决方法：**
1. 重新打开 .ioc 文件
2. 在 CubeMX 中修改配置
3. 重新生成代码
4. 保留 USER CODE 区域的代码

---

## 最佳实践

### 1. 配置顺序

```
1. 芯片选型
2. 引脚配置
3. 时钟配置
4. 外设配置
5. NVIC 配置
6. 项目管理
7. 代码生成
```

### 2. 代码保护

```c
/* USER CODE BEGIN 0 */
// 初始化前的代码
/* USER CODE END 0 */

/* USER CODE BEGIN 1 */
// 用户变量定义
/* USER CODE END 1 */

/* USER CODE BEGIN 2 */
// 初始化代码
/* USER CODE END 2 */

/* USER CODE BEGIN 3 */
// 主循环代码
/* USER CODE END 3 */
```

### 3. 版本控制

```gitignore
# .gitignore
# 保留 .ioc 文件
!*.ioc

# 排除生成的临时文件
*.bak
*.tmp
```

---

## 参考资源

- [STM32CubeMX 用户手册](https://www.st.com/resource/en/user_manual/um1718-stm32cubemx-graphical-user-interface-stmicroelectronics.pdf)
- [STM32F407 参考手册](https://www.st.com/resource/en/reference_manual/rm0090-stm32f405415-stm32f407417-stm32f427437-and-stm32f429439-advanced-armbased-32bit-mcus-stmicroelectronics.pdf)
- [STM32CubeF4 示例项目](https://github.com/STMicroelectronics/STM32CubeF4)
