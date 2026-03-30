#!/usr/bin/env python3
"""find_column.py - Find 0-based column of a function name in a source file line.

Usage: python find_column.py --file <path> --line <int> --func <name>
Output: 0-based column number to stdout
"""

import argparse
import os
import sys


def read_line(file_path: str, line_number: int) -> str:
    """读取指定文件的指定行（1-based）。

    Args:
        file_path: 文件路径
        line_number: 1-based 行号

    Returns:
        行内容字符串（去除末尾换行）

    Raises:
        FileNotFoundError: 文件不存在
        ValueError: 行号越界
    """
    if not os.path.isfile(file_path):
        raise FileNotFoundError(f"File not found: {file_path}")

    if line_number <= 0:
        raise ValueError(f"Line number must be positive: {line_number}")

    with open(file_path, 'r', encoding='utf-8') as f:
        total_lines = 0
        for i, line in enumerate(f, start=1):
            total_lines = i
            if i == line_number:
                return line.rstrip('\n')

    raise ValueError(f"Line {line_number} out of range (file has {total_lines} lines)")


def find_column(line_content: str, func_name: str, line_number: int = 0) -> int:
    """在行内容中查找函数名的 0-based 字符偏移。

    Args:
        line_content: 行字符串
        func_name: 要查找的函数名
        line_number: 行号（用于错误信息，0 表示未知）

    Returns:
        0-based 列号

    Raises:
        ValueError: 函数名不在该行中
    """
    idx = line_content.find(func_name)
    if idx == -1:
        if line_number > 0:
            raise ValueError(f"Function '{func_name}' not found in line {line_number}")
        raise ValueError(f"Function '{func_name}' not found in line")
    return idx


def main() -> int:
    """CLI 入口。解析参数 → read_line → find_column → print(col)。"""
    parser = argparse.ArgumentParser(
        description='Find 0-based column of a function name in a source file line.'
    )
    parser.add_argument('--file', required=True, help='Source file path (absolute or relative)')
    parser.add_argument('--line', required=True, type=int, help='1-based line number')
    parser.add_argument('--func', required=True, help='Function name (exact substring match)')

    args = parser.parse_args()

    try:
        line_content = read_line(args.file, args.line)
        col = find_column(line_content, args.func, args.line)
        print(col)
        return 0
    except FileNotFoundError as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1
    except ValueError as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1


if __name__ == '__main__':
    sys.exit(main())
