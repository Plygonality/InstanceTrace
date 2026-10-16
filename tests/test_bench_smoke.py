from instancetrace.bench.measure import measure_count


def test_small_bench_records_times():
    result = measure_count(32)
    assert result["live_count"] == 32
    assert result["instrument_seconds"] >= 0
    assert result["baseline_seconds"] >= 0
    assert result["query_seconds"] >= 0
