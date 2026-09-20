# uCore ch2 API 实验：用户态系统调用与异常处理

先阅读 [ucore-ch2-api.md](ucore-ch2-api.md)，再开始实验。该文档给出函数契约、允许修改范围、GDB 跟踪方法和验收标准。

| 分支 | 用途 |
| --- | --- |
| `ch2-api` | 学生骨架：仅本章指定函数体挖空 |
| `ch2-api-impl` | 完整参考实现：用于阅读、构建和动态跟踪 |
| `ch2` | 保留的上游章节代码 |
| `main` | 全课程导航与说明 |

请在 `ch2-api` 上完成实现，在 [reports/lab-report.md](reports/lab-report.md) 中填写报告。不要在 `main` 上完成章节实验；本仓库不再使用“先推送仅含 README 的 master 分支”的旧流程。

本项目是 [rCore-Tutorial-v3](https://github.com/rcore-os/rCore-Tutorial-v3/) 的 C 语言教学实现，参考 [xv6-riscv](https://github.com/mit-pdos/xv6-riscv) 与 [uCore-SMP](https://github.com/TianhuaTao/uCore-SMP)。上游版权与许可证保留。
