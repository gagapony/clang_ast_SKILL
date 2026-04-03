# SKILL.md — clangd-call-tree-skill

> 基于 clangd-call-tree 的代码调用路径分析与自动修改 Skill

## ⚠️ 硬约束

**你是流程执行器，不是代码搜索器。**

### 禁止
- 跳过、合并、重排任何 Step
- 禁止中途停止，如有用户确认的点，需要主动向客户弹出 `AskUserQuestion tool` 交互窗口

### 强制
- 每个 Step 按顺序执行，等脚本输出再进下一步
- Step 3 必须用 `scripts/clang_ast/main.py`
- Step 4 喂入 `call_graph_keypoint.json`，不喂 `call_graph.json`
- Step 8 修改位置必须来自 `report.md`
- 用 read/grep **理解代码内容**（宏、枚举、类型）允许，**定位代码**禁止

**判断标准：** "改哪里" → 脚本输出。"改什么" → 阅读理解。违反 = 停止，重做该 Step。

---

## 流程总览

```
Step 0   用户输入需求
          ↓
Step 1   读 modules/module.json → 匹配模块
          ↓
Step 2   sub-agent: 从 info.md 函数目录匹配入口 → find_column.py
          ↓ 
Step 3   ★ scripts/clang_ast/main.py 生成 call_graph.json ★
          ↓ [验证门: 文件存在且非空]
Step 4   extract_keypoint.py → call_graph_keypoint.json (index + brief)
          ↓
Step 5   sub-agent: 基于 keypoint 过滤 → filtered_indices.json
          ↓ [验证门: index 是否存在于 call_graph.json]
Step 6   simple_call_graph.py → filtered.json
          ↓
Step 7   generate_report.py → report.md
          ↓ [多入口? → merge_reports.py → merged/]
Step 8   sub-agent: 基于 report.md 制定修改计划
          ↓ [验证门: 函数名是否存在于 filtered.json]
Step 9   Linus Reviewer 审查 (最多 3 轮)
          ↓
Step 10  sub-agent: 按修改计划实现
          ↓
Step 11  用户确认
          ↓
Step 12  commit
          ↓
Step 13  清理 artifacts/ merged/
```

---

## 前置条件

1. `modules/module.json` 已配置（从 `modules/module.json.example` 复制）
2. 目标模块有 `info.md`、`filter.cfg`、`callback.toml`
3. 项目有 `compile_commands.json`
4. 安装了 `clangd` 和 Python 3.8+
5. `scripts/clang_ast/` 含 `main.py` + `src/`

---

## 目录结构

```
clangd-call-tree-skill/
├── SKILL.md
├── CLAUDE.md → SKILL.md
├── scripts/
│   ├── clang_ast/                    # clangd-call-tree 工具
│   │   ├── main.py
│   │   └── src/
│   ├── find_column.py                # Step 2: 列号计算
│   ├── extract_keypoint.py           # Step 4: 提取 index+brief
│   ├── simple_call_graph.py          # Step 6: 精简调用图
│   ├── generate_report.py            # Step 7: 报告生成
│   └── merge_reports.py              # Step 7: 多入口合并
├── modules/
│   ├── module.json.example
│   ├── demo/
│   ├── ldc/
│   └── venc/
├── templates/commit/
│   └── format.md
├── artifacts/                        # 运行时产物 (完成后清理)
└── merged/                           # 合并产物 (完成后清理)
```

---

## Step 0: 用户输入

用户提供自然语言需求。

主 agent 解析需求，提取关键词供 Step 1 使用。

---

## Step 1: 模块匹配

**执行者：** 主 agent

1. 读取 `modules/module.json`
2. 从需求提取关键词
3. 匹配 `modules.*.keywords`
4. 命中 → 加载 `info.md`

多关键词：取交集；无交集 → 语义兜底。

**输出：** 模块名、info.md 路径、filter_cfg 路径、callback_cfg 路径、project_root

---

## Step 2: 入口函数定位

**执行者：** sub-agent

### Prompt 模板（固定，主 agent 禁止修改模板内容，只填 `{{}}` 占位符）

```
你是代码分析专家。按以下流程执行：

1. 阅读下方"参考文档"和"入口函数目录"，理解模块上下文
2. 结合需求关键词，选出最贴合需求的函数作为入口点
3. 仅从目录中选择，禁止输出目录外的函数
4. 禁止使用任何文件读取或搜索工具，所有必要信息已在下方完整提供

## 需求
{{USER_REQUIREMENT}}

## 关键词（从需求提取）
{{KEYWORDS}}

## 参考文档（info.md 引用的相关源文件内容，供理解函数签名和上下文）
{{REFERENCE_DOCS}}

## 入口函数目录（从 info.md 提取，这是唯一候选池）
{{ENTRY_FUNC_CATALOG}}

## 输出格式（严格 JSON，禁止额外文字）
{
  "entry_functions": [
    {"func_name": "xxx", "file": "path/file.c", "line": 100}
  ],
  "reasoning": "选择理由"
}
```

### 主 agent 操作

1. 提取关键词 → 填 `{{KEYWORDS}}`
2. 原样传递用户需求 → 填 `{{USER_REQUIREMENT}}`
3. 从 info.md 提取 `## Step2 Config` 段落：
   - 查找 `### 入口函数目录` 及其下方所有表格内容
   - 保留表头、所有函数行、文件归属标题（`#### 文件名`）
   - 整段填入 `{{ENTRY_FUNC_CATALOG}}`
   - **禁止对目录内容做删减或概括**
   - 如果 info.md 无 `## Step2 Config` → 报错停止，要求补充
4. 预读 info.md 中引用的文档 → 填 `{{REFERENCE_DOCS}}`：
   - 从 info.md 的 `### Entry扩散文件` 段落提取文件列表
   - 从 info.md 的 `## 入口函数检索范围` 段落提取头文件/源文件路径
   - 从 info.md 的 `## 参考文档` 段落提取额外文档路径（如有）
   - 所有路径相对于 `{project_root}` 解析
   - 逐一 `read` 每个文件，格式化拼接：
     ```
     ### {文件名} ({相对路径})
     {文件完整内容}

     ---
     ```
   - 如果某个文件不存在 → 标注 `[文件未找到: {路径}]`，不中断流程
   - 如果无引用文档 → 填 `无额外参考文档`
5. **禁止改模板其他部分**

### 后处理

```bash
python3 scripts/find_column.py \
  --file "{project_root}/{file}" \
  --line {line} \
  --func "{func_name}"
```

拼接入口点：`{file}:{line}:{col}`

多入口 → 后续 Step 3-7 对每个独立执行（run_0, run_1, ...）

---

## Step 3: 调用图生成

**执行者：** 主 agent（shell）

```bash
cd {SKILL_DIR}
mkdir -p artifacts/run_{N}

python3.12 scripts/clang_ast/main.py \
  -p {project_root} \
  -e "{file}:{line}:{col}" \
  -f all \
  -c {filter_cfg} \
  --callback-config {callback_cfg} \
  -d 10 \
  -o artifacts/run_{N}/call_graph
```

**产出：** `artifacts/run_{N}/call_graph.json` + `call_graph.txt`

### 验证门

```bash
python3 -c "
import json
data = json.load(open('artifacts/run_{N}/call_graph.json'))
assert len(data) > 0, 'empty'
print(f'OK: {len(data)} nodes')
"
```

失败 → 排查 clang_ast 配置。**不得跳过。**

### 错误处理

- 失败 → 检查 `compile_commands.json` / clangd 安装
- 空输出 → 检查 `filter.cfg` 是否覆盖目标文件

---

## Step 4: 调用图精简

**执行者：** 主 agent（脚本）

```bash
python3 scripts/extract_keypoint.py \
  --input artifacts/run_{N}/call_graph.json \
  --output artifacts/run_{N}/call_graph_keypoint.json
```

**产出：** `artifacts/run_{N}/call_graph_keypoint.json`

每个节点只保留 `index` + `brief`：

```json
[
  {"index": 0, "brief": "创建 LDC 通道"},
  {"index": 1, "brief": "null"}
]
```

其他字段（name, file, tag, path, line）可通过 index 从 `call_graph.json` 还原。

### 验证门

```bash
python3 -c "
import json
data = json.load(open('artifacts/run_{N}/call_graph_keypoint.json'))
assert len(data) > 0, 'empty'
print(f'OK: {len(data)} nodes')
"
```

**Step 5 的 sub-agent 喂入 `call_graph_keypoint.json`，不喂 `call_graph.json`。**

---

## Step 5: 调用路径过滤

**执行者：** sub-agent

### 约束

- 只能基于 `call_graph_keypoint.json` 过滤
- 禁止自行搜索项目源码
- 必须以 keypoint 中的 index 为基准筛选

### Sub-agent Prompt

```
你是代码分析专家。根据需求，从调用图关键点中筛选相关路径。

## 需求
{用户需求}

## 入口函数
{entry_function}

## 调用图关键点
每个节点: index (唯一标识), brief (函数描述或 null)

{call_graph_keypoint.json 内容}

## 任务
分析 brief，判断是否与需求相关。保留相关节点，排除无关。

## 输出 (JSON)
{
  "entry_function": "{入口函数名}",
  "filtered_indices": [相关 index 列表],
  "filter_reason": {"index": "保留理由"},
  "excluded_count": 排除数
}

## 判断规则
1. 入口函数本身 → 必选
2. 需求关键词直接相关 → 必选
3. 数据传递链中间函数 → 必选
4. 通用工具函数 (log, delay, malloc) → 排除
5. 不相关第三方库 → 排除
6. brief 为 null 且无法判断 → 排除
```

### 验证门

```bash
python3 -c "
import json
original = json.load(open('artifacts/run_{N}/call_graph.json'))
filtered = json.load(open('artifacts/run_{N}/filtered_indices.json'))
valid = {n['index'] for n in original}
invalid = [i for i in filtered['filtered_indices'] if i not in valid]
if invalid:
    print(f'Invalid indices: {invalid}')
    exit(1)
print('OK')
"
```

失败 → 打回 Step 5。

---

## Step 6: 精简调用图

**执行者：** 主 agent（脚本）

```bash
python3 scripts/simple_call_graph.py \
  --original artifacts/run_{N}/call_graph.json \
  --indices artifacts/run_{N}/filtered_indices.json \
  --source {project_root} \
  --output artifacts/run_{N}/filtered.json
```

**产出：** `artifacts/run_{N}/filtered.json`（过滤后节点 + 边 + 源码片段）

---

## Step 7: 报告生成

**执行者：** 主 agent（脚本）

```bash
python3 scripts/generate_report.py \
  --filtered artifacts/run_{N}/filtered.json \
  --info {info_md_path} \
  --output artifacts/run_{N}/report.md \
  --requirement "{用户需求}"
```

**产出：** `artifacts/run_{N}/report.md`（调用树 + 函数详情 + 源码片段）

如有多个 run（多入口），合并：

```bash
python3 scripts/merge_reports.py \
  --runs artifacts/run_0 artifacts/run_1 ... \
  --output merged/
```

**产出：** `merged/filtered.json` + `merged/report.md`

后续 Step 8-13 使用 `merged/report.md`（或单个 `report.md`）

---

## Step 8: 修改计划

**执行者：** sub-agent

### 约束

- 修改位置（函数、文件、行号）必须来自 `report.md` — **禁止用 grep/find 定位**
- 允许 read/grep 查阅宏定义、枚举、类型定义等**上下文**
- 判断依据："理解代码" → 允许。"找代码" → 禁止。

### Sub-agent Prompt

```
你是高级代码分析师。根据报告和需求，制定修改计划。

## 需求
{用户需求}

## 调用分析报告
{report.md 内容}

## 任务
1. 分析调用树，理解执行路径
2. 定位修改位置
3. 制定修改方案

## 输出 (Markdown)
# 修改计划: {需求}

## 原始需求摘要
- 需求: {需求}
- 涉及模块: {模块}

## 分析结论
{为什么需要修改这些位置}

## 修改位置

### 修改 1: {简述}
- 文件: {path}
- 函数: {func_name}
- 行号: {line}
- 当前逻辑: {描述}
- 修改方案: {描述}
- 原因: {为什么}
```

### 验证门

```bash
python3 -c "
import json, re
with open('modification_plan.md') as f:
    plan = f.read()
funcs_in_plan = set(re.findall(r'函数[：:]\s*(\S+)', plan))
with open('merged/filtered.json') as f:
    data = json.load(f)
valid_funcs = {n['self']['name'] for n in data['nodes']}
invalid = funcs_in_plan - valid_funcs
if invalid:
    print(f'Not in call graph: {invalid}')
    exit(1)
print('OK')
"
```

失败 → 打回 Step 8。

---

## Step 9: Linus Reviewer 审查

**执行者：** sub-agent（Linus Reviewer）

### Prompt

```
你是 Linus Reviewer。零容忍审查。

## 需求
{用户需求}

## 报告
{report.md 内容}

## 修改计划
{modification_plan.md 内容}

## 审查标准
1. 是否完整覆盖需求所有关键点
2. 修改位置是否准确（函数、文件、行号与 report.md 一致）
3. 修改逻辑是否合理，有无副作用遗漏

## 输出
- APPROVE: "APPROVED" + 总结
- REJECT: 具体问题 + 原因
- 3 轮不通过 → "ESCALATE: 需要人工介入"
```

- APPROVE → Step 10
- REJECT → 打回 Step 8（最多 3 轮）
- ESCALATE → 停止

---

## Step 10: 代码实现

**执行者：** sub-agent

### 约束

- 只修改 `modification_plan.md` 列出的文件和行号
- 禁止修改计划外文件
- 实现前先读目标文件确认上下文

### Prompt

```
你是代码实现专家。按修改计划修改代码。

## 修改计划
{modification_plan.md (approved)}

## 报告
{report.md 内容}

## 任务
按计划执行修改，修改前先读当前代码确认上下文。

## 输出
## 修改完成

### 修改 1: {简述}
- 文件: {path}
- 修改前: {关键片段}
- 修改后: {关键片段}

## 约束
- 只改计划指定位置
- 保持代码风格一致
- 确保修改后可编译
```

---

## Step 11: 用户确认

**执行者：** 主 agent → 用户

```markdown
## 修改确认

**需求:** {需求}
**修改内容:** {Step 10 摘要}
**涉及文件:**
- file1.c (N 行)
- file2.h (N 行)

**使用 AskUserQuestion tool 询问是否确认修改: YES / NO**
```

YES → Step 12。NO → 停止。

---

## Step 12: Commit

**执行者：** sub-agent

```
你是 Git 提交专家。按模板提交。

## 修改内容
{Step 10 输出}

## 模板
{templates/commit/format.md 内容}

## 模板变量
- 项目名: {项目名}
- 模块名: {模块名}
- ticket: rdm_task / rdm_issue / mantis_id / sspm_id / comake_id

## 约束
- 只能使用英文
- commit msg 不得超过300字符
- 一定确认到有ticket 才能继续提交

## 任务
1. 读 .repo/manifest.xml 确定涉及的 git 仓库
2. 单仓库 → 一个 commit；多仓库 → 按仓库拆分
3. 进入到符合.repo/manifest.xml 的 git 仓库
4. 按模板生成 commit message
5. git add + git commit
```

---

## Step 13: 清理与总结

**执行者：** 主 agent

```bash
rm -rf artifacts/ merged/
```

```markdown
## 任务完成

**需求:** {需求}
**模块:** {模块名}
**入口:** {entry_function(s)}
**修改文件:**
- {file1} (N 行)
- {file2} (N 行)
**Commit:** {hash} - {subject}
```

---

## 错误处理

| 场景 | 处理 |
|------|------|
| module.json 不存在 | 提示从 .example 复制 |
| 模块匹配失败 | 列出可用模块，提示选择 |
| 入口函数定位失败 | 列出 info.md 候选函数 |
| clang_ast 失败 | 检查 compile_commands.json / clangd |
| Step 5 过滤为空 | 降低过滤粒度 |
| Step 8 校验失败 | 附带错误打回 |
| Step 9 轮次超限 | ESCALATE，停止 |
| Step 11 用户 NO | 停止，保留代码 |
| Step 12 多仓库 | 按 manifest.xml 拆分 commit |

## 路径参考

| 变量 | 说明 | 示例 |
|------|------|------|
| `SKILL_DIR` | Skill 根目录 | `~/.openclaw/code/projects/clangd-call-tree-skill/` |
| `project_root` | 项目根目录 | 从 `modules/module.json` 读取 |
| `module_dir` | 模块目录 | `{SKILL_DIR}/modules/{module_name}/` |
