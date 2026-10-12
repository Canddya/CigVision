# CigVision · 卷烟盒外观质量智能检测平台

> 软件全称：基于YOLO图像分类的卷烟盒外观质量智能检测平台　｜　版本：V1.0　｜　英文简称：CigVision

基于 YOLOv11 图像分类的卷烟盒外观质量在线检测平台。在浏览器中上传 1–100 张 JPG/PNG/BMP 图片，后台逐张判定“良好 / 缺陷”，实时显示检测进度、置信度与推理耗时，支持历史记录追溯、CSV 报告导出，并提供产线设备的实时图片推送接口。

> 本仓库只包含**在线检测平台的部署与运行代码**，不含模型训练、数据集制作脚本。

## 功能

- 批量图片导入：JPG / PNG / BMP，每批 1–100 张，单张 ≤ 20 MB，单批总量 ≤ 200 MB
- 智能缺陷判定：YOLOv11 图像分类模型，类别 `Right`（良好）与 `Wrong`（缺陷）
- 实时进度监控：进度条、已完成数量与失败数量
- 结果详情预览：逐张判定、置信度、推理耗时与原图预览
- 历史记录追溯：自动保存最近 100 个批次，可随时重新打开
- CSV 报告导出：UTF-8 BOM 编码，含判定、置信度、耗时与模型 SHA256
- 产线实时接口：带访问密钥的单图推送，同步返回判定结果

## 目录结构

```text
CigVision-github/
├─ webapp/                    网站后端与前端（FastAPI + 原生 HTML/CSS/JS）
│  ├─ main.py                 路由、上传校验、异步推理、数据库读写、CSV 导出
│  ├─ inference.py            YOLO 分类适配层
│  ├─ schema.sql              数据库建表脚本（启动时自动执行）
│  ├─ __init__.py             包声明
│  └─ static/                 前端页面与静态资源
│     ├─ index.html
│     ├─ style.css
│     ├─ app.js
│     └─ *.png                页头标识与页脚底纹
├─ scripts/
│  ├─ start.py                启动入口（必需）
│  └─ accept*.py, visual*.py  可选验收脚本
├─ CigYOLO/
│  ├─ predict.py              命令行预测工具（可选）
│  └─ data/                   6 张样例图片（良好 3 / 缺陷 3）
├─ params/
│  └─ best.pt                 YOLOv11 二分类权重
├─ models/                    备用权重目录（见 models/README.md）
├─ db/                        SQLite 数据库与上传图片（首次启动自动生成）
├─ docs/                      设计说明与接口文档
├─ requirements-web.txt       网站依赖清单
├─ start.ps1                  Windows 一键启动脚本
└─ README.md
```

## 环境要求

| 项目 | 要求 |
|---|---|
| 操作系统 | Windows 10/11 |
| Python | 3.9（推荐 conda 环境，环境名 `pytorch`） |
| 深度学习框架 | PyTorch 2.x + Ultralytics 8.3.200 |
| 硬件 | 有 NVIDIA 显卡时自动使用 GPU，否则回退 CPU |
| 浏览器 | Chrome 或 Edge |

## 快速开始

### 1. 获取代码

```bash
git clone https://github.com/Canddya/CigVision.git
cd CigVision
```

或不熟悉命令行时直接下载压缩包：

1. 用浏览器打开 https://github.com/Canddya/CigVision ，点击页面右上方的绿色 “Code” 按钮；
2. 在下拉菜单中选择 “Download ZIP”，下载得到 `CigVision-main.zip`；
3. 右键压缩包选择“全部解压”，解压到本地目录，例如 `D:\CigVision`；
4. 若解压后的目录名为 `CigVision-main`，可重命名为 `CigVision`，便于后续命令书写。

解压或克隆完成后，根目录应包含 `webapp`、`scripts`、`CigYOLO`、`params`、`db`、`models` 六个文件夹，
以及 `requirements-web.txt`、`start.ps1`、`README.md` 三个文件；其中 `params/best.pt`（约 3 MB）是检测所需的模型权重。

### 2. 创建并激活环境

```powershell
conda create -n pytorch python=3.9 -y
conda activate pytorch
```

### 3. 安装 PyTorch

```powershell
# 有 NVIDIA 显卡（以 CUDA 12.6 为例）
conda install pytorch torchvision torchaudio pytorch-cuda=12.6 -c pytorch -c nvidia -y

# 无显卡时改用 CPU 版本
# conda install pytorch torchvision torchaudio cpuonly -c pytorch -y
```

### 4. 安装网站依赖

```powershell
cd CigVision-github
pip install -r requirements-web.txt
```

> **不要加 `--no-deps`。** 该参数会跳过 FastAPI、Uvicorn 的间接依赖（starlette、pydantic、anyio、click、h11 等），服务将无法启动。

### 5. 放置模型权重

二分类权重放在 `params/best.pt`，类别必须恰为 `Right` 与 `Wrong`。本仓库已附带该权重。也可用环境变量指定其他路径（优先级最高）：

```powershell
$env:CIGYOLO_MODEL = 'D:\models\best.pt'
```

### 6. 启动服务

```powershell
# 方式一：一键脚本
.\start.ps1

# 方式二：直接命令
conda run --no-capture-output -n pytorch python scripts/start.py
```

浏览器打开 http://127.0.0.1:8000 ，左侧“模型信息”显示“模型已就绪”即为成功。停止服务按 `Ctrl + C`。控制台出现 `Uvicorn running on http://127.0.0.1:8000` 表示服务正在常驻运行，属正常现象。

> `start.ps1` 中写死了 conda 环境名 `pytorch`；若你的环境名不同，请修改该文件或改用方式二。

## 首次自测（验证复现成功）

1. 在工作台左侧点击“选择图片”，选中 `CigYOLO/data` 下的 6 张样例（良好 3 张、缺陷 3 张）；
2. 点击“上传并开始检测”，等待进度显示“已完成”；
3. 统计区应显示良好 3 张、缺陷 3 张；点击结果行“查看”可预览原图与判定详情；
4. 点击“导出 CSV”下载报告，用 Excel 打开中文不乱码；
5. 切换到“检测记录”，可看到本次批次；刷新页面后仍能恢复该批次结果。

## 产线实时接口

在工作台左侧“流水线实时接口”区域点击“进入接口配置”，设置产线名称、设备编号与访问密钥，打开“启用实时接口”并保存（立即生效，无需重启）。设备随后以 `multipart/form-data` 向 `POST /api/line/image` 推送单张图片：

```bash
curl -X POST "http://127.0.0.1:8000/api/line/image" \
  -H "X-CigYOLO-Key: 此处填写访问密钥" \
  -H "X-Image-ID: LINE01-20261012-000001" \
  -F "image=@camera.jpg"
```

请求需要请求头 `X-CigYOLO-Key`；建议同时传入唯一的 `X-Image-ID`，相同设备编号与图片编号只接收一次，可避免设备重试造成重复记录。接口同步返回类别、置信度、推理耗时与批次编号。

## 可选配置项

| 环境变量 | 作用 | 默认值 |
|---|---|---|
| `CIGYOLO_MODEL` | 模型权重的绝对路径 | `params/best.pt`，否则回退 `models/best.pt` |
| `CIGYOLO_PORT` | 服务监听端口 | `8000` |
| `CIGYOLO_DATA_DIR` | 数据目录（数据库与上传图片） | 项目下的 `db/` |

## 数据与备份

- 数据库：`db/cigyolo.sqlite3`（批次、图片记录、流水线配置、接收事件，首次启动自动建库建表）
- 上传图片：`db/uploads/<批次UUID>/<图片UUID>.png`（统一转为 PNG 存储）
- 备份与迁移：停止服务后整体复制 `db/` 文件夹即可
- `db/` 内容已被 `.gitignore` 忽略，克隆后从空库开始，历史记录随使用自动累积

## 可选：验收脚本

`scripts/` 下的验收脚本用于自动化验证，需要额外依赖：

```powershell
pip install httpx playwright
```

| 脚本 | 前置条件 |
|---|---|
| `scripts/acceptance.py` | 无需启动服务（使用 TestClient 与独立测试数据） |
| `scripts/visual_acceptance.py` | 需先启动服务，并先运行 `acceptance.py` 生成 `docs/acceptance/` |
| `scripts/visual_inference_acceptance.py` | 需先运行 `acceptance.py`（会读取其生成的结果文件） |
| `scripts/accept_line_interface.py` | 需在 8002 端口启动服务 |
| `scripts/accept_trained_model.py` | 需在 8000 端口启动服务 |

脚本内的浏览器路径默认指向 Chrome，若本机只有 Edge，可改为 `C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe`；改用 Edge 无需执行 `playwright install`。

## 常见问题

| 现象 | 原因与处理 |
|---|---|
| “未配置模型 / 模型加载失败” | 权重缺失，或类别不是 `{Right, Wrong}`；放好权重后点击“重新加载” |
| 启动报 `No module named 'starlette'` 或 `'click'` | 安装依赖时误用了 `--no-deps`，重新执行 `pip install -r requirements-web.txt` |
| “开始检测”按钮灰显 | 模型未就绪；上传与预览仍可用，检测不可用 |
| 端口被占用 | 设置 `$env:CIGYOLO_PORT='8008'` 后重新启动 |
| 提示“已有批次正在检测，请等待完成” | 服务端同一时间只允许一个批次运行 |
| 页面样式或脚本未更新 | 首页已按资源内容哈希自动加版本戳，强制刷新即可 |

## 说明

- `params/best.pt` 为本项目训练得到的二分类权重，随仓库分发以便直接复现检测效果。若仓库需要公开，请注意权重将一并公开；如需保护模型，可改用私有仓库，或把权重放到 Release 中单独下载并将 `params/best.pt` 加入 `.gitignore`。
- 本平台使用 YOLOv11 **图像分类**模型判断整张图片的外观类别，不输出缺陷的具体位置；置信度是模型对该分类的概率估计，不代表检测准确率。
- 服务默认仅监听 `127.0.0.1`，不对外网开放；检测结果与上传图片全部保存在本机。
