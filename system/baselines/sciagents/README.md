# SciAgents

保留原生图工具、对话管理器及终止规则；匹配领域图逐域验收，原图迁移单列。新领域 driver 首槽门禁不能仅靠修改并发参数跳过。

上游：https://github.com/lamm-mit/SciAgentsDiscovery，固定 commit `c5c30451b29cba813a11b5ce078909a214dad9f2`。

实现入口：

- [driver.py](../snapshot/phases/offline-20261117/staging/sci_strict_json_domains_v1/package/driver.py)
- [sciagents_matched_graph.py](../snapshot/phases/offline-20261117/adapters/sciagents_matched_graph.py)
- [sciagents.py](../snapshot/phases/offline-20261117/adapters/sciagents.py)

这是当前离线批次的源码快照。运行所需的上游 checkout、统一语料、图/实体输入、环境和逐槽验收清单需另行准备；此目录不携带历史运行权限或已签发的准入凭据。请先阅读 [总说明](../README.md)。
