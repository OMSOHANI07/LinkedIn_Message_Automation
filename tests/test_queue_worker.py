import asyncio

import pytest

from app.bot import queue_worker


@pytest.fixture(autouse=True)
def _reset_worker():
    """Each test gets a fresh queue/worker state - the module holds globals."""
    queue_worker._queue = asyncio.Queue()
    queue_worker._worker_busy = False
    queue_worker._worker_task = None
    yield
    if queue_worker._worker_task is not None:
        queue_worker._worker_task.cancel()


@pytest.mark.asyncio
async def test_jobs_run_one_at_a_time_in_order():
    order: list[int] = []
    concurrent_count = 0
    max_concurrent = 0

    async def make_job(n: int):
        async def job():
            nonlocal concurrent_count, max_concurrent
            concurrent_count += 1
            max_concurrent = max(max_concurrent, concurrent_count)
            await asyncio.sleep(0.01)
            order.append(n)
            concurrent_count -= 1

        return job

    queue_worker.start_worker()
    for n in range(5):
        await queue_worker.enqueue(await make_job(n))

    for _ in range(50):
        if len(order) == 5:
            break
        await asyncio.sleep(0.01)

    assert order == [0, 1, 2, 3, 4]
    assert max_concurrent == 1  # never more than one job in flight at once


@pytest.mark.asyncio
async def test_queue_position_reflects_pending_and_in_flight():
    assert queue_worker.queue_position() == 1  # nothing queued yet

    release = asyncio.Event()

    async def blocking_job():
        await release.wait()

    queue_worker.start_worker()
    await queue_worker.enqueue(blocking_job)
    await asyncio.sleep(0.02)  # let the worker pick it up

    assert queue_worker.queue_position() == 2  # one in flight + this new one

    async def noop():
        return None

    await queue_worker.enqueue(noop)
    assert queue_worker.queue_position() == 3  # one in flight + one queued + this new one

    release.set()
    for _ in range(50):
        if not queue_worker._worker_busy and queue_worker._queue.empty():
            break
        await asyncio.sleep(0.01)


@pytest.mark.asyncio
async def test_a_failing_job_does_not_stop_the_worker():
    results: list[str] = []

    async def failing_job():
        raise RuntimeError("boom")

    async def ok_job():
        results.append("ok")

    queue_worker.start_worker()
    await queue_worker.enqueue(failing_job)
    await queue_worker.enqueue(ok_job)

    for _ in range(50):
        if results:
            break
        await asyncio.sleep(0.01)

    assert results == ["ok"]
