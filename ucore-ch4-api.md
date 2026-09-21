# uCore ch4 API 实验：Sv39 页表与地址转换

## 实验内容

本实验实现 uCore 的页表查找、建立映射、地址转换与撤销映射四项基础能力。学生在 `ch4-api` 完成 `os/vm.c` 中四个函数体，参考实现位于 `ch4-api-impl`。

| 函数 | 要完成的能力 | 主要调用者 |
| --- | --- | --- |
| `walk()` | 查找末级页表项，并按需建立中间页表 | `mappages`、`walkaddr`、`uvmunmap` |
| `mappages()` | 将虚拟地址范围映射到连续物理页 | 内核页表创建、应用加载、堆增长 |
| `walkaddr()` | 检查用户映射并返回物理页基址 | `copyin`、`copyout`、`copyinstr`、`useraddr` |
| `uvmunmap()` | 撤销映射，按调用者要求回收数据页 | `uvmdealloc`、`uvmfree` |

实验只覆盖基础页表 API。物理页分配、内核页表布局、应用加载、地址空间切换、用户数据复制、调度与陷阱汇编均已提供；原始课程中 `mmap`、`munmap`、`sys_trace` 等拓展 TODO 保留，不属于本轮实现或验收范围。不要用第四章全量拓展测试的失败推断本次四个 API 均不正确。

## 实验要求

1. **代码范围**：只允许修改 `os/vm.c` 中 `walk()`、`mappages()`、`walkaddr()`、`uvmunmap()` 四个函数的函数体；不得修改它们的签名、全局数据、同文件其他函数或新增文件级辅助函数。禁止修改其他任何代码文件、构建脚本、测试程序与 `lab.json`。Markdown 报告和真实日志放在 `reports/`，课程过程记录保留于 `.ai/`。
2. **静态分析与动态跟踪**：阅读 `ch4-api-impl` 的四个目标函数及其调用链，使用 GDB 观察三级页表、页表项标志、物理地址和撤销前后的映射。形成 Markdown 分析报告，逐项解释参考函数与任务描述的对应关系，引用中必须包含参考 commit、文件路径、函数名和行号。
3. **独立实现与对比**：在学生分支独立完成四个函数，运行基础应用及下面的页表动态检查；随后比较自己的实现与参考实现的异同，解释原因以及为何满足同一接口约定。
4. **问题与解决思路**：记录实验过程中主要问题、定位依据、解决方法和验证结果。填写 [报告模板](reports/lab-report.md)，提交真实 GDB 与运行日志；预期值与实际观测值分开记录。

## 页表接口与职责划分

| 功能 | 接口 | 约定 |
| --- | --- | --- |
| 查找或建立末级页表路径 | `walk` | 返回 PTE 指针；中间页表由 `kalloc` 分配 |
| 建立映射 | `mappages` | 一次映射多个连续物理页，以整数返回码表示结果 |
| 查询用户地址 | `walk`、`walkaddr`、已提供的 `useraddr` | `walkaddr` 返回物理页基址；`useraddr` 补上页内偏移 |
| 撤销映射 | `uvmunmap` | `do_free` 区分只撤销映射与同时回收数据页 |
| 创建地址空间与分配内存 | 已提供的 `kvmmake`、`bin_loader`、`uvmalloc` 等 | 保持已有实现，不属于本章修改范围 |

`walkaddr` 只检查 `V/U` 标志，没有表示所请求读写权限的参数，不能将它视为完整的访问权限检查。用户态的读、写、执行权限由硬件页表检查执行。

## 已提供的数据结构与前提

`os/riscv.h` 定义 `pagetable_t`、`pte_t`、`PTE_V/R/W/X/U`、`PA2PTE`、`PTE2PA`、`PX`、`PGSIZE` 和 `MAXVA`。本实验仅使用 4 KiB 叶子页，不实现大页。

- 一个页表页包含 512 个 64 位 PTE，Sv39 使用三级页表；中间项指向下一层，末级项指向数据页。
- 本仓库选用低地址范围 `0 <= va < MAXVA`，其中 `MAXVA = 1 << 38`，避免最高位符号扩展。该限制比完整 Sv39 的地址表示更窄。
- 页表根、中间页表以及数据页的生命周期不同：`uvmunmap` 可释放数据页，`freewalk` 递归释放已无叶子映射的页表页。
- 内核对可用物理 RAM 恒等映射，所以 `PTE2PA` 得到的中间页表地址可以作为内核指针访问。
- 调用者提供合法且不会算术溢出的区间。本轮不要求为恶意内核调用者设计通用参数校验，也不要求修改 TLB 刷新路径。

## `walk`

```c
pte_t *walk(pagetable_t pagetable, uint64 va, int alloc);
```

**输入**：合法页表根、虚拟地址 `va` 和是否允许分配中间页表的 `alloc`。现有页表使用 4 KiB 映射，不能含上层大页叶子。

**输出**：存在或成功建立到末级的路径时，返回末级 PTE 的地址；这个 PTE 本身可能仍是无效的。路径缺失且 `alloc == 0`，或中间页表分配失败，返回空指针。`va >= MAXVA` 触发 `panic("walk")`。

**约束**：先从第 2 级逐级下降至第 0 级。已有中间项必须复用；新页表必须清零，并将父项编码为新页表物理地址加 `PTE_V`，不设叶子的 R/W/X/U 位。本函数不分配数据页，不建立末级数据映射。若后续分配失败，先前建立的中间页表保留在树内，接口没有事务回滚承诺。

## `mappages`

```c
int mappages(pagetable_t pagetable, uint64 va, uint64 size,
             uint64 pa, int perm);
```

**输入**：`size > 0`，`[va, va + size)` 不溢出且位于允许的地址范围；`pa` 给出第一个虚拟页对应的物理页基址，调用者保证适当对齐及后续物理页有效。`perm` 是调用者选定的合法叶子权限。

**输出**：全部页面映射成功返回 0；中间页表无法分配或遇到已有有效映射时返回 -1（重映射保留已有日志）。

**约束**：处理从 `PGROUNDDOWN(va)` 到 `PGROUNDDOWN(va + size - 1)` 的所有页面。每个叶子项保存对应物理页、传入权限及 `PTE_V`；虚拟页和物理页均按 `PGSIZE` 递增。禁止覆盖已有有效映射。本函数不取得数据页分配所有权，也不自行刷新 TLB。失败时可能已经完成前缀映射，不能在报告中声称原参考函数会自动回滚。

## `walkaddr`

```c
uint64 walkaddr(pagetable_t pagetable, uint64 va);
```

**输入**：需要查询的用户页表与虚拟字节地址。

**输出**：地址在允许范围、页表路径存在且末级项同时具有 `PTE_V | PTE_U` 时，返回物理页基址；否则返回 0。

**约束**：查询不得分配页表或修改任何映射。返回值不包含页内偏移；已提供的 `useraddr`、`copyin/out/instr` 负责加入偏移。遵循当前接口的 V/U 检查，不增加改变调用语义的 R/W 参数。

## `uvmunmap`

```c
void uvmunmap(pagetable_t pagetable, uint64 va, uint64 npages, int do_free);
```

**输入**：页对齐的首地址、非负页数（无符号类型）、无溢出的合法范围。`do_free != 0` 时，待释放页必须来自 `kalloc`、由调用者拥有且没有其他活跃所有者；`do_free == 0` 时只解除映射。

**输出**：范围内的叶子映射被清除，按 `do_free` 决定是否调用 `kfree`；不返回值。

**约束**：首地址不对齐触发 `panic`；路径不存在或叶子项无效时允许跳过，不因稀疏地址空间失败。有效项若只有 `PTE_V` 而没有叶子权限，则触发非叶子检查。释放数据页时先从 PTE 取得物理地址，再清空页表项。其他页面不受影响；中间页表页仍留给 `freewalk`，本函数不刷新 TLB。`npages == 0` 时不移除任何页面。

## 已提供的配套代码

| 路径 | 功能 |
| --- | --- |
| `os/kalloc.c` | 物理页分配、回收 |
| `os/vm.c` 其余函数 | 内核映射、页表根创建与回收、用户复制、堆增长/收缩 |
| `os/loader.c::bin_loader` | 原始二进制应用、用户栈、trapframe、trampoline 映射 |
| `os/proc.c`、`os/trap.c`、`os/trampoline.S` | 调度、trap 处理与页表切换 |
| `os/syscall.c::sys_gettimeofday` | 先构造内核时间结构，再用 `copyout` 写入用户页表，避免原始 TODO 直接解引用用户虚拟地址 |

`sys_gettimeofday` 的配套修补用于保证已提供的时间路径可工作，不是学生新增的实现点。原始 `mmap/munmap/sys_trace` TODO 保留；本章 `freeproc` 也没有启用完整地址空间释放，不能据基础应用结束就宣称验证了整个进程资源回收。

## 静态阅读与 GDB 动态跟踪

在单独目录读取参考实现并记录准确版本：

```bash
git fetch origin
git worktree add ../ucore-ch4-reference origin/ch4-api-impl
cd ../ucore-ch4-reference
git rev-parse HEAD
nl -ba os/vm.c
python3 tools/run_lab.py --prepare-only
make clean
make user CHAPTER=4 BASE=1 TOOLPREFIX=riscv64-unknown-elf- BOOTLOADER=default
make gdbserver CHAPTER=4 BASE=1 LOG=info TOOLPREFIX=riscv64-unknown-elf- BOOTLOADER=default
```

另开终端，在参考目录运行 `mkdir -p reports`、`gdb-multiarch -nx build/kernel`（也可使用支持 RISC-V 的 GNU GDB），然后：

```gdb
set architecture riscv:rv64
set pagination off
set logging file reports/gdb.log
set logging enabled on
target remote :15234
break walk
continue
p/x pagetable
p/x va
p alloc
bt
p/x (va >> 30) & 0x1ff
p/x (va >> 21) & 0x1ff
p/x (va >> 12) & 0x1ff
```

用 `next` 逐级观察 `pte`、`*pte`、`pagetable`。结合 `list` 记录读取和写回的行号，解释父 PTE 如何编码下一层物理页。第一次路径通常来自 `kvmmake → kvmmap → mappages → walk`；用 `bt` 确认，不能假定运行一定停在某个调用者。

再禁用已有断点，在 `mappages`、`walkaddr` 分别设置断点，观察页表、虚拟地址、权限、返回值。使用 `finish` 记录当前函数的实际返回值，并解释 `walkaddr` 返回的是页基址而非最终字节地址。

### 补充动态验收：撤销映射与所有权

`BASE=1` 基础应用不会自然覆盖 `uvmunmap`。因此，不能把基础应用全部结束当作该函数已获验证。下面在参考实现或已完成学生实现上，用 GDB 临时分配独立页表和数据页进行检查，无需修改测试源码。

重新启动 QEMU，连接 GDB 后仅在 `scheduler` 入口停下，此时物理页分配器与内核页表已经初始化、尚未首次进入用户态。禁用其他断点，再按顺序执行；每次分配若得到 0 就停止，不能继续访问空指针。

```gdb
break scheduler
continue
disable breakpoints
set $pt = (pagetable_t)uvmcreate()
p/x $pt
set $frame = (unsigned long)kalloc()
p/x $frame
p mappages($pt, 0x4000, 4096, $frame, 0x16)
set $entry = (pte_t *)walk($pt, 0x4000, 0)
p/x *$entry
p walkaddr($pt, 0x4123) == $frame
p useraddr($pt, 0x4123) == $frame + 0x123
call uvmunmap($pt, 0x4000, 1, 0)
p *$entry == 0
p walkaddr($pt, 0x4000) == 0
p mappages($pt, 0x4000, 4096, $frame, 0x16)
call uvmunmap($pt, 0x4000, 1, 1)
p *$entry == 0
p walkaddr($pt, 0x4000) == 0
call uvmunmap($pt, 0x3ffffff000, 1, 0)
call freewalk($pt)
continue
```

`0x16 = PTE_R | PTE_W | PTE_U`；`0x3ffffff000` 是本仓库的 `TRAMPOLINE`。两次 `mappages` 应返回 0，所有比较表达式应返回 1。第一次 `do_free=0` 后可重新映射同一数据页；第二次 `do_free=1` 后不得再访问 `$frame`。最后只撤销共享 trampoline 的映射，不能释放其内核代码页；再释放临时页表页。可先在 `kfree` 设置断点并记录调用栈，分别观察 `do_free=0/1` 的回收差异，随后禁用该断点完成后续调用。

这组操作检验映射/撤销的局部行为；不等于对所有分配失败、非法输入和并发情况的完整证明。如 GDB 版本不支持远程目标函数调用，记录该限制，使用支持 RISC-V inferior call 的 GDB 完成此步骤，不能直接将未执行项目标成通过。

## 运行与验收

学生分支根目录执行；已存在 `user/` 时跳过 clone：

```bash
python3 tools/run_lab.py --prepare-only
make clean
make test CHAPTER=4 BASE=1 TOOLPREFIX=riscv64-unknown-elf- BOOTLOADER=default
```

未完成骨架会在建内核页表时打印 `TODO(ch4-api): mappages` 并停机。完成后应观察基本应用的 `Hello world from user mode program!`、`Test power OK!`、`Test write A/B/C OK!` 等输出，以及最终 `all apps over`。后者是现有 `finished()` 使用 panic 的正常终止标记；其他 panic、断言失败、死循环和缺少成功行均需分析。实际关键行以固定测试 commit 的程序为准。

补充验证已提供的用户时间复制路径：

```bash
make clean
make test CHAPTER=4_3 BASE=1 TOOLPREFIX=riscv64-unknown-elf- BOOTLOADER=default
```

该集合增加 `ch3b_sleep`，应出现 `Test sleep OK!`。切换测试集合前 clean，避免静态镜像残留。`make test` 只启动应用，不是自动评分器；记录测试仓库 commit 和完整输出。此轮不要求运行 `CHAPTER=4 BASE=0/2` 的 `mmap/munmap/trace` 拓展集合，也不能宣称它们已通过。

## 提交要求

提交 `os/vm.c` 的四个函数体和填写完整的 `reports/lab-report.md`，保留真实运行/GDB日志与按课程要求记录的 `.ai/` 过程材料：

```bash
git status
git diff
git add os/vm.c reports
git commit -m "finish ucore ch4 api lab"
```

报告必须说明末级 PTE 指针与有效映射的区别、地址与页内偏移的区别，以及 `do_free` 为什么不能总设为 1。

## 阶段验收

以下阶段用于安排学习进度和人工验收，沿用本章现有测例与 GDB 流程。每阶段记录“源码检查 / 构建 / 参考动态跟踪 / 自己实现运行”各自的实际结果。

仍有其他目标函数未完成时，可先完成参考跟踪、源码检查和构建；运行到其 TODO 应记录为“受未完成依赖阻塞”，不能记为整章通过，也不能临时复制参考函数、跳过调用或修改测试来完成阶段验收。最终仍须完成全部目标函数及本章原有验收。

| 阶段 | 实现范围 | 检查方式与完成依据 |
| --- | --- | --- |
| 页表路径与映射 | `walk/mappages` | 在参考实现观察已有页表与新建中间页表，检查自己的页级推进逻辑并构建。 |
| 地址与所有权 | `walkaddr/uvmunmap` | 完成四个函数后，沿用本文已有页表 GDB 操作观察页基址、页内偏移与撤销映射。 |
| 整章验收 | 四个目标函数 | 运行原有基础集合，并分别记录已有 GDB 补充检查与时间路径检查；注明各自覆盖范围。 |

## 答辩问题

可从下表抽取两个问题，结合本人提交代码和报告进行约 5—8 分钟交流。先说明预期状态变化，再定位源码或已有日志；没有实际触发的分支明确标记为推导。不要求为答辩修改禁止改动的文件或新增测试。实现与参考相同可以是合理结果，评价依据是语义解释、证据对应和对边界的理解。

| 问题 | 建议说明材料 |
| --- | --- |
| walk 返回的指针与 walkaddr 返回的地址分别表示什么？页内偏移由谁补入？ | 一次映射中的 PTE 地址、物理页基址和用户字节地址。 |
| do_free 为 0 或非零时，数据页与中间页表分别由谁回收？ | uvmunmap/freewalk 的所有权与实际 GDB 观察。 |
| 为什么查询用户地址需要检查 PTE_U？现有接口能否判断所有读写权限？ | 接口参数、V/U 检查与硬件权限边界。 |

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
