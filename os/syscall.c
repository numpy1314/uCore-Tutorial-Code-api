#include "syscall.h"
#include "defs.h"
#include "loader.h"
#include "syscall_ids.h"
#include "trap.h"

uint64 sys_write(int fd, char *str, uint len)
{
	debugf("sys_write fd = %d str = %x, len = %d", fd, str, len);
	if (fd != STDOUT)
		return -1;
	for (int i = 0; i < len; ++i) {
		console_putchar(str[i]);
	}
	return len;
}

__attribute__((noreturn)) void sys_exit(int code)
{
	debugf("sysexit(%d)", code);
	run_next_app();
	printf("ALL DONE\n");
	shutdown();
	__builtin_unreachable();
}

extern char trap_page[];

void syscall()
{
	panic("TODO(ch2-api): syscall");
	shutdown();
	for (;;) {
	}
}
