# ROS2 内省技能

使用这些工具，无需预知机器人配置，即可自主探索任意 ROS2 机器人的节点、话题、服务。

## 发现工作流

连接到未知机器人时，按以下顺序探索：

1. `ros_list_nodes()` — 了解有哪些节点在运行
2. `ros_list_topics(show_types=True)` — 列出所有话题及消息类型
3. `ros_topic_info('/topic_name')` — 了解某话题的发布者/订阅者
4. `ros_topic_echo('/topic_name', timeout_s=5)` — 采样实际数据

## 常见模式

### 检查机器人速度接口
```
ros_topic_info('/cmd_vel')
→ {type: 'geometry_msgs/msg/Twist', subscriber_count: 1, publishers: [], ...}
```
`publisher_count=0` 说明没有其他控制器在发速度，可以安全接管。

### 读取传感器数据
```
ros_topic_echo('/scan', timeout_s=5)          # 激光雷达
ros_topic_echo('/odom', timeout_s=3)          # 里程计
ros_topic_echo('/camera/image_raw', timeout_s=5)  # 相机（返回元数据，非图像）
ros_topic_echo('/battery_state', timeout_s=30)    # 低频话题需要更长超时
```

### 发布单次消息
```
ros_topic_pub('/cmd_vel', 'geometry_msgs/msg/Twist',
              {'linear': {'x': 0.0, 'y': 0.0, 'z': 0.0},
               'angular': {'x': 0.0, 'y': 0.0, 'z': 0.0}})
```

### 调用服务
```
ros_service_list()   # 先找到可用服务
ros_service_call('/clear_costmaps', 'std_srvs/srv/Empty', {})
ros_service_call('/reinitialize_global_localization', 'std_srvs/srv/Empty', {})
```

## 安全规则

- **运动话题有警告**：`ros_topic_pub` 对 `/cmd_vel` 等话题始终返回 `warning` 字段。
  发布前先用 `robot_status()` 确认机器人处于 `IDLE` 状态，且周围无障碍。
- **紧急停止用 `robot_stop()`**，不用 `ros_topic_pub`。
  `robot_stop()` 通过专用 stop_flag 确保 < 50ms 响应，更可靠。
- **重置定位前取消任务**：`/reinitialize_global_localization` 会影响正在进行的导航，
  先用 `task_cancel(task_id)` 取消当前任务。

## 超时建议

| 话题类型 | 推荐 timeout_s |
|----------|----------------|
| 高频（> 1 Hz） | 3–5 |
| 中频（0.1–1 Hz） | 10–15 |
| 低频（< 0.1 Hz） | 20–30 |
| 服务调用 | 10（默认） |

## 诊断 ROS_DOMAIN_ID 问题

如果 `ros_list_nodes()` 返回空列表但确认机器人在运行：
- 查看响应中的 `ros_domain_id` 字段
- 机器人可能在不同的 ROS_DOMAIN_ID 上
- 请用户确认或在启动脚本中设置 `ROS_DOMAIN_ID` 环境变量后重启 bridge

## 注意事项

- 所有工具在 ROS2 不可用时返回 `{"error": "ROS2 not available: ..."}` 而非崩溃
- `ros_topic_echo` 超时时返回 `{"error": "timeout"}` — 先用 `ros_topic_info` 确认话题有发布者
- `ros_service_list()` 返回的 `type` 字段即 `ros_service_call` 所需的 `srv_type` 参数
