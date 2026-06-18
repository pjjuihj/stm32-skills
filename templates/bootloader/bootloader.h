/**
  ******************************************************************************
  * @file    bootloader.h
  * @brief   USB DFU Bootloader 跳转功能
  *
  * 利用 STM32F407 内置 ROM 引导程序（0x1FFF0000）实现 USB DFU 烧录。
  ******************************************************************************
  */

#ifndef __BOOTLOADER_H
#define __BOOTLOADER_H

#include "stm32f4xx_hal.h"

/* DFU 标志位地址（使用 RAM 末尾 4 字节） */
#define DFU_FLAG_ADDR       ((volatile uint32_t *)0x2001FFF0)
#define DFU_FLAG_MAGIC      0xDEADBEEF

/* 系统存储器地址（STM32F407 内置 ROM DFU 引导程序） */
#define SYSMEM_BASE         0x1FFF0000

/**
  * @brief  检查 DFU 标志位，如果已设置则跳转到 DFU 模式
  * @note   应在 HAL_Init() 之后、SystemClock_Config() 之前调用
  * @retval 1: 已跳转到 DFU（不会返回）  0: 正常启动
  */
uint8_t Bootloader_CheckFlag(void);

/**
  * @brief  设置 DFU 标志位并触发软复位
  * @note   调用后不会返回，MCU 将复位并进入 DFU 模式
  */
void Bootloader_SetDFUFlag(void);

/**
  * @brief  直接跳转到 ROM DFU 引导程序
  */
void Bootloader_JumpToDFU(void);

#endif /* __BOOTLOADER_H */
