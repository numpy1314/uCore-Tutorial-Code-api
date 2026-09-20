# uCore 第 7 章 API 实验

从 [ucore-ch7-api.md](ucore-ch7-api.md) 开始。学生分支 `ch7-api`；教师参考分支 `ch7-api-impl`。提交报告使用 [reports/lab-report.md](reports/lab-report.md)，代码范围见 [lab.json](lab.json)。

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
