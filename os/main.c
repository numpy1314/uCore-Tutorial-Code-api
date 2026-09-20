#include "console.h"
#include "defs.h"

extern char s_text[];
extern char e_text[];
extern char s_rodata[];
extern char e_rodata[];
extern char s_data[];
extern char e_data[];
extern char s_bss[];
extern char e_bss[];

int threadid()
{
	return 0;
}

void clean_bss()
{
	panic("TODO(ch1-api): clean_bss");
	for (;;) {
	}
}

void main()
{
	panic("TODO(ch1-api): main");
	for (;;) {
	}
}
