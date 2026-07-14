# 开发指南

## 开发原则

- Agent 核心保持框架无关，不引入现成 Agent SDK。
- 新工具使用 `@tool` 装饰器并提供明确类型注解。
- 外部 API 调用必须设置超时并返回可识别错误。
- 密钥只能来自环境变量或被 Git 忽略的本机运行时设置。
- 前后端字段变更需要同步修改 Pydantic 模型与 TypeScript 类型。
- 不在测试中调用计费或不稳定的外部服务。

## 增加工具

1. 在 `backend/app/tools/` 创建函数并添加 `@tool(description=...)`。
2. 参数与返回值使用明确类型注解。
3. 在 `backend/app/tools/__init__.py` 注册工具。
4. 运行 `/api/tools` 检查生成的 JSON Schema。
5. 为纯逻辑部分增加单元测试。

## 修改规划流程

- 快速链路位于 `backend/app/domain/hybrid_planner.py`。
- ReAct 规划封装位于 `backend/app/domain/planner.py`。
- 多城市拆分与合并位于 `backend/app/domain/multi_city.py`。
- 结构化结果与图谱位于 `backend/app/domain/knowledge_graph.py`。

修改工具步骤时应保留 `purpose` 元数据，因为结构化结果构建器会用它区分景点、餐饮、住宿和攻略数据。

## 质量检查

```powershell
cd backend
python -m compileall app
python -m unittest discover -s tests -v

cd ..\frontend-vue
npm ci
npm run build
```

## 日志与本地数据

以下内容只用于本机运行，不应提交：

- `.env`
- `backend/runtime_settings.json`
- `backend/data/user_memory.json`
- `backend/logs/` 与 `frontend-vue/logs/`
- `frontend-vue/dist/`、`node_modules/`

## 提交约定

建议使用 Conventional Commits：

- `feat:` 新功能
- `fix:` 缺陷修复
- `docs:` 文档
- `refactor:` 不改变行为的重构
- `test:` 测试
- `chore:` 工程配置

分支示例：`feat/editable-budget`、`fix/weather-date-mapping`、`docs/deployment-guide`。
