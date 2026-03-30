#!/usr/bin/env python3
"""merge_reports.py - Merge multiple run directories into a single merged output.

Usage: python merge_reports.py --runs <dir1> <dir2> [...] [--output <dir>]
Output: merged/filtered.json + merged/report.md
"""

import argparse
import json
import os
import re
import sys


TREE_PREFIX = "    "  # 每级缩进 4 空格


def load_json(path: str):
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


def load_all_runs(run_dirs: list) -> list:
    """加载所有 run 目录的 filtered.json。

    Args:
        run_dirs: run 目录路径列表

    Returns:
        [{"root_index": int, "nodes": list}, ...]

    Raises:
        SystemExit: 目录不存在或无有效 run
    """
    runs = []
    for d in run_dirs:
        filtered_path = os.path.join(d, 'filtered.json')
        if not os.path.isdir(d):
            print(f"Error: Run directory not found: {d}", file=sys.stderr)
            sys.exit(1)
        if not os.path.isfile(filtered_path):
            print(f"Warning: filtered.json not found in {d}, skipping", file=sys.stderr)
            continue
        try:
            data = load_json(filtered_path)
            runs.append(data)
        except json.JSONDecodeError as e:
            print(f"Warning: Invalid JSON in {filtered_path}: {e}, skipping", file=sys.stderr)
            continue
    return runs


def deduplicate_nodes(all_runs: list) -> tuple:
    """以 qualified_name 去重，分配新 index，重映射边。

    修复: 每个 node 必须用自己所属 run 的 index_map 做 remap_edges，
    不能合并为全局字典（不同 run 的原始 index 含义不同，会冲突覆盖）。

    Args:
        all_runs: 所有 run 的 filtered 数据列表

    Returns:
        (merged_nodes: list, root_indices: list)
    """
    seen = {}  # qualified_name → new_index
    merged_nodes = []
    root_indices = []

    for run in all_runs:
        # 第一遍: 为当前 run 的所有节点建立 old_index → new_index 映射
        # 必须先遍历完所有节点再做 remap，因为 node 可能互相引用
        run_index_map = {}
        nodes_to_add = []  # (new_idx, node_copy)

        for node in run['nodes']:
            info = node['self']
            qname = info.get('qualified_name') or info.get('name')
            if not qname:
                print(f"Warning: qualified_name missing, using name fallback",
                      file=sys.stderr)
                qname = info.get('name', f"unknown_{node['index']}")

            if qname in seen:
                # 已存在，记录映射（不加入 merged_nodes）
                run_index_map[node['index']] = seen[qname]
            else:
                # 新节点，分配新 index
                new_idx = len(merged_nodes)
                seen[qname] = new_idx
                run_index_map[node['index']] = new_idx
                node_copy = dict(node)
                nodes_to_add.append((new_idx, node_copy))

        # 第二遍: 用当前 run 的 index_map 重映射边，然后加入 merged_nodes
        for new_idx, node_copy in nodes_to_add:
            remap_edges(node_copy, run_index_map)
            merged_nodes.append(node_copy)

        # 重映射 root_index
        old_root = run.get('root_index')
        if old_root is not None and old_root in run_index_map:
            root_indices.append(run_index_map[old_root])

    return merged_nodes, root_indices


def remap_edges(node: dict, remap: dict) -> dict:
    """重映射单个节点的 parents/children index。

    Args:
        node: 节点 dict
        remap: {old_index: new_index}

    Returns:
        更新后的节点 dict
    """
    node['parents'] = [remap[p] for p in node.get('parents', []) if p in remap]
    node['children'] = [remap[c] for c in node.get('children', []) if c in remap]
    return node


def extract_module_overview(info_path: str) -> str:
    """从 info.md 提取模块概况段落。

    策略:
    - 读取整个文件内容
    - 提取 "## 模块说明" 之后的段落（到下一个 ## 或文件结尾）
    - 若无此标题，返回整个文件内容

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
        return content.strip()

    after_marker = content[idx + len(marker):]
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

    if tag == "INTERNAL":
        for child_idx in node.get('children', []):
            child_node = node_map.get(child_idx)
            if child_node is None:
                continue
            result += generate_call_tree(node_map, child_idx, depth + 1, visited)

    return result


def generate_function_details(node_map: dict) -> str:
    """为每个节点生成函数详情 Markdown 段落（按 qualified_name 去重）。

    Args:
        node_map: {index: node} 字典

    Returns:
        函数详情 Markdown 文本
    """
    seen_qnames = set()
    sections = []

    for idx in sorted(node_map.keys()):
        node = node_map[idx]
        info = node['self']
        qualified_name = info.get('qualified_name', info.get('name', ''))

        if qualified_name in seen_qnames:
            continue
        seen_qnames.add(qualified_name)

        tag = node['tag']
        name = info['name']
        path = info.get('path', '')
        line = info.get('line', [0, 0])
        brief = info.get('brief', '')

        line_start = line[0] if isinstance(line, list) else line

        section = f"### {name} ({path}:{line_start})\n\n"
        section += f"- brief: {brief}\n"
        section += f"- tag: {tag}\n"
        section += f"- qualified_name: {qualified_name}\n"

        if tag == "INTERNAL" and node.get('source_snippet'):
            section += f"\n```c\n{node['source_snippet']}\n```\n"

        sections.append(section)

    return "\n".join(sections)


def generate_merged_report(run_dirs: list, merged_data: dict) -> str:
    """生成合并后的 report.md 内容。

    策略:
    1. 模块概况取第一个 run
    2. 调用树拼接（所有 run 的 root 按顺序展开）
    3. 函数详情以 qualified_name 去重

    Args:
        run_dirs: run 目录列表
        merged_data: 合并后的 filtered 数据

    Returns:
        report.md 内容
    """
    # 模块概况: 取第一个 run
    first_info = os.path.join(run_dirs[0], 'info.md')
    module_overview = extract_module_overview(first_info)

    # 调用树
    node_map = build_node_map(merged_data['nodes'])
    call_tree_parts = []
    for root_idx in merged_data.get('root_indices', [merged_data['root_index']]):
        tree_text = generate_call_tree(node_map, root_idx)
        if tree_text:
            call_tree_parts.append(tree_text.rstrip())
    call_tree = "\n\n".join(call_tree_parts)

    # 函数详情
    function_details = generate_function_details(node_map)

    # 组装
    report = "# 调用分析报告 (合并)\n\n"
    report += f"## 模块概况\n\n{module_overview}\n\n"
    report += f"## 调用树\n\n```\n{call_tree}\n```\n\n"
    report += f"## 函数详情\n\n{function_details}\n"
    return report


def main() -> int:
    """CLI 入口。

    1. argparse 解析 run_dirs + output_dir
    2. load_all_runs
    3. deduplicate_nodes + remap_edges
    4. 输出 merged/filtered.json
    5. generate_merged_report → merged/report.md
    """
    parser = argparse.ArgumentParser(
        description='Merge multiple run directories into a single merged output.'
    )
    parser.add_argument('--runs', nargs='+', required=True,
                        help='Run directory paths (e.g. run_0/ run_1/ ...)')
    parser.add_argument('--output', default='merged',
                        help='Output directory (default: merged/)')

    args = parser.parse_args()

    # 1. 加载所有 run
    all_runs = load_all_runs(args.runs)
    if not all_runs:
        print("Error: No valid runs found", file=sys.stderr)
        return 1

    # 2. 去重 + index 重映射 + 边重建（deduplicate_nodes 内部完成 per-run remap）
    merged_nodes, root_indices = deduplicate_nodes(all_runs)

    # 3. index 已在 deduplicate_nodes 中连续分配，直接组装输出
    merged_data = {
        'root_indices': root_indices,
        'root_index': root_indices[0] if root_indices else 0,
        'nodes': merged_nodes,
    }

    # 6. 写 filtered.json
    os.makedirs(args.output, exist_ok=True)
    out_filtered = os.path.join(args.output, 'filtered.json')
    try:
        with open(out_filtered, 'w', encoding='utf-8') as f:
            json.dump(merged_data, f, ensure_ascii=False, indent=2)
    except IOError as e:
        print(f"Error: Cannot write {out_filtered}: {e}", file=sys.stderr)
        return 1

    # 7. 生成并写 report.md
    report = generate_merged_report(args.runs, merged_data)
    out_report = os.path.join(args.output, 'report.md')
    try:
        with open(out_report, 'w', encoding='utf-8') as f:
            f.write(report)
    except IOError as e:
        print(f"Error: Cannot write {out_report}: {e}", file=sys.stderr)
        return 1

    return 0


if __name__ == '__main__':
    sys.exit(main())
