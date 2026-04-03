#!/usr/bin/env python3
"""
Step 2: 从 info.md 提取入口函数目录（确定性）

解析 info.md 中的 ## Step2 Config 段落，
提取函数目录表格，输出结构化 JSON。
主 agent 拿到 JSON 后直接填 prompt 模板，不需要 LLM 做提取。

用法:
  python3 step2_extract.py --info /path/to/info.md

输出 (stdout JSON):
{
  "has_config": true,
  "entry_files": ["mi_ldc_pass.c", "ldc_api.c"],
  "catalog_markdown": "#### mi_ldc_pass.c\n\n| 函数名 | 行号 | 说明 |\n...",
  "functions": [
    {"name": "LDC_Init", "file": "mi_ldc_pass.c", "line": 45, "desc": "编码通道初始化"},
    ...
  ]
}
"""

import argparse
import json
import os
import re
import sys


def extract_step2_config(info_path: str) -> dict:
    with open(info_path, 'r') as f:
        content = f.read()

    # 定位 ## Step2 Config 段落
    pattern = r'##\s+Step2\s+Config\s*\n(.*?)(?=\n##\s|\Z)'
    match = re.search(pattern, content, re.DOTALL)

    if not match:
        return {
            'has_config': False,
            'entry_files': [],
            'catalog_markdown': '',
            'functions': [],
            'error': 'info.md 中未找到 ## Step2 Config 段落，请补充'
        }

    config_block = match.group(1)

    # 提取入口文件列表
    entry_files = []
    file_pattern = r'^-\s+(\S+\.c)\s*$'
    for line in config_block.split('\n'):
        m = re.match(file_pattern, line.strip())
        if m:
            entry_files.append(m.group(1))

    # 提取函数目录 markdown（从 ### 入口函数目录 到文件末尾或下一个 ## ）
    catalog_pattern = r'###\s+入口函数目录\s*\n(.*?)(?=\n###\s|\n##\s|\Z)'
    catalog_match = re.search(catalog_pattern, config_block, re.DOTALL)
    catalog_md = catalog_match.group(1).strip() if catalog_match else ''

    # 解析函数表格
    functions = []
    current_file = None

    for line in config_block.split('\n'):
        # 检测 #### 文件名
        file_header = re.match(r'####\s+(\S+\.c)', line.strip())
        if file_header:
            current_file = file_header.group(1)
            continue

        # 解析表格行: | func_name | line | desc |
        if current_file and '|' in line:
            cells = [c.strip() for c in line.split('|')]
            cells = [c for c in cells if c]  # 去掉首尾空串
            if len(cells) >= 2 and cells[0] not in ('函数名', '---', ''):
                # 跳过表头和分隔线
                if all(c.replace('-', '') == '' for c in cells):
                    continue
                try:
                    line_num = int(cells[1])
                except ValueError:
                    continue
                functions.append({
                    'name': cells[0],
                    'file': current_file,
                    'line': line_num,
                    'desc': cells[2] if len(cells) > 2 else ''
                })

    return {
        'has_config': True,
        'entry_files': entry_files,
        'catalog_markdown': catalog_md,
        'functions': functions
    }


def main():
    parser = argparse.ArgumentParser(description='Step2: 提取入口函数目录')
    parser.add_argument('--info', required=True, help='info.md 路径')
    args = parser.parse_args()

    if not os.path.exists(args.info):
        print(json.dumps({'has_config': False, 'error': f'info.md 不存在: {args.info}'}))
        sys.exit(1)

    result = extract_step2_config(args.info)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    sys.exit(0 if result['has_config'] else 1)


if __name__ == '__main__':
    main()
