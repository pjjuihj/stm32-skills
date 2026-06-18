#!/usr/bin/env python
"""CubeMX 配置逻辑验证脚本。

检查配置函数生成的值是否符合 CubeMX 格式规范。

使用示例：
  python test_logic_validation.py
  python test_logic_validation.py --verbose
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

# ======================== 逻辑验证 ========================

def validate_adc_config(verbose: bool = False) -> list[str]:
    """验证 ADC 配置逻辑"""
    issues = []

    with tempfile.NamedTemporaryFile(mode='w', suffix='.ioc', delete=False) as f:
        temp_file = f.name
        f.write("#MicroXplorer Configuration settings - do not modify\n")

    ioc = IocParser()
    ioc.load(temp_file)
    modifier = IocModifier(ioc)

    # 测试不同触发源
    triggers = ["TIM9_TRGO", "TIM2_TRGO", "SOFTWARE"]
    for trigger in triggers:
        modifier.config_adc(adc="ADC1", channel=0, trigger=trigger, sampling=3)
        expected = f"ADC_EXTERNALTRIGCONV_{trigger}"
        actual = ioc.get("ADC1.ExternalTrigConv")
        if actual != expected:
            issues.append(f"ADC 触发源格式错误: 期望 '{expected}', 实际 '{actual}'")

    # 测试不同采样时间
    sampling_tests = [
        (3, "ADC_SAMPLETIME_3CYCLES"),
        (15, "ADC_SAMPLETIME_15CYCLES"),
        (28, "ADC_SAMPLETIME_28CYCLES"),
        (56, "ADC_SAMPLETIME_56CYCLES"),
        (84, "ADC_SAMPLETIME_84CYCLES"),
        (112, "ADC_SAMPLETIME_112CYCLES"),
        (144, "ADC_SAMPLETIME_144CYCLES"),
        (480, "ADC_SAMPLETIME_480CYCLES"),
    ]
    for sampling, expected in sampling_tests:
        modifier.config_adc(adc="ADC1", channel=0, trigger="TIM9_TRGO", sampling=sampling)
        actual = ioc.get("ADC1.SamplingTime-ADC1_IN0")
        if actual != expected:
            issues.append(f"ADC 采样时间格式错误: 采样={sampling}, 期望 '{expected}', 实际 '{actual}'")

    # 测试不同分辨率
    resolution_tests = [
        (6, "ADC_RESOLUTION_6B"),
        (8, "ADC_RESOLUTION_8B"),
        (10, "ADC_RESOLUTION_10B"),
        (12, "ADC_RESOLUTION_12B"),
    ]
    for resolution, expected in resolution_tests:
        modifier.config_adc(adc="ADC1", channel=0, resolution=resolution)
        actual = ioc.get("ADC1.Resolution")
        if actual != expected:
            issues.append(f"ADC 分辨率格式错误: 分辨率={resolution}, 期望 '{expected}', 实际 '{actual}'")

    os.unlink(temp_file)

    if verbose:
        for issue in issues:
            print(f"  ❌ {issue}")

    return issues


def validate_dac_config(verbose: bool = False) -> list[str]:
    """验证 DAC 配置逻辑"""
    issues = []

    with tempfile.NamedTemporaryFile(mode='w', suffix='.ioc', delete=False) as f:
        temp_file = f.name
        f.write("#MicroXplorer Configuration settings - do not modify\n")

    ioc = IocParser()
    ioc.load(temp_file)
    modifier = IocModifier(ioc)

    # 测试不同触发源
    triggers = ["TIM5_TRGO", "TIM6_TRGO", "SOFTWARE"]
    for trigger in triggers:
        modifier.config_dac(dac="DAC", channel=1, trigger=trigger)
        expected = f"DAC_TRIGGER_{trigger}"
        actual = ioc.get("DAC.Trigger-DAC_OUT1")
        if actual != expected:
            issues.append(f"DAC 触发源格式错误: 期望 '{expected}', 实际 '{actual}'")

    # 测试不同通道
    for channel in [1, 2]:
        modifier.config_dac(dac="DAC", channel=channel, trigger="TIM5_TRGO")
        expected = f"DAC_CHANNEL_{channel}"
        actual = ioc.get(f"DAC.Channel-DAC_OUT{channel}")
        if actual != expected:
            issues.append(f"DAC 通道格式错误: 通道={channel}, 期望 '{expected}', 实际 '{actual}'")

    # 测试输出缓冲
    for buffer, expected in [("enable", "DAC_OUTPUTBUFFER_ENABLE"), ("disable", "DAC_OUTPUTBUFFER_DISABLE")]:
        modifier.config_dac(dac="DAC", channel=1, trigger="TIM5_TRGO", buffer=buffer)
        actual = ioc.get("DAC.OutputBuffer-DAC_OUT1")
        if actual != expected:
            issues.append(f"DAC 输出缓冲格式错误: 缓冲={buffer}, 期望 '{expected}', 实际 '{actual}'")

    os.unlink(temp_file)

    if verbose:
        for issue in issues:
            print(f"  ❌ {issue}")

    return issues


def validate_usart_config(verbose: bool = False) -> list[str]:
    """验证 USART 配置逻辑"""
    issues = []

    with tempfile.NamedTemporaryFile(mode='w', suffix='.ioc', delete=False) as f:
        temp_file = f.name
        f.write("#MicroXplorer Configuration settings - do not modify\n")

    ioc = IocParser()
    ioc.load(temp_file)
    modifier = IocModifier(ioc)

    # 测试波特率
    modifier.config_usart(usart="USART1", baudrate=9600)
    if ioc.get("USART1.BaudRate") != "9600":
        issues.append(f"USART 波特率配置失败")

    # 测试数据位
    for databits, expected in [(8, "UART_WORDLENGTH_8B"), (9, "UART_WORDLENGTH_9B")]:
        modifier.config_usart(usart="USART1", baudrate=115200, databits=databits)
        actual = ioc.get("USART1.WordLength")
        if actual != expected:
            issues.append(f"USART 数据位格式错误: 数据位={databits}, 期望 '{expected}', 实际 '{actual}'")

    # 测试停止位
    for stopbits, expected in [(1, "UART_STOPBITS_1"), (2, "UART_STOPBITS_2")]:
        modifier.config_usart(usart="USART1", baudrate=115200, stopbits=stopbits)
        actual = ioc.get("USART1.StopBits")
        if actual != expected:
            issues.append(f"USART 停止位格式错误: 停止位={stopbits}, 期望 '{expected}', 实际 '{actual}'")

    # 测试校验位
    for parity, expected in [("None", "UART_PARITY_NONE"), ("Even", "UART_PARITY_EVEN"), ("Odd", "UART_PARITY_ODD")]:
        modifier.config_usart(usart="USART1", baudrate=115200, parity=parity)
        actual = ioc.get("USART1.Parity")
        if actual != expected:
            issues.append(f"USART 校验位格式错误: 校验={parity}, 期望 '{expected}', 实际 '{actual}'")

    os.unlink(temp_file)

    if verbose:
        for issue in issues:
            print(f"  ❌ {issue}")

    return issues


def validate_i2c_config(verbose: bool = False) -> list[str]:
    """验证 I2C 配置逻辑"""
    issues = []

    with tempfile.NamedTemporaryFile(mode='w', suffix='.ioc', delete=False) as f:
        temp_file = f.name
        f.write("#MicroXplorer Configuration settings - do not modify\n")

    ioc = IocParser()
    ioc.load(temp_file)
    modifier = IocModifier(ioc)

    # 测试速度模式
    for speed, expected_mode in [(100000, "I2C_SPEEDMODE_STANDARD"), (400000, "I2C_SPEEDMODE_FAST")]:
        modifier.config_i2c(i2c="I2C1", speed=speed)
        actual = ioc.get("I2C1.SpeedMode")
        if actual != expected_mode:
            issues.append(f"I2C 速度模式错误: 速度={speed}, 期望 '{expected_mode}', 实际 '{actual}'")

    # 测试地址模式
    for addressing, expected in [(7, "I2C_ADDRESSINGMODE_7BIT"), (10, "I2C_ADDRESSINGMODE_10BIT")]:
        modifier.config_i2c(i2c="I2C1", speed=100000, addressing=addressing)
        actual = ioc.get("I2C1.AddressingMode")
        if actual != expected:
            issues.append(f"I2C 地址模式错误: 地址={addressing}, 期望 '{expected}', 实际 '{actual}'")

    os.unlink(temp_file)

    if verbose:
        for issue in issues:
            print(f"  ❌ {issue}")

    return issues


def validate_spi_config(verbose: bool = False) -> list[str]:
    """验证 SPI 配置逻辑"""
    issues = []

    with tempfile.NamedTemporaryFile(mode='w', suffix='.ioc', delete=False) as f:
        temp_file = f.name
        f.write("#MicroXplorer Configuration settings - do not modify\n")

    ioc = IocParser()
    ioc.load(temp_file)
    modifier = IocModifier(ioc)

    # 测试模式
    for mode, expected in [("Master", "SPI_MODE_MASTER"), ("Slave", "SPI_MODE_SLAVE")]:
        modifier.config_spi(spi="SPI1", mode=mode)
        actual = ioc.get("SPI1.Mode")
        if actual != expected:
            issues.append(f"SPI 模式错误: 模式={mode}, 期望 '{expected}', 实际 '{actual}'")

    # 测试方向（修复：HalfDuplex 应该是 SPI_DIRECTION_1LINE）
    for direction, expected in [
        ("FullDuplex", "SPI_DIRECTION_2LINES"),
        ("HalfDuplex", "SPI_DIRECTION_1LINE"),
        ("ReceiveOnly", "SPI_DIRECTION_2LINES_RXONLY"),
        ("TransmitOnly", "SPI_DIRECTION_1LINE"),
    ]:
        modifier.config_spi(spi="SPI1", mode="Master", direction=direction)
        actual = ioc.get("SPI1.Direction")
        if actual != expected:
            issues.append(f"SPI 方向错误: 方向={direction}, 期望 '{expected}', 实际 '{actual}'")

    # 测试数据大小
    for datasize, expected in [(8, "SPI_DATASIZE_8BIT"), (16, "SPI_DATASIZE_16BIT")]:
        modifier.config_spi(spi="SPI1", mode="Master", datasize=datasize)
        actual = ioc.get("SPI1.DataSize")
        if actual != expected:
            issues.append(f"SPI 数据大小错误: 大小={datasize}, 期望 '{expected}', 实际 '{actual}'")

    # 测试时钟极性
    for cpol, expected in [("Low", "SPI_POLARITY_LOW"), ("High", "SPI_POLARITY_HIGH")]:
        modifier.config_spi(spi="SPI1", mode="Master", cpol=cpol)
        actual = ioc.get("SPI1.CLKPolarity")
        if actual != expected:
            issues.append(f"SPI 时钟极性错误: 极性={cpol}, 期望 '{expected}', 实际 '{actual}'")

    # 测试时钟相位
    for cpha, expected in [("Edge1", "SPI_PHASE_1EDGE"), ("Edge2", "SPI_PHASE_2EDGE")]:
        modifier.config_spi(spi="SPI1", mode="Master", cpha=cpha)
        actual = ioc.get("SPI1.CLKPhase")
        if actual != expected:
            issues.append(f"SPI 时钟相位错误: 相位={cpha}, 期望 '{expected}', 实际 '{actual}'")

    os.unlink(temp_file)

    if verbose:
        for issue in issues:
            print(f"  ❌ {issue}")

    return issues


def validate_tim_config(verbose: bool = False) -> list[str]:
    """验证定时器配置逻辑"""
    issues = []

    with tempfile.NamedTemporaryFile(mode='w', suffix='.ioc', delete=False) as f:
        temp_file = f.name
        f.write("#MicroXplorer Configuration settings - do not modify\nRCC.SYSCLKFreq_VALUE=168000000\nRCC.APB1TimFreq_Value=84000000\nRCC.APB2TimFreq_Value=168000000\n")

    ioc = IocParser()
    ioc.load(temp_file)
    modifier = IocModifier(ioc)

    # 测试预分频格式
    modifier.config_tim(tim="TIM3", prescaler=84, period=1000)
    actual = ioc.get("TIM3.Prescaler")
    if actual != "84-1":
        issues.append(f"定时器预分频格式错误: 期望 '84-1', 实际 '{actual}'")

    # 测试周期格式
    actual = ioc.get("TIM3.Period")
    if actual != "1000-1":
        issues.append(f"定时器周期格式错误: 期望 '1000-1', 实际 '{actual}'")

    # 测试计数模式
    for mode, expected in [
        ("Up", "TIM_COUNTERMODE_UP"),
        ("Down", "TIM_COUNTERMODE_DOWN"),
    ]:
        modifier.config_tim(tim="TIM3", prescaler=84, period=1000, counter_mode=mode)
        actual = ioc.get("TIM3.CounterMode")
        if actual != expected:
            issues.append(f"定时器计数模式错误: 模式={mode}, 期望 '{expected}', 实际 '{actual}'")

    # 测试触发输出
    for trigger, expected in [
        ("TRGO", "TIM_TRGO_UPDATE"),
        ("OC1REF", "TIM_TRGO_OC1REF"),
        ("OC2REF", "TIM_TRGO_OC2REF"),
    ]:
        modifier.config_tim(tim="TIM3", prescaler=84, period=1000, trigger=trigger)
        actual = ioc.get("TIM3.TriggerOutput")
        if actual != expected:
            issues.append(f"定时器触发输出错误: 触发={trigger}, 期望 '{expected}', 实际 '{actual}'")

    os.unlink(temp_file)

    if verbose:
        for issue in issues:
            print(f"  ❌ {issue}")

    return issues


def validate_gpio_config(verbose: bool = False) -> list[str]:
    """验证 GPIO 配置逻辑"""
    issues = []

    with tempfile.NamedTemporaryFile(mode='w', suffix='.ioc', delete=False) as f:
        temp_file = f.name
        f.write("#MicroXplorer Configuration settings - do not modify\n")

    ioc = IocParser()
    ioc.load(temp_file)
    modifier = IocModifier(ioc)

    # 测试模式
    for mode, expected in [
        ("Input", "GPIO_MODE_INPUT"),
        ("Output", "GPIO_MODE_OUTPUT_PP"),
        ("AlternateFunction", "GPIO_MODE_AF_PP"),
        ("Analog", "GPIO_MODE_ANALOG"),
    ]:
        modifier.config_gpio(pin="PA0", mode=mode)
        actual = ioc.get("PA0.GPIO_Mode")
        if actual != expected:
            issues.append(f"GPIO 模式错误: 模式={mode}, 期望 '{expected}', 实际 '{actual}'")

    # 测试速度
    for speed, expected in [
        ("Low", "GPIO_SPEED_FREQ_LOW"),
        ("Medium", "GPIO_SPEED_FREQ_MEDIUM"),
        ("High", "GPIO_SPEED_FREQ_HIGH"),
        ("VeryHigh", "GPIO_SPEED_FREQ_VERY_HIGH"),
    ]:
        modifier.config_gpio(pin="PA0", mode="Output", speed=speed)
        actual = ioc.get("PA0.GPIO_Speed")
        if actual != expected:
            issues.append(f"GPIO 速度错误: 速度={speed}, 期望 '{expected}', 实际 '{actual}'")

    # 测试上下拉
    for pull, expected in [
        ("NoPull", "GPIO_NOPULL"),
        ("PullUp", "GPIO_PULLUP"),
        ("PullDown", "GPIO_PULLDOWN"),
    ]:
        modifier.config_gpio(pin="PA0", mode="Output", pull=pull)
        actual = ioc.get("PA0.GPIO_PuPd")
        if actual != expected:
            issues.append(f"GPIO 上下拉错误: 上下拉={pull}, 期望 '{expected}', 实际 '{actual}'")

    os.unlink(temp_file)

    if verbose:
        for issue in issues:
            print(f"  ❌ {issue}")

    return issues


def validate_nvic_config(verbose: bool = False) -> list[str]:
    """验证 NVIC 配置逻辑"""
    issues = []

    with tempfile.NamedTemporaryFile(mode='w', suffix='.ioc', delete=False) as f:
        temp_file = f.name
        f.write("#MicroXplorer Configuration settings - do not modify\n")

    ioc = IocParser()
    ioc.load(temp_file)
    modifier = IocModifier(ioc)

    # 测试中断配置格式
    modifier.config_nvic(irq="USART1_IRQn", priority=5, enabled=True)
    actual = ioc.get("NVIC.USART1_IRQn")

    # 格式应该是: true\:5\:0\:false\:false\:true\:true\:true\:true
    if "\\:5\\:" not in actual:
        issues.append(f"NVIC 优先级格式错误: 期望包含 '\\:5\\:', 实际 '{actual}'")

    if not actual.startswith("true"):
        issues.append(f"NVIC 使能格式错误: 期望以 'true' 开头, 实际 '{actual}'")

    os.unlink(temp_file)

    if verbose:
        for issue in issues:
            print(f"  ❌ {issue}")

    return issues


def validate_clock_config(verbose: bool = False) -> list[str]:
    """验证时钟配置逻辑"""
    issues = []

    with tempfile.NamedTemporaryFile(mode='w', suffix='.ioc', delete=False) as f:
        temp_file = f.name
        f.write("#MicroXplorer Configuration settings - do not modify\n")

    ioc = IocParser()
    ioc.load(temp_file)
    modifier = IocModifier(ioc)

    # 测试 HSE 配置（先设置 HSE，再设置 SYSCLK）
    modifier.set_clock(hse=8)
    actual = ioc.get("RCC.HSE_VALUE")
    if actual != "8000000":
        issues.append(f"HSE 配置错误: 期望 '8000000', 实际 '{actual}'")

    # 测试 SYSCLK 配置
    modifier.set_clock(sysclk=168)
    actual = ioc.get("RCC.SYSCLKFreq_VALUE")
    if actual != "168000000":
        issues.append(f"SYSCLK 配置错误: 期望 '168000000', 实际 '{actual}'")

    # 测试 PLL 配置
    pllm = ioc.get("RCC.PLLM")
    plln = ioc.get("RCC.PLLN")
    if pllm != "8":
        issues.append(f"PLLM 配置错误: 期望 '8', 实际 '{pllm}'")
    if plln != "336":
        issues.append(f"PLLN 配置错误: 期望 '336', 实际 '{plln}'")

    # 测试 APB 分频
    apb1_div = ioc.get("RCC.APB1CLKDivider")
    if apb1_div != "RCC_HCLK_DIV4":
        issues.append(f"APB1 分频错误: 期望 'RCC_HCLK_DIV4', 实际 '{apb1_div}'")

    apb2_div = ioc.get("RCC.APB2CLKDivider")
    if apb2_div != "RCC_HCLK_DIV2":
        issues.append(f"APB2 分频错误: 期望 'RCC_HCLK_DIV2', 实际 '{apb2_div}'")

    os.unlink(temp_file)

    if verbose:
        for issue in issues:
            print(f"  ❌ {issue}")

    return issues


def validate_pwm_config(verbose: bool = False) -> list[str]:
    """验证 PWM 配置逻辑"""
    issues = []

    with tempfile.NamedTemporaryFile(mode='w', suffix='.ioc', delete=False) as f:
        temp_file = f.name
        f.write("#MicroXplorer Configuration settings - do not modify\nRCC.SYSCLKFreq_VALUE=168000000\nRCC.APB1TimFreq_Value=84000000\nRCC.APB2TimFreq_Value=168000000\n")

    ioc = IocParser()
    ioc.load(temp_file)
    modifier = IocModifier(ioc)

    # 测试 PWM 通道配置
    modifier.config_pwm(tim="TIM3", channel=1, prescaler=84, period=20000, pulse=1500)
    actual = ioc.get("TIM3.Channel-PWM Generation1 CH1")
    if actual != "TIM_CHANNEL_1":
        issues.append(f"PWM 通道配置错误: 期望 'TIM_CHANNEL_1', 实际 '{actual}'")

    # 测试 PWM 脉宽配置
    actual = ioc.get("TIM3.Pulse-PWM Generation1 CH1")
    if actual != "1500":
        issues.append(f"PWM 脉宽配置错误: 期望 '1500', 实际 '{actual}'")

    os.unlink(temp_file)

    if verbose:
        for issue in issues:
            print(f"  ❌ {issue}")

    return issues


def validate_encoder_config(verbose: bool = False) -> list[str]:
    """验证编码器配置逻辑"""
    issues = []

    with tempfile.NamedTemporaryFile(mode='w', suffix='.ioc', delete=False) as f:
        temp_file = f.name
        f.write("#MicroXplorer Configuration settings - do not modify\n")

    ioc = IocParser()
    ioc.load(temp_file)
    modifier = IocModifier(ioc)

    # 测试编码器模式
    for mode, expected in [
        ("TI1", "TIM_ENCODERMODE_TI1"),
        ("TI2", "TIM_ENCODERMODE_TI2"),
        ("TI12", "TIM_ENCODERMODE_TI12"),
    ]:
        modifier.config_encoder(tim="TIM2", mode=mode)
        actual = ioc.get("TIM2.EncoderMode")
        if actual != expected:
            issues.append(f"编码器模式错误: 模式={mode}, 期望 '{expected}', 实际 '{actual}'")

    # 测试极性
    for polarity, expected in [
        ("Rising", "TIM_ICPOLARITY_RISING"),
        ("Falling", "TIM_ICPOLARITY_FALLING"),
        ("Both", "TIM_ICPOLARITY_BOTHEDGE"),
    ]:
        modifier.config_encoder(tim="TIM2", mode="TI12", polarity=polarity)
        actual = ioc.get("TIM2.IC1Polarity")
        if actual != expected:
            issues.append(f"编码器极性错误: 极性={polarity}, 期望 '{expected}', 实际 '{actual}'")

    os.unlink(temp_file)

    if verbose:
        for issue in issues:
            print(f"  ❌ {issue}")

    return issues


# ======================== 主函数 ========================

def main() -> int:
    parser = argparse.ArgumentParser(
        description="CubeMX 配置逻辑验证脚本",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )

    parser.add_argument("--verbose", "-v", action="store_true", help="详细输出")

    args = parser.parse_args()

    print("=" * 60)
    print("🔍 CubeMX 配置逻辑验证")
    print("=" * 60)
    print()

    # 运行所有验证
    validations = [
        ("ADC 配置", validate_adc_config),
        ("DAC 配置", validate_dac_config),
        ("USART 配置", validate_usart_config),
        ("I2C 配置", validate_i2c_config),
        ("SPI 配置", validate_spi_config),
        ("定时器配置", validate_tim_config),
        ("GPIO 配置", validate_gpio_config),
        ("NVIC 配置", validate_nvic_config),
        ("时钟配置", validate_clock_config),
        ("PWM 配置", validate_pwm_config),
        ("编码器配置", validate_encoder_config),
    ]

    total_issues = 0
    passed = 0
    failed = 0

    for name, validate_func in validations:
        print(f"🧪 验证 {name}...")
        issues = validate_func(verbose=args.verbose)
        if issues:
            failed += 1
            total_issues += len(issues)
            print(f"  ❌ 发现 {len(issues)} 个逻辑问题")
            if args.verbose:
                for issue in issues:
                    print(f"    - {issue}")
        else:
            passed += 1
            print(f"  ✅ 逻辑验证通过")
        print()

    # 输出结果
    print("=" * 60)
    print(f"📊 验证结果: {passed} 通过, {failed} 失败, 共 {total_issues} 个问题")
    print("=" * 60)

    if failed == 0:
        print("✅ 所有逻辑验证通过！")
        return 0
    else:
        print("❌ 发现逻辑问题！")
        return 1


if __name__ == "__main__":
    sys.exit(main())
