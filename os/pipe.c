#include "defs.h"
#include "proc.h"
#include "riscv.h"

int pipealloc(struct file *f0, struct file *f1)
{
	panic("TODO(ch7-api): pipealloc");
}

void pipeclose(struct pipe *pi, int writable)
{
	panic("TODO(ch7-api): pipeclose");
}

int pipewrite(struct pipe *pi, uint64 addr, int n)
{
	panic("TODO(ch7-api): pipewrite");
}

int piperead(struct pipe *pi, uint64 addr, int n)
{
	panic("TODO(ch7-api): piperead");
}
