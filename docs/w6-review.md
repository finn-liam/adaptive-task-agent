# W6 走读文档：工程化代码全解析（AI 代笔，面试前必读）

> 本周代码由 AI 代笔（你已知情并同意）。**面试被问到 FastAPI/SSE/Postgres/Docker 时，
> 你必须能讲清楚本文档的每一节**——否则 W6 的代码在面试官眼里和"抄的"没有区别。

## 1. 整体架构：CLI 之外的第二条路

```
浏览器 (index.html)
  │ fetch POST /api/runs {goal, adaptive}
  │ EventSource GET /api/runs/{id}/events   ← SSE 实时事件流
  ▼
FastAPI (app/api/main.py)
  │ threading.Thread 后台线程跑图
  ▼
build_graph().stream(...)   ← W6 新用法：流式逐节点吐更新
  │
  ├─ 每个节点更新 → RUNS[run_id]["state"]（合并） + queue（事件）
  ├─ __interrupt__ → 发 hitl_request → threading.Event 等人 → Command(resume)
  └─ final → 事件流结束

vs CLI（main.py）：invoke() 一次拿全部结果；服务端必须 stream 才能实时播报。
```

## 2. app/api/main.py 逐块解析

### 2.1 RUNS 登记表
`RUNS[run_id] = {queue, state, status, approval_event, approved}` —— 单进程内存态。
砍 Redis 的理由（压缩方案②）：单进程内 `queue.Queue` 天然线程安全，
Redis pub/sub 只在"API 多副本部署"时才必要——我们没有多副本。

### 2.2 `_execute`：后台线程的三层循环
```
外层 for _ in range(3)          → 审批最多 3 轮（和 CLI 同款兜底）
  中层 for chunk in stream(...)  → 逐节点拿更新
    __interrupt__ → 发 hitl_request → threading.Event().wait(300) 阻塞等人
    其余 chunk    → 合并进 RUNS["state"] + 发 node_update 事件
  未被打断 → 图正常跑完，发 final
  被打断   → Command(resume={"approved": 按钮结果}) 开下一轮 stream
```

### 2.3 observations 合并的坑（AI 自己踩的，重要！）
`state.update(update)` 是"最后写入者赢"——executor 每次更新的 observations
会把之前的全部覆盖（W5 冒烟时回执数只有 1）。修法是手动模拟 operator.add：
observations 键遇到 list 就 extend，其余键才覆盖。
**这和 W4 的教训同源：脱离 reducer 手动合并状态时，追加语义要自己实现。**

### 2.4 SSE 端点（asyncio + 线程队列的桥）
```python
item = await asyncio.to_thread(q.get, timeout=15)   # 阻塞 get 放进线程池
```
`queue.Queue.get` 是阻塞调用，直接写在 async 函数里会卡死事件循环；
`asyncio.to_thread` 把它扔进线程池等。15 秒超时 → 抛 Empty → 发 `: keepalive`
心跳行（SSE 协议的注释行），防止浏览器/代理掐断空闲连接。

## 3. index.html 要点
- `EventSource` 是浏览器原生 SSE 客户端：`es.addEventListener("事件名", 处理函数)`；
- `node_update` 触发 `refreshSnapshot()`：重新 GET /api/runs/{id} 拉"最新白板"，
  渲染任务清单和流水——**前端不做状态推算，永远以服务端快照为准**；
- HITL 按钮 → POST /approvals → 后端 `ev.set()` 唤醒等人的线程；
- 已知简化：跨运行的运行列表没有持久化（刷新页面后历史 run 不可见），V2 可做。

## 4. Postgres 切换（graph.py `_default_checkpointer`）
- 环境变量 `USE_POSTGRES=1` + `POSTGRES_URI` → 用 psycopg 连接并包成 PostgresSaver；
- `saver.setup()` 幂等建表；不设变量 → 走 SQLite。**build_graph 一行没改**——
  这就是 D3"同一接口渐进替换"的兑现；
- compose 里 postgres 服务 + healthcheck + `depends_on: service_healthy`
  保证 API 启动时库已就绪。

## 5. Docker 三件套
- **Dockerfile**：`uv sync --frozen --no-dev` 用锁文件装出可复现环境；
  先 COPY 依赖清单再 COPY 代码 = 利用层缓存（改代码不重装依赖）；
- **.dockerignore**：排除 .venv/results/数据库文件；注意 data/ 不能排
  （search_knowledge 运行时要读语料——AI 曾写错又自己修掉）；
- **compose**：api depends_on postgres healthy；env_file 注入三把钥匙。

## 6. 已知缺口（如实记录）
1. **Postgres 路径未实机验证**：写完时 Docker Desktop 没开。启动 Docker 后
   `docker compose up --build` 即为最终验收（PostgresSaver.setup 会自动建表）；
2. SSE 只在单进程内有效（无 Redis 广播）——多副本部署是 V2 话题；
3. HITL 等待上限 300 秒，超时自动当拒绝；
4. RUNS 不持久化：API 重启后历史 run 不可查（V2 可落库）；
5. evaluate.py 的 Retry Rate 恒为 0（重试在包装器内未回写状态字段）——统计盲区。

## 7. 面试问答速备

问：同步图怎么做成 HTTP 服务的实时流？
答：后台线程跑 `graph.stream(updates)` 逐节点吐更新进线程安全队列，
SSE 的 async 生成器用 `asyncio.to_thread(q.get)` 桥接读取——线程和事件循环各干各的。

问：审批在 Web 端怎么流转？
答：图 interrupt → 线程发 hitl_request 事件并阻塞在 threading.Event；
前端弹按钮 → POST /approvals → 后端设置标志位并 event.set() →
线程拿到 approved 构造 Command(resume) 回注图。前提是有 checkpointer，
否则暂停即失忆。

问：为什么砍 Redis？
答：单进程内 queue.Queue 就够；Redis pub/sub 的价值在多副本广播。
压缩方案明确允许，且 README 如实声明了单进程边界——诚实比堆关键词重要。
