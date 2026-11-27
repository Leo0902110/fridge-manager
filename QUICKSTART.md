# 🧊 冰箱管家 - 快速启动指南

## 项目结构

```
fridge-manager/
├── backend/              # 后端 API (Django)
│   ├── app/
│   │   ├── db/           # legacy SQLite 初始化
│   │   └── services/     # legacy 业务逻辑（Qwen）
│   ├── django_api/       # Django API
│   ├── fridge_service/   # Django 配置
│   ├── main.py           # Django 启动入口
│   ├── requirements.txt  # Python 依赖
│   └── .env.example      # 环境变量示例
├── miniprogram/          # 微信小程序前端
│   ├── pages/            # 页面
│   ├── components/       # 组件
│   ├── utils/            # 工具函数
│   ├── app.js            # 小程序入口
│   └── project.config.json
└── README.md
```

## 🚀 快速启动

### 1. 启动后端

```bash
cd fridge-manager/backend

# 创建虚拟环境（可选）
python -m venv venv
source venv/bin/activate  # Mac/Linux
# 或 venv\Scripts\activate  # Windows

# 安装依赖
pip install -r requirements.txt

# 复制环境变量
cp .env.example .env
# 编辑 .env 配置百度 AI API Key

# 启动服务
python main.py
```

后端将在 http://localhost:8000 启动
健康检查：http://localhost:8000/health

### 2. 配置小程序

1. 打开 **微信开发者工具**
2. 导入 `miniprogram/` 目录
3. 在 `project.config.json` 中修改 `appid` 为你的小程序 AppID
4. 在 `utils/api.js` 中修改 `API_BASE_URL` 为后端地址：
   ```javascript
   API_BASE_URL: 'http://localhost:8000/api/v1'
   // 或部署后的服务器地址
   ```

### 3. 配置百度 AI（可选）

1. 访问 https://ai.baidu.com/
2. 注册并创建应用
3. 获取 API Key 和 Secret Key
4. 在 `backend/.env` 中配置：
   ```
   BAIDU_API_KEY=your_api_key
   BAIDU_SECRET_KEY=your_secret_key
   ```

## 📱 功能说明

### 首页
- 冰箱概览统计
- 临期食物提醒
- 食物列表（支持筛选）

### 添加食物
- 拍照 AI 识别
- 手动输入
- 自动保质期计算
- 存放位置选择

### 详情页
- 食物详细信息
- 剩余天数显示
- 删除/吃完操作

### 设置页
- 使用统计
- 关于信息
- 反馈联系

## 🔧 开发提示

### 后端 API 测试

```bash
# 登录拿 token
TOKEN=$(curl -s -X POST http://localhost:8000/api/v1/auth/login \
   -H "Content-Type: application/json" \
   -d '{"code":"local-test-code"}' | python3 -c 'import sys,json; print(json.load(sys.stdin)["data"]["token"])')

# 获取食物列表
curl http://localhost:8000/api/v1/foods -H "Authorization: Bearer $TOKEN"

# 添加食物
curl -X POST http://localhost:8000/api/v1/foods \
   -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"name":"苹果","category":"水果","location":"fridge","shelf_life_days":30}'

# 获取概览
curl http://localhost:8000/api/v1/foods/stats/overview -H "Authorization: Bearer $TOKEN"
```

### 小程序调试

1. 在微信开发者工具中开启「调试模式」
2. 查看 Console 日志
3. 使用「真机预览」测试实际效果

## 📋 TODO

- [ ] 微信订阅消息通知
- [ ] 食物编辑功能
- [ ] 批量操作
- [ ] 数据导出
- [ ] 分享功能
- [ ] 多用户支持

## 🆘 常见问题

**Q: 后端启动失败？**
A: 检查 Python 版本（建议 3.9+），确保依赖安装完整。

**Q: 小程序请求失败？**
A: 检查后端 CORS 配置，确保 API 地址正确。

**Q: AI 识别不工作？**
A: 检查百度 AI API Key 配置，确保网络通畅。

**Q: 数据库在哪里？**
A: SQLite 数据库文件在 `backend/fridge.db`，可手动删除重置。

## 📞 技术支持

如有问题，请查看：
- 后端日志
- 小程序 Console
- API 文档：http://localhost:8000/docs
