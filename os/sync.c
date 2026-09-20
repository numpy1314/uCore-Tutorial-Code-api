#include "defs.h"
#include "proc.h"
#include "sync.h"

struct mutex *mutex_create(int blocking)
{
	struct proc *p = curr_proc();
	if (p->next_mutex_id >= LOCK_POOL_SIZE) {
		return NULL;
	}
	struct mutex *m = &p->mutex_pool[p->next_mutex_id];
	p->next_mutex_id++;
	m->blocking = blocking;
	m->locked = 0;
	if (blocking) {
		// blocking mutex need wait queue but spinning mutex not
		init_queue(&m->wait_queue, WAIT_QUEUE_MAX_LENGTH,
			   m->_wait_queue_data);
	}
	return m;
}

void mutex_lock(struct mutex *m)
{
	panic("TODO(ch8-api): mutex_lock");
}

void mutex_unlock(struct mutex *m)
{
	panic("TODO(ch8-api): mutex_unlock");
}

struct semaphore *semaphore_create(int count)
{
	struct proc *p = curr_proc();
	if (p->next_semaphore_id >= LOCK_POOL_SIZE) {
		return NULL;
	}
	struct semaphore *s = &p->semaphore_pool[p->next_semaphore_id];
	p->next_semaphore_id++;
	s->count = count;
	init_queue(&s->wait_queue, WAIT_QUEUE_MAX_LENGTH, s->_wait_queue_data);
	return s;
}

void semaphore_up(struct semaphore *s)
{
	panic("TODO(ch8-api): semaphore_up");
}

void semaphore_down(struct semaphore *s)
{
	panic("TODO(ch8-api): semaphore_down");
}

struct condvar *condvar_create()
{
	struct proc *p = curr_proc();
	if (p->next_condvar_id >= LOCK_POOL_SIZE) {
		return NULL;
	}
	struct condvar *c = &p->condvar_pool[p->next_condvar_id];
	p->next_condvar_id++;
	init_queue(&c->wait_queue, WAIT_QUEUE_MAX_LENGTH, c->_wait_queue_data);
	return c;
}

void cond_signal(struct condvar *cond)
{
	panic("TODO(ch8-api): cond_signal");
}

void cond_wait(struct condvar *cond, struct mutex *m)
{
	panic("TODO(ch8-api): cond_wait");
}
