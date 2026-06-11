"""自动检测项目配置的共享模块。

提供 auto_detect_config() 函数，供其他脚本调用。
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


def find_detect_config() -> str | None:
    """查找 detect_config.py 脚本路径。"""
    # 同目录下的 detect_config.py
    candidate = Path(__file__).parent / "detect_config.py"
    if candidate.exists():
        return str(candidate)
    return None


def auto_detect_config(project_dir: str) -> dict | None:
    """自动检测项目配置。

    Args:
        project_dir: 项目根目录路径

    Returns:
        配置字典，失败返回 None
    """
    detect_script = find_detect_config()
    if not detect_script:
        return None

    try:
        proc = subprocess.run(
            [sys.executable, detect_script, "--scan", project_dir],
            capture_output=True, text=True, timeout=30,
        )
        if proc.returncode == 0 and proc.stdout.strip():
            config = json.loads(proc.stdout)
            if "error" not in config:
                return config
    except (subprocess.TimeoutExpired, json.JSONDecodeError, FileNotFoundError):
        pass

    return None


def resolve_paths(config: dict, project_dir: str) -> dict:
    """从检测到的配置中解析出常用路径。

    Args:
        config: detect_config.py 返回的配置
        project_dir: 项目根目录

    Returns:
        包含 uv4_path, project_file, elf_path, src_dir, chip 等的字典
    """
    project = Path(project_dir)
    result = {}

    # UV4 路径（从配置推断或查找）
    ide = config.get("ide", "")
    if ide == "keil":
        import shutil
        uv4 = shutil.which("UV4") or shutil.which("UV4.exe")
        if not uv4:
            # 检查常见 Keil 安装路径
            for candidate in [
                "D:/k5/UV4/UV4.exe",
                "C:/Keil_v5/UV4/UV4.exe",
                "C:/Keil/UV4/UV4.exe",
            ]:
                if Path(candidate).exists():
                    uv4 = candidate
                    break
        if uv4:
            result["uv4_path"] = str(Path(uv4).resolve())

    # 项目文件
    if "project_file" in config:
        pf = Path(config["project_file"])
        if not pf.is_absolute():
            pf = project / pf
        result["project_file"] = str(pf)

    # ELF 输出路径（相对于项目文件所在目录）
    output_dir = config.get("output_dir", "")
    output_name = config.get("output_name", "")
    if output_dir and output_name:
        # 项目文件所在目录
        project_file = config.get("project_file", "")
        if project_file:
            pf = Path(project_file)
            if not pf.is_absolute():
                pf = project / pf
            base_dir = pf.parent
        else:
            base_dir = project

        elf_dir = base_dir / output_dir if not Path(output_dir).is_absolute() else Path(output_dir)
        elf_path = elf_dir / f"{output_name}.axf"
        if elf_path.exists():
            result["elf_path"] = str(elf_path)
        else:
            # 尝试其他常见路径
            for candidate in [
                base_dir / f"{output_name}.axf",
                project / "MDK-ARM" / output_dir / f"{output_name}.axf",
                project / "MDK-ARM" / f"{output_name}.axf",
            ]:
                if candidate.exists():
                    result["elf_path"] = str(candidate)
                    break

    # 源码目录
    source_files = config.get("source_files", [])
    if source_files:
        # 从源文件路径推断源码目录
        # 尝试每个源文件，找到第一个 .c 文件
        for src in source_files:
            if not src.endswith((".c", ".C")):
                continue
            first_src = Path(src)
            if not first_src.is_absolute():
                # 相对于项目文件目录
                project_file = config.get("project_file", "")
                if project_file:
                    pf = Path(project_file)
                    if not pf.is_absolute():
                        pf = project / pf
                    first_src = pf.parent / first_src
                else:
                    first_src = project / first_src
            # 向上找到包含 Core/Src 或 Src 的目录
            for parent in first_src.parents:
                if (parent / "Core" / "Src").exists():
                    result["src_dir"] = str(parent / "Core" / "Src")
                    break
                elif (parent / "Src").exists():
                    result["src_dir"] = str(parent / "Src")
                    break
            if "src_dir" in result:
                break

        # 如果还是找不到，尝试常见的目录结构
        if "src_dir" not in result:
            for candidate in [project / "Core" / "Src", project / "Src", project / "src"]:
                if candidate.exists():
                    result["src_dir"] = str(candidate)
                    break

    # Target 名称
    if "target_name" in config:
        result["target"] = config["target_name"]

    # 芯片信息
    if "device" in config:
        result["device"] = config["device"]
    if "chip_info" in config:
        chip = config["chip_info"]
        result["chip"] = config.get("device", "")
        result["flash_kb"] = chip.get("flash_kb", 0)
        result["ram_kb"] = chip.get("ram_kb", 0)
        result["ccm_kb"] = chip.get("ccm_kb", 0)
        result["series"] = chip.get("series", "")

    # 编译器信息
    result["compiler"] = config.get("compiler", "")
    result["optim_level"] = config.get("optim_level", "")
    result["lto_enabled"] = config.get("lto_enabled", False)

    return result


def add_auto_argument(parser) -> None:
    """给 argparse 解析器添加 --auto 参数。"""
    parser.add_argument(
        "--auto",
        metavar="PROJECT_DIR",
        help="自动检测项目配置（指定项目根目录，自动推断 --uv4, --project, --src-dir 等参数）",
    )


def apply_auto_config(args, parser) -> None:
    """应用 --auto 检测到的配置到 args 中（仅填充未指定的参数）。

    Args:
        args: argparse 解析结果
        parser: argparse 解析器（用于检查参数默认值）
    """
    if not hasattr(args, "auto") or not args.auto:
        return

    config = auto_detect_config(args.auto)
    if not config:
        print(f"Warning: Auto-detect failed for {args.auto}", file=sys.stderr)
        return

    paths = resolve_paths(config, args.auto)

    # 仅填充未指定的参数
    if hasattr(args, "uv4") and not args.uv4 and "uv4_path" in paths:
        args.uv4 = paths["uv4_path"]

    if hasattr(args, "project") and not args.project and "project_file" in paths:
        args.project = paths["project_file"]

    if hasattr(args, "elf") and not args.elf and "elf_path" in paths:
        args.elf = paths["elf_path"]

    if hasattr(args, "src_dir") and not args.src_dir and "src_dir" in paths:
        args.src_dir = paths["src_dir"]

    if hasattr(args, "chip") and not args.chip and "chip" in paths:
        args.chip = paths["chip"]

    if hasattr(args, "target") and not args.target and "target" in paths:
        args.target = paths["target"]

    if hasattr(args, "renode") and not args.renode:
        import shutil
        renode = shutil.which("renode")
        if renode:
            args.renode = renode
