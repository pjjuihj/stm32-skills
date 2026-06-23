#!/usr/bin/env python
"""CubeMX 配置模块测试脚本。

测试所有配置函数是否正常工作。

使用示例：
  python test_cubemx_config.py
  python test_cubemx_config.py --verbose
"""

from __future__ import annotations

import argparse
import io
import os
import sys
import tempfile
from pathlib import Path

# 编码处理
if sys.stdout and hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

# 添加父目录到路径
sys.path.insert(0, str(Path(__file__).parent))

from cubemx_config import IocParser, IocModifier

# ======================== 测试用例 ========================

def test_basic_config(verbose: bool = False) -> bool:
    """测试基础配置"""
    print("🧪 测试基础配置...")

    try:
        # 创建临时文件
        with tempfile.NamedTemporaryFile(mode='w', suffix='.ioc', delete=False) as f:
            temp_file = f.name
            f.write("#MicroXplorer Configuration settings - do not modify\n")

        # 测试解析器
        ioc = IocParser()
        ioc.load(temp_file)

        # 测试设置和获取
        ioc.set("Mcu.Family", "STM32F4")
        assert ioc.get("Mcu.Family") == "STM32F4", "设置/获取失败"

        # 测试保存
        ioc.save(temp_file)

        # 重新加载验证
        ioc2 = IocParser()
        ioc2.load(temp_file)
        assert ioc2.get("Mcu.Family") == "STM32F4", "保存/加载失败"

        os.unlink(temp_file)
        print("  ✅ 基础配置测试通过")
        return True

    except Exception as e:
        print(f"  ❌ 基础配置测试失败: {e}")
        if verbose:
            import traceback
            traceback.print_exc()
        return False


def test_peripheral_config(verbose: bool = False) -> bool:
    """测试外设配置"""
    print("🧪 测试外设配置...")

    try:
        with tempfile.NamedTemporaryFile(mode='w', suffix='.ioc', delete=False) as f:
            temp_file = f.name
            f.write("#MicroXplorer Configuration settings - do not modify\n")

        ioc = IocParser()
        ioc.load(temp_file)
        modifier = IocModifier(ioc)

        # 测试添加外设
        modifier.add_peripheral("USART1")
        assert "USART1" in ioc.get_peripherals(), "添加外设失败"

        # 测试配置 USART
        modifier.config_usart(
            usart="USART1",
            baudrate=115200,
            databits=8,
            stopbits=1,
            parity="None"
        )
        assert ioc.get("USART1.BaudRate") == "115200", "USART 配置失败"

        # 测试配置 I2C
        modifier.add_peripheral("I2C1")
        modifier.config_i2c(i2c="I2C1", speed=400000, addressing=7)
        assert ioc.get("I2C1.Speed") == "400000", "I2C 配置失败"

        # 测试配置 SPI
        modifier.add_peripheral("SPI1")
        modifier.config_spi(
            spi="SPI1",
            mode="Master",
            direction="FullDuplex",
            datasize=8,
            cpol="Low",
            cpha="Edge1",
            prescaler=2
        )
        assert ioc.get("SPI1.Mode") == "SPI_MODE_MASTER", "SPI 配置失败"

        os.unlink(temp_file)
        print("  ✅ 外设配置测试通过")
        return True

    except Exception as e:
        print(f"  ❌ 外设配置测试失败: {e}")
        if verbose:
            import traceback
            traceback.print_exc()
        return False


def test_timer_config(verbose: bool = False) -> bool:
    """测试定时器配置"""
    print("🧪 测试定时器配置...")

    try:
        with tempfile.NamedTemporaryFile(mode='w', suffix='.ioc', delete=False) as f:
            temp_file = f.name
            f.write("#MicroXplorer Configuration settings - do not modify\nRCC.SYSCLKFreq_VALUE=168000000\nRCC.APB1TimFreq_Value=84000000\nRCC.APB2TimFreq_Value=168000000\n")

        ioc = IocParser()
        ioc.load(temp_file)
        modifier = IocModifier(ioc)

        # 测试配置定时器
        modifier.add_peripheral("TIM3")
        modifier.config_tim(
            tim="TIM3",
            prescaler=84,
            period=1000,
            counter_mode="Up",
            trigger="TRGO"
        )
        assert ioc.get("TIM3.Prescaler") == "84-1", "定时器预分频配置失败"
        assert ioc.get("TIM3.Period") == "1000-1", "定时器周期配置失败"

        # 测试配置 PWM
        modifier.config_pwm(
            tim="TIM3",
            channel=1,
            prescaler=84,
            period=20000,
            pulse=1500,
            polarity="High"
        )
        assert "TIM_CHANNEL_1" in ioc.get("TIM3.Channel-PWM Generation1 CH1"), "PWM 通道配置失败"

        # 测试配置编码器
        modifier.add_peripheral("TIM2")
        modifier.config_encoder(
            tim="TIM2",
            mode="TI12",
            period=65535,
            polarity="Rising"
        )
        assert ioc.get("TIM2.EncoderMode") == "TIM_ENCODERMODE_TI12", "编码器配置失败"

        os.unlink(temp_file)
        print("  ✅ 定时器配置测试通过")
        return True

    except Exception as e:
        print(f"  ❌ 定时器配置测试失败: {e}")
        if verbose:
            import traceback
            traceback.print_exc()
        return False


def test_adc_dac_config(verbose: bool = False) -> bool:
    """测试 ADC/DAC 配置"""
    print("🧪 测试 ADC/DAC 配置...")

    try:
        with tempfile.NamedTemporaryFile(mode='w', suffix='.ioc', delete=False) as f:
            temp_file = f.name
            f.write("#MicroXplorer Configuration settings - do not modify\n")

        ioc = IocParser()
        ioc.load(temp_file)
        modifier = IocModifier(ioc)

        # 测试配置 ADC
        modifier.add_peripheral("ADC1")
        modifier.config_adc(
            adc="ADC1",
            channel=6,
            trigger="TIM9_TRGO",
            sampling=3,
            resolution=12,
            alignment="Right"
        )
        assert ioc.get("ADC1.Resolution") == "ADC_RESOLUTION_12B", "ADC 分辨率配置失败"
        assert ioc.get("ADC1.ScanConvMode") == "DISABLE", "ADC 扫描模式配置失败"

        # 测试配置 DAC
        modifier.add_peripheral("DAC")
        modifier.config_dac(
            dac="DAC",
            channel=1,
            trigger="TIM5_TRGO",
            buffer="enable"
        )
        assert "DAC_CHANNEL_1" in ioc.get("DAC.Channel-DAC_OUT1"), "DAC 通道配置失败"

        os.unlink(temp_file)
        print("  ✅ ADC/DAC 配置测试通过")
        return True

    except Exception as e:
        print(f"  ❌ ADC/DAC 配置测试失败: {e}")
        if verbose:
            import traceback
            traceback.print_exc()
        return False


def test_gpio_config(verbose: bool = False) -> bool:
    """测试 GPIO 配置"""
    print("🧪 测试 GPIO 配置...")

    try:
        with tempfile.NamedTemporaryFile(mode='w', suffix='.ioc', delete=False) as f:
            temp_file = f.name
            f.write("#MicroXplorer Configuration settings - do not modify\n")

        ioc = IocParser()
        ioc.load(temp_file)
        modifier = IocModifier(ioc)

        # 测试配置 GPIO
        modifier.config_gpio(
            pin="PA8",
            mode="Output",
            speed="High",
            pull="NoPull",
            label="LED",
            initial_state=0
        )
        assert ioc.get("PA8.Signal") == "GPIO_Output", "GPIO 信号配置失败"
        assert ioc.get("PA8.GPIO_Label") == "LED", "GPIO 标签配置失败"

        os.unlink(temp_file)
        print("  ✅ GPIO 配置测试通过")
        return True

    except Exception as e:
        print(f"  ❌ GPIO 配置测试失败: {e}")
        if verbose:
            import traceback
            traceback.print_exc()
        return False


def test_nvic_config(verbose: bool = False) -> bool:
    """测试 NVIC 配置"""
    print("🧪 测试 NVIC 配置...")

    try:
        with tempfile.NamedTemporaryFile(mode='w', suffix='.ioc', delete=False) as f:
            temp_file = f.name
            f.write("#MicroXplorer Configuration settings - do not modify\n")

        ioc = IocParser()
        ioc.load(temp_file)
        modifier = IocModifier(ioc)

        # 测试配置 NVIC
        modifier.config_nvic(
            irq="USART1_IRQn",
            priority=5,
            enabled=True
        )
        assert "USART1_IRQn" in ioc.get("NVIC.IPParameters"), "NVIC 配置失败"

        os.unlink(temp_file)
        print("  ✅ NVIC 配置测试通过")
        return True

    except Exception as e:
        print(f"  ❌ NVIC 配置测试失败: {e}")
        if verbose:
            import traceback
            traceback.print_exc()
        return False


def test_clock_config(verbose: bool = False) -> bool:
    """测试时钟配置"""
    print("🧪 测试时钟配置...")

    try:
        with tempfile.NamedTemporaryFile(mode='w', suffix='.ioc', delete=False) as f:
            temp_file = f.name
            f.write("#MicroXplorer Configuration settings - do not modify\nRCC.HSE_VALUE=8000000\n")

        ioc = IocParser()
        ioc.load(temp_file)
        modifier = IocModifier(ioc)

        # 测试配置时钟
        modifier.set_clock(hse=8, sysclk=168)
        assert ioc.get("RCC.HSE_VALUE") == "8000000", "HSE 配置失败"
        assert ioc.get("RCC.SYSCLKFreq_VALUE") == "168000000", "SYSCLK 配置失败"

        os.unlink(temp_file)
        print("  ✅ 时钟配置测试通过")
        return True

    except Exception as e:
        print(f"  ❌ 时钟配置测试失败: {e}")
        if verbose:
            import traceback
            traceback.print_exc()
        return False


def test_freertos_config(verbose: bool = False) -> bool:
    """测试 FreeRTOS 配置"""
    print("🧪 测试 FreeRTOS 配置...")

    try:
        with tempfile.NamedTemporaryFile(mode='w', suffix='.ioc', delete=False) as f:
            temp_file = f.name
            f.write("#MicroXplorer Configuration settings - do not modify\n")

        ioc = IocParser()
        ioc.load(temp_file)
        modifier = IocModifier(ioc)

        # 测试添加任务
        modifier.add_freertos_task(
            name="TestTask",
            stack_size=256,
            priority="Normal",
            entry_function="StartTestTask"
        )
        assert "TestTask" in ioc.get("FREERTOS.Tasks01"), "FreeRTOS 任务添加失败"

        os.unlink(temp_file)
        print("  ✅ FreeRTOS 配置测试通过")
        return True

    except Exception as e:
        print(f"  ❌ FreeRTOS 配置测试失败: {e}")
        if verbose:
            import traceback
            traceback.print_exc()
        return False


def test_dma_config(verbose: bool = False) -> bool:
    """测试 DMA 配置"""
    print("🧪 测试 DMA 配置...")

    try:
        with tempfile.NamedTemporaryFile(mode='w', suffix='.ioc', delete=False) as f:
            temp_file = f.name
            f.write("#MicroXplorer Configuration settings - do not modify\n")

        ioc = IocParser()
        ioc.load(temp_file)
        modifier = IocModifier(ioc)

        # 测试配置 DMA
        modifier.config_dma(
            dma_stream="DMA2_Stream0",
            channel=0,
            direction="PeripheralToMemory",
            mode="Circular",
            priority="High",
            request="ADC1"
        )
        assert ioc.get("DMA2_Stream0.Channel") == "DMA_CHANNEL_0", "DMA 通道配置失败"
        assert ioc.get("DMA2_Stream0.Mode") == "DMA_CIRCULAR", "DMA 模式配置失败"

        os.unlink(temp_file)
        print("  ✅ DMA 配置测试通过")
        return True

    except Exception as e:
        print(f"  ❌ DMA 配置测试失败: {e}")
        if verbose:
            import traceback
            traceback.print_exc()
        return False


def test_new_configs(verbose: bool = False) -> bool:
    """测试新增配置功能"""
    print("🧪 测试新增配置功能...")

    try:
        with tempfile.NamedTemporaryFile(mode='w', suffix='.ioc', delete=False) as f:
            temp_file = f.name
            f.write("#MicroXplorer Configuration settings - do not modify\n")

        ioc = IocParser()
        ioc.load(temp_file)
        modifier = IocModifier(ioc)

        # 测试 FMC 配置
        modifier.add_peripheral("FMC")
        modifier.config_fmc(
            fmc="FMC",
            memory_type="SRAM",
            data_width=16,
            address_width=20,
            read_cycle=15,
            write_cycle=15
        )
        assert ioc.get("FMC.MemoryType") == "FMC_MEMORY_TYPE_SRAM", "FMC 配置失败"

        # 测试 DCMI 配置
        modifier.add_peripheral("DCMI")
        modifier.config_dcmi(
            dcmi="DCMI",
            capture_rate="AllFrame",
            synchro_mode="Hardware",
            pck_polarity="Rising",
            vs_polarity="High",
            hs_polarity="High"
        )
        assert ioc.get("DCMI.CaptureRate") == "DCMI_CR_ALL_FRAME", "DCMI 配置失败"

        # 测试 ETH 配置
        modifier.add_peripheral("ETH")
        modifier.config_eth(
            eth="ETH",
            mode="RMII",
            speed=100,
            duplex="Full",
            mac_address="00:80:E1:00:00:00"
        )
        assert ioc.get("ETH.MediaInterface") == "ETH_MEDIA_IF_RMII", "ETH 配置失败"

        # 测试 USB 设备配置
        modifier.add_peripheral("USB_OTG_FS")
        modifier.config_usb_device(
            usb="USB_OTG_FS",
            class_type="CDC",
            speed="Full",
            vbus_sensing=True
        )
        assert ioc.get("USB_OTG_FS.Mode") == "DEVICE_VBUS", "USB 设备配置失败"

        # 测试电源管理配置
        modifier.config_power(
            mode="Run",
            voltage_scale="Scale1",
            pvd_enabled=False,
            pvd_level=2.9
        )
        assert ioc.get("PWR.LowPowerMode") == "PWR_LOWPOWERMODE_DISABLE", "电源配置失败"

        # 测试 RTC 闹钟配置
        modifier.add_peripheral("RTC")
        modifier.config_rtc_alarm(
            rtc="RTC",
            alarm=1,
            mask="None",
            wake_up=False
        )

        # 测试 FatFS 配置
        modifier.add_peripheral("FATFS")
        modifier.config_fatfs(
            fatfs="FATFS",
            drive="SD",
            max_filename=255,
            code_page=437
        )
        assert ioc.get("FATFS.Drive") == "FATFS_DRIVE_SD", "FatFS 配置失败"

        # 测试 LwIP 配置
        modifier.add_peripheral("LWIP")
        modifier.config_lwip(
            lwip="LWIP",
            dhcp=True,
            ip_address="192.168.1.100",
            subnet_mask="255.255.255.0",
            gateway="192.168.1.1"
        )
        assert ioc.get("LWIP.DHCP") == "ENABLE", "LwIP 配置失败"

        # 测试 FreeRTOS 堆配置
        modifier.add_peripheral("FREERTOS")
        modifier.config_freertos_heap(
            freertos="FREERTOS",
            heap_size=16384,
            stack_overflow_check=2,
            use_trace=True,
            use_mutexes=True,
            use_recursive_mutexes=True
        )
        assert ioc.get("FREERTOS.configTOTAL_HEAP_SIZE") == "16384", "FreeRTOS 堆配置失败"

        os.unlink(temp_file)
        print("  ✅ 新增配置功能测试通过")
        return True

    except Exception as e:
        print(f"  ❌ 新增配置功能测试失败: {e}")
        if verbose:
            import traceback
            traceback.print_exc()
        return False


# ======================== 主函数 ========================

def main() -> int:
    parser = argparse.ArgumentParser(
        description="CubeMX 配置模块测试脚本",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )

    parser.add_argument("--verbose", "-v", action="store_true", help="详细输出")

    args = parser.parse_args()

    print("=" * 60)
    print("🧪 CubeMX 配置模块测试")
    print("=" * 60)
    print()

    # 运行所有测试
    tests = [
        test_basic_config,
        test_peripheral_config,
        test_timer_config,
        test_adc_dac_config,
        test_gpio_config,
        test_nvic_config,
        test_clock_config,
        test_freertos_config,
        test_dma_config,
        test_new_configs,
    ]

    passed = 0
    failed = 0

    for test in tests:
        if test(verbose=args.verbose):
            passed += 1
        else:
            failed += 1
        print()

    # 输出结果
    print("=" * 60)
    print(f"📊 测试结果: {passed} 通过, {failed} 失败, 共 {passed + failed} 个测试")
    print("=" * 60)

    if failed == 0:
        print("✅ 所有测试通过！")
        return 0
    else:
        print("❌ 部分测试失败！")
        return 1


if __name__ == "__main__":
    sys.exit(main())
