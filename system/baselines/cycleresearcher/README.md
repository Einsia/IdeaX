# CycleResearcher

每槽 10 个原生候选、Standard Mode / 4 reviewers、官方教程 Top1。v5 使用 upstream parser、教程 fallback 和原顺序 first-max；v4 仅作为历史请求载体依赖，兼容映射不参与 v5 选择。

上游：https://github.com/zhu-minjun/Researcher，固定 commit `8c1b253092f3f41b3efc414fb189004855bb49f8`。

实现入口：

- [adapter_v5.py](../snapshot/phases/offline-20261117/state/cycle_slot190_v5_continuation_v2_20261118_A/adapter_v5.py)
- [runner.py](../snapshot/phases/offline-20261117/state/cycle_slot190_v5_continuation_v2_20261118_A/runner.py)
- [replay.py](../snapshot/phases/offline-20261117/state/cycle_upstream_parser_full189_20261118_B/replay.py)

这是当前离线批次的源码快照。运行所需的上游 checkout、统一语料、图/实体输入、环境和逐槽验收清单需另行准备；此目录不携带历史运行权限或已签发的准入凭据。请先阅读 [总说明](../README.md)。
