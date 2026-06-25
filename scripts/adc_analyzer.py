#!/usr/bin/env python
"""STM32 ADC 噪声/纹波分析工具。

对 ADC 采样数据做统计分析：均值、标准差、ENOB、SNR。

用法:
  python adc_analyzer.py --auto . --data samples.bin           # 分析二进制采样数据
  python adc_analyzer.py --auto . --data samples.csv           # 分析 CSV 数据
  python adc_analyzer.py --auto . --port COM3 --duration 5     # 从串口采集分析
  python adc_analyzer.py --auto . --data samples.bin --fft     # FFT 频谱分析

功能:
  - 统计分析：均值、标准差、最大值、最小值、峰峰值
  - ENOB（有效位数）计算
  - SNR（信噪比）计算
  - SINAD（信噪失真比）计算
  - FFT 频谱分析（可选）
  - 噪声直方图
"""

from __future__ import annotations

import argparse
import json
import math
import os
import struct
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).parent
from shared import setup_encoding
setup_encoding()


def load_data_from_file(filepath: str) -> list[int]:
    """从文件加载 ADC 采样数据。"""
    if filepath.endswith(".bin"):
        with open(filepath, "rb") as f:
            data = f.read()
        # 假设 16-bit 无符号
        return list(struct.unpack(f"<{len(data)//2}H", data))
    elif filepath.endswith(".csv"):
        values = []
        with open(filepath, "r") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#"):
                    try:
                        values.append(int(line.split(",")[0]))
                    except ValueError:
                        continue
        return values
    else:
        return []


def load_data_from_serial(port: str, duration: float = 5.0,
                          baudrate: int = 115200) -> list[int]:
    """从串口采集 ADC 数据。"""
    try:
        import serial
        import time
    except ImportError:
        print("❌ 需要安装 pyserial: pip install pyserial")
        return []

    ser = serial.Serial(port, baudrate, timeout=1)
    ser.reset_input_buffer()

    # 发送采集命令
    ser.write(b"@ADC_DUMP\r\n")
    ser.flush()

    values = []
    start = time.time()
    while time.time() - start < duration:
        if ser.in_waiting:
            chunk = ser.read(ser.in_waiting).decode("utf-8", errors="replace")
            for line in chunk.strip().split("\n"):
                try:
                    values.append(int(line.strip()))
                except ValueError:
                    continue
        time.sleep(0.01)

    ser.close()
    return values


def calculate_statistics(data: list[int]) -> dict:
    """计算统计指标。"""
    if not data:
        return {}

    n = len(data)
    mean = sum(data) / n
    variance = sum((x - mean) ** 2 for x in data) / n
    std_dev = math.sqrt(variance)
    min_val = min(data)
    max_val = max(data)
    pp_val = max_val - min_val

    return {
        "count": n,
        "mean": mean,
        "std_dev": std_dev,
        "variance": variance,
        "min": min_val,
        "max": max_val,
        "pp": pp_val,
        "rms": math.sqrt(sum(x ** 2 for x in data) / n),
    }


def calculate_enob(std_dev: float, vref: float = 3.3, resolution: int = 12) -> float:
    """计算 ENOB（有效位数）。"""
    if std_dev <= 0:
        return resolution
    # ENOB = log2(Vref / (std_dev * sqrt(12)))
    # 对于量化噪声：ENOB = resolution - log2(noise_ratio)
    quantization_noise = vref / (2 ** resolution)
    total_noise = math.sqrt(std_dev ** 2 + quantization_noise ** 2)
    enob = math.log2(vref / (total_noise * math.sqrt(12)))
    return enob


def calculate_snr(std_dev: float, signal_amplitude: float) -> float:
    """计算 SNR（信噪比）。"""
    if std_dev <= 0:
        return float('inf')
    return 20 * math.log10(signal_amplitude / std_dev)


def calculate_sinad(data: list[int], fundamental_freq: float = None) -> float:
    """计算 SINAD（信噪失真比）。"""
    if not data:
        return 0.0

    mean = sum(data) / len(data)
    # 简化计算：SINAD ≈ SNR + 3dB（近似）
    std_dev = math.sqrt(sum((x - mean) ** 2 for x in data) / len(data))
    if std_dev <= 0:
        return float('inf')
    return 20 * math.log10(mean / std_dev) if mean > 0 else 0.0


def perform_fft(data: list[int], sample_rate: float = 100000) -> list[dict]:
    """执行 FFT 频谱分析。"""
    try:
        import numpy as np
    except ImportError:
        # 简化 FFT（不用 numpy）
        return perform_fft_simple(data, sample_rate)

    n = len(data)
    # 去直流
    mean = sum(data) / n
    centered = [x - mean for x in data]

    # FFT
    fft_result = np.fft.fft(centered)
    freqs = np.fft.fftfreq(n, 1.0 / sample_rate)
    magnitudes = np.abs(fft_result) / n

    # 只取正频率
    results = []
    for i in range(n // 2):
        results.append({
            "freq_hz": float(freqs[i]),
            "magnitude": float(magnitudes[i]),
            "magnitude_db": 20 * math.log10(magnitudes[i]) if magnitudes[i] > 0 else -100,
        })

    return results


def perform_fft_simple(data: list[int], sample_rate: float = 100000) -> list[dict]:
    """简化 FFT（不用 numpy）。"""
    n = len(data)
    mean = sum(data) / n
    centered = [x - mean for x in data]

    results = []
    for k in range(n // 2):
        real = sum(centered[i] * math.cos(2 * math.pi * k * i / n) for i in range(n)) / n
        imag = sum(centered[i] * math.sin(2 * math.pi * k * i / n) for i in range(n)) / n
        magnitude = math.sqrt(real ** 2 + imag ** 2)
        freq = k * sample_rate / n

        results.append({
            "freq_hz": freq,
            "magnitude": magnitude,
            "magnitude_db": 20 * math.log10(magnitude) if magnitude > 0 else -100,
        })

    return results


def analyze_adc(data: list[int], vref: float = 3.3,
                resolution: int = 12, sample_rate: float = 100000,
                do_fft: bool = False) -> dict:
    """分析 ADC 数据。"""
    stats = calculate_statistics(data)

    # 将 ADC 值转换为电压
    lsb = vref / (2 ** resolution)
    stats["voltage_mean"] = stats["mean"] * lsb
    stats["voltage_std"] = stats["std_dev"] * lsb
    stats["voltage_pp"] = stats["pp"] * lsb

    # ENOB
    enob = calculate_enob(stats["std_dev"], vref, resolution)
    stats["enob"] = enob
    stats["enob_bits_lost"] = resolution - enob

    # SNR
    signal_amplitude = stats["pp"] / 2  # 假设信号幅度为峰峰值的一半
    snr = calculate_snr(stats["std_dev"], signal_amplitude)
    stats["snr_db"] = snr

    # SINAD
    sinad = calculate_sinad(data)
    stats["sinad_db"] = sinad

    # FFT
    fft_result = []
    if do_fft and len(data) >= 64:
        fft_result = perform_fft(data, sample_rate)
        # 找到基波和主要谐波
        if fft_result:
            sorted_by_mag = sorted(fft_result, key=lambda x: x["magnitude"], reverse=True)
            stats["fundamental_freq"] = sorted_by_mag[0]["freq_hz"] if sorted_by_mag else 0
            stats["harmonics"] = sorted_by_mag[:5]

    return {
        "statistics": stats,
        "fft": fft_result[:100] if fft_result else [],  # 只返回前 100 个频率点
    }


def main():
    parser = argparse.ArgumentParser(description="STM32 ADC 噪声/纹波分析工具")
    parser.add_argument("--auto", metavar="DIR", default=".", help="项目目录")
    parser.add_argument("--data", help="采样数据文件（.bin 或 .csv）")
    parser.add_argument("--port", help="串口端口")
    parser.add_argument("--duration", type=float, default=5.0, help="串口采集时长（秒）")
    parser.add_argument("--vref", type=float, default=3.3, help="参考电压（V）")
    parser.add_argument("--resolution", type=int, default=12, help="ADC 分辨率（bit）")
    parser.add_argument("--sample-rate", type=float, default=100000, help="采样率（Hz）")
    parser.add_argument("--fft", action="store_true", help="执行 FFT 频谱分析")
    parser.add_argument("--json", action="store_true", help="JSON 格式输出")
    args = parser.parse_args()

    # 加载数据
    data = []
    if args.data:
        data = load_data_from_file(args.data)
    elif args.port:
        data = load_data_from_serial(args.port, args.duration)
    else:
        print("❌ 请指定 --data 或 --port")
        sys.exit(1)

    if not data:
        print("❌ 未获取到数据")
        sys.exit(1)

    # 分析
    result = analyze_adc(data, args.vref, args.resolution, args.sample_rate, args.fft)

    if args.json:
        print(json.dumps(result, indent=2, ensure_ascii=False))
    else:
        stats = result["statistics"]
        print(f"📊 ADC 噪声分析报告")
        print()
        print(f"采样点数: {stats['count']}")
        print(f"参考电压: {args.vref}V")
        print(f"分辨率: {args.resolution} bit")
        print()

        print(f"统计指标:")
        print(f"  均值:     {stats['mean']:.1f} ({stats['voltage_mean']:.4f} V)")
        print(f"  标准差:   {stats['std_dev']:.2f} ({stats['voltage_std']:.6f} V)")
        print(f"  最小值:   {stats['min']}")
        print(f"  最大值:   {stats['max']}")
        print(f"  峰峰值:   {stats['pp']} ({stats['voltage_pp']:.4f} V)")
        print(f"  RMS:      {stats['rms']:.1f}")
        print()

        print(f"质量指标:")
        print(f"  ENOB:     {stats['enob']:.1f} bit（丢失 {stats['enob_bits_lost']:.1f} bit）")
        print(f"  SNR:      {stats['snr_db']:.1f} dB")
        print(f"  SINAD:    {stats['sinad_db']:.1f} dB")
        print()

        # 质量评估
        if stats["enob"] >= args.resolution - 1:
            print(f"✅ ADC 质量优秀（ENOB 接近理论值）")
        elif stats["enob"] >= args.resolution - 2:
            print(f"⚠️ ADC 质量良好（ENOB 略低于理论值）")
        else:
            print(f"❌ ADC 噪声较大（ENOB 明显低于理论值）")
            print(f"   建议: 检查电源纹波、去耦电容、参考电压稳定性")

        # FFT 结果
        if result["fft"]:
            print()
            print(f"FFT 频谱分析:")
            sorted_by_mag = sorted(result["fft"], key=lambda x: x["magnitude"], reverse=True)
            for i, f in enumerate(sorted_by_mag[:5]):
                print(f"  {i+1}. {f['freq_hz']:.0f} Hz  {f['magnitude']:.1f}  {f['magnitude_db']:.1f} dB")


if __name__ == "__main__":
    main()
