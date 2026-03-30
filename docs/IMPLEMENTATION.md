# IMPLEMENTATION.md — Python 脚本详细实现规范

> 基于 REQUIREMENTS.md §4 Step 2/5/6，定义三个 Python 脚本的完整接口、数据流、函数拆分与错误处理。

**约束：** Python 3.8+ 标准库，零第三方依赖。

---

## 全局约定

| 项目 | 规范 |
|------|------|
| 编码 | UTF-8，所有文件 I/O 统一 `encoding='utf-8'` |
| 错误输出 | `sys.stderr`，`exit(1)` |
| 正常输出 | `sys.stdout`（find_column）或写文件（其余两个） |
| CLI | `argparse`，每个参数带 help string |
| 结构 | 每个脚本顶层: imports → 常量 → 辅助函数 → CLI 函数 → main |

---

## 脚本 1: `scripts/find_column.py`

### 1.1 用途

给定源文件、行号、函数名，返回该函数名在行内的 0-based 字符偏移（列号）。供 Step 2 拼接 `file:line:col` 入口点格式使用。

### 1.2 CLI 接口

```
python find_column.py --file <path> --line <int> --func <name>
```

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `--file` | str | 是 | 源文件路径（绝对或相对） |
| `--line` | int | 是 | 1-based 行号 |
| `--func` | str | 是 | 函数名（精确子串匹配） |

### 1.3 输出规范

- **stdout:** 单行，纯整数（0-based 列号），无多余空格/换行
- **stderr:** 错误信息
- **exit code:** 0 成功，1 失败

### 1.4 数据流

```
stdin: (none)
stdout: "42"
stderr: (error messages only)
```

### 1.5 函数拆分

```python
def read_line(file_path: str, line_number: int) -> str:
    """
    读取指定文件的指定行（1-based）。

    Args:
        file_path: 文件路径
        line_number: 1-based 行号

    Returns:
        行内容字符串（去除末尾换行）

    Raises:
        FileNotFoundError: 文件不存在
        ValueError: 行号越界
    """

def find_column(line_content: str, func_name: str) -> int:
    """
    在行内容中查找函数名的 0-based 字符偏移。

    Args:
        line_content: 行字符串
        func_name: 要查找的函数名

    Returns:
        0-based 列号

    Raises:
        ValueError: 函数名不在该行中
    """

def main() -> int:
    """
    CLI 入口。解析参数 → read_line → find_column → print(col)。
    捕获异常，stderr 报错，返回 exit code。
    """
```

### 1.6 逻辑细节

1. **文件读取：**
   - `os.path.isfile(file_path)` 检查存在性
   - 逐行读取（`enumerate(f, start=1)`），到目标行停下
   - 不一次性读整个文件（大文件友好）

2. **列号计算：**
   - `line_content.find(func_name)` → 返回首次出现的位置
   - 返回 `-1` → 抛出 `ValueError`

3. **错误处理：**

   | 场景 | 输出 | exit |
   |------|------|------|
   | 文件不存在 | `Error: File not found: {path}` | 1 |
   | 行号 ≤ 0 | `Error: Line number must be positive: {line}` | 1 |
   | 行号超出文件行数 | `Error: Line {line} out of range (file has {total} lines)` | 1 |
   | 函数名不在该行 | `Error: Function '{func}' not found in line {line}` | 1 |

### 1.7 边界情况

- 函数名包含 `::`（C++ 限定名）→ 直接匹配，不做特殊处理
- 同一行出现多次函数名 → 取第一次（`str.find` 行为）
- Tab 字符 → 不做展开，按原始字节偏移

---

## 脚本 2: `scripts/simple_call_graph.py`

### 2.1 用途

将 clangd-call-tree 的原始 `call_graph.json` 按 `filtered_indices` 过滤，提取源码片段，重建边，生成精简的 `filtered.json`。供 Step 5 使用。

### 2.2 CLI 接口

```
python simple_call_graph.py \
  --original <path> \
  --indices <path> \
  [--source <path>] \
  --output <path>
```

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `--original` | str | 是 | 原始 `call_graph.json` 路径 |
| `--indices` | str | 是 | `filtered_indices` JSON 文件路径 |
| `--source` | str | 否 | 项目源码根路径，default=None；不传时用 node.self.path（绝对路径）直接读取 |
| `--output` | str | 是 | 输出 `filtered.json` 路径 |

### 2.3 输入格式

**call_graph.json:**
```json
[
  {
    "index": 0,
    "tag": "INTERNAL",
    "self": {
      "path": "/abs/path/to/file.c",
      "line": [88, 120],
      "type": "function",
      "name": "MI_LDC_CreateChannel",
      "qualified_name": "MI_LDC_CreateChannel",
      "brief": "Create LDC channel with config"
    },
    "parents": [5, 12],
    "children": [1, 3, 7]
  }
]
```

**filtered_indices JSON:**
```json
{
  "entry_function": "MI_LDC_CreateChannel",
  "filtered_indices": [0, 3, 9, 15, 22],
  "filter_reason": { "0": "入口函数，必选" },
  "excluded_count": 85
}
```

### 2.4 输出格式

```json
{
  "root_index": 0,
  "nodes": [
    {
      "index": 0,
      "tag": "INTERNAL",
      "self": { "path", "line", "name", "qualified_name", "brief" },
      "parents": [5],
      "children": [3, 9],
      "source_snippet": "int MI_LDC_CreateChannel(...) {\n  ...\n}"
    }
  ]
}
```

- `source_snippet`: 仅 INTERNAL 节点有值；EXTERNAL 节点为 `""`
- `parents` / `children`: 仅保留属于 filtered 集合的 index
- `root_index`: filtered 集合中 `parents` 为空的节点 index（取第一个）

### 2.5 函数拆分

```python
def load_json(path: str) -> list:
    """
    加载 JSON 文件并返回解析后的对象。

    Args:
        path: JSON 文件路径

    Returns:
        解析后的 Python 对象

    Raises:
        FileNotFoundError: 文件不存在
        json.JSONDecodeError: JSON 格式错误
    """

def load_filtered_indices(path: str) -> dict:
    """
    加载 filtered_indices JSON 文件。

    Args:
        path: filtered_indices JSON 路径

    Returns:
        dict with keys: entry_function, filtered_indices, filter_reason, excluded_count

    Raises:
        KeyError: 缺少必要字段
    """

def filter_nodes(nodes: list, indices: set) -> dict:
    """
    按 index 过滤节点，重建边，返回 {index: node} 字典。

    Args:
        nodes: 原始节点列表
        indices: 需要保留的 index 集合

    Returns:
        {index: filtered_node_dict}
    """

def rebuild_edges(node: dict, valid_indices: set) -> dict:
    """
    重建单个节点的 parents/children 边，仅保留 valid_indices 中的 index。

    Args:
        node: 原始节点 dict
        valid_indices: 有效 index 集合

    Returns:
        更新后的节点 dict（parents/children 已过滤）
    """

def extract_source_snippet(file_path: str, line_range: list, source_root: str) -> str:
    """
    从源文件提取指定行范围的代码段。

    Args:
        file_path: 节点 self.path（绝对路径）
        line_range: [start_line, end_line]（1-based，闭区间）
        source_root: 源码根路径（用于路径解析 fallback）

    Returns:
        代码段字符串；文件不可读时返回空字符串
    """

def find_root_index(nodes: dict) -> int:
    """
    在 filtered 节点集合中找到 root_index。

    定义: parents 为空列表的节点为 root。
    若有多个，取第一个（按 index 升序）。
    若无，取 index 最小的节点。

    Args:
        nodes: {index: node} 字典

    Returns:
        root_index
    """

def build_output(nodes: dict, root_index: int) -> dict:
    """
    组装最终输出 dict。

    Args:
        nodes: {index: node} 字典
        root_index: 根节点 index

    Returns:
        {"root_index": int, "nodes": list}
    """

def main() -> int:
    """
    CLI 入口。
    1. argparse 解析
    2. load_json(original) → nodes list
    3. load_filtered_indices(indices) → filtered set
    4. filter_nodes + rebuild_edges
    5. 对 INTERNAL 节点: extract_source_snippet
    6. find_root_index
    7. build_output → json.dump to output
    """
```

### 2.6 逻辑细节

#### 路径解析策略 (extract_source_snippet)

```
优先级:
1. 直接使用 node.self.path（绝对路径） → os.path.isfile 检查
2. 尝试 source_root + 相对路径（如果 self.path 是相对路径）
3. 两者都失败 → 返回 "" 并 stderr 警告
```

#### 源码提取

```python
# line_range 示例: [88, 120]（1-based, 闭区间）
# 提取第 88 行到第 120 行的内容

with open(file_path, 'r', encoding='utf-8') as f:
    lines = f.readlines()

# 截取 [start-1 : end]（Python 0-based slice）
snippet_lines = lines[start_line - 1 : end_line]
snippet = ''.join(snippet_lines).rstrip('\n')
```

- 不做语法高亮，纯文本
- 去除末尾多余空行（`rstrip`）

#### 边重建

```python
valid_indices = set(filtered_indices)

for node in filtered_nodes.values():
    # parents: 原始 parents ∩ valid_indices
    node['parents'] = [p for p in node.get('parents', []) if p in valid_indices]
    # children: 原始 children ∩ valid_indices
    node['children'] = [c for c in node.get('children', []) if c in valid_indices]
```

#### root_index 判定

```python
# 优先: 找 parents 为空的节点
roots = [idx for idx, n in nodes.items() if not n['parents']]
if roots:
    root_index = min(roots)  # 取 index 最小的
else:
    root_index = min(nodes.keys())  # fallback: index 最小的
```

### 2.7 错误处理

| 场景 | 处理 | exit |
|------|------|------|
| original 文件不存在 | stderr 报错 | 1 |
| original JSON 解析失败 | stderr 报错 + 行列信息 | 1 |
| indices 文件不存在 | stderr 报错 | 1 |
| indices 缺少 `filtered_indices` 字段 | stderr 报错 | 1 |
| source 路径不存在 | stderr 警告（继续，snippet 为空） | 0 |
| 节点 self.path 文件不可读 | stderr 警告，snippet = "" | 0 |
| filtered_indices 含不存在的 index | stderr 警告，跳过 | 0 |
| output 目录不存在 | 自动创建（`os.makedirs(os.path.dirname(output), exist_ok=True)`） | - |
| output 写入失败 | stderr 报错 | 1 |

### 2.8 输出节点顺序

- nodes 列表按 index 升序排列，保证确定性输出

---

## 脚本 3: `scripts/generate_report.py`

### 3.1 用途

将 `filtered.json` + `info.md` 组装为人类可读的 `report.md`。供 Step 6 使用。

### 3.2 CLI 接口

```
python generate_report.py \
  --filtered <path> \
  --info <path> \
  --output <path> \
  --requirement <str>
```

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `--filtered` | str | 是 | `filtered.json` 路径 |
| `--info` | str | 是 | `info.md` 路径 |
| `--output` | str | 是 | 输出 `report.md` 路径 |
| `--requirement` | str | 是 | 用户需求描述文本 |

### 3.3 输出模板

```markdown
# 调用分析报告: {requirement}

## 模块概况

{从 info.md 提取的核心段落}

## 调用树

{ASIC 可视化缩进树}

## 函数详情

### {func_name} ({path}:{line})

- brief: {brief}
- tag: {INTERNAL|EXTERNAL}

```c
{source_snippet（仅 INTERNAL 节点有）}
```

### {next_func} ...
```

### 3.4 函数拆分

```python
def load_filtered_json(path: str) -> dict:
    """
    加载 filtered.json。

    Returns:
        {"root_index": int, "nodes": list}

    Raises:
        FileNotFoundError
        json.JSONDecodeError
        KeyError: 缺少 root_index 或 nodes
    """

def extract_module_overview(info_path: str) -> str:
    """
    从 info.md 提取模块概况段落。

    策略:
    - 读取整个文件内容
    - 提取 "## 模块说明" 之后的段落（到下一个 ## 或文件结尾）
    - 若无此标题，返回整个文件内容

    Args:
        info_path: info.md 文件路径

    Returns:
        模块概况文本（Markdown 格式）
    """

def build_node_map(nodes: list) -> dict:
    """
    将节点列表转为 {index: node} 字典。

    Args:
        nodes: 节点列表

    Returns:
        {index: node_dict}
    """

def generate_call_tree(node_map: dict, root_index: int, depth: int = 0,
                       visited: set = None) -> str:
    """
    递归生成 ASIC 可视化调用树（纯缩进格式）。

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

def generate_function_details(node_map: dict) -> str:
    """
    为每个节点生成函数详情 Markdown 段落。

    顺序: 按 index 升序
    每个节点格式:

    ### {name} ({path}:{line[0]})

    - brief: {brief}
    - tag: {tag}
    - qualified_name: {qualified_name}

    ```c
    {source_snippet}
    ```

    EXTERNAL 节点无 source_snippet 代码块。

    Args:
        node_map: {index: node} 字典

    Returns:
        函数详情 Markdown 文本
    """

def assemble_report(requirement: str, module_overview: str,
                    call_tree: str, function_details: str) -> str:
    """
    组装最终 report.md。

    Args:
        requirement: 需求描述
        module_overview: 模块概况段落
        call_tree: ASIC 调用树文本
        function_details: 函数详情文本

    Returns:
        完整 report.md 内容
    """

def main() -> int:
    """
    CLI 入口。
    1. argparse 解析
    2. load_filtered_json
    3. extract_module_overview
    4. build_node_map
    5. generate_call_tree
    6. generate_function_details
    7. assemble_report
    8. 写入 output
    """
```

### 3.5 逻辑细节

#### ASIC 调用树生成

递归遍历，从 `root_index` 开始。采用纯缩进格式（无分支符），精确定义见 REQUIREMENTS.md §3.5。

```python
TREE_PREFIX = "    "  # 每级缩进 4 空格

def generate_call_tree(node_map, root_index, depth=0, visited=None):
    if visited is None:
        visited = set()

    if root_index in visited:
        return ""  # 防环
    visited.add(root_index)

    node = node_map.get(root_index)
    if node is None:
        import sys
        print(f"Warning: root_index {root_index} not found in node_map, skipping",
              file=sys.stderr)
        return ""

    info = node['self']
    tag = node['tag']
    line_start = info['line'][0] if isinstance(info['line'], list) else info['line']
    name = info['name']
    brief = info.get('brief', '')
    path = info['path']

    # 当前行: name (path:line) - brief
    indent = TREE_PREFIX * depth
    line = f"{indent}{name} ({path}:{line_start})"
    if brief:
        line += f" - {brief}"
    if tag == "EXTERNAL":
        line += " [EXTERNAL]"
    result = line + "\n"

    # 仅 INTERNAL 展开 children
    if tag == "INTERNAL":
        for child_idx in node.get('children', []):
            child_node = node_map.get(child_idx)
            if child_node is None:
                continue
            result += generate_call_tree(node_map, child_idx, depth + 1, visited)

    return result
```

格式示例（纯缩进）:

```
root_func (path/file.c:88) - brief
    child_a (path/file.c:42) - brief
        grandchild_x (path/file.c:10) - brief
    child_b (path/lib.h:5) - brief [EXTERNAL]
```

#### info.md 概况提取

```python
def extract_module_overview(info_path):
    with open(info_path, 'r', encoding='utf-8') as f:
        content = f.read()

    # 查找 "## 模块说明" 标题
    marker = "## 模块说明"
    idx = content.find(marker)
    if idx == -1:
        # fallback: 返回整个文件（去除一级标题）
        return content.strip()

    # 提取从 marker 开始到下一个 ## 或文件结尾
    after_marker = content[idx + len(marker):]
    # 找下一个同级标题
    next_section = re.search(r'\n## ', after_marker)
    if next_section:
        overview = after_marker[:next_section.start()]
    else:
        overview = after_marker

    return overview.strip()
```

#### 函数详情生成

```python
def generate_function_details(node_map):
    sections = []
    for idx in sorted(node_map.keys()):
        node = node_map[idx]
        info = node['self']
        tag = node['tag']
        name = info['name']
        path = info['path']
        line = info['line']
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
```

#### report.md 组装

```python
def assemble_report(requirement, module_overview, call_tree, function_details):
    report = f"# 调用分析报告: {requirement}\n\n"
    report += f"## 模块概况\n\n{module_overview}\n\n"
    report += f"## 调用树\n\n```\n{call_tree}```\n\n"
    report += f"## 函数详情\n\n{function_details}\n"
    return report
```

### 3.6 错误处理

| 场景 | 处理 | exit |
|------|------|------|
| filtered 文件不存在 | stderr 报错 | 1 |
| filtered JSON 解析失败 | stderr 报错 | 1 |
| filtered 缺少 root_index/nodes | stderr 报错 | 1 |
| info 文件不存在 | stderr 警告，module_overview = "" | 0 |
| info 文件为空 | module_overview = "" | 0 |
| output 目录不存在 | 自动创建 | - |
| output 写入失败 | stderr 报错 | 1 |
| 节点引用的 index 在 node_map 中不存在 | 跳过（不报错） | 0 |

### 3.7 边界情况

- 空 nodes 列表 → report 只含标题和模块概况
- EXTERNAL 节点无 source_snippet → 不生成代码块
- source_snippet 为空字符串 → 不生成代码块
- 节点循环引用 → visited 集合防环
- requirement 含特殊字符（换行等）→ 取第一行

---

## 数据流总图

```
Step 2 (sub-agent)
  ├── 读 info.md → 定位入口函数
  ├── find_column.py --file --line --func → col
  └── 输出: file:line:col

Step 3 (clangd-call-tree CLI)
  ├── python main.py -e "file:line:col" -f all -o artifacts/run_N/call_graph
  └── 产出: call_graph.json + call_graph.txt

Step 4 (sub-agent)
  ├── 输入: requirement + call_graph.json(brief+index)
  └── 输出: filtered_indices.json

Step 5 (脚本)
  ├── simple_call_graph.py --original call_graph.json
  │   --indices filtered_indices.json --source <root> --output filtered.json
  └── 产出: filtered.json

Step 6 (脚本)
  ├── generate_report.py --filtered filtered.json
  │   --info info.md --output report.md --requirement "..."
  └── 产出: report.md

Step 6.5 (脚本，多入口时)
  ├── merge_reports.py --runs run_0/ run_1/ ... --output merged/
  ├── 合并 filtered.json（qualified_name 去重 + index 重映射）
  └── 产出: merged/filtered.json + merged/report.md
```

---

## 脚本 4: `scripts/merge_reports.py`（或 generate_report.py --merge 模式）

### 4.1 用途

多入口分析时，合并多个 `artifacts/run_N/` 的产物，生成去重后的 `merged/filtered.json` 和 `merged/report.md`。

### 4.2 CLI 接口

独立脚本模式:

```
python merge_reports.py \
  --runs <run_dir_0> <run_dir_1> [<run_dir_2> ...] \
  --output <merged_dir>
```

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `--runs` | str+ | 是 | 多个 `artifacts/run_N` 目录路径 |
| `--output` | str | 否 | 输出目录，默认 `merged/` |

### 4.3 合并规则

**去重 key:** `qualified_name`（节点 `self.qualified_name`）

**index 重映射:**
```
遍历所有 run 的节点:
  if qualified_name 已存在 → 跳过，记录 old_index → existing_new_index 映射
  if qualified_name 不存在 → 分配新 index（从 0 递增），加入 merged_nodes
重映射所有节点的 parents/children 中的 index 引用
```

**root_index 合并:**
- 每个 run 的 root_index 重映射后，全部保留为 merged 的 root candidates
- 最终取第一个（或 parents 为空的节点）

### 4.4 输出

**merged/filtered.json:**
```json
{
  "root_indices": [0],
  "root_index": 0,
  "nodes": [...]
}
```
- `root_indices`: 所有原始 root（重映射后）
- `root_index`: 合并后的主 root（第一个 root candidate）
- `nodes`: 去重后的全量节点（index 连续，从 0 开始）

**merged/report.md:**
- 模块概况: 取第一个 run 的 info.md
- 调用树: 所有 run 的调用树按 run 顺序拼接
- 函数详情: 以 qualified_name 去重，保留首次出现

### 4.5 函数拆分

```python
def load_all_runs(run_dirs: list) -> list:
    """
    加载所有 run 目录的 filtered.json。

    Returns:
        [{"root_index": int, "nodes": list}, ...]
    """

def deduplicate_nodes(all_runs: list) -> tuple:
    """
    以 qualified_name 去重，分配新 index。

    Returns:
        (merged_nodes: list, index_maps: list)
        index_maps: 每个 run 的 {old_index: new_index} 映射
    """

def remap_edges(node: dict, remap: dict) -> dict:
    """
    重映射单个节点的 parents/children index。

    Args:
        node: 节点 dict
        remap: {old_index: new_index}

    Returns:
        更新后的节点 dict
    """

def merge_reports(run_dirs: list, output_dir: str) -> int:
    """
    合并多个 run 的 report.md。

    策略:
    1. 模块概况取第一个 run
    2. 调用树拼接（中间以空行分隔）
    3. 函数详情以 qualified_name 去重

    Args:
        run_dirs: run 目录列表
        output_dir: 输出目录

    Returns:
        exit code
    """

def main() -> int:
    """
    CLI 入口。
    1. argparse 解析 run_dirs + output_dir
    2. load_all_runs
    3. deduplicate_nodes + remap_edges
    4. 输出 merged/filtered.json
    5. merge_reports → merged/report.md
    """
```

### 4.6 错误处理

| 场景 | 处理 | exit |
|------|------|------|
| run_dir 不存在 | stderr 报错 | 1 |
| run_dir 中无 filtered.json | stderr 报错，跳过该 run | 0 |
| qualified_name 缺失 | stderr 警告，用 name 作为 fallback key | 0 |
| output 目录不存在 | 自动创建 | - |

---

## 测试要点

### find_column.py
- 正常: 已知文件+行号+函数名 → 返回正确列号
- 错误: 文件不存在 → exit 1
- 错误: 行号越界 → exit 1
- 错误: 函数名不在行中 → exit 1
- 边界: 函数名在行首 → 返回 0
- 边界: 函数名在行尾 → 返回正确偏移

### simple_call_graph.py
- 正常: 完整 JSON + indices → 输出 filtered.json
- 验证: filtered.json 中所有 index 在 indices 集合内
- 验证: parents/children 仅含 filtered 集合内 index
- 验证: root_index 的 parents 为空
- 验证: INTERNAL 节点有非空 source_snippet
- 验证: EXTERNAL 节点 source_snippet 为空
- 错误: 原始 JSON 不存在 → exit 1

### generate_report.py
- 正常: 完整 filtered.json + info.md → 输出 report.md
- 验证: report.md 包含 "## 模块概况" 段
- 验证: report.md 包含 "## 调用树" 段（缩进格式）
- 验证: report.md 包含 "## 函数详情" 段
- 验证: 每个 INTERNAL 节点有 source 代码块
- 边界: info.md 不存在 → report 仍可生成（概况为空）
- 边界: 空 nodes → report 只有标题
