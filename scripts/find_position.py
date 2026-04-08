#!/usr/bin/env python3
"""find_position.py - 使用简单正则搜索定位函数行号和列号。

用法:
    python find_position.py --file <path> --func <name>

输出 JSON:
    {
        "file": "path/to/file.c",
        "function": "func_name",
        "line": 123,
        "column": 5,
        "success": true
    }
"""

import argparse
import json
import os
import re
import sys


def find_function(file_path: str, func_name: str) -> dict:
    """
    在文件中搜索函数定义，返回行号和列号。

    使用简单的正则匹配，不依赖 clangd。
    """
    if not os.path.exists(file_path):
        return {"success": False, "error": f"File not found: {file_path}"}

    with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
        lines = f.readlines()

    # 函数定义模式：匹配 func_name 后紧跟 (
    # 支持多种格式：
    #   int func_name(
    #   void func_name (
    #   static int func_name(
    #   func_name(
    escaped_name = re.escape(func_name)

    patterns = [
        # 标准函数定义: type func_name(
        rf'^(\s*)(?:[\w\s\*]+?)\b{escaped_name}\s*\(',
        # 函数指针赋值: .func_name =
        rf'^(\s*)\.{escaped_name}\s*=',
        # 宏定义: #define func_name(
        rf'^(\s*)#define\s+{escaped_name}\s*\(',
        # 简单形式: func_name(  (行首或空白后)
        rf'(?:^|\s)({escaped_name})\s*\(',
    ]

    for line_num, line in enumerate(lines, 1):
        for pattern in patterns:
            match = re.search(pattern, line)
            if match:
                # 找到函数名在行中的位置
                func_match = re.search(escaped_name, line)
                if func_match:
                    col = func_match.start()  # 0-based
                    return {
                        "success": True,
                        "file": file_path,
                        "function": func_name,
                        "line": line_num - 1,
                        "column": col
                    }

    return {
        "success": False,
        "error": f"Function '{func_name}' not found in {file_path}"
    }


def main():
    parser = argparse.ArgumentParser(
        description="定位函数在源文件中的行号和列号"
    )
    parser.add_argument("--file", required=True, help="源文件路径")
    parser.add_argument("--func", required=True, help="函数名")

    args = parser.parse_args()

    # 解析文件路径
    file_path = os.path.abspath(args.file)

    result = find_function(file_path, args.func)
    print(json.dumps(result, indent=2))

    if not result.get("success"):
        sys.exit(1)


if __name__ == "__main__":
    main()
