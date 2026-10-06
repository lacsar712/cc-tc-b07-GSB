# 隧道收敛测缝台

测量员登记里程桩号与收敛毫米值。接口进程内后台线程认领待判行（不另起 worker 容器），按绝对值是否不超过 3.0 mm 给出合格或超限。页面是 Svelte。

## 技术栈

- 后端：Flask、Gunicorn、SQLAlchemy、进程内认领线程
- 前端：Svelte、Vite、nginx 反代 `/api`
- 数据库：PostgreSQL 16

## 端口

| 服务 | 地址 |
|------|------|
| 页面 | http://localhost:3201 |
| 接口 | http://localhost:8201 |
| PostgreSQL | localhost:54401（库名 `tunnelconv`） |

## 账号

| 用户 | 密码 | 权限 |
|------|------|------|
| surveyor | surv123456 | 可提交、可合成 |
| inspector | insp123456 | 只读：可看列表与合成预览，不能提交/生成 |

## 启动

```bash
cd projects/21-tunnel-convergence-desk
docker compose up --build
```

健康检查：`GET http://localhost:8201/api/health`

## 种子

| 桩号 | 类别 | 收敛 | 结论 |
|------|------|------|------|
| K12+180 | 拱顶 | 1.2 mm | 合格 |
| K12+220 | 拱顶 | 2.0 mm | 合格 |
| K18+040 | 拱顶 | 5.6 mm | 超限 |
| K18+060 | 边墙 | 4.2 mm | 超限 |
| K22+100 | 注浆段 | 0.8 mm | 合格 |

## 已办结测缝合成（合成专页）

页眉进入「合成专页」，把**已办结**测缝勾进来：

1. 至少勾选 **2 笔**，且必须是**同一类别**（拱顶 / 边墙 / 注浆段）。不足两笔、勾进未办结、拱顶与边墙（或注浆段）混勾，后台一律 400 拒收。
2. 点「预览后台平均」：平均毫米只由后台 `POST /api/merge/preview` 算出，前端不心算、不记账。
3. 测量员点「生成合成新单」`POST /api/merge`：新单 `delta_mm` 等于后台平均、`status=pending`（待认领，由认领线程判定，绝不直接写成已办结），同时在**同一事务**写入一条合成流水（`merge_flows`：来源编号、类别、平均、生成人）。任一一边失败整体回滚。
4. 巡检员可以预览，点不了生成（后端 403）。
5. 合成流水在专页下方展示；`GET /api/merge/flows` 可查。
