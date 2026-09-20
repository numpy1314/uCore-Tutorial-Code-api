#ifndef PROC_H
#define PROC_H

#include "types.h"

#define NPROC (16)
#define MAX_SYSCALL_NUM (411)

// Saved registers for kernel context switches.
struct context {
	uint64 ra;
	uint64 sp;

	// callee-saved
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

// Lifecycle states used by allocation, loading, scheduling, and termination.
enum procstate { UNUSED, USED, SLEEPING, RUNNABLE, RUNNING, ZOMBIE };

// Per-process state. A slot's array index binds together this structure and
// its statically allocated kernel stack, user stack, and trapframe storage.
struct proc {
	enum procstate state; // Process state
	int pid; // Process ID
	uint64 ustack; // Virtual address of user stack
	uint64 kstack; // Virtual address of kernel stack
	struct trapframe *trapframe; // data page for trampoline.S
	struct context context; // swtch() here to run process
	// Per-process syscall counts, indexed by syscall number.
	uint64 syscall_counts[MAX_SYSCALL_NUM];
};

// Return the process currently executing in user or kernel context.
struct proc *curr_proc();
// Terminate the current process and schedule another; does not return normally.
void exit(int);
// Initialize all process-management state before loading applications.
void proc_init();
// Run prepared processes from the boot context; never returns to main.
void scheduler() __attribute__((noreturn));
// Switch from a non-RUNNING process back to the scheduler context.
void sched();
// Make the current process runnable and schedule another process.
void yield();
// Allocate and initialize an UNUSED process slot, or return null.
struct proc *allocproc();
// Save the old context and restore the new context. Implemented in switch.S.
void swtch(struct context *, struct context *);

#endif // PROC_H
