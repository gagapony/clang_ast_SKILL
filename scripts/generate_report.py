#!/usr/bin/env python3
"""generate_report.py - Generate human-readable report.md from filtered.json + info.md.

Usage: python generate_report.py --filtered <path> --info <path> --output <path> --requirement <str>
Output: report.md
"""

import argparse
import json
import os
import re
import sys


TREE_PREFIX = "    "  # 每级缩进 4 空格


def load_filtered_json(path: str) -> dict:
    """加载 filtered.json。

    Returns:
        {"root_index": int, "nodes": list}

    Raises:
        FileNotFoundError
        json.JSONDecodeError
        KeyError: 缺少 root_index 或 nodes
    """
    with open(path, 'r', encoding='utf-8') as f:
        data = json.load(f)
    if 'root_index' not in data:
        raise KeyError("Missing 'root_index' in filtered.json")
    if 'nodes' not in data:
        raise KeyError("Missing 'nodes' in filtered.json")
    return data


def extract_module_overview(info_path: str) -> str:
    """从 info.md 提取模块概况段落。

    策略:
    - 读取整个文件内容
    - 提取 "## 模块说明" 之后的段落（到下一个 ## 或文件结尾）
    - 若无此标题，返回整个文件内容（去除一级标题）

    Args:
        info_path: info.md 文件路径

    Returns:
        模块概况文本（Markdown 格式）
    """
    if not os.path.isfile(info_path):
        return ''

    with open(info_path, 'r', encoding='utf-8') as f:
        content = f.read()

    marker = "## 模块说明"
    idx = content.find(marker)
    if idx == -1:
        # fallback: 返回整个文件（去除一级标题）
        return content.strip()

    after_marker = content[idx + len(marker):]
    # 找下一个同级标题
    next_section = re.search(r'\n## ', after_marker)
    if next_section:
        overview = after_marker[:next_section.start()]
    else:
        overview = after_marker

    return overview.strip()


def build_node_map(nodes: list) -> dict:
    """将节点列表转为 {index: node} 字典。

    Args:
        nodes: 节点列表

    Returns:
        {index: node_dict}
    """
    return {node['index']: node for node in nodes}


def generate_call_tree(node_map: dict, root_index: int, depth: int = 0,
                       visited: set = None) -> str:
    """递归生成 ASIC 可视化调用树（纯缩进格式）。

    格式规则:
    - 每行格式: {indent}{name} ({path}:{line[0]}) - {brief}
    - EXTERNAL 节点: 行末追加 [EXTERNAL]，不展开 children
    - INTERNAL 节点: 展开 children（递归，depth+1）
    - 缩进: 每级 4 空格
    - 防环: visited 集合防止重复展开

    Args:
        node_map: {index: node} 字典
        root_index: 根节点 index
        depth: 当前缩进深度
        visited: 已访问 index 集合（防环）

    Returns:
        缩进树文本
    """
    if visited is None:
        visited = set()

    if root_index in visited:
        return ''
    visited.add(root_index)

    node = node_map.get(root_index)
    if node is None:
        print(f"Warning: root_index {root_index} not found in node_map, skipping",
              file=sys.stderr)
        return ''

    info = node['self']
    tag = node['tag']
    line = info.get('line', [0, 0])
    line_start = line[0] if isinstance(line, list) else line
    name = info['name']
    brief = info.get('brief', '')
    path = info.get('path', '')

    indent = TREE_PREFIX * depth
    line_text = f"{indent}{name} ({path}:{line_start})"
    if brief:
        line_text += f" - {brief}"
    if tag == "EXTERNAL":
        line_text += " [EXTERNAL]"
    result = line_text + "\n"

    # 仅 INTERNAL 展开 children
    if tag == "INTERNAL":
        for child_idx in node.get('children', []):
            child_node = node_map.get(child_idx)
            if child_node is None:
                continue
            result += generate_call_tree(node_map, child_idx, depth + 1, visited)

    return result


def generate_function_details(node_map: dict) -> str:
    """为每个节点生成函数详情 Markdown 段落。

    顺序: 按 index 升序

    Args:
        node_map: {index: node} 字典

    Returns:
        函数详情 Markdown 文本
    """
    sections = []
    for idx in sorted(node_map.keys()):
        node = node_map[idx]
        info = node['self']
        tag = node['tag']
        name = info['name']
        path = info.get('path', '')
        line = info.get('line', [0, 0])
        brief = info.get('brief', '')
        qualified_name = info.get('qualified_name', name)

        line_start = line[0] if isinstance(line, list) else line

        section = f"### {name} ({path}:{line_start})\n\n"
        section += f"- brief: {brief}\n"
        section += f"- tag: {tag}\n"
        section += f"- qualified_name: {qualified_name}\n"

        if tag == "INTERNAL" and node.get('source_snippet'):
            section += f"\n```c\n{node['source_snippet']}\n```\n"

        sections.append(section)

    return "\n".join(sections)


def assemble_report(requirement: str, module_overview: str,
                    call_tree: str, function_details: str) -> str:
    """组装最终 report.md。

    Args:
        requirement: 需求描述
        module_overview: 模块概况段落
        call_tree: ASIC 调用树文本
        function_details: 函数详情文本

    Returns:
        完整 report.md 内容
    """
    report = f"# 调用分析报告: {requirement}\n\n"
    report += f"## 模块概况\n\n{module_overview}\n\n"
    report += f"## 调用树\n\n```\n{call_tree}```\n\n"
    report += f"## 函数详情\n\n{function_details}\n"
    return report


def main() -> int:
    """CLI 入口。

    1. argparse 解析
    2. load_filtered_json
    3. extract_module_overview
    4. build_node_map
    5. generate_call_tree
    6. generate_function_details
    7. assemble_report
    8. 写入 output
    """
    parser = argparse.ArgumentParser(
        description='Generate human-readable report.md from filtered.json + info.md.'
    )
    parser.add_argument('--filtered', required=True, help='filtered.json path')
    parser.add_argument('--info', required=True, help='info.md path')
    parser.add_argument('--output', required=True, help='Output report.md path')
    parser.add_argument('--requirement', required=True, help='User requirement description text')

    args = parser.parse_args()

    # 1. 加载 filtered.json
    try:
        filtered_data = load_filtered_json(args.filtered)
    except FileNotFoundError as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1
    except json.JSONDecodeError as e:
        print(f"Error: Invalid JSON in {args.filtered}: {e}", file=sys.stderr)
        return 1
    except KeyError as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1

    # 2. 提取模块概况
    module_overview = extract_module_overview(args.info)
    if not os.path.isfile(args.info):
        print(f"Warning: info file not found: {args.info}, module_overview set to empty",
              file=sys.stderr)

    # 3. 构建 node map
    node_map = build_node_map(filtered_data['nodes'])

    # 4. 生成调用树
    call_tree = generate_call_tree(node_map, filtered_data['root_index'])

    # 5. 生成函数详情
    function_details = generate_function_details(node_map)

    # 6. 组装报告
    requirement = args.requirement.split('\n')[0]
    report = assemble_report(requirement, module_overview, call_tree, function_details)

    # 7. 写文件
    out_dir = os.path.dirname(args.output)
    if out_dir:
        os.makedirs(out_dir, exist_ok=True)

    try:
        with open(args.output, 'w', encoding='utf-8') as f:
            f.write(report)
    except IOError as e:
        print(f"Error: Cannot write output: {e}", file=sys.stderr)
        return 1

    return 0


if __name__ == '__main__':
    sys.exit(main())
