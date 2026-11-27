# 🧊 冰箱管家 (Fridge Manager)

智能冰箱食物管理小程序 - 再也不让食物过期浪费

## ✨ 功能特性

- 📸 **拍照识别** - AI 自动识别食物类型
- ⏰ **智能记录** - 自动记录放入时间
- 🎯 **保质期预测** - 基于食物类型智能推理临期时间
- 🔔 **临期提醒** - 到期前微信通知
- 📊 **库存概览** - 可视化冰箱状态

## 🏗️ 技术架构

```
fridge-manager/
├── miniprogram/          # 微信小程序前端
│   ├── pages/
│   │   ├── index/        # 首页 - 冰箱概览
│   │   ├── add/          # 添加食物（拍照）
│   │   ├── detail/       # 食物详情
│   │   └── settings/     # 设置
│   ├── custom-tab-bar/   # 自定义底部导航栏
│   ├── images/           # 图标与静态资源
│   ├── utils/
│   │   ├── api.js        # API 调用封装
│   │   └── imageCache.js # 本地图片缓存
│   ├── app.js
│   ├── app.json
│   └── app.wxss
├── backend/              # 后端 API
│   ├── app/
│   │   ├── services/     # Qwen AI 识别与保质期推理服务
│   │   └── db/           # SQLite 数据库封装
│   ├── django_api/       # Django API 视图与路由
│   ├── fridge_service/   # Django settings/asgi/wsgi
│   ├── main.py           # Django ASGI 启动入口
│   ├── manage.py
│   └── requirements.txt
├── Dockerfile            # 容器化部署配置
├── DEPLOYMENT.md         # 通用部署说明
└── README.md
```

## 🚀 快速开始

### 前端（小程序）
1. 打开微信开发者工具
2. 导入 `miniprogram/` 目录
3. 在 `project.config.json` 中配置你的 AppID
4. 开发环境后端地址在 `miniprogram/app.js` 中配置；正式上线按 `DEPLOYMENT.md` 配置 HTTPS 域名

### 后端
```bash
cd backend
pip install -r requirements.txt
python main.py
```

当前 `main.py` 启动的是 Django ASGI 服务，默认监听 `http://127.0.0.1:8000`。

### Docker 部署
项目根目录已提供 [Dockerfile](./Dockerfile)，可直接构建并运行后端服务：
```bash
docker build -t fridge-manager-backend .
docker run -d -p 8000:8000 --env-file backend/.env fridge-manager-backend
```

## 🔑 API 配置

### 通义千问 AI（推荐）
1. 访问 https://dashscope.console.aliyun.com/
2. 登录并创建 API Key
3. 在 `backend/.env` 中配置：
```
DASHSCOPE_API_KEY=your_dashscope_api_key
QWEN_MODEL=qwen-plus
QWEN_VL_MODEL=qwen-vl-max
```

**详细说明：** 查看 `backend/QWEN_CONFIG.md`

### 正式上线

正式版/体验版必须使用 HTTPS 后端域名，并在微信公众平台配置合法域名。多人使用时还需要配置微信小程序登录，后端会按 `openid` 隔离每个用户的冰箱数据。完整步骤见 `DEPLOYMENT.md`。

### 百度 AI 开放平台（备用）
1. 访问 https://ai.baidu.com/
2. 创建应用获取 API Key
3. 在 `backend/.env` 中配置：
```
BAIDU_API_KEY=your_api_key
BAIDU_SECRET_KEY=your_secret_key
```

### 微信订阅消息（提醒通知）
1. 登录微信公众平台
2. 申请订阅消息模板
3. 配置模板 ID


## 📄 许可证
MIT License
