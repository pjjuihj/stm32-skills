#!/usr/bin/env python
"""STM32CubeMX 配置自动化工具。

解析、修改、生成 .ioc 配置文件，并可调用 CubeMX CLI 生成代码。

功能：
- 解析 .ioc 文件，输出 JSON 格式配置
- 从零创建新 .ioc 文件（指定 MCU、引脚、外设）
- 修改现有 .ioc 文件（添加外设、引脚、时钟、FreeRTOS 任务）
- 自动配置详细参数（ADC、DAC、USART、I2C、TIM 等）
- 调用 CubeMX CLI 生成初始化代码

使用示例：
  python cubemx_config.py --parse project.ioc
  python cubemx_config.py --create --mcu STM32F407VETx --output new.ioc
  python cubemx_config.py --modify project.ioc --add-peripheral USART3
  python cubemx_config.py --modify project.ioc --set-clock --hse 8 --sysclk 168
  python cubemx_config.py --modify project.ioc --add-task --name MyTask --stack 256 --priority Normal
  python cubemx_config.py --modify project.ioc --config-adc --channel 6 --trigger "TIM9_TRGO" --sampling 3
  python cubemx_config.py --modify project.ioc --config-dac --trigger "TIM5_TRGO" --buffer enable
  python cubemx_config.py --modify project.ioc --config-usart --baudrate 115200 --databits 8 --stopbits 1
  python cubemx_config.py --modify project.ioc --config-i2c --speed 400000
  python cubemx_config.py --modify project.ioc --config-tim --prescaler 84 --period 1000 --trigger "TRGO"
  python cubemx_config.py --generate project.ioc --toolchain "MDK-ARM V5"
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import subprocess
import sys
from collections import OrderedDict
from pathlib import Path
from typing import Any, Optional

# 编码处理
if sys.stdout and hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

# 日志配置
logger = logging.getLogger(__name__)

# ======================== 常量 ========================

# CubeMX 默认安装路径
DEFAULT_CUBEMX_PATHS = [
    r"C:\Program Files\STMicroelectronics\STM32Cube\STM32CubeMX\STM32CubeMX.exe",
    r"C:\Program Files (x86)\STMicroelectronics\STM32Cube\STM32CubeMX\STM32CubeMX.exe",
    os.path.expanduser(r"~\STM32CubeMX\STM32CubeMX.exe"),
]

# FreeRTOS 优先级映射
FREERTOS_PRIORITY_MAP = {
    "Idle": 0,
    "Low": 8,
    "Normal": 24,
    "High": 40,
    "Realtime": 56,
}

# 默认时钟频率
DEFAULT_HSE_VALUE = 8000000      # 8 MHz
DEFAULT_APB1_FREQ = 42000000     # 42 MHz
DEFAULT_APB2_FREQ = 84000000     # 84 MHz
DEFAULT_APB1_TIM_FREQ = 84000000 # 84 MHz
DEFAULT_APB2_TIM_FREQ = 168000000 # 168 MHz
DEFAULT_SYSCLK_FREQ = 168000000  # 168 MHz

# ADC 参数范围
ADC_CHANNEL_MIN = 0
ADC_CHANNEL_MAX = 15
ADC_RESOLUTIONS = [6, 8, 10, 12]
ADC_SAMPLING_TIMES = [3, 15, 28, 56, 84, 112, 144, 480]

# DAC 参数范围
DAC_CHANNEL_MIN = 1
DAC_CHANNEL_MAX = 2

# IWDG 参数范围
IWDG_PRESCALER_MIN = 4
IWDG_PRESCALER_MAX = 256
IWDG_RELOAD_MIN = 0
IWDG_RELOAD_MAX = 4095

# APB1 定时器列表
APB1_TIMERS = {"TIM2", "TIM3", "TIM4", "TIM5", "TIM6", "TIM7", "TIM12", "TIM13", "TIM14"}

# MCU 数据库（常用型号）
MCU_DATABASE = {
    "STM32F407VETx": {
        "family": "STM32F4",
        "package": "LQFP100",
        "flash": 512,
        "ram": 128,
        "pins": 100,
    },
    "STM32F407VGTx": {
        "family": "STM32F4",
        "package": "LQFP100",
        "flash": 1024,
        "ram": 128,
        "pins": 100,
    },
    "STM32F401CCU6": {
        "family": "STM32F4",
        "package": "UFQFPN48",
        "flash": 256,
        "ram": 64,
        "pins": 48,
    },
    "STM32F103C8T6": {
        "family": "STM32F1",
        "package": "LQFP48",
        "flash": 64,
        "ram": 20,
        "pins": 48,
    },
}


def _safe_int(value: str, default: int = 0) -> int:
    """安全转换字符串为整数"""
    try:
        return int(value)
    except (ValueError, TypeError):
        return default

# ======================== IOC 解析器 ========================

class IocParser:
    """.ioc 文件解析器"""

    def __init__(self) -> None:
        self.data: OrderedDict[str, str] = OrderedDict()

    def load(self, filepath: str) -> None:
        """加载 .ioc 文件

        Args:
            filepath: .ioc 文件路径

        Raises:
            FileNotFoundError: 文件不存在
            PermissionError: 无读取权限
        """
        path = Path(filepath)
        if not path.exists():
            raise FileNotFoundError(f"IOC 文件不存在: {filepath}")
        if not path.is_file():
            raise ValueError(f"路径不是文件: {filepath}")

        with open(filepath, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                if "=" in line:
                    key, value = line.split("=", 1)
                    self.data[key.strip()] = value.strip()

    def save(self, filepath: str) -> None:
        """保存 .ioc 文件

        Args:
            filepath: 输出文件路径

        Raises:
            PermissionError: 无写入权限
        """
        with open(filepath, "w", encoding="utf-8") as f:
            f.write("#MicroXplorer Configuration settings - do not modify\n")
            for key, value in self.data.items():
                f.write(f"{key}={value}\n")

    def get(self, key: str, default: str = "") -> str:
        """获取配置值"""
        return self.data.get(key, default)

    def set(self, key: str, value: str) -> None:
        """设置配置值"""
        self.data[key] = value

    def get_int(self, key: str, default: int = 0) -> int:
        """安全获取整数值"""
        return _safe_int(self.get(key, str(default)), default)

    def get_section(self, section: str) -> OrderedDict[str, str]:
        """获取指定 section 的所有配置"""
        result = OrderedDict()
        prefix = section + "."
        for key, value in self.data.items():
            if key.startswith(prefix):
                result[key] = value
        return result

    def get_mcu_info(self) -> dict[str, Any]:
        """获取 MCU 信息"""
        return {
            "family": self.get("Mcu.Family"),
            "name": self.get("Mcu.UserName"),
            "package": self.get("Mcu.Package"),
            "device_id": self.get("ProjectManager.DeviceId"),
        }

    def get_pins(self) -> list[dict[str, str]]:
        """获取引脚配置"""
        pins = []
        pin_count = self.get_int("Mcu.PinsNb", 0)
        for i in range(pin_count):
            pin_name = self.get(f"Mcu.Pin{i}")
            if pin_name and not pin_name.startswith("VP_"):
                pin_info: dict[str, str] = {"name": pin_name}
                # 获取引脚信号
                signal = self.get(f"{pin_name}.Signal")
                if signal:
                    pin_info["signal"] = signal
                # 获取引脚模式
                mode = self.get(f"{pin_name}.Mode")
                if mode:
                    pin_info["mode"] = mode
                # 获取 GPIO 参数
                label = self.get(f"{pin_name}.GPIO_Label")
                if label:
                    pin_info["label"] = label
                pins.append(pin_info)
        return pins

    def get_peripherals(self) -> list[str]:
        """获取已配置的外设列表"""
        peripherals = []
        ip_count = self.get_int("Mcu.IPNb", 0)
        for i in range(ip_count):
            ip = self.get(f"Mcu.IP{i}")
            if ip:
                peripherals.append(ip)
        return peripherals

    def get_clock_config(self) -> dict[str, Any]:
        """获取时钟配置"""
        return {
            "hse": self.get("RCC.HSE_VALUE"),
            "hsi": self.get("RCC.HSI_VALUE"),
            "sysclk": self.get("RCC.SYSCLKFreq_VALUE"),
            "hclk": self.get("RCC.HCLKFreq_Value"),
            "apb1": self.get("RCC.APB1Freq_Value"),
            "apb2": self.get("RCC.APB2Freq_Value"),
            "pllm": self.get("RCC.PLLM"),
            "plln": self.get("RCC.PLLN"),
            "pllq": self.get("RCC.PLLQCLKFreq_Value"),
            "pll_source": self.get("RCC.PLLSourceVirtual"),
        }

    def get_freertos_tasks(self) -> list[dict[str, Any]]:
        """获取 FreeRTOS 任务配置"""
        tasks: list[dict[str, Any]] = []
        tasks_str = self.get("FREERTOS.Tasks01")
        if not tasks_str:
            return tasks

        for task_str in tasks_str.split(";"):
            parts = task_str.split(",")
            if len(parts) >= 4:
                tasks.append({
                    "name": parts[0],
                    "priority": _safe_int(parts[1], 24),
                    "stack_size": _safe_int(parts[2], 256),
                    "entry_function": parts[3],
                })
        return tasks

    def to_dict(self) -> dict[str, Any]:
        """转换为字典格式"""
        return {
            "mcu": self.get_mcu_info(),
            "pins": self.get_pins(),
            "peripherals": self.get_peripherals(),
            "clock": self.get_clock_config(),
            "freertos_tasks": self.get_freertos_tasks(),
            "raw": dict(self.data),
        }


# ======================== IOC 修改器 ========================

class IocModifier:
    """.ioc 文件修改器"""

    def __init__(self, ioc: IocParser, verbose: bool = True) -> None:
        self.ioc = ioc
        self.verbose = verbose

    def _log(self, message: str) -> None:
        """输出日志（可通过 verbose 控制）"""
        if self.verbose:
            print(message)

    def _ensure_peripheral(self, name: str) -> None:
        """确保外设已启用（提取重复逻辑）"""
        if name not in self.ioc.get_peripherals():
            self.add_peripheral(name)

    def _append_ip_param(self, peripheral: str, param: str) -> None:
        """追加 IPParameters 参数（避免重复）"""
        ip_params = self.ioc.get(f"{peripheral}.IPParameters", "")
        if param not in ip_params:
            if ip_params:
                ip_params += f",{param}"
            else:
                ip_params = param
            self.ioc.set(f"{peripheral}.IPParameters", ip_params)

    def add_peripheral(self, peripheral: str) -> None:
        """添加外设"""
        # 检查是否已存在
        peripherals = self.ioc.get_peripherals()
        if peripheral in peripherals:
            self._log(f"⚠️ 外设 {peripheral} 已存在")
            return

        # 添加到 IP 列表
        ip_count = self.ioc.get_int("Mcu.IPNb", 0)
        self.ioc.set(f"Mcu.IP{ip_count}", peripheral)
        self.ioc.set("Mcu.IPNb", str(ip_count + 1))

        # 更新 IPParameters
        ip_params = self.ioc.get(f"{peripheral}.IPParameters", "")
        if not ip_params:
            self.ioc.set(f"{peripheral}.IPParameters", "")

        self._log(f"✅ 已添加外设: {peripheral}")

    def add_pin(self, pin: str, signal: str, mode: str = "", label: str = "",
                gpio_params: Optional[dict[str, str]] = None) -> None:
        """添加引脚配置

        Args:
            pin: 引脚名称 (如 PA8)
            signal: 信号名称 (如 GPIO_Output)
            mode: 模式 (可选)
            label: 引脚标签 (可选)
            gpio_params: GPIO 参数字典 (可选)
        """
        # 检查是否已存在
        pin_count = self.ioc.get_int("Mcu.PinsNb", 0)
        for i in range(pin_count):
            if self.ioc.get(f"Mcu.Pin{i}") == pin:
                self._log(f"⚠️ 引脚 {pin} 已存在，将更新配置")
                break
        else:
            # 添加新引脚
            self.ioc.set(f"Mcu.Pin{pin_count}", pin)
            self.ioc.set("Mcu.PinsNb", str(pin_count + 1))

        # 设置信号
        self.ioc.set(f"{pin}.Signal", signal)

        # 设置模式
        if mode:
            self.ioc.set(f"{pin}.Mode", mode)

        # 设置标签
        if label:
            self.ioc.set(f"{pin}.GPIO_Label", label)
            if gpio_params is None:
                gpio_params = {}
            gpio_params.setdefault("GPIO_Label", label)

        # 设置 GPIO 参数
        if gpio_params:
            params_str = ",".join(gpio_params.keys())
            self.ioc.set(f"{pin}.GPIOParameters", params_str)
            for key, value in gpio_params.items():
                self.ioc.set(f"{pin}.{key}", value)

        self._log(f"✅ 已配置引脚: {pin} -> {signal}")

    def set_clock(self, hse: Optional[int] = None, sysclk: Optional[int] = None,
                  apb1_div: Optional[int] = None, apb2_div: Optional[int] = None,
                  pllp: int = 2) -> None:
        """配置时钟树

        Args:
            hse: HSE 频率 (MHz)
            sysclk: SYSCLK 频率 (MHz)
            apb1_div: APB1 分频系数 (1, 2, 4, 8, 16)
            apb2_div: APB2 分频系数 (1, 2, 4, 8, 16)
            pllp: PLLP 分频系数 (2, 4, 6, 8)
        """
        if hse is not None:
            self.ioc.set("RCC.HSE_VALUE", str(hse * 1000000))
            self._log(f"✅ HSE: {hse} MHz")

        if sysclk is not None:
            # 计算 PLL 参数
            hse_val = self.ioc.get_int("RCC.HSE_VALUE", DEFAULT_HSE_VALUE)
            pllm = hse_val // 1000000  # VCO 输入 1 MHz
            if pllm == 0:
                pllm = 1  # 防止除零

            # PLLN = (SYSCLK * PLLP) / (HSE / PLLM)
            # SYSCLK 单位是 MHz，需要转换为 Hz
            vco_input = hse_val // pllm  # VCO 输入频率
            if vco_input == 0:
                vco_input = 1  # 防止除零
            plln = (sysclk * 1000000 * pllp) // vco_input
            if plln == 0:
                plln = 1  # 防止除零
            pllq = plln * 1000000 // 48000000  # USB 时钟 48 MHz
            if pllq == 0:
                pllq = 1  # 防止除零

            self.ioc.set("RCC.PLLM", str(pllm))
            self.ioc.set("RCC.PLLN", str(plln))
            self.ioc.set("RCC.PLLQCLKFreq_Value", str(plln * 1000000 // pllp))
            self.ioc.set("RCC.SYSCLKFreq_VALUE", str(sysclk * 1000000))
            self.ioc.set("RCC.HCLKFreq_Value", str(sysclk * 1000000))
            self.ioc.set("RCC.CortexFreq_Value", str(sysclk * 1000000))
            self.ioc.set("RCC.FCLKCortexFreq_Value", str(sysclk * 1000000))
            self.ioc.set("RCC.AHBFreq_Value", str(sysclk * 1000000))
            self.ioc.set("RCC.PLLCLKFreq_Value", str(sysclk * 1000000))
            self.ioc.set("RCC.MCO2PinFreq_Value", str(sysclk * 1000000))
            self.ioc.set("RCC.EthernetFreq_Value", str(sysclk * 1000000))

            # 计算 APB 频率
            if apb1_div is None:
                apb1_div = 4 if sysclk >= 84 else 1
            if apb2_div is None:
                apb2_div = 2 if sysclk >= 84 else 1

            # 确保分频系数有效
            if apb1_div not in [1, 2, 4, 8, 16]:
                apb1_div = 4
            if apb2_div not in [1, 2, 4, 8, 16]:
                apb2_div = 2

            apb1_freq = sysclk // apb1_div
            apb2_freq = sysclk // apb2_div

            self.ioc.set("RCC.APB1CLKDivider", f"RCC_HCLK_DIV{apb1_div}")
            self.ioc.set("RCC.APB1Freq_Value", str(apb1_freq * 1000000))
            self.ioc.set("RCC.APB1TimFreq_Value", str(apb1_freq * 2 * 1000000))
            self.ioc.set("RCC.APB2CLKDivider", f"RCC_HCLK_DIV{apb2_div}")
            self.ioc.set("RCC.APB2Freq_Value", str(apb2_freq * 1000000))
            self.ioc.set("RCC.APB2TimFreq_Value", str(apb2_freq * 2 * 1000000))

            self._log(f"✅ SYSCLK: {sysclk} MHz, APB1: {apb1_freq} MHz, APB2: {apb2_freq} MHz")

    def add_freertos_task(self, name: str, stack_size: int = 256,
                          priority: str = "Normal", entry_function: str = "") -> None:
        """添加 FreeRTOS 任务

        Args:
            name: 任务名称（不能包含逗号或分号）
            stack_size: 栈大小（字节）
            priority: 优先级 (Idle, Low, Normal, High, Realtime)
            entry_function: 入口函数名（默认为 Start{name}）
        """
        # 验证任务名称
        if not name or "," in name or ";" in name:
            self._log(f"❌ 无效的任务名称: {name}")
            return

        # 确保 FreeRTOS 已启用
        self._ensure_peripheral("FREERTOS")
        if "FREERTOS" not in self.ioc.get_peripherals():
            self.ioc.set("VP_FREERTOS_VS_CMSIS_V2.Mode", "CMSIS_V2")
            self.ioc.set("VP_FREERTOS_VS_CMSIS_V2.Signal", "FREERTOS_VS_CMSIS_V2")
            self.ioc.set("FREERTOS.configTOTAL_HEAP_SIZE", "16384")
            self.ioc.set("FREERTOS.configCHECK_FOR_STACK_OVERFLOW", "2")
            self.ioc.set("FREERTOS.FootprintOK", "true")

        # 获取优先级数值
        priority_val = FREERTOS_PRIORITY_MAP.get(priority, 24)

        # 生成入口函数名
        if not entry_function:
            entry_function = f"Start{name}"

        # 获取现有任务列表
        tasks_str = self.ioc.get("FREERTOS.Tasks01", "")
        new_task = f"{name},{priority_val},{stack_size},{entry_function},Default,NULL,Dynamic,NULL,NULL"

        if tasks_str:
            self.ioc.set("FREERTOS.Tasks01", f"{tasks_str};{new_task}")
        else:
            self.ioc.set("FREERTOS.Tasks01", new_task)

        # 更新 IPParameters
        self._append_ip_param("FREERTOS", "Tasks01")

        self._log(f"✅ 已添加 FreeRTOS 任务: {name} (优先级={priority}, 栈={stack_size})")

    def set_usart(self, usart: str, baudrate: int = 115200, mode: str = "Asynchronous") -> None:
        """配置 USART"""
        self._ensure_peripheral(usart)
        self.ioc.set(f"{usart}.BaudRate", str(baudrate))
        self.ioc.set(f"{usart}.VirtualMode", "VM_ASYNC")
        self._append_ip_param(usart, "VirtualMode")
        self._append_ip_param(usart, "BaudRate")
        self._log(f"✅ 已配置 {usart}: {baudrate} bps")

    def set_i2c(self, i2c: str, speed: int = 100000) -> None:
        """配置 I2C"""
        self._ensure_peripheral(i2c)
        self.ioc.set(f"{i2c}.Speed", str(speed))
        self._append_ip_param(i2c, "Speed")
        self._log(f"✅ 已配置 {i2c}: {speed} Hz")

    def config_adc(self, adc: str = "ADC1", channel: int = 6,
                   trigger: str = "TIM9_TRGO", sampling: int = 3,
                   resolution: int = 12, alignment: str = "Right") -> None:
        """配置 ADC 详细参数

        Args:
            adc: ADC 外设名称
            channel: ADC 通道号 (0-15)
            trigger: 触发源 (TIM9_TRGO, TIM2_TRGO, SOFTWARE 等)
            sampling: 采样周期 (3, 15, 28, 56, 84, 112, 144, 480)
            resolution: 分辨率 (6, 8, 10, 12)
            alignment: 数据对齐 (Right, Left)

        Raises:
            ValueError: 参数超出有效范围
        """
        # 输入验证
        if not ADC_CHANNEL_MIN <= channel <= ADC_CHANNEL_MAX:
            self._log(f"❌ ADC 通道号必须在 {ADC_CHANNEL_MIN}-{ADC_CHANNEL_MAX} 之间，实际为 {channel}")
            return
        if resolution not in ADC_RESOLUTIONS:
            self._log(f"❌ ADC 分辨率必须是 {ADC_RESOLUTIONS} 之一，实际为 {resolution}")
            return

        # 确保 ADC 外设已启用
        self._ensure_peripheral(adc)

        # ADC 基本配置
        self.ioc.set(f"{adc}.ScanConvMode", "DISABLE")
        self.ioc.set(f"{adc}.ContinuousConvMode", "DISABLE")
        self.ioc.set(f"{adc}.DiscontinuousConvMode", "DISABLE")
        self.ioc.set(f"{adc}.ExternalTrigConvEdge", "ADC_EXTERNALTRIGCONVEDGE_RISING")
        self.ioc.set(f"{adc}.ExternalTrigConv", f"ADC_EXTERNALTRIGCONV_{trigger}")
        self.ioc.set(f"{adc}.DataAlign", f"ADC_DATAALIGN_{alignment.upper()}")
        self.ioc.set(f"{adc}.NbrOfConversion", "1")
        self.ioc.set(f"{adc}.DMAContinuousRequests", "DISABLE")
        self.ioc.set(f"{adc}.EOCSelection", "ADC_EOC_SINGLE_CONV")

        # 分辨率
        self.ioc.set(f"{adc}.Resolution", f"ADC_RESOLUTION_{resolution}B")

        # 通道配置
        ch_name = f"ADC1_IN{channel}"
        self.ioc.set(f"{adc}.Channel-{ch_name}", f"ADC_CHANNEL_{channel}")
        self.ioc.set(f"{adc}.Rank-{ch_name}", "1")

        # 采样时间（查找最接近的值）
        sampling_map = {
            3: "ADC_SAMPLETIME_3CYCLES",
            15: "ADC_SAMPLETIME_15CYCLES",
            28: "ADC_SAMPLETIME_28CYCLES",
            56: "ADC_SAMPLETIME_56CYCLES",
            84: "ADC_SAMPLETIME_84CYCLES",
            112: "ADC_SAMPLETIME_112CYCLES",
            144: "ADC_SAMPLETIME_144CYCLES",
            480: "ADC_SAMPLETIME_480CYCLES",
        }
        # 查找最接近的采样时间
        closest = min(sampling_map.keys(), key=lambda x: abs(x - sampling))
        self.ioc.set(f"{adc}.SamplingTime-{ch_name}", sampling_map[closest])

        # IPParameters
        self._append_ip_param(adc, "Resolution")
        self._append_ip_param(adc, "ScanConvMode")
        self._append_ip_param(adc, "ContinuousConvMode")
        self._append_ip_param(adc, "ExternalTrigConv")
        self._append_ip_param(adc, "ExternalTrigConvEdge")
        self._append_ip_param(adc, "DataAlign")
        self._append_ip_param(adc, "NbrOfConversion")
        self._append_ip_param(adc, f"Channel-{ch_name}")
        self._append_ip_param(adc, f"Rank-{ch_name}")
        self._append_ip_param(adc, f"SamplingTime-{ch_name}")

        self._log(f"✅ 已配置 {adc}: 通道{channel}, 触发={trigger}, 采样={closest}周期, 分辨率={resolution}位")

    def config_dac(self, dac: str = "DAC", channel: int = 1,
                   trigger: str = "TIM5_TRGO", buffer: str = "enable") -> None:
        """配置 DAC 详细参数

        Args:
            dac: DAC 外设名称
            channel: DAC 通道号 (1 或 2)
            trigger: 触发源 (TIM5_TRGO, TIM6_TRGO, SOFTWARE 等)
            buffer: 输出缓冲 (enable 或 disable)
        """
        # 输入验证
        if not DAC_CHANNEL_MIN <= channel <= DAC_CHANNEL_MAX:
            self._log(f"❌ DAC 通道号必须在 {DAC_CHANNEL_MIN}-{DAC_CHANNEL_MAX} 之间，实际为 {channel}")
            return

        # 确保 DAC 外设已启用
        self._ensure_peripheral(dac)

        # DAC 通道配置
        ch_name = f"DAC_OUT{channel}"
        self.ioc.set(f"{dac}.Channel-{ch_name}", f"DAC_CHANNEL_{channel}")

        # 触发配置
        self.ioc.set(f"{dac}.Trigger-{ch_name}", f"DAC_TRIGGER_{trigger}")
        self.ioc.set(f"{dac}.OutputBuffer-{ch_name}", f"DAC_OUTPUTBUFFER_{buffer.upper()}")

        # 生成模式（默认禁用，使用软件触发）
        self.ioc.set(f"{dac}.WaveGeneration-{ch_name}", "DAC_WAVEGENERATION_NONE")

        # IPParameters
        self._append_ip_param(dac, f"Channel-{ch_name}")
        self._append_ip_param(dac, f"Trigger-{ch_name}")
        self._append_ip_param(dac, f"OutputBuffer-{ch_name}")
        self._append_ip_param(dac, f"WaveGeneration-{ch_name}")

        self._log(f"✅ 已配置 {dac}: 通道{channel}, 触发={trigger}, 缓冲={buffer}")

    def config_usart(self, usart: str = "USART2", baudrate: int = 115200,
                     databits: int = 8, stopbits: float = 1, parity: str = "None") -> None:
        """配置 USART 详细参数

        Args:
            usart: USART 外设名称
            baudrate: 波特率
            databits: 数据位 (8 或 9)
            stopbits: 停止位 (1 或 2)
            parity: 校验位 (None, Even, Odd)
        """
        # 确保 USART 外设已启用
        self._ensure_peripheral(usart)

        # 基本配置
        self.ioc.set(f"{usart}.BaudRate", str(baudrate))
        self.ioc.set(f"{usart}.VirtualMode", "VM_ASYNC")

        # 数据位
        if databits == 9:
            self.ioc.set(f"{usart}.WordLength", "UART_WORDLENGTH_9B")
        else:
            self.ioc.set(f"{usart}.WordLength", "UART_WORDLENGTH_8B")

        # 停止位
        if stopbits == 2:
            self.ioc.set(f"{usart}.StopBits", "UART_STOPBITS_2")
        else:
            self.ioc.set(f"{usart}.StopBits", "UART_STOPBITS_1")

        # 校验位
        if parity == "Even":
            self.ioc.set(f"{usart}.Parity", "UART_PARITY_EVEN")
        elif parity == "Odd":
            self.ioc.set(f"{usart}.Parity", "UART_PARITY_ODD")
        else:
            self.ioc.set(f"{usart}.Parity", "UART_PARITY_NONE")

        # 模式（TX+RX）
        self.ioc.set(f"{usart}.Mode", "MODE_TX_RX")

        # IPParameters
        self._append_ip_param(usart, "VirtualMode")
        self._append_ip_param(usart, "BaudRate")
        self._append_ip_param(usart, "WordLength")
        self._append_ip_param(usart, "StopBits")
        self._append_ip_param(usart, "Parity")
        self._append_ip_param(usart, "Mode")

        self._log(f"✅ 已配置 {usart}: {baudrate}bps, {databits}数据位, {stopbits}停止位, {parity}校验")

    def config_i2c(self, i2c: str = "I2C1", speed: int = 400000,
                   addressing: int = 7) -> None:
        """配置 I2C 详细参数

        Args:
            i2c: I2C 外设名称
            speed: 速度 (100000 或 400000)
            addressing: 地址模式 (7 或 10)
        """
        # 确保 I2C 外设已启用
        peripherals = self.ioc.get_peripherals()
        if i2c not in peripherals:
            self.add_peripheral(i2c)

        # 速度配置
        self.ioc.set(f"{i2c}.Speed", str(speed))

        # 速度模式
        if speed >= 400000:
            self.ioc.set(f"{i2c}.SpeedMode", "I2C_SPEEDMODE_FAST")
        else:
            self.ioc.set(f"{i2c}.SpeedMode", "I2C_SPEEDMODE_STANDARD")

        # 地址模式
        if addressing == 10:
            self.ioc.set(f"{i2c}.AddressingMode", "I2C_ADDRESSINGMODE_10BIT")
        else:
            self.ioc.set(f"{i2c}.AddressingMode", "I2C_ADDRESSINGMODE_7BIT")

        # IPParameters
        self.ioc.set(f"{i2c}.IPParameters", "Speed,SpeedMode,AddressingMode")

        self._log(f"✅ 已配置 {i2c}: {speed}Hz, {addressing}位地址")

    def config_tim(self, tim: str = "TIM9", prescaler: int = 84,
                   period: int = 1000, counter_mode: str = "Up",
                   trigger: str = "TRGO") -> None:
        """配置定时器详细参数

        Args:
            tim: 定时器外设名称
            prescaler: 预分频系数
            period: 周期/重装载值
            counter_mode: 计数模式 (Up, Down, CenterAligned1/2/3)
            trigger: 触发输出 (TRGO, OC1REF, OC2REF 等)
        """
        # 输入验证
        if prescaler == 0:
            self._log(f"❌ 定时器预分频不能为 0")
            return
        if period == 0:
            self._log(f"❌ 定时器周期不能为 0")
            return

        # 确保定时器外设已启用
        self._ensure_peripheral(tim)

        # 预分频和周期
        self.ioc.set(f"{tim}.Prescaler", f"{prescaler}-1")
        self.ioc.set(f"{tim}.Period", f"{period}-1")

        # 计数模式
        mode_map = {
            "Down": "TIM_COUNTERMODE_DOWN",
            "CenterAligned1": "CENTERALIGNED1",
            "CenterAligned2": "CENTERALIGNED2",
            "CenterAligned3": "CENTERALIGNED3",
        }
        self.ioc.set(f"{tim}.CounterMode", mode_map.get(counter_mode, "TIM_COUNTERMODE_UP"))

        # 触发输出配置
        trigger_map = {
            "TRGO": "TIM_TRGO_UPDATE",
            "OC1REF": "TIM_TRGO_OC1REF",
            "OC2REF": "TIM_TRGO_OC2REF",
        }
        self.ioc.set(f"{tim}.TriggerOutput", trigger_map.get(trigger, "TIM_TRGO_UPDATE"))

        # IPParameters
        self._append_ip_param(tim, "Prescaler")
        self._append_ip_param(tim, "Period")
        self._append_ip_param(tim, "CounterMode")
        self._append_ip_param(tim, "TriggerOutput")

        # 计算实际频率
        if tim in APB1_TIMERS:
            timer_freq = self.ioc.get_int("RCC.APB1TimFreq_Value", DEFAULT_APB1_TIM_FREQ)
        else:
            timer_freq = self.ioc.get_int("RCC.APB2TimFreq_Value", DEFAULT_APB2_TIM_FREQ)

        actual_freq = timer_freq / prescaler / period
        self._log(f"✅ 已配置 {tim}: 预分频={prescaler}, 周期={period}, 实际频率={actual_freq:.1f}Hz")

    def config_nvic(self, irq: str, priority: int = 5, enabled: bool = True) -> None:
        """配置 NVIC 中断优先级

        Args:
            irq: 中断名称 (如 USART1_IRQn)
            priority: 抢占优先级 (0-15)
            enabled: 是否启用
        """
        # 输入验证
        if not 0 <= priority <= 15:
            self._log(f"❌ NVIC 优先级必须在 0-15 之间，实际为 {priority}")
            return

        # NVIC 配置格式: enabled\:preemption\:sub\:...
        enabled_str = "true" if enabled else "false"
        config = f"{enabled_str}\\:{priority}\\:0\\:false\\:false\\:true\\:true\\:true\\:true"

        self.ioc.set(f"NVIC.{irq}", config)

        # 更新 NVIC IPParameters
        self._append_ip_param("NVIC", irq)

        self._log(f"✅ 已配置 NVIC: {irq} (优先级={priority}, {'启用' if enabled else '禁用'})")

    def config_scope_siggen(self, adc_channel: int = 6, dac_channel: int = 1,
                            usart: str = "USART2", baudrate: int = 115200) -> None:
        """一键配置串口示波器 + 信号发生器

        Args:
            adc_channel: ADC 通道号 (示波器输入)
            dac_channel: DAC 通道号 (信号发生器输出)
            usart: 串口外设
            baudrate: 串口波特率
        """
        self._log("\n🔧 一键配置串口示波器 + 信号发生器")
        self._log("=" * 50)

        # 1. 配置 ADC (示波器)
        self.config_adc(
            adc="ADC1",
            channel=adc_channel,
            trigger="TIM9_TRGO",
            sampling=3,
            resolution=12,
            alignment="Right"
        )

        # 2. 配置 DAC (信号发生器)
        self.config_dac(
            dac="DAC",
            channel=dac_channel,
            trigger="TIM5_TRGO",
            buffer="enable"
        )

        # 3. 配置 USART (串口通信)
        self.config_usart(
            usart=usart,
            baudrate=baudrate,
            databits=8,
            stopbits=1,
            parity="None"
        )

        # 4. 配置 I2C1 (OLED 显示)
        self.config_i2c(
            i2c="I2C1",
            speed=400000,
            addressing=7
        )

        # 5. 配置定时器
        # TIM9: ADC 触发 (1kHz 采样率)
        self.config_tim(
            tim="TIM9",
            prescaler=84,
            period=1000,
            counter_mode="Up",
            trigger="TRGO"
        )

        # TIM5: DAC 触发 (500Hz 输出)
        self.config_tim(
            tim="TIM5",
            prescaler=84,
            period=2000,
            counter_mode="Up",
            trigger="TRGO"
        )

        # 6. 配置 NVIC 中断
        self.config_nvic("TIM5_IRQn", priority=6, enabled=True)
        self.config_nvic("TIM1_BRK_TIM9_IRQn", priority=6, enabled=True)
        self.config_nvic(f"{usart}_IRQn", priority=5, enabled=True)

        self._log("\n✅ 串口示波器 + 信号发生器配置完成！")

    def config_dma(self, dma_stream: str = "DMA2_Stream0", channel: int = 0,
                   direction: str = "PeripheralToMemory", mode: str = "Normal",
                   priority: str = "Low", request: str = "ADC1") -> None:
        """配置 DMA 详细参数

        Args:
            dma_stream: DMA 流名称 (如 DMA2_Stream0)
            channel: DMA 通道号 (0-15)
            direction: 传输方向 (PeripheralToMemory, MemoryToPeripheral, MemoryToMemory)
            mode: 模式 (Normal, Circular)
            priority: 优先级 (Low, Medium, High, VeryHigh)
            request: 关联的外设请求
        """
        # DMA 通道配置
        self.ioc.set(f"{dma_stream}.Channel", f"DMA_CHANNEL_{channel}")

        # 传输方向
        if direction == "MemoryToPeripheral":
            self.ioc.set(f"{dma_stream}.Direction", "DMA_MEMORY_TO_PERIPH")
        elif direction == "MemoryToMemory":
            self.ioc.set(f"{dma_stream}.Direction", "DMA_MEMORY_TO_MEMORY")
        else:
            self.ioc.set(f"{dma_stream}.Direction", "DMA_PERIPH_TO_MEMORY")

        # 模式
        if mode == "Circular":
            self.ioc.set(f"{dma_stream}.Mode", "DMA_CIRCULAR")
        else:
            self.ioc.set(f"{dma_stream}.Mode", "DMA_NORMAL")

        # 优先级
        if priority == "Medium":
            self.ioc.set(f"{dma_stream}.Priority", "DMA_PRIORITY_MEDIUM")
        elif priority == "High":
            self.ioc.set(f"{dma_stream}.Priority", "DMA_PRIORITY_HIGH")
        elif priority == "VeryHigh":
            self.ioc.set(f"{dma_stream}.Priority", "DMA_PRIORITY_VERY_HIGH")
        else:
            self.ioc.set(f"{dma_stream}.Priority", "DMA_PRIORITY_LOW")

        # 关联外设
        self.ioc.set(f"{dma_stream}.Request", f"DMA_REQUEST_{request}")

        # 数据宽度
        self.ioc.set(f"{dma_stream}.PeriphDataAlignment", "DMA_PDATAALIGN_WORD")
        self.ioc.set(f"{dma_stream}.MemDataAlignment", "DMA_MDATAALIGN_WORD")

        # 地址自增
        self.ioc.set(f"{dma_stream}.PeriphInc", "DMA_PINC_DISABLE")
        self.ioc.set(f"{dma_stream}.MemInc", "DMA_MINC_ENABLE")

        # IPParameters
        self.ioc.set(f"{dma_stream}.IPParameters", "Channel,Direction,Mode,Priority,Request,PeriphDataAlignment,MemDataAlignment,PeriphInc,MemInc")

        self._log(f"✅ 已配置 {dma_stream}: 通道{channel}, 方向={direction}, 模式={mode}, 优先级={priority}")

    def config_spi(self, spi: str = "SPI1", mode: str = "Master",
                   direction: str = "FullDuplex", datasize: int = 8,
                   cpol: str = "Low", cpha: str = "Edge1", prescaler: int = 2) -> None:
        """配置 SPI 详细参数

        Args:
            spi: SPI 外设名称
            mode: 模式 (Master, Slave)
            direction: 方向 (FullDuplex, HalfDuplex, ReceiveOnly, TransmitOnly)
            datasize: 数据大小 (8, 16)
            cpol: 时钟极性 (Low, High)
            cpha: 时钟相位 (Edge1, Edge2)
            prescaler: 预分频系数 (2, 4, 8, 16, 32, 64, 128, 256)
        """
        # 确保 SPI 外设已启用
        self._ensure_peripheral(spi)

        # 模式
        if mode == "Slave":
            self.ioc.set(f"{spi}.Mode", "SPI_MODE_SLAVE")
        else:
            self.ioc.set(f"{spi}.Mode", "SPI_MODE_MASTER")

        # 方向（修复 HalfDuplex 映射）
        direction_map = {
            "FullDuplex": "SPI_DIRECTION_2LINES",
            "HalfDuplex": "SPI_DIRECTION_1LINE",  # 修复：HalfDuplex 应该是 1LINE
            "ReceiveOnly": "SPI_DIRECTION_2LINES_RXONLY",
            "TransmitOnly": "SPI_DIRECTION_1LINE",
        }
        self.ioc.set(f"{spi}.Direction", direction_map.get(direction, "SPI_DIRECTION_2LINES"))

        # 数据大小
        if datasize == 16:
            self.ioc.set(f"{spi}.DataSize", "SPI_DATASIZE_16BIT")
        else:
            self.ioc.set(f"{spi}.DataSize", "SPI_DATASIZE_8BIT")

        # 时钟极性
        if cpol == "High":
            self.ioc.set(f"{spi}.CLKPolarity", "SPI_POLARITY_HIGH")
        else:
            self.ioc.set(f"{spi}.CLKPolarity", "SPI_POLARITY_LOW")

        # 时钟相位
        if cpha == "Edge2":
            self.ioc.set(f"{spi}.CLKPhase", "SPI_PHASE_2EDGE")
        else:
            self.ioc.set(f"{spi}.CLKPhase", "SPI_PHASE_1EDGE")

        # 预分频
        self.ioc.set(f"{spi}.BaudRatePrescaler", f"SPI_BAUDRATEPRESCALER_{prescaler}")

        # NSS 管理
        self.ioc.set(f"{spi}.NSS", "SPI_NSS_SOFT")

        # 其他设置
        self.ioc.set(f"{spi}.FirstBit", "SPI_FIRSTBIT_MSB")
        self.ioc.set(f"{spi}.TIMode", "SPI_TIMODE_DISABLE")
        self.ioc.set(f"{spi}.CRCCalculation", "SPI_CRCCALCULATION_DISABLE")

        # IPParameters
        self._append_ip_param(spi, "Mode")
        self._append_ip_param(spi, "Direction")
        self._append_ip_param(spi, "DataSize")
        self._append_ip_param(spi, "CLKPolarity")
        self._append_ip_param(spi, "CLKPhase")
        self._append_ip_param(spi, "BaudRatePrescaler")
        self._append_ip_param(spi, "NSS")
        self._append_ip_param(spi, "FirstBit")
        self._append_ip_param(spi, "TIMode")
        self._append_ip_param(spi, "CRCCalculation")

        self._log(f"✅ 已配置 {spi}: 模式={mode}, 方向={direction}, 数据={datasize}位, CPOL={cpol}, CPHA={cpha}")

    def config_rtc(self, rtc: str = "RTC", clock_source: str = "LSE",
                   format: str = "24h", date_format: str = "DD/MM/YYYY") -> None:
        """配置 RTC 详细参数

        Args:
            rtc: RTC 外设名称
            clock_source: 时钟源 (LSE, LSI, HSE)
            format: 时间格式 (24h, 12h)
            date_format: 日期格式 (DD/MM/YYYY, MM/DD/YYYY, YYYY/MM/DD)
        """
        # 确保 RTC 外设已启用
        peripherals = self.ioc.get_peripherals()
        if rtc not in peripherals:
            self.add_peripheral(rtc)

        # 时钟源配置
        if clock_source == "LSE":
            self.ioc.set("VP_RTC_VS_LSE_Asynchronous", "RCC_RTCCLKSOURCE_LSE")
            self.ioc.set("RCC.RTCClockSelection", "RCC_RTCCLKSOURCE_LSE")
        elif clock_source == "LSI":
            self.ioc.set("VP_RTC_VS_LSI_Asynchronous", "RCC_RTCCLKSOURCE_LSI")
            self.ioc.set("RCC.RTCClockSelection", "RCC_RTCCLKSOURCE_LSI")
        else:  # HSE
            self.ioc.set("VP_RTC_VS_HSE_Asynchronous", "RCC_RTCCLKSOURCE_HSE_DIV128")
            self.ioc.set("RCC.RTCClockSelection", "RCC_RTCCLKSOURCE_HSE_DIV128")

        # 时间格式
        if format == "12h":
            self.ioc.set(f"{rtc}.HourFormat", "RTC_HOURFORMAT_12")
        else:
            self.ioc.set(f"{rtc}.HourFormat", "RTC_HOURFORMAT_24")

        # 异步预分频
        self.ioc.set(f"{rtc}.AsynchPrediv", "127")

        # 同步预分频
        self.ioc.set(f"{rtc}.SynchPrediv", "255")

        # 日期格式
        if date_format == "MM/DD/YYYY":
            self.ioc.set(f"{rtc}.DateMode", "RTC_DATEMODE_MMDDYYYY")
        elif date_format == "YYYY/MM/DD":
            self.ioc.set(f"{rtc}.DateMode", "RTC_DATEMODE_YYYYMMDD")
        else:
            self.ioc.set(f"{rtc}.DateMode", "RTC_DATEMODE_DDMMYYYY")

        # IPParameters
        self.ioc.set(f"{rtc}.IPParameters", "HourFormat,AsynchPrediv,SynchPrediv,DateMode")

        self._log(f"✅ 已配置 {rtc}: 时钟源={clock_source}, 格式={format}, 日期格式={date_format}")

    def config_can(self, can: str = "CAN1", mode: str = "Normal",
                   baudrate: int = 500000, sjw: int = 1, bs1: int = 6, bs2: int = 8,
                   apb1_freq: int = DEFAULT_APB1_FREQ) -> None:
        """配置 CAN 详细参数

        Args:
            can: CAN 外设名称
            mode: 模式 (Normal, Loopback, Silent, SilentLoopback)
            baudrate: 波特率 (125000, 250000, 500000, 1000000)
            sjw: 同步跳转宽度 (1, 2, 3, 4)
            bs1: 位段 1 (1-16)
            bs2: 位段 2 (1-8)
            apb1_freq: APB1 时钟频率 (Hz)
        """
        # 输入验证
        if baudrate == 0:
            self._log(f"❌ CAN 波特率不能为 0")
            return

        # 确保 CAN 外设已启用
        self._ensure_peripheral(can)

        # 模式
        mode_map = {
            "Loopback": "CAN_MODE_LOOPBACK",
            "Silent": "CAN_MODE_SILENT",
            "SilentLoopback": "CAN_MODE_SILENT_LOOPBACK",
        }
        self.ioc.set(f"{can}.Mode", mode_map.get(mode, "CAN_MODE_NORMAL"))

        # 波特率计算
        prescaler = apb1_freq // (baudrate * (1 + bs1 + bs2))
        if prescaler == 0:
            prescaler = 1  # 防止除零
            self._log(f"⚠️ CAN 预分频计算结果为 0，已调整为 1")

        # 时间段配置
        self.ioc.set(f"{can}.TimeSeg1", f"CAN_BS1_{bs1}TQ")
        self.ioc.set(f"{can}.TimeSeg2", f"CAN_BS2_{bs2}TQ")
        self.ioc.set(f"{can}.SyncJumpWidth", f"CAN_SJW_{sjw}TQ")
        self.ioc.set(f"{can}.Prescaler", str(prescaler))

        # 其他设置
        self.ioc.set(f"{can}.TimeTriggeredMode", "DISABLE")
        self.ioc.set(f"{can}.AutoBusOff", "DISABLE")
        self.ioc.set(f"{can}.AutoWakeUp", "DISABLE")
        self.ioc.set(f"{can}.AutoRetransmission", "ENABLE")
        self.ioc.set(f"{can}.ReceiveFifoLocked", "DISABLE")
        self.ioc.set(f"{can}.TransmitFifoPriority", "DISABLE")

        # IPParameters
        self._append_ip_param(can, "Mode")
        self._append_ip_param(can, "TimeSeg1")
        self._append_ip_param(can, "TimeSeg2")
        self._append_ip_param(can, "SyncJumpWidth")
        self._append_ip_param(can, "Prescaler")
        self._append_ip_param(can, "TimeTriggeredMode")
        self._append_ip_param(can, "AutoBusOff")
        self._append_ip_param(can, "AutoWakeUp")
        self._append_ip_param(can, "AutoRetransmission")
        self._append_ip_param(can, "ReceiveFifoLocked")
        self._append_ip_param(can, "TransmitFifoPriority")

        self._log(f"✅ 已配置 {can}: 模式={mode}, 波特率={baudrate}, 预分频={prescaler}")

    def config_gpio(self, pin: str, mode: str = "Output", speed: str = "High",
                    pull: str = "NoPull", label: str = "", initial_state: int = 0) -> None:
        """配置 GPIO 详细参数

        Args:
            pin: 引脚名称 (如 PA8)
            mode: 模式 (Input, Output, AlternateFunction, Analog)
            speed: 速度 (Low, Medium, High, VeryHigh)
            pull: 上下拉 (NoPull, PullUp, PullDown)
            label: 引脚标签
            initial_state: 初始状态 (0 或 1)
        """
        # 引脚信号
        self.ioc.set(f"{pin}.Signal", "GPIO_Output" if mode == "Output" else "GPIO_Input")

        # 模式
        mode_map = {
            "Input": "GPIO_MODE_INPUT",
            "AlternateFunction": "GPIO_MODE_AF_PP",
            "Analog": "GPIO_MODE_ANALOG",
        }
        self.ioc.set(f"{pin}.GPIO_Mode", mode_map.get(mode, "GPIO_MODE_OUTPUT_PP"))

        # 速度
        speed_map = {
            "Low": "GPIO_SPEED_FREQ_LOW",
            "Medium": "GPIO_SPEED_FREQ_MEDIUM",
            "VeryHigh": "GPIO_SPEED_FREQ_VERY_HIGH",
        }
        self.ioc.set(f"{pin}.GPIO_Speed", speed_map.get(speed, "GPIO_SPEED_FREQ_HIGH"))

        # 上下拉
        pull_map = {
            "PullUp": "GPIO_PULLUP",
            "PullDown": "GPIO_PULLDOWN",
        }
        self.ioc.set(f"{pin}.GPIO_PuPd", pull_map.get(pull, "GPIO_NOPULL"))

        # 标签
        if label:
            self.ioc.set(f"{pin}.GPIO_Label", label)

        # 初始状态
        if mode == "Output":
            self.ioc.set(f"{pin}.PinState", "GPIO_PIN_SET" if initial_state == 1 else "GPIO_PIN_RESET")

        # IPParameters
        params = ["GPIO_Mode", "GPIO_Speed", "GPIO_PuPd"]
        if label:
            params.append("GPIO_Label")
        if mode == "Output":
            params.append("PinState")
        self.ioc.set(f"{pin}.GPIOParameters", ",".join(params))

        self._log(f"✅ 已配置 {pin}: 模式={mode}, 速度={speed}, 上下拉={pull}" + (f", 标签={label}" if label else ""))

    def config_pwm(self, tim: str = "TIM3", channel: int = 1,
                   prescaler: int = 84, period: int = 20000,
                   pulse: int = 1500, polarity: str = "High") -> None:
        """配置 PWM 详细参数

        Args:
            tim: 定时器外设名称
            channel: 通道号 (1-4)
            prescaler: 预分频系数
            period: 周期/重装载值
            pulse: 初始脉宽
            polarity: 极性 (High, Low)
        """
        # 确保定时器外设已启用
        peripherals = self.ioc.get_peripherals()
        if tim not in peripherals:
            self.add_peripheral(tim)

        # 预分频和周期
        self.ioc.set(f"{tim}.Prescaler", f"{prescaler}-1")
        self.ioc.set(f"{tim}.Period", f"{period}-1")

        # PWM 模式
        ch_name = f"PWM Generation{channel} CH{channel}"
        self.ioc.set(f"{tim}.Channel-PWM Generation{channel} CH{channel}", f"TIM_CHANNEL_{channel}")
        self.ioc.set(f"{tim}.Pulse-PWM Generation{channel} CH{channel}", str(pulse))

        # 极性
        if polarity == "Low":
            self.ioc.set(f"{tim}.OC-PWM Generation{channel} CH{channel}", "TIM_OCPOLARITY_LOW")
        else:
            self.ioc.set(f"{tim}.OC-PWM Generation{channel} CH{channel}", "TIM_OCPOLARITY_HIGH")

        # 计算实际频率和占空比
        sysclk = int(self.ioc.get("RCC.SYSCLKFreq_VALUE", "168000000"))
        if tim in ["TIM2", "TIM3", "TIM4", "TIM5", "TIM6", "TIM7", "TIM12", "TIM13", "TIM14"]:
            apb_freq = int(self.ioc.get("RCC.APB1TimFreq_Value", "84000000"))
        else:
            apb_freq = int(self.ioc.get("RCC.APB2TimFreq_Value", "168000000"))

        actual_freq = apb_freq / prescaler / period
        duty_cycle = pulse / period * 100

        # IPParameters
        self.ioc.set(f"{tim}.IPParameters", f"Prescaler,Period,Channel-PWM Generation{channel} CH{channel},Pulse-PWM Generation{channel} CH{channel},OC-PWM Generation{channel} CH{channel}")

        self._log(f"✅ 已配置 {tim} CH{channel}: 频率={actual_freq:.1f}Hz, 占空比={duty_cycle:.1f}%, 脉宽={pulse}")

    def config_encoder(self, tim: str = "TIM2", mode: str = "TI12",
                       period: int = 65535, polarity: str = "Rising") -> None:
        """配置编码器接口

        Args:
            tim: 定时器外设名称
            mode: 模式 (TI1, TI2, TI12)
            period: 周期/重装载值
            polarity: 边沿极性 (Rising, Falling, Both)
        """
        # 确保定时器外设已启用
        peripherals = self.ioc.get_peripherals()
        if tim not in peripherals:
            self.add_peripheral(tim)

        # 编码器模式
        if mode == "TI1":
            self.ioc.set(f"{tim}.EncoderMode", "TIM_ENCODERMODE_TI1")
        elif mode == "TI2":
            self.ioc.set(f"{tim}.EncoderMode", "TIM_ENCODERMODE_TI2")
        else:
            self.ioc.set(f"{tim}.EncoderMode", "TIM_ENCODERMODE_TI12")

        # 周期
        self.ioc.set(f"{tim}.Period", str(period))

        # IC1 极性
        if polarity == "Falling":
            self.ioc.set(f"{tim}.IC1Polarity", "TIM_ICPOLARITY_FALLING")
        elif polarity == "Both":
            self.ioc.set(f"{tim}.IC1Polarity", "TIM_ICPOLARITY_BOTHEDGE")
        else:
            self.ioc.set(f"{tim}.IC1Polarity", "TIM_ICPOLARITY_RISING")

        # IC2 极性
        self.ioc.set(f"{tim}.IC2Polarity", self.ioc.get(f"{tim}.IC1Polarity"))

        # IPParameters
        self.ioc.set(f"{tim}.IPParameters", "EncoderMode,Period,IC1Polarity,IC2Polarity")

        self._log(f"✅ 已配置 {tim} 编码器: 模式={mode}, 周期={period}, 极性={polarity}")

    def config_watchdog(self, iwdg: str = "IWDG", prescaler: int = 64,
                        reload: int = 625, window: int = 0) -> None:
        """配置看门狗

        Args:
            iwdg: IWDG 外设名称
            prescaler: 预分频系数 (4, 8, 16, 32, 64, 128, 256)
            reload: 重装载值 (0-4095)
            window: 窗口值 (0-4095, 0 表示禁用窗口功能)
        """
        # 输入验证
        if not IWDG_RELOAD_MIN <= reload <= IWDG_RELOAD_MAX:
            self._log(f"❌ IWDG 重装载值必须在 {IWDG_RELOAD_MIN}-{IWDG_RELOAD_MAX} 之间，实际为 {reload}")
            return

        # 确保 IWDG 外设已启用
        self._ensure_peripheral(iwdg)

        # 预分频（查找最接近的值）
        prescaler_map = {
            4: "IWDG_PRESCALER_4",
            8: "IWDG_PRESCALER_8",
            16: "IWDG_PRESCALER_16",
            32: "IWDG_PRESCALER_32",
            64: "IWDG_PRESCALER_64",
            128: "IWDG_PRESCALER_128",
            256: "IWDG_PRESCALER_256",
        }
        closest = min(prescaler_map.keys(), key=lambda x: abs(x - prescaler))
        self.ioc.set(f"{iwdg}.Prescaler", prescaler_map[closest])

        # 重装载值
        self.ioc.set(f"{iwdg}.Reload", str(reload))

        # 窗口值
        if window > 0:
            self.ioc.set(f"{iwdg}.Window", str(window))

        # 计算超时时间
        lsi_freq = 32000  # LSI 典型频率 32kHz
        timeout_ms = (reload * closest) / lsi_freq * 1000

        # IPParameters
        self._append_ip_param(iwdg, "Prescaler")
        self._append_ip_param(iwdg, "Reload")

        self._log(f"✅ 已配置 {iwdg}: 预分频={closest}, 重装载={reload}, 超时≈{timeout_ms:.0f}ms")

    def config_system(self, debug: str = "SerialWire", sysclk_source: str = "PLL",
                      voltage_scale: str = "Scale1", prefetch: bool = True) -> None:
        """配置系统参数

        Args:
            debug: 调试接口 (SerialWire, JTAG, TraceAsSw, TraceAsync, Disable)
            sysclk_source: 系统时钟源 (HSI, HSE, PLL)
            voltage_scale: 电压调节 (Scale1, Scale2, Scale3)
            prefetch: 是否启用预取
        """
        # 调试接口
        if debug == "JTAG":
            self.ioc.set("SYS.JTAGSerial", "Full_JTAG")
        elif debug == "TraceAsSw":
            self.ioc.set("SYS.JTAGSerial", "TraceAsynchronousSw")
        elif debug == "TraceAsync":
            self.ioc.set("SYS.JTAGSerial", "TraceAsynchronous")
        elif debug == "Disable":
            self.ioc.set("SYS.JTAGSerial", "Disable")
        else:
            self.ioc.set("SYS.JTAGSerial", "Serial_Wire")

        # 系统时钟源
        if sysclk_source == "HSI":
            self.ioc.set("RCC.SYSCLKSource", "RCC_SYSCLKSOURCE_HSI")
        elif sysclk_source == "HSE":
            self.ioc.set("RCC.SYSCLKSource", "RCC_SYSCLKSOURCE_HSE")
        else:
            self.ioc.set("RCC.SYSCLKSource", "RCC_SYSCLKSOURCE_PLLCLK")

        # 电压调节
        if voltage_scale == "Scale2":
            self.ioc.set("PWR.VOS", "PWR_REGULATOR_VOLTAGE_SCALE2")
        elif voltage_scale == "Scale3":
            self.ioc.set("PWR.VOS", "PWR_REGULATOR_VOLTAGE_SCALE3")
        else:
            self.ioc.set("PWR.VOS", "PWR_REGULATOR_VOLTAGE_SCALE1")

        # 预取
        if prefetch:
            self.ioc.set("Flash.Prefetch", "ENABLE")
            self.ioc.set("Flash.InstructionCache", "ENABLE")
            self.ioc.set("Flash.DataCache", "ENABLE")
        else:
            self.ioc.set("Flash.Prefetch", "DISABLE")

        # IPParameters
        self.ioc.set("SYS.IPParameters", "JTAGSerial")
        self.ioc.set("RCC.IPParameters", self.ioc.get("RCC.IPParameters", "") + ",SYSCLKSource")
        self.ioc.set("PWR.IPParameters", "VOS")

        self._log(f"✅ 已配置系统: 调试={debug}, 时钟源={sysclk_source}, 电压={voltage_scale}, 预取={'启用' if prefetch else '禁用'}")

    def config_fmc(self, fmc: str = "FMC", memory_type: str = "SRAM",
                   data_width: int = 16, address_width: int = 20,
                   read_cycle: int = 15, write_cycle: int = 15) -> None:
        """配置 FMC 外部存储器

        Args:
            fmc: FMC 外设名称
            memory_type: 存储器类型 (SRAM, SDRAM, NOR, NAND)
            data_width: 数据宽度 (8, 16, 32)
            address_width: 地址宽度 (8, 16, 20, 24)
            read_cycle: 读周期 (ns)
            write_cycle: 写周期 (ns)
        """
        # 确保 FMC 外设已启用
        self._ensure_peripheral(fmc)

        # 存储器类型
        type_map = {
            "SDRAM": "FMC_MEMORY_TYPE_SDRAM",
            "NOR": "FMC_MEMORY_TYPE_NOR",
            "NAND": "FMC_MEMORY_TYPE_NAND",
        }
        self.ioc.set(f"{fmc}.MemoryType", type_map.get(memory_type, "FMC_MEMORY_TYPE_SRAM"))

        # 数据宽度
        width_map = {
            8: "FMC_NORSRAM_MEM_BUS_WIDTH_8",
            32: "FMC_NORSRAM_MEM_BUS_WIDTH_32",
        }
        self.ioc.set(f"{fmc}.MemoryDataWidth", width_map.get(data_width, "FMC_NORSRAM_MEM_BUS_WIDTH_16"))

        # 地址建立时间（使用地址宽度作为近似值）
        self.ioc.set(f"{fmc}.AddressSetupTime", str(address_width))

        # 读写周期
        self.ioc.set(f"{fmc}.DataSetupTime", str(read_cycle))
        self.ioc.set(f"{fmc}.BusTurnAroundDuration", str(write_cycle))

        # IPParameters
        self._append_ip_param(fmc, "MemoryType")
        self._append_ip_param(fmc, "MemoryDataWidth")
        self._append_ip_param(fmc, "AddressSetupTime")
        self._append_ip_param(fmc, "DataSetupTime")
        self._append_ip_param(fmc, "BusTurnAroundDuration")

        self._log(f"✅ 已配置 {fmc}: 类型={memory_type}, 数据={data_width}位, 地址={address_width}位, 读周期={read_cycle}ns, 写周期={write_cycle}ns")

    def config_dcmi(self, dcmi: str = "DCMI", capture_rate: str = "AllFrame",
                    synchro_mode: str = "Hardware", pck_polarity: str = "Rising",
                    vs_polarity: str = "High", hs_polarity: str = "High") -> None:
        """配置 DCMI 摄像头接口

        Args:
            dcmi: DCMI 外设名称
            capture_rate: 采集速率 (AllFrame, HalfFrame)
            synchro_mode: 同步模式 (Hardware, Software)
            pck_polarity: 像素时钟极性 (Rising, Falling)
            vs_polarity: 垂直同步极性 (High, Low)
            hs_polarity: 水平同步极性 (High, Low)
        """
        # 确保 DCMI 外设已启用
        peripherals = self.ioc.get_peripherals()
        if dcmi not in peripherals:
            self.add_peripheral(dcmi)

        # 采集速率
        if capture_rate == "HalfFrame":
            self.ioc.set(f"{dcmi}.CaptureRate", "DCMI_CR_ALTERNATE_4")
        else:
            self.ioc.set(f"{dcmi}.CaptureRate", "DCMI_CR_ALL_FRAME")

        # 同步模式
        if synchro_mode == "Software":
            self.ioc.set(f"{dcmi}.SynchroMode", "DCMI_SYNCHRO_EMBEDDED")
        else:
            self.ioc.set(f"{dcmi}.SynchroMode", "DCMI_SYNCHRO_HARDWARE")

        # 像素时钟极性
        if pck_polarity == "Falling":
            self.ioc.set(f"{dcmi}.PCKPolarity", "DCMI_PCKPOLARITY_FALLING")
        else:
            self.ioc.set(f"{dcmi}.PCKPolarity", "DCMI_PCKPOLARITY_RISING")

        # 垂直同步极性
        if vs_polarity == "Low":
            self.ioc.set(f"{dcmi}.VSPolarity", "DCMI_VSPOLARITY_LOW")
        else:
            self.ioc.set(f"{dcmi}.VSPolarity", "DCMI_VSPOLARITY_HIGH")

        # 水平同步极性
        if hs_polarity == "Low":
            self.ioc.set(f"{dcmi}.HSPolarity", "DCMI_HSPOLARITY_LOW")
        else:
            self.ioc.set(f"{dcmi}.HSPolarity", "DCMI_HSPOLARITY_HIGH")

        # IPParameters
        self.ioc.set(f"{dcmi}.IPParameters", "CaptureRate,SynchroMode,PCKPolarity,VSPolarity,HSPolarity")

        self._log(f"✅ 已配置 {dcmi}: 采集={capture_rate}, 同步={synchro_mode}, PCK={pck_polarity}, VS={vs_polarity}, HS={hs_polarity}")

    def config_eth(self, eth: str = "ETH", mode: str = "MII",
                   speed: int = 100, duplex: str = "Full",
                   mac_address: str = "00:80:E1:00:00:00") -> None:
        """配置以太网

        Args:
            eth: ETH 外设名称
            mode: 接口模式 (MII, RMII)
            speed: 速度 (10, 100)
            duplex: 双工模式 (Full, Half)
            mac_address: MAC 地址 (格式: XX:XX:XX:XX:XX:XX)
        """
        # 确保 ETH 外设已启用
        self._ensure_peripheral(eth)

        # 接口模式
        self.ioc.set(f"{eth}.MediaInterface", "ETH_MEDIA_IF_RMII" if mode == "RMII" else "ETH_MEDIA_IF_MII")

        # 速度
        self.ioc.set(f"{eth}.Speed", "ETH_SPEED_10M" if speed == 10 else "ETH_SPEED_100M")

        # 双工模式
        self.ioc.set(f"{eth}.DuplexMode", "ETH_MODE_HALFDUPLEX" if duplex == "Half" else "ETH_MODE_FULLDUPLEX")

        # MAC 地址验证和配置
        mac_parts = mac_address.split(":")
        if len(mac_parts) == 6:
            for i, part in enumerate(mac_parts):
                try:
                    val = int(part, 16)
                    if not 0 <= val <= 255:
                        self._log(f"❌ MAC 地址段 {i+1} 超出范围: {part}")
                        return
                    self.ioc.set(f"{eth}.MACAddr{i}", str(val))
                except ValueError:
                    self._log(f"❌ MAC 地址段 {i+1} 不是有效的十六进制: {part}")
                    return
        else:
            self._log(f"❌ MAC 地址格式错误: {mac_address} (需要 XX:XX:XX:XX:XX:XX)")
            return

        # IPParameters
        self._append_ip_param(eth, "MediaInterface")
        self._append_ip_param(eth, "Speed")
        self._append_ip_param(eth, "DuplexMode")
        for i in range(6):
            self._append_ip_param(eth, f"MACAddr{i}")

        self._log(f"✅ 已配置 {eth}: 模式={mode}, 速度={speed}Mbps, 双工={duplex}, MAC={mac_address}")

    def config_usb_device(self, usb: str = "USB_OTG_FS", class_type: str = "CDC",
                          speed: str = "Full", vbus_sensing: bool = True) -> None:
        """配置 USB 设备

        Args:
            usb: USB 外设名称
            class_type: 设备类 (CDC, HID, MSC, DFU, Custom)
            speed: 速度 (Full, High)
            vbus_sensing: VBUS 检测
        """
        # 确保 USB 外设已启用
        self._ensure_peripheral(usb)

        # 设备模式
        self.ioc.set(f"{usb}.Mode", "DEVICE_VBUS")

        # 速度
        self.ioc.set(f"{usb}.Speed", "USB_OTG_HS_SPEED" if speed == "High" else "USB_OTG_FS_SPEED")

        # VBUS 检测
        self.ioc.set(f"{usb}.VbusSensing", "ENABLE" if vbus_sensing else "DISABLE")

        # 设备类
        class_map = {
            "CDC": "CDC",
            "HID": "HID",
            "MSC": "MSC",
            "DFU": "DFU",
        }
        self.ioc.set(f"{usb}.ClassType", class_map.get(class_type, "Custom"))

        # IPParameters
        self._append_ip_param(usb, "Mode")
        self._append_ip_param(usb, "Speed")
        self._append_ip_param(usb, "VbusSensing")
        self._append_ip_param(usb, "ClassType")

        self._log(f"✅ 已配置 {usb}: 类型={class_type}, 速度={speed}, VBUS={'启用' if vbus_sensing else '禁用'}")

    def config_usb_host(self, usb: str = "USB_OTG_FS", speed: str = "Full",
                        vbus_sensing: bool = True) -> None:
        """配置 USB 主机

        Args:
            usb: USB 外设名称
            speed: 速度 (Full, High)
            vbus_sensing: VBUS 检测
        """
        # 确保 USB 外设已启用
        self._ensure_peripheral(usb)

        # 主机模式
        self.ioc.set(f"{usb}.Mode", "HOST_VBUS")

        # 速度
        self.ioc.set(f"{usb}.Speed", "USB_OTG_HS_SPEED" if speed == "High" else "USB_OTG_FS_SPEED")

        # VBUS 检测
        self.ioc.set(f"{usb}.VbusSensing", "ENABLE" if vbus_sensing else "DISABLE")

        # IPParameters
        self._append_ip_param(usb, "Mode")
        self._append_ip_param(usb, "Speed")
        self._append_ip_param(usb, "VbusSensing")

        self._log(f"✅ 已配置 {usb}: 主机模式, 速度={speed}, VBUS={'启用' if vbus_sensing else '禁用'}")

    def config_power(self, mode: str = "Run", voltage_scale: str = "Scale1",
                     pvd_enabled: bool = False, pvd_level: float = 2.9) -> None:
        """配置电源管理

        Args:
            mode: 运行模式 (Run, Sleep, Stop, Standby)
            voltage_scale: 电压调节 (Scale1, Scale2, Scale3)
            pvd_enabled: PVD 使能
            pvd_level: PVD 电压阈值 (2.0-2.9V)
        """
        # 运行模式
        mode_map = {
            "Sleep": "PWR_LOWPOWERMODE_SLEEP",
            "Stop": "PWR_LOWPOWERMODE_STOP",
            "Standby": "PWR_LOWPOWERMODE_STANDBY",
        }
        self.ioc.set("PWR.LowPowerMode", mode_map.get(mode, "PWR_LOWPOWERMODE_DISABLE"))

        # 电压调节
        scale_map = {
            "Scale2": "PWR_REGULATOR_VOLTAGE_SCALE2",
            "Scale3": "PWR_REGULATOR_VOLTAGE_SCALE3",
        }
        self.ioc.set("PWR.VOS", scale_map.get(voltage_scale, "PWR_REGULATOR_VOLTAGE_SCALE1"))

        # PVD 配置
        if pvd_enabled:
            self.ioc.set("PWR.PVD", "ENABLE")
            # PVD 电压阈值（查找最接近的级别）
            pvd_levels = [2.2, 2.3, 2.4, 2.5, 2.6, 2.7, 2.8, 2.9]
            closest_idx = min(range(len(pvd_levels)), key=lambda i: abs(pvd_levels[i] - pvd_level))
            self.ioc.set("PWR.PLS", f"PWR_PVDLEVEL_{closest_idx}")
        else:
            self.ioc.set("PWR.PVD", "DISABLE")

        # IPParameters
        self._append_ip_param("PWR", "LowPowerMode")
        self._append_ip_param("PWR", "VOS")
        self._append_ip_param("PWR", "PVD")
        self._append_ip_param("PWR", "PLS")

        self._log(f"✅ 已配置电源: 模式={mode}, 电压={voltage_scale}, PVD={'启用' if pvd_enabled else '禁用'}")

    def config_rtc_alarm(self, rtc: str = "RTC", alarm: int = 1,
                         mask: str = "None", wake_up: bool = False) -> None:
        """配置 RTC 闹钟

        Args:
            rtc: RTC 外设名称
            alarm: 闹钟编号 (1, 2)
            mask: 掩码 (None, DateWeekDay, Hours, Minutes, Seconds, All)
            wake_up: 唤醒使能
        """
        # 确保 RTC 外设已启用
        self._ensure_peripheral(rtc)

        # 闹钟掩码
        mask_map = {
            "All": "RTC_ALARMMASK_ALL",
            "DateWeekDay": "RTC_ALARMMASK_DATEWEEKDAY",
            "Hours": "RTC_ALARMMASK_HOURS",
            "Minutes": "RTC_ALARMMASK_MINUTES",
            "Seconds": "RTC_ALARMMASK_SECONDS",
        }
        mask_value = mask_map.get(mask, "RTC_ALARMMASK_NONE")

        if alarm == 1:
            self.ioc.set(f"{rtc}.AlarmMask", mask_value)
        else:
            self.ioc.set(f"{rtc}.AlarmMaskB", mask_value)

        # 唤醒使能
        if wake_up:
            self.ioc.set(f"{rtc}.WakeUp", "ENABLE")
            self.ioc.set(f"{rtc}.WakeUpClock", "RTC_WAKEUPCLOCK_CK_SPRE_16BITS")
            self.ioc.set(f"{rtc}.WakeUpCounter", "0")
        else:
            self.ioc.set(f"{rtc}.WakeUp", "DISABLE")

        # IPParameters
        param_name = "AlarmMask" if alarm == 1 else "AlarmMaskB"
        self._append_ip_param(rtc, param_name)
        self._append_ip_param(rtc, "WakeUp")
        self._append_ip_param(rtc, "WakeUpClock")
        self._append_ip_param(rtc, "WakeUpCounter")

        self._log(f"✅ 已配置 RTC 闹钟{alarm}: 掩码={mask}, 唤醒={'启用' if wake_up else '禁用'}")

    def config_iwdg_window(self, iwdg: str = "IWDG", window: int = 0) -> None:
        """配置 IWDG 窗口看门狗

        Args:
            iwdg: IWDG 外设名称
            window: 窗口值 (0-4095, 0 表示禁用窗口功能)
        """
        # 确保 IWDG 外设已启用
        peripherals = self.ioc.get_peripherals()
        if iwdg not in peripherals:
            self.add_peripheral(iwdg)

        # 窗口值
        if window > 0:
            self.ioc.set(f"{iwdg}.Window", str(window))
        else:
            self.ioc.set(f"{iwdg}.Window", "0")

        # IPParameters
        self.ioc.set(f"{iwdg}.IPParameters", self.ioc.get(f"{iwdg}.IPParameters", "") + ",Window")

        self._log(f"✅ 已配置 {iwdg} 窗口: {window}")

    def config_dma_circular(self, dma_stream: str = "DMA2_Stream0", channel: int = 0,
                            request: str = "ADC1", buffer_size: int = 1024) -> None:
        """配置 DMA 循环模式

        Args:
            dma_stream: DMA 流名称
            channel: DMA 通道号
            request: 关联的外设请求
            buffer_size: 缓冲区大小
        """
        # DMA 通道配置
        self.ioc.set(f"{dma_stream}.Channel", f"DMA_CHANNEL_{channel}")

        # 传输方向
        self.ioc.set(f"{dma_stream}.Direction", "DMA_PERIPH_TO_MEMORY")

        # 循环模式
        self.ioc.set(f"{dma_stream}.Mode", "DMA_CIRCULAR")

        # 优先级
        self.ioc.set(f"{dma_stream}.Priority", "DMA_PRIORITY_HIGH")

        # 关联外设
        self.ioc.set(f"{dma_stream}.Request", f"DMA_REQUEST_{request}")

        # 数据宽度
        self.ioc.set(f"{dma_stream}.PeriphDataAlignment", "DMA_PDATAALIGN_WORD")
        self.ioc.set(f"{dma_stream}.MemDataAlignment", "DMA_MDATAALIGN_WORD")

        # 地址自增
        self.ioc.set(f"{dma_stream}.PeriphInc", "DMA_PINC_DISABLE")
        self.ioc.set(f"{dma_stream}.MemInc", "DMA_MINC_ENABLE")

        # IPParameters
        self._append_ip_param(dma_stream, "Channel")
        self._append_ip_param(dma_stream, "Direction")
        self._append_ip_param(dma_stream, "Mode")
        self._append_ip_param(dma_stream, "Priority")
        self._append_ip_param(dma_stream, "Request")
        self._append_ip_param(dma_stream, "PeriphDataAlignment")
        self._append_ip_param(dma_stream, "MemDataAlignment")
        self._append_ip_param(dma_stream, "PeriphInc")
        self._append_ip_param(dma_stream, "MemInc")

        self._log(f"✅ 已配置 {dma_stream} 循环模式: 通道{channel}, 请求={request}, 缓冲={buffer_size}")

    def config_fatfs(self, fatfs: str = "FATFS", drive: str = "SD",
                     max_filename: int = 255, code_page: int = 437) -> None:
        """配置 FatFS 文件系统

        Args:
            fatfs: FATFS 外设名称
            drive: 驱动器 (SD, USB, RAM)
            max_filename: 最大文件名长度
            code_page: 代码页 (437=US, 936=GBK)
        """
        # 确保 FATFS 外设已启用
        self._ensure_peripheral(fatfs)

        # 驱动器类型
        drive_map = {
            "USB": "FATFS_DRIVE_USB",
            "RAM": "FATFS_DRIVE_RAM",
        }
        self.ioc.set(f"{fatfs}.Drive", drive_map.get(drive, "FATFS_DRIVE_SD"))

        # 最大文件名长度
        self.ioc.set(f"{fatfs}.MaxFilename", str(max_filename))

        # 代码页
        self.ioc.set(f"{fatfs}.CodePage", str(code_page))

        # IPParameters
        self._append_ip_param(fatfs, "Drive")
        self._append_ip_param(fatfs, "MaxFilename")
        self._append_ip_param(fatfs, "CodePage")

        self._log(f"✅ 已配置 {fatfs}: 驱动={drive}, 最大文件名={max_filename}, 代码页={code_page}")

    def config_lwip(self, lwip: str = "LWIP", dhcp: bool = True,
                    ip_address: str = "192.168.1.100",
                    subnet_mask: str = "255.255.255.0",
                    gateway: str = "192.168.1.1") -> None:
        """配置 LwIP 网络协议栈

        Args:
            lwip: LWIP 外设名称
            dhcp: DHCP 使能
            ip_address: IP 地址
            subnet_mask: 子网掩码
            gateway: 网关地址
        """

        def _validate_ip(ip: str, name: str) -> Optional[list[str]]:
            """验证 IP 地址格式"""
            parts = ip.split(".")
            if len(parts) != 4:
                self._log(f"❌ {name} 格式错误: {ip} (需要 4 段)")
                return None
            for part in parts:
                try:
                    val = int(part)
                    if not 0 <= val <= 255:
                        self._log(f"❌ {name} 段值超出范围: {part} (需要 0-255)")
                        return None
                except ValueError:
                    self._log(f"❌ {name} 段不是数字: {part}")
                    return None
            return parts

        # 确保 LWIP 外设已启用
        self._ensure_peripheral(lwip)

        # DHCP 配置
        self.ioc.set(f"{lwip}.DHCP", "ENABLE" if dhcp else "DISABLE")

        # IP 地址
        ip_parts = _validate_ip(ip_address, "IP 地址")
        if ip_parts:
            self.ioc.set(f"{lwip}.IP_ADDRESS0", ip_parts[0])
            self.ioc.set(f"{lwip}.IP_ADDRESS1", ip_parts[1])
            self.ioc.set(f"{lwip}.IP_ADDRESS2", ip_parts[2])
            self.ioc.set(f"{lwip}.IP_ADDRESS3", ip_parts[3])

        # 子网掩码
        mask_parts = _validate_ip(subnet_mask, "子网掩码")
        if mask_parts:
            self.ioc.set(f"{lwip}.NETMASK0", mask_parts[0])
            self.ioc.set(f"{lwip}.NETMASK1", mask_parts[1])
            self.ioc.set(f"{lwip}.NETMASK2", mask_parts[2])
            self.ioc.set(f"{lwip}.NETMASK3", mask_parts[3])

        # 网关地址
        gw_parts = _validate_ip(gateway, "网关地址")
        if gw_parts:
            self.ioc.set(f"{lwip}.GATEWAY0", gw_parts[0])
            self.ioc.set(f"{lwip}.GATEWAY1", gw_parts[1])
            self.ioc.set(f"{lwip}.GATEWAY2", gw_parts[2])
            self.ioc.set(f"{lwip}.GATEWAY3", gw_parts[3])

        # IPParameters
        self._append_ip_param(lwip, "DHCP")
        self._append_ip_param(lwip, "IP_ADDRESS0")
        self._append_ip_param(lwip, "IP_ADDRESS1")
        self._append_ip_param(lwip, "IP_ADDRESS2")
        self._append_ip_param(lwip, "IP_ADDRESS3")
        self._append_ip_param(lwip, "NETMASK0")
        self._append_ip_param(lwip, "NETMASK1")
        self._append_ip_param(lwip, "NETMASK2")
        self._append_ip_param(lwip, "NETMASK3")
        self._append_ip_param(lwip, "GATEWAY0")
        self._append_ip_param(lwip, "GATEWAY1")
        self._append_ip_param(lwip, "GATEWAY2")
        self._append_ip_param(lwip, "GATEWAY3")

        self._log(f"✅ 已配置 {lwip}: DHCP={'启用' if dhcp else '禁用'}, IP={ip_address}")

    def config_freertos_heap(self, freertos: str = "FREERTOS", heap_size: int = 16384,
                             stack_overflow_check: int = 2,
                             use_trace: bool = True,
                             use_mutexes: bool = True,
                             use_recursive_mutexes: bool = True) -> None:
        """配置 FreeRTOS 堆和调试

        Args:
            freertos: FREERTOS 外设名称
            heap_size: 堆大小 (字节)
            stack_overflow_check: 栈溢出检查 (0=禁用, 1=仅检查高水位, 2=检查高水位+模式)
            use_trace: 使用跟踪
            use_mutexes: 使用互斥锁
            use_recursive_mutexes: 使用递归互斥锁
        """
        # 确保 FREERTOS 外设已启用
        self._ensure_peripheral(freertos)

        # 堆大小
        self.ioc.set(f"{freertos}.configTOTAL_HEAP_SIZE", str(heap_size))

        # 栈溢出检查
        self.ioc.set(f"{freertos}.configCHECK_FOR_STACK_OVERFLOW", str(stack_overflow_check))

        # 跟踪
        self.ioc.set(f"{freertos}.configUSE_TRACE_FACILITY", "1" if use_trace else "0")

        # 互斥锁
        self.ioc.set(f"{freertos}.configUSE_MUTEXES", "1" if use_mutexes else "0")

        # 递归互斥锁
        self.ioc.set(f"{freertos}.configUSE_RECURSIVE_MUTEXES", "1" if use_recursive_mutexes else "0")

        # IPParameters
        self._append_ip_param(freertos, "configTOTAL_HEAP_SIZE")
        self._append_ip_param(freertos, "configCHECK_FOR_STACK_OVERFLOW")
        self._append_ip_param(freertos, "configUSE_TRACE_FACILITY")
        self._append_ip_param(freertos, "configUSE_MUTEXES")
        self._append_ip_param(freertos, "configUSE_RECURSIVE_MUTEXES")

        self._log(f"✅ 已配置 FreeRTOS: 堆={heap_size}字节, 栈溢出检查={stack_overflow_check}")

    def config_freertos_task(self, name: str, stack_size: int = 256,
                             priority: str = "Normal", entry_function: str = "",
                             parameters: str = "NULL") -> None:
        """添加 FreeRTOS 任务

        Args:
            name: 任务名称
            stack_size: 栈大小 (字节)
            priority: 优先级 (Idle, Low, Normal, High, Realtime)
            entry_function: 入口函数名
            parameters: 任务参数
        """
        # 验证任务名称
        if not name or "," in name or ";" in name:
            self._log(f"❌ 无效的任务名称: {name}")
            return

        # 确保 FreeRTOS 已启用
        self._ensure_peripheral("FREERTOS")
        if "FREERTOS" not in self.ioc.get_peripherals():
            self.ioc.set("VP_FREERTOS_VS_CMSIS_V2.Mode", "CMSIS_V2")
            self.ioc.set("VP_FREERTOS_VS_CMSIS_V2.Signal", "FREERTOS_VS_CMSIS_V2")
            self.ioc.set("FREERTOS.configTOTAL_HEAP_SIZE", "16384")
            self.ioc.set("FREERTOS.configCHECK_FOR_STACK_OVERFLOW", "2")

        # 获取优先级数值
        priority_val = FREERTOS_PRIORITY_MAP.get(priority, 24)

        # 生成入口函数名
        if not entry_function:
            entry_function = f"Start{name}"

        # 获取现有任务列表
        tasks_str = self.ioc.get("FREERTOS.Tasks01", "")
        new_task = f"{name},{priority_val},{stack_size},{entry_function},Default,{parameters},Dynamic,NULL,NULL"

        if tasks_str:
            self.ioc.set("FREERTOS.Tasks01", f"{tasks_str};{new_task}")
        else:
            self.ioc.set("FREERTOS.Tasks01", new_task)

        # 更新 IPParameters
        self._append_ip_param("FREERTOS", "Tasks01")

        self._log(f"✅ 已添加 FreeRTOS 任务: {name} (优先级={priority}, 栈={stack_size})")

    def config_scope_siggen(self, adc_channel: int = 6, dac_channel: int = 1,
                            usart: str = "USART2", baudrate: int = 115200) -> None:
        """一键配置串口示波器 + 信号发生器

        Args:
            adc_channel: ADC 通道号 (示波器输入)
            dac_channel: DAC 通道号 (信号发生器输出)
            usart: 串口外设
            baudrate: 串口波特率
        """
        self._log("\n🔧 一键配置串口示波器 + 信号发生器")
        self._log("=" * 50)

        # 1. 配置 ADC (示波器)
        self.config_adc(
            adc="ADC1",
            channel=adc_channel,
            trigger="TIM9_TRGO",
            sampling=3,
            resolution=12,
            alignment="Right"
        )

        # 2. 配置 DAC (信号发生器)
        self.config_dac(
            dac="DAC",
            channel=dac_channel,
            trigger="TIM5_TRGO",
            buffer="enable"
        )

        # 3. 配置 USART (串口通信)
        self.config_usart(
            usart=usart,
            baudrate=baudrate,
            databits=8,
            stopbits=1,
            parity="None"
        )

        # 4. 配置 I2C1 (OLED 显示)
        self.config_i2c(
            i2c="I2C1",
            speed=400000,
            addressing=7
        )

        # 5. 配置定时器
        # TIM9: ADC 触发 (1kHz 采样率)
        self.config_tim(
            tim="TIM9",
            prescaler=84,
            period=1000,
            counter_mode="Up",
            trigger="TRGO"
        )

        # TIM5: DAC 触发 (500Hz 输出)
        self.config_tim(
            tim="TIM5",
            prescaler=84,
            period=2000,
            counter_mode="Up",
            trigger="TRGO"
        )

        # 6. 配置 NVIC 中断
        self.config_nvic("TIM5_IRQn", priority=6, enabled=True)
        self.config_nvic("TIM1_BRK_TIM9_IRQn", priority=6, enabled=True)
        self.config_nvic(f"{usart}_IRQn", priority=5, enabled=True)

        self._log("\n✅ 串口示波器 + 信号发生器配置完成！")


# ======================== CubeMX CLI ========================

def find_cubemx(cli_path: str | None = None) -> str | None:
    """查找 STM32CubeMX 可执行文件"""
    if cli_path and Path(cli_path).exists():
        return cli_path

    # 检查 PATH
    try:
        result = subprocess.run(
            ["where", "STM32CubeMX.exe"],
            capture_output=True, text=True, timeout=10
        )
        if result.returncode == 0:
            return result.stdout.strip().split("\n")[0].strip()
    except (FileNotFoundError, subprocess.TimeoutExpired):
        pass

    # 搜索默认路径
    for path in DEFAULT_CUBEMX_PATHS:
        if Path(path).exists():
            return path

    return None


def generate_code(ioc_path: str, toolchain: str = "MDK-ARM V5",
                   cubemx_path: str | None = None) -> bool:
    """调用 CubeMX CLI 生成代码"""
    cubemx = find_cubemx(cubemx_path)
    if not cubemx:
        print("❌ 未找到 STM32CubeMX，请安装或通过 --cubemx 指定路径")
        return False

    ioc_file = Path(ioc_path)
    if not ioc_file.exists():
        print(f"❌ .ioc 文件不存在: {ioc_path}")
        return False

    # 构建命令
    cmd = [cubemx, "-mx", str(ioc_file.resolve()), "-gen", toolchain]
    cmd_str = " ".join(cmd)
    print(f"🔧 CubeMX 命令: {cmd_str}")
    print(f"⏳ 正在生成代码...")

    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
    except subprocess.TimeoutExpired:
        print("❌ CubeMX 执行超时（120秒）")
        return False
    except FileNotFoundError:
        print(f"❌ 未找到 CubeMX: {cubemx}")
        return False

    if result.returncode == 0:
        print("✅ 代码生成成功")
        return True
    else:
        print(f"❌ 代码生成失败 (返回码: {result.returncode})")
        if result.stderr:
            print(f"   错误: {result.stderr[:200]}")
        return False


# ======================== 输出格式 ========================

def print_parse_result(data: dict[str, Any]) -> None:
    """打印解析结果"""
    print("\n📊 IOC 配置解析结果")
    print("=" * 50)

    # MCU 信息
    mcu = data["mcu"]
    print(f"\n🔧 MCU: {mcu['name']} ({mcu['package']})")
    print(f"   系列: {mcu['family']}")

    # 外设列表
    peripherals = data["peripherals"]
    print(f"\n📦 外设 ({len(peripherals)}):")
    for p in peripherals:
        print(f"   - {p}")

    # 引脚配置
    pins = data["pins"]
    print(f"\n📌 引脚 ({len(pins)}):")
    for pin in pins:
        line = f"   {pin['name']}"
        if "signal" in pin:
            line += f" -> {pin['signal']}"
        if "label" in pin:
            line += f" [{pin['label']}]"
        print(line)

    # 时钟配置
    clock = data["clock"]
    print(f"\n⏰ 时钟:")
    print(f"   HSE: {int(clock['hse']) // 1000000} MHz")
    print(f"   SYSCLK: {int(clock['sysclk']) // 1000000} MHz")
    print(f"   APB1: {int(clock['apb1']) // 1000000} MHz")
    print(f"   APB2: {int(clock['apb2']) // 1000000} MHz")

    # FreeRTOS 任务
    tasks = data["freertos_tasks"]
    if tasks:
        print(f"\n🔄 FreeRTOS 任务 ({len(tasks)}):")
        for task in tasks:
            print(f"   - {task['name']}: 优先级={task['priority']}, 栈={task['stack_size']}")


# ======================== CLI ========================

def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="STM32CubeMX 配置自动化工具",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  %(prog)s --parse project.ioc                              # 解析配置
  %(prog)s --create --mcu STM32F407VETx --output new.ioc    # 创建新配置
  %(prog)s --modify project.ioc --add-peripheral USART3     # 添加外设
  %(prog)s --modify project.ioc --set-clock --hse 8 --sysclk 168  # 配置时钟
  %(prog)s --modify project.ioc --add-task --name MyTask --stack 256  # 添加任务
  %(prog)s --generate project.ioc --toolchain "MDK-ARM V5"  # 生成代码
        """,
    )

    # 操作模式
    group = parser.add_argument_group("操作模式")
    group.add_argument("--parse", metavar="FILE", help="解析 .ioc 文件")
    group.add_argument("--create", action="store_true", help="创建新 .ioc 文件")
    group.add_argument("--modify", metavar="FILE", help="修改 .ioc 文件")
    group.add_argument("--generate", metavar="FILE", help="调用 CubeMX 生成代码")

    # 创建选项
    create_group = parser.add_argument_group("创建选项")
    create_group.add_argument("--mcu", help="MCU 型号 (如 STM32F407VETx)")
    create_group.add_argument("--output", help="输出文件路径")

    # 修改选项
    modify_group = parser.add_argument_group("修改选项")
    modify_group.add_argument("--add-peripheral", metavar="NAME", help="添加外设")
    modify_group.add_argument("--add-pin", nargs=3, metavar=("PIN", "SIGNAL", "MODE"),
                              help="添加引脚配置")
    modify_group.add_argument("--set-clock", action="store_true", help="配置时钟树")
    modify_group.add_argument("--hse", type=int, help="HSE 频率 (MHz)")
    modify_group.add_argument("--sysclk", type=int, help="SYSCLK 频率 (MHz)")
    modify_group.add_argument("--add-task", action="store_true", help="添加 FreeRTOS 任务")
    modify_group.add_argument("--name", help="任务名称")
    modify_group.add_argument("--stack", type=int, default=256, help="任务栈大小")
    modify_group.add_argument("--priority", default="Normal",
                              choices=["Idle", "Low", "Normal", "High", "Realtime"],
                              help="任务优先级")

    # 详细配置选项
    detail_group = parser.add_argument_group("详细配置选项")
    detail_group.add_argument("--config-adc", action="store_true", help="配置 ADC 详细参数")
    detail_group.add_argument("--adc", default="ADC1", help="ADC 外设名称")
    detail_group.add_argument("--channel", type=int, default=6, help="ADC 通道号 (0-15)")
    detail_group.add_argument("--trigger", default="TIM9_TRGO", help="触发源")
    detail_group.add_argument("--sampling", type=int, default=3, help="采样周期 (3/15/28/56/84/112/144/480)")
    detail_group.add_argument("--resolution", type=int, default=12, choices=[6, 8, 10, 12],
                              help="ADC 分辨率")

    detail_group.add_argument("--config-dac", action="store_true", help="配置 DAC 详细参数")
    detail_group.add_argument("--dac", default="DAC", help="DAC 外设名称")
    detail_group.add_argument("--dac-channel", type=int, default=1, choices=[1, 2],
                              help="DAC 通道号")
    detail_group.add_argument("--buffer", default="enable", choices=["enable", "disable"],
                              help="DAC 输出缓冲")

    detail_group.add_argument("--config-usart", action="store_true", help="配置 USART 详细参数")
    detail_group.add_argument("--usart", default="USART2", help="USART 外设名称")
    detail_group.add_argument("--baudrate", type=int, default=115200, help="波特率")
    detail_group.add_argument("--databits", type=int, default=8, choices=[8, 9],
                              help="数据位")
    detail_group.add_argument("--stopbits", type=float, default=1, choices=[1, 2],
                              help="停止位")
    detail_group.add_argument("--parity", default="None", choices=["None", "Even", "Odd"],
                              help="校验位")

    detail_group.add_argument("--config-i2c", action="store_true", help="配置 I2C 详细参数")
    detail_group.add_argument("--i2c", default="I2C1", help="I2C 外设名称")
    detail_group.add_argument("--speed", type=int, default=400000, help="I2C 速度")
    detail_group.add_argument("--addressing", type=int, default=7, choices=[7, 10],
                              help="地址模式")

    detail_group.add_argument("--config-tim", action="store_true", help="配置定时器详细参数")
    detail_group.add_argument("--tim", default="TIM9", help="定时器外设名称")
    detail_group.add_argument("--prescaler", type=int, default=84, help="预分频系数")
    detail_group.add_argument("--period", type=int, default=1000, help="周期/重装载值")
    detail_group.add_argument("--counter-mode", default="Up",
                              choices=["Up", "Down", "CenterAligned1", "CenterAligned2", "CenterAligned3"],
                              help="计数模式")
    detail_group.add_argument("--tim-trigger", default="TRGO",
                              choices=["TRGO", "OC1REF", "OC2REF"],
                              help="定时器触发输出")

    detail_group.add_argument("--config-nvic", action="store_true", help="配置 NVIC 中断")
    detail_group.add_argument("--irq", help="中断名称 (如 USART1_IRQn)")
    detail_group.add_argument("--nvic-priority", type=int, default=5, help="中断优先级")
    detail_group.add_argument("--nvic-enabled", action="store_true", default=True, help="启用中断")

    # DMA 配置
    detail_group.add_argument("--config-dma", action="store_true", help="配置 DMA 详细参数")
    detail_group.add_argument("--dma-stream", default="DMA2_Stream0", help="DMA 流名称")
    detail_group.add_argument("--dma-channel", type=int, default=0, help="DMA 通道号 (0-15)")
    detail_group.add_argument("--dma-direction", default="PeripheralToMemory",
                              choices=["PeripheralToMemory", "MemoryToPeripheral", "MemoryToMemory"],
                              help="DMA 传输方向")
    detail_group.add_argument("--dma-mode", default="Normal",
                              choices=["Normal", "Circular"],
                              help="DMA 模式")
    detail_group.add_argument("--dma-priority", default="Low",
                              choices=["Low", "Medium", "High", "VeryHigh"],
                              help="DMA 优先级")
    detail_group.add_argument("--dma-request", default="ADC1", help="DMA 关联外设请求")

    # SPI 配置
    detail_group.add_argument("--config-spi", action="store_true", help="配置 SPI 详细参数")
    detail_group.add_argument("--spi", default="SPI1", help="SPI 外设名称")
    detail_group.add_argument("--spi-mode", default="Master",
                              choices=["Master", "Slave"],
                              help="SPI 模式")
    detail_group.add_argument("--spi-direction", default="FullDuplex",
                              choices=["FullDuplex", "HalfDuplex", "ReceiveOnly", "TransmitOnly"],
                              help="SPI 方向")
    detail_group.add_argument("--spi-datasize", type=int, default=8, choices=[8, 16],
                              help="SPI 数据大小")
    detail_group.add_argument("--spi-cpol", default="Low",
                              choices=["Low", "High"],
                              help="SPI 时钟极性")
    detail_group.add_argument("--spi-cpha", default="Edge1",
                              choices=["Edge1", "Edge2"],
                              help="SPI 时钟相位")
    detail_group.add_argument("--spi-prescaler", type=int, default=2,
                              choices=[2, 4, 8, 16, 32, 64, 128, 256],
                              help="SPI 预分频系数")

    # RTC 配置
    detail_group.add_argument("--config-rtc", action="store_true", help="配置 RTC 详细参数")
    detail_group.add_argument("--rtc", default="RTC", help="RTC 外设名称")
    detail_group.add_argument("--rtc-clock", default="LSE",
                              choices=["LSE", "LSI", "HSE"],
                              help="RTC 时钟源")
    detail_group.add_argument("--rtc-format", default="24h",
                              choices=["24h", "12h"],
                              help="RTC 时间格式")
    detail_group.add_argument("--rtc-dateformat", default="DD/MM/YYYY",
                              choices=["DD/MM/YYYY", "MM/DD/YYYY", "YYYY/MM/DD"],
                              help="RTC 日期格式")

    # CAN 配置
    detail_group.add_argument("--config-can", action="store_true", help="配置 CAN 详细参数")
    detail_group.add_argument("--can", default="CAN1", help="CAN 外设名称")
    detail_group.add_argument("--can-mode", default="Normal",
                              choices=["Normal", "Loopback", "Silent", "SilentLoopback"],
                              help="CAN 模式")
    detail_group.add_argument("--can-baudrate", type=int, default=500000,
                              help="CAN 波特率")
    detail_group.add_argument("--can-sjw", type=int, default=1, help="CAN 同步跳转宽度")
    detail_group.add_argument("--can-bs1", type=int, default=6, help="CAN 位段 1")
    detail_group.add_argument("--can-bs2", type=int, default=8, help="CAN 位段 2")

    # GPIO 配置
    detail_group.add_argument("--config-gpio", action="store_true", help="配置 GPIO 详细参数")
    detail_group.add_argument("--gpio-pin", help="GPIO 引脚 (如 PA8)")
    detail_group.add_argument("--gpio-mode", default="Output",
                              choices=["Input", "Output", "AlternateFunction", "Analog"],
                              help="GPIO 模式")
    detail_group.add_argument("--gpio-speed", default="High",
                              choices=["Low", "Medium", "High", "VeryHigh"],
                              help="GPIO 速度")
    detail_group.add_argument("--gpio-pull", default="NoPull",
                              choices=["NoPull", "PullUp", "PullDown"],
                              help="GPIO 上下拉")
    detail_group.add_argument("--gpio-label", help="GPIO 引脚标签")
    detail_group.add_argument("--gpio-initial", type=int, default=0, choices=[0, 1],
                              help="GPIO 初始状态")

    # PWM 配置
    detail_group.add_argument("--config-pwm", action="store_true", help="配置 PWM 详细参数")
    detail_group.add_argument("--pwm-tim", default="TIM3", help="PWM 定时器外设")
    detail_group.add_argument("--pwm-channel", type=int, default=1, choices=[1, 2, 3, 4],
                              help="PWM 通道号")
    detail_group.add_argument("--pwm-prescaler", type=int, default=84, help="PWM 预分频系数")
    detail_group.add_argument("--pwm-period", type=int, default=20000, help="PWM 周期")
    detail_group.add_argument("--pwm-pulse", type=int, default=1500, help="PWM 初始脉宽")
    detail_group.add_argument("--pwm-polarity", default="High",
                              choices=["High", "Low"],
                              help="PWM 极性")

    # 编码器配置
    detail_group.add_argument("--config-encoder", action="store_true", help="配置编码器接口")
    detail_group.add_argument("--encoder-tim", default="TIM2", help="编码器定时器外设")
    detail_group.add_argument("--encoder-mode", default="TI12",
                              choices=["TI1", "TI2", "TI12"],
                              help="编码器模式")
    detail_group.add_argument("--encoder-period", type=int, default=65535, help="编码器周期")
    detail_group.add_argument("--encoder-polarity", default="Rising",
                              choices=["Rising", "Falling", "Both"],
                              help="编码器边沿极性")

    # 看门狗配置
    detail_group.add_argument("--config-watchdog", action="store_true", help="配置看门狗")
    detail_group.add_argument("--iwdg", default="IWDG", help="IWDG 外设名称")
    detail_group.add_argument("--iwdg-prescaler", type=int, default=64,
                              choices=[4, 8, 16, 32, 64, 128, 256],
                              help="IWDG 预分频系数")
    detail_group.add_argument("--iwdg-reload", type=int, default=625, help="IWDG 重装载值")
    detail_group.add_argument("--iwdg-window", type=int, default=0, help="IWDG 窗口值")

    # 系统配置
    detail_group.add_argument("--config-system", action="store_true", help="配置系统参数")
    detail_group.add_argument("--debug-interface", default="SerialWire",
                              choices=["SerialWire", "JTAG", "TraceAsSw", "TraceAsync", "Disable"],
                              help="调试接口")
    detail_group.add_argument("--sysclk-source", default="PLL",
                              choices=["HSI", "HSE", "PLL"],
                              help="系统时钟源")
    detail_group.add_argument("--voltage-scale", default="Scale1",
                              choices=["Scale1", "Scale2", "Scale3"],
                              help="电压调节")
    detail_group.add_argument("--prefetch", action="store_true", default=True, help="启用预取")

    # FMC 配置
    detail_group.add_argument("--config-fmc", action="store_true", help="配置 FMC 外部存储器")
    detail_group.add_argument("--fmc", default="FMC", help="FMC 外设名称")
    detail_group.add_argument("--fmc-memory-type", default="SRAM",
                              choices=["SRAM", "SDRAM", "NOR", "NAND"],
                              help="存储器类型")
    detail_group.add_argument("--fmc-data-width", type=int, default=16, choices=[8, 16, 32],
                              help="数据宽度")
    detail_group.add_argument("--fmc-address-width", type=int, default=20, choices=[8, 16, 20, 24],
                              help="地址宽度")
    detail_group.add_argument("--fmc-read-cycle", type=int, default=15, help="读周期 (ns)")
    detail_group.add_argument("--fmc-write-cycle", type=int, default=15, help="写周期 (ns)")

    # DCMI 配置
    detail_group.add_argument("--config-dcmi", action="store_true", help="配置 DCMI 摄像头接口")
    detail_group.add_argument("--dcmi", default="DCMI", help="DCMI 外设名称")
    detail_group.add_argument("--dcmi-capture-rate", default="AllFrame",
                              choices=["AllFrame", "HalfFrame"],
                              help="采集速率")
    detail_group.add_argument("--dcmi-synchro", default="Hardware",
                              choices=["Hardware", "Software"],
                              help="同步模式")
    detail_group.add_argument("--dcmi-pck-polarity", default="Rising",
                              choices=["Rising", "Falling"],
                              help="像素时钟极性")
    detail_group.add_argument("--dcmi-vs-polarity", default="High",
                              choices=["High", "Low"],
                              help="垂直同步极性")
    detail_group.add_argument("--dcmi-hs-polarity", default="High",
                              choices=["High", "Low"],
                              help="水平同步极性")

    # ETH 配置
    detail_group.add_argument("--config-eth", action="store_true", help="配置以太网")
    detail_group.add_argument("--eth", default="ETH", help="ETH 外设名称")
    detail_group.add_argument("--eth-mode", default="RMII",
                              choices=["MII", "RMII"],
                              help="接口模式")
    detail_group.add_argument("--eth-speed", type=int, default=100, choices=[10, 100],
                              help="速度 (Mbps)")
    detail_group.add_argument("--eth-duplex", default="Full",
                              choices=["Full", "Half"],
                              help="双工模式")
    detail_group.add_argument("--eth-mac", default="00:80:E1:00:00:00", help="MAC 地址")

    # USB 配置
    detail_group.add_argument("--config-usb-device", action="store_true", help="配置 USB 设备")
    detail_group.add_argument("--config-usb-host", action="store_true", help="配置 USB 主机")
    detail_group.add_argument("--usb", default="USB_OTG_FS", help="USB 外设名称")
    detail_group.add_argument("--usb-class", default="CDC",
                              choices=["CDC", "HID", "MSC", "DFU", "Custom"],
                              help="USB 设备类")
    detail_group.add_argument("--usb-speed", default="Full",
                              choices=["Full", "High"],
                              help="USB 速度")
    detail_group.add_argument("--usb-vbus", action="store_true", default=True, help="VBUS 检测")

    # 电源管理配置
    detail_group.add_argument("--config-power", action="store_true", help="配置电源管理")
    detail_group.add_argument("--power-mode", default="Run",
                              choices=["Run", "Sleep", "Stop", "Standby"],
                              help="运行模式")
    detail_group.add_argument("--pvd-enable", action="store_true", help="启用 PVD")
    detail_group.add_argument("--pvd-level", type=float, default=2.9, help="PVD 电压阈值 (2.0-2.9V)")

    # RTC 闹钟配置
    detail_group.add_argument("--config-rtc-alarm", action="store_true", help="配置 RTC 闹钟")
    detail_group.add_argument("--rtc-alarm", type=int, default=1, choices=[1, 2], help="闹钟编号")
    detail_group.add_argument("--rtc-alarm-mask", default="None",
                              choices=["None", "DateWeekDay", "Hours", "Minutes", "Seconds", "All"],
                              help="闹钟掩码")
    detail_group.add_argument("--rtc-wake-up", action="store_true", help="唤醒使能")

    # DMA 循环模式配置
    detail_group.add_argument("--config-dma-circular", action="store_true", help="配置 DMA 循环模式")
    detail_group.add_argument("--dma-buffer-size", type=int, default=1024, help="DMA 缓冲区大小")

    # FatFS 配置
    detail_group.add_argument("--config-fatfs", action="store_true", help="配置 FatFS 文件系统")
    detail_group.add_argument("--fatfs", default="FATFS", help="FATFS 外设名称")
    detail_group.add_argument("--fatfs-drive", default="SD",
                              choices=["SD", "USB", "RAM"],
                              help="驱动器类型")
    detail_group.add_argument("--fatfs-max-filename", type=int, default=255, help="最大文件名长度")
    detail_group.add_argument("--fatfs-code-page", type=int, default=437, help="代码页 (437=US, 936=GBK)")

    # LwIP 配置
    detail_group.add_argument("--config-lwip", action="store_true", help="配置 LwIP 网络协议栈")
    detail_group.add_argument("--lwip", default="LWIP", help="LWIP 外设名称")
    detail_group.add_argument("--lwip-dhcp", action="store_true", default=True, help="DHCP 使能")
    detail_group.add_argument("--lwip-ip", default="192.168.1.100", help="IP 地址")
    detail_group.add_argument("--lwip-netmask", default="255.255.255.0", help="子网掩码")
    detail_group.add_argument("--lwip-gateway", default="192.168.1.1", help="网关地址")

    # FreeRTOS 高级配置
    detail_group.add_argument("--config-freertos-heap", action="store_true", help="配置 FreeRTOS 堆")
    detail_group.add_argument("--freertos-heap-size", type=int, default=16384, help="堆大小 (字节)")
    detail_group.add_argument("--freertos-stack-check", type=int, default=2, choices=[0, 1, 2],
                              help="栈溢出检查级别")
    detail_group.add_argument("--freertos-trace", action="store_true", default=True, help="使用跟踪")
    detail_group.add_argument("--freertos-mutexes", action="store_true", default=True, help="使用互斥锁")

    # 一键配置
    detail_group.add_argument("--config-scope", action="store_true",
                              help="一键配置串口示波器 + 信号发生器")

    # 生成选项
    gen_group = parser.add_argument_group("生成选项")
    gen_group.add_argument("--toolchain", default="MDK-ARM V5", help="目标工具链")
    gen_group.add_argument("--cubemx", help="STM32CubeMX 路径")

    # 通用选项
    parser.add_argument("--json", action="store_true", help="输出 JSON 格式")

    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()

    # 解析模式
    if args.parse:
        ioc = IocParser()
        ioc.load(args.parse)
        data = ioc.to_dict()

        if args.json:
            print(json.dumps(data, indent=2, ensure_ascii=False))
        else:
            print_parse_result(data)
        return 0

    # 创建模式
    if args.create:
        if not args.mcu:
            print("❌ 创建模式需要指定 --mcu")
            return 1

        output = args.output or f"{args.mcu.lower()}.ioc"
        ioc = IocParser()

        # 基本 MCU 配置
        mcu_info = MCU_DATABASE.get(args.mcu, {
            "family": args.mcu[:7],
            "package": "Unknown",
        })

        ioc.set("Mcu.Family", mcu_info["family"])
        ioc.set("Mcu.UserName", args.mcu)
        ioc.set("Mcu.Name", args.mcu)
        ioc.set("Mcu.Package", mcu_info["package"])
        ioc.set("Mcu.IPNb", "0")
        ioc.set("Mcu.PinsNb", "0")
        ioc.set("Mcu.ThirdPartyNb", "0")
        ioc.set("MxCube.Version", "6.4.0")
        ioc.set("MxDb.Version", "DB.6.0.40")
        ioc.set("File.Version", "6")
        ioc.set("ProjectManager.DeviceId", args.mcu)
        ioc.set("ProjectManager.ProjectName", Path(output).stem)
        ioc.set("ProjectManager.TargetToolchain", "MDK-ARM V5")
        ioc.set("ProjectManager.KeepUserCode", "true")

        ioc.save(output)
        print(f"✅ 已创建配置文件: {output}")  # noqa: use print for CLI output
        return 0

    # 修改模式
    if args.modify:
        ioc = IocParser()
        ioc.load(args.modify)
        modifier = IocModifier(ioc)

        # 添加外设
        if args.add_peripheral:
            modifier.add_peripheral(args.add_peripheral)

        # 添加引脚
        if args.add_pin:
            pin, signal, mode = args.add_pin
            modifier.add_pin(pin, signal, mode)

        # 配置时钟
        if args.set_clock:
            modifier.set_clock(hse=args.hse, sysclk=args.sysclk)

        # 添加 FreeRTOS 任务
        if args.add_task:
            if not args.name:
                print("❌ 添加任务需要指定 --name")
                return 1
            modifier.add_freertos_task(args.name, args.stack, args.priority)

        # 详细配置 ADC
        if args.config_adc:
            modifier.config_adc(
                adc=args.adc,
                channel=args.channel,
                trigger=args.trigger,
                sampling=args.sampling,
                resolution=args.resolution
            )

        # 详细配置 DAC
        if args.config_dac:
            modifier.config_dac(
                dac=args.dac,
                channel=args.dac_channel,
                trigger=args.trigger,
                buffer=args.buffer
            )

        # 详细配置 USART
        if args.config_usart:
            modifier.config_usart(
                usart=args.usart,
                baudrate=args.baudrate,
                databits=args.databits,
                stopbits=args.stopbits,
                parity=args.parity
            )

        # 详细配置 I2C
        if args.config_i2c:
            modifier.config_i2c(
                i2c=args.i2c,
                speed=args.speed,
                addressing=args.addressing
            )

        # 详细配置定时器
        if args.config_tim:
            modifier.config_tim(
                tim=args.tim,
                prescaler=args.prescaler,
                period=args.period,
                counter_mode=args.counter_mode,
                trigger=args.tim_trigger
            )

        # 配置 NVIC
        if args.config_nvic:
            if not args.irq:
                print("❌ 配置 NVIC 需要指定 --irq")
                return 1
            modifier.config_nvic(
                irq=args.irq,
                priority=args.nvic_priority,
                enabled=args.nvic_enabled
            )

        # 一键配置串口示波器 + 信号发生器
        if args.config_scope:
            modifier.config_scope_siggen(
                adc_channel=args.channel,
                dac_channel=args.dac_channel,
                usart=args.usart,
                baudrate=args.baudrate
            )

        # 配置 DMA
        if args.config_dma:
            modifier.config_dma(
                dma_stream=args.dma_stream,
                channel=args.dma_channel,
                direction=args.dma_direction,
                mode=args.dma_mode,
                priority=args.dma_priority,
                request=args.dma_request
            )

        # 配置 SPI
        if args.config_spi:
            modifier.config_spi(
                spi=args.spi,
                mode=args.spi_mode,
                direction=args.spi_direction,
                datasize=args.spi_datasize,
                cpol=args.spi_cpol,
                cpha=args.spi_cpha,
                prescaler=args.spi_prescaler
            )

        # 配置 RTC
        if args.config_rtc:
            modifier.config_rtc(
                rtc=args.rtc,
                clock_source=args.rtc_clock,
                format=args.rtc_format,
                date_format=args.rtc_dateformat
            )

        # 配置 CAN
        if args.config_can:
            modifier.config_can(
                can=args.can,
                mode=args.can_mode,
                baudrate=args.can_baudrate,
                sjw=args.can_sjw,
                bs1=args.can_bs1,
                bs2=args.can_bs2
            )

        # 配置 GPIO
        if args.config_gpio:
            if not args.gpio_pin:
                print("❌ 配置 GPIO 需要指定 --gpio-pin")
                return 1
            modifier.config_gpio(
                pin=args.gpio_pin,
                mode=args.gpio_mode,
                speed=args.gpio_speed,
                pull=args.gpio_pull,
                label=args.gpio_label or "",
                initial_state=args.gpio_initial
            )

        # 配置 PWM
        if args.config_pwm:
            modifier.config_pwm(
                tim=args.pwm_tim,
                channel=args.pwm_channel,
                prescaler=args.pwm_prescaler,
                period=args.pwm_period,
                pulse=args.pwm_pulse,
                polarity=args.pwm_polarity
            )

        # 配置编码器
        if args.config_encoder:
            modifier.config_encoder(
                tim=args.encoder_tim,
                mode=args.encoder_mode,
                period=args.encoder_period,
                polarity=args.encoder_polarity
            )

        # 配置看门狗
        if args.config_watchdog:
            modifier.config_watchdog(
                iwdg=args.iwdg,
                prescaler=args.iwdg_prescaler,
                reload=args.iwdg_reload,
                window=args.iwdg_window
            )

        # 配置系统
        if args.config_system:
            modifier.config_system(
                debug=args.debug_interface,
                sysclk_source=args.sysclk_source,
                voltage_scale=args.voltage_scale,
                prefetch=args.prefetch
            )

        # 配置 FMC
        if args.config_fmc:
            modifier.config_fmc(
                fmc=args.fmc,
                memory_type=args.fmc_memory_type,
                data_width=args.fmc_data_width,
                address_width=args.fmc_address_width,
                read_cycle=args.fmc_read_cycle,
                write_cycle=args.fmc_write_cycle
            )

        # 配置 DCMI
        if args.config_dcmi:
            modifier.config_dcmi(
                dcmi=args.dcmi,
                capture_rate=args.dcmi_capture_rate,
                synchro_mode=args.dcmi_synchro,
                pck_polarity=args.dcmi_pck_polarity,
                vs_polarity=args.dcmi_vs_polarity,
                hs_polarity=args.dcmi_hs_polarity
            )

        # 配置 ETH
        if args.config_eth:
            modifier.config_eth(
                eth=args.eth,
                mode=args.eth_mode,
                speed=args.eth_speed,
                duplex=args.eth_duplex,
                mac_address=args.eth_mac
            )

        # 配置 USB 设备
        if args.config_usb_device:
            modifier.config_usb_device(
                usb=args.usb,
                class_type=args.usb_class,
                speed=args.usb_speed,
                vbus_sensing=args.usb_vbus
            )

        # 配置 USB 主机
        if args.config_usb_host:
            modifier.config_usb_host(
                usb=args.usb,
                speed=args.usb_speed,
                vbus_sensing=args.usb_vbus
            )

        # 配置电源管理
        if args.config_power:
            modifier.config_power(
                mode=args.power_mode,
                voltage_scale=args.voltage_scale,
                pvd_enabled=args.pvd_enable,
                pvd_level=args.pvd_level
            )

        # 配置 RTC 闹钟
        if args.config_rtc_alarm:
            modifier.config_rtc_alarm(
                rtc=args.rtc,
                alarm=args.rtc_alarm,
                mask=args.rtc_alarm_mask,
                wake_up=args.rtc_wake_up
            )

        # 配置 DMA 循环模式
        if args.config_dma_circular:
            modifier.config_dma_circular(
                dma_stream=args.dma_stream,
                channel=args.dma_channel,
                request=args.dma_request,
                buffer_size=args.dma_buffer_size
            )

        # 配置 FatFS
        if args.config_fatfs:
            modifier.config_fatfs(
                fatfs=args.fatfs,
                drive=args.fatfs_drive,
                max_filename=args.fatfs_max_filename,
                code_page=args.fatfs_code_page
            )

        # 配置 LwIP
        if args.config_lwip:
            modifier.config_lwip(
                lwip=args.lwip,
                dhcp=args.lwip_dhcp,
                ip_address=args.lwip_ip,
                subnet_mask=args.lwip_netmask,
                gateway=args.lwip_gateway
            )

        # 配置 FreeRTOS 堆
        if args.config_freertos_heap:
            modifier.config_freertos_heap(
                freertos="FREERTOS",
                heap_size=args.freertos_heap_size,
                stack_overflow_check=args.freertos_stack_check,
                use_trace=args.freertos_trace,
                use_mutexes=args.freertos_mutexes,
                use_recursive_mutexes=args.freertos_mutexes
            )

        # 保存修改
        ioc.save(args.modify)
        print(f"\n✅ 已保存到: {args.modify}")
        return 0

    # 生成模式
    if args.generate:
        success = generate_code(args.generate, args.toolchain, args.cubemx)
        return 0 if success else 1

    # 无参数时显示帮助
    parser.print_help()
    return 1


if __name__ == "__main__":
    sys.exit(main())
