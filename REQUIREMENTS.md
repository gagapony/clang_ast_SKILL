# REQUIREMENTS.md — clangd-call-tree Skill

## 1. 目标

构建一个 SKILL，基于 clangd-call-tree 工具分析 C/C++ 项目函数调用关系，通过多 sub-agent 协作，从用户需求出发，自动定位代码修改位置，实现修改，经 review 后提交。

**核心原则：** 用户全程零干预，仅在输入需求和最终结果验收时参与。

## 2. 术语与变量

| 变量 | 说明 |
|------|------|
| `SKILL_DIR` | Skill 根目录 `~/.openclaw/code/projects/clangd-call-tree-skill/` |
| `modules.json` | 模块配置文件，定义项目根、模块列表、关键词映射 |
| `info.md` | 模块概况文档（插槽），包含 header/c 文件路径，供 sub-agent 检索入口函数 |
| `filter.cfg` | clangd-call-tree 文件过滤配置（每个模块独立） |
| `callback.toml` | clangd-call-tree 回调 API 配置（每个模块独立） |
| `call_graph.json` | clangd-call-tree 原始 JSON 输出（邻接表格式） |
| `call_graph.txt` | clangd-call-tree 原始 TXT 输出（缩进树格式） |
| `filtered.json` | 过滤后的调用图 JSON（含源码片段） |
| `report.md` | 调用分析报告（ASIC 可视化 + 函数详情 + 源码） |
| `modification_plan.md` | 修改计划文档 |
| `commit/format.md` | Commit 消息模板（插槽化） |
| `artifacts/run_N/` | 每次 clangd-call-tree 运行的产物隔离目录 |
| `merged/` | 多入口合并产物目录 |

## 3. 数据格式

### 3.1 modules.json

```json
{
  "project_root": "/path/to/project",
  "compile_commands": ".",
  "modules": {
    "ldc": {
      "info": "ldc/info.md",
      "filter_cfg": "ldc/filter.cfg",
      "callback_cfg": "ldc/callback.toml",
      "keywords": ["LDC", "ldc"]
    }
  }
}
```

- `project_root`: 所有模块共享的项目根目录
- `compile_commands`: compile_commands.json 相对于 project_root 的路径
- `modules.<name>`: 每个模块的插槽配置

### 3.2 info.md（模块概况）

每个模块目录下，描述供 sub-agent 检索的源文件：

```markdown
# LDC 模块概况

## 入口函数检索范围

- 头文件: sdk/interface/include/ldc_api.h
- 源文件: sdk/interface/src/ldc/ldc_api.c

## 模块说明

LDC（Lens Distortion Correction）镜头畸变校正模块...
```

### 3.3 call_graph.json（clangd-call-tree 输出）

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

### 3.4 Step 4 输出（filtered_indices）

```json
{
  "entry_function": "MI_LDC_CreateChannel",
  "filtered_indices": [0, 3, 9, 15, 22],
  "filter_reason": {
    "0": "入口函数，必选",
    "3": "通道配置核心逻辑",
    "9": "HW_AUTOSYNC 参数传递路径"
  },
  "excluded_count": 85
}
```

### 3.5 report.md 模板

```markdown
# 调用分析报告: {需求描述}

## 模块概况
<!-- 从 info.md 引入核心概念 -->

## 调用树
<!-- 纯缩进格式，从 filtered.json 生成 -->
root_func (path/file.c:88) - brief
    child_a (path/file.c:42) - brief
        grandchild (path/file.c:10) - brief
    another_child (path/lib.h:5) [EXTERNAL]

## 函数详情

### {func_name} ({path}:{line})
- brief: {brief}
- qualified_name: {qualified_name}
```c
// 源码段落（从 filtered.json 提取）
```

### {func_name_2} ({path}:{line})
- brief: {brief}
- qualified_name: {qualified_name}
...
```

### 3.5.1 调用树格式定义

纯缩进格式，无分支符（├──/└──），精确定义如下：

```
{indent}{name} ({path}:{line}) - {brief}
{indent}{name} ({path}:{line}) - {brief} [EXTERNAL]
```

- **缩进:** 每级 4 空格
- **每行格式:** `{indent}{func_name} ({file_path}:{line_start}) - {brief}`
  - `func_name`: 节点 `self.name`
  - `file_path`: 节点 `self.path`
  - `line_start`: `self.line[0]`（数组首元素，1-based）
  - `brief`: 节点 `self.brief`（可为空；为空时省略 ` - ` 后缀）
- **INTERNAL 节点:** 展开 children（递归输出子树，depth + 1）
- **EXTERNAL 节点:** 行末追加 `[EXTERNAL]`，**不展开** children
- **防环:** 已访问节点跳过（visited 集合）
- **root 节点** depth=0，无缩进

完整示例:
```
MI_LDC_CreateChannel (/abs/path/ldc_api.c:88) - Create LDC channel with config
    MI_LDC_InitConfig (/abs/path/ldc_config.c:22) - Initialize channel config
        validate_params (/abs/path/ldc_config.c:10) - Validate parameter range
    HAL_LDC_SetParam (/abs/hal/ldc_hal.c:150) [EXTERNAL]
    MI_LDC_StartChannel (/abs/path/ldc_api.c:156) - Start processing
```

### 3.6 commit/format.md（Commit 模板，插槽化）

```
[Project][MODULE]{subject}

[rootcause]:{rootcause}
[solution]:{solution}
[sideeffect]:{sideeffect}
[selftestlist]:
1.
2.
3.
[selftestresult]: P
[ticket]:{ticket_type}_{ticket_id}
[redflag]: N
```

模板变量（任选其一填入 ticket 字段）：
- `rdm_task`
- `rdm_issue`
- `mantis_id`
- `sspm_id`
- `comake_id`

## 4. 流程

### Step 0: 用户输入

用户提供自然语言需求描述。例如：

> "帮我修改当前的代码，要求 LDC 支持 HW_AUTOSYNC 多个 chn"

### Step 1: 模块匹配

主 agent 读取 `modules.json`，从用户需求中提取关键词，匹配模块。

- 从需求提取关键词（如 "LDC"）
- 与 `modules.*.keywords` 匹配
- 命中的模块 → 加载对应 `info.md`
- 多关键词命中 → 取交集；无交集 → 语义兜底

### Step 2: 入口函数定位

启动 sub-agent，输入：
- 用户需求描述
- 对应模块的 `info.md` 内容（header/c 文件路径）

Sub-agent 执行：
1. 读 info.md 中指定的 header 文件注释
2. 根据需求语义匹配相关函数
3. 读对应的 C 文件，定位函数定义的行号
4. 输出入口函数信息：`{ func_name, file, line }`

**Python 辅助脚本（列号计算）：**
- 输入：file + line + func_name
- 读该行，找 func_name 的字符偏移 → 输出 col
- 最终拼接：`file:line:col`

**多入口处理：**
- 如果需求涉及多个入口函数 → 列出所有入口
- 后续 step 3-6 对每个入口独立执行（run_0, run_1, ...）
- run 之间产物隔离，不互相覆盖

### Step 3: clangd-call-tree 生成调用关系

对每个入口函数执行：

```bash
python main.py \
  -p <project_root> \
  -e "<file>:<line>:<col>" \
  -f all \
  -c <module_dir>/filter.cfg \
  --callback-config <module_dir>/callback.toml \
  -o artifacts/run_N/call_graph
```

产出：`artifacts/run_N/call_graph.json` + `call_graph.txt`

### Step 4: 调用路径过滤

启动 sub-agent，输入：
- 用户需求描述
- `call_graph.json`（brief + index 字段）

Sub-agent 执行：
- 根据需求语义，筛选与需求真正相关的调用节点
- 输出 `filtered_indices` JSON（含 entry_function、filtered_indices、filter_reason、excluded_count）

**裁决规则：** 交集优先 + brief 语义兜底

**结构性校验（主 agent 执行，非 LLM）：**
- 检查 filtered_indices 中的 index 是否存在于原始 JSON 中
- 如有不存在的 index → 打回 step 4 重做

### Step 5: 精简调用图生成

Python 脚本 `simple_call_graph.py`，输入：
- 原始 `call_graph.json`
- `filtered_indices` 列表
- 源码根路径

执行：
1. 从原始 JSON 中取出 filtered_indices 对应的节点
2. 从每个节点的 `self.path` + `self.line` 读源文件，提取对应代码段
3. 重新建立 filtered 节点之间的 parent/child 关系（仅保留 filtered 集合内的边）
4. 标记 root node（filtered 集合中无有效父节点的节点）

输出：`artifacts/run_N/filtered.json`

### Step 6: 报告文档生成

Python 脚本 `generate_report.py`，输入：
- `filtered.json`
- `info.md` 模块概念

执行：
1. 从 filtered.json 生成 ASIC 可视化调用树（缩进文本格式）
2. 为每个函数生成详情：func_name、path:line、brief、源码段
3. 从 info.md 引入模块基本概念

输出：`artifacts/run_N/report.md`

### Step 6.5: 多入口合并（如有）

如果存在多个 run（run_0, run_1, ...）：
1. 合并所有 `report.md` → `merged/report.md`
2. 合并所有 `filtered.json` → `merged/filtered.json`
3. 去重重叠的函数节点

后续 step 7-12 基于 `merged/report.md`（或单个 `report.md`）执行。

### Step 7: 修改计划分析

启动 sub-agent，输入：
- 原始需求描述
- `report.md`

Sub-agent 执行：
- 分析调用树，定位需要修改的函数/位置
- 输出 `modification_plan.md`（包含原始需求摘要、分析结论、具体修改位置和内容）

### Step 7.5: 结构性校验

主 agent 执行（纯规则，不调 LLM）：
- 检查 modification_plan.md 中引用的函数名是否存在于 filtered.json 中
- 检查修改位置的文件路径+行号是否合法
- **通过** → 进入 step 8
- **失败** → 打回 step 7 重做，附带校验错误信息

### Step 8: Linus Reviewer 审查

启动 sub-agent（Linus Reviewer），输入：
- 原始需求描述
- `report.md`
- `modification_plan.md`

审查标准（按优先级）：
1. 修改计划是否完整覆盖原始需求的所有关键点
2. 修改位置是否准确（函数、文件、行号）
3. 修改逻辑是否合理，有无副作用遗漏
4. 是否需要额外的错误处理/边界检查

**最大 3 轮。** 每轮：
- approve → 进入 step 9
- reject → 打回 step 7，附带 reject 理由

3 轮不通过 → 降级为"需要人工介入"，停止自动流程。

### Step 9: 代码实现

启动 sub-agent（实现），输入：
- `modification_plan.md`（approved）
- `report.md`

Sub-agent 执行：
- 按 modification_plan.md 修改代码
- 输出修改后的代码

### Step 10: 用户确认

主 agent 向用户展示修改结果摘要，请求确认：
- YES → 进入 step 11
- NO → 停止，用户自行处理

**确认渠道：** Claude Code 交互窗口（YES/NO）/ OpenClaw webchat / Telegram

### Step 11: Commit

启动 sub-agent（commit），输入：
- 修改的文件列表
- `commit/format.md` 模板
- 模板变量（从用户输入或 modification_plan 中提取）

Sub-agent 执行：
1. 读取 `.repo/manifest.xml` → 确定涉及的 git 仓库路径
2. 检测涉及的仓库数量
   - 单仓库 → 一个 commit
   - 多仓库 → 按仓库拆分为多个 commit
3. 自主补充 commit message（模板 + 变量）
4. 执行 git add + commit

**模板变量来源：**
- `ticket_type` + `ticket_id`: 从用户输入获取（rdm_task/rdm_issue/mantis_id/sspm_id/comake_id 任选其一）
- `subject`: 从 modification_plan 推断
- `rootcause` / `solution` / `sideeffect`: 从 modification_plan 提取
- `selftestlist` / `selftestresult` / `redflag`: 由 sub-agent 自主填写

### Step 12: 清理与总结

主 agent 执行：
1. 清理中间产物：`artifacts/run_*/` 、`merged/` 全部删除
2. 生成最终总结（需求、修改内容、涉及文件、commit 信息）
3. 输出给用户

## 5. 目录结构

```
clangd-call-tree-skill/
├── SKILL.md                    # 主入口（通用，兼容 Claude Code）
├── CLAUDE.md                   # symlink → SKILL.md
├── modules.json                # 模块配置
├── scripts/
│   ├── find_column.py          # 列号计算辅助脚本
│   ├── simple_call_graph.py    # Step 5: 精简调用图生成
│   └── generate_report.py      # Step 6: 报告文档生成
├── templates/
│   └── commit/
│       └── format.md           # Commit 模板（插槽化）
├── ldc/                        # 模块插槽示例
│   ├── info.md                 # 模块概况
│   ├── filter.cfg              # 文件过滤配置
│   └── callback.toml           # 回调 API 配置
├── venc/                       # 另一个模块插槽
│   ├── info.md
│   ├── filter.cfg
│   └── callback.toml
└── artifacts/                  # 运行时产物（需求完成后清理）
    ├── run_0/
    │   ├── call_graph.json
    │   ├── call_graph.txt
    │   └── filtered.json
    ├── run_1/
    │   └── ...
    └── merged/
        ├── report.md
        └── filtered.json
```

## 6. 约束

1. **用户零干预** — 仅在 Step 0（输入需求）和 Step 10（结果验收）参与
2. **插槽化** — 模块（info/filter/callback）和 commit 模板均可替换
3. **产物隔离** — 多次 run 使用独立目录，不互相覆盖
4. **产物清理** — 每个需求完成后清除 artifacts/ 和 merged/
5. **审查上限** — Linus Reviewer 最多 3 轮，不通过则降级人工
6. **单需求单 commit** — 一个需求对应一个 commit；多仓库则拆分
7. **移植性** — SKILL.md 作为通用主入口，可移植到 Claude Code 等环境
