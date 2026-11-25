# 网站

此目录包含 Vue 网站源码。后端位于 `../servers`，开发服务器通过代理访问后端，浏览器不接收后端令牌。

在本目录安装锁定依赖并启动：

```sh
npm ci
npm run dev
```

开发地址为 `http://127.0.0.1:5173`，端口占用时会报错。根目录 `uv run main.py` 会调用相同的开发命令。
API 代理读取 `../servers/.env` 的 `AVALON_API_HOST` 和 `AVALON_API_PORT`，系统环境变量可覆盖它们。
前端环境文件保存在本目录；只有 `AVALON_PUBLIC_` 前缀的变量可以进入浏览器代码，不应在这些变量中放密钥。

```sh
npm run typecheck
npm run build
```

构建结果写入根 `data/web/dist`，后端启动时会从这里托管网站。
Vite、TypeScript 和 npm 缓存分别在根 `data/cache/vite`、`data/cache/typescript`、`data/cache/npm`。
依赖环境 `node_modules` 不提交 Git。`npm run preview` 可在 `http://127.0.0.1:4173` 预览构建；完整账号与 API 功能应通过后端托管地址验证。

后端已启动时，可执行 `npm run gen:api` 更新 `src/api/schema.d.ts` 的接口类型。它与开发代理共用后端地址配置。
