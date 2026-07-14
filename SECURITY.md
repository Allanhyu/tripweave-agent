# Security Policy

## Reporting

请通过私密渠道向仓库维护者报告安全问题，不要在公开 Issue 中粘贴 API Key、Cookie、Token、服务端地址或用户数据。

## Secret handling

- 真实配置只能保存在 `.env`、部署平台 Secret 或本机 `backend/runtime_settings.json`。
- 前端设置接口面向可信本地环境；公网部署必须增加认证或禁用该接口。
- 如果密钥曾出现在聊天、截图、提交或构建日志中，应立即在服务商控制台撤销并重新生成。
- 清理当前文件不能自动删除已有 Git 历史中的秘密；已有历史需使用 `git filter-repo` 等工具重写，并同步轮换密钥。
