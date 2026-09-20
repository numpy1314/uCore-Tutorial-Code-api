# uCore ch2 API 实验：用户态系统调用与异常处理

## 实验内容

在 `ch2-api` 分支补全系统调用分发与用户态 Trap 处理。理解用户程序怎样通过 `ecall` 请求内核服务、返回值怎样写回保存的上下文，以及异常程序终止后怎样继续执行下一应用。`ch2-api-impl` 是完整参考实现，`ch2` 保留上游代码。

| 文件 | 待实现函数 | 职责 |
| --- | --- | --- |
| `os/syscall.c` | `void syscall()` | 从已保存的寄存器取参数，分发调用并写回返回值 |
| `os/trap.c` | `void usertrap(struct trapframe *trapframe)` | 区分系统调用与异常，推进返回地址或结束当前应用 |

启动流程、顺序应用加载、Trap 汇编、`usertrapret()`、`sys_write()` 和 `sys_exit()` 均已提供。本章不实现调度器、页表隔离、文件系统或新增系统调用。

## 实验要求

1. **限制修改范围。** 只能修改 `os/syscall.c::syscall()` 与 `os/trap.c::usertrap()` 的函数体。保留签名、结构体、枚举、头文件与外围函数，不得修改其他任何代码文件、Makefile、加载器、汇编、测试或系统调用号。报告写入 `reports/lab-report.md`，日志放在 `reports/`。
2. **静态分析与动态跟踪。** 阅读 `ch2-api-impl` 并用 GDB 跟踪，逐条说明参考函数与任务描述的对应关系。提交 Markdown 分析报告，源码引用包含参考实现完整 commit、文件路径、函数名、行号及 GitHub 固定版本链接；附实际断点、寄存器 / 上下文值和控制流记录。
3. **独立实现。** 独立完成两个函数，逐个比较与参考实现的异同，说明原因和等价性。可以使用 AI 辅助理解或调试，但需要能够解释自己的代码；不能用伪造输出或改测试代替实现。
4. **问题与解决。** 如实描述主要问题、定位证据、原因、解决思路及验证结果，未执行的项目和未覆盖路径明确标注。

## 已提供的运行环境

`main()` 清零 BSS 后调用 `trap_init()`、`loader_init()` 和 `run_next_app()`。`os/loader.c` 按链接时嵌入的次序，将应用复制到 `BASE_ADDRESS = 0x80400000`，复用同一应用区域、用户栈及 `trap_page`，然后调用 `usertrapret()`。本章没有完整的进程地址空间隔离。

`os/trampoline.S::uservec` 保存通用寄存器及 `sepc` 到 `struct trapframe`，恢复内核栈，再跳到 `usertrap()`。`usertrapret()` 和 `userret` 负责 CSR 准备、寄存器恢复与 `sret`；学生不需要自行切换栈或执行 `sret`。

| 保存字段 | 含义 |
| --- | --- |
| `trapframe->a7` | 系统调用号 |
| `trapframe->a0` 至 `a5` | 六个机器字参数；返回后 `a0` 保存结果 |
| `trapframe->epc` | 恢复用户程序时的 PC；发生 `ecall` 时指向该指令本身 |
| `trapframe->sp` | 用户栈指针 |

保存用户异常地址的字段名为 `epc`。`syscall()` 没有参数，通过全局 `trap_page` 获取当前上下文。

## 接口一：`syscall()`

```c
void syscall();
```

**输入：** `trap_page` 中保存的 `struct trapframe`。调用方已处理 Trap 原因，并将 `epc` 推进到 `ecall` 后的指令。

**输出：** 正常返回时把调用结果写入同一上下文的 `a0`，不改其他保存字段；`SYS_exit` 不返回当前应用。

**职责与约束：**

1. 将 `trap_page` 转为 `struct trapframe *`。用 `a7` 取得系统调用号，先保存 `a0` 至 `a5` 六个参数，再进行分发，不可在取得参数前覆盖 `a0`。
2. 保留参考实现的 TRACE 日志语义：调用前记录编号和六个参数，返回后记录返回值，不修改已有日志宏或过滤规则。
3. 按已有 `os/syscall_ids.h` 常量分发：

| 编号 / 常量 | 调用目标 | 参数和返回行为 |
| --- | --- | --- |
| `64 / SYS_write` | `sys_write` | `a0` 转为 FD、`a1` 转为 `char *`、`a2` 转为长度；返回写入字节数，FD 不是 STDOUT 时返回 `-1` |
| `93 / SYS_exit` | `sys_exit` | `a0` 转为 `int` 退出码；运行下一应用，全部结束后打印 `ALL DONE` 并关闭，不返回旧应用 |
| 其他 | 无 | 使用 `errorf` 输出 `unknown syscall %d`，返回 `-1` |

4. 对能返回的调用，将结果写回 `trapframe->a0`。参考实现先将返回值放入 `int ret`，写入 `uint64` 字段时按 C 转换规则扩展，`-1` 表示全 1 的机器字；不要将未知调用伪装成成功。

使用已有 `sys_write` 和 `sys_exit`，不在分发层重复实现字符输出或应用加载，不加入用户指针验证、页表转换或新的系统调用。有效 `write` 输入为有效可读缓冲区和相应字节数；本章不要求提供完整的恶意指针防护。保留既有类型转换，不扩展本章接口语义。

## 接口二：`usertrap()`

```c
void usertrap(struct trapframe *trapframe);
```

**输入：** 汇编保存的当前应用上下文指针，以及硬件 CSR 中的 `sstatus`、`scause`、`stval` 等 Trap 信息。正常用户 Trap 的指针指向 `trap_page`。

**输出：** 系统调用返回时交给 `usertrapret()` 恢复用户态；异常时结束当前应用并启动下一应用；全部运行结束则关闭 QEMU。不能直接以普通 C `return` 跳回用户指令。

**职责与约束：**

1. 检查 `r_sstatus() & SSTATUS_SPP`。若非零，按参考实现调用 `panic("usertrap: not from user mode")` 记录诊断。注意本章 `os/log.h` 的 `panic` 宏仅输出，既不关闭机器也不阻止后续语句执行；参考实现随后仍读取 cause。本接口的正常前置条件是来自 U 模式，本实验保留现有教学实现，不据此宣称能够安全处理 S 模式 Trap。
2. 读取 `r_scause()`。若为 `UserEnvCall`：
   - 将 `trapframe->epc` **恰好加 4**，越过 `ecall`。压缩指令支持不改变 `ecall` 的 4 字节长度。
   - 调用 `syscall()`；若调用能返回，则调用 `usertrapret(trapframe, (uint64)boot_stack_top)`。
   - 不重复写返回值，不破坏其他保存字段。`SYS_exit` 会转入其他应用，因此不会走回当前应用的恢复流程。
3. 其他原因按参考 C 实现分类诊断：

| 原因 | 诊断与行为 |
| --- | --- |
| `StoreMisaligned`、`StorePageFault`、`LoadMisaligned`、`LoadPageFault`、`InstructionMisaligned`、`InstructionPageFault` | `errorf` 记录 cause、`r_stval()` 和 `trapframe->epc`，保留 `core dumped.` 提示 |
| `IllegalInstruction` | `errorf` 记录非法指令和 `trapframe->epc`，保留 `core dumped.` 提示 |
| 其他，包括本章未单独分类的访问故障 | `errorf` 记录 `unknown trap`、`r_scause()`、`r_stval()`、`r_sepc()` |

4. 上述所有非系统调用异常在诊断后执行相同收尾：用 `infof` 记录 `switch to next app`，调用 `run_next_app()`；若它返回，说明应用已经耗尽，打印 `ALL DONE\n` 并调用 `shutdown()`。

不要给异常统一执行 `epc += 4` 后恢复旧应用；不能在第一项异常时直接关闭而跳过其他应用。本 C 版本对未知系统调用返回 `-1`，对未知 Trap 诊断后继续下一应用，实现必须遵守上述返回值与控制流约定。`core dumped.` 是既有诊断文字，本章没有生成实际 core 文件。

## 工具与测试准备

内核需要 `riscv64-unknown-elf-` GCC/binutils、QEMU RISC-V 及 GDB；原测试仓库使用 `riscv64-linux-musl-`；教师兼容补丁允许改用同一裸机 GCC（测试自带运行库，不链接 musl），并需要 CMake。命令在章节仓库**根目录**执行。

```bash
python3 tools/run_lab.py --prepare-only
cd user
git checkout 1733f460c596b013b1c509ad42afa428640783b0
cd ..
```

已存在 `user/` 时先确认没有自己的改动，不要重复克隆或覆盖。记录测试仓库 commit；下文预期对应上述版本。`user/` 是忽略目录，不提交到实验仓库。`BASE=1` 对应本测试仓库的基础集合。

## 参考阅读与 GDB 跟踪

```bash
git fetch origin
git worktree add --detach ../ucore-ch2-reference origin/ch2-api-impl
cd ../ucore-ch2-reference
git rev-parse HEAD
nl -ba os/syscall.c
nl -ba os/trap.c
```

在参考目录按上一节准备独立 `user/`，然后启动调试服务：

```bash
make clean
make user CHAPTER=2 BASE=1 TOOLPREFIX=riscv64-unknown-elf- BOOTLOADER=default
make gdbserver LOG=trace TOOLPREFIX=riscv64-unknown-elf- BOOTLOADER=default
```

另开终端，在同一参考目录执行：

```bash
riscv64-unknown-elf-gdb -nx build/kernel
```

```gdb
set pagination off
set logging file reports/ch2-gdb.log
set logging enabled on
target remote localhost:15234
break usertrap
break syscall
continue
p/x $scause
p/x $sstatus
p/x $stval
set $tf = (struct trapframe *)trap_page
p/x $tf->epc
p/d $tf->a7
p/x $tf->a0
p/x $tf->a1
p/d $tf->a2
set $old_epc = $tf->epc
continue
p/x $tf->epc
p/d $tf->epc - $old_epc
```

第二次停止若是对应的 `syscall` 断点，`epc` 差值应为 4。基础集合按文件名排序，首个 `ch2b_exit` 调用退出且不返回；继续到 hello/power 的 `SYS_write` 后再使用 `finish` 观察返回值，不能期待 `sys_exit()` 的 `finish` 回到旧应用。在 `syscall` 处先记录编号、长度和 `a0`，正常 write 返回后比较保存的 `a0` 与写入长度，并确认其余保存字段保持原值。TRACE 日志也可用于关联实际调用。

在 `usertrapret`、`run_next_app` 设置断点，观察 write 恢复原上下文、exit 切换应用两种路径。异常集合使用下一节的补充命令准备，再重启 GDB；记录 `scause/stval/epc`、诊断、下一应用启动顺序，说明异常路径没有恢复旧 `epc`。优化可能影响逐行单步和局部变量显示，可使用 `disassemble /m usertrap`、`stepi`、`build/kernel.asm` 和保存上下文解释，不编造不可见值。

每项报告引用使用 `完整commit:os/trap.c:起始行-结束行 (usertrap)` 形式，并附 `/blob/完整commit/os/trap.c#L起始行-L结束行` 的固定版本链接。阅读和运行必须对应同一个参考 commit。

## 运行与验收

### 基础集合

```bash
make clean
make user CHAPTER=2 BASE=1 TOOLPREFIX=riscv64-unknown-elf- BOOTLOADER=default
make run LOG=trace TOOLPREFIX=riscv64-unknown-elf- BOOTLOADER=default
```

使用显式章节号以避免脱离分支时无法推导章节。构建用户程序后再编译内核，避免并行启动顺序问题。测试版本 `1733f460` 中基础集合包含以下 **3** 个应用：

| 应用 | 预期结果 |
| --- | --- |
| `ch2b_exit` | 以 `1234` 退出；TRACE 构建可看到 `sysexit(1234)`，然后执行下一应用 |
| `ch2b_hello_world` | `Hello world from user mode program!` 和 `Test hello_world OK!` |
| `ch2b_power` | 实际计算并输出幂模结果，最终 `3^100000=2749` 和 `Test power OK!` |

全部应用结束后打印 `ALL DONE`，QEMU 关闭。不能只凭最后一行或进程退出码判定通过，还要检查每个应用的行为、write 返回值与应用切换。默认 `LOG=error` 看不到加载、系统调用及退出码日志，改日志级别须先清理构建。

### 异常集合

该测试版本的异常程序命名为 `__ch2_bad_*`，**不在基础集合内**。为了既按正确入口 `0x80400000` 链接又选中异常应用，先以 `CHAPTER=2` 构建，再替换仅用于本次实验的生成目录；以下删除的均是生成文件，不是测试源代码：

```bash
make clean
make user CHAPTER=2 BASE=1 TOOLPREFIX=riscv64-unknown-elf- BOOTLOADER=default
rm -rf user/target/bin user/target/elf
mkdir -p user/target/bin user/target/elf
cp user/build/bin/__ch2_bad_* user/target/bin/
cp user/build/riscv64/__ch2_bad_* user/target/elf/
make run LOG=trace TOOLPREFIX=riscv64-unknown-elf- BOOTLOADER=default
```

预期依次运行 bad address、bad instruction 和 bad register；非法内存访问输出故障诊断，用户态执行特权指令或访问特权 CSR 输出 `IllegalInstruction`，每次诊断后尝试下一应用，最后输出 `ALL DONE` 并关闭。`StoreAccessFault` 若出现会落入参考实现的 `unknown trap` 分支，同样必须结束该应用并继续，不能强行要求所有内存错误显示 PageFault。

不要直接使用该版本的 `CHAPTER=2_bad` 构建异常程序：其 Makefile 能选中文件，但 CMake 的固定入口条件只匹配 `CHAPTER=2`。上述流程复用已有源码和正确章节链接地址，不需要修改测试。

基础和异常集合都没有覆盖未知系统调用的全部边界或错误 SPP 来源；需用源码分析明确这些路径的契约，不能把已有测试全部完成解释为覆盖所有情况。未实现骨架可编译并启动，但首次进入 `usertrap()` 时会输出 `TODO(ch2-api)`，随后占位函数显式调用 `shutdown()` 关闭机器，这不是通过。占位代码不能仅依靠本章的 `panic` 宏终止；它保留的无限循环只用于防止关闭接口意外返回。

完成 [reports/lab-report.md](reports/lab-report.md)，同时核对修改范围：

```bash
git diff --stat origin/ch2-api
git diff origin/ch2-api -- os/syscall.c os/trap.c
```

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
