# uCore-Tutorial-Code

Course project for THU-OS.

课程过程记录：在 `main` 分支的仓库根目录运行 `python3 course.py`，先自动初始化 AI 会话归档，再安装 VS Code 记录插件并打开实验工作区与实时日志。安装要求、日志位置和日常命令见 [实验过程记录说明](docs/course-recording.md)。

AI 过程记录：启动时默认使用 `auto`，可通过 `python3 course.py --agent codex` 指定客户端；也支持 `claude`、`cursor`、`vscode`、`copilot` 和 `all`。会话以 JSONL 保存到 `.ai/agent-sessions/<agent>/`，文件名包含日期时间。`.ai/agent-sessions/`、`.ai/events/` 和 `.ai/submissions/` 的全部内容可随实验代码一起提交。请同学们不要改动或删除这些记录，提交时会检查这些记录作为考核参考。详细设置见 [AI 会话归档说明](docs/agent-session-archive.md)。

**Codex 首次使用需要信任 hooks**：安装后，在实验仓库根目录运行 `codex`，输入 `/hooks`，找到 `ucore-session-archive` 的 `Stop` 和 `SessionEnd`，分别审阅并选择 **Trust（信任）**。信任后才会自动归档。使用 VS Code Codex 的同学还需重载窗口并新建会话；更新插件后，如提示 hooks 发生变化，请重新审阅并信任。

工具只在 `main` 分发；安装一次后，切换到 `ch3`–`ch8` 仍会记录。实验分支可运行 `git course logs` 查看日志，运行 `git agent-plugins auto` 再次配置 AI 归档。迁移来源和验证方式见 [记录工具功能说明](docs/course-monitor-report.md)。

课程配置以 [course-profile.json](course-profile.json) 为准：项目标识、插件与 marketplace 名称、工具分发分支，以及各实验分支必须包含的文件或目录由它统一定义。配置随工具安装到 `.ai/course-tools/`，编辑器 hooks 也保留独立副本。

首次使用依次执行：

```bash
git switch main
python3 course.py
git switch ch3
```

`main` 分发课程工具；实验分支承载实验源码。安装后通过 `git course` 和 `git agent-plugins` 使用保留在本地的工具，无需每个实验重复安装。

`.ai/events/` 保存文件、命令和 AI 操作等课程事件；`.ai/agent-sessions/` 按归档等级保存会话内容，默认 `messages` 记录用户可见问答；`.ai/submissions/` 保存提交 Hook 生成的增量事件快照。三类记录均可通过普通 `git add` 与实验代码一起提交。配置维护与测试方法见 [课程配置说明](docs/course-profile.md)。

对标 [rCore-Tutorial-v3](https://github.com/rcore-os/rCore-Tutorial-v3/) 的 C 版本代码。

主要参考 [xv6-riscv](https://github.com/mit-pdos/xv6-riscv), [uCore-SMP](https://github.com/TianhuaTao/uCore-SMP)。

课程实验基准分支为 `ch3`–`ch8`；具体实验安排以课程文档为准。

实验在线文档[uCore-Tutorial-Guide](https://learningos.cn/uCore-Tutorial-Guide/)。

注：主分支 `main` 用于分发课程说明与记录工具，实验代码位于章节分支。完成课程实验时，请在 clone 仓库后先 push `main` 分支到清华 Git，并在 `main` 完成记录配置，然后切到自己开发所需的章节分支进行后续操作。
