# 第六章：文件对象与 inode 读写 API 实验

## 实验内容

在已提供的文件系统、磁盘驱动、缓存、目录查询和进程管理基础上，完成打开对象管理、顺序读写、inode 块读写与截断。参考分支 `ch6-api-impl`，独立实现分支 `ch6-api`。本章共八个挖空函数，由 `TODO(ch6-api)` 标识：

| 可修改文件 | 待实现函数 |
| --- | --- |
| `os/file.c` | `filealloc`、`fileclose`、`fileopen`、`inoderead`、`inodewrite` |
| `os/fs.c` | `readi`、`writei`、`itrunc` |

## 实验要求

1. **限定修改范围。** 只能在上表两个文件中实现八个函数及确有必要的文件内辅助函数；保留接口签名、数据结构及配套函数语义。不能修改其他任何代码文件、用户测例、构建脚本或校验配置。报告、日志放在 `reports/`；范围以 `lab.json` 为准。
2. **静态分析与动态跟踪。** 阅读 `ch6-api-impl` 并用 GDB 跟踪八个函数，将源码功能与任务描述逐项对应，提交 Markdown 分析报告。源码引用必须包含完整 commit SHA、路径、函数名、行号；动态证据包含实际命令、断点位置、输入、变量变化、运行日志。
3. **独立实现。** 在 `ch6-api` 独立实现所有目标函数，说明实现思路、资源所有权和失败清理；逐函数与参考比较，解释相同或不同的原因，不能以复制参考代码替代独立完成。
4. **问题与解决思路。** 记录主要问题、复现方式、定位证据、分析和解决过程、复测结果，使用 [报告模板](reports/lab-report.md)。只有终端输出而没有源码和原因分析不满足要求。

## 已提供的结构与边界

| 对象/模块 | 语义与已提供能力 |
| --- | --- |
| `proc.files[FD_BUFFER_SIZE]` | 每进程 fd 表；`fdalloc` 将打开对象登记到空槽 |
| `struct file`、`filepool` | 系统范围打开对象；保存引用数、权限、inode 指针与当前偏移 |
| `struct inode`、`itable` | 磁盘 inode 的内存缓存；`iget/idup/iput/ivalid/iupdate` 管理引用、装入及元数据写回 |
| `create/namei/dirlookup/dirlink` | 根目录内单分量名称的创建和查询；不是完整多级路径解析 |
| `bmap/balloc/bfree` | 12 个直接块加一个单级间接块的映射、分配和回收 |
| `bread/bwrite/brelse` | 获取缓存块、写回和释放；每次取得的缓存引用都必须配对释放 |
| `either_copyin/either_copyout` | 根据地址种类执行内核或用户地址拷贝 |
| `os/syscall.c`、`os/proc.c` | 文件调用入口、fd 表、fork 共享打开对象和退出时关闭引用 |

必须区分三个量：fd 只是进程表下标；`file.ref` 是共享打开对象的引用数；`inode.ref` 是内存 inode 的引用数，都不是硬链接数。fork 后父子 fd 指向同一个 `file`，因此共享偏移；两次独立 open 同一文件产生不同 `file`，偏移互不影响。

接口沿用本章单核执行模型，不新增锁、日志事务或崩溃一致性机制。上游 `fs.c` 部分注释来自 xv6，并不能证明本分支存在 inode 锁或事务日志。硬链接、unlink、fstat 相关 TODO 原样保留，不属于本次基础挖空。

## 接口契约

### 1. `struct file *filealloc()`

**职责与输入：** 从全局 `filepool` 扫描空闲项，无参数。

**输出与副作用：** 找到 `ref == 0` 的项后置 `ref = 1` 并返回；耗尽返回空指针，不改动其他项。本函数只保留槽位，不获取 inode、不分配 fd；调用者负责完成 `type/readable/writable/ip/off` 初始化后才能使用或关闭对象。池首用时由 BSS 清零，回收项由 `fileclose` 清理。

### 2. `void fileclose(struct file *f)`

**输入：** 有效、已初始化的 `FD_STDIO` 或 `FD_INODE` 对象，且 `ref >= 1`；调用者负责从自己的 fd 表删除引用。本函数不能接收尚未初始化的 `FD_NONE` 对象。

**输出与副作用：** 引用数减一，仍大于零时立即返回，保持 inode、权限和偏移；最后一个引用关闭时，`FD_INODE` 调用一次 `iput`，`FD_STDIO` 不释放 inode。清零偏移、权限和引用数，设置 `type = FD_NONE`，使槽位可再次分配。不得在只关闭共享对象的一个 fd 时提前释放 inode；不能把 close 当 unlink 或 truncate。无效引用数或未知对象类型按参考实现 panic。

### 3. `int fileopen(char *path, uint64 omode)`

**输入：** 内核中的有效零结尾单分量名称 `path`，长度满足上游 `DIRSIZ` 限制；`omode` 使用 `os/fcntl.h` 中的位标志。用户字符串转换由调用方负责。

**输出：** 成功返回当前进程的新 fd；文件不存在且未指定创建、创建返回失败、打开对象耗尽、fd 耗尽时返回 `-1`。inode/磁盘资源分配内部仍可能 panic，不要求扩展底层错误接口。

| 标志或条件 | 本分支行为 |
| --- | --- |
| `O_CREATE` | 使用 `create`，不存在时创建，已存在的普通文件直接打开 |
| 无 `O_CREATE` | 使用 `namei`；不存在返回 `-1`，存在则 `ivalid` |
| `O_TRUNC` | 成功取得 file 与 fd 后截断普通文件 |
| 仅 `O_CREATE`，文件已存在 | 保留已有内容 |
| 权限位 | `readable = !(omode & O_WRONLY)`；`writable = (omode & O_WRONLY) || (omode & O_RDWR)` |

**副作用与边界：** 新对象设为 `FD_INODE`，拥有查询/创建返回的一次 inode 引用，`off = 0`。先完成对象初始化，再登记 fd；fd 分配失败可安全调用 `fileclose` 归还对象及 inode。file 分配失败则直接 `iput`。任何失败均不得留下半初始化的 fd 或打开对象，但不承诺撤销已创建的目录项。沿用仅支持普通文件的约定，查询得到其他类型会 panic。不改变其他打开对象的偏移，不擅自把权限标志解释为其他系统的数值。

### 4. `uint64 inoderead(struct file *f, uint64 va, uint64 len)`

**输入：** 有效 `FD_INODE` 打开对象；`va` 是当前进程的用户虚拟地址，`len` 与偏移符合下层 `uint` 范围。本基础实验调用者使用合法权限和缓冲区；上游系统调用层尚非完整的权限/无效指针验证实现。

**输出与副作用：** 先 `ivalid(f->ip)`，调用 `readi(f->ip, 1, va, f->off, len)`，返回实际结果。返回正数时才按实际字节数推进 `off`；返回零或错误保持偏移。底层 `-1` 通过 `uint64` 表示为全 1，用户层按系统调用返回值解释。不可直接将用户 `va` 当作内核字符串使用，不改变文件大小或数据。

### 5. `uint64 inodewrite(struct file *f, uint64 va, uint64 len)`

**输入：** 有效 `FD_INODE` 打开对象；`va` 为当前进程用户缓冲区。范围/权限前提同 `inoderead`。

**输出与副作用：** 校验装入 inode 后调用 `writei(f->ip, 1, va, f->off, len)`，返回底层实际结果，仅正值推进偏移。短写只能增加实际写入量，不能增加请求长度。文件扩容、块分配和写回由 `writei` 负责。共享对象的其他 fd 必须看到同一偏移变化。

### 6. `int readi(struct inode *ip, int user_dst, uint64 dst, uint off, uint n)`

**输入：** 已装入有效元数据的 inode、起始字节偏移 `off`、请求字节数 `n`；`user_dst == 1` 表示当前进程用户地址，否则为内核地址。

**输出：** 超过文件尾或 `off + n` 无符号溢出返回 `0`；跨 EOF 请求裁剪到剩余长度；EOF/零长返回 `0`。正常返回实际读取总量。`either_copyout` 失败返回 `-1`，即使此前部分数据已经复制，不把部分复制伪装成完整成功。

**副作用与边界：** 按 `BSIZE` 分片，以 `bmap` 找到块，`bread` 取得数据，复制当前块内实际区间后 `brelse`；任何失败分支也释放缓存引用。每次只推进已处理字节，支持跨块。不得把 `dst` 无条件视为用户地址，不访问 EOF 之外数据，不修改打开对象偏移（那是上层的职责）。已有 `bmap` 在缺块时会分配，正常读取前提是有效文件范围内对应块已经存在；本实验不扩展稀疏文件/损坏镜像语义。

### 7. `int writei(struct inode *ip, int user_src, uint64 src, uint off, uint n)`

**输入：** 有效 inode、字节偏移、数据长度及地址种类；`user_src == 1` 表示用户地址。允许覆盖已有内容或从 EOF 追加。

**输出：** `off > size`、加法溢出或结束位置超过 `MAXFILE * BSIZE` 时返回 `-1`，不创建空洞；正常返回实际写入总量。拷贝失败时返回此前成功写入字节数，可能为 `0`；与 `readi` 的失败返回规则不同。

**副作用与边界：** 按块边界调用 `bmap/bread/either_copyin/bwrite/brelse`；每次成功写入才推进源地址、偏移和总量。失败也要释放缓存引用。根据成功写到的结束位置扩展 `ip->size`，不因覆盖写而缩小。循环结束须 `iupdate`，即使大小未变，`bmap` 也可能新增块映射；不得遗漏这些元数据。磁盘耗尽保留底层 panic。上游不是事务式写入，拷贝失败的当前块不承诺完整回滚，不增加这样的测试保证。

### 8. `void itrunc(struct inode *ip)`

**输入：** 有效、已装入元数据的 inode，拥有的块地址符合本章磁盘格式。

**输出与副作用：** 释放所有非零直接数据块并清零指针；若间接块存在，读出其数组，释放每个非零数据块，释放缓存引用，再释放间接索引块本身并清零 inode 对应指针。设置 `size = 0` 并 `iupdate`。空文件可再次截断，不重复释放零地址。保留 inode 编号、类型、引用及目录项，不相当于删除文件，不修改各打开对象已有的 `off`；之后超出新 EOF 的读写按照各自边界规则处理。

## 源码阅读与 GDB 跟踪

记录完整参考 SHA 与目标文件行号。调试入口使用同一镜像，避免上一次运行留下的文件影响结果：

```bash
git switch ch6-api-impl
git rev-parse HEAD
nl -ba os/file.c
nl -ba os/fs.c
make user CHAPTER=6 BASE=1 TOOLPREFIX=riscv64-unknown-elf- BOOTLOADER=default
make clean
make build CHAPTER=6 BASE=1 INIT_PROC=ch6b_filetest_simple
make gdbserver CHAPTER=6 BASE=1 INIT_PROC=ch6b_filetest_simple TOOLPREFIX=riscv64-unknown-elf- BOOTLOADER=default
```

另一终端执行 `gdb-multiarch -nx build/kernel`，然后：

```gdb
set pagination off
set logging file reports/ch6-gdb.log
set logging enabled on
target remote :15234
break fileopen
continue
print path
x/s path
print/x omode
list fileopen
```

在 `fileopen` 中已经初始化 `f`、即将返回 fd 的源码行设置断点，观察 `fd`、`f->ref/type/off/readable/writable`、`f->ip->inum/size` 和 `current_proc->files[fd]`，记录 inode 引用如何从查询结果转移到 file。

继续分场景跟踪，必要时用 usershell 启动指定程序：

- `break inodewrite` 与 `break inoderead`：保存 `set $file = f`，观察 `off/va/len`，`finish` 后查看同一对象的偏移与返回值。不要对用户虚拟地址直接 `x/s` 断言它是可直接读取的内核地址。
- `break writei` 与 `break readi`：用 `list` 找到 `bread` 后的行，观察 `off % 1024`、分片长度 `m`、`bp->blockno`、`bp->data`，在跨块请求中对照两次循环。函数入口时局部 `bp/m` 尚未初始化，不能把此时的值写入结论。
- `break fileclose`：观察引用递减；共享引用尚存时确认 inode 未释放，最后一个引用关闭时跟踪 `iput`。基础简单文件测例不保证覆盖共享文件场景，额外证据应明确标记触发方式。
- `break itrunc`：在合法 `O_TRUNC` 打开的触发场景观察直接块、间接块及 `size` 的变化，再打开同名文件确认 EOF。基础简单文件测例不保证覆盖截断/间接块，不能将未命中断点写为已验证。

每个目标函数都要给出静态对应分析；未被基础程序触发的边界，可通过教师提供的补充程序或经记录的调试操作观察，但不允许修改正式用户测例让其通过。GDB 中不调用会修改磁盘、分配对象的内核函数冒充真实系统调用执行。

## 运行与验收

准备 `user` 测试目录与工具链后执行，先完成用户程序构建再生成镜像：

```bash
make user CHAPTER=6 BASE=1 TOOLPREFIX=riscv64-unknown-elf- BOOTLOADER=default
make clean
make test CHAPTER=6 BASE=1 INIT_PROC=ch6b_usertest TOOLPREFIX=riscv64-unknown-elf- BOOTLOADER=default
```

未完成学生骨架应可编译，首次执行目标函数将显示 `TODO(ch6-api)` 并停止，不能算验收通过。完成后至少执行基础套件、独立文件创建/读写/关闭测例，核对每项执行和退出码；顶层基础测例应退出 `0`。检查文件写入再读出的内容一致，不能只看总标语、镜像生成或用户终端启动。

**上游测试版本注意事项。** 测试库提交 `1733f460c596b013b1c509ad42afa428640783b0` 同时包含 `ch6b_filetest.c` 和 `ch6b_filetest_simple.c`。教师补丁将基础套件的文件读写项选择为后者，并修正其读取长度检查和字符串终止，使内容比较有明确依据；两个源文件均保留。这属于基础验收用例的选择，不是修复不存在的文件名。同版本 `ch6b_exec` 的 argv 未以空指针终止。应使用仓库统一测试准备工具提供并记录的修正版，不让学生擅改验收测例。未修正时不得宣称整套通过，可先独立运行：

```bash
make clean
make test CHAPTER=6 BASE=1 INIT_PROC=ch6b_filetest_simple TOOLPREFIX=riscv64-unknown-elf- BOOTLOADER=default
```

每次比较参考与独立实现时重新 `make clean` 建立同样的初始镜像，保留用户库原始 SHA 和测试修正信息。测试套件中即使某子程序 exec 失败也可能经过其他路径退出，必须结合“目标程序实际输出”判断，不能只依靠父测例返回。

本轮不要求上游的 `sys_fstat/sys_linkat/sys_unlinkat`、硬链接计数、`spawn/set_priority` 及往章 mmap 等拓展。`BASE=1` 通过不代表这些原始 TODO 已完成，也不证明完整文件权限检查、无效指针处理、磁盘满处理或崩溃恢复。

## 参考基线修正

本章基于上游 `ch6` 提交 `feb306c`。改造提供以下共同修复，学生无需跨文件处理：

- `allocproc` 根页分配失败恢复槽位；`fork` 继承用户栈/堆元数据。
- `sys_read/sys_write/sys_close` 使用 `fd >= FD_BUFFER_SIZE` 拒绝越界描述符；该系统调用层由教师提供，不属于学生修改范围。
- 进程退出时清除孩子的父指针，并释放已经退出的孤儿所占槽位；活着的孤儿继续执行，不重复释放僵尸的资源。
- `freeproc` 的 fd 遍历条件从永不进入的 `i > FD_BUFFER_SIZE` 改为正确范围，关闭后清空指针。
- `fileopen` 先初始化 `file` 再尝试登记 fd，使 fd 耗尽清理不再关闭 `FD_NONE` 对象并触发 panic。
- `gdbserver/debug` 构建目标补充文件系统镜像依赖，确保新检出即可按文档启动调试。

原有拓展 TODO 继续保留；报告应引用改造后参考实现的完整 SHA。数据结构、并发前提与 open 标志的行为均以本章接口契约和 C 源码为准。

## 阶段验收

以下阶段用于安排学习进度和人工验收，沿用本章现有测例与 GDB 流程。每阶段记录“源码检查 / 构建 / 参考动态跟踪 / 自己实现运行”各自的实际结果。

仍有其他目标函数未完成时，可先完成参考跟踪、源码检查和构建；运行到其 TODO 应记录为“受未完成依赖阻塞”，不能记为整章通过，也不能临时复制参考函数、跳过调用或修改测试来完成阶段验收。最终仍须完成全部目标函数及本章原有验收。

| 阶段 | 实现范围 | 检查方式与完成依据 |
| --- | --- | --- |
| 打开对象与引用 | `filealloc/fileclose/fileopen` | 在参考实现跟踪 fd、file、inode 的对应关系；检查自己的初始化和失败清理并构建。启动装载本身依赖 readi，此时不要求学生内核完成文件测例。 |
| 分层读写 | `readi/writei/inoderead/inodewrite` | 在参考实现观察实际字节数和偏移变化；检查各层职责、分片边界和缓存引用释放。尚未实现的 itrunc 保留 TODO，阶段结论限于已检查的代码与实际到达的路径。 |
| 截断回收与整章验收 | `itrunc` 及全部目标函数 | 静态核对直接块、间接数据块和索引块的回收；八个函数完成后运行已有 `ch6b_filetest_simple` 和 `ch6b_usertest`。基础测例未触发的截断或间接块路径注明未动态覆盖。 |

## 答辩问题

可从下表抽取两个问题，结合本人提交代码和报告进行约 5—8 分钟交流。先说明预期状态变化，再定位源码或已有日志；没有实际触发的分支明确标记为推导。不要求为答辩修改禁止改动的文件或新增测试。实现与参考相同可以是合理结果，评价依据是语义解释、证据对应和对边界的理解。

| 问题 | 建议说明材料 |
| --- | --- |
| 两个 fd 指向同一 file，与两次独立 open 同一 inode 有何区别？ | fd/file/inode 关系、引用数和偏移由谁保存。 |
| 为什么偏移只能增加实际读写字节数？跨块时地址和长度怎样推进？ | 一次读写的请求量、返回量、off 与分片计算。 |
| fd 分配失败或最后一次关闭时，哪些资源必须归还？itrunc 与 close 有何不同？ | fileopen/fileclose/itrunc 的资源归属与清理顺序。 |

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
