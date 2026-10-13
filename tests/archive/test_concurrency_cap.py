from streeteasy_archive.cli import main


def test_concurrency_above_32_is_refused(tmp_path, capsys):
    args = ["--data", str(tmp_path), "backfill", "--neighborhood", "midtown-west"]
    assert main([*args, "--concurrency", "33"]) == 2
    assert "concurrency must be 1-32" in capsys.readouterr().err


def test_handler_has_a_thread_per_request_slot():
    from scrapy.settings import Settings

    from streeteasy_archive.oxylabs import OxylabsDownloadHandler

    handler = OxylabsDownloadHandler(Settings({"CONCURRENT_REQUESTS": 32}))
    assert handler._executor._max_workers == 32
