#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
UART测试工具 - 嵌入式专家版

功能：
1. 数据接收/发送
2. 设备复位（DTR/RTS/BREAK）
3. 数据分析（统计/范围/跳变/卡值）
4. 心跳解析（key:value/寄存器位域）
5. 协议支持（Text/HEX/VOFA+）
6. 交互模式（增强调试命令）

使用方法：
  python test_uart.py --port COM3 --mode receive --duration 10
  python test_uart.py --port COM3 --mode receive --duration 10 --analyze
  python test_uart.py --port COM3 --mode reset --reset-method dtr_rts
  python test_uart.py --port COM3 --mode interactive
"""

import serial
import serial.tools.list_ports
import time
import sys
import re
import json
import argparse
import threading
from datetime import datetime

# 设置标准输出编码为UTF-8
if sys.stdout and hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass


# === 常量 ===

# 心跳前缀
HEARTBEAT_PREFIXES = ["HB", "STATUS", "DBG", "DIAG"]

# 寄存器位定义（通用）
REGISTER_BITS = {
    "en":    {"bit": 0,  "width": 1},
    "circ":  {"bit": 8,  "width": 1},
    "minc":  {"bit": 10, "width": 1},
    "psize": {"bit": 11, "width": 2},
    "msize": {"bit": 13, "width": 2},
    "tcie":  {"bit": 1,  "width": 1},
    "htie":  {"bit": 2,  "width": 1},
    "teie":  {"bit": 3,  "width": 1},
    "dir":   {"bit": 6,  "width": 1},
}

# 寄存器名模式
REGISTER_NAME_PATTERN = r"(?:DMA_)?(?:CR|SR|CSR|ISR|NDTR|PAR|M0AR|M1AR)"


class UARTTester:
    """UART测试类 - 嵌入式专家版"""

    def __init__(self, port='COM3', baudrate=115200, timeout=None, data_format='utf-8'):
        """初始化"""
        self.port = port
        self.baudrate = baudrate
        # 根据波特率动态计算超时（至少0.1秒，最多1秒）
        if timeout is None:
            self.timeout = max(0.1, min(1.0, 10.0 / baudrate * 10))
        else:
            self.timeout = timeout
        self.ser = None
        self.received_data = []
        self.is_running = False
        self.data_format = data_format  # 'utf-8', 'hex', 'ascii'

    def open(self):
        """打开串口"""
        try:
            self.ser = serial.Serial(
                port=self.port,
                baudrate=self.baudrate,
                timeout=self.timeout
            )
            # 清空串口缓冲区，避免积压数据混入
            self.ser.reset_input_buffer()
            self.ser.reset_output_buffer()
            print(f"串口已打开: {self.ser.name}")
            print(f"波特率: {self.baudrate}")
            print(f"超时: {self.timeout}秒")
            return True
        except serial.SerialException as e:
            print(f"串口错误: {e}")
            return False
        except Exception as e:
            print(f"其他错误: {e}")
            return False

    def close(self):
        """关闭串口"""
        if self.ser and self.ser.is_open:
            self.ser.close()
            print("串口已关闭")

    def reset_device(self, method='dtr_rts', signal_delay=0.1, boot_wait=0.5,
                     invert_dtr=False, invert_rts=False):
        """复位设备。

        Args:
            method: 复位方法 (dtr/rts/dtr_rts/break/break_dtr/bootloader)
            signal_delay: 信号持续时间（秒）
            boot_wait: 等待设备启动时间（秒）
            invert_dtr: 反转 DTR 极性
            invert_rts: 反转 RTS 极性

        Returns:
            复位结果字典
        """
        print(f"\n复位设备: {self.port}")
        print(f"复位方法: {method}")
        print("=" * 60)

        if not self.open():
            return {"success": False, "error": "无法打开串口"}

        try:
            # 清空缓冲区
            self.ser.reset_input_buffer()
            self.ser.reset_output_buffer()

            # 极性处理
            dtr_low = not invert_dtr
            dtr_high = invert_dtr
            rts_low = not invert_rts
            rts_high = invert_rts

            # 执行复位序列
            if method == "dtr":
                # DTR 信号复位（DTR 连接到 NRST）
                self.ser.dtr = dtr_low   # NRST 拉低
                time.sleep(signal_delay)
                self.ser.dtr = dtr_high  # NRST 释放
                time.sleep(boot_wait)

            elif method == "rts":
                # RTS 信号复位（RTS 连接到 NRST）
                self.ser.rts = rts_low   # NRST 拉低
                time.sleep(signal_delay)
                self.ser.rts = rts_high  # NRST 释放
                time.sleep(boot_wait)

            elif method == "dtr_rts":
                # DTR+RTS 组合复位（常见于 USB 转串口模块）
                # DTR 控制 NRST，RTS 控制 BOOT0
                self.ser.dtr = dtr_low   # NRST 拉低
                self.ser.rts = rts_high  # BOOT0 拉高（确保从 Flash 启动）
                time.sleep(signal_delay)
                self.ser.dtr = dtr_high  # NRST 释放
                self.ser.rts = rts_low   # BOOT0 拉低
                time.sleep(boot_wait)

            elif method == "break":
                # BREAK 信号复位
                self.ser.send_break(duration=signal_delay)
                time.sleep(boot_wait)

            elif method == "break_dtr":
                # BREAK + DTR 组合（某些板子需要）
                self.ser.send_break(duration=signal_delay)
                time.sleep(signal_delay)
                self.ser.dtr = dtr_low
                time.sleep(signal_delay)
                self.ser.dtr = dtr_high
                time.sleep(boot_wait)

            elif method == "bootloader":
                # 进入 STM32 bootloader 模式
                # 序列：BOOT0 拉高 → NRST 拉低 → NRST 释放 → 等待
                self.ser.rts = rts_high   # BOOT0 拉高
                time.sleep(signal_delay)
                self.ser.dtr = dtr_low    # NRST 拉低
                time.sleep(signal_delay)
                self.ser.dtr = dtr_high   # NRST 释放
                time.sleep(boot_wait * 2)  # bootloader 启动需要更长时间

                # 发送 0x7F 握手字节
                self.ser.write(bytes([0x7F]))
                time.sleep(0.1)

                # 读取握手响应
                handshake_data = self.ser.read(2)
                if handshake_data and 0x79 in handshake_data:
                    print("STM32 bootloader 握手成功 (收到 0x79)")
                else:
                    print("STM32 bootloader 握手失败")

            else:
                print(f"未知复位方法: {method}")
                return {"success": False, "error": f"未知复位方法: {method}"}

            print(f"复位完成，等待设备启动 ({boot_wait}s)...")

            # 验证复位（读取启动输出）
            time.sleep(0.5)
            if self.ser.in_waiting:
                data = self.ser.read(self.ser.in_waiting)
                print(f"设备输出: {data[:100]}")

            return {"success": True, "method": method}

        except Exception as e:
            print(f"复位失败: {e}")
            return {"success": False, "error": str(e)}
        finally:
            self.close()

    def receive(self, duration=10, show_timestamp=True, save_to_file=None,
                analyze=False, min_val=None, max_val=None, jump_threshold=None,
                filter_keyword=None, heartbeat=False):
        """接收数据（只接收模式）"""
        print(f"\n接收数据: {self.port} @ {self.baudrate} bps")
        print(f"监听时长: {duration} 秒")
        if filter_keyword:
            print(f"过滤关键词: {filter_keyword}")
        print("=" * 60)

        if not self.open():
            return False

        self.received_data = []
        start_time = time.time()
        self.is_running = True
        line_buf = bytearray()

        try:
            print(f"\n等待接收数据...\n")

            while time.time() - start_time < duration and self.is_running:
                # 始终尝试读取，无数据时阻塞等待超时
                waiting = self.ser.in_waiting
                data = self.ser.read(waiting if waiting > 0 else 1)
                if not data:
                    # 超时无数据，处理缓冲区中的残留行
                    if line_buf:
                        timestamp = time.time() - start_time
                        line = bytes(line_buf)
                        self._process_line(line, timestamp, show_timestamp,
                                          filter_keyword, heartbeat)
                        line_buf.clear()
                    continue

                # 逐字节处理，以\n为行结束符
                for b in data:
                    if b == ord('\n'):
                        timestamp = time.time() - start_time
                        line = bytes(line_buf)
                        self._process_line(line, timestamp, show_timestamp,
                                          filter_keyword, heartbeat)
                        line_buf.clear()
                    elif b == ord('\r'):
                        pass  # 忽略回车符
                    else:
                        line_buf.append(b)

            # 处理剩余数据
            if line_buf:
                timestamp = time.time() - start_time
                line = bytes(line_buf)
                self._process_line(line, timestamp, show_timestamp,
                                  filter_keyword, heartbeat)

            # 打印统计
            self._print_statistics()

            # 数据分析
            if analyze:
                self._analyze_data(min_val, max_val, jump_threshold)

            # 保存到文件
            if save_to_file:
                self._save_to_file(save_to_file)

            return True

        except KeyboardInterrupt:
            print("\n\n用户中断")
            return False
        except Exception as e:
            print(f"\n错误: {e}")
            return False
        finally:
            self.is_running = False
            self.close()

    def _process_line(self, line, timestamp, show_timestamp, filter_keyword, heartbeat):
        """处理一行数据。"""
        # 过滤关键词
        if filter_keyword:
            text = line.decode('utf-8', errors='replace')
            if filter_keyword not in text:
                return

        # 保存数据
        self.received_data.append({
            'timestamp': timestamp,
            'data': line
        })

        # 格式化显示
        display_data = self._format_data(line)

        # 心跳解析
        if heartbeat:
            hb_result = self._parse_heartbeat(display_data)
            if hb_result:
                print(f"[{timestamp:8.3f}] {display_data}")
                print(f"  心跳解析: {hb_result}")
                return

        if show_timestamp:
            print(f"[{timestamp:8.3f}] {display_data}")
        else:
            print(f"{display_data}")

    def _parse_heartbeat(self, text):
        """解析心跳数据。

        Args:
            text: 一行文本

        Returns:
            解析结果字典，非心跳行返回 None
        """
        # 检查是否是心跳行
        matched_prefix = None
        for p in HEARTBEAT_PREFIXES:
            if text.startswith(p):
                matched_prefix = p
                break
        if not matched_prefix:
            return None

        result = {"prefix": matched_prefix}

        # 解析所有 key:value 对（支持十进制和十六进制）
        kv_pattern = r'([A-Za-z_][A-Za-z0-9_]*)\s*:\s*(0x[0-9A-Fa-f]+|-?\d+\.?\d*)'

        for match in re.finditer(kv_pattern, text):
            key = match.group(1).lower()
            val_str = match.group(2)

            if val_str.startswith("0x") or val_str.startswith("0X"):
                val = int(val_str, 16)
                result[key] = val
                # 检查是否匹配寄存器名模式，自动解析位域
                if re.search(REGISTER_NAME_PATTERN, key, re.IGNORECASE):
                    for bit_name, bit_def in REGISTER_BITS.items():
                        bit_pos = bit_def["bit"]
                        bit_width = bit_def.get("width", 1)
                        mask = (1 << bit_width) - 1
                        result[f"{key}_{bit_name}"] = (val >> bit_pos) & mask
            else:
                try:
                    result[key] = float(val_str)
                except ValueError:
                    result[key] = val_str

        if len(result) <= 1:
            return None

        return result

    def send(self, data, wait_response=True, wait_time=1):
        """发送数据"""
        print(f"\n发送数据: {self.port} @ {self.baudrate} bps")
        print("=" * 60)

        if not self.open():
            return False

        try:
            # 发送数据
            if isinstance(data, str):
                data = data.encode('utf-8')

            print(f"发送: {data}")
            self.ser.write(data)

            # 等待响应
            if wait_response:
                print(f"等待响应: {wait_time}秒")
                time.sleep(wait_time)

                if self.ser.in_waiting:
                    response = self.ser.read(self.ser.in_waiting)
                    print(f"响应: {response}")
                    return True
                else:
                    print("无响应")
                    return False

            return True

        except Exception as e:
            print(f"错误: {e}")
            return False
        finally:
            self.close()

    def interactive(self):
        """交互模式 - 嵌入式调试增强版"""
        print(f"\n交互模式: {self.port} @ {self.baudrate} bps")
        print("=" * 60)
        print("命令:")
        print("  /hex XX XX XX  - 发送十六进制数据")
        print("  /baud N        - 切换波特率")
        print("  /reset [method]- 复位设备 (dtr/rts/dtr_rts/break)")
        print("  /analyze       - 分析已接收数据")
        print("  /filter <key>  - 设置过滤关键词")
        print("  /export [file] - 导出数据为JSON")
        print("  /clear         - 清屏")
        print("  /quit          - 退出")
        print("  其他           - 发送文本")
        print("=" * 60)

        if not self.open():
            return False

        self.is_running = True
        self.received_data = []
        filter_keyword = None

        try:
            # 启动接收线程
            receive_thread = threading.Thread(target=self._interactive_receive_thread)
            receive_thread.daemon = True
            receive_thread.start()

            # 主线程处理输入
            while self.is_running:
                try:
                    cmd = input("\n> ")

                    if cmd == "/quit":
                        break
                    elif cmd == "/clear":
                        print("\033[2J\033[H")
                    elif cmd.startswith("/baud "):
                        new_baud = int(cmd.split(" ")[1])
                        self.ser.baudrate = new_baud
                        print(f"波特率已切换: {new_baud}")
                    elif cmd.startswith("/hex "):
                        hex_str = cmd.split(" ", 1)[1]
                        data = bytes.fromhex(hex_str.replace(" ", ""))
                        self.ser.write(data)
                        print(f"已发送: {data}")
                    elif cmd.startswith("/reset"):
                        parts = cmd.split()
                        method = parts[1] if len(parts) > 1 else "dtr_rts"
                        self.close()
                        self.reset_device(method=method)
                        if not self.open():
                            print("重新打开串口失败")
                            break
                    elif cmd == "/analyze":
                        self._analyze_data()
                    elif cmd.startswith("/filter"):
                        parts = cmd.split()
                        if len(parts) > 1:
                            filter_keyword = parts[1]
                            print(f"过滤关键词已设置: {filter_keyword}")
                        else:
                            filter_keyword = None
                            print("过滤关键词已清除")
                    elif cmd.startswith("/export"):
                        parts = cmd.split()
                        filename = parts[1] if len(parts) > 1 else "uart_data.json"
                        self._export_json(filename)
                    elif cmd:
                        self.ser.write((cmd + "\r\n").encode('utf-8'))
                        print(f"已发送: {cmd}")

                except KeyboardInterrupt:
                    break
                except Exception as e:
                    print(f"错误: {e}")

            return True

        except Exception as e:
            print(f"错误: {e}")
            return False
        finally:
            self.is_running = False
            self.close()

    def _interactive_receive_thread(self):
        """交互模式接收线程"""
        line_buf = bytearray()
        while self.is_running:
            if self.ser and self.ser.is_open:
                try:
                    waiting = self.ser.in_waiting
                    data = self.ser.read(waiting if waiting > 0 else 1)
                    if data:
                        for b in data:
                            if b == ord('\n'):
                                text = bytes(line_buf).decode('utf-8', errors='replace')
                                timestamp = time.time()
                                self.received_data.append({
                                    'timestamp': timestamp,
                                    'data': bytes(line_buf)
                                })
                                # 心跳解析
                                hb_result = self._parse_heartbeat(text)
                                if hb_result:
                                    print(f"\n[接收] {text}")
                                    print(f"  心跳: {hb_result}")
                                else:
                                    print(f"\n[接收] {text}")
                                line_buf.clear()
                            elif b == ord('\r'):
                                pass
                            else:
                                line_buf.append(b)
                except Exception:
                    pass
            time.sleep(0.01)

    def _format_data(self, data):
        """格式化数据显示"""
        if self.data_format == 'hex':
            # HEX格式：显示为十六进制
            return ' '.join(f'{b:02X}' for b in data)
        elif self.data_format == 'ascii':
            # ASCII格式：只显示可打印字符
            return ''.join(chr(b) if 32 <= b < 127 else '.' for b in data)
        else:
            # UTF-8格式：解码为字符串
            return data.decode('utf-8', errors='replace')

    def _print_statistics(self):
        """打印统计信息"""
        print("\n" + "=" * 60)
        print("接收统计:")
        print(f"  接收次数: {len(self.received_data)}")

        total_bytes = sum(len(d['data']) for d in self.received_data)
        print(f"  总字节数: {total_bytes}")

        if self.received_data:
            print(f"  开始时间: {self.received_data[0]['timestamp']:.3f}s")
            print(f"  结束时间: {self.received_data[-1]['timestamp']:.3f}s")
            duration = self.received_data[-1]['timestamp'] - self.received_data[0]['timestamp']
            print(f"  持续时间: {duration:.3f}s")

            if duration > 0:
                rate = len(self.received_data) / duration
                print(f"  接收速率: {rate:.1f} 条/秒")

        print("=" * 60)

    def _analyze_data(self, min_val=None, max_val=None, jump_threshold=None):
        """分析接收的数据。"""
        if not self.received_data:
            print("\n没有数据可分析")
            return

        print("\n" + "=" * 60)
        print("数据分析")
        print("=" * 60)

        # 提取数值
        values = []
        for item in self.received_data:
            text = item['data'].decode('utf-8', errors='replace')
            parsed = self._parse_values(text)
            values.extend(parsed)

        if not values:
            print("  未找到数值数据")
            return

        # 统计分析
        n = len(values)
        mean = sum(values) / n
        min_v = min(values)
        max_v = max(values)
        range_v = max_v - min_v

        # 标准差
        variance = sum((x - mean) ** 2 for x in values) / n
        std_dev = variance ** 0.5

        print(f"\n  数值统计 ({n} 个):")
        print(f"    均值: {mean:.3f}")
        print(f"    最小: {min_v:.3f}")
        print(f"    最大: {max_v:.3f}")
        print(f"    范围: {range_v:.3f}")
        print(f"    标准差: {std_dev:.3f}")

        # 范围检查
        if min_val is not None or max_val is not None:
            out_of_range = []
            for i, v in enumerate(values):
                if min_val is not None and v < min_val:
                    out_of_range.append((i, v, "低于最小值"))
                if max_val is not None and v > max_val:
                    out_of_range.append((i, v, "高于最大值"))

            if out_of_range:
                print(f"\n  范围异常 ({len(out_of_range)} 个):")
                for idx, val, reason in out_of_range[:5]:
                    print(f"    [{idx}] {val:.3f} - {reason}")
                if len(out_of_range) > 5:
                    print(f"    ... 还有 {len(out_of_range) - 5} 个")
            else:
                print(f"\n  范围检查: 通过")

        # 跳变检测
        if jump_threshold is not None and len(values) > 1:
            jumps = []
            for i in range(1, len(values)):
                diff = abs(values[i] - values[i-1])
                if diff > jump_threshold:
                    jumps.append((i, values[i-1], values[i], diff))

            if jumps:
                print(f"\n  跳变检测 ({len(jumps)} 个):")
                for idx, from_v, to_v, diff in jumps[:5]:
                    print(f"    [{idx}] {from_v:.3f} -> {to_v:.3f} (差值: {diff:.3f})")
                if len(jumps) > 5:
                    print(f"    ... 还有 {len(jumps) - 5} 个")
            else:
                print(f"\n  跳变检测: 无跳变")

        # 卡值检测
        unique_values = len(set(values))
        if unique_values <= 3 and n > 10:
            print(f"\n  卡值警告: 只有 {unique_values} 种值（共 {n} 个采样点）")
            print(f"    可能是 ADC 卡值或传感器故障")

        # 趋势分析
        if n >= 3:
            # 线性回归
            x = list(range(n))
            x_mean = sum(x) / n
            y_mean = mean
            numerator = sum((x[i] - x_mean) * (values[i] - y_mean) for i in range(n))
            denominator = sum((x[i] - x_mean) ** 2 for i in range(n))
            slope = numerator / denominator if denominator != 0 else 0

            if slope > 0.1:
                trend = "上升"
            elif slope < -0.1:
                trend = "下降"
            else:
                trend = "平稳"

            print(f"\n  趋势分析: {trend} (斜率: {slope:.4f})")

        print("=" * 60)

    def _parse_values(self, text):
        """从文本中提取数值。

        支持格式:
          "temp:25.5,humidity:60.2"
          "25.5,60.2,101.3"
          "ADC:2048"
        """
        values = []

        # 优先匹配 "key:value" 或 "key=value" 格式中的数值
        kv_pattern = r'[:=]\s*(-?\d+\.?\d*)'
        kv_matches = re.findall(kv_pattern, text)
        if kv_matches:
            for match in kv_matches:
                try:
                    values.append(float(match))
                except ValueError:
                    continue
            return values

        # 回退到通用匹配
        pattern = r'(?:^|[,;\s\(])(-?\d+\.?\d*)(?:$|[,;\s\)])'
        matches = re.findall(pattern, text)
        for match in matches:
            try:
                values.append(float(match))
            except ValueError:
                continue
        return values

    def _save_to_file(self, filename):
        """保存数据到文件"""
        try:
            with open(filename, 'w', encoding='utf-8') as f:
                f.write(f"UART数据记录\n")
                f.write(f"端口: {self.port}\n")
                f.write(f"波特率: {self.baudrate}\n")
                f.write(f"时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
                f.write("=" * 60 + "\n")

                for item in self.received_data:
                    f.write(f"[{item['timestamp']:.3f}] {item['data'].decode('utf-8', errors='replace')}\n")

            print(f"\n数据已保存: {filename}")
        except Exception as e:
            print(f"\n保存失败: {e}")

    def _export_json(self, filename):
        """导出数据为JSON格式。"""
        try:
            export_data = {
                "port": self.port,
                "baudrate": self.baudrate,
                "timestamp": datetime.now().isoformat(),
                "entries": []
            }

            for item in self.received_data:
                text = item['data'].decode('utf-8', errors='replace')
                entry = {
                    "timestamp": item['timestamp'],
                    "text": text,
                    "values": self._parse_values(text)
                }

                # 心跳解析
                hb = self._parse_heartbeat(text)
                if hb:
                    entry["heartbeat"] = hb

                export_data["entries"].append(entry)

            with open(filename, 'w', encoding='utf-8') as f:
                json.dump(export_data, f, indent=2, ensure_ascii=False)

            print(f"\n数据已导出: {filename}")
            print(f"  条目数: {len(export_data['entries'])}")

        except Exception as e:
            print(f"\n导出失败: {e}")


def list_ports():
    """列出可用串口"""
    ports = serial.tools.list_ports.comports()

    print("可用串口:")
    print("=" * 60)
    for port in ports:
        print(f"  {port.device}: {port.description}")
        print(f"    硬件ID: {port.hwid}")
        print(f"    位置: {port.location}")
    print("=" * 60)
    print(f"共 {len(ports)} 个串口")


def main():
    """主函数"""
    parser = argparse.ArgumentParser(description='UART测试工具 - 嵌入式专家版')
    parser.add_argument('--port', default='COM3', help='串口端口')
    parser.add_argument('--baud', type=int, default=115200, help='波特率')
    parser.add_argument('--mode', choices=['receive', 'send', 'interactive', 'list', 'reset'],
                        default='receive', help='工作模式')
    parser.add_argument('--duration', type=int, default=10, help='接收时长（秒）')
    parser.add_argument('--data', help='发送数据')
    parser.add_argument('--output', help='输出文件路径')
    parser.add_argument('--no-timestamp', action='store_true', help='不显示时间戳')
    parser.add_argument('--format', choices=['utf-8', 'hex', 'ascii'],
                        default='utf-8', help='数据显示格式')

    # 数据分析参数
    parser.add_argument('--analyze', action='store_true', help='分析接收的数据')
    parser.add_argument('--min-val', type=float, help='最小值阈值')
    parser.add_argument('--max-val', type=float, help='最大值阈值')
    parser.add_argument('--jump-threshold', type=float, help='跳变阈值')

    # 过滤参数
    parser.add_argument('--filter', help='过滤关键词')

    # 心跳解析
    parser.add_argument('--heartbeat', action='store_true', help='解析心跳数据')

    # 复位参数
    parser.add_argument('--reset-method', choices=['dtr', 'rts', 'dtr_rts', 'break', 'break_dtr', 'bootloader'],
                        default='dtr_rts', help='复位方法')
    parser.add_argument('--signal-delay', type=float, default=0.1, help='复位信号持续时间（秒）')
    parser.add_argument('--boot-wait', type=float, default=0.5, help='等待设备启动时间（秒）')
    parser.add_argument('--invert-dtr', action='store_true', help='反转 DTR 极性')
    parser.add_argument('--invert-rts', action='store_true', help='反转 RTS 极性')

    args = parser.parse_args()

    print("UART测试工具 - 嵌入式专家版")
    print("=" * 60)

    if args.mode == 'list':
        list_ports()
        return

    tester = UARTTester(port=args.port, baudrate=args.baud, data_format=args.format)

    if args.mode == 'receive':
        tester.receive(
            duration=args.duration,
            show_timestamp=not args.no_timestamp,
            save_to_file=args.output,
            analyze=args.analyze,
            min_val=args.min_val,
            max_val=args.max_val,
            jump_threshold=args.jump_threshold,
            filter_keyword=args.filter,
            heartbeat=args.heartbeat
        )
    elif args.mode == 'send':
        if not args.data:
            print("错误: 发送模式需要指定 --data 参数")
            return
        tester.send(args.data)
    elif args.mode == 'interactive':
        tester.interactive()
    elif args.mode == 'reset':
        tester.reset_device(
            method=args.reset_method,
            signal_delay=args.signal_delay,
            boot_wait=args.boot_wait,
            invert_dtr=args.invert_dtr,
            invert_rts=args.invert_rts
        )

if __name__ == '__main__':
    main()
