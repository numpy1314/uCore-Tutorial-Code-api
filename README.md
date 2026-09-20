# uCore-Tutorial-Code-api

Course project for THU-OS.

课程过程记录：在 `main` 分支的仓库根目录运行 `python3 course.py`，先自动初始化 AI 会话归档，再安装 VS Code 记录插件并打开实验工作区与实时日志。安装要求、日志位置和日常命令见 [实验过程记录说明](docs/course-recording.md)。

AI 过程记录：启动时默认使用 `auto`，可通过 `python3 course.py --agent codex` 指定客户端；也支持 `claude`、`cursor`、`vscode`、`copilot` 和 `all`。会话以 JSONL 保存到 `.ai/agent-sessions/<agent>/`，文件名包含日期时间。`.ai/agent-sessions/`、`.ai/events/` 和 `.ai/submissions/` 的全部内容可随实验代码一起提交。请同学们不要改动或删除这些记录，提交时会检查这些记录作为考核参考。详细设置见 [AI 会话归档说明](docs/agent-session-archive.md)。

**Codex 首次使用需要信任 hooks**：安装后，在实验仓库根目录运行 `codex`，输入 `/hooks`，找到 `ucore-session-archive` 的 `Stop` 和 `SessionEnd`，分别审阅并选择 **Trust（信任）**。信任后才会自动归档。使用 VS Code Codex 的同学还需重载窗口并新建会话；更新插件后，如提示 hooks 发生变化，请重新审阅并信任。

工具只在 `main` 分发；安装一次后，切换到 `ch3-api` 等学生实验分支仍会记录。实验分支可运行 `git course logs` 查看日志，运行 `git agent-plugins auto` 再次配置 AI 归档。迁移来源和验证方式见 [记录工具功能说明](docs/course-monitor-report.md)。

课程配置以 [course-profile.json](course-profile.json) 为准：项目标识、插件与 marketplace 名称、工具分发分支，以及各实验分支必须包含的文件或目录由它统一定义。配置随工具安装到 `.ai/course-tools/`，编辑器 hooks 也保留独立副本。

首次使用依次执行：

```bash
git switch main
python3 course.py
git switch ch1-api
```

`main` 分发课程工具；实验分支承载实验源码。安装后通过 `git course` 和 `git agent-plugins` 使用保留在本地的工具，无需每个实验重复安装。

`.ai/events/` 保存文件、命令和 AI 操作等课程事件；`.ai/agent-sessions/` 按归档等级保存会话内容，默认 `messages` 记录用户可见问答；`.ai/submissions/` 保存提交 Hook 生成的增量事件快照。三类记录均可通过普通 `git add` 与实验代码一起提交。配置维护与测试方法见 [课程配置说明](docs/course-profile.md)。

对标 [rCore-Tutorial-v3](https://github.com/rcore-os/rCore-Tutorial-v3/) 的 C 版本代码。

主要参考 [xv6-riscv](https://github.com/mit-pdos/xv6-riscv), [uCore-SMP](https://github.com/TianhuaTao/uCore-SMP)。

## API 挖空实验

本仓库在现有 uCore C 代码上提供第 1—8 章独立实验，按功能模块及接口契约组织任务。每章只挖空本章目标函数；依赖代码由教师提供。原始 `ch1`—`ch8` 分支保留，供追溯基线。

| 章节 | 实验主题 | 学生骨架与任务书 | 对应参考实现 |
| --- | --- | --- | --- |
| 1 | 启动与 BSS 初始化 | [ch1-api](https://github.com/numpy1314/uCore-Tutorial-Code-api/tree/ch1-api) | [ch1-api-impl](https://github.com/numpy1314/uCore-Tutorial-Code-api/tree/ch1-api-impl) |
| 2 | 系统调用与异常分发 | [ch2-api](https://github.com/numpy1314/uCore-Tutorial-Code-api/tree/ch2-api) | [ch2-api-impl](https://github.com/numpy1314/uCore-Tutorial-Code-api/tree/ch2-api-impl) |
| 3 | 进程调度与退出 | [ch3-api](https://github.com/numpy1314/uCore-Tutorial-Code-api/tree/ch3-api) | [ch3-api-impl](https://github.com/numpy1314/uCore-Tutorial-Code-api/tree/ch3-api-impl) |
| 4 | Sv39 页表与地址转换 | [ch4-api](https://github.com/numpy1314/uCore-Tutorial-Code-api/tree/ch4-api) | [ch4-api-impl](https://github.com/numpy1314/uCore-Tutorial-Code-api/tree/ch4-api-impl) |
| 5 | 进程生命周期 | [ch5-api](https://github.com/numpy1314/uCore-Tutorial-Code-api/tree/ch5-api) | [ch5-api-impl](https://github.com/numpy1314/uCore-Tutorial-Code-api/tree/ch5-api-impl) |
| 6 | 文件管理与 inode | [ch6-api](https://github.com/numpy1314/uCore-Tutorial-Code-api/tree/ch6-api) | [ch6-api-impl](https://github.com/numpy1314/uCore-Tutorial-Code-api/tree/ch6-api-impl) |
| 7 | 管道与文件描述符 | [ch7-api](https://github.com/numpy1314/uCore-Tutorial-Code-api/tree/ch7-api) | [ch7-api-impl](https://github.com/numpy1314/uCore-Tutorial-Code-api/tree/ch7-api-impl) |
| 8 | 同步互斥 | [ch8-api](https://github.com/numpy1314/uCore-Tutorial-Code-api/tree/ch8-api) | [ch8-api-impl](https://github.com/numpy1314/uCore-Tutorial-Code-api/tree/ch8-api-impl) |

在对应分支阅读 `ucore-chN-api.md`，以该分支 `lab.json` 列出的函数和文件为准。`chN-api-impl` 是与该任务书配套的参考实现；原始 `chN` 可能还保留其他课程拓展题，不能把两者混用。

每章“实验内容”之后均有“实验要求”，落实以下四项：

1. 仅在列明的代码文件内完成指定函数，不能修改其余代码、测试、构建脚本或实验规则。
2. 阅读参考实现并使用 GDB 跟踪，写 Markdown 分析报告，以提交 SHA、文件路径、函数及行号引用源代码，解释实际执行与任务描述的对应关系。
3. 独立实现目标函数，再逐项比较自己与参考实现的异同及原因。
4. 记录主要问题、定位证据和解决思路。

允许填写 `reports/lab-report.md`，保存跟踪日志，以及提交课程工具生成的过程记录。报告中的调试结果必须实际取得，不使用模板文字代替实验事实。

本轮核心 API 实验不将原有 `spawn`、stride 调度、硬链接、死锁检测等拓展题默认加入验收。各章任务书会说明具体边界；基础测试通过不表示这些拓展题已完成。

学生先在 `main` 安装一次记录工具，再选择章节：

```bash
git clone https://github.com/numpy1314/uCore-Tutorial-Code-api.git
cd uCore-Tutorial-Code-api
python3 course.py
git switch ch1-api
# 保存发布时的学生骨架提交，后续范围检查与报告均使用此值
git rev-parse HEAD
```

参考分析建议使用独立工作树，避免把参考答案覆盖到学生工作区：

```bash
git fetch origin
git worktree add ../ucore-ch1-reference origin/ch1-api-impl
```

章节切换前提交或妥善保存自己的工作。每章的源码、构建产物和测试选择不同，运行统一验收入口会重新构建当前章。

教师发布与验收方法见 [API 实验维护说明](docs/api-labs.md)。

实验在线文档[uCore-Tutorial-Guide](https://learningos.cn/uCore-Tutorial-Guide/)。

注：主分支 `main` 用于分发课程说明与记录工具，实验代码位于章节分支。完成课程实验时，请在 clone 仓库后先 push `main` 分支到清华 Git，并在 `main` 完成记录配置，然后切到自己开发所需的章节分支进行后续操作。

本轮已完成 8 章、37 个函数的核心 API 实验，并实际验证所有参考与骨架。[查看逐章验证记录和发布 SHA](docs/validation.md)。
