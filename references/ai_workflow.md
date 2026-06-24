# AI 工作流指南

> **核心原则**：遇到错误时读错误总结，开发功能时读技术规范。

## 工作流程图

```
┌─────────────────────────────────────────────────────────────┐
│                      AI 工作流                               │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
                    ┌─────────────────┐
                    │  用户请求是什么？ │
                    └────────┬────────┘
                             │
              ┌──────────────┴──────────────┐
              │                             │
              ▼                             ▼
    ┌─────────────────┐           ┌─────────────────┐
    │  遇到错误/bug   │           │  开发新功能     │
    └────────┬────────┘           └────────┬────────┘
             │                             │
             ▼                             ▼
    ┌─────────────────┐           ┌─────────────────┐
    │ 读错误总结文档  │           │ 读技术规范      │
    │ error_summary   │           │ tech_spec       │
    └────────┬────────┘           └────────┬────────┘
             │                             │
             ▼                             ▼
    ┌─────────────────┐           ┌─────────────────┐
    │ 查错误追踪历史  │           │ 检查外设配置    │
    │ error_tracker   │           │ CubeMX 配置     │
    └────────┬────────┘           └────────┬────────┘
             │                             │
             ▼                             ▼
    ┌─────────────────┐           ┌─────────────────┐
    │ 获取修复建议    │           │ 代码适配配置    │
    │ --suggest       │           │ 不修改配置      │
    └────────┬────────┘           └────────┬────────┘
             │                             │
             ▼                             ▼
    ┌─────────────────┐           ┌─────────────────┐
    │ 修复并记录      │           │ 编译测试        │
    │ --record        │           │ workflow.py     │
    └─────────────────┘           └─────────────────┘
```

## 场景 1：遇到编译错误

### 步骤

```bash
# 1. 读错误总结文档
# 阅读 references/error_summary_guide.md，查找相似错误模式

# 2. 查错误追踪历史
python error_tracker.py --search "undefined reference" --text

# 3. 获取修复建议
python error_tracker.py --suggest "undefined reference to 'HAL_GPIO_Init'" --text

# 4. 执行修复
# 根据建议修复代码

# 5. 编译测试
python workflow.py --auto . --steps compile

# 6. 记录修复
python error_tracker.py --record \
  --error "undefined reference to 'HAL_GPIO_Init'" \
  --fix "添加 #include 'stm32f4xx_hal_gpio.h'" \
  --file main.c
```

### 示例对话

```
用户：编译报错 undefined reference to 'HAL_GPIO_Init'

AI：
1. 先查错误总结文档...
2. 查错误追踪历史...
3. 获取修复建议：
   - 在 stm32f4xx_hal_conf.h 中启用 HAL_GPIO_MODULE_ENABLED
   - 或在 CubeMX 中启用 GPIO 外设
4. 修复代码...
5. 编译测试...
6. 记录修复...
```

## 场景 2：开发新功能

### 步骤

```bash
# 1. 读技术规范
python tech_spec.py --auto . --text

# 2. 检查外设配置
# 查看技术规范中的"外设详细配置"章节

# 3. 检查 CubeMX 配置
# 查看技术规范中的"CubeMX 配置指南"章节

# 4. 编写代码
# 代码适配 CubeMX 配置，不修改配置

# 5. 编译测试
python workflow.py --auto . --steps compile,analyze

# 6. 生成报告
python workflow.py --auto . --steps report
```

### 示例对话

```
用户：帮我添加串口通信功能

AI：
1. 先读技术规范...
2. 检查外设配置：
   - USART1: 115200, 8N1
   - 已配置引脚: PA9(TX), PA10(RX)
3. 参考 CubeMX 配置指南...
4. 编写代码（适配 CubeMX 配置）...
5. 编译测试...
6. 生成报告...
```

## 场景 3：配置外设

### 步骤

```bash
# 1. 读技术规范
python tech_spec.py --auto . --text

# 2. 查看 CubeMX 配置指南
python cubemx_guide.py --peripheral USART1

# 3. 检查配置冲突
python pin_checker.py --ioc project.ioc
python clock_validator.py --ioc project.ioc

# 4. 在 CubeMX 中配置
# 打开 project.ioc，配置外设

# 5. 重新生成代码
# 在 CubeMX 中点击 GENERATE CODE

# 6. 编译测试
python workflow.py --auto . --steps compile
```

### 示例对话

```
用户：帮我配置 I2C1

AI：
1. 先读技术规范...
2. 查看 CubeMX 配置指南：
   python cubemx_guide.py --peripheral I2C1
3. 检查配置冲突：
   python pin_checker.py --ioc project.ioc
4. 在 CubeMX 中配置：
   - 打开 project.ioc
   - Connectivity → I2C1
   - 配置 SCL(PB6), SDA(PB7)
   - 配置速度 100kHz
5. 重新生成代码...
6. 编译测试...
```

## 场景 4：调试运行时错误

### 步骤

```bash
# 1. 读错误总结文档
# 阅读 references/error_summary_guide.md

# 2. 查错误追踪历史
python error_tracker.py --search "HardFault" --text

# 3. 获取修复建议
python error_tracker.py --suggest "HardFault" --text

# 4. 检查技术规范
python tech_spec.py --auto . --text

# 5. 检查栈堆配置
# 查看技术规范中的"构建信息"章节

# 6. 运行仿真
python workflow.py --auto . --steps simulate

# 7. 记录修复
python error_tracker.py --record \
  --error "HardFault" \
  --fix "增加栈大小到 1024 bytes" \
  --notes "FreeRTOS 项目"
```

### 示例对话

```
用户：程序运行时 HardFault

AI：
1. 先查错误总结文档...
2. 查错误追踪历史...
3. 获取修复建议：
   - 检查中断优先级
   - 检查栈溢出
   - 检查空指针访问
4. 检查技术规范：
   - 栈大小: 256 bytes（可能太小）
   - 堆大小: 512 bytes
5. 运行仿真...
6. 修复并记录...
```

## 文档读取顺序

### 遇到错误时

```
1. references/error_summary_guide.md  （错误模式库）
2. error_tracker.py --search           （项目错误历史）
3. error_tracker.py --suggest          （修复建议）
4. tech_spec.py                        （检查配置）
```

### 开发功能时

```
1. tech_spec.py                        （技术规范）
2. cubemx_guide.py                     （CubeMX 配置指南）
3. pin_checker.py                      （引脚冲突检测）
4. clock_validator.py                  （时钟配置验证）
```

### 配置外设时

```
1. tech_spec.py                        （当前配置）
2. cubemx_guide.py --peripheral        （外设配置指南）
3. pin_checker.py                      （引脚冲突检测）
4. peripheral_validator.py             （外设配置验证）
```

## 命令速查表

| 场景 | 命令 |
|------|------|
| 查错误历史 | `python error_tracker.py --search "关键词" --text` |
| 获取修复建议 | `python error_tracker.py --suggest "错误信息" --text` |
| 记录修复 | `python error_tracker.py --record --error "xxx" --fix "xxx"` |
| 读技术规范 | `python tech_spec.py --auto . --text` |
| 查 CubeMX 指南 | `python cubemx_guide.py --peripheral USART1` |
| 检查引脚冲突 | `python pin_checker.py --ioc project.ioc` |
| 检查时钟配置 | `python clock_validator.py --ioc project.ioc` |
| 编译测试 | `python workflow.py --auto . --steps compile` |
| 完整分析 | `python workflow.py --auto . --steps compile,analyze,optimize,report` |

## 注意事项

1. **CubeMX 配置为基准**
   - 不修改 CubeMX 生成的代码
   - 代码适配配置，不修改配置
   - 配置错误在 CubeMX 中修改

2. **错误修复后记录**
   - 使用 `error_tracker.py --record` 记录
   - 包含错误信息、修复方法、关联文件
   - 便于未来查找相似错误

3. **开发功能前读技术规范**
   - 检查外设配置
   - 检查引脚分配
   - 检查时钟配置

4. **使用工作流自动化**
   - 使用 `workflow.py` 编译测试
   - 使用 `--steps` 参数控制流程
   - 使用 `report` 步骤生成报告
