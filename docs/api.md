# API 说明

默认服务地址为 `http://127.0.0.1:8010`，启动后可访问 `/docs` 查看 FastAPI 自动生成的 OpenAPI 页面。

## 基础接口

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| GET | `/health` | 服务健康检查 |
| GET | `/api/tools` | 返回已注册工具及其 JSON Schema |
| POST | `/api/cache/clear` | 清空进程内工具缓存 |

## 规划接口

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| POST | `/api/trip/plan` | 同步生成规划，长任务可能受客户端超时影响 |
| POST | `/api/trip/plan/async` | 创建异步规划任务，推荐前端使用 |
| GET | `/api/trip/jobs/{job_id}` | 查询状态、进度和最终结果 |
| GET | `/api/trip/jobs/{job_id}/graph` | 获取结构化计划和知识图谱 |
| POST | `/api/trip/jobs/{job_id}/cancel` | 请求取消任务 |

异步创建请求示例：

```json
{
  "city": "杭州",
  "start_date": "2026-07-20",
  "days": 2,
  "cities": [],
  "travelers": 2,
  "max_budget": 2500,
  "preferences": ["历史文化", "美食"],
  "pace": "moderate",
  "accommodation": "standard hotel",
  "transportation": "public transit",
  "special_requirements": "",
  "include_packing": true
}
```

多城市请求将 `cities` 设置为：

```json
[
  {"city": "杭州", "days": 2},
  {"city": "苏州", "days": 2}
]
```

异步任务状态包括 `queued`、`running`、`completed`、`failed`、`cancelling` 和 `cancelled`。完成结果主要字段为：

- `content`：可读规划文本。
- `raw_steps`：工具与 Agent 步骤。
- `structured_plan`：日程、POI、天气、预算、约束和行李数据。
- `knowledge_graph`：节点、关系与类别。

## 地图接口

| 方法 | 路径 | 主要参数 |
| --- | --- | --- |
| GET | `/api/map/config` | 无；只返回浏览器可用的高德 JS 配置 |
| GET | `/api/map/poi` | `city`、`keyword`、`limit` |
| GET | `/api/map/geocode` | `address`、`city` |
| GET | `/api/map/route` | `origin`、`destination`、`city`、`mode` |
| GET | `/api/map/static` | `city`、`keyword`、`center`、`zoom`、`points` |
| GET | `/api/poi/photo` | `name`、`city` |

`mode` 支持 `walking`、`driving` 和 `transit`。Web 服务 Key 只在后端使用；`/api/map/config` 不会返回 Web 服务 Key。

## 攻略接口

`GET /api/travel/notes?city=杭州&keywords=旅游%20攻略&limit=5`

接口通过 Tavily 搜索公开网页，提炼候选景点、避坑点和预约提醒。候选景点进入规划前还会通过高德 POI 搜索验证。

## 记忆接口

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| GET | `/api/memory` | 获取本机用户偏好 |
| POST | `/api/memory` | 更新本机用户偏好 |
| POST | `/api/memory/from-request` | 从规划请求保存偏好 |
| POST | `/api/memory/reset` | 重置为默认偏好 |

该记忆文件不包含账户隔离机制，部署为公开服务前应替换为数据库并增加身份认证。

## 设置接口

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| GET | `/api/settings` | 返回配置状态，不返回密钥明文 |
| POST | `/api/settings` | 保存本机运行时配置 |

运行时配置写入 `backend/runtime_settings.json`。该接口仅适合可信本地环境，公开部署时应禁用或增加管理员认证。
