# 模型权重目录（备用）

本目录用于放置备用权重 `models/best.pt`。程序加载权重的顺序为：

1. 环境变量 `CIGYOLO_MODEL` 指定的路径（优先级最高）
2. `params/best.pt`（本仓库默认位置）
3. `models/best.pt`（本目录）

权重必须是 YOLO 分类模型，且类别恰为 `Right` 与 `Wrong` 两类，否则会被拒绝加载并在页面提示“模型加载失败”。

注意：`.gitignore` 已忽略 `models/*.pt`，放在本目录的权重不会随仓库分发。
