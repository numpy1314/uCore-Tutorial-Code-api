# uCore ch8 API 实验：线程同步

## 实验内容

本实验在已有线程创建、调度、退出及同步对象创建接口上，实现互斥锁、信号量和条件变量。目标是让共享状态、等待队列、线程状态和调度行为一致，并理解“让出 CPU 后重试”“阻塞等待”和“资源直接交接”的区别。

学生分支为 `ch8-api`，参考分支为 `ch8-api-impl`。只补全 `os/sync.c` 中以下 6 个函数体里的 `TODO(ch8-api)`，构造器和其他配套代码已经提供。

| 原语 | 待实现函数 |
| --- | --- |
| 自旋式与阻塞式互斥锁 | `mutex_lock`、`mutex_unlock` |
| 计数信号量 | `semaphore_down`、`semaphore_up` |
| 条件变量 | `cond_wait`、`cond_signal` |

## 实验要求

1. **限定代码范围**：只允许修改 `os/sync.c` 中表列 6 个函数体，不能改变函数签名、构造器、数据结构、调度、系统调用或任何其他代码文件，也不新增辅助函数。报告写入 `reports/lab-report.md`。代码范围由 `lab.json` 明确列出。
2. **静态分析与动态跟踪**：阅读 `ch8-api-impl` 中参考实现，通过 GDB 动态跟踪，分析这 6 个函数如何对应任务描述。提交 Markdown 报告，源码引用含提交 SHA、路径、函数和行号；跟踪记录包含真实断点、线程状态、计数/锁状态、队列及唤醒后的变化。
3. **独立实现与比较**：独立完成函数，逐一对比自己的实现与参考代码，说明相同点、不同点及原因。可使用 AI 辅助阅读和排错，但需记录采纳内容并能够解释最终实现，不用复制参考代码代替独立实现。
4. **问题与解决思路**：记录主要问题、复现条件、分析假设、解决过程和复测证据；不能把未触发的分支或未运行的测例写成已验证。

## 分支基线与范围

原始第八章提交为 `35b5c01188112bc741cbec08a2ed4997a88a0232`。教师参考实现修正了 `mutex_lock` 自旋等待结束后遗漏 `m->locked = 1` 的问题，避免等待者返回时实际没有占用锁。文档契约以修复后的参考分支为准，学生分支必须实现正确的锁获取语义。

两分支共同提供前章管道脚手架修复：`sys_pipe` 的指针初始化、描述符错误判断和回滚，`fileclose` 的 `FD_NONE` 回收，`freeproc` 的文件清理循环，以及文件描述符上界检查。学生无需再次实现前章管道。

本轮不挖空线程创建/退出，也不要求死锁检测。原代码保留的 `enable_deadlock_detect` 等拓展 TODO 不属于这 6 个函数，验收使用 `BASE=1`，`ch8_deadlock_*` 不属于本轮通过条件。

配套进程退出代码会释放已经成为僵尸的孤儿所占槽位（`P_UNUSED`），不再次释放已回收的线程或用户内存；存活孩子继续执行。该处理已提供。

## 数据结构与执行假设

`os/sync.h` 定义：

| 对象 | 状态 |
| --- | --- |
| `struct mutex` | `blocking` 选择阻塞式/自旋式；`locked` 表示锁已占用；阻塞式使用 `wait_queue` |
| `struct semaphore` | 有符号 `count` 与 FIFO `wait_queue` |
| `struct condvar` | 只记录 FIFO `wait_queue`，不保存用户条件或累积许可 |

`mutex_create`、`semaphore_create`、`condvar_create` 已提供对象初始化；系统调用已负责查找对象。以下函数以有效对象及正常使用为前提，不扩展无效 ID 的返回规则。互斥锁不是递归锁，解锁由持有者进行，条件等待前调用者已持有关联锁。初始信号量计数应非负；不要求恢复队列溢出或整数溢出。

| 配套函数/状态 | 含义 |
| --- | --- |
| `curr_thread()` | 当前线程 |
| `task_to_id` / `id_to_task` | 线程与队列保存的标识之间转换；无效标识转为 `NULL` |
| `push_queue` / `pop_queue` | FIFO 入队/出队；空队列返回 -1，溢出 `panic` |
| `yield()` | 当前线程设为 `RUNNABLE`，加入就绪队列，再调度 |
| `sched()` | 切换到调度器；调用前当前线程不能仍为 `RUNNING` |
| `SLEEPING` | 线程阻塞，不进入就绪队列 |
| `RUNNABLE` + `add_task(t)` | 唤醒等待者；只登记为可运行，不立即切换至它 |

本基线是单核且内核中的同步路径仅在显式调度点切换线程。这个假设支持在 `cond_wait` 中连续完成解锁、入队和阻塞状态登记；不应宣称该代码适用于 SMP 或可抢占内核。不得将阻塞锁实现为反复 `yield`。

## 函数契约

### `void mutex_lock(struct mutex *m)`

输入有效互斥锁，输出为无返回值；函数返回时当前线程已经持锁。

- 空闲时设置 `locked = 1` 后返回。
- 自旋式锁已占用时，循环 `yield` 后重新检查。等待结束必须设置 `locked = 1` 才可返回；不能因为曾经看到锁空闲就省略占用动作。自旋式锁不使用等待队列。
- 阻塞式锁已占用时，将当前线程标识加入等待队尾，设为 `SLEEPING`，调用 `sched`。同一次等待只入队一次。
- 阻塞等待者恢复时，锁已由 `mutex_unlock` 直接交接，`locked` 仍为 1；此时直接返回，不能重新排队或把锁清为 0。

### `void mutex_unlock(struct mutex *m)`

输入为当前线程持有的有效锁，无返回值。

- 自旋式锁直接设 `locked = 0`；不使用等待队列、不主动调度。
- 阻塞式锁队列为空时设 `locked = 0`。
- 有等待者时 FIFO 取出一个线程，将其设为 `RUNNABLE` 并 `add_task`。`locked` 保持 1，资源直接交接给该线程，避免其他线程抢占。

一次解锁最多唤醒一个等待者，不把它重新插回等待队列，不立即执行 `sched`。

### `void semaphore_down(struct semaphore *s)`

输入有效信号量，正常返回表示当前线程取得了一个许可。先将 `count` 减一；结果非负时直接返回。结果为负时，将当前线程加入等待队尾、设为 `SLEEPING` 并调度。等待者恢复时许可已由 `up` 交付，不再次减计数。

在无中间操作的稳定状态下，`count > 0` 表示空余许可，`count == 0` 表示许可用尽但无人排队，`count < 0` 时 `-count` 对应等待者数。不要把计数钳制到零，也不能用忙等替代阻塞。

### `void semaphore_up(struct semaphore *s)`

输入有效信号量，无返回值。先将 `count` 加一；结果 `<= 0` 时，取出等待队首并使其 `RUNNABLE`、加入就绪队列；结果 `> 0` 时保留许可供后续获取。一次 `up` 至多唤醒一个线程，唤醒不再次修改计数。

若 `count <= 0` 却没有等待者，属于内部不变量破坏，保留参考实现的 `panic`。信号量可由其他线程 `up` 作为通知，不新增“只有持有者才能 up”的限制。

### `void cond_wait(struct condvar *cond, struct mutex *m)`

输入有效条件变量和当前线程持有的互斥锁。执行顺序为：释放 `m`、将当前线程放入条件等待队列、设为 `SLEEPING`、调用 `sched`；被唤醒并恢复后调用 `mutex_lock(m)`，重新持有同一把锁才能返回。

通知仅使线程可以重新检查条件，不意味着用户条件必然成立，也不直接转交互斥锁。重新加锁可能再次阻塞。调用者负责在持锁状态下循环检查用户条件；不得在未重新加锁时返回。

### `void cond_signal(struct condvar *cond)`

输入有效条件变量，无返回值。从等待队首取出至多一个线程，设为 `RUNNABLE` 后 `add_task`。队列为空时什么都不发生，不存储这次通知。不能把条件变量做成信号量，不自动解锁、获取或转交任何互斥锁，也不阻塞通知线程。

## 静态阅读与 GDB 跟踪

```bash
git fetch origin
git worktree add ../ucore-ch8-reference origin/ch8-api-impl
cd ../ucore-ch8-reference
git rev-parse HEAD
nl -ba os/sync.c
nl -ba os/proc.c
```

按下一节准备用户程序并编译，再在两个终端运行：

```bash
# 终端 A
make gdbserver CHAPTER=8 BASE=1 TOOLPREFIX=riscv64-unknown-elf- BOOTLOADER=default
# 终端 B；显式禁用自动加载 .gdbinit，避免重复连接
gdb-multiarch -nx build/kernel
```

```gdb
set architecture riscv:rv64
target remote localhost:15234
break mutex_lock
break mutex_unlock
break semaphore_down
break semaphore_up
break cond_wait
break cond_signal
continue
```

在 QEMU 用户终端分别运行 `ch8b_spin_mut_race`、`ch8b_mut_race`、`ch8b_sync_sem`、`ch8b_test_condvar`。可以按原语分别设置断点，避免输出过多。使用 `info args`、`list`、`next`、`step` 与 `bt` 记录调用路径；在对应函数中用 `print *m`、`print *s` 或 `print cond->wait_queue` 观察状态。`print current_thread->tid` 和 `print current_thread->state` 可观察当前线程；断至 `sched` 前后时注意当前线程可能已切换。

报告至少解释：自旋式锁重新占用、阻塞式锁直接交接、信号量负计数与队列对应、条件等待醒来后重新加锁四种情形。简单测例未必触发每种竞争窗口；只有实际命中的路径才能作为动态证据，其他路径用源码推导并注明。如优化导致变量不可见，记录入口参数寄存器并查看 `disassemble /m`，不编造观察值。

## 运行与验收

环境需要 RISC-V GCC/binutils、QEMU、GDB、主机 C 编译器及 CMake。先按公共环境说明准备固定版本 `user`；来源为 `https://github.com/LearningOS/uCore-Tutorial-Test`，报告需记录实际测试 SHA 和教师补丁。

```bash
make user CHAPTER=8 BASE=1 TOOLPREFIX=riscv64-unknown-elf- BOOTLOADER=default
make clean
make build CHAPTER=8 BASE=1
make run CHAPTER=8 BASE=1 TOOLPREFIX=riscv64-unknown-elf- BOOTLOADER=default
```

在用户终端逐一运行下列本章基础用例，然后运行 `ch8b_usertest` 检查往章回归。不能用含死锁检测的拓展集合替代 `BASE=1`。

| 测例 | 验收对象 |
| --- | --- |
| `ch8b_spin_mut_race` | 自旋式互斥 |
| `ch8b_mut_race`、`ch8b_mut_phi_din` | 阻塞式互斥与竞争 |
| `ch8b_sync_sem`、`ch8b_mpsc_sem` | 信号量通知、生产消费 |
| `ch8b_test_condvar` | 条件等待、通知及重新加锁 |
| `ch8b_threads`、`ch8b_threads_arg` | 已提供的线程功能回归 |

上游测试库 `ch8b_usertest.c` 存在将 `ch8b_mut_phi_din.c` 当作程序名的错误项，公共环境准备应应用教师提供的测试修补。若直接使用未修补的上游版本，该项会导致 `exec` 失败，不能判为同步函数实现错误，也不能把该汇总写成通过。保留测试修补前后版本信息；学生不能通过删测例掩盖自身实现问题。

学生骨架可编译，运行到目标函数时应报 `TODO(ch8-api)` 并停止，属于未完成状态。提交前消除所有 6 个占位、完成代码范围检查、保存编译及基础测试原始输出并交报告。只证明实际运行的测试；不宣称死锁检测、SMP 或全部边界已覆盖。

## 阶段验收

以下阶段用于安排学习进度和人工验收，沿用本章现有测例与 GDB 流程。每阶段记录“源码检查 / 构建 / 参考动态跟踪 / 自己实现运行”各自的实际结果。

仍有其他目标函数未完成时，可先完成参考跟踪、源码检查和构建；运行到其 TODO 应记录为“受未完成依赖阻塞”，不能记为整章通过，也不能临时复制参考函数、跳过调用或修改测试来完成阶段验收。最终仍须完成全部目标函数及本章原有验收。

| 阶段 | 实现范围 | 检查方式与完成依据 |
| --- | --- | --- |
| 互斥与交接 | `mutex_lock/mutex_unlock` | 对照参考实现分析自旋式和阻塞式等待；可将已有 `ch8b_spin_mut_race`、`ch8b_mut_race` 分别设为 INIT_PROC 观察已完成的互斥实现。 |
| 许可与通知 | `semaphore_down/up/cond_wait/signal` | 按原语补全后，分别使用已有 `ch8b_sync_sem`、`ch8b_test_condvar` 跟踪计数、等待状态和恢复路径；尚未触发的竞争情形进行源码推导。 |
| 整章验收 | 六个目标函数 | 全部完成后运行原有 `ch8b_usertest`；说明当前单核执行前提，以及实际动态观察的范围。 |

分原语观察可使用已有程序，例如先完成两个互斥函数后执行：

```bash
make clean
make test CHAPTER=8 BASE=1 INIT_PROC=ch8b_mut_race TOOLPREFIX=riscv64-unknown-elf- BOOTLOADER=default
```

替换 INIT_PROC 时重新清理和构建；单个程序通过不等于其余同步原语已完成。

## 答辩问题

可从下表抽取两个问题，结合本人提交代码和报告进行约 5—8 分钟交流。先说明预期状态变化，再定位源码或已有日志；没有实际触发的分支明确标记为推导。不要求为答辩修改禁止改动的文件或新增测试。实现与参考相同可以是合理结果，评价依据是语义解释、证据对应和对边界的理解。

| 问题 | 建议说明材料 |
| --- | --- |
| 阻塞锁唤醒等待者时，为什么 locked 可以保持为 1？这与自旋式锁有何不同？ | 等待队列、RUNNABLE 状态与资源交接位置。 |
| 信号量 count 为负时表示什么？up 后为零时应否唤醒等待者？ | 计数变化、排队人数和对应源码分支。 |
| signal 后通知线程仍持锁时，等待线程能否从 cond_wait 返回？当前解锁与入队顺序依赖什么执行前提？ | 醒来后的重新加锁、可能再次阻塞的位置和单核显式调度假设。 |

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

课程记录工具须先在 `main` 安装一次。
