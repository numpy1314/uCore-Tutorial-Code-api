#include "proc.h"
#include "defs.h"
#include "loader.h"
#include "trap.h"

struct proc pool[NPROC];
char kstack[NPROC][PAGE_SIZE];
__attribute__((aligned(4096))) char ustack[NPROC][PAGE_SIZE];
__attribute__((aligned(4096))) char trapframe[NPROC][PAGE_SIZE];

extern char boot_stack_top[];
struct proc *current_proc;
struct proc idle;

static __attribute__((noreturn)) void todo_api(const char *function)
{
	printf("Unimplemented ch3 API: %s\n", function);
	shutdown();
	for (;;) {
		// Keep the noreturn contract if the platform shutdown call returns.
	}
}

int threadid()
{
	return curr_proc()->pid;
}

struct proc *curr_proc()
{
	return current_proc;
}

// Initialize process-management state before applications are loaded.
//
// Inputs: none. The statically allocated process table, kernel stacks, user
// stacks, trapframes, idle process, and current-process pointer are available.
// Output: every process slot is UNUSED and owns the stack/trapframe storage
// at the same array index; idle represents the boot scheduler context and is
// the current process.
// Constraints: all syscall counters start at zero and no application is made
// RUNNABLE here; run_all_app() performs application allocation and loading.
void proc_init(void)
{
	// TODO(ch3-api): initialize pool, per-slot resources, idle, and current_proc.
	todo_api("proc_init");
}

int allocpid()
{
	static int PID = 1;
	return PID++;
}

// Look in the process table for an UNUSED proc.
// If found, initialize state required to run in the kernel.
// If there are no free procs, or a memory allocation fails, return 0.
struct proc *allocproc(void)
{
	struct proc *p;
	for (p = pool; p < &pool[NPROC]; p++) {
		if (p->state == UNUSED) {
			goto found;
		}
	}
	return 0;

found:
	p->pid = allocpid();
	p->state = USED;
	memset(&p->context, 0, sizeof(p->context));
	memset(p->trapframe, 0, PAGE_SIZE);
	memset((void *)p->kstack, 0, PAGE_SIZE);
	memset(p->syscall_counts, 0, sizeof(p->syscall_counts));
	p->context.ra = (uint64)usertrapret;
	p->context.sp = p->kstack + PAGE_SIZE;
	return p;
}

// Run runnable processes from the boot scheduler context.
//
// Inputs: none. run_all_app() has prepared zero or more RUNNABLE entries in
// pool, and idle.context holds the scheduler context when a process is active.
// Output: execution switches to runnable processes; this function never
// returns to main(). A process later returns control through sched().
// Constraints: scan valid process slots in ascending order and continue after
// the slot that most recently returned. Before switching, change the selected
// process to RUNNING and make current_proc point to it. Never select UNUSED,
// USED, SLEEPING, RUNNING, or ZOMBIE entries. swtch() arguments must point to
// storage that remains valid for the complete context switch.
void scheduler(void)
{
	// TODO(ch3-api): select RUNNABLE processes and switch contexts forever.
	todo_api("scheduler");
}

// Switch to scheduler.  Must hold only p->lock
// and have changed proc->state. Saves and restores
// intena because intena is a property of this
// kernel thread, not this CPU. It should
// be proc->intena and proc->noff, but that would
// break in the few places where a lock is held but
// there's no process.
void sched(void)
{
	struct proc *p = curr_proc();
	if (p->state == RUNNING)
		panic("sched running");
	swtch(&p->context, &idle.context);
}

// Suspend the current process and give up the CPU for one scheduling round.
//
// Inputs: current_proc identifies the RUNNING process that invoked sys_yield
// or was preempted by the timer interrupt.
// Output: the process becomes RUNNABLE and execution switches to scheduler();
// this call returns only after the same process is selected again.
// Constraints: preserve the process context and its future scheduling
// eligibility. sched() requires the caller to change state before switching.
void yield(void)
{
	// TODO(ch3-api): preserve eligibility and return control to the scheduler.
	todo_api("yield");
}

// Terminate the current process and return control to the scheduler.
//
// Inputs: code is the application exit status; current_proc identifies the
// RUNNING process that is terminating.
// Output: the process is no longer runnable, finished() records one completed
// application, and another runnable process receives the CPU. Normal execution
// never returns to the exiting process.
// Constraints: mark the process unavailable before scheduling, call finished()
// exactly once, and do not restore the exiting process context.
void exit(int code)
{
	(void)code;
	// TODO(ch3-api): remove the process, record completion, and schedule next.
	todo_api("exit");
}
