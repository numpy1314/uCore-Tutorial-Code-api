# uCore 第 5 章 API 实验：进程生命周期

- [实验任务、接口契约与验收](ucore-ch5-api.md)
- 学生分支：`ch5-api`，参考实现分支：`ch5-api-impl`。
- [实验范围清单](lab.json)；[Markdown 实验报告模板](reports/lab-report.md)。
- 先阅读参考实现并完成 GDB 跟踪，再独立实现学生分支中的指定函数；原有课程记录文件继续保留。
- 本实验以 `BASE=1` 为基础范围，原上游的拓展 TODO 不在本轮验收中。

---

# uCore-Tutorial-Code

Course project for THU-OS.

对标 [rCore-Tutorial-v3](https://github.com/rcore-os/rCore-Tutorial-v3/) 的 C 版本代码。

主要参考 [xv6-riscv](https://github.com/mit-pdos/xv6-riscv), [uCore-SMP](https://github.com/TianhuaTao/uCore-SMP)。

实验 lab1-lab5 基准代码分别位于 ch3-ch8　分支下。

注：为了兼容清华 Git 的需求、避免同学在主分支写代码、明确主分支的功能性，特意单独建了仅包含 README 与 LICENSE 的 master 分支，完成课程实验时请在 clone 仓库后先 push master 分支到清华 Git，然后切到自己开发所需的分支进行后续操作。

## 本地开发测试

在本地开发并测试时，需要拉取 uCore-Tutorial-Test 到 `user` 文件夹。你可以根据网络情况和个人偏好选择下列一项执行：

```bash
# 清华 git 使用 https
git clone https://git.tsinghua.edu.cn/os-lab/<semester>/public/ucore-tutorial-test.git user
# 清华 git 使用 ssh
git clone git@git.tsinghua.edu.cn:os-lab/<semester>/public/ucore-tutorial-test.git user
# GitHub 使用 https
git clone https://github.com/LearningOS/uCore-Tutorial-Test.git user
# GitHub 使用 ssh
git clone git@github.com:LearningOS/uCore-Tutorial-Test.git user
```

注意：`user` 已添加至 `.gitignore`，你无需将其提交，ci 也不会使用它

## 实验过程记录

本分支包含 `course.py` 及完整运行依赖。可直接在仓库根目录运行 `python3 course.py`，初始化 AI 会话归档、安装记录工具并打开实验工作区。仅安装、不打开编辑器时运行 `python3 course.py install --skip-extension`。

安装后可使用 `python3 course.py status` 或 `git course status` 检查状态；切换章节会保留已有配置和过程记录。使用说明见 [实验过程记录说明](docs/course-recording.md)。
