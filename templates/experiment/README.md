# 实验模板五件套 v0.1（experiment/<exp_id>/）

每个实验一个目录，**五件套齐备才算完成**（动态证据四元组 + intent）：

1. `intent.md` —— 实验意图：验证什么假设 / 复现什么现象；预期产出。
2. `setup.sh` —— 从零复现环境：clone/切 commit、装依赖、准备输入。（只读原始仓库的引用；副本用完即弃）
3. `patch.diff` —— 对副本或沙盒的全部改动（实验的化身；没有改动也要生成空 diff 并注明）。
4. `reproduce.sh` —— 一键复现：跑实验并产出 log。（第三方据此核验）
5. `log` —— 原始输出（不加工；含时间戳、命令、退出码）。

补充纪律：
- 副本铁律：证据行号只认原始仓库；FIX-VERIFIED-ON-COPY 不改 FAIL 判定。
- 快照：五件套内记录实验时的 commit hash；仓库漂移则实验作废重跑。
- 悬置：跑不了的标 RUNTIME-UNVERIFIED / DEFERRED / SKIP-HUMAN，逐项注明重试条件，禁止降级冒充 PASS。
