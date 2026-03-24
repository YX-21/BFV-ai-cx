# BFV Gametools 数据面板

基于 `Flask + aiohttp + Gametools API` 的《战地 V》查询工具，支持：

- 玩家战绩查询：玩家名 / `personaId`
- 服务器搜索：平台、地区、返回数量过滤
- 首页全局概览：在线玩家、活跃服务器、热门地图、热门模式、区域活跃度
- 服务器玩家列表：后端批量补齐 `BFBAN` 状态

## 这次升级做了什么

- 统一改为通过 `Gametools` 接口拉取 BFV 数据
- 首页统计从手工遍历服务器改成 `GET /bfv/status/`
- 服务器玩家列表改成后端一次调用 `POST /bfban/checkban/`
- 玩家查询支持平台切换，并自动识别玩家名 / 数字 ID
- 前端拆分为 `templates/index.html + static/styles.css + static/app.js`
- 页面重做为更适合持续扩展的仪表盘布局

## 安装

```bash
pip install -r requirements.txt
```

## 启动

```bash
python app.py
```

默认访问地址：

```text
http://127.0.0.1:5000
```

## 可选环境变量

```text
HOST=0.0.0.0
PORT=5000
DEBUG=true
BFV_DEFAULT_PLATFORM=pc
BFV_DEFAULT_LANG=zh-cn
BFV_REQUEST_TIMEOUT=15
BFV_DASHBOARD_CACHE_TTL=90
BFV_BFBAN_CACHE_TTL=600
BFV_SERVER_LIMIT=20
BFV_MAX_SERVER_LIMIT=50
```

## 主要后端接口

- `GET /api/overview`：全局状态概览
- `POST /api/player`：玩家战绩查询
- `POST /api/servers`：服务器搜索
- `GET /api/server-players`：服务器玩家列表

## 数据来源

- Gametools Swagger: `https://api.gametools.network/docs`
- BFV 状态接口: `https://api.gametools.network/bfv/status/`
- BFV 玩家接口: `https://api.gametools.network/bfv/stats/`
- BFBAN 批量校验: `https://api.gametools.network/bfban/checkban/`
