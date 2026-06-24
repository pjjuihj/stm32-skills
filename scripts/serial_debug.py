#!/usr/bin/env python
"""STM32 串口调试助手 — 专为 AI 辅助调试设计。

支持三种协议：
  text  - 文本命令（@LED_ON\\r\\n）
  hex   - HEX 数据包（FF 01 02 03 04 FE）
  printf - 被动监听 printf 输出

用法:
  # 文本命令
  python serial_debug.py --port COM3 --proto text --send "@LED_ON"
  python serial_debug.py --port COM3 --proto text --send "@LED_OFF"

  # HEX 数据包
  python serial_debug.py --port COM3 --proto hex --send "01 02 03 04"
  python serial_debug.py --port COM3 --proto hex --send "01 02 03 04" --recv-timeout 2

  # printf 监听
  python serial_debug.py --port COM3 --proto printf --listen 10
  python serial_debug.py --port COM3 --proto printf --listen 10 --filter "temp"

  # 交互模式（支持所有协议切换）
  python serial_debug.py --port COM3 --mode interactive

  # 批量命令
  python serial_debug.py --port COM3 --proto text --batch commands.txt

  # 自动模式（读取项目配置）
  python serial_debug.py --auto . --proto text --send "@LED_ON"

  # 工作流集成（读取 workflow_result.json）
  python serial_debug.py --workflow workflow_result.json --proto printf --listen 30

安全约束:
  - 默认不自动重连
  - 发送前不自动清空缓冲区
  - 所有操作都有超时保护
"""

from __future__ import annotations

import argparse
import json
import re
import struct
import sys
import threading
import time
from datetime import datetime
from pathlib import Path

# 使用共享模块
try:
    from shared import setup_encoding, read_json_file
except ImportError:
    def setup_encoding():
        if sys.stdout and hasattr(sys.stdout, "reconfigure"):
            try:
                sys.stdout.reconfigure(encoding="utf-8", errors="replace")
            except Exception:
                pass
        if sys.stderr and hasattr(sys.stderr, "reconfigure"):
            try:
                sys.stderr.reconfigure(encoding="utf-8", errors="replace")
            except Exception:
                pass

    def read_json_file(file_path):
        try:
            return json.loads(Path(file_path).read_text(encoding="utf-8"))
        except:
            return None

try:
    import serial
    import serial.tools.list_ports
except ImportError:
    print("错误: 需要安装 pyserial。运行: pip install pyserial", file=sys.stderr)
    sys.exit(1)


# === 协议常量 ===

HEX_HEADER = 0xFF
HEX_TAIL = 0xFE
HEX_DATA_LEN = 4  # 默认数据长度


# === 项目配置读取 ===

def load_project_config(project_dir: str) -> dict:
    """加载项目配置。"""
    config = {}

    # 尝试从 workflow_result.json 读取
    workflow_file = Path(project_dir) / "workflow_result.json"
    if workflow_file.exists():
        workflow_data = read_json_file(str(workflow_file))
        if workflow_data:
            config["workflow"] = workflow_data
            config["device"] = workflow_data.get("device", "")
            config["project_dir"] = workflow_data.get("project_dir", project_dir)

    # 尝试从 detect_config.py 读取
    try:
        import subprocess
        detect_script = Path(__file__).parent / "detect_config.py"
        if detect_script.exists():
            proc = subprocess.run(
                [sys.executable, str(detect_script), "--scan", project_dir],
                capture_output=True, text=True, timeout=10,
            )
            if proc.returncode == 0:
                detect_data = json.loads(proc.stdout)
                if "error" not in detect_data:
                    config["detect"] = detect_data
                    config["device"] = detect_data.get("device", config.get("device", ""))
    except Exception:
        pass

    return config


def get_serial_config_from_project(config: dict) -> dict:
    """从项目配置中提取串口配置。"""
    serial_config = {
        "baud": 115200,
        "protocol": "text",
    }

    # 从 workflow 结果中提取
    if "workflow" in config:
        workflow = config["workflow"]
        steps = workflow.get("steps", {})
        if "serial" in steps:
            serial_data = steps["serial"]
            if "baud" in serial_data:
                serial_config["baud"] = serial_data["baud"]
            if "protocol" in serial_data:
                serial_config["protocol"] = serial_data["protocol"]

    # 从 detect 结果中提取
    if "detect" in config:
        detect = config["detect"]
        # 检查 USART 配置
        if "peripherals" in detect:
            for periph in detect["peripherals"]:
                if "USART" in periph.get("name", ""):
                    if "baudrate" in periph:
                        serial_config["baud"] = int(periph["baudrate"])

    return serial_config


def detect_protocol(data: bytes) -> str:
    """自动检测数据协议。

    Args:
        data: 接收到的数据

    Returns:
        协议类型: "text", "hex", "vofa-firewater", "vofa-justfloat", "unknown"
    """
    if not data:
        return "unknown"

    # 检查是否为文本
    try:
        text = data.decode("utf-8", errors="strict")
        # 检查是否为 VOFA+ FireWater 格式（逗号分隔的浮点数）
        if "," in text:
            parts = text.strip().split(",")
            try:
                [float(p) for p in parts]
                return "vofa-firewater"
            except ValueError:
                pass
        # 检查是否为普通文本
        if any(c.isalpha() or c in "@#$%+=" for c in text):
            return "text"
    except UnicodeDecodeError:
        pass

    # 检查是否为 VOFA+ JustFloat 格式（帧尾 0x00 0x00 0x80 0x7F）
    if data.endswith(b"\x00\x00\x80\x7f"):
        return "vofa-justfloat"

    # 检查是否为 HEX 包格式（帧头 0xFF，帧尾 0xFE）
    if data[0] == 0xFF and data[-1] == 0xFE:
        return "hex"

    return "hex"


def auto_detect_baud(port: str, timeout: float = 2.0) -> int:
    """自动检测波特率。

    Args:
        port: 串口号
        timeout: 超时时间

    Returns:
        检测到的波特率，失败返回 0
    """
    common_bauds = [115200, 9600, 19200, 38400, 57600, 230400, 460800, 921600]

    for baud in common_bauds:
        try:
            ser = serial.Serial(port=port, baudrate=baud, timeout=0.5)
            # 等待数据
            start = time.time()
            data = bytearray()
            while time.time() - start < timeout:
                chunk = ser.read(1)
                if chunk:
                    data.extend(chunk)
                    # 收到足够数据就返回
                    if len(data) >= 10:
                        ser.close()
                        return baud
            ser.close()
        except Exception:
            continue

    return 0


# === 工具函数 ===

def list_ports() -> list[dict]:
    """列出可用串口。"""
    ports = []
    for p in serial.tools.list_ports.comports():
        ports.append({"port": p.device, "description": p.description, "hwid": p.hwid})
    return ports


def parse_hex_string(hex_str: str) -> bytes:
    """解析十六进制字符串为字节。

    支持格式: "FF 01 02 03" 或 "FF010203" 或 "ff,01,02,03"
    """
    # 清理：去掉逗号、0x 前缀
    hex_str = hex_str.replace(",", " ").replace("0x", "").replace("0X", "")
    # 去掉多余空格
    hex_str = " ".join(hex_str.split())
    try:
        return bytes.fromhex(hex_str)
    except ValueError as e:
        raise ValueError(f"无效的十六进制: '{hex_str}' - {e}")


def hex_display(data: bytes) -> str:
    """格式化显示字节数据。"""
    hex_part = " ".join(f"{b:02X}" for b in data)
    ascii_part = "".join(chr(b) if 32 <= b < 127 else "." for b in data)
    return f"{hex_part}  |{ascii_part}|"


def ts_str(start: float) -> str:
    """生成时间戳字符串。"""
    return f"[{time.time() - start:8.3f}]"


# === 协议发送 ===

def send_text(ser: serial.Serial, cmd: str):
    """发送文本命令（自动附加 \\r\\n）。"""
    if not cmd.endswith("\r\n"):
        cmd += "\r\n"
    ser.write(cmd.encode("utf-8"))
    ser.flush()


def send_hex_packet(ser: serial.Serial, data: bytes):
    """发送 HEX 数据包（自动加帧头帧尾）。

    格式: [0xFF] [data...] [0xFE]
    """
    packet = bytes([HEX_HEADER]) + data + bytes([HEX_TAIL])
    ser.write(packet)
    ser.flush()


def send_raw_hex(ser: serial.Serial, data: bytes):
    """发送原始 HEX 字节（不加帧头帧尾）。"""
    ser.write(data)
    ser.flush()


# === 协议接收 ===

def recv_text(ser: serial.Serial, timeout: float = 2.0) -> list[str]:
    """接收文本行（直到超时）。"""
    lines = []
    ser.timeout = timeout
    while True:
        line = ser.readline()
        if not line:
            break
        try:
            text = line.decode("utf-8", errors="replace").strip()
        except Exception:
            text = line.hex()
        if text:
            lines.append(text)
    return lines


def recv_hex_packets(ser: serial.Serial, timeout: float = 2.0, max_packets: int = 10) -> list[dict]:
    """接收 HEX 数据包（解析帧头帧尾）。

    格式: [0xFF] [data...] [0xFE]
    """
    packets = []
    ser.timeout = 0.1  # 短超时，逐字节读取
    start = time.time()
    buf = bytearray()

    while time.time() - start < timeout and len(packets) < max_packets:
        data = ser.read(1)
        if not data:
            continue
        buf.append(data[0])

        # 查找完整包
        while len(buf) >= 6:  # 最小包: header + 4 data + tail
            # 查找帧头
            try:
                hdr_idx = buf.index(HEX_HEADER)
            except ValueError:
                buf.clear()
                break

            if hdr_idx > 0:
                buf = buf[hdr_idx:]  # 丢弃帧头前的数据

            # 查找帧尾
            try:
                tail_idx = buf.index(HEX_TAIL, 1)
            except ValueError:
                # 帧尾还没收到，继续等
                if len(buf) > 20:  # 包太长，可能是噪声
                    buf.pop(0)
                break

            # 提取数据
            payload = bytes(buf[1:tail_idx])
            packets.append({
                "raw": bytes(buf[:tail_idx + 1]).hex(" "),
                "data": payload.hex(" "),
                "data_len": len(payload),
            })
            buf = buf[tail_idx + 1:]

    return packets


def recv_printf(ser: serial.Serial, duration: float = 10.0, keyword: str | None = None) -> list[dict]:
    """监听 printf 输出（文本行模式）。"""
    entries = []
    ser.timeout = 0.1
    start = time.time()
    line_buf = bytearray()

    while time.time() - start < duration:
        data = ser.read(1)
        if not data:
            if line_buf:
                # 超时，输出缓冲区内容
                try:
                    text = bytes(line_buf).decode("utf-8", errors="replace").strip()
                except Exception:
                    text = bytes(line_buf).hex()
                if text:
                    if not keyword or keyword.lower() in text.lower():
                        ts = time.time() - start
                        entry = {"timestamp": round(ts, 3), "text": text}
                        entries.append(entry)
                        print(f"[{ts:8.3f}] {text}")
                line_buf.clear()
            continue

        for b in data:
            if b == ord("\n"):
                try:
                    text = bytes(line_buf).decode("utf-8", errors="replace").strip()
                except Exception:
                    text = bytes(line_buf).hex()
                if text:
                    if not keyword or keyword.lower() in text.lower():
                        ts = time.time() - start
                        entry = {"timestamp": round(ts, 3), "text": text}
                        entries.append(entry)
                        print(f"[{ts:8.3f}] {text}")
                line_buf.clear()
            elif b == ord("\r"):
                pass  # 忽略 \r
            else:
                line_buf.append(b)

    return entries


# === 调试命令 ===

def debug_send_recv(ser: serial.Serial, proto: str, send_data: str,
                    recv_timeout: float = 2.0) -> dict:
    """发送命令并接收响应。

    Args:
        ser: 串口对象
        proto: 协议类型 (text/hex/printf)
        send_data: 发送的数据
        recv_timeout: 接收超时

    Returns:
        {"sent": ..., "received": ...}
    """
    start = time.time()
    result = {"protocol": proto, "sent": send_data, "received": []}

    if proto == "text":
        send_text(ser, send_data)
        print(f"[TX] {send_data}")
        lines = recv_text(ser, recv_timeout)
        result["received"] = lines
        for line in lines:
            print(f"[RX] {line}")

    elif proto == "hex":
        data = parse_hex_string(send_data)
        send_hex_packet(ser, data)
        print(f"[TX] {hex_display(bytes([HEX_HEADER]) + data + bytes([HEX_TAIL]))}")
        packets = recv_hex_packets(ser, recv_timeout)
        result["received"] = packets
        for pkt in packets:
            print(f"[RX] data={pkt['data']} len={pkt['data_len']}")

    elif proto == "printf":
        # printf 模式不发送，只监听
        print(f"监听 printf 输出 {recv_timeout}s...")
        entries = recv_printf(ser, recv_timeout)
        result["received"] = entries

    result["duration_ms"] = round((time.time() - start) * 1000)
    return result


def debug_batch(ser: serial.Serial, proto: str, batch_file: str,
                recv_timeout: float = 2.0, interval: float = 0.5) -> list[dict]:
    """批量执行命令。

    batch_file 格式（每行一个命令）:
      @LED_ON
      @LED_OFF
      01 02 03 04    （hex 模式下自动解析为 HEX 包）
    """
    lines = Path(batch_file).read_text(encoding="utf-8").splitlines()
    results = []

    for i, line in enumerate(lines):
        line = line.strip()
        if not line or line.startswith("#"):
            continue

        print(f"\n--- 命令 {i+1}: {line} ---")
        result = debug_send_recv(ser, proto, line, recv_timeout)
        results.append(result)

        if interval > 0:
            time.sleep(interval)

    return results


# === 数据分析功能 ===

def parse_values_from_text(text: str) -> list[float]:
    """从文本中提取数值。

    支持格式:
      "temp:25.5,humidity:60.2"
      "25.5,60.2,101.3"
      "ADC:2048"
    """
    values = []
    # 尝试提取所有数值
    import re
    # 匹配整数和浮点数
    pattern = r'-?\d+\.?\d*'
    matches = re.findall(pattern, text)
    for match in matches:
        try:
            values.append(float(match))
        except ValueError:
            continue
    return values


def analyze_data_range(values: list[float], min_val: float = None,
                       max_val: float = None) -> dict:
    """分析数据范围。

    Args:
        values: 数值列表
        min_val: 最小值阈值（可选）
        max_val: 最大值阈值（可选）

    Returns:
        分析结果
    """
    if not values:
        return {"error": "没有数据"}

    result = {
        "count": len(values),
        "min": min(values),
        "max": max(values),
        "mean": sum(values) / len(values),
        "range": max(values) - min(values),
        "out_of_range": [],
    }

    # 检查范围
    if min_val is not None or max_val is not None:
        for i, v in enumerate(values):
            if min_val is not None and v < min_val:
                result["out_of_range"].append({"index": i, "value": v, "reason": "低于最小值"})
            if max_val is not None and v > max_val:
                result["out_of_range"].append({"index": i, "value": v, "reason": "高于最大值"})

    return result


def analyze_data_jumps(values: list[float], threshold: float = None) -> dict:
    """分析数据跳变。

    Args:
        values: 数值列表
        threshold: 跳变阈值（可选，默认为平均值的 50%）

    Returns:
        分析结果
    """
    if len(values) < 2:
        return {"error": "数据不足，需要至少 2 个值"}

    # 计算差值
    diffs = [abs(values[i+1] - values[i]) for i in range(len(values)-1)]

    # 计算统计信息
    mean_diff = sum(diffs) / len(diffs)
    max_diff = max(diffs)

    # 自动计算阈值
    if threshold is None:
        threshold = mean_diff * 3  # 默认为平均差值的 3 倍

    # 查找跳变
    jumps = []
    for i, diff in enumerate(diffs):
        if diff > threshold:
            jumps.append({
                "index": i,
                "from": values[i],
                "to": values[i+1],
                "diff": diff,
                "threshold": threshold,
            })

    return {
        "count": len(values),
        "mean_diff": mean_diff,
        "max_diff": max_diff,
        "threshold": threshold,
        "jumps": jumps,
        "jump_count": len(jumps),
    }


def analyze_data_stability(values: list[float], window_size: int = 5) -> dict:
    """分析数据稳定性。

    Args:
        values: 数值列表
        window_size: 滑动窗口大小

    Returns:
        分析结果
    """
    if len(values) < window_size:
        return {"error": f"数据不足，需要至少 {window_size} 个值"}

    # 计算滑动窗口的标准差
    std_devs = []
    for i in range(len(values) - window_size + 1):
        window = values[i:i + window_size]
        mean = sum(window) / len(window)
        variance = sum((x - mean) ** 2 for x in window) / len(window)
        std_devs.append(variance ** 0.5)

    # 计算整体稳定性
    mean_std = sum(std_devs) / len(std_devs)
    max_std = max(std_devs)

    # 判断稳定性
    is_stable = max_std < mean_std * 2

    return {
        "count": len(values),
        "window_size": window_size,
        "mean_std": mean_std,
        "max_std": max_std,
        "is_stable": is_stable,
        "std_devs": std_devs[:10],  # 只返回前 10 个
    }


def analyze_data_continuity(values: list[float], expected_interval: float = None,
                            tolerance: float = 0.1) -> dict:
    """分析数据连续性。

    Args:
        values: 数值列表
        expected_interval: 预期间隔（可选）
        tolerance: 容差百分比（默认 10%）

    Returns:
        分析结果
    """
    if len(values) < 2:
        return {"error": "数据不足，需要至少 2 个值"}

    # 计算差值
    diffs = [values[i+1] - values[i] for i in range(len(values)-1)]

    # 计算统计信息
    mean_diff = sum(diffs) / len(diffs)
    std_diff = (sum((d - mean_diff)**2 for d in diffs) / len(diffs)) ** 0.5

    # 检查连续性
    discontinuities = []
    if expected_interval is not None:
        for i, diff in enumerate(diffs):
            if abs(diff - expected_interval) > expected_interval * tolerance:
                discontinuities.append({
                    "index": i,
                    "from": values[i],
                    "to": values[i+1],
                    "diff": diff,
                    "expected": expected_interval,
                    "deviation": abs(diff - expected_interval),
                })

    return {
        "count": len(values),
        "mean_diff": mean_diff,
        "std_diff": std_diff,
        "expected_interval": expected_interval,
        "discontinuities": discontinuities,
        "discontinuity_count": len(discontinuities),
    }


def analyze_data_statistics(values: list[float]) -> dict:
    """统计分析。

    Args:
        values: 数值列表

    Returns:
        统计结果
    """
    if not values:
        return {"error": "没有数据"}

    n = len(values)
    mean = sum(values) / n
    variance = sum((x - mean)**2 for x in values) / n
    std_dev = variance ** 0.5

    # 排序后计算中位数
    sorted_values = sorted(values)
    if n % 2 == 0:
        median = (sorted_values[n//2 - 1] + sorted_values[n//2]) / 2
    else:
        median = sorted_values[n//2]

    return {
        "count": n,
        "min": min(values),
        "max": max(values),
        "mean": mean,
        "median": median,
        "std_dev": std_dev,
        "variance": variance,
    }


def debug_analyze(ser: serial.Serial, duration: float = 10.0,
                  min_val: float = None, max_val: float = None,
                  jump_threshold: float = None,
                  expected_interval: float = None) -> dict:
    """数据分析模式：监听数据并分析范围、跳变、连续性。

    Args:
        ser: 串口对象
        duration: 监听时长（秒）
        min_val: 最小值阈值
        max_val: 最大值阈值
        jump_threshold: 跳变阈值
        expected_interval: 预期间隔

    Returns:
        分析结果
    """
    print(f"数据分析模式: 监听 {duration}s")
    print(f"  范围检查: [{min_val}, {max_val}]")
    print(f"  跳变阈值: {jump_threshold}")
    print(f"  预期间隔: {expected_interval}")
    print("-" * 60)

    values = []
    start = time.time()
    ser.timeout = 0.1
    line_buf = bytearray()

    while time.time() - start < duration:
        data = ser.read(1)
        if not data:
            if line_buf:
                try:
                    text = bytes(line_buf).decode("utf-8", errors="replace").strip()
                except Exception:
                    text = ""
                if text:
                    # 提取数值
                    new_values = parse_values_from_text(text)
                    if new_values:
                        values.extend(new_values)
                        ts = time.time() - start
                        print(f"[{ts:8.3f}] {text} -> {new_values}")
                line_buf.clear()
            continue

        for b in data:
            if b == ord("\n"):
                try:
                    text = bytes(line_buf).decode("utf-8", errors="replace").strip()
                except Exception:
                    text = ""
                if text:
                    # 提取数值
                    new_values = parse_values_from_text(text)
                    if new_values:
                        values.extend(new_values)
                        ts = time.time() - start
                        print(f"[{ts:8.3f}] {text} -> {new_values}")
                line_buf.clear()
            elif b == ord("\r"):
                pass
            else:
                line_buf.append(b)

    print("-" * 60)
    print(f"采集完成: {len(values)} 个数值")

    # 分析结果
    result = {
        "duration": duration,
        "values_count": len(values),
        "values": values[:100],  # 只保存前 100 个值
    }

    # 范围分析
    if values:
        range_result = analyze_data_range(values, min_val, max_val)
        result["range_analysis"] = range_result
        print(f"\n范围分析:")
        print(f"  最小值: {range_result['min']}")
        print(f"  最大值: {range_result['max']}")
        print(f"  平均值: {range_result['mean']:.2f}")
        print(f"  范围: {range_result['range']}")
        if range_result.get("out_of_range"):
            print(f"  ⚠️ 超出范围: {len(range_result['out_of_range'])} 个")

    # 跳变分析
    if len(values) >= 2:
        jump_result = analyze_data_jumps(values, jump_threshold)
        result["jump_analysis"] = jump_result
        print(f"\n跳变分析:")
        print(f"  平均差值: {jump_result['mean_diff']:.2f}")
        print(f"  最大差值: {jump_result['max_diff']:.2f}")
        print(f"  跳变阈值: {jump_result['threshold']:.2f}")
        print(f"  跳变次数: {jump_result['jump_count']}")
        if jump_result.get("jumps"):
            print(f"  ⚠️ 跳变详情:")
            for jump in jump_result["jumps"][:5]:  # 只显示前 5 个
                print(f"    [{jump['index']}] {jump['from']:.2f} -> {jump['to']:.2f} (差值: {jump['diff']:.2f})")

    # 连续性分析
    if len(values) >= 2 and expected_interval is not None:
        cont_result = analyze_data_continuity(values, expected_interval)
        result["continuity_analysis"] = cont_result
        print(f"\n连续性分析:")
        print(f"  预期间隔: {cont_result['expected_interval']}")
        print(f"  实际平均间隔: {cont_result['mean_diff']:.2f}")
        print(f"  标准差: {cont_result['std_diff']:.2f}")
        print(f"  不连续点: {cont_result['discontinuity_count']}")
        if cont_result.get("discontinuities"):
            print(f"  ⚠️ 不连续详情:")
            for disc in cont_result["discontinuities"][:5]:
                print(f"    [{disc['index']}] {disc['from']:.2f} -> {disc['to']:.2f} (偏差: {disc['deviation']:.2f})")

    # 统计分析
    if values:
        stats_result = analyze_data_statistics(values)
        result["statistics"] = stats_result
        print(f"\n统计分析:")
        print(f"  中位数: {stats_result['median']:.2f}")
        print(f"  标准差: {stats_result['std_dev']:.2f}")
        print(f"  方差: {stats_result['variance']:.2f}")

    return result


def debug_interactive(ser: serial.Serial, default_proto: str = "text"):
    """交互模式：支持所有协议切换。"""
    proto = default_proto
    start = time.time()

    print(f"交互调试模式: {ser.port} @ {ser.baudrate} bps")
    print(f"当前协议: {proto}")
    print("-" * 60)
    print("命令:")
    print("  <数据>           发送数据（根据当前协议自动处理）")
    print("  /proto text      切换到文本协议")
    print("  /proto hex       切换到 HEX 包协议")
    print("  /proto printf    切换到 printf 监听模式")
    print("  /listen <秒>     监听指定时长")
    print("  /hex <字节>      直接发送原始 HEX 字节（不加帧头帧尾）")
    print("  /baud <波特率>   切换波特率")
    print("  /timeout <秒>    设置接收超时")
    print("  /quit            退出")
    print("-" * 60)

    recv_timeout = 2.0

    # 后台接收线程
    running = True
    rx_log = []

    def reader_thread():
        nonlocal running
        ser.timeout = 0.1
        buf = bytearray()
        while running:
            try:
                data = ser.read(1)
                if not data:
                    if buf:
                        try:
                            text = bytes(buf).decode("utf-8", errors="replace").strip()
                        except Exception:
                            text = bytes(buf).hex()
                        if text:
                            ts = time.time() - start
                            rx_log.append({"timestamp": round(ts, 3), "text": text})
                            print(f"\r[RX {ts:8.3f}] {text}")
                            sys.stdout.write(f"> ")
                            sys.stdout.flush()
                        buf.clear()
                    continue

                for b in data:
                    if b == ord("\n"):
                        try:
                            text = bytes(buf).decode("utf-8", errors="replace").strip()
                        except Exception:
                            text = bytes(buf).hex()
                        if text:
                            ts = time.time() - start
                            rx_log.append({"timestamp": round(ts, 3), "text": text})
                            print(f"\r[RX {ts:8.3f}] {text}")
                            sys.stdout.write(f"> ")
                            sys.stdout.flush()
                        buf.clear()
                    elif b == ord("\r"):
                        pass
                    else:
                        buf.append(b)
            except (serial.SerialException, OSError):
                if running:
                    print("\r\n⚠️ 串口连接断开")
                    running = False
                break

    reader = threading.Thread(target=reader_thread, daemon=True)
    reader.start()

    try:
        while running:
            try:
                line = input("> ")
            except EOFError:
                break

            line = line.strip()
            if not line:
                continue

            # 命令处理
            if line.startswith("/"):
                parts = line.split(maxsplit=1)
                cmd = parts[0].lower()
                arg = parts[1] if len(parts) > 1 else ""

                if cmd == "/quit":
                    break
                elif cmd == "/proto":
                    if arg in ("text", "hex", "printf"):
                        proto = arg
                        print(f"协议已切换: {proto}")
                    else:
                        print(f"未知协议: {arg}。可用: text, hex, printf")
                elif cmd == "/listen":
                    try:
                        duration = float(arg)
                        print(f"监听 {duration}s...")
                        recv_printf(ser, duration)
                    except ValueError:
                        print(f"无效时长: {arg}")
                elif cmd == "/hex":
                    try:
                        data = parse_hex_string(arg)
                        send_raw_hex(ser, data)
                        print(f"[TX RAW] {hex_display(data)}")
                    except ValueError as e:
                        print(f"错误: {e}")
                elif cmd == "/baud":
                    try:
                        ser.baudrate = int(arg)
                        print(f"波特率已切换: {ser.baudrate}")
                    except ValueError:
                        print(f"无效波特率: {arg}")
                elif cmd == "/timeout":
                    try:
                        recv_timeout = float(arg)
                        print(f"接收超时: {recv_timeout}s")
                    except ValueError:
                        print(f"无效超时: {arg}")
                else:
                    print(f"未知命令: {cmd}")
                continue

            # 数据发送
            if proto == "text":
                send_text(ser, line)
                ts = time.time() - start
                print(f"[TX {ts:8.3f}] {line}")

            elif proto == "hex":
                try:
                    data = parse_hex_string(line)
                    send_hex_packet(ser, data)
                    ts = time.time() - start
                    print(f"[TX {ts:8.3f}] {hex_display(bytes([HEX_HEADER]) + data + bytes([HEX_TAIL]))}")
                except ValueError as e:
                    print(f"错误: {e}")

            elif proto == "printf":
                print("printf 模式下只能接收，不能发送。用 /proto text 或 /proto hex 切换。")

    except KeyboardInterrupt:
        pass

    running = False
    reader.join(timeout=2)

    print(f"\n调试结束: {len(rx_log)} 条接收数据")
    return {"mode": "interactive", "protocol": proto, "rx_count": len(rx_log)}


# === CLI ===

def main() -> int:
    parser = argparse.ArgumentParser(
        description="STM32 串口调试助手",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  %(prog)s --list                                        # 列出串口
  %(prog)s --port COM3 --proto text --send "@LED_ON"     # 发送文本命令
  %(prog)s --port COM3 --proto hex --send "01 02 03 04"  # 发送 HEX 包
  %(prog)s --port COM3 --proto printf --listen 10        # 监听 printf 输出
  %(prog)s --port COM3 --mode interactive                # 交互模式
  %(prog)s --port COM3 --mode analyze --duration 10      # 数据分析模式
  %(prog)s --port COM3 --mode analyze --duration 10 --min-val 0 --max-val 100
  %(prog)s --port COM3 --mode analyze --duration 10 --jump-threshold 10
  %(prog)s --port COM3 --mode analyze --duration 10 --expected-interval 1
  %(prog)s --port COM3 --proto text --batch cmds.txt     # 批量命令
  %(prog)s --auto . --port COM3 --proto text --send "@LED_ON"  # 自动模式
  %(prog)s --workflow workflow_result.json --port COM3 --proto printf --listen 30

协议:
  text   - 文本命令: 自动附加 \\r\\n
  hex    - HEX 包: 自动加帧头 0xFF 和帧尾 0xFE
  printf - 被动监听: 只接收，不发送

数据分析:
  analyze - 监听数据并分析范围、跳变、连续性
        """,
    )

    parser.add_argument("--list", action="store_true", help="列出可用串口")
    parser.add_argument("--port", help="串口号 (如 COM3)")
    parser.add_argument("--baud", type=int, default=9600, help="波特率 (默认 9600)")
    parser.add_argument("--proto", choices=["text", "hex", "printf"], default="text",
                        help="协议类型 (默认 text)")
    parser.add_argument("--mode", choices=["oneshot", "interactive", "analyze"], default="oneshot",
                        help="工作模式 (默认 oneshot)")
    parser.add_argument("--send", help="要发送的数据")
    parser.add_argument("--listen", type=float, help="监听时长 (秒，printf 模式)")
    parser.add_argument("--duration", type=float, default=10, help="分析时长 (秒，analyze 模式)")
    parser.add_argument("--recv-timeout", type=float, default=2.0, help="接收超时 (秒)")
    parser.add_argument("--filter", help="过滤关键字")
    parser.add_argument("--batch", help="批量命令文件")
    parser.add_argument("--output", help="输出 JSON 文件路径")
    parser.add_argument("--hex-data-len", type=int, default=4,
                        help="HEX 包数据长度 (默认 4，用于自动补零)")
    parser.add_argument("--auto", metavar="PROJECT_DIR",
                        help="自动检测项目配置（指定项目根目录）")
    parser.add_argument("--workflow", help="工作流结果 JSON 文件")
    # 数据分析参数
    parser.add_argument("--min-val", type=float, help="最小值阈值 (analyze 模式)")
    parser.add_argument("--max-val", type=float, help="最大值阈值 (analyze 模式)")
    parser.add_argument("--jump-threshold", type=float, help="跳变阈值 (analyze 模式)")
    parser.add_argument("--expected-interval", type=float, help="预期间隔 (analyze 模式)")

    args = parser.parse_args()

    # 加载项目配置
    project_config = {}
    if args.auto:
        print(f"加载项目配置: {args.auto}")
        project_config = load_project_config(args.auto)
        if project_config:
            print(f"  设备: {project_config.get('device', 'N/A')}")
            # 获取串口配置
            serial_config = get_serial_config_from_project(project_config)
            if not args.baud or args.baud == 9600:
                args.baud = serial_config.get("baud", 9600)
            if args.proto == "text":
                args.proto = serial_config.get("protocol", "text")
    elif args.workflow:
        print(f"加载工作流结果: {args.workflow}")
        workflow_data = read_json_file(args.workflow)
        if workflow_data:
            project_config["workflow"] = workflow_data
            project_config["device"] = workflow_data.get("device", "")
            project_config["project_dir"] = workflow_data.get("project_dir", "")

    if args.list:
        ports = list_ports()
        if not ports:
            print("未找到可用串口")
            return 1
        print("可用串口:")
        for p in ports:
            print(f"  {p['port']}: {p['description']} ({p['hwid']})")
        return 0

    if not args.port:
        parser.error("请指定 --port")

    # 打开串口
    try:
        ser = serial.Serial(port=args.port, baudrate=args.baud, timeout=1.0)
    except serial.SerialException as e:
        print(f"错误: 无法打开串口 {args.port}: {e}", file=sys.stderr)
        return 1

    print(f"已连接: {args.port} @ {args.baud} bps")

    try:
        if args.mode == "interactive":
            debug_interactive(ser, args.proto)
        elif args.mode == "analyze":
            # 数据分析模式
            result = debug_analyze(
                ser,
                duration=args.duration,
                min_val=args.min_val,
                max_val=args.max_val,
                jump_threshold=args.jump_threshold,
                expected_interval=args.expected_interval,
            )
            if args.output:
                Path(args.output).write_text(
                    json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")
                print(f"结果已保存: {args.output}")
        elif args.batch:
            results = debug_batch(ser, args.proto, args.batch, args.recv_timeout)
            if args.output:
                Path(args.output).write_text(
                    json.dumps(results, indent=2, ensure_ascii=False), encoding="utf-8")
                print(f"结果已保存: {args.output}")
        elif args.send or args.listen:
            if args.proto == "printf":
                duration = args.listen or 10.0
                print(f"监听 printf 输出 {duration}s...")
                entries = recv_printf(ser, duration, args.filter)
                print(f"\n共 {len(entries)} 条数据")
                if args.output:
                    Path(args.output).write_text(
                        json.dumps(entries, indent=2, ensure_ascii=False), encoding="utf-8")
                    print(f"结果已保存: {args.output}")
            else:
                if not args.send:
                    parser.error(f"{args.proto} 模式需要 --send")
                result = debug_send_recv(ser, args.proto, args.send, args.recv_timeout)
                if args.output:
                    Path(args.output).write_text(
                        json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")
                    print(f"结果已保存: {args.output}")
        else:
            parser.error("请指定 --send, --listen, --batch 或 --mode interactive/analyze")

    finally:
        ser.close()

    return 0


if __name__ == "__main__":
    sys.exit(main())
