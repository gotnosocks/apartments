from streeteasy_archive.cli import main


def test_concurrency_above_32_is_refused(tmp_path, capsys):
    args = ["--data", str(tmp_path), "backfill", "--neighborhood", "midtown-west"]
    assert main([*args, "--concurrency", "33"]) == 2
    assert "concurrency must be 1-32" in capsys.readouterr().err


def test_thread_pool_has_a_thread_per_worker():
    import asyncio

    from streeteasy_archive.cli import size_thread_pool

    loop = asyncio.new_event_loop()
    try:
        size_thread_pool(loop, 32)
        assert loop._default_executor._max_workers == 32
    finally:
        loop.close()
