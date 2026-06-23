# STM32 Keil Workflow 技能改进方案

## 目标

解决工作流不顺畅的问题：参数重复输入、编译修复不自动、缺少一键流程。

## 改进内容

### 1. 创建 `workflow.py` — 统一工作流编排器

**位置**: `scripts/workflow.py`

**功能**:
- 自动检测项目配置（调用 `detect_config.py`）
- 编译 → 分析 → 优化 → 烧录 一键执行
- 编译失败 → 自动调用 `auto_fix.py` → 重新编译（最多 3 轮）
- 每步输出自动保存，供下一步使用
- 支持 `--steps` 选择执行哪些步骤

**命令行接口**:
```bash
# 一键全流程（自动检测项目）
python workflow.py --auto .

# 只编译+修复
python workflow.py --auto . --steps compile

# 编译+分析+优化
python workflow.py --auto . --steps compile,analyze,optimize

# 指定烧录端口
python workflow.py --auto . --steps compile,analyze,flash --port COM3

# 跳过编译，只做分析（使用已有的 .axf）
python workflow.py --auto . --steps analyze,optimize
```

**内部流程**:
```
┌─────────────┐
│ auto_detect  │ → 发现 .uvprojx, .axf, .ioc
└──────┬──────┘
       ▼
┌─────────────┐     失败
│   compile   │ ──────────┐
└──────┬──────┘           ▼
       │            ┌───────────┐
       │ 成功       │ auto_fix  │ → 修复 → 重新编译 (最多3轮)
       │            └───────────┘
       ▼
┌─────────────┐
│  check_elf  │ → 检查编译产物
└──────┬──────┘
       ▼
┌─────────────┐
│  debug_sim  │ → 静态分析
└──────┬──────┘
       ▼
┌─────────────┐
│  optimize   │ → 优化建议
└──────┬──────┘
       ▼
┌─────────────┐
│    flash    │ → 烧录（需确认）
└─────────────┘
```

### 2. 为 `auto_fix.py` 和 `serial_monitor.py` 添加 `--auto` 支持

**auto_fix.py**:
- 添加 `--auto` 参数，自动检测项目目录
- 自动查找 build.log（在 MDK-ARM/ 或项目根目录）

**serial_monitor.py**:
- 添加 `--auto` 参数（仅用于自动检测，串口仍需手动指定或自动列出）

### 3. 更新 SKILL.md

**主要改动**:

1. **新增"快速开始"章节** — 放在最前面，展示最简单的用法:
   ```bash
   python workflow.py --auto . --steps compile,analyze
   ```

2. **新增 `--auto` 说明** — 所有脚本都支持 `--auto <项目目录>` 自动检测配置

3. **新增 `workflow.py` 说明** — 一键工作流编排器

4. **精简 CubeMX 配置章节** — 将详细配置移到 `references/cubemx_quick_ref.md`，SKILL.md 只保留常用命令

5. **更新"一行命令"** — 优先展示 `--auto` 用法

6. **更新工具脚本表格** — 添加 `workflow.py` 和 `--auto` 列

**目标行数**: 从 350 行精简到 ~250 行

### 4. 创建 `references/cubemx_quick_ref.md`

将 SKILL.md 中的 CubeMX 详细配置（~100 行）移到这个参考文件中。

## 文件变更清单

| 文件 | 操作 | 说明 |
|------|------|------|
| `scripts/workflow.py` | **新建** | 统一工作流编排器 |
| `scripts/auto_fix.py` | **修改** | 添加 `--auto` 支持 |
| `scripts/serial_monitor.py` | **修改** | 添加 `--auto` 支持 |
| `SKILL.md` | **重写** | 精简 + 添加快速开始 + 添加 workflow.py + 添加 --auto 说明 |
| `references/cubemx_quick_ref.md` | **新建** | CubeMX 详细配置参考 |

## 验证方法

1. 在用户的 STM32 项目目录下运行 `python workflow.py --auto . --steps compile,analyze`
2. 验证自动检测到 .uvprojx、.axf 路径
3. 验证编译失败时自动调用 auto_fix.py
4. 验证分析结果正确输出
