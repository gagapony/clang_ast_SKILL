# SKILL.md — clangd-call-tree-skill

> 基于 clangd-call-tree 的代码调用路径分析与自动修改 Skill

## 概述

从用户自然语言需求出发，自动分析 C/C++ 项目函数调用关系，定位代码修改位置，实现修改，经审查后提交。

**核心流程：** 需求 → 入口函数定位 → 调用图生成 → 路径过滤 → 报告生成 → 修改分析 → 审查 → 实现 → 确认 → 提交

## 前置条件

1. `modules.json` 已配置（从 `modules.json.example` 复制并修改 `project_root`）
2. 目标模块目录下有 `info.md`、`filter.cfg`、`callback.toml`
3. 项目有 `compile_commands.json`
4. 安装了 `clangd` 和 Python 3.8+
5. `clangd-call-tree` 工具可用（路径: `~/.openclaw/code/projects/clangd-call-tree/main.py`）

## 目录结构

```
clangd-call-tree-skill/
├── SKILL.md                    # 本文件
├── CLAUDE.md                   # symlink → SKILL.md
├── modules.json.example        # 模块配置示例
├── scripts/
│   ├── find_column.py          # Step 2: 列号计算
│   ├── simple_call_graph.py    # Step 5: 精简调用图
│   ├── generate_report.py      # Step 6: 报告生成
│   └── merge_reports.py        # Step 6.5: 多入口合并
├── templates/commit/
│   └── format.md               # Commit 模板
├── demo/                       # 演示模块
├── ldc/                        # ldc 模块插槽
├── artifacts/                  # 运行时产物（完成后清理）
└── merged/                     # 合并产物（完成后清理）
```

## 流程

### Step 0: 用户输入

用户提供自然语言需求描述。例如：

> "帮我修改当前的代码，要求 LDC 支持 HW_AUTOSYNC 多个 chn"

主 agent 解析需求，提取关键信息供后续步骤使用。

### Step 1: 模块匹配

**执行者：** 主 agent

1. 读取 `modules.json`
2. 从用户需求提取关键词
3. 与 `modules.*.keywords` 匹配
4. 命中的模块 → 加载对应 `info.md`、`filter_cfg`、`callback_cfg`

**多关键词处理：** 取交集；无交集 → 语义兜底

**输出：** 模块名、info.md 路径、filter_cfg 路径、callback_cfg 路径、project_root

### Step 2: 入口函数定位

**执行者：** sub-agent

**Sub-agent Prompt 模板：**

```
你是代码分析专家。根据需求和模块信息，定位入口函数。

## 需求
{用户需求描述}

## 模块信息
{info.md 内容}

## 任务
1. 读取 info.md 中指定的头文件，理解 API 接口
2. 根据需求语义，匹配相关的入口函数
3. 读取对应的 C 源文件，找到函数定义的精确行号
4. 输出入口函数信息

## 输出格式 (JSON)
```json
{
  "entry_functions": [
    {
      "func_name": "函数名",
      "file": "相对路径/file.c",
      "line": 行号(1-based)
    }
  ],
  "reasoning": "为什么选择这些入口函数"
}
```

如果需求涉及多个独立的功能点，可能需要多个入口函数。
```

**主 agent 后处理：**

对每个入口函数，调用 `find_column.py` 获取列号：

```bash
python3 scripts/find_column.py \
  --file "{project_root}/{file}" \
  --line {line} \
  --func "{func_name}"
```

拼接为入口点格式：`{file}:{line}:{col}`

**多入口决策：**
- 如果返回多个 entry_functions → 后续 Step 3-6 对每个独立执行（run_0, run_1, ...）
- 如果 entry_functions 中有交集关系 → 合并为单个入口

### Step 3: clangd-call-tree 生成调用关系

**执行者：** 主 agent（shell 命令）

对每个入口函数执行：

```bash
cd {SKILL_DIR}
mkdir -p artifacts/run_{N}

python3 {CLANGD_CALL_TREE_PATH}/main.py \
  -p {project_root} \
  -e "{file}:{line}:{col}" \
  -f all \
  -c {filter_cfg} \
  --callback-config {callback_cfg} \
  -d 10 \
  -o artifacts/run_{N}/call_graph
```

**产出：** `artifacts/run_{N}/call_graph.json` + `call_graph.txt`

**错误处理：**
- clangd-call-tree 失败 → 检查 compile_commands.json 是否存在，clangd 是否安装
- 空输出 → 检查 filter.cfg 是否覆盖了目标文件

### Step 4: 调用路径过滤

**执行者：** sub-agent

**Sub-agent Prompt 模板：**

```
你是代码分析专家。根据用户需求，从调用图中筛选真正相关的调用路径。

## 用户需求
{用户需求描述}

## 入口函数
{entry_function}

## 调用图数据
以下 JSON 包含所有函数节点。每个节点有:
- index: 唯一标识
- tag: INTERNAL(项目代码) / EXTERNAL(第三方库)
- self.name: 函数名
- self.qualified_name: 限定名
- self.brief: 函数描述
- self.path: 文件路径
- self.line: [起始行, 结束行]
- parents: 调用此函数的父节点 index 列表
- children: 此函数调用的子节点 index 列表

{call_graph.json 内容 (仅 brief + index + name + tag)}

## 任务
分析每个节点的 brief 和函数名，判断是否与用户需求相关。
保留与需求相关的节点，排除无关的节点。

## 输出格式 (JSON)
```json
{
  "entry_function": "{入口函数名}",
  "filtered_indices": [相关节点的 index 列表],
  "filter_reason": {
    "index": "保留理由"
  },
  "excluded_count": 排除的节点数
}
```

## 判断规则
1. 入口函数本身 → 必选
2. 与需求关键词直接相关的函数 → 必选
3. 数据传递链上的中间函数 → 必选
4. 通用工具函数 (log, delay, malloc 等) → 排除
5. 不相关的第三方库调用 → 排除
6. brief 为 null 且函数名无法判断相关性 → 排除
```

**结构性校验（主 agent 执行）：**

```bash
# 验证 filtered_indices 中的 index 是否存在于原始 JSON 中
python3 -c "
import json
original = json.load(open('artifacts/run_{N}/call_graph.json'))
filtered = json.load(open('artifacts/run_{N}/filtered_indices.json'))
valid = {n['index'] for n in original}
invalid = [i for i in filtered['filtered_indices'] if i not in valid]
if invalid:
    print(f'Invalid indices: {invalid}')
    exit(1)
print('Validation passed')
"
```

校验失败 → 打回 Step 4 重做

### Step 5: 精简调用图生成

**执行者：** 主 agent（脚本调用）

```bash
python3 scripts/simple_call_graph.py \
  --original artifacts/run_{N}/call_graph.json \
  --indices artifacts/run_{N}/filtered_indices.json \
  --source {project_root} \
  --output artifacts/run_{N}/filtered.json
```

**产出：** `artifacts/run_{N}/filtered.json`

包含过滤后的节点、重建的边、源码片段、root_index 标记。

### Step 6: 报告文档生成

**执行者：** 主 agent（脚本调用）

```bash
python3 scripts/generate_report.py \
  --filtered artifacts/run_{N}/filtered.json \
  --info {info_md_path} \
  --output artifacts/run_{N}/report.md \
  --requirement "{用户需求描述}"
```

**产出：** `artifacts/run_{N}/report.md`

包含模块概况、ASIC 可视化调用树、函数详情（含源码片段）。

### Step 6.5: 多入口合并（如有多个 run）

**执行者：** 主 agent（脚本调用）

```bash
python3 scripts/merge_reports.py \
  --runs artifacts/run_0 artifacts/run_1 ... \
  --output merged/
```

**产出：** `merged/filtered.json` + `merged/report.md`

**后续 Step 7-12 使用 `merged/report.md`（或单个 `report.md`）**

### Step 7: 修改计划分析

**执行者：** sub-agent

**Sub-agent Prompt 模板：**

```
你是高级代码分析师。根据调用分析报告和用户需求，制定代码修改计划。

## 用户需求
{用户需求描述}

## 调用分析报告
{report.md 内容}

## 任务
1. 分析调用树，理解代码执行路径
2. 定位需要修改的函数和位置
3. 制定具体的修改方案

## 输出格式 (Markdown)
```markdown
# 修改计划: {需求描述}

## 原始需求摘要
- 需求: {需求}
- 涉及模块: {模块}
- 涉及仓库: {仓库路径}

## 分析结论
{对调用树的分析，说明为什么需要修改这些位置}

## 修改位置

### 修改 1: {简述}
- 文件: {path}
- 函数: {func_name}
- 行号: {line}
- 当前逻辑: {描述当前代码}
- 修改方案: {描述如何修改}
- 原因: {为什么需要修改}

### 修改 2: ...
```

确保修改计划完整覆盖用户需求的所有关键点。
```

### Step 7.5: 结构性校验

**执行者：** 主 agent（纯规则，不调 LLM）

```bash
# 检查 modification_plan.md 中引用的函数是否存在于 filtered.json
python3 -c "
import json, re

# 读取 modification_plan.md 提取函数名
with open('modification_plan.md') as f:
    plan = f.read()
funcs_in_plan = set(re.findall(r'函数[：:]\s*(\S+)', plan))

# 读取 filtered.json
with open('merged/filtered.json') as f:
    data = json.load(f)
valid_funcs = {n['self']['name'] for n in data['nodes']}

# 检查
invalid = funcs_in_plan - valid_funcs
if invalid:
    print(f'Functions not in call graph: {invalid}')
    exit(1)
print('Structural validation passed')
"
```

**通过** → Step 8
**失败** → 打回 Step 7，附带校验错误信息

### Step 8: Linus Reviewer 审查

**执行者：** sub-agent（Linus Reviewer）

**Sub-agent Prompt 模板：**

```
你是 Linus Reviewer。零容忍审查。

## 原始需求
{用户需求描述}

## 调用分析报告
{report.md 内容}

## 修改计划
{modification_plan.md 内容}

## 审查标准（按优先级）
1. 修改计划是否完整覆盖原始需求的所有关键点
2. 修改位置是否准确（函数、文件、行号与 report.md 一致）
3. 修改逻辑是否合理，有无副作用遗漏
4. 是否需要额外的错误处理/边界检查

## 输出格式
- APPROVE: "APPROVED" + 简要总结
- REJECT: 列出具体问题，说明原因

最大 3 轮。3 轮不通过 → 输出 "ESCALATE: 需要人工介入"
```

**循环控制：**
- APPROVE → Step 9
- REJECT → 打回 Step 7，附带 reject 理由（最多 3 轮）
- ESCALATE → 停止自动流程，通知用户

### Step 9: 代码实现

**执行者：** sub-agent（实现）

**Sub-agent Prompt 模板：**

```
你是代码实现专家。根据修改计划，修改代码。

## 修改计划
{modification_plan.md (approved)}

## 调用分析报告
{report.md 内容}

## 任务
按照修改计划，对每个修改位置执行代码修改。
修改前先阅读当前代码，确保理解上下文。

## 输出格式
```markdown
## 修改完成

### 修改 1: {简述}
- 文件: {path}
- 修改前: {关键代码片段}
- 修改后: {关键代码片段}

### 修改 2: ...
```

## 约束
- 只修改修改计划中指定的位置
- 不要修改不相关的代码
- 保持代码风格一致
- 确保修改后代码可编译
```

### Step 10: 用户确认

**执行者：** 主 agent → 用户

展示修改结果摘要：

```markdown
## 修改确认

**需求:** {用户需求}

**修改内容:**
{Step 9 的输出摘要}

**涉及文件:**
- file1.c (N 行修改)
- file2.h (N 行修改)

**请确认: YES / NO**
```

**确认渠道：** Claude Code 交互窗口 / OpenClaw webchat / Telegram
- YES → Step 11
- NO → 停止

### Step 11: Commit

**执行者：** sub-agent（commit）

**Sub-agent Prompt 模板：**

```
你是 Git 提交专家。根据修改内容和 commit 模板，生成 commit 信息并提交。

## 修改内容
{Step 9 的输出}

## Commit 模板
{templates/commit/format.md 内容}

## 模板变量
- 项目名: {项目名}
- 模块名: {模块名}
- ticket: 从以下中选择一个（用户提供）:
  - rdm_task: {值或留空}
  - rdm_issue: {值或留空}
  - mantis_id: {值或留空}
  - sspm_id: {值或留空}
  - comake_id: {值或留空}

## 任务
1. 读取 .repo/manifest.xml 确定涉及的 git 仓库
2. 检测涉及的仓库数量
   - 单仓库 → 一个 commit
   - 多仓库 → 按仓库拆分多个 commit
3. 按模板格式生成 commit message
4. 执行 git add + git commit

## commit message 规则
- subject: 简洁描述修改内容（不超过 50 字符）
- rootcause: 问题原因
- solution: 解决方案
- sideeffect: 潜在副作用
- selftestlist: 自测项目
- selftestresult: P(ass)/F(ail)
- ticket: ticket_type_ticket_id（用户提供的任一值）
- redflag: Y/N
```

### Step 12: 清理与总结

**执行者：** 主 agent

1. **清理中间产物：**
   ```bash
   rm -rf artifacts/ merged/
   ```

2. **生成最终总结：**
   ```markdown
   ## 任务完成

   **需求:** {用户需求}
   **模块:** {模块名}
   **入口函数:** {entry_function(s)}
   **修改文件:**
   - {file1} (N 行)
   - {file2} (N 行)
   **Commit:** {commit hash} - {commit subject}
   **Ticket:** {ticket}
   ```

## 错误处理与降级策略

| 场景 | 处理 |
|------|------|
| modules.json 不存在 | 提示用户从 .example 复制并配置 |
| 模块匹配失败 | 列出可用模块，提示用户选择 |
| 入口函数定位失败 | 列出 info.md 中的候选函数 |
| clangd-call-tree 失败 | 检查 compile_commands.json / clangd 安装 |
| Step 4 过滤结果为空 | 降低过滤粒度，保留更多节点 |
| Step 7 结构校验失败 | 附带错误信息打回 Step 7 |
| Step 8 审查 3 轮不通过 | ESCALATE，停止自动流程 |
| Step 10 用户选择 NO | 停止，保留修改代码供用户参考 |
| Step 11 多仓库检测 | 按 manifest.xml 拆分 commit |

## 环境变量与路径

| 变量 | 说明 | 示例 |
|------|------|------|
| `SKILL_DIR` | Skill 根目录 | `~/.openclaw/code/projects/clangd-call-tree-skill/` |
| `CLANGD_CALL_TREE` | clangd-call-tree 路径 | `~/.openclaw/code/projects/clangd-call-tree/main.py` |
| `project_root` | 项目根目录 | 从 modules.json 读取 |
| `module_dir` | 模块目录 | `{SKILL_DIR}/{module_name}/` |
