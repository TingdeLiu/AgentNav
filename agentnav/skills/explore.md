# explore skill

当目标不在当前视野时，使用以下步骤主动搜索：

1. `robot_scan()` — 旋转一圈，获取各方向场景描述
2. 根据 scan 结果判断最可能的方向（如"180°有门，厨房可能在门后"）
3. `s2_locate("朝那个方向移动")` → pose
4. `s1_move(pose)` → task_id，用 `task_status` 轮询直到 `phase == "arrived"`
5. `robot_look(focus=目标)` — 检查目标是否可见
6. 若可见：执行标准导航（robot_look → s2_locate → s1_move → 轮询 → 验证）
7. 若不可见且探索次数未超过 3 次：回到步骤 1
8. 若超过 3 次：告知用户未找到目标，请求更多信息或建议

## 注意事项

- 每次 scan 前先用 `robot_look()` 看当前方向，避免冗余旋转
- 优先选择"门"、"走廊"、"开口"等方向延伸搜索范围
- 如果 task_status 返回 `status: "failed"`，分析 `error` / `s2_interpretation` 再决定是否重试
- scan 默认角度为 0°、90°、180°、270°；若某方向明显更有希望，可传 `angles=[angle]` 单独扫
