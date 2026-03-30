#!/usr/bin/env python3
"""simple_call_graph.py - Filter call_graph.json by filtered_indices, extract source snippets.

Usage: python simple_call_graph.py --original <path> --indices <path> [--source <path>] --output <path>
Output: filtered.json
"""

import argparse
import json
import os
import sys


def load_json(path: str) -> list:
    """加载 JSON 文件并返回解析后的对象。

    Args:
        path: JSON 文件路径

    Returns:
        解析后的 Python 对象

    Raises:
        FileNotFoundError: 文件不存在
        json.JSONDecodeError: JSON 格式错误
    """
    with open(path, 'r', encoding='utf-8') as f:
        return json.load(f)


def load_filtered_indices(path: str) -> dict:
    """加载 filtered_indices JSON 文件。

    Args:
        path: filtered_indices JSON 路径

    Returns:
        dict with keys: entry_function, filtered_indices, filter_reason, excluded_count

    Raises:
        KeyError: 缺少必要字段
        FileNotFoundError: 文件不存在
        json.JSONDecodeError: JSON 格式错误
    """
    data = load_json(path)
    if 'filtered_indices' not in data:
        raise KeyError("Missing required field 'filtered_indices' in JSON")
    return data


def rebuild_edges(node: dict, valid_indices: set) -> dict:
    """重建单个节点的 parents/children 边，仅保留 valid_indices 中的 index。

    Args:
        node: 原始节点 dict
        valid_indices: 有效 index 集合

    Returns:
        更新后的节点 dict（parents/children 已过滤）
    """
    node['parents'] = [p for p in node.get('parents', []) if p in valid_indices]
    node['children'] = [c for c in node.get('children', []) if c in valid_indices]
    return node


def filter_nodes(nodes: list, indices: set) -> dict:
    """按 index 过滤节点，重建边，返回 {index: node} 字典。

    Args:
        nodes: 原始节点列表
        indices: 需要保留的 index 集合

    Returns:
        {index: filtered_node_dict}
    """
    filtered = {}
    for node in nodes:
        idx = node['index']
        if idx in indices:
            new_node = dict(node)
            rebuild_edges(new_node, indices)
            filtered[idx] = new_node
    return filtered


def extract_source_snippet(file_path: str, line_range: list, source_root: str = None) -> str:
    """从源文件提取指定行范围的代码段。

    Args:
        file_path: 节点 self.path（绝对路径）
        line_range: [start_line, end_line]（1-based，闭区间）
        source_root: 源码根路径（用于路径解析 fallback）

    Returns:
        代码段字符串；文件不可读时返回空字符串
    """
    resolved_path = None

    # 策略 1: 直接使用 node.self.path（绝对路径）
    if os.path.isfile(file_path):
        resolved_path = file_path
    # 策略 2: 尝试 source_root + 相对路径
    elif source_root and not os.path.isabs(file_path):
        candidate = os.path.join(source_root, file_path)
        if os.path.isfile(candidate):
            resolved_path = candidate

    if resolved_path is None:
        print(f"Warning: source file not readable: {file_path}, snippet set to empty",
              file=sys.stderr)
        return ''

    start_line, end_line = line_range[0], line_range[1]
    try:
        with open(resolved_path, 'r', encoding='utf-8') as f:
            lines = f.readlines()
        snippet_lines = lines[start_line - 1 : end_line]
        snippet = ''.join(snippet_lines).rstrip('\n')
        return snippet
    except (IOError, OSError) as e:
        print(f"Warning: cannot read {resolved_path}: {e}, snippet set to empty",
              file=sys.stderr)
        return ''


def find_root_index(nodes: dict) -> int:
    """在 filtered 节点集合中找到 root_index。

    定义: parents 为空列表的节点为 root。
    若有多个，取第一个（按 index 升序）。
    若无，取 index 最小的节点。

    Args:
        nodes: {index: node} 字典

    Returns:
        root_index
    """
    roots = [idx for idx, n in nodes.items() if not n['parents']]
    if roots:
        return min(roots)
    return min(nodes.keys()) if nodes else 0


def build_output(nodes: dict, root_index: int) -> dict:
    """组装最终输出 dict。

    Args:
        nodes: {index: node} 字典
        root_index: 根节点 index

    Returns:
        {"root_index": int, "nodes": list}
    """
    node_list = sorted(nodes.values(), key=lambda n: n['index'])
    return {
        'root_index': root_index,
        'nodes': node_list,
    }


def main() -> int:
    """CLI 入口。

    1. argparse 解析
    2. load_json(original) → nodes list
    3. load_filtered_indices(indices) → filtered set
    4. filter_nodes + rebuild_edges
    5. 对 INTERNAL 节点: extract_source_snippet
    6. find_root_index
    7. build_output → json.dump to output
    """
    parser = argparse.ArgumentParser(
        description='Filter call_graph.json by filtered_indices, extract snippets, output filtered.json.'
    )
    parser.add_argument('--original', required=True, help='Original call_graph.json path')
    parser.add_argument('--indices', required=True, help='filtered_indices JSON file path')
    parser.add_argument('--source', default=None, help='Project source root path (optional)')
    parser.add_argument('--output', required=True, help='Output filtered.json path')

    args = parser.parse_args()

    # 1. 加载原始 call_graph
    try:
        nodes = load_json(args.original)
    except FileNotFoundError as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1
    except json.JSONDecodeError as e:
        print(f"Error: Invalid JSON in {args.original}: {e}", file=sys.stderr)
        return 1

    # 2. 加载 filtered_indices
    try:
        indices_data = load_filtered_indices(args.indices)
    except FileNotFoundError as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1
    except json.JSONDecodeError as e:
        print(f"Error: Invalid JSON in {args.indices}: {e}", file=sys.stderr)
        return 1
    except KeyError as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1

    valid_indices = set(indices_data['filtered_indices'])

    # 3. 过滤节点，重建边
    filtered = filter_nodes(nodes, valid_indices)

    # 4. 对 INTERNAL 节点提取源码片段
    for idx, node in filtered.items():
        if node['tag'] == 'INTERNAL':
            line_range = node['self']['line']
            file_path = node['self']['path']
            node['source_snippet'] = extract_source_snippet(file_path, line_range, args.source)
        else:
            node['source_snippet'] = ''

    # 5. 找 root_index
    root_index = find_root_index(filtered)

    # 6. 组装输出
    output_data = build_output(filtered, root_index)

    # 7. 写文件
    out_dir = os.path.dirname(args.output)
    if out_dir:
        os.makedirs(out_dir, exist_ok=True)

    try:
        with open(args.output, 'w', encoding='utf-8') as f:
            json.dump(output_data, f, ensure_ascii=False, indent=2)
    except IOError as e:
        print(f"Error: Cannot write output: {e}", file=sys.stderr)
        return 1

    return 0


if __name__ == '__main__':
    sys.exit(main())
