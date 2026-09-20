# uCore ch1 API 实验：裸机 C 内核启动与 BSS 初始化

## 实验内容

在 `ch1-api` 分支补全 `os/main.c` 中的 `clean_bss()` 和 `main()`，理解裸机 C 程序的入口、链接符号、全局数据初始化及 SBI 输出。`ch1-api-impl` 保留完整参考实现，`ch1` 保留上游代码。

| 文件 | 待实现函数 | 职责 |
| --- | --- | --- |
| `os/main.c` | `void clean_bss()` | 清零链接脚本指定的 BSS 区间 |
| `os/main.c` | `void main()` | 按顺序初始化、输出启动信息和段地址、结束本章演示 |

入口汇编、链接脚本、控制台、日志宏和 SBI 调用均已提供。本章没有用户程序、系统调用分发、任务调度或动态内存分配。

## 实验要求

1. **限制修改范围。** 只修改 `os/main.c` 中 `clean_bss()` 和 `main()` 的函数体；保留头文件、函数签名、链接符号声明和 `threadid()`，不得修改其他任何代码文件、构建脚本或测试。实验报告可填写在 `reports/lab-report.md`，原始日志放在 `reports/`。不能以修改测试、链接地址、退出接口或直接粘贴输出满足要求。
2. **静态分析与动态跟踪。** 阅读 `ch1-api-impl`，使用 GDB 跟踪参考实现，分析这两个函数的行为如何逐项对应任务描述。提交 Markdown 报告，源码引用必须包含参考实现完整 commit、文件路径、函数名和行号，并附对应 GitHub 固定版本链接；记录实际断点、命令和观察结果。
3. **独立实现。** 在理解任务和参考实现后独立补全函数，逐个比较自己的实现与参考实现的异同，说明选择理由及其是否改变语义。可以使用 AI 辅助理解和调试，但必须理解提交代码并能够解释运行过程。
4. **问题与解决。** 描述实验中遇到的主要问题、定位证据、原因、尝试过的方案和最终验证结果；未遇到的问题不要编造，未执行的验证明确标注。

## 已提供的启动环境

QEMU 的 `virt` 机器加载 `bootloader/rustsbi-qemu.bin`。RustSBI 将控制权交给位于 `0x80200000` 的内核，`os/entry.S::_entry` 将 `sp` 设置为 `boot_stack_top`，再调用 `main()`。启动栈为 64 KiB，进入 C 函数前已经可用。

`os/kernel.ld` 将 `.bss.stack` 放在 `s_bss` **之前**，因此 `[s_bss, e_bss)` 不包含正在使用的启动栈。链接符号表示地址，不能把它们当作函数调用。各地址可能随构建变化，必须取符号本身的地址。

## 接口一：`clean_bss()`

```c
void clean_bss();
```

**输入：** 无显式参数；使用已有 `extern char s_bss[]` 和 `e_bss[]`，入口已准备好栈。

**输出：** 正常返回；半开区间 `[s_bss, e_bss)` 的每个字节变成零，范围以外的内存保持不变。

**职责与约束：**

- 使用地址边界逐字节清零，或调用本仓库已有的等价清零函数；不要硬编码段地址或长度。
- 上界不包含在内；不要误把 `e_bss` 处的一个字节也写零。
- 不要从 `boot_stack` 开始清零，不能破坏当前栈、代码或已初始化数据。
- 空区间合法，此时不写内存。本章源文件几乎没有需要放入普通 BSS 的全局对象，实际构建可能得到空区间；不能为制造现象新增全局变量或扩大清零范围。
- 本函数不输出日志、不初始化控制台、不退出 QEMU。

## 接口二：`main()`

```c
void main();
```

**输入：** 无参数；入口汇编已经设置 `sp`。这是 freestanding 内核的 C 入口，不是宿主 Linux 进程的 `int main()`。

**输出：** 完成规定输出后调用已有 `panic("ALL DONE")`，经 SBI shutdown 结束运行；不返回入口汇编继续执行。

按下列顺序执行：

1. 调用 `clean_bss()`，然后调用 `console_init()`。不能先建立依赖全局变量的状态再清空 BSS。
2. 使用已有 `printf` 输出一个空行，再输出 `hello wrold!`。这里保留本章既有的输出文本。
3. 使用以下日志宏、格式串和对应链接符号输出内存布局，保持顺序及级别：

| 顺序 | 宏 | 格式串 | 参数 |
| --- | --- | --- | --- |
| 1 | `errorf` | `stext: %p` | `s_text` |
| 2 | `warnf` | `etext: %p` | `e_text` |
| 3 | `infof` | `sroda: %p` | `s_rodata` |
| 4 | `debugf` | `eroda: %p` | `e_rodata` |
| 5 | `debugf` | `sdata: %p` | `s_data` |
| 6 | `infof` | `edata: %p` | `e_data` |
| 7 | `warnf` | `sbss : %p` | `s_bss` |
| 8 | `errorf` | `ebss : %p` | `e_bss` |

4. 调用 `panic("ALL DONE")`。本章上游用 panic 宏表示演示结束，这是本实验保留的行为；`TODO(ch1-api)` panic 表示未完成，二者不能混淆。不能替换为无限循环或宿主 `exit()`。

`LOG` 默认是 `error`，因此默认只看到上述两条 ERROR 级地址日志；使用 `LOG=debug` 构建可以看到全部八条。日志级别在编译时决定，更改 `LOG` 后先清理旧构建。不要修改日志模块强制显示。

## 参考阅读与 GDB 跟踪

建议使用独立目录查看参考分支，避免覆盖自己的实现：

```bash
git fetch origin
git worktree add --detach ../ucore-ch1-reference origin/ch1-api-impl
cd ../ucore-ch1-reference
git rev-parse HEAD
nl -ba os/main.c
make clean
make build LOG=debug
make gdbserver LOG=debug TOOLPREFIX=riscv64-unknown-elf- BOOTLOADER=default
```

另开终端，在该参考目录中启动 GDB。使用 `-nx` 避免 `.gdbinit` 重复连接：

```bash
riscv64-unknown-elf-gdb -nx build/kernel
```

```gdb
set pagination off
set logging file reports/ch1-gdb.log
set logging enabled on
target remote localhost:15234
break main
break clean_bss
continue
info registers sp pc
p/x &boot_stack
p/x &boot_stack_top
p/x &s_bss
p/x &e_bss
p/d (char *)&e_bss - (char *)&s_bss
continue
list
disassemble /m clean_bss
```

然后使用 `next` 或 `stepi` 跟踪清零与返回。记录以下观察：

| 观察点 | 要回答的问题 |
| --- | --- |
| `main` 入口的 `sp` | 是否落在启动栈范围内？进入 C 函数后的栈帧为何会让它低于栈顶？ |
| `clean_bss` 中的边界和循环条件 | 清零范围是否为半开区间？是否排除启动栈？空区间时为什么不会写内存？ |
| 清零后 `console_init` 和输出 | 调用顺序是否与任务一致？本章的 `console_init` 当前做了什么？ |
| `shutdown` 断点 | 是在全部输出后进入关闭流程，还是被未实现 TODO 提前终止？ |

如区间非空，可用 `x/16bx` 查看**区间内**最多 16 个字节，并在循环前后对比；不能在空区间声称观察到了清零。如果固件原先已将该内存置零，应说明仅观察零值不能单独证明清零循环被执行，还要结合单步指令和地址范围。编译优化可能内联函数或隐藏局部变量，可结合 `disassemble /m`、`stepi` 和 `build/kernel.asm` 跟踪，不能伪造变量值。

继续跟踪关闭路径：

```gdb
break console_init
break shutdown
continue
```

固定版本引用示例格式为 `完整commit:os/main.c:起始行-结束行 (clean_bss)`；GitHub 链接使用 `/blob/完整commit/os/main.c#L起始行-L结束行`。行号从实际参考提交获取，不引用会移动的分支名代替 commit。

## 运行与验收

工具环境需要 RISC-V 裸机 GCC/binutils（默认前缀 `riscv64-unknown-elf-`）、`qemu-system-riscv64`，动态跟踪还需对应 GDB。命令均在本章仓库根目录执行，不是 `os/` 目录；本章不需要 `user/` 测试仓库。

```bash
make clean
make run LOG=debug TOOLPREFIX=riscv64-unknown-elf- BOOTLOADER=default
```

补全后应看到 `hello wrold!`、与链接符号对应的八条段地址日志，以及最终的 `ALL DONE`，随后 QEMU 结束。具体地址不固定，也不要求每段非空。默认 `make run` 仅显示 ERROR 级别的段日志是正常的。

验收同时检查源码范围、初始化顺序及 GDB 证据。只出现 `ALL DONE` 或 QEMU 退出码为零不能证明实现正确：panic 宏和正常结束都使用同一 SBI 关闭接口，TODO 骨架也可能让 QEMU 返回零。未完成骨架可编译，但会输出 `TODO(ch1-api)` 并提前关闭，不应判为通过。

实验报告使用 [reports/lab-report.md](reports/lab-report.md)。可用下列命令查看自己的变更范围；`origin/ch1-api` 必须是课程发放的骨架版本：

```bash
git diff --stat origin/ch1-api
git diff origin/ch1-api -- os/main.c
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
