#!/usr/bin/env python
"""STM32 项目初始化工具。

创建新的 STM32 项目结构，包括必要的目录和文件。

功能：
- 创建标准项目目录结构
- 生成配置文件模板
- 初始化 CubeMX 配置
- 支持从 GitHub 加载模板

使用示例：
  python project_init.py --name my_project --mcu STM32F407VETx
  python project_init.py --name my_project --mcu STM32F407VETx --template scope_siggen
  python project_init.py --name my_project --template https://github.com/user/repo/raw/main/templates/scope_siggen.json
"""

from __future__ import annotations

import argparse
import io
import json
import os
import sys
from pathlib import Path
from urllib.request import urlopen, Request
from urllib.error import URLError

# 编码处理
if sys.stdout and hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

# ======================== GitHub 模板配置 ========================

GITHUB_REPO = "https://api.github.com/repos/your-username/stm32-project-templates/contents/templates"
GITHUB_RAW_BASE = "https://raw.githubusercontent.com/your-username/stm32-project-templates/main/templates"

def load_template_from_github(template_name: str) -> dict | None:
    """从 GitHub 加载模板"""
    try:
        # 如果是完整 URL，直接使用
        if template_name.startswith("http"):
            url = template_name
        else:
            # 否则从仓库加载
            url = f"{GITHUB_RAW_BASE}/{template_name}.json"

        print(f"📥 从 GitHub 加载模板: {url}")
        req = Request(url, headers={"User-Agent": "STM32-Project-Init"})
        with urlopen(req, timeout=10) as response:
            content = response.read().decode("utf-8")
            return json.loads(content)
    except URLError as e:
        print(f"⚠️ GitHub 加载失败: {e}")
        return None
    except json.JSONDecodeError as e:
        print(f"⚠️ JSON 解析失败: {e}")
        return None

def load_template_from_local(template_name: str) -> dict | None:
    """从本地加载模板"""
    # 获取脚本所在目录
    script_dir = Path(__file__).parent.parent
    template_path = script_dir / "templates" / f"{template_name}.json"

    if not template_path.exists():
        return None

    try:
        with open(template_path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        print(f"⚠️ 本地模板加载失败: {e}")
        return None

def load_template(template_name: str, use_github: bool = True) -> dict | None:
    """加载模板（优先 GitHub，回退本地）"""
    template = None

    if use_github:
        template = load_template_from_github(template_name)

    if template is None:
        template = load_template_from_local(template_name)

    return template

# ======================== 项目模板 ========================

PROJECT_STRUCTURE = [
    "Core/Inc",
    "Core/Src",
    "Board",
    "Board/OLED",
    "Board/MPU6050",
    "Board/Balance",
    "Board/Scope",
    "Board/SigGen",
    "Board/VOFA",
    "Board/Bootloader",
    "Drivers",
    "Middlewares",
    "MDK-ARM",
    "Docs"
]

# ======================== 文件模板 ========================

MAIN_C_TEMPLATE = """/**
  ******************************************************************************
  * @file    main.c
  * @brief   主程序文件
  ******************************************************************************
  */

#include "main.h"
#include "gpio.h"

/* 私有函数原型 */
void SystemClock_Config(void);

/**
  * @brief  主函数
  */
int main(void)
{
    /* MCU 配置 */
    HAL_Init();

    /* 配置系统时钟 */
    SystemClock_Config();

    /* 初始化所有配置的外设 */
    MX_GPIO_Init();

    /* 主循环 */
    while (1)
    {
        /* 用户代码 */
        HAL_GPIO_TogglePin(GPIOA, GPIO_PIN_8);
        HAL_Delay(500);
    }
}

/**
  * @brief  系统时钟配置
  */
void SystemClock_Config(void)
{
    RCC_OscInitTypeDef RCC_OscInitStruct = {0};
    RCC_ClkInitTypeDef RCC_ClkInitStruct = {0};

    __HAL_RCC_PWR_CLK_ENABLE();
    __HAL_PWR_VOLTAGESCALING_CONFIG(PWR_REGULATOR_VOLTAGE_SCALE1);

    RCC_OscInitStruct.OscillatorType = RCC_OSCILLATORTYPE_HSE;
    RCC_OscInitStruct.HSEState = RCC_HSE_ON;
    RCC_OscInitStruct.PLL.PLLState = RCC_PLL_ON;
    RCC_OscInitStruct.PLL.PLLSource = RCC_PLLSOURCE_HSE;
    RCC_OscInitStruct.PLL.PLLM = 8;
    RCC_OscInitStruct.PLL.PLLN = 336;
    RCC_OscInitStruct.PLL.PLLP = RCC_PLLP_DIV2;
    RCC_OscInitStruct.PLL.PLLQ = 4;
    if (HAL_RCC_OscConfig(&RCC_OscInitStruct) != HAL_OK)
    {
        Error_Handler();
    }

    RCC_ClkInitStruct.ClockType = RCC_CLOCKTYPE_HCLK | RCC_CLOCKTYPE_SYSCLK
                                | RCC_CLOCKTYPE_PCLK1 | RCC_CLOCKTYPE_PCLK2;
    RCC_ClkInitStruct.SYSCLKSource = RCC_SYSCLKSOURCE_PLLCLK;
    RCC_ClkInitStruct.AHBCLKDivider = RCC_SYSCLK_DIV1;
    RCC_ClkInitStruct.APB1CLKDivider = RCC_HCLK_DIV4;
    RCC_ClkInitStruct.APB2CLKDivider = RCC_HCLK_DIV2;
    if (HAL_RCC_ClockConfig(&RCC_ClkInitStruct, FLASH_LATENCY_5) != HAL_OK)
    {
        Error_Handler();
    }
}

/**
  * @brief  错误处理函数
  */
void Error_Handler(void)
{
    __disable_irq();
    while (1)
    {
    }
}
"""

MAIN_H_TEMPLATE = """/**
  ******************************************************************************
  * @file    main.h
  * @brief   主程序头文件
  ******************************************************************************
  */

#ifndef __MAIN_H
#define __MAIN_H

#ifdef __cplusplus
extern "C" {
#endif

#include "stm32f4xx_hal.h"

/* 引脚定义 */
#define LED_Pin GPIO_PIN_8
#define LED_GPIO_Port GPIOA

/* 函数声明 */
void Error_Handler(void);

#ifdef __cplusplus
}
#endif

#endif /* __MAIN_H */
"""

GPIO_C_TEMPLATE = """/**
  ******************************************************************************
  * @file    gpio.c
  * @brief   GPIO 配置
  ******************************************************************************
  */

#include "gpio.h"

/**
  * @brief  GPIO 初始化
  */
void MX_GPIO_Init(void)
{
    GPIO_InitTypeDef GPIO_InitStruct = {0};

    /* GPIO 时钟使能 */
    __HAL_RCC_GPIOA_CLK_ENABLE();

    /* 配置 GPIO 引脚输出电平 */
    HAL_GPIO_WritePin(LED_GPIO_Port, LED_Pin, GPIO_PIN_RESET);

    /* 配置 GPIO 引脚 */
    GPIO_InitStruct.Pin = LED_Pin;
    GPIO_InitStruct.Mode = GPIO_MODE_OUTPUT_PP;
    GPIO_InitStruct.Pull = GPIO_NOPULL;
    GPIO_InitStruct.Speed = GPIO_SPEED_FREQ_LOW;
    HAL_GPIO_Init(LED_GPIO_Port, &GPIO_InitStruct);
}
"""

GPIO_H_TEMPLATE = """/**
  ******************************************************************************
  * @file    gpio.h
  * @brief   GPIO 配置头文件
  ******************************************************************************
  */

#ifndef __GPIO_H
#define __GPIO_H

#include "main.h"

/* 函数声明 */
void MX_GPIO_Init(void);

#endif /* __GPIO_H */
"""

CONFIG_H_TEMPLATE = """/**
  ******************************************************************************
  * @file    config.h
  * @brief   项目配置文件
  ******************************************************************************
  */

#ifndef __CONFIG_H
#define __CONFIG_H

/* 系统配置 */
#define SYSTEM_CLOCK_HZ         168000000   /* 系统时钟 168MHz */

/* LED 配置 */
#define LED_Pin                 GPIO_PIN_8
#define LED_GPIO_Port           GPIOA

/* 串口配置 */
#define UART_BAUDRATE           115200

/* ADC 配置 */
#define ADC_CHANNEL             ADC_CHANNEL_0

/* DAC 配置 */
#define DAC_CHANNEL             DAC_CHANNEL_1

#endif /* __CONFIG_H */
"""

# ======================== 项目初始化 ========================

def create_project_structure(project_dir: str, project_name: str) -> None:
    """创建项目目录结构"""
    for dir_path in PROJECT_STRUCTURE:
        full_path = os.path.join(project_dir, project_name, dir_path)
        os.makedirs(full_path, exist_ok=True)
        print(f"✅ 创建目录: {dir_path}")

def create_project_files(project_dir: str, project_name: str, template: dict | None = None) -> None:
    """创建项目文件"""
    project_path = os.path.join(project_dir, project_name)

    # 创建 main.c
    with open(os.path.join(project_path, "Core", "Src", "main.c"), "w", encoding="utf-8") as f:
        f.write(MAIN_C_TEMPLATE)
    print("✅ 创建文件: Core/Src/main.c")

    # 创建 main.h
    with open(os.path.join(project_path, "Core", "Inc", "main.h"), "w", encoding="utf-8") as f:
        f.write(MAIN_H_TEMPLATE)
    print("✅ 创建文件: Core/Inc/main.h")

    # 创建 gpio.c
    with open(os.path.join(project_path, "Core", "Src", "gpio.c"), "w", encoding="utf-8") as f:
        f.write(GPIO_C_TEMPLATE)
    print("✅ 创建文件: Core/Src/gpio.c")

    # 创建 gpio.h
    with open(os.path.join(project_path, "Core", "Inc", "gpio.h"), "w", encoding="utf-8") as f:
        f.write(GPIO_H_TEMPLATE)
    print("✅ 创建文件: Core/Inc/gpio.h")

    # 创建 config.h
    with open(os.path.join(project_path, "Board", "config.h"), "w", encoding="utf-8") as f:
        f.write(CONFIG_H_TEMPLATE)
    print("✅ 创建文件: Board/config.h")

    # 如果有模板，创建模板配置文件
    if template:
        template_path = os.path.join(project_path, "Board", "template.json")
        with open(template_path, "w", encoding="utf-8") as f:
            json.dump(template, f, indent=2, ensure_ascii=False)
        print("✅ 创建文件: Board/template.json")

def create_readme(project_dir: str, project_name: str, mcu: str, template: dict | None = None) -> None:
    """创建 README 文件"""
    template_info = ""
    if template:
        template_info = f"""
## 模板信息

- **模板名称**: {template.get('name', 'N/A')}
- **描述**: {template.get('description', 'N/A')}
- **外设**: {', '.join(template.get('peripherals', []))}

### 引脚分配

| 引脚 | 功能 | 标签 |
|------|------|------|
"""
        for pin in template.get('pins', []):
            template_info += f"| {pin.get('pin', 'N/A')} | {pin.get('signal', 'N/A')} | {pin.get('label', 'N/A')} |\n"

    readme_content = f"""# {project_name}

基于 {mcu} 的 STM32 项目
{template_info}
## 项目结构

## 项目结构

```
{project_name}/
├── Core/
│   ├── Inc/        # 头文件
│   └── Src/        # 源文件
├── Board/          # 板级驱动
├── Drivers/        # HAL 驱动
├── Middlewares/    # 中间件
├── MDK-ARM/        # Keil 工程
└── Docs/           # 文档
```

## 编译

```bash
cd MDK-ARM
UV4.exe -b "{project_name}.uvprojx" -t "{project_name}" -o build.log -j0
```

## 烧录

```bash
# ST-LINK
STM32_Programmer_CLI.exe -c port=SWD mode=UR freq=4000 -w {project_name}.axf -v -rst

# USB DFU
python usb_dfu_flash.py --full --port COM3 --firmware {project_name}.hex
```

## 功能

- [ ] LED 闪烁
- [ ] 串口通信
- [ ] ADC 采集
- [ ] DAC 输出

## 许可证

MIT License
"""

    with open(os.path.join(project_dir, project_name, "README.md"), "w", encoding="utf-8") as f:
        f.write(readme_content)
    print("✅ 创建文件: README.md")

# ======================== CLI ========================

def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="STM32 项目初始化工具",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  %(prog)s --name my_project --mcu STM32F407VETx                    # 创建基础项目
  %(prog)s --name my_project --mcu STM32F407VETx --template scope   # 创建示波器项目
  %(prog)s --name my_project --template scope_siggen                # 从本地加载模板
  %(prog)s --name my_project --template https://github.com/user/repo/raw/main/templates/scope_siggen.json  # 从 GitHub 加载
        """,
    )

    parser.add_argument("--name", required=True, help="项目名称")
    parser.add_argument("--mcu", default="STM32F407VETx", help="MCU 型号")
    parser.add_argument("--dir", default=".", help="项目目录")
    parser.add_argument("--template", default="basic",
                        help="项目模板（本地名称或 GitHub URL）")
    parser.add_argument("--local-only", action="store_true",
                        help="仅使用本地模板，不从 GitHub 加载")

    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()

    print(f"🔧 创建项目: {args.name}")
    print(f"   MCU: {args.mcu}")
    print(f"   模板: {args.template}")
    print()

    # 加载模板
    use_github = not args.local_only
    template = load_template(args.template, use_github=use_github)

    if template:
        print(f"✅ 模板加载成功: {template.get('name', args.template)}")
        print(f"   描述: {template.get('description', 'N/A')}")
        print(f"   外设: {', '.join(template.get('peripherals', []))}")
        print()
    else:
        print(f"⚠️ 未找到模板 '{args.template}'，使用默认配置")
        print()

    # 创建项目结构
    create_project_structure(args.dir, args.name)

    # 创建项目文件
    create_project_files(args.dir, args.name, template)

    # 创建 README
    create_readme(args.dir, args.name, args.mcu, template)

    print()
    print(f"✅ 项目创建成功: {args.name}")
    print(f"   位置: {os.path.join(args.dir, args.name)}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
