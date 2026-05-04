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
│   ├── components/
│   │   └── food-card/    # 食物卡片组件
│   ├── utils/
│   │   └── api.js        # API 调用封装
│   ├── app.js
│   ├── app.json
│   └── app.wxss
├── backend/              # 后端 API
│   ├── app/
│   │   ├── api/          # API 路由
│   │   ├── services/     # 业务逻辑
│   │   ├── models/       # 数据模型
│   │   └── db/           # 数据库
│   ├── main.py
│   └── requirements.txt
└── README.md
```

## 🚀 快速开始

### 前端（小程序）
1. 打开微信开发者工具
2. 导入 `miniprogram/` 目录
3. 在 `project.config.json` 中配置你的 AppID
4. 修改 `utils/api.js` 中的后端地址

### 后端
```bash
cd backend
pip install -r requirements.txt
python main.py
```

## 🔑 API 配置

### 通义千问 AI（推荐）
1. 访问 https://dashscope.console.aliyun.com/
2. 登录并创建 API Key
3. 在 `backend/.env` 中配置：
```
DASHSCOPE_API_KEY=sk-your_api_key
QWEN_MODEL=qwen-plus
QWEN_VL_MODEL=qwen-vl-max
```

**详细说明：** 查看 `backend/QWEN_CONFIG.md`

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
