# Contributing

感谢参与 TripWeave Agent。提交修改前请先确认 Issue 或说明要解决的问题，避免重复实现。

## 本地检查

```powershell
cd backend
python -m compileall app
python -m unittest discover -s tests -v

cd ..\frontend-vue
npm ci
npm run build
```

## Pull Request 要求

- 保持 Agent 核心不依赖第三方 Agent 框架。
- 不提交真实 API Key、Cookie、Token、用户记忆或运行日志。
- 新增外部工具时提供超时、错误处理和环境变量模板。
- 修改 API 字段时同步更新 Pydantic 模型、TypeScript 类型和文档。
- 说明实际执行过的测试，不要将未执行的检查标记为通过。
- 尽量保持修改范围小，不混入无关格式化或重构。

## Commit

建议使用 Conventional Commits，例如：

```text
feat: add editable intercity transport budget
fix: align multi-city weather dates
docs: document AMap key requirements
```
