#!/usr/bin/env python
"""STM32 统一工作流编排器。

一键执行编译 → 分析 → 优化 → 仿真 → 烧录 → 验证全流程。
支持自动检测项目配置，编译失败自动修复重编。

用法:
  python workflow.py --auto .                              # 全流程（除烧录）
  python workflow.py --auto . --steps compile              # 只编译
  python workflow.py --auto . --steps compile,analyze      # 编译+分析
  python workflow.py --auto . --steps compile,analyze,flash --port COM3

步骤:
  compile   - 编译项目（失败自动修复，最多 3 轮）
  analyze   - ELF 检查 + 静态分析
  optimize  - 优化建议
  simulate  - Renode 仿真
  flash     - 烧录到硬件（需指定 --port 或确认）
  serial    - 串口验证
  health    - 项目健康检查
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from datetime import datetime
from pathlib import Path

# 脚本目录
SCRIPT_DIR = Path(__file__).parent

# 使用共享模块
from shared import setup_encoding, run_script, parse_json_output, find_uv4

# 编码处理
setup_encoding()


# === 项目检测（使用 auto_detect 模块） ===

def detect_and_resolve(project_dir: str) -> dict:
    """使用 auto_detect 模块检测项目并解析路径。"""
    try:
        from auto_detect import auto_detect_config, resolve_paths
        config = auto_detect_config(project_dir)
        if config:
            return resolve_paths(config, project_dir)
    except ImportError:
        pass
    return {"project_dir": str(Path(project_dir).resolve())}


# === 步骤执行器 ===

def run_compile(paths: dict, max_fix_rounds: int = 3) -> dict:
    """编译项目，失败时自动修复重编。"""
    project_file = paths.get("project_file")
    uv4_path = paths.get("uv4_path")
    target = paths.get("target")

    if not project_file:
        return {
            "success": False,
            "error": "未找到项目文件 (.uvprojx)",
            "suggestion": "请确保目录中有 .uvprojx 文件，或使用 --auto <项目目录>"
        }
    if not uv4_path:
        return {
            "success": False,
            "error": "未找到 UV4.exe",
            "suggestion": "请使用 --uv4 <路径> 指定 UV4.exe，或将 Keil 加入 PATH"
        }

    project_dir = paths["project_dir"]
    build_log = os.path.join(project_dir, "build.log")

    for round_num in range(1, max_fix_rounds + 1):
        print(f"\n{'='*60}")
        print(f"编译第 {round_num} 轮...")
        print(f"{'='*60}")

        # 构建编译命令
        cmd = [uv4_path, "-b", project_file, "-o", build_log, "-j0"]
        if target:
            cmd.extend(["-t", target])

        print(f"  命令: {' '.join(cmd)}")
        print(f"  项目: {project_file}")
        print(f"  Target: {target or '默认'}")

        try:
            proc = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
            returncode = proc.returncode
        except subprocess.TimeoutExpired:
            return {
                "success": False,
                "error": "编译超时（300 秒）",
                "suggestion": "项目可能太大，尝试减少源文件或关闭优化",
                "rounds": round_num
            }
        except FileNotFoundError:
            return {
                "success": False,
                "error": f"UV4.exe 未找到: {uv4_path}",
                "suggestion": "请检查 UV4.exe 路径是否正确",
                "rounds": round_num
            }

        if returncode <= 1:
            print(f"✅ 编译成功（返回码: {returncode}）")
            return {"success": True, "log": build_log, "rounds": round_num, "returncode": returncode}

        print(f"❌ 编译失败（返回码: {returncode}）")

        # 显示编译错误摘要
        if os.path.exists(build_log):
            try:
                with open(build_log, "r", encoding="utf-8", errors="replace") as f:
                    lines = f.readlines()
                error_lines = [l.strip() for l in lines if "error:" in l.lower() or "fatal" in l.lower()]
                if error_lines:
                    print(f"\n  错误摘要（前 5 条）:")
                    for err in error_lines[:5]:
                        print(f"    • {err[:120]}")
            except Exception:
                pass

        if round_num >= max_fix_rounds:
            print(f"\n已达到最大修复轮数 ({max_fix_rounds})")
            return {
                "success": False,
                "log": build_log,
                "rounds": round_num,
                "returncode": returncode,
                "suggestion": "请查看 build.log 了解详细错误信息"
            }

        # 调用 auto_fix.py（使用 --auto 参数）
        print(f"\n尝试自动修复...")
        result = run_script("auto_fix.py", ["--auto", project_dir, "--auto-fix"], timeout=60)
        if result["success"]:
            print(result["stdout"])
        else:
            error_msg = result.get('stderr', result.get('error', ''))
            print(f"⚠️ 自动修复失败: {error_msg[:200]}")
            print(f"  建议: 手动检查 build.log 中的错误")

    return {"success": False, "error": "编译失败", "rounds": max_fix_rounds}


def run_analyze(paths: dict) -> dict:
    """运行 ELF 检查和静态分析。"""
    results = {}
    elf_path = paths.get("elf_path")
    uv4_path = paths.get("uv4_path")

    if not elf_path:
        return {
            "success": False,
            "error": "未找到 ELF/AXF 文件",
            "suggestion": "请先运行编译步骤: workflow.py --auto . --steps compile"
        }

    # check_elf.py
    print(f"\n[1/2] 运行 ELF 检查...")
    print(f"  文件: {elf_path}")
    args = ["--elf", elf_path]
    if uv4_path:
        args.extend(["--uv4", uv4_path])
    r = run_script("check_elf.py", args, timeout=60)
    if r["success"]:
        results["check_elf"] = parse_json_output(r["stdout"]) or {"raw": r["stdout"]}
        print("  ✅ ELF 检查完成")
        # 显示关键信息
        elf_data = results["check_elf"]
        if "size" in elf_data:
            size = elf_data["size"]
            print(f"  Flash: {size.get('text', 0) + size.get('ro_data', 0)} bytes")
            print(f"  RAM: {size.get('data', 0) + size.get('bss', 0)} bytes")
    else:
        error_msg = r.get("stderr", r.get("error", ""))
        results["check_elf"] = {"success": False, "error": error_msg}
        print(f"  ⚠️ ELF 检查失败: {error_msg[:100]}")

    # debug_sim.py
    print(f"\n[2/2] 运行静态分析...")
    args = ["--elf", elf_path, "--mode", "sim"]
    if uv4_path:
        args.extend(["--uv4", uv4_path])
    r = run_script("debug_sim.py", args, timeout=60)
    if r["success"]:
        results["debug_sim"] = parse_json_output(r["stdout"]) or {"raw": r["stdout"]}
        print("  ✅ 静态分析完成")
        # 显示关键信息
        sim_data = results["debug_sim"]
        if "vector_table" in sim_data:
            vt = sim_data["vector_table"]
            if vt.get("valid"):
                print(f"  向量表: 有效")
            else:
                print(f"  向量表: ⚠️ 可能无效")
        if "stack_heap" in sim_data:
            sh = sim_data["stack_heap"]
            print(f"  栈: {sh.get('stack_size', 'N/A')} bytes")
            print(f"  堆: {sh.get('heap_size', 'N/A')} bytes")
    else:
        error_msg = r.get("stderr", r.get("error", ""))
        results["debug_sim"] = {"success": False, "error": error_msg}
        print(f"  ⚠️ 静态分析失败: {error_msg[:100]}")

    return results


def run_optimize(paths: dict) -> dict:
    """运行优化分析。"""
    elf_path = paths.get("elf_path")
    uv4_path = paths.get("uv4_path")
    project_file = paths.get("project_file")
    src_dir = paths.get("src_dir")

    if not elf_path:
        return {
            "success": False,
            "error": "未找到 ELF/AXF 文件",
            "suggestion": "请先运行编译步骤: workflow.py --auto . --steps compile"
        }

    print(f"\n运行优化分析...")
    print(f"  ELF: {elf_path}")
    args = ["--elf", elf_path]
    if uv4_path:
        args.extend(["--uv4", uv4_path])
    if project_file:
        args.extend(["--project", project_file])
    if src_dir:
        args.extend(["--src-dir", src_dir])

    r = run_script("optimize.py", args, timeout=120)
    if r["success"]:
        result = parse_json_output(r["stdout"]) or {"raw": r["stdout"]}
        print("✅ 优化分析完成")
        # 显示关键信息
        if "flash_usage" in result:
            print(f"  Flash 使用率: {result['flash_usage'].get('percent', 'N/A')}%")
        if "ram_usage" in result:
            print(f"  RAM 使用率: {result['ram_usage'].get('percent', 'N/A')}%")
        return result
    else:
        error_msg = r.get("stderr", r.get("error", ""))
        print(f"⚠️ 优化分析失败: {error_msg[:100]}")
        return {
            "success": False,
            "error": error_msg,
            "suggestion": "请检查 ELF 文件是否有效，或尝试重新编译"
        }


def run_simulate(paths: dict, mode: str = "boot", timeout: int = 5) -> dict:
    """运行 Renode 仿真。"""
    elf_path = paths.get("elf_path")
    if not elf_path:
        return {
            "success": False,
            "error": "未找到 ELF/AXF 文件",
            "suggestion": "请先运行编译步骤: workflow.py --auto . --steps compile"
        }

    print(f"\n运行 Renode 仿真 (mode={mode})...")
    print(f"  ELF: {elf_path}")
    args = ["--elf", elf_path, "--mode", mode, "--timeout", str(timeout)]
    r = run_script("renode_sim.py", args, timeout=timeout + 30)
    if r["success"]:
        result = parse_json_output(r["stdout"]) or {"raw": r["stdout"]}
        print("✅ 仿真完成")
        if "boot_success" in result:
            print(f"  启动: {'成功' if result['boot_success'] else '失败'}")
        if "hardfault" in result:
            print(f"  HardFault: {'有' if result['hardfault'] else '无'}")
        return result
    else:
        error_msg = r.get("stderr", r.get("error", ""))
        print(f"⚠️ 仿真失败: {error_msg[:100]}")
        return {
            "success": False,
            "error": error_msg,
            "suggestion": "请检查 Renode 是否安装，或尝试其他仿真模式"
        }


def run_flash(paths: dict, port: str | None = None, firmware: str | None = None) -> dict:
    """烧录到硬件。"""
    project_file = paths.get("project_file")
    uv4_path = paths.get("uv4_path")
    target = paths.get("target")
    elf_path = paths.get("elf_path")

    # 方法 1: ST-LINK 通过 UV4
    if project_file and uv4_path:
        print(f"\n使用 ST-LINK 烧录...")
        flash_log = os.path.join(paths["project_dir"], "flash.log")
        cmd = [uv4_path, "-f", project_file, "-o", flash_log]
        if target:
            cmd.extend(["-t", target])

        try:
            proc = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
            if proc.returncode == 0:
                print("✅ ST-LINK 烧录成功")
                return {"success": True, "method": "st-link", "log": flash_log}
            else:
                print(f"⚠️ ST-LINK 烧录失败（返回码: {proc.returncode}）")
                return {"success": False, "method": "st-link", "error": proc.stderr}
        except subprocess.TimeoutExpired:
            return {"success": False, "method": "st-link", "error": "烧录超时"}

    # 方法 2: USB DFU
    if port and elf_path:
        print(f"\n使用 USB DFU 烧录...")
        firmware_path = firmware or elf_path
        args = ["--full", "--port", port, "--firmware", firmware_path]
        r = run_script("usb_dfu_flash.py", args, timeout=120)
        if r["success"]:
            print("✅ USB DFU 烧录成功")
            return {"success": True, "method": "usb-dfu", "output": r["stdout"]}
        else:
            return {"success": False, "method": "usb-dfu", "error": r.get("stderr", r.get("error", ""))}

    return {"success": False, "error": "无可用烧录方式（需要 ST-LINK 或 USB DFU + COM 端口）"}


def run_health(paths: dict) -> dict:
    """运行项目健康检查。"""
    project_dir = paths.get("project_dir", ".")
    print(f"\n运行项目健康检查...")
    r = run_script("health_check.py", ["--project", project_dir], timeout=30)
    if r["success"]:
        print("✅ 健康检查完成")
        return {"success": True, "output": r["stdout"]}
    else:
        print(f"⚠️ 健康检查发现问题")
        return {"success": False, "output": r["stdout"], "error": r.get("stderr", "")}


def run_serial_check(paths: dict, port: str | None = None, baud: int = 115200,
                     proto: str = "text", duration: float = 10.0,
                     test_commands: list[str] = None) -> dict:
    """运行串口验证。

    Args:
        paths: 项目路径
        port: 串口号
        baud: 波特率
        proto: 协议类型
        duration: 监听时长
        test_commands: 测试命令列表（可选）
    """
    if not port:
        return {"skipped": True, "reason": "未指定 --port"}

    print(f"\n运行串口验证...")
    print(f"  端口: {port}")
    print(f"  波特率: {baud}")
    print(f"  协议: {proto}")
    print(f"  时长: {duration}s")

    result = {
        "success": True,
        "port": port,
        "baud": baud,
        "protocol": proto,
        "duration": duration,
        "tests": [],
        "listen_data": [],
    }

    project_dir = paths.get("project_dir", ".")

    # 步骤 1：发送测试命令（如果有）
    if test_commands:
        print(f"\n  发送测试命令...")
        for i, cmd in enumerate(test_commands, 1):
            print(f"    [{i}/{len(test_commands)}] {cmd}")
            args = [
                "--port", port,
                "--baud", str(baud),
                "--proto", proto,
                "--send", cmd,
                "--recv-timeout", "2",
            ]

            r = run_script("serial_debug.py", args, timeout=10)
            test_result = {
                "command": cmd,
                "success": r["success"],
            }

            if r["success"]:
                # 尝试解析响应
                try:
                    output = r["stdout"]
                    # 提取 [RX] 行
                    rx_lines = [line for line in output.split("\n") if "[RX" in line]
                    if rx_lines:
                        test_result["response"] = rx_lines[0].split("]", 1)[-1].strip()
                except Exception:
                    pass
            else:
                test_result["error"] = r.get("error", "")

            result["tests"].append(test_result)

    # 步骤 2：监听 printf 输出
    print(f"\n  监听 printf 输出 ({duration}s)...")
    listen_file = os.path.join(project_dir, "serial_listen.json")
    args = [
        "--port", port,
        "--baud", str(baud),
        "--proto", "printf",
        "--listen", str(duration),
        "--output", listen_file,
    ]

    r = run_script("serial_debug.py", args, timeout=int(duration) + 10)

    if r["success"]:
        # 读取监听结果
        if os.path.exists(listen_file):
            try:
                with open(listen_file, "r", encoding="utf-8") as f:
                    listen_data = json.load(f)
                    result["listen_data"] = listen_data
                    result["listen_entries"] = len(listen_data) if isinstance(listen_data, list) else 0
            except Exception:
                pass
        print(f"  ✅ 监听完成: {result.get('listen_entries', 0)} 条数据")
    else:
        result["listen_error"] = r.get("error", "")
        print(f"  ⚠️ 监听失败")

    # 步骤 3：保存结果
    result_file = os.path.join(project_dir, "serial_result.json")
    try:
        with open(result_file, "w", encoding="utf-8") as f:
            json.dump(result, f, indent=2, ensure_ascii=False)
        result["result_file"] = result_file
    except Exception:
        pass

    # 总结
    test_passed = sum(1 for t in result["tests"] if t.get("success"))
    test_total = len(result["tests"])
    result["test_summary"] = f"{test_passed}/{test_total} 通过"

    print(f"\n  串口验证完成:")
    print(f"    测试命令: {result['test_summary']}")
    print(f"    监听数据: {result.get('listen_entries', 0)} 条")

    return result


def run_post_analysis(paths: dict, workflow_result: dict) -> dict:
    """运行后置分析（错误总结 + 技术规范）。"""
    results = {}

    # 错误总结
    print(f"\n生成错误总结...")
    result_file = os.path.join(paths.get("project_dir", "."), "workflow_result.json")
    args = ["--workflow", result_file, "--text"]
    r = run_script("error_summary.py", args, timeout=30)
    if r["success"]:
        results["error_summary"] = {"success": True, "output": r["stdout"]}
        print("✅ 错误总结已生成")
    else:
        results["error_summary"] = {"success": False, "error": r.get("error", "")}
        print(f"⚠️ 错误总结生成失败")

    # 技术规范
    print(f"\n生成技术规范...")
    tech_spec_file = os.path.join(paths.get("project_dir", "."), "tech_spec.md")
    args = ["--workflow", result_file, "--output", tech_spec_file, "--text"]
    r = run_script("tech_spec.py", args, timeout=30)
    if r["success"]:
        results["tech_spec"] = {"success": True, "output": tech_spec_file}
        print(f"✅ 技术规范已生成: {tech_spec_file}")
    else:
        results["tech_spec"] = {"success": False, "error": r.get("error", "")}
        print(f"⚠️ 技术规范生成失败")

    return results


# === 主流程 ===

VALID_STEPS = ["compile", "analyze", "optimize", "simulate", "flash", "serial", "health", "report"]

def run_workflow(paths: dict, steps: list[str], port: str | None = None,
                 firmware: str | None = None, max_fix_rounds: int = 3,
                 serial_config: dict = None) -> dict:
    """执行工作流。"""
    results = {
        "project_dir": paths.get("project_dir", ""),
        "device": paths.get("device", ""),
        "steps": {},
        "timestamp": datetime.now().isoformat(),
    }

    # 串口配置
    if serial_config is None:
        serial_config = {}
    baud = serial_config.get("baud", 115200)
    proto = serial_config.get("proto", "text")
    duration = serial_config.get("duration", 10.0)
    test_commands = serial_config.get("test_commands", [])
    batch_file = serial_config.get("batch_file", "")

    for step in steps:
        print(f"\n{'#'*60}")
        print(f"# 步骤: {step}")
        print(f"{'#'*60}")

        if step == "compile":
            result = run_compile(paths, max_fix_rounds)
            results["steps"]["compile"] = result
            if not result["success"]:
                print(f"\n❌ 编译失败，跳过后续步骤")
                break

        elif step == "analyze":
            results["steps"]["analyze"] = run_analyze(paths)

        elif step == "optimize":
            results["steps"]["optimize"] = run_optimize(paths)

        elif step == "simulate":
            results["steps"]["simulate"] = run_simulate(paths)

        elif step == "flash":
            results["steps"]["flash"] = run_flash(paths, port, firmware)

        elif step == "serial":
            # 如果有批量命令文件，读取命令
            if batch_file and os.path.exists(batch_file):
                try:
                    with open(batch_file, "r", encoding="utf-8") as f:
                        batch_commands = [line.strip() for line in f if line.strip() and not line.startswith("#")]
                    test_commands.extend(batch_commands)
                    print(f"  从 {batch_file} 加载了 {len(batch_commands)} 条命令")
                except Exception:
                    pass

            results["steps"]["serial"] = run_serial_check(
                paths, port, baud, proto, duration, test_commands
            )

        elif step == "health":
            results["steps"]["health"] = run_health(paths)

        elif step == "report":
            # 保存当前结果到文件
            result_file = os.path.join(paths.get("project_dir", "."), "workflow_result.json")
            try:
                with open(result_file, "w", encoding="utf-8") as f:
                    json.dump(results, f, indent=2, ensure_ascii=False)
            except OSError:
                pass
            # 运行后置分析
            results["post_analysis"] = run_post_analysis(paths, results)

    return results


# === CLI ===

def main() -> int:
    parser = argparse.ArgumentParser(
        description="STM32 统一工作流编排器",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=f"""
示例:
  %(prog)s --auto .                              # 全流程（编译+分析+优化）
  %(prog)s --auto . --steps compile              # 只编译
  %(prog)s --auto . --steps compile,analyze      # 编译+分析
  %(prog)s --auto . --steps compile,analyze,report  # 编译+分析+报告
  %(prog)s --auto . --steps compile,analyze,flash --port COM3

可用步骤: {', '.join(VALID_STEPS)}

report 步骤会自动运行 error_summary.py 和 tech_spec.py 生成错误总结和技术规范。
        """,
    )

    parser.add_argument("--auto", metavar="PROJECT_DIR",
                        help="自动检测项目配置（指定项目根目录）")
    parser.add_argument("--steps", default="compile,analyze,optimize",
                        help=f"要执行的步骤，逗号分隔 (默认: compile,analyze,optimize)")
    parser.add_argument("--port", help="串口号（烧录用，如 COM3）")
    parser.add_argument("--firmware", help="固件文件路径（烧录用）")
    parser.add_argument("--max-fix-rounds", type=int, default=3,
                        help="编译失败最大修复轮数 (默认: 3)")
    parser.add_argument("--json", action="store_true", help="输出 JSON 格式")

    # 串口配置参数
    parser.add_argument("--serial-baud", type=int, default=115200,
                        help="串口波特率 (默认: 115200)")
    parser.add_argument("--serial-proto", choices=["text", "hex", "printf"], default="text",
                        help="串口协议 (默认: text)")
    parser.add_argument("--serial-duration", type=float, default=10.0,
                        help="串口监听时长/秒 (默认: 10)")
    parser.add_argument("--serial-cmd", help="串口测试命令，逗号分隔")
    parser.add_argument("--serial-batch", help="串口批量命令文件")

    # 手动指定参数（兼容非 --auto 模式）
    parser.add_argument("--uv4", help="UV4.exe 路径")
    parser.add_argument("--project", help="项目文件路径 (.uvprojx)")
    parser.add_argument("--elf", help="ELF/AXF 文件路径")

    args = parser.parse_args()

    if not args.auto and not args.project:
        parser.error("请指定 --auto <项目目录> 或 --project <项目文件>")

    # 解析步骤
    steps = [s.strip() for s in args.steps.split(",")]
    for step in steps:
        if step not in VALID_STEPS:
            parser.error(f"未知步骤: {step}。有效步骤: {', '.join(VALID_STEPS)}")

    # 检测项目
    if args.auto:
        print(f"检测项目: {args.auto}")
        paths = detect_and_resolve(args.auto)
        if not paths.get("project_file"):
            print("⚠️ 未找到项目文件，将使用手动参数")
    else:
        paths = {"project_dir": "."}
        if args.uv4:
            paths["uv4_path"] = args.uv4
        if args.project:
            paths["project_file"] = args.project
        if args.elf:
            paths["elf_path"] = args.elf

    # 打印检测结果
    print(f"\n项目配置:")
    for key, value in paths.items():
        print(f"  {key}: {value}")

    # 串口配置
    serial_config = {
        "baud": args.serial_baud,
        "proto": args.serial_proto,
        "duration": args.serial_duration,
        "test_commands": [],
        "batch_file": args.serial_batch,
    }

    # 解析串口测试命令
    if args.serial_cmd:
        serial_config["test_commands"] = [cmd.strip() for cmd in args.serial_cmd.split(",")]

    # 执行工作流
    results = run_workflow(
        paths, steps,
        port=args.port,
        firmware=args.firmware,
        max_fix_rounds=args.max_fix_rounds,
        serial_config=serial_config,
    )

    # 输出结果
    if args.json:
        json.dump(results, sys.stdout, indent=2, ensure_ascii=False)
        print()
    else:
        print(f"\n{'='*60}")
        print("工作流完成")
        print(f"{'='*60}")
        for step_name, step_result in results["steps"].items():
            if isinstance(step_result, dict):
                if "success" in step_result:
                    status = "✅ 成功" if step_result["success"] else "❌ 失败"
                    print(f"  {step_name}: {status}")
                elif "error" in step_result:
                    print(f"  {step_name}: ⚠️ {step_result['error'][:100]}")
                elif "skipped" in step_result:
                    print(f"  {step_name}: ⏭️ 跳过")
                else:
                    print(f"  {step_name}: ✅ 完成")

    # 保存结果
    result_file = os.path.join(paths.get("project_dir", "."), "workflow_result.json")
    try:
        with open(result_file, "w", encoding="utf-8") as f:
            json.dump(results, f, indent=2, ensure_ascii=False)
        print(f"\n结果已保存到: {result_file}")
    except OSError as e:
        print(f"\n⚠️ 无法保存结果: {e}")

    # 返回码
    for step_result in results["steps"].values():
        if isinstance(step_result, dict) and step_result.get("success") is False:
            return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
