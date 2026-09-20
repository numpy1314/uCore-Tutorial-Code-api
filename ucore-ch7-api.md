# uCore ch7 API 实验：管道通信与端点生命周期

## 实验内容

本实验在 uCore 第七章已有进程、页表、文件表和文件系统上，实现匿名管道。通过共享环形缓冲区传递字节，在空/满条件下让出 CPU，把两个端点接入进程文件描述符表，并在最后的端点关闭时释放资源。

学生分支为 `ch7-api`，参考分支为 `ch7-api-impl`。只补全以下 5 个函数体中的 `TODO(ch7-api)`；其余代码已经提供。

| 文件 | 待实现函数 |
| --- | --- |
| `os/pipe.c` | `pipealloc`、`pipeclose`、`pipewrite`、`piperead` |
| `os/syscall.c` | `sys_pipe` |

## 实验要求

1. **限定代码范围**：只能修改上表两个文件中列出的 5 个函数体，不改变签名、头文件、结构体、常量、其他函数或任何其他代码文件，不新增辅助函数。报告写入 `reports/lab-report.md`；报告不是代码修改例外。范围清单为 `lab.json`。
2. **静态分析与动态跟踪**：阅读 `ch7-api-impl` 参考实现，使用 GDB 跟踪本章函数，解释函数行为如何对应任务描述。提交 Markdown 分析报告，每个源码引用写明参考提交 SHA、文件路径、函数名和行号，并保存断点、关键变量、调度前后及返回值的真实观察记录。
3. **独立实现与比较**：在学生分支独立补全 5 个函数；逐函数比较自己的实现与参考实现的相同点、不同点及原因。可使用 AI 辅助理解和排错，但需记录采纳内容并解释自己的实现，不以复制参考实现代替独立完成。
4. **问题与解决思路**：描述主要问题、复现条件、原因分析、解决过程和复测证据；未验证内容明确标为未验证。

## 分支与源码基线

原始第七章提交为 `1e2cf385985dee325b038d52869e04046b9a8198`。参考实现已修正 `sys_pipe` 未初始化指针、无符号描述符判断及失败回滚，学生需要在该目标函数内独立实现相同的错误处理契约。两分支共同提供的配套修复包括：允许 `fileclose` 回收尚未赋予类型的 `FD_NONE` 文件槽；修正 `freeproc` 不执行的描述符清理循环；修正读写和关闭系统调用的描述符上界判断。学生只实现前述函数体，不能改这些配套函数。

本实验沿用 uCore 的现有接口与返回语义。该基线没有 `sys_dup` 的实现与分发，因此本章不包含该接口。已有 `spawn`、优先级、`fstat/link/unlink` 等其他章节 TODO 不属于本轮范围；不要求用 `BASE=0` 或 `BASE=2` 验收。

## 数据结构和已提供接口

`os/file.h` 中 `struct pipe` 包含 512 字节缓冲区 `data[PIPESIZE]`、累计读写计数 `nread/nwrite`、端点标志 `readopen/writeopen`。保持可读量不超过容量；当前下标由计数对 `PIPESIZE` 取模得到。同一管道两端共用一份对象。

`struct file` 记录 `type`、引用数 `ref`、读写权限和 `pipe` 指针。`fork` 复制描述符并增加引用；`fileclose` 仅在文件引用降至零时调用 `pipeclose`，不能把一次描述符关闭直接等同于整个端点关闭。

| 接口 | 本章使用方式 |
| --- | --- |
| `kalloc/kfree` | 分配、释放一页内核内存；管道对象放入该页 |
| `filealloc/fileclose` | 申请引用数为 1 的文件槽、释放一个引用；分配失败为 `NULL` |
| `fdalloc` | 在当前进程寻找空槽并登记文件指针，返回 `int` 描述符或 `-1` |
| `copyin/copyout` | 在当前进程页表下复制用户内存，失败返回负值；不能直接解引用用户地址 |
| `curr_proc/yield` | 获取当前进程；使当前进程重新就绪后调度其他进程 |

本章使用单核、内核执行到显式调度点才切换进程的教学模型，不要求实现 SMP 锁。不能在满/空时原地忙等，也不能增加与既有调度器不匹配的阻塞状态。

配套进程退出代码会释放已经成为僵尸的孤儿所占槽位；存活孩子清除父指针后继续执行。该生命周期处理已提供，学生无需修改 `os/proc.c`。

## 函数契约

### `int pipealloc(struct file *f0, struct file *f1)`

输入是两个不同且已分配的有效文件槽，调用者负责检查分配成功。分配一页，初始化读写计数为 0、两端开启；`f0` 是只读端、`f1` 是只写端，两者类型均为 `FD_PIPE` 且指向同一个管道。成功返回 0；内存分配失败返回 -1，不能泄漏管道页，也不替调用方释放文件槽。不要重置由 `filealloc` 管理的引用数。

### `void pipeclose(struct pipe *pi, int writable)`

输入为仍然存活的管道，以及被关闭端的写权限。`writable != 0` 关闭写端，否则关闭读端；只在两个端点均关闭后 `kfree` 一次。此函数由最后一次 `fileclose` 调用，不修改文件引用数，不调度，不访问已释放的管道。

### `int pipewrite(struct pipe *pi, uint64 addr, int n)`

输入为有效管道、当前进程的用户源地址和正数长度。按 FIFO 顺序从用户内存复制字节，成功写完返回 `n`。遇读端关闭时返回 -1，即使此前已经写过部分字节，也保留既有返回约定。

每次写入量同时受未写字节数、空闲容量、缓冲区末尾连续空间限制。先 `copyin` 成功，再推进 `nwrite` 和累计写入数。缓冲区满时 `yield`，恢复后重新检查读端和空间。不得覆盖未读数据，不得把用户虚拟地址当内核指针。本基线 `n <= 0` 或 `copyin` 失败会 `panic`；本实验保持此行为，不将这些情况宣称为完整 POSIX 错误处理。

### `int piperead(struct pipe *pi, uint64 addr, int n)`

输入为有效管道、当前进程的用户目标地址和正数长度。缓冲区为空且写端仍开时 `yield` 后重查；为空且写端关闭时返回 -1。本章以 -1 表示这个终止情形，实现必须保留该返回值约定。

有数据时按 FIFO 顺序复制最多 `n` 字节，也允许返回当前可读数据量；一旦已读数据且缓冲区变空，不等待凑满 `n`。每次复制量受剩余请求、可读量和连续空间约束。先 `copyout` 成功，再推进 `nread` 和已读数。写端已关但缓冲区仍有数据时先读完数据。`n <= 0` 或 `copyout` 失败保持基线的 `panic` 行为。

### `uint64 sys_pipe(uint64 fdarray)`

输入 `fdarray` 指向用户空间的 **两个 `uint64` 元素**；这是本仓库用户态 `pipe` 测试的 ABI，不能改成两个 `int`。成功申请两个文件槽和一个管道，登记两个描述符，并写回 `[读端fd, 写端fd]`，返回 0。申请文件/内存/描述符或 `copyout` 失败时返回 `-1`（以 `uint64` 位模式传递）。

描述符分配结果必须先用有符号类型检查失败；文件指针初始化并判空后才能交给 `pipealloc`。任何失败路径都需清除已经登记的 `p->files[]`、关闭已分配文件引用，连带释放管道；不能遗留悬挂指针或重复释放。复制失败可能已经改写用户数组的部分字节，本实验只要求资源回滚，不承诺恢复用户内存。`fileclose` 的 `FD_NONE` 支持已作为脚手架提供。

## 静态分析与 GDB 跟踪

先记录参考版本，不要在参考分支补学生答案：

```bash
git fetch origin
git worktree add ../ucore-ch7-reference origin/ch7-api-impl
cd ../ucore-ch7-reference
git rev-parse HEAD
nl -ba os/pipe.c
nl -ba os/syscall.c
```

按下一节准备用户程序并编译。在两个终端运行（`.gdbinit` 的自动加载因环境而异，这里显式禁用自动加载）：

```bash
# 终端 A：内核入口暂停，GDB 端口 15234
make gdbserver CHAPTER=7 BASE=1 TOOLPREFIX=riscv64-unknown-elf- BOOTLOADER=default
# 终端 B
gdb-multiarch -nx build/kernel
```

```gdb
set architecture riscv:rv64
target remote localhost:15234
break sys_pipe
break pipealloc
break pipewrite
break piperead
break pipeclose
continue
```

在 QEMU 终端输入 `ch7b_pipetest`。断在 `sys_pipe` 后用 `info args`、`list`、`next` 和 `finish` 观察分配顺序及返回值；进入管道读写后用 `print *pi`、`print pi->nwrite - pi->nread`、`print pi->readopen`、`print pi->writeopen`。寄存器返回值可用 `print/x $a0` 查看。局部变量被优化时在函数入口观察参数寄存器，并结合 `disassemble /m`；不要伪造看不到的变量值。

至少记录一次管道创建、读写计数变化和端点关闭。`ch7b_pipetest` 的消息短于 512 字节，不保证触发满缓冲区或环绕；未观察到的路径通过源码推导并注明，不能当作动态覆盖。若教师另行提供长消息/异常路径测试，记录该测试版本及实际命中路径。

## 运行与验收

需要 RISC-V GCC/binutils、QEMU、GDB、主机 C 编译器及 CMake。先按仓库公共环境说明准备固定版本的 `user` 目录。运行 `python3 tools/run_lab.py --prepare-only` 准备；该固定测试版本同时存在 `ch6b_filetest` 与 `ch6b_filetest_simple`；教师补丁选择经过读取长度和字符串终止修正的 `ch6b_filetest_simple` 作为基础文件读写项。应使用随仓库提供的固定补丁，保持本章套件输入一致。

```bash
make user CHAPTER=7 BASE=1 TOOLPREFIX=riscv64-unknown-elf- BOOTLOADER=default
make clean
make build CHAPTER=7 BASE=1
make run CHAPTER=7 BASE=1 TOOLPREFIX=riscv64-unknown-elf- BOOTLOADER=default
```

在用户终端先运行 `ch7b_pipetest`，再运行 `ch7b_usertest`。后者包含往章基础测试；保留 `pipetest passed!`、汇总及退出状态。不能只根据出现 shell 或编译成功判断实验通过。

未补全的学生骨架可以编译，但运行至指定函数应报告 `TODO(ch7-api)` 并停止，这是预期的未完成状态。提交时 5 个占位均应消除，并提交报告。参考实现的存在、静态检查通过、基础用例通过分别是不同证据，不能据此宣称所有边界或全部拓展测试均已通过。

## 阶段验收

以下阶段用于安排学习进度和人工验收，沿用本章现有测例与 GDB 流程。每阶段记录“源码检查 / 构建 / 参考动态跟踪 / 自己实现运行”各自的实际结果。

仍有其他目标函数未完成时，可先完成参考跟踪、源码检查和构建；运行到其 TODO 应记录为“受未完成依赖阻塞”，不能记为整章通过，也不能临时复制参考函数、跳过调用或修改测试来完成阶段验收。最终仍须完成全部目标函数及本章原有验收。

| 阶段 | 实现范围 | 检查方式与完成依据 |
| --- | --- | --- |
| 对象与端点 | `pipealloc/pipeclose/sys_pipe` | 在参考实现跟踪共享对象、两个 fd 和引用释放；检查自己的申请及回滚路径并构建。 |
| 数据传输 | `pipewrite/piperead` | 完成五个函数后运行已有 `ch7b_pipetest`，记录读写计数与端点标志；环绕和满缓冲区按源码解释，未触发时不写成已验证。 |
| 整章验收 | 五个目标函数 | 运行原有 `ch7b_usertest` 与统一 positive 入口，核对每项结果和管道实际输出。 |

## 答辩问题

助教可从下表抽取两个问题，结合本人提交代码和报告进行约 5—8 分钟交流。先说明预期状态变化，再定位源码或已有日志；没有实际触发的分支明确标记为推导。不要求为答辩修改禁止改动的文件或新增测试。实现与参考相同可以是合理结果，评价依据是语义解释、证据对应和对边界的理解。

| 问题 | 建议说明材料 |
| --- | --- |
| 父子各关闭一个 fd 时，为什么管道对象可能仍然存活？ | file 引用数、端点标志和最终释放条件。 |
| 如何区分缓冲区空与满？传输位置越过缓冲区末尾后怎样定位字节？ | nread/nwrite、容量和取模；区分实际观察与推导。 |
| 写端关闭但仍有未读数据时应怎样返回？sys_pipe 中途失败如何清理？ | 本章返回约定、端点状态、已登记 fd 与对象引用。 |

## 统一检查入口


统一验收采用 QEMU 附带的 OpenSBI（安装 `opensbi`，参数 `BOOTLOADER=default`）；仓库原始 RustSBI 仍保留用于历史环境，不能将旧固件在新版 QEMU 下的启动失败归因于学生函数。本文手动构建/GDB 命令同样需要先运行 `python3 tools/run_lab.py --prepare-only`（第 1 章无需用户程序），并使用 `TOOLPREFIX=riscv64-unknown-elf-` 和 `BOOTLOADER=default`。完整工具安装说明见主分支 `docs/api-labs.md`。

正式修改范围验收必须使用课程发布时保存的完整学生骨架 SHA；默认 `origin/chN-api` 只方便自查，在个人仓库推送后可能移动，不能替代固定基线。文本日志可存 `reports/*.txt` 或 `reports/*.log`，图片不在本轮自动范围白名单内。

优先使用仓库提供的固定版本测试入口。它会记录构建和运行日志，避免切章后误用旧应用或磁盘镜像。工具要求和兼容性说明见 `tools/run_lab.py --help`。

```bash
# 骨架发布时先记录 git rev-parse HEAD 的完整 SHA
python3 tools/check_lab.py --base <学生骨架SHA>
# 完成代码后同时要求不存在本章 TODO 标记
python3 tools/check_lab.py --base <学生骨架SHA> --require-complete
# 实际运行功能验收；适用于参考实现和完成后的学生实现
python3 tools/run_lab.py --mode positive
```

教师验证尚未填写的初始骨架可运行 `python3 tools/run_lab.py --mode negative`；这只检查骨架能够编译并在 TODO 处停止，不表示实验完成。范围检查只自动核验文件边界，函数体范围、实现正确性与报告质量仍需复核。课程记录工具须先在 `main` 安装一次。
