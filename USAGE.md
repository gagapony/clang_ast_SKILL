# clangd-call-tree-skill 使用指南

## 1. 安装

### 1.1 前置依赖

```bash
# clangd (LLVM 语言服务器)
sudo apt install clangd          # Ubuntu/Debian
brew install clangd               # macOS

# Python 3.8+
python3 --version

# clangd-call-tree 工具
cd ~
git clone <clangd-call-tree-repo-url>
cd clangd-call-tree
pip install -r requirements.txt   # 如有依赖
```

### 1.2 复制 Skill 到项目

```bash
# 方式 A: 直接放在项目根目录
cp -r /path/to/clangd-call-tree-skill /your-project/.skills/clangd-call-tree

# 方式 B: 放在全局目录（Claude Code 全局配置）
cp -r /path/to/clangd-call-tree-skill ~/.claude/skills/clangd-call-tree
```

### 1.3 配置模块

```bash
cd /your-project/.skills/clangd-call-tree   # 或你选择的路径

# 复制配置模板
cp modules/module.json.example modules/module.json

# 编辑 modules/module.json
```

**modules/module.json 示例：**

```json
{
  "project_root": "/home/user/your-project",
  "compile_commands": ".",
  "modules": {
    "ldc": {
      "info": "modules/ldc/info.md",
      "filter_cfg": "modules/ldc/filter.cfg",
      "callback_cfg": "modules/ldc/callback.toml",
      "keywords": ["LDC", "ldc", "畸变"]
    }
  }
}
```

需要改的地方：
- `project_root`: 你的项目根目录（compile_commands.json 所在目录）
- `modules`: 根据实际项目添加/修改模块

### 1.4 配置模块插槽

每个模块需要三个文件：

**info.md** — 告诉 AI 去哪里找入口函数：
```markdown
# LDC 模块概况

## 入口函数检索范围
- 头文件: sdk/interface/include/ldc_api.h
- 源文件: sdk/interface/src/ldc/ldc_api.c

## 模块说明
LDC 镜头畸变校正模块，支持多通道配置...
```

**filter.cfg** — 告诉 clangd-call-tree 分析哪些文件：
```
+sdk/interface/src/ldc/
+sdk/interface/include/
```

**callback.toml** — 回调 API 配置（如模块使用了回调机制）：
```toml
# 如果模块没有回调，留空即可
```

### 1.5 验证工具

`scripts/clang_ast/` 目录已包含 clangd-call-tree 工具（`main.py` + `src/`），无需额外配置路径。

验证：
```bash
cd /your-project/.skills/clangd-call-tree
python3.12 scripts/clang_ast/main.py --help
```

---

## 2. 在 Claude Code 中使用

### 2.1 方式一：项目级 Skill（推荐）

将 skill 放在项目目录下，Claude Code 会自动读取：

```
your-project/
├── .claude/
│   └── CLAUDE.md          # 引用 skill
├── .skills/
│   └── clangd-call-tree/  # skill 目录
│       ├── SKILL.md
│       ├── CLAUDE.md → SKILL.md
│       ├── modules/
│       │   └── module.json
│       └── ...
└── src/
    └── ...
```

在 `.claude/CLAUDE.md` 中添加：

```markdown
# Skills
请读取 .skills/clangd-call-tree/SKILL.md 了解可用的代码分析能力。
```

### 2.2 方式二：全局 Skill

将 skill 放在全局目录：

```
~/.claude/
├── CLAUDE.md              # 全局配置
└── skills/
    └── clangd-call-tree/
        ├── SKILL.md
        └── ...
```

在 `~/.claude/CLAUDE.md` 中添加：

```markdown
# Skills
- clangd-call-tree: 代码调用路径分析工具，见 ~/.claude/skills/clangd-call-tree/SKILL.md
```

### 2.3 方式三：直接引用

不放 CLAUDE.md，每次手动告诉 Claude Code：

```
请读取 /path/to/clangd-call-tree-skill/SKILL.md，然后按流程帮我分析代码。
需求：LDC 支持 HW_AUTOSYNC 多个 chn
```

---

## 3. 使用示例

### 基本用法

在 Claude Code 对话中输入：

```
帮我修改当前代码，要求 LDC 支持 HW_AUTOSYNC 多个 chn
```

Claude Code 会自动：
1. 匹配 LDC 模块
2. 定位入口函数（如 `MI_LDC_CreateChannel`）
3. 生成调用图
4. 过滤相关路径
5. 分析修改位置
6. 实现修改
7. 提交代码

### 添加新模块

```bash
# 1. 创建模块目录
mkdir -p .skills/clangd-call-tree/modules/venc

# 2. 编写 info.md
cat > .skills/clangd-call-tree/modules/venc/info.md << 'EOF'
# VENC 模块概况

## 入口函数检索范围
- 头文件: sdk/interface/include/venc_api.h
- 源文件: sdk/interface/src/venc/venc_api.c

## 模块说明
视频编码模块...
EOF

# 3. 创建 filter.cfg
echo "+sdk/interface/src/venc/" > .skills/clangd-call-tree/modules/venc/filter.cfg
touch .skills/clangd-call-tree/modules/venc/callback.toml

# 4. 更新 modules/module.json，添加 venc 模块
```

然后就可以用：
```
帮我修改 VENC 编码参数，支持 4K 分辨率
```

### 自定义 Commit 模板

编辑 `templates/commit/format.md`：

```
[{project}][{module}] {subject}

原因: {rootcause}
方案: {solution}
影响: {sideeffect}
自测: {selftestresult}
问题单: {ticket}
```

---

## 4. 故障排查

| 问题 | 排查 |
|------|------|
| "modules/module.json not found" | 确认已 `cp modules/module.json.example modules/module.json` 并配置 |
| "compile_commands.json not found" | 确认 `project_root` 指向正确目录 |
| "clangd not found" | 安装 clangd: `sudo apt install clangd` |
| "Function not found" | 检查 info.md 中的头文件/源文件路径是否正确 |
| "No valid runs found" | 检查 artifacts/ 目录是否有产物 |
| 入口函数定位错误 | 检查 info.md 中的注释是否足够详细 |
