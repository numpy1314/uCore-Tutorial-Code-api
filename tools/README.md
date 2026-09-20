# 实验验证工具

学生代码范围以发布骨架的 `lab.json` 为准，正式验收固定完整 SHA。

```bash
python3 tools/check_lab.py --base <学生骨架SHA> --require-complete
python3 tools/run_lab.py --mode positive
```

- `positive`：构建并运行配套基础应用，核对每项退出状态。
- `negative`：只验证尚未填写的教师骨架能编译并明确输出本章 TODO；不是完成实验。
- `gdb`：重建并实际命中第一个目标函数断点，验证调试链路；不替代逐函数报告。
- `--prepare-only`：准备固定测试提交与教师补丁；已有不匹配修改时拒绝覆盖。
- 运行证据保存在 `artifacts/chN-模式/`，包括 result.json、构建和 QEMU/GDB 日志。

Ubuntu/Debian 需要 `gcc-riscv64-unknown-elf binutils-riscv64-unknown-elf qemu-system-misc opensbi cmake make gdb-multiarch`。用户测试为自带运行库的 freestanding 程序，教师补丁允许统一使用裸机工具链。宿主文件系统生成工具还需要本机 C 编译器。

固件默认 `--bios default` 使用发行版 OpenSBI；可用 `--bios /绝对路径/fw_dynamic.bin` 明确指定。原仓库 RustSBI 与本次 QEMU 8.2 环境不兼容，未用其运行失败判定学生函数。手动 Make 命令可加 `BOOTLOADER=default TOOLPREFIX=riscv64-unknown-elf-`。

[test-upstream metadata](tests-upstream.json) 记录固定提交、补丁哈希和上游测试错误的修正依据。修补源码是教师提供的测试输入；学生不得自行更改测试。范围检查器只验证文件边界，不能证明算法正确或独立完成。
