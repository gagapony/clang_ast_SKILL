你是代码分析专家。根据需求筛选调用图关键点。

## 需求
__USER_REQUIREMENT__

## 入口函数
__ENTRY_FUNCTION__

## 调用图关键点（index + brief）
__CALL_GRAPH_KEYPOINT_JSON__

## 任务
分析 brief，判断是否与需求相关。保留相关节点，排除无关。

## 输出（严格 JSON，禁止额外文字）
{
  "entry_function": "__入口函数名__",
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
