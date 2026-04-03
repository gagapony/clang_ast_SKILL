#!/usr/bin/env bash
# pipeline.sh — 确定性脚本流水线，AI 只需调用一个命令
# 用法: bash {SKILL_DIR}/scripts/pipeline.sh <step> <args...>

set -euo pipefail

SKILL_DIR="$(cd "$(dirname "$0")/.." && pwd)"

die() { echo "FAIL: $*" >&2; exit 1; }

# ============================================================
# Step 3: 调用图生成 + 验证
# 用法: pipeline.sh step3 <project_root> <entry> <filter_cfg> <callback_cfg> <run_N>
# ============================================================
step3() {
    local project_root="$1"
    local entry="$2"
    local filter_cfg="$3"
    local callback_cfg="$4"
    local run_n="$5"

    local out_dir="${SKILL_DIR}/artifacts/${run_n}"
    mkdir -p "${out_dir}"

    echo "[Step 3] 生成调用图..."
    echo "  entry: ${entry}"
    echo "  project_root: ${project_root}"

    python3.12 "${SKILL_DIR}/scripts/clang_ast/main.py" \
        -p "${project_root}" \
        -e "${entry}" \
        -f all \
        -c "${filter_cfg}" \
        --callback-config "${callback_cfg}" \
        -d 10 \
        -o "${out_dir}/call_graph" \
    || die "clang_ast/main.py 执行失败"

    # 验证产出
    [ -f "${out_dir}/call_graph.json" ] || die "call_graph.json 未生成"
    [ -s "${out_dir}/call_graph.json" ] || die "call_graph.json 为空"

    local node_count
    node_count=$(python3 -c "
import json
data = json.load(open('${out_dir}/call_graph.json'))
assert len(data) > 0, 'empty graph'
print(len(data))
")
    echo "[Step 3] OK: ${node_count} nodes"
}

# ============================================================
# Step 4: 调用图精简 + 验证
# 用法: pipeline.sh step4 <run_N>
# ============================================================
step4() {
    local run_n="$1"
    local out_dir="${SKILL_DIR}/artifacts/${run_n}"

    [ -f "${out_dir}/call_graph.json" ] || die "Step 3 产出不存在，先运行 step3"

    echo "[Step 4] 提取关键点..."

    python3 "${SKILL_DIR}/scripts/extract_keypoint.py" \
        --input "${out_dir}/call_graph.json" \
        --output "${out_dir}/call_graph_keypoint.json" \
    || die "extract_keypoint.py 执行失败"

    [ -f "${out_dir}/call_graph_keypoint.json" ] || die "call_graph_keypoint.json 未生成"
    [ -s "${out_dir}/call_graph_keypoint.json" ] || die "call_graph_keypoint.json 为空"

    local kp_count
    kp_count=$(python3 -c "
import json
data = json.load(open('${out_dir}/call_graph_keypoint.json'))
assert len(data) > 0, 'empty'
print(len(data))
")
    echo "[Step 4] OK: ${kp_count} keypoints"
}

# ============================================================
# Step 3+4: 一键执行（推荐）
# 用法: pipeline.sh step3-4 <project_root> <entry> <filter_cfg> <callback_cfg> <run_N>
# ============================================================
step3_4() {
    step3 "$1" "$2" "$3" "$4" "$5"
    step4 "$5"
    echo "[Step 3+4] 全部完成"
}

# ============================================================
# Step 5 验证门: 检查 filtered_indices 合法性
# 用法: pipeline.sh verify-step5 <run_N>
# ============================================================
verify_step5() {
    local run_n="$1"
    local out_dir="${SKILL_DIR}/artifacts/${run_n}"

    [ -f "${out_dir}/call_graph.json" ] || die "call_graph.json 不存在"
    [ -f "${out_dir}/filtered_indices.json" ] || die "filtered_indices.json 不存在"

    python3 -c "
import json
original = json.load(open('${out_dir}/call_graph.json'))
filtered = json.load(open('${out_dir}/filtered_indices.json'))
valid = {n['index'] for n in original}
indices = filtered['filtered_indices']
invalid = [i for i in indices if i not in valid]
if invalid:
    print(f'FAIL: Invalid indices: {invalid}')
    exit(1)
print(f'OK: {len(indices)} valid indices')
"
}

# ============================================================
# Step 6: 精简调用图
# 用法: pipeline.sh step6 <project_root> <run_N>
# ============================================================
step6() {
    local project_root="$1"
    local run_n="$2"
    local out_dir="${SKILL_DIR}/artifacts/${run_n}"

    [ -f "${out_dir}/call_graph.json" ] || die "call_graph.json 不存在"
    [ -f "${out_dir}/filtered_indices.json" ] || die "filtered_indices.json 不存在"

    echo "[Step 6] 生成精简调用图..."

    python3 "${SKILL_DIR}/scripts/simple_call_graph.py" \
        --original "${out_dir}/call_graph.json" \
        --indices "${out_dir}/filtered_indices.json" \
        --source "${project_root}" \
        --output "${out_dir}/filtered.json" \
    || die "simple_call_graph.py 执行失败"

    [ -f "${out_dir}/filtered.json" ] || die "filtered.json 未生成"
    echo "[Step 6] OK"
}

# ============================================================
# Step 7: 报告生成
# 用法: pipeline.sh step7 <info_md_path> <requirement> <run_N>
# ============================================================
step7() {
    local info_md="$1"
    local requirement="$2"
    local run_n="$3"
    local out_dir="${SKILL_DIR}/artifacts/${run_n}"

    [ -f "${out_dir}/filtered.json" ] || die "filtered.json 不存在"

    echo "[Step 7] 生成报告..."

    python3 "${SKILL_DIR}/scripts/generate_report.py" \
        --filtered "${out_dir}/filtered.json" \
        --info "${info_md}" \
        --output "${out_dir}/report.md" \
        --requirement "${requirement}" \
    || die "generate_report.py 执行失败"

    [ -f "${out_dir}/report.md" ] || die "report.md 未生成"
    echo "[Step 7] OK"
}

# ============================================================
# Step 6+7: 一键执行
# 用法: pipeline.sh step6-7 <project_root> <info_md_path> <requirement> <run_N>
# ============================================================
step6_7() {
    step6 "$1" "$4"
    step7 "$2" "$3" "$4"
    echo "[Step 6+7] 全部完成"
}

# ============================================================
# Merge: 多入口合并
# 用法: pipeline.sh merge <run_N1> <run_N2> ...
# ============================================================
merge() {
    echo "[Merge] 合并多个 run..."
    local runs=()
    for r in "$@"; do
        runs+=("${SKILL_DIR}/artifacts/${r}")
    done

    python3 "${SKILL_DIR}/scripts/merge_reports.py" \
        --runs "${runs[@]}" \
        --output "${SKILL_DIR}/merged/" \
    || die "merge_reports.py 执行失败"

    echo "[Merge] OK"
}

# ============================================================
# Step 8 验证门
# 用法: pipeline.sh verify-step8 <run_N>
# ============================================================
verify_step8() {
    local run_n="$1"
    local plan_file="${SKILL_DIR}/artifacts/${run_n}/modification_plan.md"
    local filtered_file="${SKILL_DIR}/merged/filtered.json"
    # fallback: single run
    [ -f "${filtered_file}" ] || filtered_file="${SKILL_DIR}/artifacts/${run_n}/filtered.json"

    [ -f "${plan_file}" ] || die "modification_plan.md 不存在"
    [ -f "${filtered_file}" ] || die "filtered.json 不存在"

    python3 -c "
import json, re
with open('${plan_file}') as f:
    plan = f.read()
funcs_in_plan = set(re.findall(r'函数[：:]\s*(\S+)', plan))
with open('${filtered_file}') as f:
    data = json.load(f)
valid_funcs = {n['self']['name'] for n in data['nodes']}
invalid = funcs_in_plan - valid_funcs
if invalid:
    print(f'FAIL: Not in call graph: {invalid}')
    exit(1)
print('OK')
"
}

# ============================================================
# Clean: 清理所有产物
# 用法: pipeline.sh clean
# ============================================================
clean() {
    rm -rf "${SKILL_DIR}/artifacts/" "${SKILL_DIR}/merged/"
    echo "[Clean] OK"
}

# ============================================================
# Main
# ============================================================
case "${1:-}" in
    step3)     step3 "$2" "$3" "$4" "$5" "$6" ;;
    step4)     step4 "$2" ;;
    step3-4)   step3_4 "$2" "$3" "$4" "$5" "$6" ;;
    verify-step5) verify_step5 "$2" ;;
    step6)     step6 "$2" "$3" ;;
    step7)     step7 "$2" "$3" "$4" ;;
    step6-7)   step6_7 "$2" "$3" "$4" "$5" ;;
    merge)     shift; merge "$@" ;;
    verify-step8) verify_step8 "$2" ;;
    clean)     clean ;;
    *)
        echo "Usage: $0 <command> [args...]"
        echo ""
        echo "Commands:"
        echo "  step3     <project_root> <entry> <filter_cfg> <callback_cfg> <run_N>"
        echo "  step4     <run_N>"
        echo "  step3-4   <project_root> <entry> <filter_cfg> <callback_cfg> <run_N>"
        echo "  verify-step5  <run_N>"
        echo "  step6     <project_root> <run_N>"
        echo "  step7     <info_md> <requirement> <run_N>"
        echo "  step6-7   <project_root> <info_md> <requirement> <run_N>"
        echo "  merge     <run_N1> <run_N2> ..."
        echo "  verify-step8  <run_N>"
        echo "  clean"
        exit 1
        ;;
esac
