# uCore ch3 API 实验：多道程序与分时调度

## 实验内容

本实验基于 `ch3-api` 分支，要求同学借助文档或 AI 完成 uCore 第三章的进程管理与分时调度核心，使多个静态加载的应用能够在单核环境中轮流执行。需要实现的能力包括进程管理状态初始化、从内核启动阶段进入应用、当前进程暂停后的调度，以及当前进程退出后的调度。

代码提供全部数据结构、汇编上下文切换、应用加载、陷阱处理、时钟中断与系统调用实现。学生只需要完成 `os/proc.c` 中四处标有 `TODO(ch3-api)` 的函数：

| 函数 | 学习目标 |
| --- | --- |
| `proc_init()` | 建立进程表、静态运行资源与调度器启动上下文之间的关系 |
| `scheduler()` | 选择可运行进程并在调度器上下文和进程上下文之间切换 |
| `yield()` | 保存当前进程的继续运行资格并主动交出 CPU |
| `exit(int code)` | 终止当前进程并将执行权交回调度器 |

这四个函数的名称、参数、返回类型以及在现有内核中的调用关系必须保持不变。本实验仅允许修改上表四个函数的函数体，不得新增文件级辅助函数或改变系统调用 ABI。

本文按模块和接口说明职责、输入、输出与约束，所有约定以本仓库 `ch3-api` 分支代码为准。

## 实验要求

1. **代码范围**：只允许修改 `os/proc.c` 中 `proc_init()`、`scheduler()`、`yield()`、`exit(int code)` 四个函数的函数体；签名、全局数据结构和文件内其他函数保持不变。禁止修改任何其他代码文件、构建脚本、测试程序与 `lab.json`。报告和真实日志放入 `reports/`，课程过程记录保留于 `.ai/`。
2. **静态分析与动态跟踪**：先在 `ch3-api-impl` 参考分支阅读上述函数及其调用者，再用 GDB 跟踪进程状态与上下文切换；形成 Markdown 分析报告，逐项建立“任务要求—参考实现—运行现象”的对应关系。每项源码引用必须包含参考 commit、文件路径、函数名与行号，不能只给会变化的分支链接。
3. **独立实现与对比**：回到 `ch3-api`，独立完成四个函数；完成后逐项比较自己的实现与参考代码，说明相同点、不同点及其原因，并用运行结果验证语义。
4. **问题与解决思路**：记录实验中的主要问题、分析过程、解决方法和验证结果。填写 [报告模板](reports/lab-report.md)，提交代码、报告及实际跟踪/运行日志，禁止把预期结果写成已经观测的结果。

## 进程管理与调度接口

本章使用静态进程表 `pool`、启动上下文 `idle` 和当前进程指针 `current_proc` 记录进程及调度状态。各接口分工如下：

| 执行阶段 | 接口 | 职责 |
| --- | --- | --- |
| 准备进程资源 | `proc_init()`，配合已提供的 `allocproc()` 与 `run_all_app()` | 初始化进程槽位及首次运行所需资源 |
| 首次运行应用 | `scheduler()` 的首次选择与切换 | 从内核启动流程进入第一个应用 |
| 暂停并重新调度 | `yield()`、已提供的 `sched()` 和 `scheduler()` | 保留当前执行进度并运行后继进程 |
| 退出并调度其他进程 | `exit()`、已提供的 `sched()` 和 `scheduler()` | 结束当前执行生命周期并运行后继进程 |

`scheduler()` 是一个常驻循环，既负责首次应用启动，也负责每次从 `sched()` 返回后选择下一个可运行进程。

## `os::proc` 模块

`os/proc.c` 和 `os/proc.h` 定义进程状态、进程控制块、静态运行资源以及调度接口。内核在单核环境运行，同一时刻至多有一个应用进程处于 `RUNNING` 状态。

### `enum procstate`

`procstate` 描述进程槽位的生命周期状态：

```c
enum procstate { UNUSED, USED, SLEEPING, RUNNABLE, RUNNING, ZOMBIE };
```

| 状态 | 本章含义 |
| --- | --- |
| `UNUSED` | 空闲槽位，可以被 `allocproc()` 使用；退出后的槽位也回到该状态 |
| `USED` | 已分配并完成内核上下文初始化，应用尚未准备运行 |
| `SLEEPING` | 为后续章节保留的阻塞状态，本实验不会调度它 |
| `RUNNABLE` | 应用已加载或暂时让出 CPU，等待调度 |
| `RUNNING` | 当前获得 CPU 的应用进程 |
| `ZOMBIE` | 为后续章节保留的退出状态，本章退出流程使用 `UNUSED` |

本章的主要状态转换如下：

```text
proc_init       allocproc       run_all_app        scheduler
  任意状态 ──> UNUSED ────────> USED ───────────> RUNNABLE ─────> RUNNING
                                                        ^             |
                                                        |             |
                                                        +── yield() ──+

RUNNING ── exit() ──> UNUSED
```

### `struct context`

`context` 保存内核上下文切换需要保留的寄存器：

```c
struct context {
    uint64 ra;
    uint64 sp;
    uint64 s0;
    uint64 s1;
    uint64 s2;
    uint64 s3;
    uint64 s4;
    uint64 s5;
    uint64 s6;
    uint64 s7;
    uint64 s8;
    uint64 s9;
    uint64 s10;
    uint64 s11;
};
```

`swtch(old, new)` 将当前寄存器保存到 `old` 指向的结构，再从 `new` 指向的结构恢复寄存器。它从“新上下文上次调用 `swtch` 的位置”继续执行。首次运行的进程由已提供的 `allocproc()` 把 `ra` 初始化为 `usertrapret`，把 `sp` 初始化为对应内核栈顶。

### `struct proc`

```c
struct proc {
    enum procstate state;
    int pid;
    uint64 ustack;
    uint64 kstack;
    struct trapframe *trapframe;
    struct context context;
    uint64 syscall_counts[MAX_SYSCALL_NUM];
};
```

`proc` 是本章的进程控制块。`state` 决定它是否具备调度资格；`context` 保存内核态恢复位置；`trapframe` 保存用户态寄存器；`kstack` 和 `ustack` 分别指向内核栈与用户栈；`syscall_counts` 按系统调用号记录该进程的调用次数。

进程编号 `pid` 与进程表数组下标用途不同。调度器遍历的是 `pool` 中的槽位，不能假定 `pid` 连续或等于数组下标。

### 全局调度状态

```c
struct proc pool[NPROC];
struct proc idle;
struct proc *current_proc;
```

- `pool` 是固定容量的进程表。
- `idle` 保存内核启动阶段以及调度循环的上下文，不表示一个用户应用。
- `current_proc` 指向当前运行的应用进程；进入首次调度前，它指向 `idle`。

静态数组 `kstack`、`ustack` 和 `trapframe` 与 `pool` 使用相同下标。初始化必须维持这种对应关系，保证每个进程槽位拥有独立且长期有效的上下文存储。

## `proc_init`

```c
void proc_init(void);
```

description: `proc_init` 在内核启动早期初始化进程管理状态。`main()` 在加载应用、设置陷阱和定时器之前调用它。该函数只准备槽位和静态资源；应用的分配、装载以及 `RUNNABLE` 状态由已提供的 `run_all_app()` 完成。

### 输入

没有显式参数。输入来自静态分配的 `pool`、`kstack`、`ustack`、`trapframe`、`idle` 与启动栈符号 `boot_stack_top`。

### 输出

- `pool` 中每个槽位均为 `UNUSED`。
- 每个槽位的内核栈、用户栈和陷阱帧指针与相同数组下标的静态存储对应。
- 每个槽位的系统调用计数全部为零。
- `idle` 表示启动调度上下文，其内核栈指向 `boot_stack_top`，进程号为 `0`。
- `current_proc` 指向 `idle`。

### 关键约束

- 初始化所有 `NPROC` 个槽位，不能只初始化实际应用数量。
- 各槽位的栈、陷阱帧和系统调用计数相互独立。
- 本函数不得把任何槽位设为 `RUNNABLE` 或执行上下文切换。
- 函数返回后，`allocproc()` 和 `run_all_app()` 必须能够直接使用这些状态。

## `scheduler`

```c
void scheduler(void) __attribute__((noreturn));
```

description: `scheduler` 是常驻内核调度循环。`main()` 在所有应用完成加载后调用它。调度器寻找 `RUNNABLE` 进程，将其设为当前运行进程，然后从 `idle.context` 切换到该进程的 `context`。进程调用 `sched()` 后，执行流回到调度器上一次 `swtch()` 的位置。

### 输入

没有显式参数。`run_all_app()` 已在 `pool` 中准备好实际应用对应的 `RUNNABLE` 槽位；其他槽位可能处于不能调度的状态。

### 输出

函数持续选择可运行进程并移交 CPU，不返回 `main()`。首次选择使第一个可运行应用开始执行。后续选择发生在进程主动让出、被时钟抢占或退出以后。

### 关键约束

- 只选择状态为 `RUNNABLE` 的进程。
- 按 `pool` 的槽位顺序扫描；某个进程返回调度器后，继续检查它后面的槽位，从而形成轮转顺序。
- 切换前将目标状态设为 `RUNNING`，并让 `current_proc` 指向同一个进程。
- `swtch()` 的两个参数必须指向在切换全过程中保持有效的上下文结构。
- 从进程返回后重新依据状态判断调度资格；退出进程不能再次运行。
- 没有可运行进程时继续等待。全部应用结束由已提供的 `finished()` 终止内核。

## `yield`

```c
void yield(void);
```

description: `yield` 暂停当前进程并交出 CPU。它同时服务于应用通过 `sys_sched_yield` 的主动让出和时钟中断触发的抢占。当前进程仍具有后续执行资格。

### 输入

没有显式参数。`current_proc` 指向调用发生时的 `RUNNING` 进程，其内核栈和 `context` 存储有效。

### 输出

当前进程进入 `RUNNABLE` 状态并通过 `sched()` 返回调度器。当它以后再次被选中时，从原有内核控制流继续，本次 `yield()` 调用随后返回。

### 关键约束

- 调用 `sched()` 前必须先把当前进程从 `RUNNING` 改为 `RUNNABLE`，否则 `sched()` 会触发检查失败。
- 不得清空或重新初始化当前进程的上下文、陷阱帧和系统调用计数。
- 主动让出和定时器抢占共享相同的状态转换与恢复语义。

## `exit`

```c
void exit(int code);
```

description: `exit` 终止当前进程。正常的 `sys_exit` 和导致应用终止的异常处理都会调用它。退出进程失去调度资格，调度器随后运行其他进程。

### 输入

`code` 是应用退出码。`current_proc` 指向需要终止的 `RUNNING` 进程。

### 输出

当前进程变为 `UNUSED`，`finished()` 记录一个应用完成，随后通过 `sched()` 返回调度器。正常执行不会回到退出调用点；最后一个应用结束时，`finished()` 终止内核。

### 关键约束

- 在调用 `sched()` 前移除当前进程的运行资格。
- 每个退出进程只调用一次 `finished()`。
- 不得把退出进程重新设为 `RUNNABLE`，也不得恢复它的应用执行现场。
- 保留现有日志，使退出码与进程号可被观察。

## 已提供的配套功能

以下代码已经完整提供，学生应保留其实现和调用关系：

| 代码位置 | 已提供内容 |
| --- | --- |
| `os/loader.c` | 应用数量读取、应用装载、进程分配、用户入口与栈初始化 |
| `os/proc.c::allocproc()` | 选择 `UNUSED` 槽位，初始化 PID、陷阱帧、内核上下文和系统调用计数 |
| `os/proc.c::sched()` | 检查当前进程状态并从进程上下文切换回 `idle.context` |
| `os/switch.S` | `swtch()` 的 RISC-V 寄存器保存与恢复 |
| `os/trap.c` | 用户陷阱、定时器抢占、应用异常退出和用户态恢复 |
| `os/timer.c` | 时钟读取与下一次定时器中断设置 |
| `os/syscall.c` | 系统调用分发、`sys_sched_yield`、`sys_exit` 和完整的 `sys_trace` |

`sys_trace` 依赖 `current_proc` 与实际运行进程一致，并访问该进程独立的 `syscall_counts`。调度实现必须保持这项约束。

## 完整执行流程

1. `main()` 调用 `proc_init()`，建立空进程表和 `idle` 调度上下文。
2. `loader_init()` 取得静态应用数量。
3. `run_all_app()` 为每个应用调用 `allocproc()`，设置用户入口和用户栈，并将进程设为 `RUNNABLE`。
4. `main()` 调用 `scheduler()`；调度器选择首个可运行进程并执行 `swtch()`。
5. 进程首次恢复到 `usertrapret`，随后进入用户态。
6. 应用主动让出或发生时钟中断时，`yield()` 把它设为 `RUNNABLE`，`sched()` 切回调度器。
7. 应用退出或发生致命异常时，`exit()` 移除其调度资格并切回调度器。
8. 调度器继续选择其他 `RUNNABLE` 进程，直到 `finished()` 发现全部应用结束。

## 静态阅读与 GDB 动态跟踪

在独立目录阅读参考分支，避免把参考实现覆盖到作业分支：

```bash
git fetch origin
git worktree add ../ucore-ch3-reference origin/ch3-api-impl
cd ../ucore-ch3-reference
git rev-parse HEAD
nl -ba os/proc.c
```

记录 `proc_init → run_all_app → scheduler → swtch → usertrapret` 的启动调用链，以及 `sys_sched_yield/usertrap → yield → sched → swtch` 的后续调度链。`swtch` 保存的是内核上下文；用户寄存器保存在 `trapframe`，两者不能混为一谈。

参考目录也需要自己的 `user/` 测试仓库。先准备应用，再启动 QEMU GDB 服务；本章完整测试使用 `BASE=2`（测试仓库仅对 `BASE=1` 单独筛选，`BASE=2` 在本章等价于默认完整集合）：

```bash
python3 tools/run_lab.py --prepare-only
make clean
make user CHAPTER=3 BASE=2 TOOLPREFIX=riscv64-unknown-elf- BOOTLOADER=default
make gdbserver CHAPTER=3 BASE=2 LOG=info TOOLPREFIX=riscv64-unknown-elf- BOOTLOADER=default
```

另开终端，在参考目录显式加载符号并连接（`-nx` 跳过仓库的自动连接配置）：

```bash
mkdir -p reports
gdb-multiarch -nx build/kernel
```

也可将 `gdb-multiarch` 替换为支持 RISC-V 的 `riscv64-unknown-elf-gdb`。在 GDB 中：

```gdb
set architecture riscv:rv64
set pagination off
set logging file reports/gdb.log
set logging enabled on
target remote :15234
break proc_init
continue
finish
p current_proc == &idle
p pool[0].state
p/x pool[0].kstack
p/x pool[1].kstack
p pool[0].syscall_counts[64]
break scheduler
continue
p pool[0].state
p/x pool[0].context.ra
p/x pool[0].context.sp
break swtch
continue
p current_proc->pid
p current_proc->state
info registers a0 a1 sp ra
bt
```

在第一次 `swtch` 处，比较 `a0/a1` 与 `&idle.context`、`&current_proc->context`；通过 `disassemble swtch` 与 `si` 观察保存/恢复寄存器。不要在上下文切换处用 `finish` 假设一定返回原调用栈。初始 `ra` 应对应 `usertrapret`，首次选中时进程应为 `RUNNING`。

随后按断点号禁用 `swtch` 断点，添加 `break yield` 与 `break sched`。在 `yield` 停下时保存 `set $yielded = current_proc`，用 `next` 执行状态更新；在 `sched` 入口观察 `$yielded->state` 应为 `RUNNABLE`，`bt` 区分主动让出与定时器抢占。添加 `break exit`，记录 `code` 与 PID；用 `next` 到状态更新后观察 `UNUSED`，核对其不再被选中。调度恢复后再次观察同一 PID 的执行进度，解释为什么 `yield` 可以返回而 `exit` 不应返回。

所有行号都从实际参考 commit 的 `nl -ba` 和 GDB `list` 获取；若优化使局部变量不可见，可观察 `current_proc`、全局表和寄存器，不得把猜测填作跟踪结果。

## 运行与验收

回到学生分支，在根目录准备测试仓库并运行：

```bash
python3 tools/run_lab.py --prepare-only
make clean
make test CHAPTER=3 BASE=2 TOOLPREFIX=riscv64-unknown-elf- BOOTLOADER=default
```

已有 `user/` 时，准备工具会核对固定提交与教师补丁；不匹配时先保留原目录并另行准备，不能覆盖自己的修改。切换章节或 BASE 后务必先 clean，防止静态应用镜像沿用上一次构建结果。记录测试仓库的实际 commit；`make test` 只运行应用，不是自动评分器，不能只依据进程退出码判断通过。

未完成骨架在 `proc_init` 打印 `TODO(ch3-api)` 后停机，仅表示骨架可以构建。完成后必须通过应用断言，至少观察到：

```text
Test write A OK!
Test write B OK!
Test write C OK!
Test sleep1 passed!
Test trace OK!
Test sleep OK!
```

最后的 `all apps over` 是 `finished()` 的正常终止路径，在当前内核中通过 `panic` 输出；其他 panic、assert、停滞或缺少关键成功行均需调查。多个应用的输出允许交错，不要求固定行序。报告应包含真实运行日志及对轮转、定时器抢占和退出后不再调度的解释。

## 提交要求

```bash
git status
git diff
git add os/proc.c reports
git commit -m "finish ucore ch3 api lab"
```

提交前应能解释四个接口的状态变化、两次 `swtch()` 参数分别保存和恢复什么，以及 `yield()` 返回而 `exit()` 不再返回的原因。报告引用参考分支的具体 commit，不将参考答案复制为分析报告。

## 阶段验收

以下阶段用于安排学习进度和人工验收，沿用本章现有测例与 GDB 流程。每阶段记录“源码检查 / 构建 / 参考动态跟踪 / 自己实现运行”各自的实际结果。

仍有其他目标函数未完成时，可先完成参考跟踪、源码检查和构建；运行到其 TODO 应记录为“受未完成依赖阻塞”，不能记为整章通过，也不能临时复制参考函数、跳过调用或修改测试来完成阶段验收。最终仍须完成全部目标函数及本章原有验收。

| 阶段 | 实现范围 | 检查方式与完成依据 |
| --- | --- | --- |
| 初始状态 | `proc_init` | 在参考实现核对槽位、栈、trapframe 和 `current_proc` 的对应关系；检查自己的初始化并构建。 |
| 切换与继续 | `scheduler/yield/exit` | 完成四个函数后，使用现有 yield 程序跟踪进程让出与恢复，以及退出后的状态。 |
| 整章验收 | 四个目标函数 | 运行本章原有 `BASE=2` 集合，核对各应用退出记录与 trace 结果。 |

## 答辩问题

可从下表抽取两个问题，结合本人提交代码和报告进行约 5—8 分钟交流。先说明预期状态变化，再定位源码或已有日志；没有实际触发的分支明确标记为推导。不要求为答辩修改禁止改动的文件或新增测试。实现与参考相同可以是合理结果，评价依据是语义解释、证据对应和对边界的理解。

| 问题 | 建议说明材料 |
| --- | --- |
| 为什么 trapframe 和 context 不能互换？一次 yield 从哪里继续？ | 保存的寄存器类别、swtch 调用点和恢复位置。 |
| 调度前应保持 current_proc 与进程状态怎样的关系？ | 一次切换前后的指针、状态与 PID。 |
| 退出进程为何不能重新进入 RUNNABLE？当前扫描顺序如何让其他进程获得机会？ | scheduler、exit 和实际调度记录。 |

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
