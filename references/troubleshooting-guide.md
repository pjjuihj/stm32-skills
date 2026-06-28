# STM32 HAL 故障排查指南

> 常见问题、症状及解决方案

## 快速诊断流程

```
硬件不工作？
    ↓
时钟是否启用？ → CubeMX 检查
    ↓ ✓
引脚是否正确？ → CubeMX 检查
    ↓ ✓
初始化是否调用？ → main.c 检查
    ↓ ✓
返回值检查？ → 添加错误处理
    ↓ ✓
中断是否启用？ → NVIC 配置
```

## 常见问题分类

### 1. 外设完全无响应

**症状：**
- 调用 HAL 函数后无任何反应
- GPIO 状态不改变
- 通信接口无输出

**检查清单：**
- [ ] **时钟未启用**：在 CubeMX 中检查外设时钟是否启用
- [ ] **引脚配置错误**：检查引脚模式、复用功能设置
- [ ] **初始化未调用**：在 `main.c` 的 `USER CODE BEGIN 2` 中检查
- [ ] **句柄指针错误**：确保使用 `&huart1`, `&hspi1` 等正确指针

**示例修复：**
```c
// 在 USER CODE BEGIN 2 中添加
/* USER CODE BEGIN 2 */
MX_USART1_UART_Init();  // 确保 UART 初始化被调用
/* USER CODE END 2 */
```

---

### 2. 中断不触发

**症状：**
- 中断服务函数从未执行
- 使用 `HAL_..._IT` 函数但回调不调用

**检查清单：**
- [ ] **NVIC 未启用**：在 CubeMX 中检查 NVIC Settings
- [ ] **中断优先级**：优先级配置是否合理
- [ ] **中断函数名错误**：IRQ Handler 名称必须与启动文件一致（如 `USART1_IRQHandler`），注意不要与 HAL 回调（如 `HAL_UART_RxCpltCallback`）混淆
- [ ] **IT 函数未调用**：需要先调用 `HAL_..._Start_IT`

**常见错误：**
```c
// ❌ 错误：中断函数名拼写错误（必须与 startup_stm32*.s 中一致）
void Usart1_IRQHandler(void) {  // 错误！大小写不对，应为 USART1_IRQHandler
    HAL_UART_IRQHandler(&huart1);
}

// ❌ 错误：忘记调用 IT 启动函数
void main(void) {
  // ...
  HAL_UART_Receive(&huart1, data, len, 1000);  // 错误！应该是 _IT
}

// ✅ 正确
void main(void) {
  // ...
  HAL_UART_Receive_IT(&huart1, data, len);  // 正确
}
```

---

### 3. DMA 不工作

**症状：**
- DMA 传输启动后无数据传输
- 传输完成后回调不触发
- DMA 配置莫名被修改

**检查清单：**
- [ ] **DMA 时钟未启用**：在 CubeMX 中检查 DMA 时钟
- [ ] **缓冲区对齐**：DMA 缓冲区通常需要 4 字节对齐
- [ ] **缓冲区生命周期**：缓冲区必须是全局或静态变量
- [ ] **DMA 通道冲突**：多个外设使用同一 DMA 通道
- [ ] **DMA 流/通道配置**：检查请求映射是否正确
- [ ] **HAL 函数覆盖配置**：见下方"HAL 函数偷偷改寄存器"
- [ ] **直接操作寄存器后回调失效**：见下方"直接操作 DMA 寄存器"

**示例错误：**
```c
// ❌ 错误：局部数组，函数返回后内存释放
void start_dma_wrong(void) {
    uint8_t buffer[64];  // 局部变量！
    HAL_UART_Transmit_DMA(&huart1, buffer, 64);  // 错误！
}

// ✅ 正确：静态或全局数组
static uint8_t dmaBuffer[64];  // 静态变量

void start_dma_correct(void) {
    HAL_UART_Transmit_DMA(&huart1, dmaBuffer, 64);  // 正确
}
```

#### ⚠️ HAL 函数偷偷改寄存器（实战踩坑）

**问题：** `HAL_ADC_Start_DMA()` 会覆盖 `MspInit` 中配置的 DMA 寄存器，将 PSIZE/MSIZE 从 16bit 改为 8bit，将 CIRC 从 1 改为 0。

**症状：** CubeMX 配置了 DMA 循环模式，但启动后 DMA 只传输一次就停止。

**根因：** HAL 函数内部根据 ADC 数据宽度重新计算 DMA CR 寄存器，覆盖了用户在 MspInit 中的配置。

**解决方案：**
```c
// 启动 DMA 后手动修正 CR 寄存器
HAL_ADC_Start_DMA(&hadc1, (uint32_t*)buf, len);

// 修正 PSIZE/MSIZE 为 16bit，CIRC 为 1
DMA2_Stream0->CR &= ~(DMA_SxCR_PSIZE | DMA_SxCR_MSIZE);
DMA2_Stream0->CR |= DMA_SxCR_PSIZE_0 | DMA_SxCR_MSIZE_0;  // 16bit
DMA2_Stream0->CR |= DMA_SxCR_CIRC;  // 循环模式
```

**搜索关键词：** `HAL_ADC_Start_DMA circular mode site:community.st.com`

#### ⚠️ 直接操作 DMA 寄存器后回调失效（实战踩坑）

**问题：** 直接修改 DMA CR 寄存器后，`HAL_ADC_ConvCpltCallback` 和 `HalfCpltCallback` 不再被调用。

**根因：** HAL 的回调机制依赖内部状态机，直接操作寄存器绕过了状态机，导致回调链断裂。

**解决方案：** 在 DMA 中断处理函数中手动调用 HAL 回调：
```c
void DMA2_Stream0_IRQHandler(void) {
    // 手动调用 HAL 回调，因为直接操作寄存器后 HAL 状态机失效
    if (DMA2->LISR & DMA_LISR_TCIF0) {
        DMA2->LIFCR = DMA_LIFCR_CTCIF0;  // 清除标志
        HAL_ADC_ConvCpltCallback(&hadc1);
    }
    if (DMA2->LISR & DMA_LISR_HTIF0) {
        DMA2->LIFCR = DMA_LIFCR_CHTIF0;
        HAL_ADC_HalfConvCpltCallback(&hadc1);
    }
}
```

---

### 4. 随机崩溃 / 硬故障

**症状：**
- 程序随机进入 `HardFault_Handler`
- 复位或重启
- 栈指针异常

**检查清单：**
- [ ] **栈溢出**：增加栈大小（在 .ioc 文件中配置）
- [ ] **数组越界**：检查所有数组访问
- [ ] **空指针**：检查指针是否为 NULL
- [ ] **中断中浮点运算**：Cortex-M3 无硬件 FPU，浮点由软件库实现，速度慢且消耗大量栈空间
- [ ] **大栈数组**：ISR 中不应有大数组

**调试方法：**
```c
// 在 HardFault_Handler 中添加断点查看故障地址
void HardFault_Handler(void)
{
    __disable_irq();
    while (1)
    {
        // 在此处设置断点，查看调用栈
        // 检查：LR (R14), MSP, PSP
    }
}
```

---

### 5. 时序问题 / 竞争条件

**症状：**
- 偶发性错误
- 高速运行时出错，低速时正常
- 使用调试器时问题消失
- 启动后前几帧数据异常

**检查清单：**
- [ ] **共享数据未保护**：中断和主循环共享变量需保护
- [ ] **中断优先级倒置**：高优先级中断等待低优先级资源
- [ ] **重新使能中断**：在 `HAL_..._IRQHandler` 之后 HAL 会重新使能中断
- [ ] **启动时缓冲区未稳定**：DMA 启动后前几帧数据可能不完整
- [ ] **定时器 MasterSlaveMode**：见下方"定时器配置陷阱"

#### ⚠️ 启动时缓冲区未稳定（实战踩坑）

**问题：** DMA 循环模式启动后，前几帧数据可能不完整或包含旧数据。

**症状：** 显示波形在启动后前几秒有竖线或跳变，之后恢复正常。

**解决方案：** 启动后跳过前 N 帧数据：
```c
static uint16_t startup_count = 0;
#define STARTUP_SKIP_FRAMES 20

void HAL_ADC_ConvCpltCallback(ADC_HandleTypeDef *hadc) {
    if (startup_count < STARTUP_SKIP_FRAMES) {
        startup_count++;
        return;  // 跳过前 20 帧
    }
    // 正常处理
}
```

#### ⚠️ 定时器 MasterSlaveMode 必须为 DISABLE（实战踩坑）

**问题：** CubeMX 配置定时器时，如果 MasterSlaveMode 设为 ENABLE，定时器可能不计数。

**症状：** ADC/DAC 使用定时器触发，但外设不工作，没有数据传输。

**解决方案：** 在 CubeMX 中将 TIM 的 Master Slave Mode 设为 DISABLE，或在代码中：
```c
HAL_TIM_Base_Init(&htim5);
htim5.Instance->SMCR &= ~TIM_SMCR_MSM;  // 确保 MasterSlaveMode 为 DISABLE
```

**修复共享数据竞争：**
```c
// ❌ 错误：无保护
volatile uint32_t counter = 0;

void EXTI0_IRQHandler(void) {
    counter++;  // ISR 中对 counter 的单次自增在 Cortex-M3 上不是原子的（读-改-写）
}

// ✅ 正确：在主循环侧保护共享变量
volatile uint32_t counter = 0;

void EXTI0_IRQHandler(void) {
    counter++;  // ISR 中无需 disable_irq，因为同优先级中断不会嵌套
}

void main_loop(void) {
    __disable_irq();
    uint32_t local = counter;  // 主循环读取时需要保护，防止被 ISR 打断
    __enable_irq();
}
```

---

### 6. UART 通信问题

**症状：**
- 接收到错误数据
- 丢失数据
- 只收到第一个字节

**常见原因：**
| 问题 | 原因 | 解决方案 |
|------|------|----------|
| 乱码 | 波特率不匹配 | 检查双方波特率配置 |
| 只收到首字节 | 中断模式未重启接收 | 在回调中再次调用 `HAL_UART_Receive_IT` |
| 数据丢失 | 波特率太高 | 降低波特率或使用 DMA |
| 无数据 | TX/RX 引脚反接 | 检查硬件连接 |

**接收重启示例：**
```c
void HAL_UART_RxCpltCallback(UART_HandleTypeDef *huart)
{
    if (huart->Instance == USART1) {
        // 处理接收到的数据
        process_data(rx_buffer);

        // 重启接收（关键！）
        HAL_UART_Receive_IT(&huart1, rx_buffer, RX_SIZE);
    }
}
```

---

### 7. SPI/I2C 通信失败

**症状：**
- HAL 返回 `HAL_TIMEOUT` 或 `HAL_ERROR`
- 读取到 0xFF 或 0x00
- I2C 总线锁死，后续所有传输失败

**SPI 检查清单：**
- [ ] CPOL/CPHA 配置与从机匹配
- [ ] 时钟频率不超过从机最大频率
- [ ] NSS 引脚配置（硬件/软件控制）
- [ ] MISO/MOSI 引脚未互换

**I2C 检查清单：**
- [ ] 外部上拉电阻（通常 4.7kΩ）
- [ ] 从机地址格式（7位需左移1位）
- [ ] 时钟速度（标准 100kHz，快速 400kHz）
- [ ] 调用 `HAL_I2C_IsDeviceReady()` 确认从机存在

**示例：I2C 从机地址**
```c
// ❌ 错误：7位地址未移位
HAL_I2C_Mem_Read(&hi2c1, 0x50, reg_addr, ...);

// ✅ 正确：7位地址左移1位
HAL_I2C_Mem_Read(&hi2c1, 0x50 << 1, reg_addr, ...);
```

#### ⚠️ I2C 总线锁死恢复（实战踩坑）

**问题：** I2C 传输失败后，SDA 被从设备拉低，总线锁死，所有后续传输都失败。

**错误做法 — 复杂状态机：**
```c
// ❌ 不要这样做！状态机本身会引入更严重的故障
static uint8_t i2c_err_count = 0;
static uint8_t i2c_bus_dead = 0;

void I2C_Write(uint8_t data) {
    if (i2c_bus_dead) {
        if (i2c_cooldown > 0) { i2c_cooldown--; return; }
        i2c_cooldown = 50;
    }
    // ... 如果第一次失败，总线被标记为 dead，后续所有写入被跳过
    if (++i2c_err_count >= 3) {
        i2c_bus_dead = 1;  // ← 这导致 OLED 黑屏 5 天无法定位
    }
}
```

**正确做法 — 简单恢复：**
```c
// ✅ 失败就恢复，恢复后不重试，让正常流程自然重试
void I2C_Write(uint8_t addr, uint8_t *data, uint8_t len) {
    HAL_StatusTypeDef status = HAL_I2C_Master_Transmit(&hi2c1, addr, data, len, 100);
    if (status == HAL_OK) return;

    // I2C bus recovery: 9 个时钟脉冲释放 SDA
    HAL_I2C_DeInit(&hi2c1);
    GPIO_InitTypeDef gpio = {0};
    gpio.Pin = GPIO_PIN_6 | GPIO_PIN_7;  // SCL|SDA
    gpio.Mode = GPIO_MODE_OUTPUT_OD;
    gpio.Pull = GPIO_PULLUP;
    HAL_GPIO_Init(GPIOB, &gpio);
    for (int i = 0; i < 9; i++) {
        HAL_GPIO_WritePin(GPIOB, GPIO_PIN_6, GPIO_PIN_RESET);
        HAL_Delay(1);
        HAL_GPIO_WritePin(GPIOB, GPIO_PIN_6, GPIO_PIN_SET);
        HAL_Delay(1);
    }
    // STOP 条件
    HAL_GPIO_WritePin(GPIOB, GPIO_PIN_7, GPIO_PIN_RESET);
    HAL_Delay(1);
    HAL_GPIO_WritePin(GPIOB, GPIO_PIN_6, GPIO_PIN_SET);
    HAL_Delay(1);
    HAL_GPIO_WritePin(GPIOB, GPIO_PIN_7, GPIO_PIN_SET);
    HAL_Delay(1);
    // 重新初始化 I2C 外设
    MX_I2C1_Init();
}
```

**原则：**
- 恢复逻辑 ≤ 5 行核心代码
- 不加状态机、冷却期、计数器
- 恢复后不重试，让正常流程自然重试
- 永远不放弃通信
- **恢复逻辑的 bug 比原始 bug 更致命**（可能导致整个系统卡死）

---

### 8. ADC 测量不准确

**症状：**
- 读数波动大
- 测量值明显错误
- 通道间串扰

**检查清单：**
- [ ] **采样时间**：高阻抗信号需要更长采样时间
- [ ] **时钟频率**：ADC 时钟不超过 14MHz
- [ ] **参考电压**：VREF+ 连接和稳定性
- [ ] **输入阻抗**：信号源阻抗应 < 10kΩ
- [ ] **校准**：上电后调用 `HAL_ADCEx_Calibration_Start()`

**改进采样：**
```c
// 增加采样时间（在 CubeMX 中配置）
// 或使用多次采样平均
uint32_t adc_read_average(ADC_HandleTypeDef *hadc, uint8_t channel, uint8_t samples)
{
    uint32_t sum = 0;
    ADC_ChannelConfTypeDef sConfig = {0};

    sConfig.Channel = channel;
    sConfig.Rank = ADC_REGULAR_RANK_1;
    sConfig.SamplingTime = ADC_SAMPLETIME_239CYCLES5;  // 长采样时间

    HAL_ADC_ConfigChannel(hadc, &sConfig);

    for (uint8_t i = 0; i < samples; i++) {
        HAL_ADC_Start(hadc);
        HAL_ADC_PollForConversion(hadc, 100);
        sum += HAL_ADC_GetValue(hadc);
        HAL_ADC_Stop(hadc);
    }

    return sum / samples;
}
```

---

## 调试技巧

### 1. 使用 SWO / ITM 输出调试信息
```c
// 在初始化后配置 ITM
void debug_init(void) {
    // 需要调试器支持 SWO
    ITM_SendChar('A');
}

// 使用
ITM_SendChar('X');
```

### 2. GPIO 调试（翻转引脚）
```c
// 在关键位置翻转引脚，用示波器/逻辑分析仪观察
void debug_toggle(void) {
    HAL_GPIO_TogglePin(DEBUG_GPIO_Port, DEBUG_Pin);
}

// 在代码中插入
void function_to_debug(void) {
    HAL_GPIO_WritePin(DEBUG_GPIO_Port, DEBUG_Pin, GPIO_PIN_SET);
    // 关键代码
    HAL_GPIO_WritePin(DEBUG_GPIO_Port, DEBUG_Pin, GPIO_PIN_RESET);
}
```

### 3. 返回值检查
```c
HAL_StatusTypeDef status;

status = HAL_UART_Transmit(&huart1, data, len, 1000);
if (status != HAL_OK) {
    // 处理错误
    if (status == HAL_TIMEOUT) {
        // 超时处理
    } else if (status == HAL_ERROR) {
        // 错误处理
    }
}
```

### 4. 查看寄存器状态
```c
// 查看 UART 状态
if (huart1.Instance->SR & USART_FLAG_RXNE) {
    // 接收缓冲区非空
}

// 查看 GPIO 状态
if (GPIOA->IDR & GPIO_PIN_5) {
    // PA5 为高电平
}
```

---

## 性能优化

### 减少中断开销
```c
// 使用 DMA 代替中断模式
HAL_UART_Receive_DMA(&huart1, rx_buffer, RX_SIZE);

// 在接收完成回调中处理
void HAL_UART_RxCpltCallback(UART_HandleTypeDef *huart) {
    // 一次性处理所有数据
}
```

### 使用缓冲队列
```c
// 简单环形缓冲区
#define BUFFER_SIZE 128
static uint8_t ring_buffer[BUFFER_SIZE];
static volatile uint16_t head = 0, tail = 0;

void buffer_write(uint8_t data) {
    ring_buffer[head] = data;
    head = (head + 1) % BUFFER_SIZE;
}

uint8_t buffer_read(void) {
    uint8_t data = ring_buffer[tail];
    tail = (tail + 1) % BUFFER_SIZE;
    return data;
}
```

---

## 参考资料

- [STM32F1 HAL 驱动用户手册 UM1850](https://www.st.com/resource/en/user_manual/um1850-description-of-stm32f1xx-hal-drivers-stmicroelectronics.pdf)
- [STM32F103 参考手册 RM0008](https://www.st.com/resource/en/reference_manual/rm0008-stm32f101xx-stm32f102xx-stm32f103xx-stm32f105xx-and-stm32f107xx-advanced-armbased-32bit-microcontrollers-stmicroelectronics.pdf)
- [STM32 数据手册 DS5319](https://www.st.com/resource/en/datasheet/stm32f103rb.pdf)
