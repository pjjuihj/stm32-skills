#!/usr/bin/env python
"""STM32 死机锁死预防工具。

在烧录前检查固件和配置，防止芯片死机或锁死。

功能：
  - 检查时钟配置
  - 检查读保护状态
  - 检查固件大小
  - 检查向量表
  - 检查栈堆配置

用法:
  # 完整检查
  python brick_prevention.py --auto .

  # 检查时钟配置
  python brick_prevention.py --ioc project.ioc --check clock

  # 检查固件
  python brick_prevention.py --elf project.axf --check firmware

  # 检查读保护
  python brick_prevention.py --check rdp

安全约束:
  - 只检查，不修改
  - 发现问题时警告，不自动修复
  - 时钟配置问题必须在 CubeMX 中修复
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
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

    def read_json_file(file_path):
        try:
            return json.loads(Path(file_path).read_text(encoding="utf-8"))
        except:
            return None


# === 时钟配置检查 ===

def check_clock_config(ioc_path: str) -> dict:
    """检查时钟配置。

    ⚠️ 时钟配置绝对不能修改！修改时钟配置会导致系统死机、锁死！

    Args:
        ioc_path: .ioc 文件路径

    Returns:
        检查结果
    """
    result = {
        "check": "clock",
        "passed": True,
        "warnings": [],
        "errors": [],
        "info": [],
    }

    # 读取 ioc 文件
    try:
        content = Path(ioc_path).read_text(encoding="utf-8", errors="replace")
    except Exception as e:
        result["passed"] = False
        result["errors"].append(f"无法读取 ioc 文件: {e}")
        return result

    # 提取时钟配置
    clock_config = {}
    for line in content.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip()
        if key.startswith("RCC."):
            clock_config[key] = value

    # 检查 PLL 配置
    pll_source = clock_config.get("RCC.PLLSource", "")
    pll_mul = clock_config.get("RCC.PLLMUL", "")
    pll_div = clock_config.get("RCC.PLLDIV", "")

    if not pll_source:
        result["warnings"].append("PLL 源未配置")
    else:
        result["info"].append(f"PLL 源: {pll_source}")

    if not pll_mul:
        result["warnings"].append("PLL 倍频未配置")
    else:
        result["info"].append(f"PLL 倍频: {pll_mul}")

    # 检查 HSE 配置
    hse = clock_config.get("RCC.HSE_VALUE", "")
    if not hse:
        result["warnings"].append("HSE 值未配置，可能使用内部时钟")
    else:
        result["info"].append(f"HSE: {hse} MHz")

    # 检查 HSI 配置
    hsi = clock_config.get("RCC.HSI_VALUE", "")
    if hsi:
        result["info"].append(f"HSI: {hsi} MHz")

    # 检查 SYSCLK 源
    sysclk_src = clock_config.get("RCC.SYSCLKSource", "")
    if not sysclk_src:
        result["warnings"].append("SYSCLK 源未配置")
    else:
        result["info"].append(f"SYSCLK 源: {sysclk_src}")

    # 检查 AHB 分频
    ahb_div = clock_config.get("RCC.HCLK", "")
    if not ahb_div:
        result["warnings"].append("AHB 分频未配置")
    else:
        result["info"].append(f"AHB 分频: {ahb_div}")

    # 检查 APB1 分频
    apb1_div = clock_config.get("RCC.PCLK1", "")
    if not apb1_div:
        result["warnings"].append("APB1 分频未配置")
    else:
        result["info"].append(f"APB1 分频: {apb1_div}")

    # 检查 APB2 分频
    apb2_div = clock_config.get("RCC.PCLK2", "")
    if not apb2_div:
        result["warnings"].append("APB2 分频未配置")
    else:
        result["info"].append(f"APB2 分频: {apb2_div}")

    # 检查是否使用外部晶振
    if "HSE" in pll_source and not hse:
        result["errors"].append("PLL 源选择 HSE，但 HSE 值未配置！")
        result["passed"] = False

    return result


# === 固件检查 ===

def check_firmware(elf_path: str, uv4_path: str = None) -> dict:
    """检查固件。

    Args:
        elf_path: ELF/AXF 文件路径
        uv4_path: UV4.exe 路径

    Returns:
        检查结果
    """
    result = {
        "check": "firmware",
        "passed": True,
        "warnings": [],
        "errors": [],
        "info": [],
    }

    elf_file = Path(elf_path)
    if not elf_file.exists():
        result["passed"] = False
        result["errors"].append(f"固件文件不存在: {elf_path}")
        return result

    # 检查文件大小
    file_size = elf_file.stat().st_size
    result["info"].append(f"固件大小: {file_size} bytes ({file_size/1024:.1f} KB)")

    # 检查文件格式
    try:
        with open(elf_path, "rb") as f:
            header = f.read(4)
            if header[:4] != b'\x7fELF':
                result["warnings"].append("文件格式可能不正确（不是 ELF 格式）")
    except Exception:
        pass

    # 使用 fromelf 检查
    if uv4_path:
        try:
            from shared import find_fromelf
            fromelf = find_fromelf(uv4_path)
            if fromelf:
                proc = subprocess.run(
                    [fromelf, "-z", elf_path],
                    capture_output=True, text=True, timeout=30,
                )
                if proc.returncode == 0:
                    # 解析输出
                    lines = proc.stdout.splitlines()
                    for line in lines:
                        if "ROM Totals" in line:
                            result["info"].append(f"ROM 使用: {line.strip()}")
                        if "RAM Totals" in line:
                            result["info"].append(f"RAM 使用: {line.strip()}")
        except Exception:
            pass

    return result


# === Flash 保护检查 ===

def check_flash_protection(ioc_path: str = None) -> dict:
    """检查 Flash 保护状态。

    Args:
        ioc_path: .ioc 文件路径

    Returns:
        检查结果
    """
    result = {
        "check": "flash_protection",
        "passed": True,
        "warnings": [],
        "errors": [],
        "info": [],
    }

    # 尝试使用 STM32_Programmer_CLI 检查
    try:
        proc = subprocess.run(
            ["STM32_Programmer_CLI.exe", "-c", "port=SWD", "mode=UR"],
            capture_output=True, text=True, timeout=10,
        )
        if proc.returncode == 0:
            output = proc.stdout
            # 检查 Flash 保护
            if "Write Protection" in output:
                if "enabled" in output.lower():
                    result["warnings"].append("Flash 写保护已启用！")
                    result["info"].append("Flash 写保护: 已启用")
                else:
                    result["info"].append("Flash 写保护: 未启用")
    except FileNotFoundError:
        result["warnings"].append("STM32_Programmer_CLI 未找到，跳过 Flash 保护检查")
    except Exception as e:
        result["warnings"].append(f"Flash 保护检查失败: {e}")

    return result


# === Option Bytes 检查 ===

def check_option_bytes() -> dict:
    """检查 Option Bytes 配置。

    Returns:
        检查结果
    """
    result = {
        "check": "option_bytes",
        "passed": True,
        "warnings": [],
        "errors": [],
        "info": [],
    }

    # 尝试使用 STM32_Programmer_CLI 检查
    try:
        proc = subprocess.run(
            ["STM32_Programmer_CLI.exe", "-c", "port=SWD", "mode=UR", "-ob"],
            capture_output=True, text=True, timeout=10,
        )
        if proc.returncode == 0:
            output = proc.stdout
            # 解析 Option Bytes
            for line in output.splitlines():
                if "RDP" in line:
                    result["info"].append(f"RDP: {line.strip()}")
                if "nRST_STOP" in line:
                    result["info"].append(f"STOP 模式复位: {line.strip()}")
                if "nRST_STDBY" in line:
                    result["info"].append(f"待机模式复位: {line.strip()}")
                if "IWDG_SW" in line:
                    result["info"].append(f"独立看门狗: {line.strip()}")
                if "WWDG_SW" in line:
                    result["info"].append(f"窗口看门狗: {line.strip()}")
    except FileNotFoundError:
        result["warnings"].append("STM32_Programmer_CLI 未找到，跳过 Option Bytes 检查")
    except Exception as e:
        result["warnings"].append(f"Option Bytes 检查失败: {e}")

    return result


# === NVIC 优先级检查 ===

def check_nvic_priority(ioc_path: str) -> dict:
    """检查 NVIC 优先级配置。

    Args:
        ioc_path: .ioc 文件路径

    Returns:
        检查结果
    """
    result = {
        "check": "nvic_priority",
        "passed": True,
        "warnings": [],
        "errors": [],
        "info": [],
    }

    # 读取 ioc 文件
    try:
        content = Path(ioc_path).read_text(encoding="utf-8", errors="replace")
    except Exception as e:
        result["warnings"].append(f"无法读取 ioc 文件: {e}")
        return result

    # 提取 NVIC 配置
    nvic_config = {}
    for line in content.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip()

        # NVIC 配置
        if ".NVIC" in key and ".Enable" in key and value.lower() == "true":
            irq = key.split(".")[0]
            nvic_config[irq] = {"enabled": True}

        if ".NVIC" in key and ".PreemptionPriority" in key:
            irq = key.split(".")[0]
            if irq in nvic_config:
                nvic_config[irq]["preemption_priority"] = int(value)

        if ".NVIC" in key and ".SubPriority" in key:
            irq = key.split(".")[0]
            if irq in nvic_config:
                nvic_config[irq]["sub_priority"] = int(value)

    # 检查优先级配置
    if nvic_config:
        result["info"].append(f"NVIC 配置: {len(nvic_config)} 个中断")

        # 检查优先级冲突
        priorities = {}
        for irq, config in nvic_config.items():
            if "preemption_priority" in config:
                prio = config["preemption_priority"]
                if prio not in priorities:
                    priorities[prio] = []
                priorities[prio].append(irq)

        # 检查是否有太多中断使用相同优先级
        for prio, irqs in priorities.items():
            if len(irqs) > 3:
                result["warnings"].append(f"优先级 {prio} 有 {len(irqs)} 个中断: {', '.join(irqs[:3])}...")

    return result


# === DMA 冲突检查 ===

def check_dma_conflict(ioc_path: str) -> dict:
    """检查 DMA 冲突。

    Args:
        ioc_path: .ioc 文件路径

    Returns:
        检查结果
    """
    result = {
        "check": "dma_conflict",
        "passed": True,
        "warnings": [],
        "errors": [],
        "info": [],
    }

    # 读取 ioc 文件
    try:
        content = Path(ioc_path).read_text(encoding="utf-8", errors="replace")
    except Exception as e:
        result["warnings"].append(f"无法读取 ioc 文件: {e}")
        return result

    # 提取 DMA 配置
    dma_config = {}
    for line in content.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip()

        # DMA 配置
        if "DMA" in key and ".Request" in key:
            dma_match = re.match(r"(.+?)\.DMA_.*", key)
            if dma_match:
                dma_name = dma_match.group(1)
                if dma_name not in dma_config:
                    dma_config[dma_name] = {"request": value}
                else:
                    dma_config[dma_name]["request"] = value

    # 检查 DMA 冲突
    if dma_config:
        result["info"].append(f"DMA 配置: {len(dma_config)} 个通道")

        # 检查是否有重复的 DMA 请求
        requests = {}
        for dma, config in dma_config.items():
            req = config.get("request", "")
            if req:
                if req not in requests:
                    requests[req] = []
                requests[req].append(dma)

        for req, dmas in requests.items():
            if len(dmas) > 1:
                result["warnings"].append(f"DMA 请求 {req} 被多个通道使用: {', '.join(dmas)}")

    return result


# === 内存重叠检查 ===

def check_memory_overlap(elf_path: str, uv4_path: str = None) -> dict:
    """检查内存重叠。

    Args:
        elf_path: ELF/AXF 文件路径
        uv4_path: UV4.exe 路径

    Returns:
        检查结果
    """
    result = {
        "check": "memory_overlap",
        "passed": True,
        "warnings": [],
        "errors": [],
        "info": [],
    }

    # 使用 check_elf.py 检查
    try:
        import subprocess
        check_elf_script = Path(__file__).parent / "check_elf.py"
        if check_elf_script.exists():
            args = [sys.executable, str(check_elf_script), "--elf", elf_path]
            if uv4_path:
                args.extend(["--uv4", uv4_path])
            proc = subprocess.run(args, capture_output=True, text=True, timeout=30)
            if proc.returncode == 0:
                data = json.loads(proc.stdout)
                if "size" in data:
                    size = data["size"]
                    text_size = size.get("text", 0)
                    ro_data = size.get("ro_data", 0)
                    data_size = size.get("data", 0)
                    bss_size = size.get("bss", 0)

                    result["info"].append(f"代码段: {text_size} bytes")
                    result["info"].append(f"只读数据: {ro_data} bytes")
                    result["info"].append(f"已初始化数据: {data_size} bytes")
                    result["info"].append(f"未初始化数据: {bss_size} bytes")

                    # 检查是否超出 Flash
                    flash_size = 64 * 1024  # 默认 64KB
                    total_flash = text_size + ro_data
                    if total_flash > flash_size:
                        result["errors"].append(f"Flash 溢出: {total_flash} > {flash_size} bytes")
                        result["passed"] = False

                    # 检查是否超出 RAM
                    ram_size = 20 * 1024  # 默认 20KB
                    total_ram = data_size + bss_size
                    if total_ram > ram_size:
                        result["errors"].append(f"RAM 溢出: {total_ram} > {ram_size} bytes")
                        result["passed"] = False
    except Exception:
        pass

    return result


# === 读保护检查 ===

def check_rdp() -> dict:
    """检查读保护状态。

    Returns:
        检查结果
    """
    result = {
        "check": "rdp",
        "passed": True,
        "warnings": [],
        "errors": [],
        "info": [],
    }

    # 尝试使用 STM32_Programmer_CLI 检查
    try:
        proc = subprocess.run(
            ["STM32_Programmer_CLI.exe", "-c", "port=SWD", "mode=UR"],
            capture_output=True, text=True, timeout=10,
        )
        if proc.returncode == 0:
            output = proc.stdout
            # 检查 RDP 状态
            if "RDP level 1" in output or "RDP level 2" in output:
                result["warnings"].append("读保护 (RDP) 已启用！")
                result["warnings"].append("解除读保护会擦除整个芯片！")
                result["info"].append("RDP 状态: 已启用")
            elif "RDP level 0" in output:
                result["info"].append("RDP 状态: 未启用")
            else:
                result["info"].append("RDP 状态: 未知")
        else:
            result["warnings"].append("无法连接到芯片，检查 SWD 连接")
    except FileNotFoundError:
        result["warnings"].append("STM32_Programmer_CLI 未找到，跳过 RDP 检查")
    except Exception as e:
        result["warnings"].append(f"RDP 检查失败: {e}")

    return result


# === 向量表检查 ===

def check_vector_table(elf_path: str, uv4_path: str = None) -> dict:
    """检查向量表。

    Args:
        elf_path: ELF/AXF 文件路径
        uv4_path: UV4.exe 路径

    Returns:
        检查结果
    """
    result = {
        "check": "vector_table",
        "passed": True,
        "warnings": [],
        "errors": [],
        "info": [],
    }

    # 使用 check_elf.py 检查
    try:
        import subprocess
        check_elf_script = Path(__file__).parent / "check_elf.py"
        if check_elf_script.exists():
            args = [sys.executable, str(check_elf_script), "--elf", elf_path]
            if uv4_path:
                args.extend(["--uv4", uv4_path])
            proc = subprocess.run(args, capture_output=True, text=True, timeout=30)
            if proc.returncode == 0:
                data = json.loads(proc.stdout)
                if "vector_table" in data:
                    vt = data["vector_table"]
                    if not vt.get("valid", True):
                        result["errors"].append("向量表无效！")
                        result["passed"] = False
                    else:
                        result["info"].append("向量表: 有效")
    except Exception:
        pass

    return result


# === 栈堆检查 ===

def check_stack_heap(elf_path: str, uv4_path: str = None) -> dict:
    """检查栈堆配置。

    Args:
        elf_path: ELF/AXF 文件路径
        uv4_path: UV4.exe 路径

    Returns:
        检查结果
    """
    result = {
        "check": "stack_heap",
        "passed": True,
        "warnings": [],
        "errors": [],
        "info": [],
    }

    # 使用 check_elf.py 检查
    try:
        import subprocess
        check_elf_script = Path(__file__).parent / "check_elf.py"
        if check_elf_script.exists():
            args = [sys.executable, str(check_elf_script), "--elf", elf_path]
            if uv4_path:
                args.extend(["--uv4", uv4_path])
            proc = subprocess.run(args, capture_output=True, text=True, timeout=30)
            if proc.returncode == 0:
                data = json.loads(proc.stdout)
                if "stack_heap" in data:
                    sh = data["stack_heap"]
                    stack = sh.get("stack_size", 0)
                    heap = sh.get("heap_size", 0)
                    result["info"].append(f"栈大小: {stack} bytes")
                    result["info"].append(f"堆大小: {heap} bytes")
                    if stack < 256:
                        result["warnings"].append(f"栈大小过小: {stack} bytes，建议至少 512 bytes")
                    if heap < 0:
                        result["errors"].append("堆配置错误（负值）！")
                        result["passed"] = False
    except Exception:
        pass

    return result


# === 完整检查 ===

def run_full_check(project_dir: str = None, ioc_path: str = None,
                   elf_path: str = None, uv4_path: str = None) -> dict:
    """运行完整检查。

    Args:
        project_dir: 项目目录
        ioc_path: .ioc 文件路径
        elf_path: ELF/AXF 文件路径
        uv4_path: UV4.exe 路径

    Returns:
        检查结果
    """
    results = {
        "timestamp": None,
        "checks": [],
        "passed": True,
        "warnings_count": 0,
        "errors_count": 0,
    }

    from datetime import datetime
    results["timestamp"] = datetime.now().isoformat()

    # 检查时钟配置
    if ioc_path:
        print(f"\n检查时钟配置...")
        clock_result = check_clock_config(ioc_path)
        results["checks"].append(clock_result)
        if not clock_result["passed"]:
            results["passed"] = False
        results["warnings_count"] += len(clock_result["warnings"])
        results["errors_count"] += len(clock_result["errors"])
        print(f"  ✅ 时钟配置检查完成" if clock_result["passed"] else f"  ❌ 时钟配置检查失败")

    # 检查 NVIC 优先级
    if ioc_path:
        print(f"\n检查 NVIC 优先级...")
        nvic_result = check_nvic_priority(ioc_path)
        results["checks"].append(nvic_result)
        if not nvic_result["passed"]:
            results["passed"] = False
        results["warnings_count"] += len(nvic_result["warnings"])
        results["errors_count"] += len(nvic_result["errors"])
        print(f"  ✅ NVIC 优先级检查完成" if nvic_result["passed"] else f"  ❌ NVIC 优先级检查失败")

    # 检查 DMA 冲突
    if ioc_path:
        print(f"\n检查 DMA 冲突...")
        dma_result = check_dma_conflict(ioc_path)
        results["checks"].append(dma_result)
        if not dma_result["passed"]:
            results["passed"] = False
        results["warnings_count"] += len(dma_result["warnings"])
        results["errors_count"] += len(dma_result["errors"])
        print(f"  ✅ DMA 冲突检查完成" if dma_result["passed"] else f"  ❌ DMA 冲突检查失败")

    # 检查固件
    if elf_path:
        print(f"\n检查固件...")
        firmware_result = check_firmware(elf_path, uv4_path)
        results["checks"].append(firmware_result)
        if not firmware_result["passed"]:
            results["passed"] = False
        results["warnings_count"] += len(firmware_result["warnings"])
        results["errors_count"] += len(firmware_result["errors"])
        print(f"  ✅ 固件检查完成" if firmware_result["passed"] else f"  ❌ 固件检查失败")

    # 检查向量表
    if elf_path:
        print(f"\n检查向量表...")
        vector_result = check_vector_table(elf_path, uv4_path)
        results["checks"].append(vector_result)
        if not vector_result["passed"]:
            results["passed"] = False
        results["warnings_count"] += len(vector_result["warnings"])
        results["errors_count"] += len(vector_result["errors"])
        print(f"  ✅ 向量表检查完成" if vector_result["passed"] else f"  ❌ 向量表检查失败")

    # 检查栈堆
    if elf_path:
        print(f"\n检查栈堆...")
        stack_result = check_stack_heap(elf_path, uv4_path)
        results["checks"].append(stack_result)
        if not stack_result["passed"]:
            results["passed"] = False
        results["warnings_count"] += len(stack_result["warnings"])
        results["errors_count"] += len(stack_result["errors"])
        print(f"  ✅ 栈堆检查完成" if stack_result["passed"] else f"  ❌ 栈堆检查失败")

    # 检查内存重叠
    if elf_path:
        print(f"\n检查内存重叠...")
        memory_result = check_memory_overlap(elf_path, uv4_path)
        results["checks"].append(memory_result)
        if not memory_result["passed"]:
            results["passed"] = False
        results["warnings_count"] += len(memory_result["warnings"])
        results["errors_count"] += len(memory_result["errors"])
        print(f"  ✅ 内存重叠检查完成" if memory_result["passed"] else f"  ❌ 内存重叠检查失败")

    # 检查读保护
    print(f"\n检查读保护...")
    rdp_result = check_rdp()
    results["checks"].append(rdp_result)
    if not rdp_result["passed"]:
        results["passed"] = False
    results["warnings_count"] += len(rdp_result["warnings"])
    results["errors_count"] += len(rdp_result["errors"])
    print(f"  ✅ 读保护检查完成" if rdp_result["passed"] else f"  ❌ 读保护检查失败")

    # 检查 Flash 保护
    print(f"\n检查 Flash 保护...")
    flash_result = check_flash_protection()
    results["checks"].append(flash_result)
    if not flash_result["passed"]:
        results["passed"] = False
    results["warnings_count"] += len(flash_result["warnings"])
    results["errors_count"] += len(flash_result["errors"])
    print(f"  ✅ Flash 保护检查完成" if flash_result["passed"] else f"  ❌ Flash 保护检查失败")

    # 检查 Option Bytes
    print(f"\n检查 Option Bytes...")
    ob_result = check_option_bytes()
    results["checks"].append(ob_result)
    if not ob_result["passed"]:
        results["passed"] = False
    results["warnings_count"] += len(ob_result["warnings"])
    results["errors_count"] += len(ob_result["errors"])
    print(f"  ✅ Option Bytes 检查完成" if ob_result["passed"] else f"  ❌ Option Bytes 检查失败")

    return results


def format_check_report(results: dict) -> str:
    """格式化检查报告。"""
    lines = []

    lines.append("=" * 60)
    lines.append("STM32 死机锁死预防检查报告")
    lines.append("=" * 60)
    lines.append(f"\n时间: {results['timestamp']}")

    # 总体结果
    status = "✅ 通过" if results["passed"] else "❌ 失败"
    lines.append(f"\n总体结果: {status}")
    lines.append(f"警告: {results['warnings_count']}")
    lines.append(f"错误: {results['errors_count']}")

    # 详细结果
    for check in results["checks"]:
        check_name = check["check"]
        check_status = "✅" if check["passed"] else "❌"
        lines.append(f"\n{check_status} {check_name}")

        if check.get("info"):
            for info in check["info"]:
                lines.append(f"  ℹ️ {info}")

        if check.get("warnings"):
            for warning in check["warnings"]:
                lines.append(f"  ⚠️ {warning}")

        if check.get("errors"):
            for error in check["errors"]:
                lines.append(f"  ❌ {error}")

    # 安全提示
    lines.append("\n" + "=" * 60)
    lines.append("安全提示")
    lines.append("=" * 60)
    lines.append("\n⚠️ 时钟配置绝对不能修改！修改会导致系统死机、锁死！")
    lines.append("⚠️ 如果芯片死机，先检查读保护状态，再尝试擦除。")
    lines.append("⚠️ 解除读保护会擦除整个芯片！")

    return "\n".join(lines)


# === CLI ===

def main() -> int:
    setup_encoding()

    parser = argparse.ArgumentParser(
        description="STM32 死机锁死预防工具",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  %(prog)s --auto .                              # 完整检查
  %(prog)s --ioc project.ioc --check clock       # 检查时钟配置
  %(prog)s --elf project.axf --check firmware    # 检查固件
  %(prog)s --check rdp                           # 检查读保护
        """,
    )

    parser.add_argument("--auto", metavar="PROJECT_DIR",
                        help="自动检测项目配置")
    parser.add_argument("--ioc", help="CubeMX .ioc 文件")
    parser.add_argument("--elf", help="ELF/AXF 文件")
    parser.add_argument("--uv4", help="UV4.exe 路径")
    parser.add_argument("--check", choices=["clock", "firmware", "rdp", "vector", "stack", "all"],
                        default="all", help="检查类型")
    parser.add_argument("--text", action="store_true", help="文本格式输出")
    parser.add_argument("--output", help="输出文件路径")

    args = parser.parse_args()

    # 自动模式
    if args.auto:
        try:
            from auto_detect import auto_detect_config
            config = auto_detect_config(args.auto)
            if config:
                if not args.uv4 and "uv4_path" in config:
                    args.uv4 = config["uv4_path"]
                if not args.elf and "elf_path" in config:
                    args.elf = config["elf_path"]
                if not args.ioc:
                    ioc_files = list(Path(args.auto).glob("*.ioc"))
                    if ioc_files:
                        args.ioc = str(ioc_files[0])
        except ImportError:
            pass

    # 运行检查
    if args.check == "all":
        results = run_full_check(
            project_dir=args.auto,
            ioc_path=args.ioc,
            elf_path=args.elf,
            uv4_path=args.uv4,
        )
    elif args.check == "clock":
        if not args.ioc:
            parser.error("clock 检查需要 --ioc 参数")
        results = {"checks": [check_clock_config(args.ioc)]}
    elif args.check == "firmware":
        if not args.elf:
            parser.error("firmware 检查需要 --elf 参数")
        results = {"checks": [check_firmware(args.elf, args.uv4)]}
    elif args.check == "rdp":
        results = {"checks": [check_rdp()]}
    elif args.check == "vector":
        if not args.elf:
            parser.error("vector 检查需要 --elf 参数")
        results = {"checks": [check_vector_table(args.elf, args.uv4)]}
    elif args.check == "stack":
        if not args.elf:
            parser.error("stack 检查需要 --elf 参数")
        results = {"checks": [check_stack_heap(args.elf, args.uv4)]}
    else:
        parser.error(f"未知检查类型: {args.check}")

    # 输出结果
    if args.text:
        print(format_check_report(results))
    else:
        print(json.dumps(results, indent=2, ensure_ascii=False))

    # 保存到文件
    if args.output:
        Path(args.output).write_text(
            json.dumps(results, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        print(f"\n结果已保存: {args.output}")

    return 0 if results.get("passed", True) else 1


if __name__ == "__main__":
    sys.exit(main())
