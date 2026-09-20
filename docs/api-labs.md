# API 实验维护与验收

## 分支与来源

- `main` 分发课程记录工具、章节索引和维护说明。
- `ch1`—`ch8` 保留本次改造前的原始代码和历史。
- `chN-api` 分发学生骨架；`chN-api-impl` 是本章任务对应的参考实现。
- `lab.json` 描述章节、目标函数、允许修改的代码文件及基础测试选择。
- 每章均有 `ucore-chN-api.md` 与 `reports/lab-report.md`。所有任务书在“实验内容”之后单列老师要求的四项“实验要求”。

源代码来自本账户已有 API 仓库以及其上游 `leeehh/uCore-Tutorial-Code`，已有第三章成果保留。实验按照 uCore 的 C 代码、调用关系和学习目标确定函数范围，并明确各接口的职责与约束。

## 给学生的要求

1. 先在 `main` 执行 `python3 course.py` 安装过程记录，再切换章节。工具只需安装一次。
2. 保存学生骨架的完整提交 SHA，作为分析平台 `base_ref`、修改范围检查与报告的基线。
3. 在单独工作树阅读和 GDB 跟踪 `chN-api-impl`，记录该参考实现的完整 SHA。
4. 回到学生工作树完成限定代码，填写报告，保留实际终端/GDB 日志。
5. 先检查修改范围，再运行功能验证。AI 会话及 IDE 记录沿用现有课程配置与提交约定。

报告必须说明任务条目与参考函数之间的对应关系，包括调用者、输入状态、输出状态、错误路径与关键不变量；不能只贴一段代码。GDB 记录至少含断点位置、命令、观察值及解释。独立实现后说明与参考实现相同或不同之处以及原因。

## 范围检查

在学生分支运行：

```bash
python3 tools/check_lab.py --base <发布时保存的学生骨架SHA>
python3 tools/check_lab.py --base <学生骨架SHA> --require-complete
```

第一条检查已提交、已暂存、未暂存和未跟踪的修改；第二条额外拒绝剩余本章 TODO。允许改动的代码以基线中的 `lab.json` 为准。Markdown 报告、文本跟踪记录和规定路径下的课程 JSONL 日志可提交。参考分支的公共脚手架修复由教师维护，学生不能借机修改外围文件。

范围检查是帮助学生发现越界修改的工具，不构成防作弊隔离。教师验收应使用可信版本的检查器、测试和规则，而不是执行学生自行改写的测试脚本。该检查不判断算法正确性或报告质量。

## 构建与运行

以 Ubuntu/Debian 环境为例：

```bash
sudo apt-get update
sudo apt-get install gcc-riscv64-unknown-elf binutils-riscv64-unknown-elf qemu-system-misc opensbi cmake make gcc python3 gdb-multiarch
```

统一工具使用发行版 OpenSBI。手动运行 Make 可指定 `BOOTLOADER=default TOOLPREFIX=riscv64-unknown-elf-`；本次 QEMU 8.2 环境未使用仓库内旧 RustSBI 完成验证。统一入口会选取固定提交的测试源码并应用有记录的测试修正，保证测试输入可追溯。使用前阅读当前章节的任务书及 `tools/run_lab.py --help`。

```bash
# 配套参考实现：必须完成真实功能测试
python3 tools/run_lab.py --mode positive

# 初始学生骨架：应编译成功，并明确在本章 TODO 处停止
python3 tools/run_lab.py --mode negative
```

negative 成功只表明挖空骨架可用，不表示实验完成。学生完成代码后运行 positive。GDB 的具体断点、观察对象和不被基础应用覆盖的补充路径见各章任务书。

构建可通过 `CHAPTER=N` 明确指定章节，不依赖当前分支名。切换章节或测试集后必须重新打包应用与文件系统，不能使用残留镜像判断运行结果。

## 验收范围

第 1 章验证启动输出与教学代码的结束路径；第 2—4 章验证批处理/调度/分页基础应用；第 5—8 章验证相应基础用户程序及逐项退出状态。第三章已有 `sys_trace` 参考实现，保留包含该测试的选择。测试日志出现最终通过文字仍须核对每一个子测试，不能忽略中间失败。

原始实验的 `spawn`、stride/优先级调度、额外映射系统调用、硬链接、死锁检测等不自动成为本轮核心 API 实验的任务。基础测试通过不证明这些拓展能力存在；任何未实际运行的补充测试应标明“未验证”。

## 教师发布

发布前同时验证配套参考与学生骨架，确认两者目标文件之外一致，任务书、白名单、占位函数相互对应，且每章“实验要求”紧随“实验内容”。原有章节分支保留，禁止强制覆盖其历史。

记录学生/参考分支的最终 SHA、工具链版本、测试仓库固定 SHA、测试修正补丁及真实日志。将发布 SHA 交给课程分析平台作为 `base_ref`。本轮具体执行结果见 [验证记录](validation.md)。

GitHub Actions 自动验证 `main` 的工具回归和 `chN-api-impl` 的运行结果；学生初始骨架不自动冒充功能测试通过。可在 Actions 手动选择 `negative` 验证空骨架，完成实现后使用 `positive`。本轮通过结论来自已归档的本地真实执行，远端 CI 的状态以具体运行记录为准。
