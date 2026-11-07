# 同赛道开源方式参考

核对日期：2026-11-07。下面比较的是仓库如何组织代码与复现资料，不对参赛成绩作比较，也不将外部仓库内容作为本项目的能力证明。

| 同赛道仓库 | 可观察的公开方式 | 本仓库采用的方式 |
| --- | --- | --- |
| [terra901/TAGC-Data-Intelligence-Decision-Science](https://github.com/terra901/TAGC-Data-Intelligence-Decision-Science) | 中英文入口、脱敏实现、独立架构资料；README 明确排除私有任务资料、凭据、日志、索引与原始提交 | 中英文 README、架构文档、数据与输出分离、本地资料接入步骤 |
| [KailBug/TGAC2025](https://github.com/KailBug/TGAC2025) | 按 Schema 检索、SQL 生成、执行与修正介绍模块，提供环境变量和运行环境说明，描述 Docker / StarRocks 流程 | 展示核心模块及技术选择，提供 `.env.example`、容器配置与可验证命令 |
| [Puiching-Memory/TGAC_2025](https://github.com/Puiching-Memory/TGAC_2025) | 目录说明、运行入口、已接入与预留组件区分、数据和社区资料说明 | 明确实际实现、边界与验证范围，说明缓存回归和新模型推理的区别 |

[gstranded/tgac-2025-proof](https://github.com/gstranded/tgac-2025-proof) 与第一项为同一方案的补充材料入口，不作为另一个独立队伍重复统计。本仓库未复制其他队伍的实现代码、图表或获奖材料。

## 资料和许可证处理

这些仓库的资料策略并不相同：有的发布脱敏源码并排除任务数据，有的保留比赛资料快照。公开可见不等于获得了再次分发授权，因此本仓库选择源码加自造演示，并提供本地导入原资料的路径。

核对时，Puiching-Memory 仓库包含 GPL-3.0 许可证；terra901 与 gstranded 的仓库根目录未见许可证文件；KailBug 的 README 展示 MIT 徽章，但根目录未见对应许可证文件。此处只记录观察结果，不推断未展示的授权。本仓库为自己的代码、文档和自造数据提供完整 MIT 文本，外部项目继续受其各自条件约束。

## 比赛来源

- [CompeteHub：TGAC 赛道三数智决策科学](https://www.competehub.dev/zh/competitions/tgac_03)：用于确认赛道名称与自然语言查询场景。
- [TGAC 官方网站](https://tgac.tencent.com/)：赛事主入口；核对时页面请求返回错误，未据此补写官方规则、榜单或数据再分发条款。

本版本没有原始比赛资料的再分发许可声明。关于公开包和本地资料的区别，见 [data/README.md](../data/README.md) 与 [NOTICE](../NOTICE.md)。
