#!/usr/bin/env python3
"""
从 call_graph.json 提取关键点（index + brief），生成精简版供 sub-agent 分析。

其他字段（name, file, tag, path, line）可通过 index 从 call_graph.json 还原。

用法:
    python3 scripts/extract_keypoint.py --input call_graph.json --output call_graph_keypoint.json
"""

import argparse
import json
import sys


def main():
    parser = argparse.ArgumentParser(description="Extract keypoint (index + brief) from call_graph.json")
    parser.add_argument("--input", "-i", required=True, help="Input call_graph.json")
    parser.add_argument("--output", "-o", required=True, help="Output keypoint JSON")
    args = parser.parse_args()

    with open(args.input, "r", encoding="utf-8") as f:
        graph = json.load(f)

    keypoint = []
    for node in graph:
        keypoint.append({
            "index": node["index"],
            "brief": node["self"].get("brief") or "null"
        })

    with open(args.output, "w", encoding="utf-8") as f:
        json.dump(keypoint, f, indent=2, ensure_ascii=False)

    no_brief = sum(1 for n in keypoint if n["brief"] == "null")
    print(f"Extracted: {len(keypoint)} nodes, {no_brief} without brief")
    print(f"Output: {args.output}")


if __name__ == "__main__":
    sys.exit(main())
