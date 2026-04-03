# SKILL.md — clangd-call-tree-skill

## ⚡ 激活规则（最高优先级）

**当用户提出代码修改需求时，你是一个严格的流程执行器。禁止自行 grep/search 代码。**

### 你的第一个动作（二选一）：

- **新需求** → 执行 `bash {SKILL_DIR}/scripts/orchestrator.sh init "用户需求"`
- **中断恢复** → 执行 `bash {SKILL_DIR}/scripts/orchestrator.sh next`，从断点继续

### 每个 Step 完成后的强制动作（两步，不可省略）：

```bash
# 1. 保存关键变量到状态文件
bash {SKILL_DIR}/scripts/orchestrator.sh set <key> <value>

# 2. 标记步骤完成，推进到下一步
bash {SKILL_DIR}/scripts/orchestrator.sh done-step <step号>
```

---

## 🔴 红线（违反 = 停止重做）

1. **禁止 grep/rg/fd/find/search 搜索代码定位** — "在哪里"由脚本输出告诉你
2. **禁止跳步** — 每个 step 完成后必须 `done-step`
3. **禁止手动拼 python 命令** — 所有脚本走 `pipeline.sh`
4. **禁止自行定位修改位置** — Step 8 位置必须来自 `report.md`
5. 允许 read 代码来**理解**宏/枚举/类型，但**不能用来定位函数在哪**
6. **每完成一个 step，必须 `set` + `done-step`**，防止上下文丢失时无法恢复

---

## Step 0: 用户输入

用户提供自然语言需求。主 agent 解析需求，提取关键词。

```bash
bash {SKILL_DIR}/scripts/orchestrator.sh init "用户需求"
```

**Checkpoint：**
```bash
bash {SKILL_DIR}/scripts/orchestrator.sh done-step 0
```

---

## Step 1: 模块匹配

1. 读取 `modules/module.json`
2. 从需求提取关键词
3. 匹配 `modules.*.keywords`
4. 命中 → 加载 `info.md`

**Checkpoint：**
```bash
bash {SKILL_DIR}/scripts/orchestrator.sh set module "{模块名}"
bash {SKILL_DIR}/scripts/orchestrator.sh set project_root "{project_root}"
bash {SKILL_DIR}/scripts/orchestrator.sh set info_md "{info_md_path}"
bash {SKILL_DIR}/scripts/orchestrator.sh set filter_cfg "{filter_cfg}"
bash {SKILL_DIR}/scripts/orchestrator.sh set callback_cfg "{callback_cfg}"
bash {SKILL_DIR}/scripts/orchestrator.sh done-step 1
```

---

## Step 2: 入口函数定位

**执行者：** sub-agent

### 主 agent 准备（spawn 之前完成）

1. 提取关键词 → `{{KEYWORDS}}`
2. 原样需求 → `{{USER_REQUIREMENT}}`
3. 从 info.md 提取 `## Step2 Config` → `### 入口函数目录` 整段 → `{{ENTRY_FUNC_CATALOG}}`
   - 无 `## Step2 Config` → 报错停止
4. 预读引用文档 → `{{REFERENCE_DOCS}}`：
   - 从 `### Entry扩散文件` / `## 入口函数检索范围` / `## 参考文档` 提取路径
   - 相对 `{project_root}` 解析，逐一 read
   - 格式：`### {文件名} ({路径})\n{内容}\n---`
   - 文件不存在 → `[文件未找到]`，不中断

### Sub-agent Prompt（固定模板）

```
你是代码分析专家。
1. 阅读"参考文档"和"入口函数目录"
2. 选出最贴合需求的函数作为入口点
3. 仅从目录中选择，禁止输出目录外的函数
4. 禁止使用任何文件读取或搜索工具

## 需求
{{USER_REQUIREMENT}}

## 关键词
{{KEYWORDS}}

## 参考文档
{{REFERENCE_DOCS}}

## 入口函数目录（唯一候选池）
{{ENTRY_FUNC_CATALOG}}

## 输出（严格 JSON）
{
  "entry_functions": [
    {"func_name": "xxx", "file": "path/file.c", "line": 100}
  ],
  "reasoning": "选择理由"
}
```

### 后处理

```bash
mkdir -p {SKILL_DIR}/artifacts/run_{N}
python3 {SKILL_DIR}/scripts/find_column.py \
  --file "{project_root}/{file}" --line {line} --func "{func_name}"
```

**Checkpoint：**
```bash
bash {SKILL_DIR}/scripts/orchestrator.sh set entry_function "{func_name}"
bash {SKILL_DIR}/scripts/orchestrator.sh set entry_point "{file}:{line}:{col}"
bash {SKILL_DIR}/scripts/orchestrator.sh set run_count "{N}"
bash {SKILL_DIR}/scripts/orchestrator.sh done-step 2
```

---

## Step 3+4: 调用图 + 精简

```bash
bash {SKILL_DIR}/scripts/pipeline.sh step3-4 \
  "{project_root}" "{entry_point}" "{filter_cfg}" "{callback_cfg}" "run_{N}"
```

**Checkpoint：**
```bash
bash {SKILL_DIR}/scripts/orchestrator.sh done-step 3-4
```

---

## Step 5: 调用路径过滤

**执行者：** sub-agent

### 约束
- 只基于 `call_graph_keypoint.json`，禁止搜索源码

### Sub-agent Prompt

```
你是代码分析专家。根据需求筛选调用图关键点。

## 需求
{用户需求}

## 入口函数
{entry_function}

## 调用图关键点（index + brief）
{call_graph_keypoint.json 内容}

## 输出（严格 JSON）
{
  "entry_function": "{入口函数名}",
  "filtered_indices": [相关 index 列表],
  "filter_reason": {"index": "保留理由"},
  "excluded_count": 排除数
}

## 判断规则
1. 入口函数 → 必选
2. 需求关键词直接相关 → 必选
3. 数据传递链中间函数 → 必选
4. 通用工具函数 (log, delay, malloc) → 排除
5. 不相关第三方库 → 排除
6. brief 为 null 且无法判断 → 排除
```

**写入 filtered_indices.json 后验证：**
```bash
bash {SKILL_DIR}/scripts/pipeline.sh verify-step5 "run_{N}"
```

**Checkpoint：**
```bash
bash {SKILL_DIR}/scripts/orchestrator.sh done-step 5
```

---

## Step 6+7: 精简图 + 报告

```bash
bash {SKILL_DIR}/scripts/pipeline.sh step6-7 \
  "{project_root}" "{info_md_path}" "{用户需求}" "run_{N}"
```

多入口合并：
```bash
bash {SKILL_DIR}/scripts/pipeline.sh merge run_0 run_1 ...
```

**Checkpoint：**
```bash
bash {SKILL_DIR}/scripts/orchestrator.sh set report_path "{SKILL_DIR}/artifacts/run_{N}/report.md"
bash {SKILL_DIR}/scripts/orchestrator.sh done-step 6-7
```

---

## Step 8: 修改计划

**执行者：** sub-agent

### 约束
- 位置必须来自 `report.md`，禁止 grep/find 定位

### Sub-agent Prompt

```
你是高级代码分析师。根据报告制定修改计划。

## 需求
{用户需求}

## 调用分析报告
{report.md 内容}

## 输出 (Markdown)
# 修改计划: {需求}

## 分析结论
{原因}

## 修改位置
### 修改 1: {简述}
- 文件: {path}
- 函数: {func_name}
- 行号: {line}
- 当前逻辑: {描述}
- 修改方案: {描述}
```

**验证：**
```bash
bash {SKILL_DIR}/scripts/pipeline.sh verify-step8 "run_{N}"
```

**Checkpoint：**
```bash
bash {SKILL_DIR}/scripts/orchestrator.sh done-step 8
```

---

## Step 9: Linus Reviewer

```
你是 Linus Reviewer。零容忍审查。

## 需求 / 报告 / 修改计划
{三者内容}

## 输出
- APPROVE: "APPROVED" + 总结
- REJECT: 问题 + 原因
- 3 轮不通过 → "ESCALATE: 需要人工介入"
```

- APPROVE → Step 10
- REJECT → 打回 Step 8（最多 3 轮）

**Checkpoint：**
```bash
bash {SKILL_DIR}/scripts/orchestrator.sh done-step 9
```

---

## Step 10: 代码实现

```
你是代码实现专家。按修改计划修改代码。

## 修改计划
{modification_plan.md}

## 报告
{report.md}

## 约束
- 只改计划指定位置
- 修改前先读当前代码确认上下文
- 保持代码风格一致
```

**Checkpoint：**
```bash
bash {SKILL_DIR}/scripts/orchestrator.sh done-step 10
```

---

## Step 11: 用户确认

向用户展示修改摘要，**使用 AskUserQuestion tool 询问 YES/NO**。

YES → Step 12。NO → 停止。

**Checkpoint：**
```bash
bash {SKILL_DIR}/scripts/orchestrator.sh done-step 11
```

---

## Step 12: Commit

```
你是 Git 提交专家。按模板提交。

## 模板
{templates/commit/format.md}

## 约束
- 只能英文，commit msg ≤ 300 字符
- 必须有 ticket 才能提交
- 多仓库按 manifest.xml 拆分
```

**Checkpoint：**
```bash
bash {SKILL_DIR}/scripts/orchestrator.sh done-step 12
```

---

## Step 13: 清理与总结

```bash
bash {SKILL_DIR}/scripts/pipeline.sh clean
bash {SKILL_DIR}/scripts/orchestrator.sh done-step 13
```

输出最终总结：需求、模块、入口函数、修改文件、commit hash。

---

## 错误处理

| 场景 | 处理 |
|------|------|
| module.json 不存在 | 提示从 .example 复制 |
| 模块匹配失败 | 列出可用模块，提示选择 |
| pipeline 失败 | 检查 compile_commands.json / clangd / filter.cfg |
| Step 5 过滤为空 | 降低过滤粒度 |
| Step 8 校验失败 | 附带错误打回 |
| Step 9 轮次超限 | ESCALATE，停止 |
| Step 11 用户 NO | 停止，保留代码 |
| **AI 中途停止** | **用户重新发消息，AI 读 `orchestrator.sh next` 恢复** |

## 路径参考

| 变量 | 说明 |
|------|------|
| `SKILL_DIR` | Skill 根目录（实际安装路径） |
| `project_root` | 从 `modules/module.json` 读取 |
| `module_dir` | `{SKILL_DIR}/modules/{module_name}/` |
