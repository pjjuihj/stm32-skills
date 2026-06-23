#!/usr/bin/env python
"""STM32 串口验证工具。

支持数据接收、命令发送、协议解析、自动化测试和稳定性测试。

用法:
  python serial_monitor.py --port COM3 --baud 115200 --mode monitor --duration 10
  python serial_monitor.py --port COM3 --baud 115200 --mode send --send "T\\r" --wait 2
  python serial_monitor.py --port COM3 --baud 115200 --mode parse --protocol vofa-firewater
  python serial_monitor.py --port COM3 --baud 115200 --mode test --test-file tests.json
  python serial_monitor.py --port COM3 --baud 115200 --mode stress --duration 60

协议:
  raw             - 原始字节（十六进制 + ASCII）
  text            - 文本行（\\r\\n 分隔）
  vofa-firewater  - VOFA+ FireWater（逗号分隔浮点数）
  vofa-justfloat  - VOFA+ JustFloat（二进制浮点数帧）
  custom          - 自定义帧格式（--frame-header/--frame-tail/--frame-size）

依赖:
  pip install pyserial
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

try:
    import serial
    import serial.tools.list_ports
except ImportError:
    print("错误: 需要安装 pyserial。运行: pip install pyserial", file=sys.stderr)
    sys.exit(1)


# === 协议解析器 ===

def parse_raw(data: bytes) -> list[dict]:
    """原始字节显示（十六进制 + ASCII）。"""
    hex_str = " ".join(f"{b:02X}" for b in data)
    ascii_str = "".join(chr(b) if 32 <= b < 127 else "." for b in data)
    return [{"type": "raw", "hex": hex_str, "ascii": ascii_str, "bytes": len(data)}]


def parse_text(data: bytes) -> list[dict]:
    """文本行解析（按 \\r\\n 分隔）。"""
    try:
        text = data.decode("utf-8", errors="replace")
    except Exception:
        text = data.decode("latin-1")
    lines = re.split(r"[\r\n]+", text)
    return [{"type": "text", "line": line.strip()} for line in lines if line.strip()]


def parse_vofa_firewater(data: bytes) -> list[dict]:
    """VOFA+ FireWater 协议解析（逗号分隔浮点数，以 \\n 结尾）。"""
    try:
        text = data.decode("utf-8", errors="replace")
    except Exception:
        return []

    results = []
    for line in re.split(r"[\r\n]+", text):
        line = line.strip()
        if not line:
            continue
        values = []
        for part in line.split(","):
            part = part.strip()
            try:
                values.append(float(part))
            except ValueError:
                pass
        if values:
            results.append({"type": "vofa-firewater", "values": values, "raw": line})
    return results


def parse_vofa_justfloat(data: bytes) -> list[dict]:
    """VOFA+ JustFloat 协议解析（二进制浮点数帧，帧尾 0x00 0x00 0x80 0x7F）。"""
    tail = b"\x00\x00\x80\x7f"
    results = []
    pos = 0
    while pos <= len(data) - 4:
        end = data.find(tail, pos)
        if end < 0:
            break
        frame = data[pos:end]
        if len(frame) >= 4 and len(frame) % 4 == 0:
            values = list(struct.unpack(f"<{len(frame)//4}f", frame))
            results.append({"type": "vofa-justfloat", "values": values, "frame_bytes": len(frame)})
        pos = end + 4
    return results


def parse_custom_frame(data: bytes, header: bytes, tail: bytes, size: int | None) -> list[dict]:
    """自定义帧格式解析。"""
    results = []
    pos = 0
    while pos < len(data):
        start = data.find(header, pos)
        if start < 0:
            break
        if size:
            end = start + len(header) + size
            if end <= len(data):
                frame = data[start:end]
                payload = frame[len(header):len(header)+size]
                results.append({"type": "custom", "frame": frame.hex(), "payload": payload.hex(), "size": len(payload)})
            pos = start + 1
        else:
            end = data.find(tail, start + len(header))
            if end >= 0:
                frame = data[start:end + len(tail)]
                payload = data[start + len(header):end]
                results.append({"type": "custom", "frame": frame.hex(), "payload": payload.hex(), "size": len(payload)})
                pos = end + len(tail)
            else:
                break
    return results


PARSERS = {
    "raw": parse_raw,
    "text": parse_text,
    "vofa-firewater": parse_vofa_firewater,
    "vofa-justfloat": parse_vofa_justfloat,
}


# === 实时日志 ===

class LogWriter:
    """实时日志写入器，每条数据立即写入文件。"""

    def __init__(self, path: str):
        self._file = open(path, "a", encoding="utf-8")
        self._count = 0

    def write(self, entry: dict):
        """写入一条日志记录并立即刷新。"""
        line = json.dumps(entry, ensure_ascii=False)
        self._file.write(line + "\n")
        self._file.flush()
        self._count += 1

    @property
    def count(self):
        return self._count

    def close(self):
        self._file.close()


# === 核心功能 ===

def list_ports() -> list[dict]:
    """列出可用串口。"""
    ports = []
    for p in serial.tools.list_ports.comports():
        ports.append({"port": p.device, "description": p.description, "hwid": p.hwid})
    return ports


def open_serial(port: str, baud: int, timeout: float = 1.0) -> serial.Serial:
    """打开串口连接。"""
    return serial.Serial(port=port, baudrate=baud, timeout=timeout)


def cmd_monitor(ser: serial.Serial, duration: float, protocol: str, output: str | None,
                log_writer: LogWriter | None = None, keyword: str | None = None) -> dict:
    """持续接收并显示数据。

    Args:
        ser: 串口对象
        duration: 监听时长（秒）
        protocol: 协议类型
        output: 结束后保存的 JSON 文件路径
        log_writer: 实时日志写入器（每条数据立即写入文件）
        keyword: 过滤关键字（只显示包含此关键字的行）
    """
    parser = PARSERS.get(protocol, parse_raw)
    log = []
    start = time.time()

    print(f"监听 {ser.port} @ {ser.baudrate} bps，协议: {protocol}，时长: {duration}s")
    if keyword:
        print(f"过滤: 包含 '{keyword}' 的数据")
    if log_writer:
        print(f"实时日志: 启用")
    print("-" * 60)
    print("按 Ctrl+C 停止监听")
    print("-" * 60)

    try:
        while time.time() - start < duration:
            data = ser.read(ser.in_waiting or 1)
            if not data:
                continue

            ts = time.time() - start
            parsed = parser(data)

            for item in parsed:
                entry = {"timestamp": round(ts, 3), **item}
                log.append(entry)

                # 关键字过滤
                if keyword:
                    text_repr = json.dumps(entry, ensure_ascii=False)
                    if keyword.lower() not in text_repr.lower():
                        continue

                # 实时日志
                if log_writer:
                    log_writer.write(entry)

                # 显示
                if protocol == "raw":
                    print(f"[{ts:8.3f}] {item['hex']}  |{item['ascii']}|")
                elif protocol == "text":
                    print(f"[{ts:8.3f}] {item['line']}")
                elif "vofa" in protocol:
                    vals = " ".join(f"{v:.4f}" for v in item.get("values", []))
                    print(f"[{ts:8.3f}] {vals}")
                elif protocol == "custom":
                    print(f"[{ts:8.3f}] [{item['size']}B] {item['payload']}")
    except KeyboardInterrupt:
        pass

    print("-" * 60)
    print(f"接收完成: {len(log)} 条数据")
    if log_writer:
        print(f"实时日志已写入: {log_writer.count} 条")

    if output:
        Path(output).write_text(json.dumps(log, indent=2, ensure_ascii=False), encoding="utf-8")
        print(f"日志已保存: {output}")

    return {"mode": "monitor", "protocol": protocol, "entries": len(log), "duration": time.time() - start, "log": log}


def cmd_interactive(ser: serial.Serial, protocol: str, log_writer: LogWriter | None = None,
                    keyword: str | None = None) -> dict:
    """交互模式：监听串口数据的同时可以输入命令发送。

    支持:
      - 文本输入直接发送（自动附加 \\r\\n）
      - /hex FF 01 02 发送十六进制字节
      - /baud 9600 切换波特率
      - /log on|off 开关实时日志
      - /filter <keyword> 设置过滤关键字
      - /clear 清屏
      - /quit 退出

    Args:
        ser: 串口对象
        protocol: 接收数据的协议类型
        log_writer: 实时日志写入器
        keyword: 过滤关键字
    """
    parser = PARSERS.get(protocol, parse_raw)
    log = []
    start = time.time()
    running = True
    current_keyword = keyword

    def reader_thread():
        """后台线程：持续读取串口数据并显示。"""
        nonlocal running
        while running:
            try:
                data = ser.read(ser.in_waiting or 1)
                if not data:
                    continue

                ts = time.time() - start
                parsed = parser(data)

                for item in parsed:
                    entry = {"timestamp": round(ts, 3), **item}
                    log.append(entry)

                    # 关键字过滤
                    if current_keyword:
                        text_repr = json.dumps(entry, ensure_ascii=False)
                        if current_keyword.lower() not in text_repr.lower():
                            continue

                    # 实时日志
                    if log_writer:
                        log_writer.write(entry)

                    # 显示（使用前缀标记来自设备）
                    if protocol == "raw":
                        print(f"\r[DEV {ts:8.3f}] {item['hex']}  |{item['ascii']}|")
                    elif protocol == "text":
                        print(f"\r[DEV {ts:8.3f}] {item['line']}")
                    elif "vofa" in protocol:
                        vals = " ".join(f"{v:.4f}" for v in item.get("values", []))
                        print(f"\r[DEV {ts:8.3f}] {vals}")
                    elif protocol == "custom":
                        print(f"\r[DEV {ts:8.3f}] [{item['size']}B] {item['payload']}")

                    # 重新显示输入提示
                    sys.stdout.write("> ")
                    sys.stdout.flush()
            except (serial.SerialException, OSError):
                if running:
                    print("\r\n⚠️ 串口连接断开")
                    running = False
                break

    # 启动读取线程
    reader = threading.Thread(target=reader_thread, daemon=True)
    reader.start()

    print(f"交互模式: {ser.port} @ {ser.baudrate} bps，协议: {protocol}")
    if current_keyword:
        print(f"过滤: 包含 '{current_keyword}' 的数据")
    print("-" * 60)
    print("输入文本发送，或使用命令:")
    print("  /hex FF 01 02    发送十六进制字节")
    print("  /baud 9600       切换波特率")
    print("  /filter <keyword> 设置过滤关键字")
    print("  /log on|off       开关实时日志")
    print("  /clear            清屏")
    print("  /quit             退出")
    print("-" * 60)

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
                elif cmd == "/hex":
                    try:
                        hex_bytes = bytes.fromhex(arg.replace(" ", ""))
                        ser.write(hex_bytes)
                        print(f"[TX] {hex_bytes.hex(' ')}")
                    except ValueError:
                        print(f"错误: 无效的十六进制 '{arg}'")
                elif cmd == "/baud":
                    try:
                        new_baud = int(arg)
                        ser.baudrate = new_baud
                        print(f"波特率已切换: {new_baud}")
                    except ValueError:
                        print(f"错误: 无效的波特率 '{arg}'")
                elif cmd == "/filter":
                    current_keyword = arg if arg else None
                    if current_keyword:
                        print(f"过滤已设置: '{current_keyword}'")
                    else:
                        print("过滤已清除")
                elif cmd == "/log":
                    if arg == "on" and log_writer:
                        print("实时日志: 已启用")
                    elif arg == "off":
                        # 不关闭 writer，只是标记
                        print("实时日志: 已禁用（文件仍打开，重启后生效）")
                    else:
                        print(f"用法: /log on|off")
                elif cmd == "/clear":
                    print("\033[2J\033[H", end="")
                else:
                    print(f"未知命令: {cmd}")
                continue

            # 文本发送（自动附加 \r\n）
            send_bytes = line.encode("utf-8") + b"\r\n"
            ser.write(send_bytes)
            ts = time.time() - start
            print(f"[TX {ts:8.3f}] {line}")

    except KeyboardInterrupt:
        pass

    running = False
    reader.join(timeout=2)

    print("-" * 60)
    print(f"交互结束: {len(log)} 条接收数据")

    return {"mode": "interactive", "protocol": protocol, "entries": len(log), "duration": time.time() - start}


def cmd_send(ser: serial.Serial, send_data: str, wait: float, protocol: str, output: str | None) -> dict:
    """发送命令并捕获响应。"""
    parser = PARSERS.get(protocol, parse_text)

    # 处理转义字符
    send_bytes = send_data.encode("utf-8").decode("unicode_escape").encode("latin-1")

    print(f"发送: {send_bytes!r}")
    ser.write(send_bytes)
    ser.flush()

    print(f"等待响应 {wait}s...")
    time.sleep(wait)

    data = ser.read(ser.in_waiting or 0)
    if not data:
        print("无响应")
        return {"mode": "send", "sent": send_data, "response_bytes": 0, "parsed": []}

    parsed = parser(data)
    print(f"接收: {len(data)} bytes")

    for item in parsed:
        if "line" in item:
            print(f"  > {item['line']}")
        elif "values" in item:
            vals = " ".join(f"{v:.4f}" for v in item["values"])
            print(f"  > {vals}")
        else:
            print(f"  > {data.hex()}")

    result = {"mode": "send", "sent": send_data, "response_bytes": len(data), "parsed": parsed}
    if output:
        Path(output).write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")
    return result


def cmd_test(ser: serial.Serial, test_file: str, protocol: str, output: str | None) -> dict:
    """自动化测试：发送多条命令，验证响应。"""
    tests = json.loads(Path(test_file).read_text(encoding="utf-8"))
    results = []
    passed = 0
    failed = 0

    print(f"运行测试文件: {test_file}")
    print("-" * 60)

    for i, test in enumerate(tests):
        cmd = test.get("send", "")
        expected = test.get("expect", "")
        timeout = test.get("timeout", 2.0)
        name = test.get("name", f"test-{i}")

        # 发送
        send_bytes = cmd.encode("utf-8").decode("unicode_escape").encode("latin-1")
        ser.write(send_bytes)
        ser.flush()
        time.sleep(timeout)

        # 接收
        data = ser.read(ser.in_waiting or 0)
        response = data.decode("utf-8", errors="replace").strip()

        # 验证
        if expected:
            ok = expected in response
        else:
            ok = len(data) > 0

        status = "PASS" if ok else "FAIL"
        if ok:
            passed += 1
        else:
            failed += 1

        print(f"  [{status}] {name}: send={cmd!r} expect={expected!r} got={response[:80]!r}")
        results.append({"name": name, "send": cmd, "expected": expected, "response": response, "status": status})

    print("-" * 60)
    print(f"测试完成: {passed} 通过, {failed} 失败, 共 {len(tests)} 条")

    result = {"mode": "test", "total": len(tests), "passed": passed, "failed": failed, "results": results}
    if output:
        Path(output).write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")
    return result


def cmd_stress(ser: serial.Serial, duration: float, protocol: str, output: str | None) -> dict:
    """稳定性测试：长时间运行，检测异常。"""
    parser = PARSERS.get(protocol, parse_raw)
    total_bytes = 0
    total_packets = 0
    errors = 0
    gaps = []  # 超过 1 秒无数据的间隔
    last_data_time = time.time()
    start = time.time()

    print(f"稳定性测试: {ser.port} @ {ser.baudrate} bps，时长: {duration}s")
    print("-" * 60)

    while time.time() - start < duration:
        data = ser.read(ser.in_waiting or 1)
        if not data:
            now = time.time()
            if now - last_data_time > 5.0:
                gaps.append({"timestamp": round(now - start, 1), "duration": round(now - last_data_time, 1)})
                last_data_time = now  # 避免重复报告
            continue

        last_data_time = time.time()
        total_bytes += len(data)
        total_packets += 1

        # 检测乱码（非协议数据）
        if protocol == "text":
            try:
                data.decode("utf-8")
            except UnicodeDecodeError:
                errors += 1

        # 进度显示
        elapsed = time.time() - start
        if int(elapsed) % 10 == 0 and int(elapsed) > 0:
            print(f"  [{elapsed:.0f}s] {total_bytes} bytes, {total_packets} packets, {errors} errors")

    elapsed = time.time() - start
    print("-" * 60)
    print(f"稳定性测试完成:")
    print(f"  总字节: {total_bytes}")
    print(f"  总包数: {total_packets}")
    print(f"  错误数: {errors}")
    print(f"  数据间隔 >5s: {len(gaps)} 次")
    if total_bytes > 0:
        print(f"  平均速率: {total_bytes/elapsed:.0f} bytes/s")

    status = "PASS" if errors == 0 and len(gaps) == 0 else ("WARN" if errors == 0 else "FAIL")

    result = {
        "mode": "stress",
        "duration": round(elapsed, 1),
        "total_bytes": total_bytes,
        "total_packets": total_packets,
        "errors": errors,
        "gaps": gaps,
        "avg_rate_bps": round(total_bytes / elapsed) if elapsed > 0 else 0,
        "status": status,
    }
    if output:
        Path(output).write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")
    return result


# === 主函数 ===

def main() -> int:
    from shared import setup_encoding
    setup_encoding()
    parser = argparse.ArgumentParser(
        description="STM32 串口验证工具",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""示例:
  %(prog)s --list                                    # 列出可用串口
  %(prog)s --port COM3 --mode monitor --duration 10              # 监听 10 秒
  %(prog)s --port COM3 --mode interactive                        # 交互模式（边收边发）
  %(prog)s --port COM3 --mode monitor --log-file uart.log       # 监听+实时写入日志
  %(prog)s --port COM3 --mode monitor --filter "error"          # 只显示含 error 的数据
  %(prog)s --port COM3 --mode send --send "T\\\\r" --wait 2
  %(prog)s --port COM3 --mode parse --protocol vofa-firewater --duration 10
  %(prog)s --port COM3 --mode test --test-file tests.json
  %(prog)s --port COM3 --mode stress --duration 60
""",
    )
    parser.add_argument("--auto", metavar="PROJECT_DIR",
                        help="自动检测项目配置并列出可用串口（指定项目根目录）")
    parser.add_argument("--list", action="store_true", help="列出可用串口")
    parser.add_argument("--port", help="串口号 (如 COM3)")
    parser.add_argument("--baud", type=int, default=115200, help="波特率 (默认 115200)")
    parser.add_argument("--mode", choices=["monitor", "send", "parse", "test", "stress", "interactive"], default="monitor", help="工作模式 (monitor/interactive/send/parse/test/stress)")
    parser.add_argument("--protocol", choices=["raw", "text", "vofa-firewater", "vofa-justfloat", "custom"], default="text", help="协议类型")
    parser.add_argument("--duration", type=float, default=10, help="监听/测试时长 (秒)")
    parser.add_argument("--send", help="要发送的数据")
    parser.add_argument("--wait", type=float, default=2, help="发送后等待时间 (秒)")
    parser.add_argument("--test-file", help="测试用例 JSON 文件")
    parser.add_argument("--output", help="输出 JSON 文件路径（结束后保存）")
    parser.add_argument("--log-file", help="实时日志文件路径（接收时立即写入）")
    parser.add_argument("--filter", help="过滤关键字（只显示包含此关键字的数据）")
    parser.add_argument("--frame-header", help="自定义帧头 (十六进制)")
    parser.add_argument("--frame-tail", help="自定义帧尾 (十六进制)")
    parser.add_argument("--frame-size", type=int, help="自定义帧载荷大小 (固定长度模式)")
    args = parser.parse_args()

    # --auto 模式：列出串口并显示项目信息
    if args.auto:
        # 列出可用串口
        ports = list_ports()
        if not ports:
            print("未找到可用串口")
            return 1
        print("可用串口:")
        for p in ports:
            print(f"  {p['port']}: {p['description']} ({p['hwid']})")
        # 尝试检测项目中的波特率配置
        try:
            import subprocess
            detect_script = Path(__file__).parent / "detect_config.py"
            if detect_script.exists():
                proc = subprocess.run(
                    [sys.executable, str(detect_script), "--scan", args.auto],
                    capture_output=True, text=True, timeout=10,
                )
                if proc.returncode == 0:
                    config = json.loads(proc.stdout)
                    if "device" in config:
                        print(f"\n项目芯片: {config['device']}")
        except Exception:
            pass
        print(f"\n提示: 使用 --port <串口号> 连接设备")
        return 0

    # 列出串口
    if args.list:
        ports = list_ports()
        if not ports:
            print("未找到可用串口")
            return 1
        print("可用串口:")
        for p in ports:
            print(f"  {p['port']}: {p['description']} ({p['hwid']})")
        return 0

    # 需要串口连接的模式
    if not args.port:
        print("错误: 请指定 --port", file=sys.stderr)
        return 1

    # 自定义协议配置
    if args.protocol == "custom":
        if args.frame_header and args.frame_tail:
            header = bytes.fromhex(args.frame_header)
            tail = bytes.fromhex(args.frame_tail)
            PARSERS["custom"] = lambda data, h=header, t=tail, s=args.frame_size: parse_custom_frame(data, h, t, s)
        else:
            print("错误: 自定义协议需要 --frame-header 和 --frame-tail", file=sys.stderr)
            return 1

    # 打开串口
    try:
        ser = open_serial(args.port, args.baud)
    except serial.SerialException as e:
        print(f"错误: 无法打开串口 {args.port}: {e}", file=sys.stderr)
        return 1

    print(f"已连接: {args.port} @ {args.baud} bps")

    # 创建实时日志写入器
    log_writer = None
    if args.log_file:
        log_writer = LogWriter(args.log_file)
        print(f"实时日志: {args.log_file}")

    try:
        if args.mode == "monitor":
            result = cmd_monitor(ser, args.duration, args.protocol, args.output,
                                 log_writer=log_writer, keyword=args.filter)
        elif args.mode == "interactive":
            result = cmd_interactive(ser, args.protocol, log_writer=log_writer, keyword=args.filter)
        elif args.mode == "send":
            if not args.send:
                print("错误: send 模式需要 --send", file=sys.stderr)
                return 1
            result = cmd_send(ser, args.send, args.wait, args.protocol, args.output)
        elif args.mode == "parse":
            result = cmd_monitor(ser, args.duration, args.protocol, args.output,
                                 log_writer=log_writer, keyword=args.filter)
        elif args.mode == "test":
            if not args.test_file:
                print("错误: test 模式需要 --test-file", file=sys.stderr)
                return 1
            result = cmd_test(ser, args.test_file, args.protocol, args.output)
        elif args.mode == "stress":
            result = cmd_stress(ser, args.duration, args.protocol, args.output)
        else:
            print(f"错误: 未知模式 {args.mode}", file=sys.stderr)
            return 1
    finally:
        if log_writer:
            log_writer.close()
            print(f"实时日志已关闭: {log_writer.count} 条记录")
        ser.close()

    # 输出 JSON
    if args.output:
        print(f"结果已保存: {args.output}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
