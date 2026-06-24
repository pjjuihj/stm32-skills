# 错误总结工具使用指南

> **维护约定**：每次解决错误/bug 时，更新本文档的错误模式库和修复建议。

## AI 工作流

### 遇到错误时

```bash
# 1. 先查错误总结文档
# 阅读本文档，查找相似错误模式

# 2. 查错误追踪历史
python error_tracker.py --search "错误关键词" --text

# 3. 获取修复建议
python error_tracker.py --suggest "错误信息" --text

# 4. 修复后记录
python error_tracker.py --record --error "xxx" --fix "xxx" --file main.c
```

### 开发功能时

```bash
# 1. 先读技术规范
python tech_spec.py --auto . --text

# 2. 检查外设配置
# 查看技术规范中的"外设详细配置"章节

# 3. 遵循 CubeMX 配置
# 代码适配配置，不修改配置
```

## 更新日志

| 日期 | 错误类型 | 修复方法 | 关联文件 |
|------|---------|---------|---------|
| 2026-06-23 | 编译日志解析不全 | 新增链接错误模式（undefined reference、multiple definition、region overflow） | error_summary.py |
| 2026-06-23 | 串口乱码 | 波特率不匹配，检查实际固件配置 | serial_debug.py |
| 2026-06-23 | workflow.py 重复代码 | 提取 shared.py 共享模块 | shared.py |

## 概述

`error_summary.py` 是一个综合错误分析工具，用于汇总和分析 STM32 项目中的各种错误。

## 功能特性

- **健康分数**：0-100 分，A-F 等级
- **错误分类**：按严重程度和来源分类
- **文件分组**：按文件路径分组显示错误
- **修复建议**：按优先级排序的修复建议
- **多来源支持**：编译、ELF、仿真、优化、健康检查

## 使用方法

### 基本用法

```bash
# 分析工作流结果
python error_summary.py --workflow workflow_result.json

# 文本格式输出
python error_summary.py --workflow workflow_result.json --text

# 自动检测项目
python error_summary.py --auto . --text

# 指定编译日志
python error_summary.py --log build.log --text

# 指定 ELF 检查结果
python error_summary.py --elf check_elf.json --text
```

### 参数说明

| 参数 | 说明 | 示例 |
|------|------|------|
| `--workflow` | 工作流结果 JSON 文件 | `--workflow workflow_result.json` |
| `--auto` | 自动检测项目配置 | `--auto .` |
| `--log` | 编译日志文件 | `--log build.log` |
| `--elf` | ELF 检查结果 JSON | `--elf check_elf.json` |
| `--sim` | 静态分析结果 JSON | `--sim debug_sim.json` |
| `--optimize` | 优化分析结果 JSON | `--optimize optimize.json` |
| `--health` | 健康检查结果 JSON | `--health health.json` |
| `--text` | 文本格式输出 | `--text` |
| `--output` | 输出文件路径 | `--output report.json` |

## 输出格式

### JSON 格式

```json
{
  "timestamp": "2026-06-23T22:34:41.163143",
  "summary": {
    "total_errors": 0,
    "total_warnings": 0,
    "error_files": 0,
    "health_score": 100,
    "health_grade": "A",
    "by_source": {},
    "by_severity": {}
  },
  "errors": [],
  "grouped_errors": {},
  "fix_suggestions": []
}
```

### 文本格式

```
============================================================
STM32 错误总结报告
============================================================
时间: 2026-06-23T22:34:41.163143

健康分数: 100/100 (A)
错误总数: 0
警告总数: 0
错误文件: 0 个

✅ 恭喜！没有发现任何错误。

============================================================
```

## 健康分数计算

| 分数 | 等级 | 说明 |
|------|------|------|
| 90-100 | A | 优秀，无错误或极少警告 |
| 80-89 | B | 良好，有少量警告 |
| 70-79 | C | 一般，有警告需要关注 |
| 60-69 | D | 较差，有错误需要修复 |
| 0-59 | F | 严重，有严重错误 |

## 错误来源

| 来源 | 说明 | 权重 |
|------|------|------|
| `build` | 编译错误 | 10 |
| `elf_check` | ELF 检查错误 | 8 |
| `sim` | 静态分析错误 | 7 |
| `optimize` | 优化警告 | 3 |
| `health` | 健康检查警告 | 2 |
| `renode` | 仿真错误 | 6 |

## 错误严重程度

| 严重程度 | 权重 | 说明 |
|---------|------|------|
| `error` | 10 | 错误，必须修复 |
| `warning` | 3 | 警告，建议修复 |
| `info` | 0 | 信息，仅供参考 |

## 修复建议

工具会根据错误类型自动生成修复建议，按优先级排序：

1. **编译错误**（优先级 1-5）
   - 头文件缺失
   - 未定义标识符
   - 链接错误

2. **ELF 检查错误**（优先级 1-4）
   - 向量表无效
   - 栈/堆配置错误
   - 关键符号缺失

3. **静态分析错误**（优先级 2-5）
   - HardFault 风险
   - 内存溢出

4. **优化警告**（优先级 6-8）
   - 大函数
   - 低优化级别

## 集成工作流

### 在 workflow.py 中使用

```bash
# 完整流程（包含错误总结）
python workflow.py --auto . --steps compile,analyze,optimize,report

# 只运行错误总结
python workflow.py --auto . --steps report
```

### 单独使用

```bash
# 分析已有的工作流结果
python error_summary.py --workflow workflow_result.json --text

# 分析编译日志
python error_summary.py --log build.log --text

# 分析多个数据源
python error_summary.py --elf check_elf.json --sim debug_sim.json --text
```

## 示例

### 示例 1：无错误项目

```
健康分数: 100/100 (A)
错误总数: 0
警告总数: 0

✅ 恭喜！没有发现任何错误。
```

### 示例 2：有编译错误

```
健康分数: 45/100 (F)
错误总数: 3
警告总数: 1

按文件分组:
  main.c:
    [error] main.c(10): undeclared identifier 'LED_PIN'
    [error] main.c(15): undefined reference to 'HAL_GPIO_Init'

修复建议:
  1. [P1] 编译错误: 添加缺失的头文件或声明
     文件: main.c
     命令: python auto_fix.py --log build.log --auto-fix
```

### 示例 3：有警告

```
健康分数: 85/100 (B)
错误总数: 0
警告总数: 2

按文件分组:
  system.c:
    [warning] system.c(50): 栈大小过小: 256 bytes
    [warning] system.c(100): 大函数: process_data (1500 bytes)

修复建议:
  1. [P6] 栈大小过小: 增加栈大小到 512+ bytes
  2. [P7] 大函数: 考虑拆分函数或优化算法
```

## 最佳实践

1. **定期运行**：每次编译后运行错误总结
2. **关注健康分数**：保持在 80 分以上
3. **修复高优先级错误**：先修复 P1-P3 的错误
4. **记录修复历史**：保存错误总结报告用于对比

## 故障排除

### 问题：无法读取工作流结果

```
错误: 工作流结果文件不存在
解决: 先运行 workflow.py 生成结果文件
```

### 问题：错误解析失败

```
错误: JSON 解析失败
解决: 检查 JSON 文件格式是否正确
```

### 问题：健康分数异常

```
原因: 错误权重配置不当
解决: 检查错误来源和严重程度是否正确
```
