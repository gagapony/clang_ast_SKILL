#!/usr/bin/env python3
"""
Step 1: 模块匹配（确定性）

读取 module.json，用关键词匹配模块。
输出 JSON，主 agent 直接填模板，不需要 LLM 做匹配。

用法:
  python3 step1_match.py --modules /path/to/module.json --keywords "关键词1" "关键词2"

输出 (stdout JSON):
{
  "matched": true,
  "module_name": "ldc",
  "info_md": "/path/to/info.md",
  "filter_cfg": "/path/to/filter.cfg",
  "callback_cfg": "/path/to/callback.toml",
  "project_root": "/path/to/project",
  "matched_keywords": ["关键词1"],
  "reason": "..."
}
"""

import argparse
import json
import os
import sys


def load_modules(path: str) -> list:
    with open(path, 'r') as f:
        data = json.load(f)
    return data.get('modules', [])


def match_module(modules: list, keywords: list) -> dict:
    """关键词匹配：优先交集，无交集用语义子串兜底"""
    best = None
    best_score = 0

    for mod in modules:
        mod_keywords = [k.lower() for k in mod.get('keywords', [])]
        matched = []
        for kw in keywords:
            kw_lower = kw.lower()
            for mk in mod_keywords:
                if kw_lower in mk or mk in kw_lower:
                    matched.append(kw)
                    break

        score = len(matched)
        if score > best_score:
            best_score = score
            best = {
                'matched': True,
                'module_name': mod['name'],
                'info_md': mod.get('info_md', ''),
                'filter_cfg': mod.get('filter_cfg', ''),
                'callback_cfg': mod.get('callback_cfg', ''),
                'project_root': mod.get('project_root', ''),
                'matched_keywords': matched,
                'reason': f'关键词命中 {score}/{len(keywords)}: {", ".join(matched)}'
            }

    if best is None:
        available = [m['name'] for m in modules]
        return {
            'matched': False,
            'module_name': '',
            'info_md': '',
            'filter_cfg': '',
            'callback_cfg': '',
            'project_root': '',
            'matched_keywords': [],
            'reason': f'无匹配模块。可用模块: {", ".join(available)}'
        }

    return best


def main():
    parser = argparse.ArgumentParser(description='Step1: 模块匹配')
    parser.add_argument('--modules', required=True, help='module.json 路径')
    parser.add_argument('--keywords', nargs='+', required=True, help='关键词列表')
    args = parser.parse_args()

    if not os.path.exists(args.modules):
        print(json.dumps({'matched': False, 'reason': f'module.json 不存在: {args.modules}'}))
        sys.exit(1)

    modules = load_modules(args.modules)
    result = match_module(modules, args.keywords)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    sys.exit(0 if result['matched'] else 1)


if __name__ == '__main__':
    main()
