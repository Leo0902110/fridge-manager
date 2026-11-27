# 🔧 配置通义千问 API

## 1. 获取 API Key

### 步骤

1. **访问阿里云 DashScope**
   - 网址：https://dashscope.console.aliyun.com/
   
2. **登录/注册阿里云账号**
   - 如果没有账号，先注册

3. **开通 DashScope 服务**
   - 进入控制台
   - 点击「开通服务」

4. **创建 API Key**
   - 进入「API-KEY Management」
   - 点击「创建新的 API-KEY」
   - 复制生成的 API Key

### 免费额度

- 新用户有 **免费额度**（约 1000 次调用）
- Qwen-VL 图片识别：约 0.03 元/次
- Qwen-Plus 文本：约 0.004 元/千 tokens

---

## 2. 配置环境变量

### 方式一：编辑 .env 文件

```bash
cd /Users/gongchen/Desktop/fridge-manager/backend
cp .env.example .env
```

编辑 `.env` 文件：

```env
DASHSCOPE_API_KEY=sk-xxxxxxxxxxxxxxxxxxxxxxxx
QWEN_MODEL=qwen-plus
QWEN_VL_MODEL=qwen-vl-max
```

### 方式二：命令行导出

```bash
export DASHSCOPE_API_KEY=sk-xxxxxxxxxxxxxxxxxxxxxxxx
export QWEN_MODEL=qwen-plus
export QWEN_VL_MODEL=qwen-vl-max
```

---

## 3. 安装依赖

```bash
cd /Users/gongchen/Desktop/fridge-manager/backend
pip install dashscope
```

---

## 4. 测试 API

### 测试千问服务

```bash
cd /Users/gongchen/Desktop/fridge-manager/backend
python -c "
from app.services.qwen_service import qwen_service
import os
os.environ['DASHSCOPE_API_KEY'] = 'sk-your-key'

# 测试文本生成
result = qwen_service.infer_shelf_life('苹果', '水果', 'fridge')
print('保质期推理结果:', result)
"
```

### 测试 API 端点

启动后端后：

```bash
# 启动服务
python main.py

# 另一个终端测试
# 推理保质期
curl -X POST http://localhost:8000/api/v1/recognition/infer-shelf-life \
  -F "name=苹果" \
  -F "category=水果" \
  -F "location=fridge"

# 获取食用建议
curl http://localhost:8000/api/v1/recognition/suggestion/苹果?days_left=3
```

---

## 5. 模型选择

| 模型 | 用途 | 价格 | 推荐场景 |
|------|------|------|----------|
| `qwen-vl-max` | 图片识别 | 较高 | 高精度食物识别 |
| `qwen-vl-plus` | 图片识别 | 中等 | 日常使用 |
| `qwen-plus` | 文本推理 | 低 | 保质期推理、建议生成 |
| `qwen-turbo` | 文本 | 最低 | 简单问答 |

### 推荐配置

```env
# 图片识别（食物识别）
QWEN_VL_MODEL=qwen-vl-plus

# 文本推理（保质期、建议）
QWEN_MODEL=qwen-plus
```

---

## 6. 故障排查

### 问题 1：API Key 无效

```
错误：Invalid API Key
解决：检查 API Key 是否正确复制，确保没有多余空格
```

### 问题 2：服务未开通

```
错误：Service not enabled
解决：登录 DashScope 控制台开通服务
```

### 问题 3：额度不足

```
错误：Insufficient quota
解决：充值或等待下月额度重置
```

### 问题 4：图片识别失败

```
错误：Image processing failed
解决：
1. 检查图片格式（支持 jpg/png/webp）
2. 检查图片大小（<10MB）
3. 使用 file:// 协议或 base64 编码
```

---

## 7. 费用估算

### 日常使用场景

假设每天识别 10 次食物，推理 20 次保质期：

| 项目 | 次数/天 | 单价 | 月费用 |
|------|---------|------|--------|
| 图片识别 | 10 | 0.03 元 | 9 元 |
| 文本推理 | 20 | 0.004 元 | 0.24 元 |
| **总计** | - | - | **约 10 元/月** |

### 免费额度

新用户免费额度可使用约 **1-2 个月**（轻度使用）

---

## 8. 安全建议

1. **不要将 API Key 提交到 Git**
   - `.env` 文件已添加到 `.gitignore`

2. **定期轮换 API Key**
   - 建议每 3 个月更换一次

3. **设置额度提醒**
   - 在阿里云控制台设置消费提醒

4. **限制调用频率**
   - 后端已实现基本的错误处理

---

## 9. 备用方案

如果千问 API 不可用，系统会自动降级：

1. 使用内置保质期参考数据
2. 使用默认值（7 天）
3. 提示用户手动输入

---

## 📞 获取帮助

- DashScope 文档：https://help.aliyun.com/zh/dashscope/
- API 参考：https://dashscope.console.aliyun.com/api
- 技术支持：阿里云工单
