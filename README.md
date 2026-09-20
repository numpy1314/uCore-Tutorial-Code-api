# uCore ch4 API 实验

- `ch4-api`：学生骨架，仅完成 `os/vm.c` 的四个页表函数。
- `ch4-api-impl`：对应的参考实现。
- [实验内容、实验要求和 GDB 验收](ucore-ch4-api.md)
- [报告模板](reports/lab-report.md)

本轮为基础 API 实验，使用 `CHAPTER=4 BASE=1`；原课程 `mmap/munmap/trace` 等拓展不属于本轮范围。请先阅读实验文档中的修改范围与撤销映射补充验收。

# uCore-Tutorial-Code

Course project for THU-OS.

对标 [rCore-Tutorial-v3](https://github.com/rcore-os/rCore-Tutorial-v3/) 的 C 版本代码。

主要参考 [xv6-riscv](https://github.com/mit-pdos/xv6-riscv), [uCore-SMP](https://github.com/TianhuaTao/uCore-SMP)。

实验 lab1-lab5 基准代码分别位于 ch3-ch8　分支下。

当前仓库默认分支 `main` 是课程导航入口。API 实验请使用 `chN-api` 学生分支，参考实现位于 `chN-api-impl`；原始 `ch1`—`ch8` 分支保留用于对照，无需先推送历史 `master` 分支。

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
