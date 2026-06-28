# 分阶段验证流程

> **嵌入式开发的核心不是写代码，是验证每一步。**

---

## 为什么需要分阶段验证

嵌入式系统和上层软件最大的区别：**出了问题你看不到。** PC 上程序崩了有 crash log、有 debugger、有 core dump。STM32 上 OLED 黑了，你什么都看不到——除非你提前确认过每个模块单独工作。

**一次性写完所有代码再测试 = 赌博。** 出问题时，你不知道是哪个外设的问题、哪个配置的问题、还是哪个逻辑的问题。

**分阶段验证 = 每一步都有验收标准。** 出问题时，你知道问题在哪一层。

---

## 阶段 1：外设单独验证

**原则：不写一行应用代码。每个外设独立烧录测试。**

### 1.1 UART 验证

**验收标准：** 串口终端有输出。

```c
int main(void) {
    HAL_Init();
    SystemClock_Config();
    MX_GPIO_Init();
    MX_USART1_UART_Init();
    while (1) {
        HAL_UART_Transmit(&huart1, "HELLO\r\n", 7, 100);
        HAL_Delay(1000);
    }
}
```

**失败排查：**
- 没有输出 → 检查 TX/RX 引脚是否接反、波特率是否匹配
- 乱码 → 检查时钟配置、波特率计算
- 只输出一次 → 检查主循环是否卡死

---

### 1.2 ADC 验证

**验收标准：** 串口输出的 ADC 值随输入变化，范围 0-4095。

```c
int main(void) {
    HAL_Init();
    SystemClock_Config();
    MX_GPIO_Init();
    MX_USART1_UART_Init();
    MX_ADC1_Init();
    while (1) {
        HAL_ADC_Start(&hadc1);
        HAL_ADC_PollForConversion(&hadc1, 100);
        uint32_t val = HAL_ADC_GetValue(&hadc1);
        char buf[32];
        int n = snprintf(buf, sizeof(buf), "ADC: %lu\r\n", val);
        HAL_UART_Transmit(&huart1, (uint8_t*)buf, n, 100);
        HAL_Delay(500);
    }
}
```

**失败排查：**
- 值恒为 0 → 检查引脚配置、通道选择、时钟使能
- 值恒为 4095 → 检查是否接了 VREF
- 值不随输入变化 → 检查是否读了错误的通道
- 值波动大 → 增加采样时间、检查参考电压稳定性

---

### 1.3 DAC 验证

**验收标准：** 万用表量 DAC 引脚，读到正确电压（2048 → ~1.65V）。

```c
int main(void) {
    HAL_Init();
    SystemClock_Config();
    MX_GPIO_Init();
    MX_DAC_Init();
    HAL_DAC_Start(&hdac, DAC_CHANNEL_1);
    HAL_DAC_SetValue(&hdac, DAC_CHANNEL_1, DAC_ALIGN_12B_R, 2048);
    while (1) { __WFI(); }
}
```

**失败排查：**
- 电压为 0 → 检查引脚配置、DAC 通道选择
- 电压不对 → 检查参考电压、对齐方式（12bit 左对齐 vs 右对齐）
- 有噪声 → 检查电源滤波、输出负载

---

### 1.4 定时器验证

**验收标准：** 读 TIM->CNT 寄存器在计数。

```c
int main(void) {
    HAL_Init();
    SystemClock_Config();
    MX_GPIO_Init();
    MX_USART1_UART_Init();
    MX_TIM5_Init();
    HAL_TIM_Base_Start(&htim5);
    while (1) {
        char buf[32];
        int n = snprintf(buf, sizeof(buf), "CNT: %lu\r\n", TIM5->CNT);
        HAL_UART_Transmit(&huart1, (uint8_t*)buf, n, 100);
        HAL_Delay(500);
    }
}
```

**失败排查：**
- CNT 恒为 0 → 检查时钟使能、MasterSlaveMode（必须为 DISABLE）
- CNT 不溢出 → 检查 ARR 配置
- CNT 溢出过快 → 检查 PSC 分频

---

### 1.5 I2C 验证

**验收标准：** `HAL_I2C_IsDeviceReady` 返回 HAL_OK。

```c
int main(void) {
    HAL_Init();
    SystemClock_Config();
    MX_GPIO_Init();
    MX_USART1_UART_Init();
    MX_I2C1_Init();
    while (1) {
        HAL_StatusTypeDef status = HAL_I2C_IsDeviceReady(&hi2c1, 0x3C << 1, 3, 100);
        char buf[32];
        int n = snprintf(buf, sizeof(buf), "I2C: %s\r\n",
                         status == HAL_OK ? "OK" : "FAIL");
        HAL_UART_Transmit(&huart1, (uint8_t*)buf, n, 100);
        HAL_Delay(1000);
    }
}
```

**失败排查：**
- 返回 FAIL → 检查上拉电阻（4.7kΩ）、地址是否正确（7位左移1位）、SCL/SDA 引脚
- 偶尔 FAIL → 检查总线速率、信号完整性
- 一直 FAIL → I2C 总线可能锁死，需要恢复（9 个时钟脉冲 + STOP）

---

### 1.6 OLED 验证

**验收标准：** 屏幕上画出一条线。

```c
int main(void) {
    HAL_Init();
    SystemClock_Config();
    MX_GPIO_Init();
    MX_USART1_UART_Init();
    MX_I2C1_Init();
    OLED_Init();
    OLED_Clear();
    // 画一条从 (0,0) 到 (127,0) 的线
    for (int x = 0; x < 128; x++) {
        OLED_GRAM[x][0] = 0xFF;
    }
    OLED_Refresh();
    while (1) { __WFI(); }
}
```

**失败排查：**
- 黑屏 → I2C 通信是否成功（加串口日志确认）
- 花屏 → 初始化命令序列是否正确、GRAM 刷新逻辑
- 闪烁 → 刷新频率、I2C 速率

---

## 阶段 2：数据链路验证

**原则：不接 UI。确认数据从 A 流到 B，值正确。**

### 2.1 TIM → ADC → DMA 链路

**验收标准：** DMA 回调触发，串口输出的 ADC 数据正确。

```c
static uint16_t adc_buf[128];
static volatile uint8_t dma_done = 0;

void HAL_ADC_ConvCpltCallback(ADC_HandleTypeDef *hadc) {
    dma_done = 1;
}

int main(void) {
    // ... 初始化 ...
    HAL_ADC_Start_DMA(&hadc1, (uint32_t*)adc_buf, 128);
    while (1) {
        if (dma_done) {
            dma_done = 0;
            // 打印前 10 个值
            for (int i = 0; i < 10; i++) {
                char buf[16];
                int n = snprintf(buf, sizeof(buf), "%u ", adc_buf[i]);
                HAL_UART_Transmit(&huart1, (uint8_t*)buf, n, 100);
            }
            HAL_UART_Transmit(&huart1, "\r\n", 2, 100);
        }
    }
}
```

**失败排查：**
- 回调不触发 → DMA 配置、NVIC 优先级、HAL 回调是否失效（直接操作寄存器后会失效）
- 数据全为 0 → ADC 通道配置、DMA 方向
- 数据不对 → 检查 PSIZE/MSIZE 是否被 HAL 覆盖

### 2.2 DAC 输出 → ADC 输入 自测链路

**验收标准：** DAC 输出已知值，ADC 读回相近值。

```c
// DAC 输出 2048（~1.65V），ADC 应该读到 ~2048
HAL_DAC_SetValue(&hdac, DAC_CHANNEL_1, DAC_ALIGN_12B_R, 2048);
HAL_Delay(10);
HAL_ADC_Start(&hadc1);
HAL_ADC_PollForConversion(&hadc1, 100);
uint32_t adc_val = HAL_ADC_GetValue(&hadc1);
// adc_val 应该在 2048 ± 50 范围内
```

**失败排查：**
- 差值过大 → 检查参考电压、接线、ADC/DAC 对齐方式
- 不稳定 → 检查电源滤波、采样时间

---

## 阶段 3：集成显示

**原则：底层已验证，只排查 UI 逻辑。**

### 3.1 OLED 基本显示

**验收标准：** 在 OLED 上画出静态波形。

```c
// 用已知数据画波形（不用真实 ADC 数据）
for (int x = 0; x < 128; x++) {
    int y = 32 + (int)(20.0f * sinf(x * 0.1f));  // 正弦波
    OLED_DrawPoint(x, y, 1);
}
OLED_Refresh();
```

### 3.2 真实数据 + OLED 显示

**验收标准：** ADC 数据渲染为波形，显示在 OLED 上。

```c
// DMA 采集 → 波形渲染 → OLED 显示
// 因为阶段 2 已验证 ADC 数据正确，这里只需要排查渲染逻辑
```

### 3.3 完整功能

**验收标准：** 按钮切换、触发模式、信号发生器等交互功能。

---

## 验收清单模板

每个阶段完成后，填写以下清单：

```
阶段 1 - 外设单独验证
  [ ] UART: 串口输出 HELLO
  [ ] ADC: 值随输入变化，范围 0-4095
  [ ] DAC: 万用表量到正确电压
  [ ] TIM: CNT 寄存器在计数
  [ ] I2C: IsDeviceReady 返回 OK
  [ ] OLED: 画出一条线

阶段 2 - 数据链路验证
  [ ] TIM→ADC→DMA: 回调触发，数据正确
  [ ] DAC→ADC 自测: 误差 < 2%

阶段 3 - 集成显示
  [ ] 静态波形: 正弦波正确显示
  [ ] 实时波形: ADC 数据渲染正确
  [ ] 交互功能: 按钮、触发、切换
```

**没有通过验收，不进入下一阶段。**

---

## 核心原则

| 原则 | 说明 |
|------|------|
| **每个外设独立验证** | 不要同时配置所有外设再测试 |
| **验收标准明确** | "能用"不是标准，"串口输出 HELLO"是标准 |
| **失败时缩小范围** | 阶段 1 失败 = 外设配置问题，阶段 2 失败 = 数据链路问题 |
| **不跳过阶段** | 阶段 1 没通过就不要做阶段 2 |
| **记录每个阶段的结果** | 下次出问题时，知道从哪个阶段开始排查 |
