/**
  ******************************************************************************
  * @file    bootloader.c
  * @brief   USB DFU Bootloader 跳转功能实现
  *
  * 利用 STM32F407 内置 ROM 引导程序实现 USB DFU 固件更新。
  ******************************************************************************
  */

#include "bootloader.h"

/* 函数指针类型：ROM DFU 复位向量 */
typedef void (*pFunction)(void);

/**
  * @brief  检查 DFU 标志位，如果已设置则跳转到 DFU 模式
  */
uint8_t Bootloader_CheckFlag(void)
{
    if (*DFU_FLAG_ADDR == DFU_FLAG_MAGIC) {
        /* 清除标志位（防止复位后再次进入 DFU） */
        *DFU_FLAG_ADDR = 0;

        /* 跳转到 DFU（不会返回） */
        Bootloader_JumpToDFU();
        return 1;
    }
    return 0;
}

/**
  * @brief  设置 DFU 标志位并触发软复位
  */
void Bootloader_SetDFUFlag(void)
{
    /* 设置标志位 */
    *DFU_FLAG_ADDR = DFU_FLAG_MAGIC;

    /* 触发软复位 */
    NVIC_SystemReset();
}

/**
  * @brief  直接跳转到 ROM DFU 引导程序
  */
void Bootloader_JumpToDFU(void)
{
    pFunction JumpToApplication;
    uint32_t JumpAddress;

    /* 1. 禁用所有中断 */
    __disable_irq();

    /* 2. 停止 SysTick */
    SysTick->CTRL = 0;
    SysTick->LOAD = 0;
    SysTick->VAL  = 0;

    /* 3. 关闭所有已启用的外设时钟 */
    __HAL_RCC_GPIOA_CLK_DISABLE();
    __HAL_RCC_GPIOB_CLK_DISABLE();
    __HAL_RCC_GPIOD_CLK_DISABLE();
    __HAL_RCC_GPIOH_CLK_DISABLE();
    __HAL_RCC_I2C1_CLK_DISABLE();
    __HAL_RCC_I2C2_CLK_DISABLE();
    __HAL_RCC_USART1_CLK_DISABLE();
    __HAL_RCC_USART2_CLK_DISABLE();
    __HAL_RCC_TIM2_CLK_DISABLE();
    __HAL_RCC_TIM3_CLK_DISABLE();
    __HAL_RCC_TIM4_CLK_DISABLE();
    __HAL_RCC_TIM5_CLK_DISABLE();
    __HAL_RCC_TIM9_CLK_DISABLE();
    __HAL_RCC_ADC1_CLK_DISABLE();
    __HAL_RCC_DAC_CLK_DISABLE();
    __HAL_RCC_DMA1_CLK_DISABLE();
    __HAL_RCC_DMA2_CLK_DISABLE();

    /* 4. 重新使能 GPIOA 时钟（USB DFU 需要 PA11/PA12） */
    __HAL_RCC_GPIOA_CLK_ENABLE();

    /* 5. 将 PA11/PA12 配置为浮空输入（释放 USB 引脚给 ROM DFU） */
    GPIO_InitTypeDef GPIO_InitStruct = {0};
    GPIO_InitStruct.Pin   = GPIO_PIN_11 | GPIO_PIN_12;
    GPIO_InitStruct.Mode  = GPIO_MODE_INPUT;
    GPIO_InitStruct.Pull  = GPIO_NOPULL;
    HAL_GPIO_Init(GPIOA, &GPIO_InitStruct);

    __HAL_RCC_GPIOA_CLK_DISABLE();

    /* 6. 从系统存储器读取入口地址 */
    JumpAddress = *(__IO uint32_t *)(SYSMEM_BASE + 4);
    JumpToApplication = (pFunction)JumpAddress;

    /* 7. 设置主栈指针 */
    __set_MSP(*(__IO uint32_t *)SYSMEM_BASE);

    /* 8. 跳转到 ROM DFU 引导程序 */
    JumpToApplication();
}
