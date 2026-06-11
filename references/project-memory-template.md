# 项目记忆 — STM32 Keil 工程配置

> 复制此文件到项目根目录，填入实际配置。
> 技能会优先读取此文件获取项目信息，不硬编码路径。

## 工具链路径

- **Keil UV4.exe**: `<路径，如 D:/k5/UV4/UV4.exe>`
- **ARM Compiler (armclang)**: `<路径，如 D:/k5/ARM/ARMCLANG/bin/armclang.exe>`
- **STM32_Programmer_CLI**: `<路径，如 C:/Program Files/STMicroelectronics/STM32Cube/STM32CubeProgrammer/bin/STM32_Programmer_CLI.exe>`
- **arm-none-eabi 工具链**: `<路径，如有>`

## 工程信息

- **项目文件**: `<相对路径 .uvprojx，如 MDK-ARM/project.uvprojx>`
- **Target 名称**: `<Keil 中 Target 下拉框名称，如 project_led>`
- **默认配置**: `Debug`
- **ELF 输出**: `<相对路径 .axf，如 MDK-ARM/project/project.axf>`
- **HEX 输出**: `<相对路径 .hex，如 MDK-ARM/project/project.hex>`

## 目标芯片

- **MCU**: `<型号，如 STM32F407VETx>`
- **封装**: `<如 LQFP100>`
- **内核**: `<如 Cortex-M4F>`
- **主频**: `<如 168MHz>`
- **Flash**: `<大小>（<地址范围，如 0x08000000 - 0x0807FFFF>）`
- **SRAM**: `<大小>（<地址范围，如 0x20000000 - 0x2001FFFF>）`

## 调试器配置

- **调试器**: `<如 ST-LINK V2>`
- **接口**: `SWD`
- **SWD 频率**: `4000 kHz`
- **连接模式**: `UR`（Under Reset）
- **复位模式**: `HWrst`
- **ST-LINK SN**: `<如有多个调试器，填入序列号>`

## 串口配置

- **调试串口**: `<如 COM3>`
- **波特率**: `115200`
- **数据位**: `8`
- **停止位**: `1`
- **校验**: `None`
- **蓝牙串口**: `<如有，如 COM4, 9600 baud>`

## 需要保护的 Flash 区域

<!-- 列出不能被擦除的 Flash 区域 -->
<!-- 例如：校准参数页、Option Bytes、用户数据区 -->

- 无特殊保护区域（如需保护请填入地址范围）

## 已知问题与注意事项

<!-- 记录本项目的已知问题、特殊配置、历史踩坑 -->

- `<项目特殊配置和踩坑记录>`

## 构建历史

<!-- 记录最近的构建结果，帮助 Agent 判断当前状态 -->

| 日期 | 提交 | 结果 | 备注 |
|------|------|------|------|
| | | | |
