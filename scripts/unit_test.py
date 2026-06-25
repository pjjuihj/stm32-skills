#!/usr/bin/env python
"""STM32 单元测试框架。

在 PC 上运行嵌入式代码的单元测试（mock HAL），输出 xUnit 格式报告。

用法:
  python unit_test.py --auto . --generate                     # 生成测试模板
  python unit_test.py --auto . --run                          # 运行测试
  python unit_test.py --auto . --run --report result.xml      # 生成 xUnit 报告

测试文件格式（test_xxx.c）:
  #include "test_framework.h"
  #include "my_module.h"

  void test_adc_init(void) {
      TEST_ASSERT_EQUAL(0, adc_init());
  }

  void test_adc_read(void) {
      int value = adc_read();
      TEST_ASSERT_GREATER_OR_EQUAL(0, value);
      TEST_ASSERT_LESS_OR_EQUAL(4095, value);
  }

  int main(void) {
      RUN_TEST(test_adc_init);
      RUN_TEST(test_adc_read);
      return TEST_REPORT();
  }
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import xml.etree.ElementTree as ET
from datetime import datetime
from pathlib import Path

SCRIPT_DIR = Path(__file__).parent
from shared import setup_encoding
setup_encoding()


# 测试框架头文件模板
TEST_FRAMEWORK_H = '''\
#ifndef TEST_FRAMEWORK_H
#define TEST_FRAMEWORK_H

#include <stdio.h>
#include <stdlib.h>
#include <string.h>

static int _test_pass = 0;
static int _test_fail = 0;
static int _test_total = 0;
static const char *_current_test = NULL;

#define TEST_ASSERT_EQUAL(expected, actual) do { \\
    _test_total++; \\
    if ((expected) == (actual)) { \\
        _test_pass++; \\
    } else { \\
        _test_fail++; \\
        printf("  FAIL: %s:%d: expected %d, got %d\\n", __FILE__, __LINE__, (int)(expected), (int)(actual)); \\
    } \\
} while(0)

#define TEST_ASSERT_NOT_EQUAL(expected, actual) do { \\
    _test_total++; \\
    if ((expected) != (actual)) { \\
        _test_pass++; \\
    } else { \\
        _test_fail++; \\
        printf("  FAIL: %s:%d: expected not %d\\n", __FILE__, __LINE__, (int)(expected)); \\
    } \\
} while(0)

#define TEST_ASSERT_GREATER_OR_EQUAL(threshold, actual) do { \\
    _test_total++; \\
    if ((actual) >= (threshold)) { \\
        _test_pass++; \\
    } else { \\
        _test_fail++; \\
        printf("  FAIL: %s:%d: %d < %d\\n", __FILE__, __LINE__, (int)(actual), (int)(threshold)); \\
    } \\
} while(0)

#define TEST_ASSERT_LESS_OR_EQUAL(threshold, actual) do { \\
    _test_total++; \\
    if ((actual) <= (threshold)) { \\
        _test_pass++; \\
    } else { \\
        _test_fail++; \\
        printf("  FAIL: %s:%d: %d > %d\\n", __FILE__, __LINE__, (int)(actual), (int)(threshold)); \\
    } \\
} while(0)

#define TEST_ASSERT_TRUE(condition) do { \\
    _test_total++; \\
    if (condition) { \\
        _test_pass++; \\
    } else { \\
        _test_fail++; \\
        printf("  FAIL: %s:%d: condition is false\\n", __FILE__, __LINE__); \\
    } \\
} while(0)

#define TEST_ASSERT_FALSE(condition) do { \\
    _test_total++; \\
    if (!(condition)) { \\
        _test_pass++; \\
    } else { \\
        _test_fail++; \\
        printf("  FAIL: %s:%d: condition is true\\n", __FILE__, __LINE__); \\
    } \\
} while(0)

#define TEST_ASSERT_NULL(ptr) TEST_ASSERT_EQUAL(NULL, (void*)(ptr))
#define TEST_ASSERT_NOT_NULL(ptr) TEST_ASSERT_NOT_EQUAL(NULL, (void*)(ptr))

#define TEST_ASSERT_EQUAL_STRING(expected, actual) do { \\
    _test_total++; \\
    if (strcmp((expected), (actual)) == 0) { \\
        _test_pass++; \\
    } else { \\
        _test_fail++; \\
        printf("  FAIL: %s:%d: expected \\"%s\\", got \\"%s\\"\\n", __FILE__, __LINE__, (expected), (actual)); \\
    } \\
} while(0)

#define RUN_TEST(func) do { \\
    _current_test = #func; \\
    printf("  %s... ", _current_test); \\
    func(); \\
    printf("PASS\\n"); \\
} while(0)

#define TEST_REPORT() ({ \\
    printf("\\n========================================\\n"); \\
    printf("Tests: %d  Passed: %d  Failed: %d\\n", _test_total, _test_pass, _test_fail); \\
    printf("========================================\\n"); \\
    (_test_fail > 0) ? 1 : 0; \\
})

#endif /* TEST_FRAMEWORK_H */
'''

# HAL mock 头文件模板
HAL_MOCK_H = '''\
#ifndef HAL_MOCK_H
#define HAL_MOCK_H

#include <stdint.h>

/* Mock HAL types */
typedef struct { uint32_t CR; uint32_t NDTR; uint32_t PAR; uint32_t M0AR; } DMA_Stream_TypeDef;
typedef struct { uint32_t SR; uint32_t DR; uint32_t BRR; uint32_t CR1; } USART_TypeDef;
typedef struct { uint32_t CR1; uint32_t CR2; uint32_t SMCR; uint32_t ARR; uint32_t PSC; uint32_t CNT; } TIM_TypeDef;
typedef struct { uint32_t SR; uint32_t CR1; uint32_t CR2; } ADC_TypeDef;
typedef struct { uint32_t MODER; uint32_t ODR; uint32_t IDR; } GPIO_TypeDef;
typedef uint32_t HAL_StatusTypeDef;

#define HAL_OK 0
#define HAL_ERROR 1
#define HAL_BUSY 2

/* Mock HAL functions */
static inline HAL_StatusTypeDef HAL_UART_Transmit(void *h, uint8_t *d, uint16_t s, uint32_t t) { return HAL_OK; }
static inline HAL_StatusTypeDef HAL_UART_Receive(void *h, uint8_t *d, uint16_t s, uint32_t t) { return HAL_OK; }
static inline HAL_StatusTypeDef HAL_ADC_Start(void *h) { return HAL_OK; }
static inline HAL_StatusTypeDef HAL_ADC_Start_DMA(void *h, uint32_t *b, uint32_t l) { return HAL_OK; }
static inline HAL_StatusTypeDef HAL_DAC_Start(void *h, uint32_t c) { return HAL_OK; }
static inline HAL_StatusTypeDef HAL_DAC_Start_DMA(void *h, uint32_t c, uint32_t *d, uint32_t l, uint32_t a) { return HAL_OK; }
static inline void HAL_GPIO_WritePin(GPIO_TypeDef *g, uint32_t p, uint32_t s) {}
static inline uint32_t HAL_GPIO_ReadPin(GPIO_TypeDef *g, uint32_t p) { return 0; }
static inline void HAL_Delay(uint32_t d) {}
static inline uint32_t HAL_RCC_GetSysClockFreq(void) { return 168000000; }

/* Mock registers */
static DMA_TypeDef mock_dma1, mock_dma2;
static USART_TypeDef mock_usart1, mock_usart2;
static TIM_TypeDef mock_tim1, mock_tim2, mock_tim5, mock_tim8;
static ADC_TypeDef mock_adc1;
static GPIO_TypeDef mock_gpioa, mock_gpiob;

#define DMA1_Stream0 ((DMA_Stream_TypeDef*)&mock_dma1)
#define DMA1_Stream5 ((DMA_Stream_TypeDef*)&mock_dma1)
#define DMA2_Stream0 ((DMA_Stream_TypeDef*)&mock_dma2)
#define USART1 ((USART_TypeDef*)&mock_usart1)
#define USART2 ((USART_TypeDef*)&mock_usart2)
#define TIM1 ((TIM_TypeDef*)&mock_tim1)
#define TIM2 ((TIM_TypeDef*)&mock_tim2)
#define TIM5 ((TIM_TypeDef*)&mock_tim5)
#define TIM8 ((TIM_TypeDef*)&mock_tim8)
#define ADC1 ((ADC_TypeDef*)&mock_adc1)
#define GPIOA ((GPIO_TypeDef*)&mock_gpioa)
#define GPIOB ((GPIO_TypeDef*)&mock_gpiob)

#endif /* HAL_MOCK_H */
'''

# CMakeLists.txt 模板
CMAKE_TEMPLATE = '''\
cmake_minimum_required(VERSION 3.10)
project(stm32_unit_tests C)

set(CMAKE_C_STANDARD 11)

# 包含路径
include_directories(${CMAKE_SOURCE_DIR}/test)
include_directories(${CMAKE_SOURCE_DIR}/Core/Inc)

# 收集测试文件
file(GLOB TEST_SOURCES test/test_*.c)

# 编译测试
foreach(test_file ${TEST_SOURCES})
    get_filename_component(test_name ${test_file} NAME_WE)
    add_executable(${test_name} ${test_file})
    add_test(NAME ${test_name} COMMAND ${test_name})
endforeach()
'''


def generate_template(project_dir: str) -> dict:
    """生成测试框架模板。"""
    test_dir = os.path.join(project_dir, "test")
    os.makedirs(test_dir, exist_ok=True)

    # 写入测试框架头文件
    with open(os.path.join(test_dir, "test_framework.h"), "w") as f:
        f.write(TEST_FRAMEWORK_H)

    # 写入 HAL mock
    with open(os.path.join(test_dir, "hal_mock.h"), "w") as f:
        f.write(HAL_MOCK_H)

    # 写入示例测试
    example_test = '''\
#include "test_framework.h"
#include "hal_mock.h"

/* 被测函数（替换为你的实际函数） */
int adc_init(void) { return 0; }
int adc_read(void) { return 2048; }

void test_adc_init(void) {
    TEST_ASSERT_EQUAL(0, adc_init());
}

void test_adc_read_range(void) {
    int value = adc_read();
    TEST_ASSERT_GREATER_OR_EQUAL(0, value);
    TEST_ASSERT_LESS_OR_EQUAL(4095, value);
}

int main(void) {
    RUN_TEST(test_adc_init);
    RUN_TEST(test_adc_read_range);
    return TEST_REPORT();
}
'''
    with open(os.path.join(test_dir, "test_example.c"), "w") as f:
        f.write(example_test)

    # 写入 CMakeLists.txt
    with open(os.path.join(test_dir, "CMakeLists.txt"), "w") as f:
        f.write(CMAKE_TEMPLATE)

    return {
        "success": True,
        "files": [
            "test/test_framework.h",
            "test/hal_mock.h",
            "test/test_example.c",
            "test/CMakeLists.txt",
        ],
    }


def run_tests(project_dir: str, compiler: str = "gcc") -> dict:
    """编译并运行测试。"""
    test_dir = os.path.join(project_dir, "test")
    if not os.path.isdir(test_dir):
        return {"error": "test/ 目录不存在，先运行 --generate"}

    # 查找测试文件
    test_files = [f for f in os.listdir(test_dir) if f.startswith("test_") and f.endswith(".c")]
    if not test_files:
        return {"error": "未找到测试文件（test_*.c）"}

    results = []
    total_pass = 0
    total_fail = 0

    for test_file in test_files:
        test_name = test_file.replace(".c", "")
        test_path = os.path.join(test_dir, test_file)
        exe_path = os.path.join(test_dir, test_name)

        # 编译
        cmd = [compiler, "-I", test_dir, "-o", exe_path, test_path, "-lm"]
        try:
            proc = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
            if proc.returncode != 0:
                results.append({
                    "name": test_name,
                    "status": "compile_error",
                    "error": proc.stderr[:500],
                })
                continue
        except FileNotFoundError:
            return {"error": f"编译器未找到: {compiler}"}

        # 运行
        try:
            proc = subprocess.run([exe_path], capture_output=True, text=True, timeout=10)
            output = proc.stdout

            # 解析结果
            pass_count = output.count("PASS")
            fail_count = output.count("FAIL")

            results.append({
                "name": test_name,
                "status": "pass" if proc.returncode == 0 else "fail",
                "output": output,
                "pass_count": pass_count,
                "fail_count": fail_count,
            })

            total_pass += pass_count
            total_fail += fail_count

        except subprocess.TimeoutExpired:
            results.append({
                "name": test_name,
                "status": "timeout",
            })

    return {
        "results": results,
        "total_pass": total_pass,
        "total_fail": total_fail,
        "total_tests": total_pass + total_fail,
    }


def generate_xunit_report(test_result: dict, output_file: str) -> str:
    """生成 xUnit 格式报告。"""
    root = ET.Element("testsuites")
    suite = ET.SubElement(root, "testsuite",
                          name="STM32 Unit Tests",
                          tests=str(test_result.get("total_tests", 0)),
                          failures=str(test_result.get("total_fail", 0)))

    for r in test_result.get("results", []):
        case = ET.SubElement(suite, "testcase",
                             name=r["name"],
                             classname="stm32_test")

        if r["status"] == "fail":
            failure = ET.SubElement(case, "failure",
                                   message="Test failed")
            failure.text = r.get("output", "")
        elif r["status"] == "compile_error":
            error = ET.SubElement(case, "error",
                                  message="Compile error")
            error.text = r.get("error", "")
        elif r["status"] == "timeout":
            error = ET.SubElement(case, "error",
                                  message="Timeout")

    tree = ET.ElementTree(root)
    tree.write(output_file, encoding="utf-8", xml_declaration=True)
    return output_file


def main():
    parser = argparse.ArgumentParser(description="STM32 单元测试框架")
    parser.add_argument("--auto", metavar="DIR", default=".", help="项目目录")
    parser.add_argument("--generate", action="store_true", help="生成测试模板")
    parser.add_argument("--run", action="store_true", help="运行测试")
    parser.add_argument("--compiler", default="gcc", help="编译器")
    parser.add_argument("--report", metavar="FILE", help="生成 xUnit 报告")
    parser.add_argument("--json", action="store_true", help="JSON 格式输出")
    args = parser.parse_args()

    project_dir = str(Path(args.auto).resolve())

    if args.generate:
        result = generate_template(project_dir)
        if args.json:
            print(json.dumps(result, indent=2, ensure_ascii=False))
        else:
            print("✅ 测试模板已生成:")
            for f in result["files"]:
                print(f"  📄 {f}")

    elif args.run:
        result = run_tests(project_dir, args.compiler)

        if args.json:
            print(json.dumps(result, indent=2, ensure_ascii=False))
        else:
            for r in result.get("results", []):
                status_icon = {"pass": "✅", "fail": "❌", "compile_error": "🔨",
                               "timeout": "⏰"}.get(r["status"], "?")
                print(f"{status_icon} {r['name']}: {r['status']}")
                if r.get("output"):
                    print(r["output"])

            print(f"\n总计: {result.get('total_pass', 0)} 通过, {result.get('total_fail', 0)} 失败")

        if args.report:
            generate_xunit_report(result, args.report)
            if not args.json:
                print(f"📄 报告已保存: {args.report}")

    else:
        parser.print_help()


if __name__ == "__main__":
    main()
