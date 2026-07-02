from pathlib import Path

from trace_eval import parse_trace_file


def test_trace_parser_loads_all_files():
    root = Path(__file__).resolve().parents[2]
    trace_files = sorted(root.glob("C*.md"))
    assert trace_files, "No trace files found for evaluation"
    for trace_file in trace_files:
        turns = parse_trace_file(trace_file)
        assert turns, f"Trace {trace_file.name} parsed no turns"
        assert all(turn.user for turn in turns), f"Trace {trace_file.name} has a turn without user text"
