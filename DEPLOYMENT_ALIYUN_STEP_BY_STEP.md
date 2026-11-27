# 冰箱管家正式上线详细步骤

这份文档按“阿里云轻量应用服务器 + 域名备案 + Nginx HTTPS + 微信小程序发布”的路径写。腾讯云同理，只是控制台入口名称不同。

## 总览

正式上线需要完成 6 件事：

1. 购买云服务器。
2. 购买域名并备案。
3. 把后端部署到服务器。
4. 配置 HTTPS。
5. 在微信公众平台配置合法域名。
6. 小程序上传体验版、提交审核、发布。

推荐先用一个后端域名：

```text
api.example.com
```

上线后实际地址：

```text
https://api.example.com/api/v1
```

## 1. 购买云服务器

### 推荐规格

少量用户测试：

- 类型：轻量应用服务器
- 系统：Ubuntu 22.04 LTS
- 配置：1 核 2G
- 带宽：3M 起步
- 系统盘：40GB 起步

正式用户逐渐增加后再升级：

- 2 核 4G
- 5M 带宽以上
- 数据库迁移到 MySQL 或 PostgreSQL

### 购买后要记录

- 公网 IP
- SSH 登录用户名，通常是 `root` 或 `ubuntu`
- SSH 密码或密钥

### 安全组/防火墙开放端口

至少开放：

| 端口 | 用途 |
| --- | --- |
| 22 | SSH 登录 |
| 80 | HTTP，用于证书申请和自动跳转 HTTPS |
| 443 | HTTPS，小程序正式访问 |

不建议开放 `8000` 给公网。Django 服务监听本机 `127.0.0.1:8000`，公网只通过 Nginx 的 443 访问。

## 2. 购买域名并备案

### 域名建议

可以买一个简单域名，例如：

```text
example.com
```

然后创建后端子域名：

```text
api.example.com
```

### 备案

如果服务器在中国大陆，微信小程序正式合法域名通常需要备案域名。

备案流程大致是：

1. 在阿里云购买域名。
2. 进入阿里云 ICP 备案系统。
3. 填写个人/企业主体信息。
4. 填写网站/服务信息。
5. 按要求完成短信核验、人脸核验。
6. 等待管局审核。

备案通过后，再进行 DNS 解析。

### DNS 解析

在域名 DNS 控制台添加：

| 类型 | 主机记录 | 记录值 |
| --- | --- | --- |
| A | api | 你的云服务器公网 IP |

解析完成后，访问：

```text
http://api.example.com
```

应该能到达你的服务器。

## 3. 部署后端到服务器

### 安装系统依赖

在服务器上安装 Python、Git、Nginx：

```bash
apt update
apt install -y python3 python3-venv python3-pip git nginx
```

### 放置项目代码

推荐目录：

```text
/opt/fridge-manager
```

可以从 GitHub 拉取：

```bash
cd /opt
git clone https://github.com/Leo0902110/---.git fridge-manager-repo
cp -r fridge-manager-repo/fridge-manager /opt/fridge-manager
```

如果远程仓库目录结构保持当前状态，实际后端目录是：

```text
/opt/fridge-manager/backend
```

### 创建 Python 虚拟环境

```bash
cd /opt/fridge-manager
python3 -m venv .venv
source .venv/bin/activate
pip install -r backend/requirements.txt
```

### 配置后端环境变量

在服务器创建：

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

- `API_PUBLIC_BASE_URL` 不带 `/api/v1`。
- `ALLOW_DEV_LOGIN` 正式服务器必须是 `false`。
- `.env` 不能提交到 GitHub。

### 测试后端启动

```bash
cd /opt/fridge-manager/backend
/opt/fridge-manager/.venv/bin/python main.py
```

本机测试：

```bash
curl http://127.0.0.1:8000/health
```

返回 `healthy` 后停止手动进程，改成 systemd 托管。

## 4. 用 systemd 保持后端长期运行

创建服务文件：

```text
/etc/systemd/system/fridge-manager.service
```

内容：

```ini
[Unit]
Description=Fridge Manager Django Backend
After=network.target

[Service]
WorkingDirectory=/opt/fridge-manager/backend
Environment=PYTHONUNBUFFERED=1
ExecStart=/opt/fridge-manager/.venv/bin/python /opt/fridge-manager/backend/main.py
Restart=always
RestartSec=3

[Install]
WantedBy=multi-user.target
```

启动服务：

```bash
systemctl daemon-reload
systemctl enable fridge-manager
systemctl start fridge-manager
systemctl status fridge-manager
```

查看日志：

```bash
journalctl -u fridge-manager -f
```

## 5. 配置 Nginx 反向代理

创建 Nginx 配置：

```text
/etc/nginx/sites-available/fridge-manager
```

先配置 HTTP：

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

启用配置：

```bash
ln -s /etc/nginx/sites-available/fridge-manager /etc/nginx/sites-enabled/fridge-manager
nginx -t
systemctl reload nginx
```

测试：

```bash
curl http://api.example.com/health
```

## 6. 配置 HTTPS 证书

### 方案 A：阿里云免费证书

1. 进入阿里云 SSL 证书控制台。
2. 申请免费 DV 证书。
3. 绑定域名 `api.example.com`。
4. 按提示完成 DNS 验证。
5. 下载 Nginx 证书。
6. 上传到服务器，例如：

```text
/etc/nginx/certs/api.example.com.pem
/etc/nginx/certs/api.example.com.key
```

然后把 Nginx 配置改成：

```nginx
server {
    listen 80;
    server_name api.example.com;
    return 301 https://$host$request_uri;
}

server {
    listen 443 ssl http2;
    server_name api.example.com;

    ssl_certificate /etc/nginx/certs/api.example.com.pem;
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

### 方案 B：Certbot 自动证书

也可以用 Let's Encrypt：

```bash
apt install -y certbot python3-certbot-nginx
certbot --nginx -d api.example.com
```

如果服务器在国内，证书申请可能受网络影响；阿里云证书更稳。

### HTTPS 验证

确认：

```bash
curl https://api.example.com/health
```

返回：

```json
{"status":"healthy","service":"fridge-manager-api"}
```

## 7. 修改小程序正式接口地址

打开 [miniprogram/app.js](miniprogram/app.js)，把：

```js
const PRODUCTION_API_BASE_URL = 'https://api.your-domain.com/api/v1'
```

改成：

```js
const PRODUCTION_API_BASE_URL = 'https://api.example.com/api/v1'
```

然后重新上传小程序代码。

## 8. 微信公众平台配置合法域名

进入微信公众平台：

```text
小程序后台 → 开发 → 开发管理 → 开发设置 → 服务器域名
```

添加：

| 配置项 | 域名 |
| --- | --- |
| request 合法域名 | https://api.example.com |
| uploadFile 合法域名 | https://api.example.com |
| downloadFile 合法域名 | https://api.example.com |

保存后，微信开发者工具里点击：

```text
详情 → 本地设置
```

关闭：

```text
不校验合法域名、web-view、TLS 版本以及 HTTPS 证书
```

然后重新编译，确认没有域名和证书报错。

## 9. 配置微信登录信息

进入微信公众平台获取：

```text
小程序后台 → 开发 → 开发管理 → 开发设置
```

记录：

- AppID
- AppSecret

填入服务器的：

```text
/opt/fridge-manager/backend/.env
```

更新后重启后端：

```bash
systemctl restart fridge-manager
```

验证登录接口：

- 小程序端会自动 `wx.login`。
- 后端 `/api/v1/auth/login` 会用 `code` 换 `openid`。
- 每个用户的数据按 `openid` 隔离。

## 10. 上传体验版

在微信开发者工具：

1. 打开 `miniprogram/` 目录。
2. 确认 AppID 是正式小程序 AppID。
3. 点击“上传”。
4. 填写版本号，例如 `1.0.0`。
5. 填写项目备注，例如“正式上线首版”。

然后进入微信公众平台：

```text
版本管理 → 开发版本
```

设为体验版。

## 11. 真机体验版测试

至少测试：

- 第一次打开是否自动登录。
- 首页是否能加载。
- 拍照识别是否正常。
- 添加食物是否正常。
- 首页图片是否正常显示且无 HTTP 警告。
- 标记“吃完”后统计是否增加。
- 两台手机是否只能看到各自的数据。
- 关闭“不校验合法域名”后是否仍正常。

如果两台手机能看到彼此数据，说明用户隔离没生效，不能提交审核。

## 12. 提交审核和发布

进入微信公众平台：

```text
版本管理 → 提交审核
```

常见需要填写：

- 服务类目：按实际小程序选择。
- 功能说明：冰箱食物管理、拍照识别、临期提醒。
- 隐私保护指引：说明会使用摄像头/相册、上传图片用于食物识别。
- 测试账号：本项目是微信静默登录，一般不需要账号密码；可在备注说明。

审核通过后点击发布。

## 13. 后续维护建议

### 数据备份

当前使用 SQLite，数据库文件在：

```text
/opt/fridge-manager/backend/fridge.db
```

建议每天备份一次：

```bash
mkdir -p /opt/fridge-manager/backups
cp /opt/fridge-manager/backend/fridge.db /opt/fridge-manager/backups/fridge-$(date +%F).db
```

用户变多后建议迁移到 MySQL 或 PostgreSQL。

### 更新后端

```bash
cd /opt/fridge-manager-repo
git pull
rsync -a --delete --exclude='backend/.env' --exclude='backend/fridge.db' --exclude='backend/uploads' fridge-manager/ /opt/fridge-manager/
cd /opt/fridge-manager
source .venv/bin/activate
pip install -r backend/requirements.txt
systemctl restart fridge-manager
```

### 常见问题

#### 小程序提示 request 域名不合法

检查微信公众平台是否添加了 `https://api.example.com`，并确认开发者工具关闭了“不校验合法域名”。

#### 图片仍提示 HTTP 不支持

检查服务器 `.env`：

```env
API_PUBLIC_BASE_URL=https://api.example.com
```

然后重启后端，新上传的图片才会返回 HTTPS 地址。

#### 登录 500

正式服务器检查：

```env
WECHAT_APPID=...
WECHAT_APP_SECRET=...
ALLOW_DEV_LOGIN=false
```

本地开发可以不填微信密钥，`127.0.0.1` 会自动使用开发登录。

#### 识别超时

通义千问视觉识别可能需要较久。项目小程序端识别超时已设置为 60 秒。如果仍频繁超时，检查服务器到 DashScope 的网络、模型配置和后端日志。
