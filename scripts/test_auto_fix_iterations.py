#!/usr/bin/env python
"""auto_fix.py 自动化迭代测试

运行 50 次迭代测试，验证 auto_fix.py 的健壮性。

使用示例：
  python test_auto_fix_iterations.py
  python test_auto_fix_iterations.py --iterations 100
"""

from __future__ import annotations

import argparse
import io
import os
import sys
import tempfile
from pathlib import Path
from typing import Any

# 编码处理
if sys.stdout and hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

# 添加父目录到路径
sys.path.insert(0, str(Path(__file__).parent))

from auto_fix import parse_build_log, fix_errors, HEADER_TEMPLATES, SOURCE_TEMPLATES


def create_test_build_log(errors: list[str]) -> str:
    """创建测试用 build.log"""
    lines = []
    for error in errors:
        lines.append(error)
    return "\n".join(lines)


def run_iteration(iteration: int, test_errors: list[str]) -> dict[str, Any]:
    """运行单次迭代"""
    result = {
        "iteration": iteration,
        "input_errors": len(test_errors),
        "fixes": 0,
        "warnings": 0,
        "errors": 0,
        "success": False
    }

    try:
        # 创建临时 build.log
        with tempfile.NamedTemporaryFile(mode='w', suffix='.log', delete=False) as f:
            log_path = f.name
            f.write(create_test_build_log(test_errors))

        # 解析错误
        errors = parse_build_log(log_path)
        result["parsed_errors"] = len(errors)

        # 创建临时项目目录
        with tempfile.TemporaryDirectory() as project_dir:
            # 运行修复
            fixes = fix_errors(errors, project_dir)
            result["fixes"] = len(fixes)

            # 统计结果
            for fix in fixes:
                if fix.get("type") == "warning":
                    result["warnings"] += 1
                elif fix.get("type") == "error":
                    result["errors"] += 1

        result["success"] = True

        # 清理临时文件
        os.unlink(log_path)

    except Exception as e:
        result["error"] = str(e)

    return result


def main() -> int:
    parser = argparse.ArgumentParser(
        description="auto_fix.py 自动化迭代测试",
    )
    parser.add_argument("--iterations", type=int, default=50, help="迭代次数")
    parser.add_argument("--verbose", action="store_true", help="详细输出")

    args = parser.parse_args()

    # 测试用例：各种编译错误模式
    test_errors = [
        # 头文件缺失
        ["'FreeRTOSConfig.h' file not found"],
        ["'balance.h' file not found"],
        ["'vofa.h' file not found"],
        ["'bootloader.h' file not found"],
        ["'pid.h' file not found"],

        # 文件不存在
        ["no such file or directory: '../Core/Src/freertos.c'"],
        ["no such file or directory: '../Board/MPU6050/inv_mpu.c'"],
        ["no such file or directory: '../Board/Balance/balance.c'"],
        ["no such file or directory: '../Board/VOFA/vofa.c'"],
        ["no such file or running: '../Board/Bootloader/bootloader.c'"],

        # 隐式声明
        ["implicit declaration of function 'HAL_Delay'"],
        ["implicit declaration of function 'printf'"],
        ["implicit declaration of function 'memcpy'"],
        ["implicit declaration of function 'strlen'"],
        ["implicit declaration of function 'snprintf'"],

        # 未定义符号
        ["Undefined symbol VOFA_ParseByte"],
        ["Undefined symbol Bootloader_CheckFlag"],
        ["Undefined symbol Balance_Init"],
        ["Undefined symbol Encoder_GetSpeed"],
        ["Undefined symbol Motor_SetPWM"],
    ]

    print("=" * 60)
    print(f"🧪 auto_fix.py 自动化迭代测试 ({args.iterations} 次)")
    print("=" * 60)
    print()

    results = []
    for i in range(args.iterations):
        # 从测试用例中随机选择
        test_idx = i % len(test_errors)
        test_case = test_errors[test_idx]

        result = run_iteration(i + 1, test_case)
        results.append(result)

        if args.verbose:
            status = "✅" if result["success"] else "❌"
            print(f"  {status} 迭代 {i+1}: 输入={result['input_errors']}, 解析={result['parsed_errors']}, 修复={result['fixes']}")

    # 统计结果
    total = len(results)
    success = sum(1 for r in results if r["success"])
    failed = sum(1 for r in results if not r["success"])
    total_fixes = sum(r.get("fixes", 0) for r in results)

    print()
    print("=" * 60)
    print(f"📊 测试结果: {total} 次迭代")
    print(f"   成功: {success}")
    print(f"   失败: {failed}")
    print(f"   总修复数: {total_fixes}")
    print("=" * 60)

    if failed == 0:
        print("✅ 所有迭代测试通过！")
    else:
        print(f"❌ {failed} 次迭代失败")

    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
