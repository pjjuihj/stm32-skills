# 常见问题排查

## 编译问题

### UV4.exe 找不到
- 检查 Keil 安装路径（通常 `C:\Keil_v5\UV4\UV4.exe` 或 `D:\k5\UV4\UV4.exe`）
- 运行 `where UV4.exe` 或在注册表中查找

### 编译报错 `portmacro.h not found`
- FreeRTOS 使用了 RVDS port，ARMClang 不支持
- 解决：将 `portable/RVDS/ARM_CM4F` 替换为 `portable/GCC/ARM_CM4F`

### 编译报错 `undefined reference`
- 检查头文件是否包含
- 检查函数是否声明
- 检查库是否链接（.uvprojx 中的 Groups）

### 编译报错 `multiple definition`
- 全局变量在多个 .c 文件中定义
- 解决：改为 `extern` 声明或加 `static`

## 烧录问题

### ST-LINK 连接失败
1. 检查是否有其他程序占用（STM32CubeIDE、CubeProgrammer、OpenOCD）
2. 检查 USB 连接和目标板供电
3. 尝试不同连接模式：`UR` → `HotPlug` → `NORMAL`
4. 检查 SWD 频率（降低到 1000 kHz）

### 烧录报错 `No ST-LINK detected`
- 检查 USB 线是否支持数据传输（非充电线）
- 检查 ST-LINK 驱动是否安装
- 尝试更换 USB 端口

## 仿真问题

### Renode 启动超时
- 检查端口是否被占用（Renode 默认用 1234 端口）
- 使用 `--port 0` 让 Renode 自动选择端口
- 检查 ELF 文件是否正确

### Renode 仿真中 IWDG 复位
- 仿真速度慢于实时，看门狗会提前触发
- 这是正常现象，不影响启动验证结果

## 串口问题

### 串口无数据
- 检查 COM 号是否正确（`--list` 列出可用串口）
- 检查波特率是否匹配
- 检查 TX/RX 接线是否正确（交叉连接）
- 检查固件是否正常启动

### 串口数据乱码
- 波特率不匹配
- 检查数据位/停止位/校验位配置
- 检查电平是否匹配（3.3V vs 5V）

## 优化分析问题

### fromelf 找不到
- 使用 `--uv4` 参数指定 UV4.exe 路径
- fromelf 位于 `<Keil>/ARM/ARMCLANG/bin/fromelf.exe`

### cppcheck 未安装
- 下载：https://cppcheck.sourceforge.io/
- 或使用包管理器：`winget install cppcheck`
- 安装后确保在 PATH 中
