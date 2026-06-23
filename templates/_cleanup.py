import os
import glob

# 保留的代表模板
KEEP = {
    # PWM/舵机
    "pwm_servo_smooth", "pwm_servo_pid", "pwm_servo_position", "pwm_servo_speed",
    "pwm_servo_encoder", "pwm_servo_multi",
    # 传感器
    "dht11_sensor", "bmp280_sensor", "mpu6050_sensor", "ds18b20_sensor",
    "hcsr04_ultrasonic", "light_sensor", "soil_moisture",
    # 通信
    "uart_comm", "i2c_sensor", "can_bus", "bluetooth_comm",
    "rs485_modbus", "protocol_parser",
    # 显示
    "oled_display", "tft_st7735", "lcd1602_i2c", "led_matrix",
    # 电机
    "pwm_motor", "stepper_motor", "encoder_motor", "dc_motor_hbridge",
    # 无线
    "nrf24l01_wireless", "lora_sx1278", "wifi_esp8266",
    # 其他
    "freertos_basic", "scope_siggen", "usb_cdc", "basic_gpio",
    "adc_dma", "pid_controller", "sd_card",
}

# 获取所有 JSON 模板
all_templates = set()
for f in glob.glob("*.json"):
    all_templates.add(f.replace(".json", ""))

# 计算要删除的
to_delete = all_templates - KEEP

print(f"总模板数: {len(all_templates)}")
print(f"保留: {len(KEEP)}")
print(f"删除: {len(to_delete)}")

# 删除
deleted = 0
for name in sorted(to_delete):
    filename = f"{name}.json"
    if os.path.exists(filename):
        os.remove(filename)
        deleted += 1

print(f"已删除: {deleted} 个文件")

# 列出保留的
print("\n保留的模板:")
for name in sorted(KEEP):
    if os.path.exists(f"{name}.json"):
        print(f"  ✓ {name}.json")
    else:
        print(f"  ✗ {name}.json (不存在)")
