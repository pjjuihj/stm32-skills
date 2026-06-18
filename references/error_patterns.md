# STM32 编译错误模式库

## 常见错误类型

### 1. 文件缺失错误

| 错误信息 | 原因 | 修复方法 |
|---------|------|---------|
| `'xxx.h' file not found` | 头文件缺失 | 创建头文件或添加 include 路径 |
| `no such file or directory: 'xxx.c'` | 源文件缺失 | 创建源文件 |
| `cannot open source input file` | 文件路径错误 | 检查文件路径 |

### 2. 类型错误

| 错误信息 | 原因 | 修复方法 |
|---------|------|---------|
| `unknown type name 'xxx'` | 类型未定义 | 添加 typedef 或包含头文件 |
| `use of undeclared identifier` | 标识符未声明 | 添加声明或包含头文件 |
| `incompatible type` | 类型不匹配 | 类型转换或修复签名 |

### 3. 链接错误

| 错误信息 | 原因 | 修复方法 |
|---------|------|---------|
| `undefined reference to 'xxx'` | 函数未定义 | 添加函数实现或链接库 |
| `multiple definition of 'xxx'` | 重复定义 | 添加 static 或 extern |
| `undefined symbol` | 符号未定义 | 检查头文件和源文件 |

### 4. 语法错误

| 错误信息 | 原因 | 修复方法 |
|---------|------|---------|
| `expected ';' before '}'` | 缺少分号 | 添加分号 |
| `expected '}' before end of file` | 缺少大括号 | 添加大括号 |
| `stray '\xxx' in program` | 非法字符 | 删除或替换字符 |

## FreeRTOS 相关错误

### 1. FreeRTOSConfig.h 缺失

```
错误: 'FreeRTOSConfig.h' file not found
修复: 创建 FreeRTOSConfig.h 文件，包含必要的配置宏
```

### 2. 优先级配置错误

```
错误: configUSE_PORT_OPTIMISED_TASK_SELECTION can only be set to 1 when configMAX_PRIORITIES is less than or equal to 32
修复: 将 configMAX_PRIORITIES 设置为 32 或更小
```

### 3. 内存配置错误

```
错误: insufficient memory for heap
修复: 增加 configTOTAL_HEAP_SIZE 或优化内存使用
```

## HAL 相关错误

### 1. HAL 模块未启用

```
错误: 'HAL_xxx_MODULE_ENABLED' not defined
修复: 在 stm32f4xx_hal_conf.h 中启用对应的 HAL 模块
```

### 2. 外设句柄未定义

```
错误: 'xxx_HandleTypeDef' undeclared
修复: 在 main.h 中声明外设句柄
```

### 3. 回调函数未实现

```
错误: undefined reference to 'HAL_xxx_Callback'
修复: 实现回调函数
```

## CubeMX 相关错误

### 1. 代码生成冲突

```
错误: multiple definition of 'MX_xxx_Init'
修复: 检查 USER CODE 区域，避免重复定义
```

### 2. 引脚冲突

```
错误: Pin xx is already configured
修复: 检查引脚配置，避免冲突
```

### 3. 时钟配置错误

```
错误: PLL configuration error
修复: 检查时钟树配置，确保输入时钟和分频系数正确
```

## 自动修复脚本支持的错误

| 错误类型 | 自动修复 | 脚本 |
|---------|---------|------|
| 头文件缺失 | ✅ | auto_fix.py |
| 源文件缺失 | ✅ | auto_fix.py |
| FreeRTOSConfig.h 缺失 | ✅ | auto_fix.py |
| HAL 模块未启用 | ⚠️ | 手动修复 |
| 链接错误 | ❌ | 手动修复 |
