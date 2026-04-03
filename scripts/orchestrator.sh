#!/usr/bin/env bash
# orchestrator.sh — 状态机驱动的流程编排器
#
# 用法:
#   bash orchestrator.sh init "用户需求"
#   bash orchestrator.sh status
#   bash orchestrator.sh next              # 提示当前步骤
#   bash orchestrator.sh done-step <step>  # 标记步骤完成
#   bash orchestrator.sh set <key> <value> # 写入状态变量
#   bash orchestrator.sh get <key>         # 读取状态变量
#   bash orchestrator.sh reset             # 清除所有状态

set -euo pipefail

SKILL_DIR="$(cd "$(dirname "$0")/.." && pwd)"
STATE_FILE="${SKILL_DIR}/.state.json"

die() { echo "FAIL: $*" >&2; exit 1; }

# Step 定义（顺序）
STEPS=(0 1 2 3-4 5 6-7 8 9 10 11 12 13)

step_index() {
    local target="$1"
    for i in "${!STEPS[@]}"; do
        if [ "${STEPS[$i]}" = "$target" ]; then
            echo "$i"
            return
        fi
    done
    die "Unknown step: $target"
}

next_step() {
    local current="$1"
    local idx
    idx=$(step_index "$current")
    local next_idx=$((idx + 1))
    if [ "$next_idx" -ge "${#STEPS[@]}" ]; then
        echo "DONE"
    else
        echo "${STEPS[$next_idx]}"
    fi
}

read_state() {
    if [ -f "$STATE_FILE" ]; then
        cat "$STATE_FILE"
    else
        echo '{}'
    fi
}

write_state() {
    local content="$1"
    echo "$content" > "$STATE_FILE"
}

init_state() {
    local requirement="$1"
    write_state "$(python3 -c "
import json, time
state = {
    'current_step': '0',
    'requirement': '''$requirement''',
    'started_at': time.strftime('%Y-%m-%d %H:%M:%S'),
    'completed_steps': [],
    'variables': {}
}
print(json.dumps(state, ensure_ascii=False, indent=2))
")"
    echo "[INIT] 流程已启动"
    echo "  需求: $requirement"
    echo "  当前步骤: Step 0"
    echo ""
    echo "下一步动作: 提取关键词，然后读 modules/module.json 进入 Step 1"
}

cmd_status() {
    local state
    state=$(read_state)
    python3 -c "
import json, sys
state = json.loads('''$state''')
step = state.get('current_step', '?')
completed = state.get('completed_steps', [])
req = state.get('requirement', '?')
variables = state.get('variables', {})

print('=== 流程状态 ===')
print(f'需求: {req}')
print(f'当前步骤: Step {step}')
print(f'已完成步骤: {completed}')
print()

if variables:
    print('=== 状态变量 ===')
    for k, v in variables.items():
        val = str(v)
        if len(val) > 200:
            val = val[:200] + '...'
        print(f'  {k}: {val}')
    print()
"
}

cmd_next() {
    local state
    state=$(read_state)
    python3 -c "
import json, sys
state = json.loads('''$state''')
step = state.get('current_step', '0')

instructions = {
    '0': 'Step 0: 从需求提取关键词。完成后执行: orchestrator.sh done-step 0',
    '1': 'Step 1: 读取 modules/module.json，匹配模块。完成后执行: orchestrator.sh done-step 1',
    '2': 'Step 2: 预读 info.md + 引用文档，spawn sub-agent 定位入口函数。完成后执行: orchestrator.sh done-step 2',
    '3-4': 'Step 3-4: 执行 pipeline.sh step3-4。完成后执行: orchestrator.sh done-step 3-4',
    '5': 'Step 5: spawn sub-agent 过滤调用路径，写入 filtered_indices.json。完成后执行: orchestrator.sh done-step 5',
    '6-7': 'Step 6-7: 执行 pipeline.sh step6-7。完成后执行: orchestrator.sh done-step 6-7',
    '8': 'Step 8: spawn sub-agent 制定修改计划。完成后执行: orchestrator.sh done-step 8',
    '9': 'Step 9: spawn Linus Reviewer 审查。完成后执行: orchestrator.sh done-step 9',
    '10': 'Step 10: spawn sub-agent 实现代码。完成后执行: orchestrator.sh done-step 10',
    '11': 'Step 11: 向用户确认修改 YES/NO。完成后执行: orchestrator.sh done-step 11',
    '12': 'Step 12: spawn sub-agent git commit。完成后执行: orchestrator.sh done-step 12',
    '13': 'Step 13: 执行 pipeline.sh clean，输出总结。完成后执行: orchestrator.sh done-step 13',
}

instr = instructions.get(step, f'Unknown step: {step}')
print(f'当前: Step {step}')
print(f'指令: {instr}')
print()
print('⚠️ 完成当前步骤后，必须执行:')
print(f'  bash {'''$SKILL_DIR'''}/scripts/orchestrator.sh done-step {step}')
"
}

cmd_done_step() {
    local completed="$1"
    local state
    state=$(read_state)
    local next
    next=$(next_step "$completed")

    local new_state
    new_state=$(python3 -c "
import json
state = json.loads('''$state''')
completed_steps = state.get('completed_steps', [])
if '''$completed''' not in completed_steps:
    completed_steps.append('''$completed''')
state['completed_steps'] = completed_steps
state['current_step'] = '''$next'''
print(json.dumps(state, ensure_ascii=False, indent=2))
")
    write_state "$new_state"

    echo "[DONE] Step $completed ✓"
    echo "[NEXT] → Step $next"
    echo ""

    if [ "$next" = "DONE" ]; then
        echo "🎉 全部步骤已完成！"
    else
        echo "下一步: bash $SKILL_DIR/scripts/orchestrator.sh next"
    fi
}

cmd_set() {
    local key="$1"
    shift
    local value="$*"
    local state
    state=$(read_state)
    local new_state
    new_state=$(python3 -c "
import json
state = json.loads('''$state''')
state['variables']['''$key'''] = '''$value'''
print(json.dumps(state, ensure_ascii=False, indent=2))
")
    write_state "$new_state"
    echo "[SET] $key = $value"
}

cmd_get() {
    local key="$1"
    local state
    state=$(read_state)
    python3 -c "
import json
state = json.loads('''$state''')
print(state.get('variables', {}).get('''$key''', ''))
"
}

cmd_reset() {
    rm -f "$STATE_FILE"
    echo "[RESET] 状态已清除"
}

# Main
case "${1:-}" in
    init)
        [ -z "${2:-}" ] && die "Usage: orchestrator.sh init \"用户需求\""
        init_state "$2"
        ;;
    status)  cmd_status ;;
    next)    cmd_next ;;
    done-step)
        [ -z "${2:-}" ] && die "Usage: orchestrator.sh done-step <step>"
        cmd_done_step "$2"
        ;;
    set)
        [ -z "${2:-}" ] && die "Usage: orchestrator.sh set <key> <value>"
        cmd_set "$2" "${@:3}"
        ;;
    get)
        [ -z "${2:-}" ] && die "Usage: orchestrator.sh get <key>"
        cmd_get "$2"
        ;;
    reset)   cmd_reset ;;
    *)
        echo "状态机驱动的流程编排器"
        echo ""
        echo "Usage: $0 <command> [args...]"
        echo ""
        echo "Commands:"
        echo "  init \"需求\"        初始化流程"
        echo "  status              查看当前状态"
        echo "  next                查看下一步指令"
        echo "  done-step <step>    标记步骤完成，推进到下一步"
        echo "  set <key> <value>   保存状态变量"
        echo "  get <key>           读取状态变量"
        echo "  reset               清除状态"
        ;;
esac
