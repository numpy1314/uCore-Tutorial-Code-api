# 第五章：进程生命周期 API 实验

## 实验内容

沿用 uCore 的 C 实现和已有调度、页表、陷阱处理，完成进程从分配、复制、程序替换到退出、等待回收的闭环。参考分支 `ch5-api-impl`，独立实现分支 `ch5-api`。本章只挖空 `os/proc.c` 的六个函数：`allocproc`、`freeproc`、`fork`、`exec`、`wait`、`exit`。每个挖空函数以 `TODO(ch5-api)` 标识；函数签名、结构体和调用方均保留。

## 实验要求

1. **限定修改范围。** 只能在 `os/proc.c` 内实现上述六个函数及确有必要的文件内辅助函数；保持接口签名、结构定义、已提供函数语义和调用关系。不能修改其他任何代码文件、用户测例、构建脚本或校验配置；报告、日志放在 `reports/`。范围以 `lab.json` 为准。
2. **静态分析与动态跟踪。** 阅读 `ch5-api-impl`，使用 GDB 跟踪目标函数，将任务要求逐条对应到源码和实际状态变化，形成 Markdown 报告。每个源码引用须包含参考实现的完整 commit SHA、文件路径、函数名与行号，可附固定提交链接；每项动态观察须保留断点、命令、变量或寄存器和关键日志。
3. **独立实现。** 在 `ch5-api` 完成六个函数，不以直接复制参考函数作为独立实现。逐项比较自己的实现与参考实现的异同，说明选择依据和产生差异的原因，并用测试结果支持结论。
4. **问题与解决思路。** 描述实验过程遇到的主要问题、定位证据、原因分析、解决思路和复测结果。使用 [报告模板](reports/lab-report.md)，不能只提交输出文字。

## 已提供的执行环境

| 位置 | 已提供内容 |
| --- | --- |
| `os/proc.h`、`os/proc.c` | 进程池、每个槽位独有的静态内核栈和 trapframe、PID 分配、就绪队列、调度与切换 |
| `os/vm.c` | `uvmcreate`、`uvmcopy`、`uvmunmap`、`uvmfree` 等内存操作 |
| `os/loader.c` | 按名称查询嵌入的用户程序、映射程序与用户栈、初始化入口与堆边界 |
| `os/syscall.c` | `sys_clone`、`sys_exec`、`sys_wait`、`sys_exit` 与用户参数适配 |
| `os/trap.c`、`os/trampoline.S`、`os/switch.S` | 用户态陷入/返回及内核上下文切换 |

本章按原有单核协作式内核路径理解这些接口，不添加多核锁协议。进程状态包括 `UNUSED`、`USED`、`RUNNABLE`、`RUNNING`、`ZOMBIE`；已有 `SLEEPING` 枚举不意味着本章 `wait` 已采用睡眠队列。

`trapframe` 保存用户寄存器；`context` 保存内核切换现场，两者不能混用。`p->ustack` 在本章实际保存用户栈起点，尽管结构字段旁的上游注释写作 kernel stack。`max_page` 是需要管理的用户虚拟页范围上界，不能误认为已经分配的物理页总数。

## 接口契约

### 1. `struct proc *allocproc()`

**职责与输入：** 从已由 `proc_init` 初始化的 `pool` 找一个 `UNUSED` 槽位，为新进程准备初始内核执行环境；无参数，不加载用户程序。

**输出：** 成功返回 `USED` 进程；进程槽位耗尽或 `uvmcreate` 的根页分配失败时返回空指针，失败槽位仍为 `UNUSED`。下层映射分配失败仍可能触发已有 panic，不要求将所有 OOM 转换为可恢复错误。

**副作用与边界：** 分配新 PID，创建映射了 trampoline 和该槽位 trapframe 的用户页表；保留 `proc_init` 设定的内核栈/trapframe 地址。清零 `ustack`、`max_page`、父指针、退出码、堆边界、内核上下文、栈内容和用户陷阱上下文。`context.ra` 指向 `usertrapret`，`context.sp` 指向该进程的内核栈顶。本函数不加入就绪队列，也不进入用户态。PID 单调分配，失败可留下编号空洞。

### 2. `void freeproc(struct proc *p)`

**职责与输入：** 释放有效进程 `p` 所拥有的用户地址空间，复用已提供的 `freepagetable`。调用者保证该进程不会继续使用已释放的用户映射。

**输出与副作用：** 有页表时释放用户映射及页表页，令 `pagetable = 0`、`state = UNUSED`；页表为空时不重复释放。不释放静态内核栈或静态 trapframe，也不把 trampoline 的共享物理页交给页分配器。保留 PID、父指针和退出码，供 `exit` 将进程改为 `ZOMBIE` 后由父进程查询。本函数不切换 CPU、不移除队列项。当前进程仍需在静态内核栈上走完退出路径，因此不能将整个进程对象清零。

### 3. `int fork()`

**职责与输入：** 复制当前运行进程的用户执行环境，创建其直接子进程。无参数；当前进程的地址空间和 trapframe 必须有效。

**输出：** 父进程得到子 PID；子进程通过自己的 trapframe 得到 `a0 = 0`。两种返回发生在各自的用户执行流中，不是 C 函数调用两次返回。沿用参考策略，进程分配或用户页复制失败会 panic。

**副作用与边界：** 复用 `allocproc`，通过 `uvmcopy` 深拷贝用户页；继承 `max_page`、用户栈位置和 `heap_bottom/program_brk`，复制用户寄存器后仅将子返回值改成零。子进程使用自己新分配的内核上下文、内核栈和 trapframe，设置 `parent` 为当前进程，变为 `RUNNABLE` 并恰好入队一次。父进程的用户数据和寄存器不被覆盖，不重新加载程序，不在这里额外推进 `epc`；陷阱处理已处理系统调用后的用户 PC。

### 4. `int exec(char *name)`

**职责与输入：** `name` 是系统调用层复制到内核的、以零结尾的程序名称；以该程序替换当前进程的用户内容。

**输出：** 名称不存在返回 `-1`，当前程序与元数据不变；成功返回 `0`，之后由既有陷阱返回路径进入新程序。加载过程中内存不足仍按下层策略 panic；不要求为此实现事务式回滚。

**副作用与边界：** 必须先查找程序再销毁旧用户映射；保留现有页表的 trampoline/trapframe 映射，清除旧用户页面并重置范围，再调用 `loader` 建立新内容。入口 `epc`、用户 `sp`、栈位置、`max_page` 和堆边界由 loader 更新。保留 PID、父子关系、静态内核栈和当前内核调用现场；不分配新进程，不加入新队列项。loader 按既有实现将状态设为 `RUNNABLE`，本章不另改这一约定；不要误将此状态赋值等同于入队。本章 `exec` 尚无 argv 参数。

### 5. `int wait(int pid, int *code)`

**职责与输入：** 等待当前进程的直接子进程；`pid > 0` 指定子 PID，`pid <= 0` 接受任意直接子进程。`code` 是 `sys_wait` 完成用户地址转换后提供的有效、可写内核地址，不是未经转换的用户虚拟地址；本章接口不接受空指针。

**输出：** 回收到匹配的 `ZOMBIE` 时返回其 PID，并写入退出码；没有匹配子进程时返回 `-1` 且不写退出码。匹配的孩子存在但尚未退出时不得提前报告成功或返回 `-1`。

**副作用与边界：** 扫描进程池，过滤非 `UNUSED`、父指针及 PID。僵尸的用户内存已经在 `exit` 释放，仅将槽位标成 `UNUSED`，避免二次释放。若仍需等待，将父进程改为 `RUNNABLE`、入队一次并 `sched`，恢复后重新扫描。不得忙等独占 CPU，不回收其他父进程的孩子，不将仍运行的孩子释放。

### 6. `void exit(int code)`

**职责与输入：** 结束当前进程；`code` 是向父进程报告的退出码。

**输出：** 不再返回原用户程序；通过 `sched` 切换到调度器。函数签名沿用已有 `void`，系统调用包装另有 noreturn 约定。

**副作用与边界：** 先记录退出码，再 `freeproc` 回收用户内存。存在父进程时设为 `ZOMBIE` 保留身份/退出码；无父进程时保持 `UNUSED`。遍历孩子将其 `parent` 置空，沿用本章不交给 init 进程收养的简化策略；这也不补做已经退出的孤儿回收。退出进程不再入队。`sched` 前状态不能为 `RUNNING`，不得返回已释放的用户地址空间。

## 源码阅读与 GDB 跟踪

先记录参考版本并取出带行号源码：

```bash
git switch ch5-api-impl
git rev-parse HEAD
nl -ba os/proc.c
make user CHAPTER=5 BASE=1 TOOLPREFIX=riscv64-unknown-elf- BOOTLOADER=default
make clean
make build CHAPTER=5 BASE=1 INIT_PROC=ch5b_usertest
make gdbserver CHAPTER=5 BASE=1 INIT_PROC=ch5b_usertest TOOLPREFIX=riscv64-unknown-elf- BOOTLOADER=default
```

另一个终端启动 GDB；`-nx` 避免 `.gdbinit` 自动连接同一端口：

```bash
riscv64-unknown-elf-gdb -nx build/kernel
```

```gdb
set pagination off
set logging file reports/ch5-gdb.log
set logging enabled on
target remote :15234
break fork
continue
set $parent = current_proc
print $parent->pid
print $parent->program_brk
list fork
next
```

在 `list fork` 显示的 `add_task(np)` 所在行设源码断点，继续到该行，观察 `np->pid`、`np->parent`、`np->trapframe->a0`、两个页表指针与两组堆边界；用 `next` 执行入队，再在调度/陷阱返回处确认子进程实际执行。不要假设优化后任意时刻局部变量都可读，可在初始化完成且变量仍存活的行观察，必要时用一致的无优化调试构建并记录编译参数。

接着分别跟踪：

- `break exec`：记录当前 PID、`name`、旧 `epc/sp/max_page`；在 loader 返回后的源码行观察新值，确认 PID 不变。触发失败查找时确认旧映射未销毁。
- `break exit`：记录 `code`、当前进程及其父指针；保存 `set $child = current_proc`。在 `sched` 前确认页表已清空、状态和退出码保留。
- `break wait`：记录父进程、筛选 PID、`code` 指针；在回收前后观察 `$child->state` 及返回 PID。无匹配孩子与仍有运行中孩子的分支分别给出证据。

GDB `finish` 不适用于永不返回的 `exit`。源码单步不自动证明返回到用户态；至少保留一次子进程真实输出与对应 PID。不要在 GDB 中调用会分配/调度的内核函数来代替被测执行。

## 运行与验收

按仓库环境准备说明准备工具链和 `user`。内核使用 `riscv64-unknown-elf-*`，用户库原构建使用 `riscv64-linux-musl-*`，QEMU 为 `qemu-system-riscv64`。从本章根目录执行，两个 make 分开确保用户程序先完成再打包：

```bash
make user CHAPTER=5 BASE=1 TOOLPREFIX=riscv64-unknown-elf- BOOTLOADER=default
make clean
make test CHAPTER=5 BASE=1 INIT_PROC=ch5b_usertest TOOLPREFIX=riscv64-unknown-elf- BOOTLOADER=default
```

参考实现与学生实现分别保留日志。未填骨架只需可编译；首次进入目标函数会输出 `TODO(ch5-api)` 并停止，这是预期现象，不能算运行通过。

验收检查 `ch5b_usertest` 列出的逐项运行结果、父子 PID 关系和退出码，再核对 `ch5b Usertests passed!`。所有该套件顶层基础子测例应以 `0` 退出；内部故意以非零码退出的子进程应由对应测例断言验证。单独运行 `ch5b_exec_simple` 补充观察程序替换。启动到 usershell、总标语或 QEMU 的宿主退出状态不能替代逐项结果，尤其不能把 exec 失败后恰好退出 `0` 当作目标程序成功执行。

本轮不实现上游已留空的 `sys_spawn`、`sys_set_priority`，不要求往章 mmap/调度拓展，不能用 `BASE=0/2` 全拓展测试作为本章已完成的证据。资源耗尽、无效用户指针和孤儿回收不是完整 POSIX 语义；基础测例通过也不能证明所有这些边界。

## 参考基线修正

本章基于上游 `ch5` 提交 `8b1edfa`：补充 `allocproc` 根页分配失败时恢复空闲槽位；补充 `fork` 对用户栈位置及两项堆边界的继承，避免子进程内存元数据与复制的页面不一致。其余原有扩展 TODO 保留。分析报告引用改造后 `ch5-api-impl` 的实际完整 SHA，不能把此上游短 SHA 当作参考函数的现版本。

## 统一检查入口


统一验收采用 QEMU 附带的 OpenSBI（安装 `opensbi`，参数 `BOOTLOADER=default`）；仓库原始 RustSBI 仍保留用于历史环境，不能将旧固件在新版 QEMU 下的启动失败归因于学生函数。下列手动构建/GDB 命令同样需要先运行 `python3 tools/run_lab.py --prepare-only`（第 1 章无需用户程序），并使用 `TOOLPREFIX=riscv64-unknown-elf-` 和 `BOOTLOADER=default`。完整工具安装说明见主分支 `docs/api-labs.md`。

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
