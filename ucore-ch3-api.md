# uCore ch3 API 实验：进程与协作式调度

## 实验内容

本实验基于 `ch3-api` 分支，要求同学借助文档或 AI 完成 uCore 第三章的进程管理与协作式调度核心，使多个静态加载的应用能够在单核环境中轮流执行。需要实现的能力包括进程管理状态初始化、从内核启动阶段进入应用、当前进程暂停后的调度，以及当前进程退出后的调度。

代码提供全部数据结构、汇编上下文切换、应用加载、陷阱处理、时钟中断与系统调用实现。学生只需要完成 `os/proc.c` 中四处标有 `TODO(ch3-api)` 的函数：

| 函数 | 学习目标 |
| --- | --- |
| `proc_init()` | 建立进程表、静态运行资源与调度器启动上下文之间的关系 |
| `scheduler()` | 选择可运行进程并在调度器上下文和进程上下文之间切换 |
| `yield()` | 保存当前进程的继续运行资格并主动交出 CPU |
| `exit(int code)` | 终止当前进程并将执行权交回调度器 |

这四个函数的名称、参数、返回类型以及在现有内核中的调用关系必须保持不变。学生可以自行设计内部辅助函数，但不应修改测试程序所依赖的系统调用 ABI。

本文沿用 rCore 第三章 API 实验按模块和接口描述职责、输入、输出与约束的方式，并将其语义转换为 uCore 的 C 语言进程模型。本文中的约束以本仓库 `ch3-api` 分支代码为准。

## 与 rCore 第三章接口的对应关系

rCore 将任务管理状态集中在 `TaskManager` 中；uCore 使用静态进程表 `pool`、启动上下文 `idle` 和当前进程指针 `current_proc` 表达同一类状态。两者的代码组织不同，但实验目标一致。

| rCore ch3 API | uCore ch3 API | 对应语义 |
| --- | --- | --- |
| `TASK_MANAGER` 初始化 | `proc_init()`，配合已提供的 `allocproc()` 与 `run_all_app()` | 准备任务/进程槽位及首次运行所需资源 |
| `run_first_task()` | `scheduler()` 的首次选择与切换 | 从内核启动流程进入第一个应用 |
| `suspend_current_and_run_next()` | `yield()`、已提供的 `sched()` 和 `scheduler()` | 保留当前执行进度并运行后继进程 |
| `exit_current_and_run_next()` | `exit()`、已提供的 `sched()` 和 `scheduler()` | 结束当前执行生命周期并运行后继进程 |

uCore 的 `scheduler()` 是一个常驻循环。它既完成首次应用启动，也处理后续每次从 `sched()` 返回后的选择，因此不能机械地把 rCore 的函数体翻译成 C。

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

## 运行与验收

先把测试程序仓库放入根目录的 `user` 文件夹：

```bash
git clone https://github.com/LearningOS/uCore-Tutorial-Test.git user
```

在仓库根目录运行：

```bash
make test BASE=2
```

构建系统会从 `ch3-api` 或 `ch3-api-impl` 分支名中识别第三章。`BASE=2` 包含任务切换、定时器、主动让出、休眠和 `sys_trace` 测试。

完成后的实现应通过现有应用断言并输出以下关键结果：

```text
Test write A OK!
Test write B OK!
Test write C OK!
Test sleep1 passed!
Test trace OK!
Test sleep OK!
```

最后出现 `all apps over` 表示所有测试应用已完成，是本章现有 `finished()` 的正常终止路径。

## 提交要求

完成实现并确认测试通过后，由学生手动检查和提交自己的修改：

```bash
git status
git diff
git add os/proc.c
git commit -m "finish ucore ch3 api lab"
```

提交前应能解释四个接口的状态变化、两次 `swtch()` 参数分别保存和恢复什么，以及 `yield()` 返回而 `exit()` 不再返回的原因。
