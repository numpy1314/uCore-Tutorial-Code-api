# uCore API 实验验证记录

首次归档完成 8 章、37 个目标函数的 API 挖空与配套教学文档。以下原始归档记录保持对应当时版本；最新教师基线维护与回归见本文后面的专节。8 个参考实现均通过本轮选定的基础运行验收，8 个学生骨架均编译成功并在本章 TODO 处按预期终止。所有章节取得了 GDB 动态证据；其覆盖范围如下，不能解释为 37 个函数及全部分支均已动态覆盖。

完整原始证据见 [evidence.zip](validation/evidence.zip)。归档包含 175 个文件，SHA-256 为 `197275357932379d320b0c36c52715639aa9e40e9afaa4af57e72c8c2c875825`，内部 `SHA256SUMS` 可逐项核验。

## 环境与固定输入

| 项目 | 本轮环境 |
| --- | --- |
| 机器与架构 | QEMU `virt`，RISC-V 64 位，1 个 vCPU，128 MiB RAM |
| QEMU | 8.2.2 |
| GCC | `riscv64-unknown-elf-gcc` 13.2.0 |
| 固件 | OpenSBI 1.3 |
| 调试器 | GDB multiarch 15.1 |
| 测试源码 | [LearningOS/uCore-Tutorial-Test](https://github.com/LearningOS/uCore-Tutorial-Test/tree/1733f460c596b013b1c509ad42afa428640783b0) |
| 测试提交 | `1733f460c596b013b1c509ad42afa428640783b0` |
| 教师测试补丁 SHA-256 | `d553d1307bd8e75060b09c403666435731d053075cee9e54b16396975380e6c6` |

补丁原文和说明分别在 [tests-upstream.patch](../tools/tests-upstream.patch) 与 [tests-upstream.json](../tools/tests-upstream.json)。第 3 章使用 `BASE=2`，包含已提供的 `sys_trace` 检查；其他有用户应用的章节使用 `BASE=1`。第 1 章没有用户测试仓库依赖。

## 逐章结果

| 章 | 主题 | 目标函数 | 主验收执行项数 | 参考运行 | 骨架负向验证 | 动态证据 |
| --- | --- | ---: | --- | --- | --- | --- |
| 1 | 裸机 C 内核启动与 BSS 初始化 | 2 | 无用户测例；启动演示 | PASS | PASS | `clean_bss` 断点 PASS |
| 2 | 用户态系统调用与异常处理 | 2 | 3 | PASS | PASS | `syscall` 断点 PASS |
| 3 | 多道程序与分时调度 | 4 | 9 | PASS | PASS | `proc_init` 断点 PASS |
| 4 | Sv39 页表与地址转换 | 4 | 6 | PASS | PASS | 页表创建/查询/撤销，9 项标记 PASS |
| 5 | 进程生命周期 | 6 | 12 | PASS | PASS | `allocproc` 断点 PASS |
| 6 | 文件对象与 inode 读写 | 8 | 14 | PASS | PASS | `filealloc` 断点 PASS |
| 7 | 管道通信与端点生命周期 | 5 | 16 | PASS | PASS | `pipealloc` 断点 PASS |
| 8 | 线程同步 | 6 | 23 | PASS | PASS | `mutex_lock` 断点 PASS |

第 2—4 章按实际应用退出记录计数；第 5—8 章按总测例逐项启动、结果及退出码计数。第 7 章原列表重复执行 `ch5b_exit`，因此是 **16 次执行、15 个不同名称**，保留上游真实列表。第 8 章删除的是错误的 `ch8b_mut_phi_din.c` 名称，正确的 `ch8b_mut_phi_din` 仍在列表中，共 23 项。

验收没有仅检查最终 `passed` 字样。第 2 章将按打包顺序出现的退出码与应用匹配；第 3—4 章将 PID 与应用的预期退出码匹配。`ch2b_exit` 的 `1234` 是该固定测例的预期值，不是放行任意非零退出。第 5—8 章核对完整测例名单、顺序和每项退出码，顶层项均为 0。前 4 章还要求 QEMU 正常退出；第 5—8 章在收集完整套件证据后允许运行器停止 QEMU。

**骨架负向 PASS 的含义**是“可以编译并触发准确的本章 TODO”，不表示学生实现通过。第 2 章最终骨架显式调用 `shutdown()`；此前仅打印 panic 后不终止的失败记录保留在归档 `historical/ch2-negative-before-shutdown/`。

## 第四章补充验证

`chapters/ch4/reference/ch4-page-table-gdb/` 保存实际 GDB 命令、输出和结果。8 个数值检查及完成标记均满足预期：

| 输出标记 | 期望与观测 |
| --- | --- |
| `MAP_FIRST` | 0：首次映射成功 |
| `PAGE_BASE` | 1：查询返回物理页基址 |
| `BYTE_OFFSET` | 1：用户字节地址补入页内偏移 |
| `UNMAP_KEEP_CLEARED` | 1：不释放数据页时 PTE 清零 |
| `UNMAP_KEEP_ABSENT` | 1：撤销后查询失败 |
| `MAP_AGAIN` | 0：同一数据页重新映射成功 |
| `UNMAP_FREE_CLEARED` | 1：释放数据页的撤销路径清零 PTE |
| `UNMAP_FREE_ABSENT` | 1：释放路径后查询失败 |
| `PAGE_TABLE_GDB_COMPLETE` | 已完成临时页表清理 |

这是在初始化后的内核中通过 GDB 调用进行的局部接口验证，不是用户应用自然覆盖，也不证明分配失败、并发或完整进程回收。另以 `CHAPTER=4_3 BASE=1` 执行 8 个应用，验证已提供的用户时间复制路径，`ch3b_sleep` / `ch3b_sleep1` 正常完成；证据在 `ch4-time/`。

## 检查器与配置回归

归档时重新运行并保存原始输出：

- 修改范围检查器：22/22 通过，覆盖已提交、暂存、工作树、未跟踪、删除、重命名、符号链接、可信基线及第三章 `BASE=2`。
- 运行结果判定器：16/16 通过，覆盖 panic 文件名不误报、真实 panic、失败子测试隐藏于总通过标语之前、缺失/乱序结果、1234 退出码绑定和第一章启动信息。
- 课程配置：3/3 通过。

共 **38 项 API 工具回归 + 3 项配置测试**。这些是教师工具的回归，不代替 QEMU 中的内核运行证据。范围检查仅约束文件；函数体限制和报告质量仍需教师复核，正式验收应使用发布时固定骨架 SHA 和可信脚本。

## 固件与测试修正记录

旧的仓库内 RustSBI 镜像在本轮 QEMU 环境中未正常进入预期运行，出现超时；改用 OpenSBI 1.3 后完成上述验收。原始控制台与部分指令跟踪保存在 `historical/firmware-investigation/`，没有把这段失败归为学生代码失败，也未证明旧固件在所有环境都不可用。

教师测试修正针对可复现的输入与构建问题：允许裸机交叉工具链前缀并显式声明 `zicsr/zifencei`；为 `ch6b_exec` 的 argv 添加空指针终止；文件测例检查实际读取长度并补字符串终止，避免比较未初始化字节；第 6—8 章基础汇总选择修正后的 `ch6b_filetest_simple` 执行读取长度和文件内容断言；`ch6b_filetest.c` 与 `ch6b_filetest_simple.c` 在固定提交中都存在，两个源码均保留，前者不在当前默认套件内。这项调整是验收用例的选择，不是修复不存在的文件名。第 8 章去掉错误的 `.c` 程序名重复项，保留正确命名的程序。历史归档中的工具说明按归档时内容保留，关于该用例选择的解释以当前说明及 `tools/tests-upstream.json` 为准。

部分 GDB 日志包含缺少可选 Python 模块的安装警告；普通断点、寄存器、调用栈与记录的页表命令仍实际执行成功，警告保留原样。每章 smoke 只验证表中断点可达，不能替代学生逐函数的静态分析与动态跟踪报告。

## 版本与证据对应

下面是最终 positive / negative 日志中实际记录的**本地构建提交**，并非对远端发布提交号的猜测。完整 Git 树、`os` 子树、内核二进制哈希及各次 GDB 的独立运行元数据位于归档 `metadata/manifest.json` 和各个原始 `result.json`。

| 章 | 参考运行提交 | 学生骨架运行提交 |
| --- | --- | --- |
| 1 | `7c50dc2b1268046275ba078177271c164719b261` | `bcf04f6da75913f0c741a101c950760a9c738c8d` |
| 2 | `3215940a2d72bb9494d0aaeb18e67b2c9e74f953` | `98d61c927b9d518f0d776396e903ae49f8f4fab6` |
| 3 | `bce18c2d1b5ba232aa9c05f6e1cf9e7ca5ffa1ca` | `3fa6c359b1d1d87d8589a7986ccb83ab547e7711` |
| 4 | `6e3a28d734a8229d945983fb7a7b8bfb9f159359` | `35daa6fdf357e2c7dfdb371e164f55364bc217e8` |
| 5 | `696dd6ba05639b7d046349fc7c64a03423934088` | `e5d4dd06c50e10ae7dea19d4716bb3fd3fef0a73` |
| 6 | `4041e83f3b4d20435e2517145f76e7e098072b53` | `41c6daf81be034f6b0a33cdc932024be59dcf135` |
| 7 | `5f083aad29a997c12f9eb16d25b29163d90097ee` | `fa16830c6fbeb5ed4fd7a33c7c8589e47f8c9de3` |
| 8 | `bf3248f43dd819825c49b6b88df62453e0af1be1` | `88a070c2b21ad1e0c108c82c54c83cea0fa7d93f` |

归档时逐章核对了上述构建提交与当前本地章节分支的 `os` 子树一致。GDB 冒烟可能早于最后一轮文档或工具更新，其 commit 与补丁哈希按当时真实记录保留，不覆盖成最终运行版本。远端发布若重建 Git 提交，应另按 Git 树对应关系核验，不能要求提交号必然相同。

本轮范围不包含原始课程仍留空的额外映射系统调用、spawn/优先级调度、硬链接、死锁检测等扩展，也不证明全部错误输入、资源耗尽、SMP 或各函数所有路径。归档没有包含用户库构建目录、内核/磁盘二进制与大体积完整指令跟踪；保留了重建输入、原始日志和二进制哈希。

## 教师基线维护与回归

本次维护修正第六章系统调用的 fd 上界判断，并补齐第五章至第八章的孤儿僵尸槽位回收；同步任务契约、固定测试说明和调试命令。各章增加三个阶段检查点、三道公开答辩问题及对应报告记录，仍使用原有 37 个实现目标和测试集合。

运行器看到套件完成标记后继续收集最多一秒的输出，避免立即停止 QEMU 截断结束诊断。本轮初次第六章运行已完成全部子项，但结束日志被截断而误判；修正收尾时机后，同一内核二进制通过原有结果检查。未放宽 panic 或子测试退出码的判定。

| 章节 | 参考基础套件 | 未填写骨架检查 |
| --- | --- | --- |
| 5 | PASS，12 项 | PASS，命中本章 TODO |
| 6 | PASS，14 项 | PASS，命中本章 TODO |
| 7 | PASS，16 次执行 | PASS，命中本章 TODO |
| 8 | PASS，23 项 | PASS，命中本章 TODO |

另外，现有 50 项工具回归通过。按任务书的阶段命令，已有 `ch5b_forktest0`（LOG=info）与 `ch8b_mut_race` 均实际运行并完成各自断言。第 1—4 章内核源码未变，沿用首次运行记录；本次没有为各接口增加新的行为或错误实现区分测试。

本轮记录的构建源码 `os` 子树、内核哈希与对应发布提交见 [维护回归摘要](validation/teaching-update.json)。原始 `evidence.zip` 仍对应首次归档，不能将其中旧运行当成本次维护的执行记录。现有基础测试通过不等于新增回收分支或所有边界均已被动态覆盖；相关修复还经源码复核。

## 远端发布版本

以下是 `numpy1314/uCore-Tutorial-Code-api` 当前的章节发布版本。第 1—4 章内核源码沿用既有验证版本；第 5—8 章包含下述教师基线维护。测试集合和构建入口保持原有设置。完整 SHA 与树 ID 见 [发布清单](validation/published-branches.json)。课程分析与正式范围检查应使用下表学生骨架的完整 SHA。

| 章 | 学生骨架提交 | 参考实现提交 |
| --- | --- | --- |
| 1 | [b68b0afa424f4c1696330392d7df77de3a2b2c2e](https://github.com/numpy1314/uCore-Tutorial-Code-api/commit/b68b0afa424f4c1696330392d7df77de3a2b2c2e) | [cda429eaebca2b673eeeec65b3eb159ff96e4887](https://github.com/numpy1314/uCore-Tutorial-Code-api/commit/cda429eaebca2b673eeeec65b3eb159ff96e4887) |
| 2 | [dd3bdf25d99585eff4a7613463145c0c3153755d](https://github.com/numpy1314/uCore-Tutorial-Code-api/commit/dd3bdf25d99585eff4a7613463145c0c3153755d) | [a9e69b4f025ba5f7361de0cb9377062785f563e8](https://github.com/numpy1314/uCore-Tutorial-Code-api/commit/a9e69b4f025ba5f7361de0cb9377062785f563e8) |
| 3 | [e362ab38cfb218d2b83645257599febb40eb4a0e](https://github.com/numpy1314/uCore-Tutorial-Code-api/commit/e362ab38cfb218d2b83645257599febb40eb4a0e) | [7d3b1ed6ad8bf4f011493dcc625ab8a6d6360779](https://github.com/numpy1314/uCore-Tutorial-Code-api/commit/7d3b1ed6ad8bf4f011493dcc625ab8a6d6360779) |
| 4 | [9df167de9ff12582fd06296ff0bcbf48fd01e32b](https://github.com/numpy1314/uCore-Tutorial-Code-api/commit/9df167de9ff12582fd06296ff0bcbf48fd01e32b) | [e92fd83a00b67b69e614b300228ce2a568dfe228](https://github.com/numpy1314/uCore-Tutorial-Code-api/commit/e92fd83a00b67b69e614b300228ce2a568dfe228) |
| 5 | [309f1311439f35a8983c071daad6fdc438ecce4e](https://github.com/numpy1314/uCore-Tutorial-Code-api/commit/309f1311439f35a8983c071daad6fdc438ecce4e) | [b5eb7cd8fe19198987d06eeb67d613c19c5fafcd](https://github.com/numpy1314/uCore-Tutorial-Code-api/commit/b5eb7cd8fe19198987d06eeb67d613c19c5fafcd) |
| 6 | [511ff949c4314b66509e6fc0a0fcfc72a2de1045](https://github.com/numpy1314/uCore-Tutorial-Code-api/commit/511ff949c4314b66509e6fc0a0fcfc72a2de1045) | [22f8af4264470dbd1c266be47599fb1c7cac7724](https://github.com/numpy1314/uCore-Tutorial-Code-api/commit/22f8af4264470dbd1c266be47599fb1c7cac7724) |
| 7 | [1fbb75f3a0e084777aab988c9e930b412ed2d531](https://github.com/numpy1314/uCore-Tutorial-Code-api/commit/1fbb75f3a0e084777aab988c9e930b412ed2d531) | [87dfe49c16b572c0fb722d165c3574aa855df8d9](https://github.com/numpy1314/uCore-Tutorial-Code-api/commit/87dfe49c16b572c0fb722d165c3574aa855df8d9) |
| 8 | [4e5aa9ebf52bc8a9e3b5e85b37ba64fd07511f5e](https://github.com/numpy1314/uCore-Tutorial-Code-api/commit/4e5aa9ebf52bc8a9e3b5e85b37ba64fd07511f5e) | [39e47b69bb6481f22f3e53b5c6ce178975d531cc](https://github.com/numpy1314/uCore-Tutorial-Code-api/commit/39e47b69bb6481f22f3e53b5c6ce178975d531cc) |
