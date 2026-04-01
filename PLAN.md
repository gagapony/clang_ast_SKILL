# PLAN.md — clangd-call-tree Skill 实现计划

## 阶段划分

### Phase 1: 基础设施

**目标：** 搭建目录结构，创建核心配置和模板文件。

| 任务 | 产出 | 说明 |
|------|------|------|
| 创建目录结构 | `clangd-call-tree-skill/` 完整目录 | 按 REQUIREMENTS.md §5 |
| 编写 `modules/module.json` | 模块配置骨架 | 含 ldc 模块示例 |
| 编写 `templates/commit/format.md` | Commit 模板 | 插槽化，变量占位符 |
| 编写 `ldc/info.md` | ldc 模块概况示例 | 含 header/c 文件路径 |
| 复制 `ldc/filter.cfg` + `ldc/callback.toml` | ldc 模块配置 | 从 clangd-call-tree 项目复制 |

### Phase 2: Python 脚本

**目标：** 实现三个核心脚本。

#### 2.1 `scripts/find_column.py` — 列号计算

```
输入: file_path, line_number, function_name
输出: column_number (0-based)
逻辑: 读指定行，str.find(function_name) 返回字符偏移
错误: 函数名不在该行 → stderr 报错，exit 1
```

#### 2.2 `scripts/simple_call_graph.py` — 精简调用图

```
输入:
  --original  原始 call_graph.json 路径
  --indices   filtered_indices (逗号分隔或 JSON 文件)
  --source    源码根路径
  --output    输出 filtered.json 路径

逻辑:
  1. 加载原始 JSON
  2. 过滤到 indices 集合
  3. 对每个 INTERNAL 节点，读源文件提取 line[0]-line[1] 的代码段
  4. 重建 parent/child 边（仅保留 filtered 集合内的边）
  5. 标记 root node（无有效父节点的节点）
  6. 输出 filtered.json

输出格式:
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

#### 2.3 `scripts/generate_report.py` — 报告生成

```
输入:
  --filtered   filtered.json 路径
  --info       info.md 路径
  --output     输出 report.md 路径
  --requirement 需求描述文本

逻辑:
  1. 从 info.md 提取模块概况段落
  2. 从 filtered.json 生成 ASIC 可视化调用树（缩进格式）
  3. 为每个节点生成函数详情：name(path:line) + brief + source_snippet
  4. 组装为 report.md

ASIC 树生成规则:
  - 从 root_index 开始递归
  - INTERNAL 节点显示 name + path:line + brief
  - EXTERNAL 节点显示 name [EXTERNAL]（不展开）
  - 缩进表示层级关系
```

### Phase 3: SKILL.md 主文档

**目标：** 编写完整的 SKILL.md，定义整个流程的 agent 指令。

```
SKILL.md 内容结构:
  1. Skill 名称与描述
  2. 前置条件（modules/module.json 配置、clangd 安装）
  3. 流程步骤（对应 REQUIREMENTS.md §4 的 Step 0-12）
  4. 每个步骤的详细指令（sub-agent prompt 模板）
  5. 脚本调用方式
  6. 错误处理与降级策略
```

**关键 sub-agent prompt 模板：**

- Step 2 prompt: 入口函数定位（读 info.md → 读 header → 读 C 文件 → 输出 file:line）
- Step 4 prompt: 调用路径过滤（需求 + JSON → filtered_indices）
- Step 7 prompt: 修改计划分析（需求 + report.md → modification_plan.md）
- Step 8 prompt: Linus Reviewer 审查（需求 + report.md + plan → approve/reject）
- Step 9 prompt: 代码实现（plan + report.md → 修改代码）
- Step 11 prompt: Commit（模板 + 变量 → git commit）

### Phase 4: Step 6.5 多入口合并（merge_reports）

**目标：** 实现多 run 产物合并，去重并生成 `merged/` 输出。

#### 合并逻辑（在 `scripts/generate_report.py` 增加 `--merge` 模式）

```
输入:
  --merge <run_dir_0> <run_dir_1> ...    多个 artifacts/run_N 目录
  --output <merged_dir>                   输出目录（默认 merged/）

逻辑:
  1. 加载每个 run_N/filtered.json
  2. 合并 nodes: 以 qualified_name 为去重 key
     - 若 qualified_name 已存在 → 跳过（保留首次出现的节点）
     - 若 index 冲突 → 重映射为新 index（从 max_index+1 开始递增）
  3. 合并 root_index: 保留所有 run 的 root_index（重映射后的值）
  4. 重建 parents/children 边（所有引用的 index 均重映射）
  5. 输出 merged/filtered.json
  6. 对每个 run_N/report.md 提取调用树段 + 函数详情段
  7. 合并去重后输出 merged/report.md
```

#### 去重规则（伪代码）

```python
# 以 qualified_name 为去重 key
seen = {}            # {qualified_name: new_index}
merged_nodes = []    # 合并后的节点列表
index_map = {}       # {old_run_index -> {old_index: new_index}}
next_index = 0

for run_dir in run_dirs:
    data = load_json(f"{run_dir}/filtered.json")
    run_remap = {}

    for node in data['nodes']:
        qname = node['self']['qualified_name']
        if qname in seen:
            # 重复节点: 记录 index 映射，不新增
            run_remap[node['index']] = seen[qname]
        else:
            # 新节点: 分配新 index
            new_idx = next_index
            next_index += 1
            seen[qname] = new_idx
            run_remap[node['index']] = new_idx
            node['index'] = new_idx
            merged_nodes.append(node)

    index_map[run_dir] = run_remap

# 重映射所有 parents/children 引用（在每轮 run 的 remap context 内完成）
for node in merged_nodes:
    # 收集所有 run 中该节点的 remap 映射
    remap = {}
    for run_dir in run_dirs:
        remap.update(index_map[run_dir])
    node['parents'] = [remap[p] for p in node['parents'] if p in remap]
    node['children'] = [remap[c] for c in node['children'] if c in remap]

#### 合并 report.md

```python
# 合并策略: 取第一个 run 的模块概况，拼接所有 run 的调用树和函数详情
# 函数详情以 qualified_name 去重

merged_overview = first_run_overview
merged_tree_lines = []
merged_details = {}  # {qualified_name: section_text}

for run_dir in run_dirs:
    report = read_report(f"{run_dir}/report.md")
    merged_tree_lines.append(report.call_tree_section)
    for section in report.function_detail_sections:
        if section.qualified_name not in merged_details:
            merged_details[section.qualified_name] = section.text

final_report = assemble(
    overview=merged_overview,
    call_tree="\n".join(merged_tree_lines),
    function_details="\n".join(merged_details.values())
)
```

### Phase 5: 验证

**目标：** 用 ldc 模块 + 示例需求验证端到端流程。

```
测试用例:
  需求: "LDC 支持 HW_AUTOSYNC 多个 chn"
  预期:
    - Step 1: 匹配 ldc 模块
    - Step 2: 定位 MI_LDC_CreateChannel
    - Step 3: 生成 call_graph.json/txt
    - Step 4: 过滤出相关节点
    - Step 5: 生成 filtered.json
    - Step 6: 生成 report.md
    - Step 7-12: （需要真实环境验证）
```

### Phase 6: manifest.xml 解析与多仓库 commit 拆分（Step 11）

**目标：** 实现 commit sub-agent 的核心逻辑：从 manifest.xml 解析仓库结构，按仓库拆分 commit。

#### manifest.xml 解析伪代码

```xml
<!-- 典型 manifest.xml 结构 -->
<manifest>
  <project name="sdk" path="sdk" />
  <project name="app" path="app" />
  <project name="hal" path="hal" />
</manifest>
```

```python
import xml.etree.ElementTree as ET

def parse_manifest(manifest_path: str) -> list:
    """
    解析 manifest.xml，返回项目路径列表。

    Args:
        manifest_path: .repo/manifest.xml 路径

    Returns:
        [{"name": str, "path": str}, ...]

    Raises:
        FileNotFoundError: manifest.xml 不存在
        ET.ParseError: XML 格式错误
    """
    tree = ET.parse(manifest_path)
    root = tree.getroot()

    projects = []
    for project in root.findall('project'):
        name = project.get('name')
        path = project.get('path', name)  # path 默认为 name
        projects.append({"name": name, "path": path})

    return projects
```

#### 多仓库 commit 拆分伪代码

```python
def split_files_by_repo(modified_files: list, manifest_projects: list,
                        repo_root: str) -> dict:
    """
    将修改文件列表按仓库分组。

    Args:
        modified_files: ["sdk/interface/src/ldc/ldc_api.c", ...]
        manifest_projects: [{"name": "sdk", "path": "sdk"}, ...]
        repo_root: 项目根目录（manifest.xml 中所有 path 的父目录）

    Returns:
        {"sdk": ["sdk/interface/src/ldc/ldc_api.c"], "app": [...], ...}
        含一个 "unmatched" key 放未匹配的文件
    """
    repo_files = {}

    for file_path in modified_files:
        matched = False
        for proj in manifest_projects:
            proj_path = proj['path']
            if file_path.startswith(proj_path + '/') or file_path == proj_path:
                repo_files.setdefault(proj['name'], []).append(file_path)
                matched = True
                break
        if not matched:
            repo_files.setdefault('unmatched', []).append(file_path)

    return repo_files

def commit_per_repo(repo_files: dict, commit_message: str, repo_root: str) -> list:
    """
    按仓库分别执行 git add + git commit。

    Args:
        repo_files: {"sdk": [...], "app": [...]}
        commit_message: commit 消息（每个 repo 附带仓库名前缀）
        repo_root: 项目根目录

    Returns:
        [{"repo": str, "success": bool, "error": str}, ...]
    """
    results = []
    for repo_name, files in repo_files.items():
        if repo_name == 'unmatched':
            continue
        repo_path = os.path.join(repo_root, repo_name)

        # git add
        for f in files:
            subprocess.run(['git', 'add', f], cwd=repo_path)

        # git commit
        msg = f"[{repo_name}] {commit_message}"
        result = subprocess.run(
            ['git', 'commit', '-m', msg],
            cwd=repo_path, capture_output=True, text=True
        )
        results.append({
            "repo": repo_name,
            "success": result.returncode == 0,
            "error": result.stderr if result.returncode != 0 else ""
        })

    return results
```

#### 流程

```
Step 11 执行流程:

1. 读 .repo/manifest.xml → parse_manifest → projects list
2. 检测修改文件列表 (git diff --name-only)
3. split_files_by_repo → repo_files dict
4. 检查 repo_files:
   - 仅一个 key (不含 unmatched) → 单仓库 commit
   - 多个 key → 按仓库拆分 commit
   - 有 unmatched → stderr 警告
5. commit_per_repo → 执行 commit
6. 输出结果摘要
```

## 实现顺序

```
Phase 1 (基础) → Phase 2.1 (find_column.py) → Phase 2.2 (simple_call_graph.py)
→ Phase 2.3 (generate_report.py) → Phase 3 (SKILL.md) → Phase 4 (merge_reports)
→ Phase 5 (端到端验证) → Phase 6 (manifest 解析 + 多仓库 commit)
```

## 依赖

- `clangd-call-tree` 工具已安装（`~/.openclaw/code/projects/clangd-call-tree/`）
- Python 3.x
- clangd 已安装
- 项目有 `compile_commands.json`
