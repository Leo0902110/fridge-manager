# 正式上线检查清单

如果需要一步一步照着做：

- 阿里云版本：[DEPLOYMENT_ALIYUN_STEP_BY_STEP.md](DEPLOYMENT_ALIYUN_STEP_BY_STEP.md)
- 腾讯云版本：[DEPLOYMENT_TENCENT_STEP_BY_STEP.md](DEPLOYMENT_TENCENT_STEP_BY_STEP.md)

## 1. 准备 HTTPS 后端域名

小程序正式版、体验版不能使用 `http://`、局域网 IP 或 `localhost`。需要准备一个已备案并配置 HTTPS 证书的域名，例如：

```text
https://api.example.com
```

后端接口地址会是：

```text
https://api.example.com/api/v1
```

图片地址会是：

```text
https://api.example.com/uploads/xxx.jpg
```

## 2. 配置后端环境变量

在服务器的 `backend/.env` 中配置：

```env
DASHSCOPE_API_KEY=你的 DashScope API Key
QWEN_MODEL=qwen-plus
QWEN_VL_MODEL=qwen-vl-max
API_PUBLIC_BASE_URL=https://api.example.com
WECHAT_APPID=你的小程序 AppID
WECHAT_APP_SECRET=你的小程序 AppSecret
AUTH_TOKEN_EXPIRE_DAYS=30
ALLOW_DEV_LOGIN=false
```

`API_PUBLIC_BASE_URL` 不要带 `/api/v1`，它用于生成上传图片的 HTTPS 公网地址。

正式上线给多人使用时，`WECHAT_APPID` 和 `WECHAT_APP_SECRET` 必须填写。后端会用 `wx.login` 的 `code` 换取用户 `openid`，并按用户隔离冰箱数据。

`ALLOW_DEV_LOGIN` 只允许本地开发时临时改成 `true`，正式服务器必须保持 `false`。

## 3. 配置小程序正式接口地址

打开 [miniprogram/app.js](miniprogram/app.js)，把：

```js
const PRODUCTION_API_BASE_URL = 'https://api.your-domain.com/api/v1'
```

改成你的正式接口地址，例如：

```js
const PRODUCTION_API_BASE_URL = 'https://api.example.com/api/v1'
```

代码已经区分环境：

- 开发版：继续使用本地 `127.0.0.1` / `localhost` / 局域网地址。
- 体验版、正式版：只使用 `PRODUCTION_API_BASE_URL`，不会再回退到 HTTP 本地地址。

## 4. 微信公众平台配置合法域名

在微信公众平台的小程序后台添加合法域名：

- request 合法域名：`https://api.example.com`
- uploadFile 合法域名：`https://api.example.com`
- downloadFile 合法域名：`https://api.example.com`

上线前在微信开发者工具中关闭“**不校验合法域名、web-view、TLS 版本以及 HTTPS 证书**”，确认请求仍然正常。

## 5. 反向代理示例

后端可以继续监听本机 `127.0.0.1:8000`，由 Nginx 提供 HTTPS：

```nginx
server {
    listen 443 ssl http2;
    server_name api.example.com;

    ssl_certificate /path/to/fullchain.pem;
    ssl_certificate_key /path/to/privkey.pem;

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

## 6. 上线前验证

逐项确认：

- `https://api.example.com/health` 返回健康状态。
- 小程序启动后 `/api/v1/auth/login` 能返回 token。
- 两台手机登录后只能看到各自添加的食物。
- 拍照识别可成功返回结果。
- 上传图片返回的 `image_url` 是 `https://api.example.com/uploads/...`。
- 首页、详情页不再出现 `<wx-image>` HTTP 警告。
- 设置页统计能记录“吃完”。
- 小程序体验版真机测试通过。
