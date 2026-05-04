# 冰箱管家腾讯云正式上线详细步骤

这份文档按“腾讯云轻量应用服务器 + 腾讯云域名/DNSPod + SSL 证书 + Nginx HTTPS + 微信小程序发布”的路径写。

## 0. 推荐架构

建议使用一个后端子域名：

```text
api.example.com
```

正式接口地址：

```text
https://api.example.com/api/v1
```

上传图片地址：

```text
https://api.example.com/uploads/xxx.jpg
```

## 1. 购买腾讯云服务器

### 推荐选择

腾讯云控制台进入：

```text
轻量应用服务器 Lighthouse → 新建实例
```

推荐配置：

- 地域：离目标用户近即可，例如广州、上海、北京。
- 镜像：Ubuntu 22.04 LTS。
- 配置：1 核 2G 起步。
- 带宽：3M 起步。
- 系统盘：40GB 起步。

少量用户测试用轻量应用服务器即可。用户明显变多后再升级到 CVM、MySQL/PostgreSQL、对象存储 COS。

### 防火墙放行端口

在轻量应用服务器控制台：

```text
实例详情 → 防火墙
```

放行：

| 端口 | 协议 | 用途 |
| --- | --- | --- |
| 22 | TCP | SSH 登录 |
| 80 | TCP | HTTP / 证书验证 / HTTPS 跳转 |
| 443 | TCP | HTTPS 正式访问 |

不要把 `8000` 直接放到公网。FastAPI 只监听本机 `127.0.0.1:8000`，公网通过 Nginx 访问。

## 2. 购买域名和备案

### 购买域名

腾讯云控制台进入：

```text
域名注册
```

购买一个域名，例如：

```text
example.com
```

### ICP 备案

如果服务器在中国大陆，正式给微信小程序使用时，域名通常需要备案。

腾讯云备案入口：

```text
腾讯云控制台 → 网站备案 / ICP 备案
```

大致步骤：

1. 填主体信息。
2. 填网站/服务信息。
3. 填服务器信息。
4. 完成短信核验、人脸核验。
5. 等待管局审核。

备案通过后再继续配置正式合法域名。

## 3. DNSPod 解析域名

腾讯云域名通常使用 DNSPod 管理解析。

进入：

```text
DNSPod → 我的域名 → 解析
```

添加记录：

| 类型 | 主机记录 | 记录值 |
| --- | --- | --- |
| A | api | 你的轻量服务器公网 IP |

等待解析生效后，本地验证：

```bash
ping api.example.com
```

如果能解析到服务器公网 IP，说明 DNS 生效。

## 4. 登录服务器并安装依赖

本机终端连接服务器：

```bash
ssh root@你的服务器公网IP
```

安装依赖：

```bash
apt update
apt install -y python3 python3-venv python3-pip git nginx curl
```

## 5. 部署项目代码

推荐放到：

```text
/opt/fridge-manager
```

拉取 GitHub 仓库：

```bash
cd /opt
git clone https://github.com/Leo0902110/---.git fridge-manager-repo
cp -r fridge-manager-repo/fridge-manager /opt/fridge-manager
```

创建 Python 虚拟环境：

```bash
cd /opt/fridge-manager
python3 -m venv .venv
source .venv/bin/activate
pip install -r backend/requirements.txt
```

## 6. 配置后端环境变量

创建：

```text
/opt/fridge-manager/backend/.env
```

内容示例：

```env
DASHSCOPE_API_KEY=你的 DashScope Key
QWEN_MODEL=qwen-plus
QWEN_VL_MODEL=qwen-vl-max

API_PUBLIC_BASE_URL=https://api.example.com

WECHAT_APPID=你的小程序 AppID
WECHAT_APP_SECRET=你的小程序 AppSecret
AUTH_TOKEN_EXPIRE_DAYS=30

ALLOW_DEV_LOGIN=false
DEV_OPENID=dev-openid
```

注意：

- `API_PUBLIC_BASE_URL` 不要带 `/api/v1`。
- 正式服务器 `ALLOW_DEV_LOGIN` 必须是 `false`。
- `.env` 不能提交到 GitHub。

## 7. 先本机启动测试后端

```bash
cd /opt/fridge-manager/backend
/opt/fridge-manager/.venv/bin/python main.py
```

另开一个 SSH 窗口测试：

```bash
curl http://127.0.0.1:8000/health
```

能看到：

```json
{"status":"healthy","service":"fridge-manager-api"}
```

就说明后端能跑。

然后停止手动进程，改用 systemd。

## 8. systemd 托管后端

创建：

```text
/etc/systemd/system/fridge-manager.service
```

内容：

```ini
[Unit]
Description=Fridge Manager FastAPI Backend
After=network.target

[Service]
WorkingDirectory=/opt/fridge-manager/backend
Environment=PYTHONUNBUFFERED=1
ExecStart=/opt/fridge-manager/.venv/bin/uvicorn main:app --host 127.0.0.1 --port 8000
Restart=always
RestartSec=3

[Install]
WantedBy=multi-user.target
```

启动：

```bash
systemctl daemon-reload
systemctl enable fridge-manager
systemctl start fridge-manager
systemctl status fridge-manager
```

看日志：

```bash
journalctl -u fridge-manager -f
```

## 9. 配置 Nginx HTTP 反向代理

创建：

```text
/etc/nginx/sites-available/fridge-manager
```

内容：

```nginx
server {
    listen 80;
    server_name api.example.com;

    client_max_body_size 20m;

    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Forwarded-Host $host;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    }
}
```

启用：

```bash
ln -s /etc/nginx/sites-available/fridge-manager /etc/nginx/sites-enabled/fridge-manager
nginx -t
systemctl reload nginx
```

验证：

```bash
curl http://api.example.com/health
```

## 10. 腾讯云申请 SSL 证书

进入腾讯云控制台：

```text
SSL 证书 → 我的证书 → 申请免费证书
```

选择：

- 证书类型：DV 免费证书。
- 绑定域名：`api.example.com`。
- 验证方式：DNS 验证。

按腾讯云提示添加 DNSPod 验证记录。证书签发后下载 Nginx 版本证书。

把证书上传到服务器，例如：

```text
/etc/nginx/certs/api.example.com_bundle.crt
/etc/nginx/certs/api.example.com.key
```

可以先创建目录：

```bash
mkdir -p /etc/nginx/certs
```

## 11. 配置 Nginx HTTPS

修改：

```text
/etc/nginx/sites-available/fridge-manager
```

改成：

```nginx
server {
    listen 80;
    server_name api.example.com;
    return 301 https://$host$request_uri;
}

server {
    listen 443 ssl http2;
    server_name api.example.com;

    ssl_certificate /etc/nginx/certs/api.example.com_bundle.crt;
    ssl_certificate_key /etc/nginx/certs/api.example.com.key;

    client_max_body_size 20m;

    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Forwarded-Host $host;
        proxy_set_header X-Forwarded-Proto https;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    }
}
```

重载：

```bash
nginx -t
systemctl reload nginx
```

验证：

```bash
curl https://api.example.com/health
```

## 12. 修改小程序正式接口地址

打开 [miniprogram/app.js](miniprogram/app.js)，把：

```js
const PRODUCTION_API_BASE_URL = 'https://api.your-domain.com/api/v1'
```

改成：

```js
const PRODUCTION_API_BASE_URL = 'https://api.example.com/api/v1'
```

重新上传小程序代码。

## 13. 微信公众平台配置合法域名

进入微信公众平台：

```text
开发 → 开发管理 → 开发设置 → 服务器域名
```

添加：

| 配置项 | 域名 |
| --- | --- |
| request 合法域名 | https://api.example.com |
| uploadFile 合法域名 | https://api.example.com |
| downloadFile 合法域名 | https://api.example.com |

然后在微信开发者工具关闭：

```text
不校验合法域名、web-view、TLS 版本以及 HTTPS 证书
```

重新编译，确认没有域名错误。

## 14. 配置微信登录

进入微信公众平台：

```text
开发 → 开发管理 → 开发设置
```

找到：

- AppID
- AppSecret

填到服务器：

```text
/opt/fridge-manager/backend/.env
```

然后重启：

```bash
systemctl restart fridge-manager
```

小程序会自动调用 `wx.login`，后端会把 `code` 换成 `openid`，每个用户的数据会按用户隔离。

## 15. 上传体验版

微信开发者工具中：

1. 打开 `miniprogram/` 目录。
2. 确认 AppID 是正式小程序 AppID。
3. 点击“上传”。
4. 填版本号，例如 `1.0.0`。
5. 填备注，例如“正式上线首版”。

微信公众平台中：

```text
版本管理 → 开发版本 → 设为体验版
```

## 16. 体验版真机测试

至少测试：

- 首次打开自动登录。
- 首页加载正常。
- 拍照识别正常。
- 添加食物正常。
- 图片是 HTTPS，无 HTTP 警告。
- 吃完后统计增加。
- 两台手机只能看到各自食物。
- 关闭“不校验合法域名”后仍能正常访问。

## 17. 提交审核与发布

微信公众平台：

```text
版本管理 → 提交审核
```

注意填写：

- 服务类目：按实际选择。
- 功能说明：冰箱食物管理、拍照识别、临期提醒。
- 隐私保护指引：说明使用摄像头/相册，上传图片用于识别。
- 审核备注：本项目使用微信静默登录，不需要账号密码。

审核通过后点击“发布”。

## 18. 后续维护

### 更新代码

```bash
cd /opt/fridge-manager-repo
git pull
rsync -a --delete --exclude='backend/.env' --exclude='backend/fridge.db' --exclude='backend/uploads' fridge-manager/ /opt/fridge-manager/
cd /opt/fridge-manager
source .venv/bin/activate
pip install -r backend/requirements.txt
systemctl restart fridge-manager
```

### 备份 SQLite

当前数据库文件：

```text
/opt/fridge-manager/backend/fridge.db
```

每日备份示例：

```bash
mkdir -p /opt/fridge-manager/backups
cp /opt/fridge-manager/backend/fridge.db /opt/fridge-manager/backups/fridge-$(date +%F).db
```

用户变多后建议迁移到腾讯云数据库 MySQL 或 PostgreSQL。

### 图片存储升级

当前图片保存在服务器本地：

```text
/opt/fridge-manager/backend/uploads
```

用户变多后建议迁移到腾讯云 COS，再用 CDN 加速。

## 19. 常见问题

### 登录 500

正式服务器检查：

```env
WECHAT_APPID=...
WECHAT_APP_SECRET=...
ALLOW_DEV_LOGIN=false
```

修改后：

```bash
systemctl restart fridge-manager
```

### request 合法域名错误

检查微信公众平台是否添加了：

```text
https://api.example.com
```

且开发者工具已关闭“不校验合法域名”。

### 图片仍然是 HTTP

检查服务器 `.env`：

```env
API_PUBLIC_BASE_URL=https://api.example.com
```

重启后端。注意旧图片 URL 可能还是旧值，新上传图片会变成 HTTPS。

### 识别超时

检查：

- DashScope Key 是否有效。
- `QWEN_VL_MODEL` 是否可用。
- 服务器能否访问 DashScope。
- 后端日志：`journalctl -u fridge-manager -f`。
