#!/usr/bin/env python
"""STM32 串口测试框架。

自动发送命令 → 检查响应 → 生成测试报告。

用法:
  python serial_test.py --port COM3 --test tests.json              # 运行测试用例
  python serial_test.py --port COM3 --test tests.json --report     # 生成报告
  python serial_test.py --port COM3 --send "@LED_ON" --expect "OK" # 单条测试

测试用例 JSON 格式:
  {
    "name": "LED 控制测试",
    "baudrate": 115200,
    "tests": [
      {
        "name": "开灯",
        "send": "@LED_ON",
        "expect": "OK",
        "timeout": 2.0
      },
      {
        "name": "查状态",
        "send": "@STATUS",
        "expect_contains": "LED:ON",
        "timeout": 1.0
      },
      {
        "name": "关灯",
        "send": "@LED_OFF",
        "expect": "OK",
        "timeout": 2.0
      }
    ]
  }
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
from datetime import datetime
from pathlib import Path

# 脚本目录
SCRIPT_DIR = Path(__file__).parent

from shared import setup_encoding

setup_encoding()

try:
    import serial
except ImportError:
    print("❌ 需要安装 pyserial: pip install pyserial")
    sys.exit(1)


class SerialTestResult:
    """单条测试结果。"""
    def __init__(self, name: str):
        self.name = name
        self.passed = False
        self.send_data = ""
        self.expected = ""
        self.actual = ""
        self.error = ""
        self.duration_ms = 0

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "passed": self.passed,
            "send": self.send_data,
            "expected": self.expected,
            "actual": self.actual,
            "error": self.error,
            "duration_ms": self.duration_ms
        }


class SerialTestRunner:
    """串口测试运行器。"""
    def __init__(self, port: str, baudrate: int = 115200, timeout: float = 2.0):
        self.port = port
        self.baudrate = baudrate
        self.default_timeout = timeout
        self.ser = None
        self.results: list[SerialTestResult] = []

    def connect(self) -> bool:
        """连接串口。"""
        try:
            self.ser = serial.Serial(
                port=self.port,
                baudrate=self.baudrate,
                timeout=self.default_timeout,
                write_timeout=2
            )
            # 清空缓冲区
            self.ser.reset_input_buffer()
            self.ser.reset_output_buffer()
            time.sleep(0.1)
            return True
        except serial.SerialException as e:
            print(f"❌ 串口连接失败: {e}")
            return False

    def disconnect(self):
        """断开串口。"""
        if self.ser and self.ser.is_open:
            self.ser.close()

    def send_and_receive(self, data: str, timeout: float = None) -> str:
        """发送数据并接收响应。"""
        if not self.ser or not self.ser.is_open:
            return ""

        timeout = timeout or self.default_timeout

        # 清空接收缓冲区
        self.ser.reset_input_buffer()
        time.sleep(0.05)

        # 发送
        send_str = data + "\r\n"
        self.ser.write(send_str.encode("utf-8"))
        self.ser.flush()

        # 接收响应
        response = ""
        start_time = time.time()
        while time.time() - start_time < timeout:
            if self.ser.in_waiting > 0:
                chunk = self.ser.read(self.ser.in_waiting).decode("utf-8", errors="replace")
                response += chunk
                # 检查是否收到完整行
                if "\n" in response:
                    break
            time.sleep(0.05)

        return response.strip()

    def run_test(self, test_case: dict) -> SerialTestResult:
        """运行单条测试。"""
        name = test_case.get("name", "unnamed")
        send_data = test_case.get("send", "")
        expect = test_case.get("expect", "")
        expect_contains = test_case.get("expect_contains", "")
        expect_regex = test_case.get("expect_regex", "")
        timeout = test_case.get("timeout", self.default_timeout)
        delay_before = test_case.get("delay_before", 0)
        delay_after = test_case.get("delay_after", 0)

        result = SerialTestResult(name)
        result.send_data = send_data
        result.expected = expect or expect_contains or expect_regex

        if delay_before > 0:
            time.sleep(delay_before)

        start_time = time.time()

        try:
            actual = self.send_and_receive(send_data, timeout)
            result.actual = actual
            result.duration_ms = int((time.time() - start_time) * 1000)

            # 检查响应
            if expect:
                result.passed = actual.strip() == expect.strip()
            elif expect_contains:
                result.passed = expect_contains in actual
            elif expect_regex:
                result.passed = bool(re.search(expect_regex, actual))
            else:
                # 没有期望值，只要收到响应就算通过
                result.passed = len(actual) > 0

        except Exception as e:
            result.error = str(e)
            result.passed = False

        if delay_after > 0:
            time.sleep(delay_after)

        return result

    def run_tests(self, test_file: str) -> list[SerialTestResult]:
        """运行测试用例文件。"""
        with open(test_file, "r", encoding="utf-8") as f:
            config = json.load(f)

        tests = config.get("tests", [])
        baudrate = config.get("baudrate", self.baudrate)
        name = config.get("name", os.path.basename(test_file))

        if baudrate != self.baudrate:
            self.baudrate = baudrate
            if self.ser and self.ser.is_open:
                self.ser.baudrate = baudrate

        print(f"\n📋 测试套件: {name}")
        print(f"   用例数: {len(tests)}")
        print(f"   波特率: {baudrate}")
        print()

        self.results = []
        for i, test_case in enumerate(tests, 1):
            test_name = test_case.get("name", f"test_{i}")
            print(f"  [{i}/{len(tests)}] {test_name}...", end=" ", flush=True)

            result = self.run_test(test_case)
            self.results.append(result)

            if result.passed:
                print(f"✅ ({result.duration_ms}ms)")
            else:
                print(f"❌")
                if result.actual:
                    print(f"         期望: {result.expected}")
                    print(f"         实际: {result.actual[:100]}")
                if result.error:
                    print(f"         错误: {result.error}")

        return self.results

    def generate_report(self, output_file: str = None) -> dict:
        """生成测试报告。"""
        total = len(self.results)
        passed = sum(1 for r in self.results if r.passed)
        failed = total - passed

        report = {
            "timestamp": datetime.now().isoformat(),
            "port": self.port,
            "baudrate": self.baudrate,
            "summary": {
                "total": total,
                "passed": passed,
                "failed": failed,
                "pass_rate": f"{passed / max(total, 1) * 100:.1f}%"
            },
            "tests": [r.to_dict() for r in self.results]
        }

        if output_file:
            with open(output_file, "w", encoding="utf-8") as f:
                json.dump(report, f, indent=2, ensure_ascii=False)
            print(f"\n📄 报告已保存: {output_file}")

        return report

    def print_summary(self):
        """打印测试摘要。"""
        total = len(self.results)
        passed = sum(1 for r in self.results if r.passed)
        failed = total - passed

        print(f"\n{'='*60}")
        print(f"测试结果: {passed}/{total} 通过 ({passed/max(total,1)*100:.1f}%)")
        print(f"{'='*60}")

        if failed > 0:
            print(f"\n失败的用例:")
            for r in self.results:
                if not r.passed:
                    print(f"  ❌ {r.name}")
                    if r.expected:
                        print(f"     期望: {r.expected}")
                    if r.actual:
                        print(f"     实际: {r.actual[:100]}")


def main():
    parser = argparse.ArgumentParser(description="STM32 串口测试框架")
    parser.add_argument("--port", required=True, help="串口端口（如 COM3）")
    parser.add_argument("--baud", type=int, default=115200, help="波特率")
    parser.add_argument("--test", help="测试用例 JSON 文件")
    parser.add_argument("--send", help="发送单条命令")
    parser.add_argument("--expect", help="期望响应")
    parser.add_argument("--expect-contains", help="期望包含")
    parser.add_argument("--timeout", type=float, default=2.0, help="响应超时（秒）")
    parser.add_argument("--report", metavar="FILE", help="生成报告文件")
    parser.add_argument("--json", action="store_true", help="JSON 格式输出")
    args = parser.parse_args()

    runner = SerialTestRunner(args.port, args.baud, args.timeout)

    if not runner.connect():
        sys.exit(1)

    try:
        if args.test:
            # 运行测试用例文件
            runner.run_tests(args.test)
            runner.print_summary()
            if args.report:
                runner.generate_report(args.report)
            elif args.json:
                report = runner.generate_report()
                print(json.dumps(report, indent=2, ensure_ascii=False))

        elif args.send:
            # 单条测试
            test_case = {
                "name": "单条测试",
                "send": args.send,
                "timeout": args.timeout
            }
            if args.expect:
                test_case["expect"] = args.expect
            elif args.expect_contains:
                test_case["expect_contains"] = args.expect_contains

            result = runner.run_test(test_case)
            runner.results = [result]
            runner.print_summary()

            if args.json:
                print(json.dumps(result.to_dict(), indent=2, ensure_ascii=False))
        else:
            print("❌ 请指定 --test 或 --send")
            sys.exit(1)

    finally:
        runner.disconnect()


if __name__ == "__main__":
    main()
