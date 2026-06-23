#!/usr/bin/env python
"""STM32 错误总结工具。

从编译日志、分析结果、工作流结果中收集错误，生成结构化总结报告。

用法:
  # 从工作流结果总结
  python error_summary.py --workflow workflow_result.json

  # 从编译日志总结
  python error_summary.py --build-log build.log

  # 从多个来源总结
  python error_summary.py --build-log build.log --elf-data check_elf.json --sim-data debug_sim.json

  # 自动模式
  python error_summary.py --auto . --text
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

# 使用共享模块
try:
    from shared import setup_encoding, print_json, print_result, read_json_file, read_text_file
except ImportError:
    def setup_encoding():
        if sys.stdout and hasattr(sys.stdout, "reconfigure"):
            try:
                sys.stdout.reconfigure(encoding="utf-8", errors="replace")
            except Exception:
                pass

    def print_json(data, pretty=True):
        setup_encoding()
        json.dump(data, sys.stdout, indent=2 if pretty else None, ensure_ascii=False)
        print()

    def read_json_file(file_path):
        try:
            return json.loads(Path(file_path).read_text(encoding="utf-8"))
        except:
            return None

    def read_text_file(file_path):
        try:
            return Path(file_path).read_text(encoding="utf-8", errors="replace")
        except:
            return None


# === 错误解析器 ===

def parse_build_log_errors(log_content: str) -> list[dict]:
    """从编译日志中提取错误。

    支持格式:
      file.c(10): error: undefined identifier 'xxx'
      file.c:10:5: error: use of undeclared identifier 'xxx'
      *** ERROR ***: ...
      undefined reference to `xxx'
      multiple definition of `xxx'
      region `xxx' overflowed by N bytes
    """
    errors = []

    # Keil MDK 格式
    keil_pattern = re.compile(
        r'^(.+?)\((\d+)\):\s*(error|warning):\s*(.+)$',
        re.MULTILINE | re.IGNORECASE
    )
    for match in keil_pattern.finditer(log_content):
        errors.append({
            "source": "build",
            "file": match.group(1).strip(),
            "line": int(match.group(2)),
            "severity": match.group(3).lower(),
            "message": match.group(4).strip(),
        })

    # GCC 格式
    gcc_pattern = re.compile(
        r'^(.+?):(\d+):(\d+):\s*(error|warning|fatal error):\s*(.+)$',
        re.MULTILINE | re.IGNORECASE
    )
    for match in gcc_pattern.finditer(log_content):
        file_line = (match.group(1).strip(), int(match.group(2)))
        if not any(e.get("file") == file_line[0] and e.get("line") == file_line[1] for e in errors):
            errors.append({
                "source": "build",
                "file": match.group(1).strip(),
                "line": int(match.group(2)),
                "column": int(match.group(3)),
                "severity": match.group(4).lower(),
                "message": match.group(5).strip(),
            })

    # 链接错误模式
    link_patterns = [
        (re.compile(r'undefined reference to [`\'](.+?)[\'\']', re.IGNORECASE), "linker", "undefined_reference"),
        (re.compile(r'multiple definition of [`\'](.+?)[\'\']', re.IGNORECASE), "linker", "multiple_definition"),
        (re.compile(r'region\s+[`\'"](.+?)[`\'"]\s+overflowed by (\d+) bytes', re.IGNORECASE), "linker", "memory_overflow"),
        (re.compile(r'cannot find -l(\S+)', re.IGNORECASE), "linker", "library_not_found"),
        (re.compile(r'ld returned (\d+) exit status', re.IGNORECASE), "linker", "link_failed"),
    ]

    for pattern, category, error_type in link_patterns:
        for match in pattern.finditer(log_content):
            msg = match.group(0).strip()
            errors.append({
                "source": "build",
                "severity": "error",
                "category": category,
                "error_type": error_type,
                "message": msg,
            })

    # 通用错误模式
    generic_patterns = [
        (re.compile(r'\*\*\*\s*ERROR\s*\*\*\*:\s*(.+)', re.IGNORECASE), "build"),
        (re.compile(r'Error:\s*(.+)', re.IGNORECASE), "build"),
        (re.compile(r'Fatal:\s*(.+)', re.IGNORECASE), "build"),
        (re.compile(r'undeclared identifier [`\'](.+?)[\'\']', re.IGNORECASE), "build"),
        (re.compile(r'expected\s+[`\'"](.+?)[`\'"]\s+before\s+', re.IGNORECASE), "build"),
        (re.compile(r'implicit declaration of function [`\'](.+?)[\'\']', re.IGNORECASE), "build"),
    ]

    for pattern, category in generic_patterns:
        for match in pattern.finditer(log_content):
            msg = match.group(0).strip()
            if not any(msg in e.get("message", "") for e in errors):
                errors.append({
                    "source": "build",
                    "severity": "error" if "Fatal" in msg else "warning",
                    "category": category,
                    "message": msg,
                })

    # 提取编译统计
    stats_pattern = re.compile(r'(\d+)\s+Error\(s\),\s*(\d+)\s+Warning\(s\)', re.IGNORECASE)
    stats_match = stats_pattern.search(log_content)
    if stats_match:
        error_count = int(stats_match.group(1))
        warning_count = int(stats_match.group(2))
        # 添加统计信息作为特殊错误条目
        errors.append({
            "source": "build",
            "severity": "info",
            "category": "statistics",
            "message": f"编译完成: {error_count} 个错误, {warning_count} 个警告",
            "error_count": error_count,
            "warning_count": warning_count,
        })

    return errors


def parse_elf_check_errors(data: dict) -> list[dict]:
    """从 ELF 检查结果中提取错误。"""
    errors = []

    # 检查向量表
    if "vector_table" in data:
        vt = data["vector_table"]
        if not vt.get("valid", True):
            errors.append({
                "source": "elf_check",
                "severity": "error",
                "category": "vector_table",
                "message": "中断向量表无效或缺失",
                "suggestion": "检查启动文件和链接脚本",
            })

    # 检查栈堆
    if "stack_heap" in data:
        sh = data["stack_heap"]
        stack = sh.get("stack_size", 0)
        heap = sh.get("heap_size", 0)

        if stack < 256:
            errors.append({
                "source": "elf_check",
                "severity": "warning",
                "category": "stack",
                "message": f"栈大小过小: {stack} bytes",
                "suggestion": "建议至少 512 bytes，FreeRTOS 项目建议 1024+",
            })
        if heap < 0:
            errors.append({
                "source": "elf_check",
                "severity": "error",
                "category": "heap",
                "message": "堆配置错误（负值）",
                "suggestion": "检查链接脚本中的堆配置",
            })

    # 检查关键符号
    if "symbols" in data:
        symbols = data["symbols"]
        required = ["main", "SystemInit", "__initial_sp"]
        for sym in required:
            if sym not in symbols:
                errors.append({
                    "source": "elf_check",
                    "severity": "warning",
                    "category": "symbol",
                    "message": f"关键符号缺失: {sym}",
                    "suggestion": f"检查 {sym} 是否定义",
                })

    return errors


def parse_sim_errors(data: dict) -> list[dict]:
    """从静态分析结果中提取错误。"""
    errors = []

    # 检查 HardFault
    if "hardfault_analysis" in data:
        hf = data["hardfault_analysis"]
        if hf.get("detected"):
            errors.append({
                "source": "sim",
                "severity": "error",
                "category": "hardfault",
                "message": "检测到 HardFault 风险",
                "details": hf.get("details", ""),
                "suggestion": "检查中断优先级、栈溢出、空指针访问",
            })

    # 检查内存溢出
    if "memory_check" in data:
        mc = data["memory_check"]
        if mc.get("flash_overflow"):
            errors.append({
                "source": "sim",
                "severity": "error",
                "category": "memory",
                "message": f"Flash 溢出: {mc.get('flash_used', 0)} / {mc.get('flash_total', 0)} bytes",
                "suggestion": "优化代码大小或更换更大 Flash 的芯片",
            })
        if mc.get("ram_overflow"):
            errors.append({
                "source": "sim",
                "severity": "error",
                "category": "memory",
                "message": f"RAM 溢出: {mc.get('ram_used', 0)} / {mc.get('ram_total', 0)} bytes",
                "suggestion": "减少全局变量或优化数据结构",
            })

    # 检查向量表问题
    if "vector_table" in data:
        vt = data["vector_table"]
        if not vt.get("valid", True):
            errors.append({
                "source": "sim",
                "severity": "error",
                "category": "vector_table",
                "message": "中断向量表配置错误",
                "suggestion": "检查启动文件和中断处理函数",
            })

    return errors


def parse_renode_errors(data: dict) -> list[dict]:
    """从 Renode 仿真结果中提取错误。"""
    errors = []

    # 检查启动状态
    if data.get("status") == "failed":
        errors.append({
            "source": "renode",
            "severity": "error",
            "category": "boot",
            "message": "固件启动失败",
            "details": data.get("error", ""),
            "suggestion": "检查时钟配置、启动文件、链接脚本",
        })

    # 检查 HardFault
    if data.get("hardfault_detected"):
        errors.append({
            "source": "renode",
            "severity": "error",
            "category": "hardfault",
            "message": "仿真中检测到 HardFault",
            "details": data.get("hardfault_details", ""),
            "suggestion": "检查中断处理、栈溢出、空指针访问",
        })

    # 检查 UART 输出
    if "uart_output" in data:
        uart = data["uart_output"]
        if uart.get("errors"):
            for err in uart["errors"]:
                errors.append({
                    "source": "renode",
                    "severity": "warning",
                    "category": "uart",
                    "message": f"UART 输出异常: {err}",
                })

    # 检查超时
    if data.get("timeout"):
        errors.append({
            "source": "renode",
            "severity": "warning",
            "category": "timeout",
            "message": f"仿真超时 ({data.get('timeout_seconds', '?')}s)",
            "suggestion": "固件可能卡死，检查主循环和中断",
        })

    return errors


def parse_health_check_errors(data: dict) -> list[dict]:
    """从健康检查结果中提取错误。"""
    errors = []

    # 检查缺失文件
    if "missing_files" in data:
        for f in data["missing_files"]:
            errors.append({
                "source": "health",
                "severity": "warning",
                "category": "missing_file",
                "message": f"缺失文件: {f}",
                "suggestion": "检查项目完整性",
            })

    # 检查缺失目录
    if "missing_dirs" in data:
        for d in data["missing_dirs"]:
            errors.append({
                "source": "health",
                "severity": "warning",
                "category": "missing_dir",
                "message": f"缺失目录: {d}",
                "suggestion": "检查项目结构",
            })

    # 检查配置问题
    if "issues" in data:
        for issue in data["issues"]:
            errors.append({
                "source": "health",
                "severity": issue.get("severity", "warning"),
                "category": issue.get("category", "config"),
                "message": issue.get("message", ""),
                "suggestion": issue.get("suggestion", ""),
            })

    return errors


def parse_optimize_warnings(data: dict) -> list[dict]:
    """从优化分析结果中提取警告。"""
    warnings = []

    # 检查大函数
    if "top_functions" in data:
        for func in data["top_functions"][:5]:
            size = func.get("size", 0)
            if size > 1024:
                warnings.append({
                    "source": "optimize",
                    "severity": "warning",
                    "category": "large_function",
                    "message": f"大函数: {func.get('name', 'unknown')} ({size} bytes)",
                    "suggestion": "考虑拆分函数或优化算法",
                })

    # 检查优化级别
    if "compiler_settings" in data:
        cs = data["compiler_settings"]
        opt_level = cs.get("optimization_level", "")
        if opt_level in ("O0", "O1"):
            warnings.append({
                "source": "optimize",
                "severity": "info",
                "category": "optimization",
                "message": f"优化级别较低: {opt_level}",
                "suggestion": "发布版本建议使用 -O2 或 -Os",
            })

    return warnings


# === 错误总结 ===

# 严重程度权重
SEVERITY_WEIGHTS = {
    "error": 10,
    "fatal": 20,
    "warning": 3,
    "info": 1,
}


def calculate_health_score(errors: list[dict]) -> dict:
    """计算项目健康分数。

    分数范围: 0-100
    - 100: 无错误
    - 80-99: 只有警告
    - 60-79: 有少量错误
    - 40-59: 有中等错误
    - 0-39: 有严重错误
    """
    if not errors:
        return {"score": 100, "grade": "A", "status": "优秀"}

    # 计算加权分数
    weighted_sum = 0
    for error in errors:
        severity = error.get("severity", "warning")
        weight = SEVERITY_WEIGHTS.get(severity, 3)
        weighted_sum += weight

    # 计算健康分数（100 - 加权分数，最低 0）
    score = max(0, 100 - weighted_sum)

    # 确定等级
    if score >= 90:
        grade = "A"
        status = "优秀"
    elif score >= 80:
        grade = "B"
        status = "良好"
    elif score >= 70:
        grade = "C"
        status = "一般"
    elif score >= 60:
        grade = "D"
        status = "较差"
    else:
        grade = "F"
        status = "需要修复"

    return {
        "score": score,
        "grade": grade,
        "status": status,
        "weighted_issues": weighted_sum,
    }


def summarize_errors(errors: list[dict]) -> dict:
    """汇总错误统计。"""
    summary = {
        "total": len(errors),
        "by_severity": {},
        "by_source": {},
        "by_category": {},
        "by_file": {},
        "health": calculate_health_score(errors),
    }

    for error in errors:
        severity = error.get("severity", "unknown")
        source = error.get("source", "unknown")
        category = error.get("category", "general")
        file = error.get("file", "unknown")

        summary["by_severity"][severity] = summary["by_severity"].get(severity, 0) + 1
        summary["by_source"][source] = summary["by_source"].get(source, 0) + 1
        summary["by_category"][category] = summary["by_category"].get(category, 0) + 1
        summary["by_file"][file] = summary["by_file"].get(file, 0) + 1

    return summary


def generate_report(errors: list[dict], summary: dict, text_mode: bool = False) -> str:
    """生成错误报告。"""
    if text_mode:
        lines = []
        lines.append("=" * 60)
        lines.append("STM32 错误总结报告")
        lines.append("=" * 60)

        # 健康分数
        health = summary.get("health", {})
        score = health.get("score", 100)
        grade = health.get("grade", "A")
        status = health.get("status", "优秀")
        lines.append(f"\n健康分数: {score}/100 ({grade} - {status})")

        # 统计摘要
        lines.append(f"\n总计: {summary['total']} 个问题")
        for severity, count in summary["by_severity"].items():
            icon = {"error": "❌", "warning": "⚠️", "info": "ℹ️"}.get(severity, "•")
            lines.append(f"  {icon} {severity}: {count}")

        # 按文件分组（如果有文件信息）
        if any(e.get("file") for e in errors):
            lines.append(f"\n{'─' * 60}")
            lines.append("\n按文件分组:")
            # 只显示有文件信息的错误
            file_errors = [e for e in errors if e.get("file")]
            files_with_errors = {}
            for e in file_errors:
                f = e["file"]
                if f not in files_with_errors:
                    files_with_errors[f] = []
                files_with_errors[f].append(e)

            # 按错误数量排序
            for file, file_errs in sorted(files_with_errors.items(), key=lambda x: len(x[1]), reverse=True):
                error_count = len([e for e in file_errs if e.get("severity") == "error"])
                warning_count = len([e for e in file_errs if e.get("severity") == "warning"])
                lines.append(f"\n  {file} ({error_count} 错误, {warning_count} 警告):")
                for i, error in enumerate(file_errs[:5], 1):
                    severity = error.get("severity", "unknown")
                    icon = {"error": "❌", "warning": "⚠️", "info": "ℹ️"}.get(severity, "•")
                    line_num = error.get("line", "")
                    line_str = f":{line_num}" if line_num else ""
                    msg = error.get("message", "")
                    lines.append(f"    {icon} {msg}{line_str}")
                    if "suggestion" in error:
                        lines.append(f"       建议: {error['suggestion']}")
                if len(file_errs) > 5:
                    lines.append(f"    ... 还有 {len(file_errs) - 5} 个问题")

        # 按来源分组
        lines.append(f"\n{'─' * 60}")
        for source, count in summary["by_source"].items():
            lines.append(f"\n[{source}] {count} 个问题:")
            source_errors = [e for e in errors if e.get("source") == source]
            for i, error in enumerate(source_errors[:10], 1):
                severity = error.get("severity", "unknown")
                icon = {"error": "❌", "warning": "⚠️", "info": "ℹ️"}.get(severity, "•")
                msg = error.get("message", "")
                file_info = ""
                if "file" in error:
                    file_info = f" [{error['file']}"
                    if "line" in error:
                        file_info += f":{error['line']}"
                    file_info += "]"
                lines.append(f"  {icon} {i}. {msg}{file_info}")
                if "suggestion" in error:
                    lines.append(f"     建议: {error['suggestion']}")

            if len(source_errors) > 10:
                lines.append(f"  ... 还有 {len(source_errors) - 10} 个问题")

        # 修复建议
        suggestions = [e.get("suggestion") for e in errors if e.get("suggestion")]
        if suggestions:
            lines.append(f"\n{'─' * 60}")
            lines.append("\n修复建议（按优先级排序）:")
            unique_suggestions = list(dict.fromkeys(suggestions))  # 去重保持顺序
            for i, suggestion in enumerate(unique_suggestions[:5], 1):
                lines.append(f"  {i}. {suggestion}")

        return "\n".join(lines)
    else:
        return json.dumps({
            "errors": errors,
            "summary": summary,
        }, indent=2, ensure_ascii=False)


# === CLI ===

def main() -> int:
    parser = argparse.ArgumentParser(
        description="STM32 错误总结工具",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  %(prog)s --build-log build.log                    # 从编译日志总结
  %(prog)s --workflow workflow_result.json          # 从工作流结果总结
  %(prog)s --auto . --text                          # 自动模式，文本输出
  %(prog)s --build-log build.log --sim-data sim.json --text
        """,
    )

    parser.add_argument("--auto", metavar="PROJECT_DIR",
                        help="自动检测项目配置")
    parser.add_argument("--build-log", help="编译日志文件路径")
    parser.add_argument("--workflow", help="工作流结果 JSON 文件")
    parser.add_argument("--elf-data", help="ELF 检查结果 JSON")
    parser.add_argument("--sim-data", help="静态分析结果 JSON")
    parser.add_argument("--optimize-data", help="优化分析结果 JSON")
    parser.add_argument("--text", action="store_true", help="文本格式输出")
    parser.add_argument("--output", help="输出文件路径")

    args = parser.parse_args()

    setup_encoding()

    errors = []

    # 自动模式
    if args.auto:
        project_dir = Path(args.auto).resolve()
        if not args.build_log:
            args.build_log = str(project_dir / "build.log")
        if not args.workflow:
            args.workflow = str(project_dir / "workflow_result.json")

    # 从工作流结果读取
    if args.workflow:
        workflow_data = read_json_file(args.workflow)
        if workflow_data:
            # 提取各步骤的错误
            steps = workflow_data.get("steps", {})
            for step_name, step_data in steps.items():
                if isinstance(step_data, dict):
                    if step_data.get("error"):
                        errors.append({
                            "source": step_name,
                            "severity": "error",
                            "message": step_data["error"],
                        })
                    if "errors" in step_data:
                        errors.extend(step_data["errors"])

    # 从编译日志读取
    if args.build_log:
        log_content = read_text_file(args.build_log)
        if log_content:
            errors.extend(parse_build_log_errors(log_content))
        else:
            print(f"⚠️ 无法读取编译日志: {args.build_log}", file=sys.stderr)

    # 从 ELF 检查结果读取
    if args.elf_data:
        elf_data = read_json_file(args.elf_data)
        if elf_data:
            errors.extend(parse_elf_check_errors(elf_data))

    # 从静态分析结果读取
    if args.sim_data:
        sim_data = read_json_file(args.sim_data)
        if sim_data:
            errors.extend(parse_sim_errors(sim_data))

    # 从优化分析结果读取
    if args.optimize_data:
        opt_data = read_json_file(args.optimize_data)
        if opt_data:
            errors.extend(parse_optimize_warnings(opt_data))

    if not errors:
        print("✅ 未发现错误或警告")
        return 0

    # 去重
    seen = set()
    unique_errors = []
    for error in errors:
        key = (error.get("source", ""), error.get("message", ""))
        if key not in seen:
            seen.add(key)
            unique_errors.append(error)
    errors = unique_errors

    # 生成总结
    summary = summarize_errors(errors)
    report = generate_report(errors, summary, text_mode=args.text)

    if args.text:
        print(report)
    else:
        print(report)

    # 保存到文件
    if args.output:
        Path(args.output).write_text(report, encoding="utf-8")
        print(f"\n报告已保存: {args.output}", file=sys.stderr)

    # 返回码：有错误返回 1
    return 1 if summary["by_severity"].get("error", 0) > 0 else 0


if __name__ == "__main__":
    sys.exit(main())
