# CigYOLO 卷烟盒外观质量检测网站

简约的本地工厂质检工作台：每批最多 100 张 JPG/PNG/BMP、异步逐张分类与实时进度、流水线单图实时接口、图片预览、历史记录、CSV 导出。数据库位于 `db/cigyolo.sqlite3`。

## 启动

在项目根目录运行：

```powershell
conda run --no-capture-output -n pytorch python scripts/start.py
```

浏览器打开 http://127.0.0.1:8000 。也可执行 `start.ps1`。默认单进程、本机监听；不要以多个 Uvicorn worker 启动。停止服务按 Ctrl+C。

## 模型接入

**已接入并验收 `params/best.pt`。** 默认优先读取该文件，缺失时回退到 `models/best.pt`；`CIGYOLO_MODEL` 环境变量优先级最高。真实样例预测、100 张批量运行和浏览器展示均已通过，详见 `docs/正式模型测试报告.md`。

1. 将可信的已训练权重放入 `params/best.pt`（或在该文件不存在时放入 `models/best.pt`）。
2. 网页点击“重新加载”，确认“模型就绪”。
3. 新上传会自动开始检测；已上传批次点击“开始检测”。

权重必须是 YOLO 分类模型，包含 `Right` 与 `Wrong` 两类。也可通过环境变量指定：

```powershell
$env:CIGYOLO_MODEL = 'D:\your-models\best.pt'
conda run --no-capture-output -n pytorch python scripts/start.py
```

可选：`CIGYOLO_PORT` 修改端口；`CIGYOLO_DATA_DIR` 修改数据目录（默认项目 `db/`）。加载的是本地可信模型文件，不允许网页上传可执行权重。

## 流水线实时接口

在“检测工作台”的“流水线实时接口”区域点击“进入接口配置”，设置产线名称、设备编号和访问密钥并启用接口。工厂设备随后以 `multipart/form-data` 向 `POST /api/line/image` 推送单张图片。接口同步返回判定、置信度、推理耗时和批次编号，记录也会出现在网站的“检测记录”中。

请求需要 `X-CigYOLO-Key`，建议同时传入唯一的 `X-Image-ID` 防止设备重试造成重复记录。完整字段、调用示例和响应格式见 [流水线实时接口说明](docs/流水线实时接口说明.md)。

## 环境与文件

运行环境：conda `pytorch`。任务开始前的已有包版本全部保留，详见 `docs/environment-verification.json`。缺失包补装采用 `pip install --no-deps`，依赖清单位于 `requirements-web.txt`，不应直接执行升级已有环境的命令。

- `CigYOLO/`：原始 Git 项目，未修改。
- `webapp/`：网站、推理适配层、SQL。
- `db/`：SQLite、上传图像、运行配置；备份时停止服务后整体复制此文件夹。
- `models/`：放入正式权重。
- `docs/assets/`：网页草图。
- `docs/acceptance/`：验收截图、结果、独立测试数据。测试权重明确标为 UNTRAINED，只验证调用链，不可用于生产判断。

## 验收复现

```powershell
conda run --no-capture-output -n pytorch python scripts/acceptance.py
# 先启动网站，再执行浏览器测试（需要本机 Chrome）
conda run --no-capture-output -n pytorch python scripts/visual_acceptance.py
# 独立端口 8001 下验证真实前向推理与浏览器结果展示
conda run --no-capture-output -n pytorch python scripts/visual_inference_acceptance.py
# 在独立端口 8002 启动服务后，验证流水线接口与配置页
conda run --no-capture-output -n pytorch python scripts/accept_line_interface.py
```

功能测试使用独立目录和随机初始化的 YOLOv11 测试权重，验证真实前向计算、持久化和接口流程。它不证明正式模型效果。正式的分类结果验收需提供训练权重后，用独立带标签图片复核。
