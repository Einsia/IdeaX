# DeepScientist

原生 idea stage、文献检索、候选比较与选择；实验执行阶段不属于本提案 baseline，proposal-only 边界在 adapter 中显式记录。

上游：https://github.com/ResearAI/DeepScientist，固定 commit `b36624417f0c6b8238ec02db37b94d6db2faa5b0`。

实现入口：

- [deepscientist.py](../snapshot/phases/offline-20261117/adapters/deepscientist.py)

这是当前离线批次的源码快照。运行所需的上游 checkout、统一语料、图/实体输入、环境和逐槽验收清单需另行准备；此目录不携带历史运行权限或已签发的准入凭据。请先阅读 [总说明](../README.md)。
