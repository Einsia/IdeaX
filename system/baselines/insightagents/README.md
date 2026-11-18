# InsightAgents

保留原生专家推荐、讨论与最终提案流程；本地文献与原生工具返回逐步回放，成功模型调用按原请求缓存复用。

上游：https://github.com/MichelleMa8/InsightAgents，固定 commit `64df251f897811b8b48976c3f464f6df4e7dd1f5`。

实现入口：

- [adapter.py](../snapshot/phases/offline-20261117/staging/insightagents_domain_admission_candidate_v2_20261118T0045/adapter.py)
- [dispatch.py](../snapshot/phases/offline-20261117/staging/insightagents_domain_admission_candidate_v2_20261118T0045/dispatch.py)
- [journal_client.py](../snapshot/phases/offline-20261117/staging/insightagents_domain_admission_candidate_v2_20261118T0045/journal_client.py)

这是当前离线批次的源码快照。运行所需的上游 checkout、统一语料、图/实体输入、环境和逐槽验收清单需另行准备；此目录不携带历史运行权限或已签发的准入凭据。请先阅读 [总说明](../README.md)。
