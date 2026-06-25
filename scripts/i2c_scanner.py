#!/usr/bin/env python
"""I2C 总线扫描工具。

通过串口命令扫描 I2C 总线上的设备地址。

用法:
  python i2c_scanner.py --port COM3                         # 扫描 I2C1（默认）
  python i2c_scanner.py --port COM3 --bus I2C2              # 扫描 I2C2
  python i2c_scanner.py --port COM3 --range 0x20 0x50       # 扫描指定范围
  python i2c_scanner.py --port COM3 --json                  # JSON 格式输出

MCU 端需要实现 I2C 扫描命令（固件中）:
  收到 "@I2C_SCAN" → 扫描 I2C 总线 → 返回 "I2C: 0x3C 0x68 0x76" 格式
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).parent
from shared import setup_encoding
setup_encoding()

try:
    import serial
except ImportError:
    print("❌ 需要安装 pyserial: pip install pyserial")
    sys.exit(1)


# 常见 I2C 设备地址表
KNOWN_DEVICES = {
    0x27: "PCF8574 (I2C GPIO)",
    0x3C: "SSD1306 (OLED 128x64)",
    0x3D: "SSD1306 (OLED alt)",
    0x48: "ADS1115 (ADC) / TMP102 (温度) / PCF8591",
    0x49: "ADS1115 (ADC alt) / TMP102 (alt)",
    0x50: "AT24C32 (EEPROM)",
    0x57: "AT24C32 (EEPROM alt)",
    0x60: "SI1145 (光传感器)",
    0x68: "DS3231 (RTC) / MPU6050 (IMU)",
    0x69: "MPU6050 (IMU alt)",
    0x76: "BME280 (温湿度气压) / BMP280",
    0x77: "BME280 (alt) / BMP180",
    0x23: "BH1750 (光照传感器)",
    0x5A: "MLX90614 (红外温度)",
    0x62: "SCD40 (CO2 传感器)",
    0x40: "INA219 (电流传感器) / HDC1080 (温湿度)",
    0x44: "SHT30 (温湿度)",
    0x5C: "AM2320 (温湿度)",
    0x1E: "HMC5883L (磁力计)",
    0x6B: "LSM9DS1 (IMU)",
    0x1D: "ADXL345 (加速度计)",
    0x53: "ADXL345 (alt)",
    0x29: "VL53L0X (激光测距)",
    0x39: "TSL2561 (光照)",
    0x41: "STMPE610 (触摸)",
    0x20: "MCP23017 (IO 扩展)",
    0x24: "MCP23017 (alt)",
}


def scan_i2c(port: str, bus: str = "I2C1", addr_range: tuple = (0x08, 0x77),
             timeout: float = 2.0) -> list[dict]:
    """通过串口扫描 I2C 总线。"""
    try:
        ser = serial.Serial(port, 115200, timeout=timeout)
        ser.reset_input_buffer()
    except serial.SerialException as e:
        print(f"❌ 串口打开失败: {e}")
        return []

    # 发送扫描命令
    cmd = f"@I2C_SCAN {bus}\r\n"
    ser.write(cmd.encode())
    ser.flush()

    # 接收响应
    response = ""
    import time
    start = time.time()
    while time.time() - start < timeout:
        if ser.in_waiting:
            chunk = ser.read(ser.in_waiting).decode("utf-8", errors="replace")
            response += chunk
            if "\n" in response:
                break
        time.sleep(0.05)
    ser.close()

    # 解析响应
    devices = []
    for line in response.strip().split("\n"):
        line = line.strip()
        if not line:
            continue
        # 解析 "I2C: 0x3C 0x68 0x76" 格式
        if "I2C:" in line or "i2c:" in line.lower():
            parts = line.split(":", 1)[-1].strip().split()
            for p in parts:
                try:
                    addr = int(p, 16)
                    if addr_range[0] <= addr <= addr_range[1]:
                        devices.append({
                            "address": addr,
                            "hex": f"0x{addr:02X}",
                            "name": KNOWN_DEVICES.get(addr, "未知设备"),
                        })
                except ValueError:
                    continue
        # 也支持 "FOUND: 0x3C" 格式
        elif "FOUND" in line.upper():
            parts = line.split(":")
            if len(parts) >= 2:
                try:
                    addr = int(parts[-1].strip(), 16)
                    devices.append({
                        "address": addr,
                        "hex": f"0x{addr:02X}",
                        "name": KNOWN_DEVICES.get(addr, "未知设备"),
                    })
                except ValueError:
                    continue

    return devices


def scan_i2c_offline(addr_range: tuple = (0x08, 0x77)) -> list[dict]:
    """离线模式：不连接串口，只显示地址范围和已知设备。"""
    devices = []
    for addr in range(addr_range[0], addr_range[1] + 1):
        if addr in KNOWN_DEVICES:
            devices.append({
                "address": addr,
                "hex": f"0x{addr:02X}",
                "name": KNOWN_DEVICES[addr],
            })
    return devices


def main():
    parser = argparse.ArgumentParser(description="I2C 总线扫描工具")
    parser.add_argument("--port", help="串口端口（如 COM3）")
    parser.add_argument("--bus", default="I2C1", help="I2C 总线（I2C1/I2C2）")
    parser.add_argument("--range", nargs=2, type=lambda x: int(x, 0),
                        default=[0x08, 0x77], help="地址范围（默认 0x08-0x77）")
    parser.add_argument("--timeout", type=float, default=3.0, help="响应超时（秒）")
    parser.add_argument("--offline", action="store_true", help="离线模式（只显示已知设备）")
    parser.add_argument("--json", action="store_true", help="JSON 格式输出")
    args = parser.parse_args()

    addr_range = (args.range[0], args.range[1])

    if args.offline:
        devices = scan_i2c_offline(addr_range)
        if args.json:
            print(json.dumps(devices, indent=2, ensure_ascii=False))
        else:
            print(f"📋 已知 I2C 设备地址表（0x{addr_range[0]:02X}-0x{addr_range[1]:02X}）:")
            for d in devices:
                print(f"  {d['hex']}  {d['name']}")
        return

    if not args.port:
        print("❌ 请指定 --port 或使用 --offline 模式")
        sys.exit(1)

    print(f"🔍 扫描 {args.bus} 总线（{args.port}）...")
    devices = scan_i2c(args.port, args.bus, addr_range, args.timeout)

    if args.json:
        print(json.dumps(devices, indent=2, ensure_ascii=False))
    else:
        if devices:
            print(f"\n✅ 发现 {len(devices)} 个设备:")
            for d in devices:
                print(f"  {d['hex']}  {d['name']}")
        else:
            print("\n⚠️ 未发现设备。检查:")
            print("  1. I2C 上拉电阻是否连接")
            print("  2. 设备是否上电")
            print("  3. 固件是否实现了 @I2C_SCAN 命令")
            print("  4. SDA/SCL 接线是否正确")


if __name__ == "__main__":
    main()
