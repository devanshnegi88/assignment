from __future__ import annotations

import argparse
import re
from dataclasses import dataclass
from pathlib import Path
from typing import List

import app.services.pipeline as pipeline
from app.catalog.loader import get_catalog
from app.schemas.chat import ChatMessage
from app.services.conversation import classify_turn

ROOT = Path(__file__).resolve().parent.parent
TRACE_GLOB = "C*.md"
REPORT_PATH = Path(__file__).resolve().parent / "trace_evaluation_report.md"


@dataclass
class ExpectedRecommendation:
    name: str
    url: str
    test_type: str


@dataclass
class ExpectedTurn:
    user: str
    assistant: str
    expected_recommendations: List[ExpectedRecommendation]
    expected_end: bool
    expected_action: str


@dataclass
class ActualTurn:
    action: str
    reply: str
    recommendations: List[ExpectedRecommendation]
    end_of_conversation: bool


@dataclass
class TraceResult:
    trace_name: str
    turn_results: List[tuple[ExpectedTurn, ActualTurn, dict]]
    summary: dict


def parse_recommendation_table(text: str) -> List[ExpectedRecommendation]:
    lines = [line.strip() for line in text.splitlines()]
    rows = []
    header_idx = None
    for idx, line in enumerate(lines):
        if re.match(r"\|\s*#\s*\|\s*Name\s*\|", line):
            header_idx = idx
            break
    if header_idx is None:
        return []
    for row in lines[header_idx + 2:]:
        if not row.startswith("|") or row.count("|") < 6:
            break
        cols = [col.strip() for col in row.split("|")[1:-1]]
        if len(cols) < 6:
            continue
        name = cols[1]
        test_type = cols[2]
        url = cols[-1]
        if url.startswith("<") and url.endswith(">"):
            url = url[1:-1]
        rows.append(ExpectedRecommendation(name=name, url=url, test_type=test_type))
    return rows


def parse_expected_action(assistant_text: str, expected_recs: List[ExpectedRecommendation], expected_end: bool) -> str:
    lower = assistant_text.lower()
    if expected_end:
        return "complete"
    if expected_recs:
        return "recommend"
    if "i can't" in lower and "advise" in lower:
        return "refuse_off_topic"
    if "difference" in lower or "compare" in lower:
        return "compare"
    if "?" in assistant_text:
        return "clarify"
    return "recommend"


def parse_trace_file(path: Path) -> List[ExpectedTurn]:
    text = path.read_text(encoding="utf-8")
    segments = re.split(r"### Turn \d+", text)[1:]
    turns: List[ExpectedTurn] = []
    for segment in segments:
        user_match = re.search(r"\*\*User\*\*\n\n> (.*?)\n\n\*\*Agent\*\*", segment, re.S)
        assistant_match = re.search(r"\*\*Agent\*\*\n\n(.*?)(?:\n\n_|\Z)", segment, re.S)
        user = user_match.group(1).strip() if user_match else ""
        assistant = assistant_match.group(1).strip() if assistant_match else ""
        expected_end = bool(re.search(r"end_of_conversation.*\*\*true\*\*", segment, re.IGNORECASE))
        expected_recs = parse_recommendation_table(assistant)
        expected_action = parse_expected_action(assistant, expected_recs, expected_end)
        turns.append(ExpectedTurn(user=user, assistant=assistant, expected_recommendations=expected_recs, expected_end=expected_end, expected_action=expected_action))
    return turns


def actual_recommendations_to_expected(items: list) -> List[ExpectedRecommendation]:
    return [ExpectedRecommendation(name=item.name, url=item.url, test_type=item.test_type) for item in items]


def compare_reply(expected_action: str, actual_reply: str) -> bool:
    normalized = actual_reply.lower()
    if expected_action == "clarify":
        return "happy to help" in normalized or "could you tell me more" in normalized
    if expected_action == "recommend":
        return "got it" in normalized or "i couldn't find" in normalized
    if expected_action == "compare":
        return "is categorized as" in normalized or "couldn't find both" in normalized
    if expected_action == "refuse_off_topic":
        return "i can only help" in normalized or "can't advise" in normalized
    return True


def compare_recommendations(expected: List[ExpectedRecommendation], actual: List[ExpectedRecommendation]) -> bool:
    if len(expected) != len(actual):
        return False
    expected_pairs = {(rec.name.lower(), rec.url.lower()) for rec in expected}
    actual_pairs = {(rec.name.lower(), rec.url.lower()) for rec in actual}
    return expected_pairs == actual_pairs


def build_report(result: TraceResult) -> str:
    lines: List[str] = []
    total_turns = len(result.turn_results)
    passed_turns = sum(1 for _, _, metadata in result.turn_results if metadata["turn_pass"])
    lines.append(f"## Trace {result.trace_name}")
    lines.append(f"- Turn pass rate: {passed_turns}/{total_turns}")
    lines.append(f"- Conversation pass: {'PASS' if result.summary['trace_pass'] else 'FAIL'}")
    lines.append("")
    lines.append("| Turn | Expected action | Actual action | Reply | Recommendations | Count | Grounding | End | Flow |")
    lines.append("|---|---|---|---|---|---|---|---|")
    for index, (expected, actual, metadata) in enumerate(result.turn_results, start=1):
        lines.append(
            "| {} | {} | {} | {} | {} | {} | {} | {} | {} |".format(
                index,
                expected.expected_action,
                actual.action,
                "PASS" if metadata["reply_pass"] else "FAIL",
                "PASS" if metadata["recommendations_pass"] else "FAIL",
                "PASS" if metadata["count_pass"] else "FAIL",
                "PASS" if metadata["grounding_pass"] else "FAIL",
                "PASS" if metadata["end_pass"] else "FAIL",
                "PASS" if metadata["flow_pass"] else "FAIL",
            )
        )
    lines.append("")
    lines.append("### Notes")
    for i, (expected, actual, metadata) in enumerate(result.turn_results, start=1):
        if not metadata["turn_pass"]:
            lines.append(f"- Turn {i} mismatches:")
            if not metadata["reply_pass"]:
                lines.append(f"  - reply_pass: expected_action={expected.expected_action} actual_reply={actual.reply!r}")
            if not metadata["recommendations_pass"]:
                lines.append(
                    f"  - recommendations_pass: expected={[(rec.name, rec.url) for rec in expected.expected_recommendations]} actual={[(rec.name, rec.url) for rec in actual.recommendations]}"
                )
            if not metadata["count_pass"]:
                lines.append(
                    f"  - count_pass: expected={len(expected.expected_recommendations)} actual={len(actual.recommendations)}"
                )
            if not metadata["grounding_pass"]:
                lines.append("  - grounding_pass: one or more actual recommendations were not found in the catalog")
            if not metadata["end_pass"]:
                lines.append(f"  - end_pass: expected={expected.expected_end} actual={actual.end_of_conversation}")
            if not metadata["flow_pass"]:
                lines.append(f"  - flow_pass: expected={expected.expected_action} actual={actual.action}")
    lines.append("")
    return "\n".join(lines)


def evaluate_trace(trace_name: str) -> TraceResult:
    trace_path = ROOT / f"{trace_name}.md"
    if not trace_path.exists():
        raise FileNotFoundError(f"Trace file not found: {trace_path}")
    turns = parse_trace_file(trace_path)
    history: List[ChatMessage] = []
    catalog = get_catalog()
    catalog_pairs = {(item.name.lower(), item.url.lower()) for item in catalog}
    turn_results = []
    for expected in turns:
        history.append(ChatMessage(role="user", content=expected.user))
        response = pipeline.run_turn(history)
        decision = classify_turn(history)
        actual_recs = actual_recommendations_to_expected(response.recommendations)
        actual_action = decision.action.value
        reply_pass = compare_reply(expected.expected_action, response.reply)
        recommendations_pass = compare_recommendations(expected.expected_recommendations, actual_recs)
        count_pass = len(expected.expected_recommendations) == len(actual_recs)
        grounding_pass = all((rec.name.lower(), rec.url.lower()) in catalog_pairs for rec in actual_recs)
        end_pass = response.end_of_conversation == expected.expected_end
        flow_pass = actual_action == expected.expected_action
        turn_pass = all([reply_pass, recommendations_pass, count_pass, grounding_pass, end_pass, flow_pass])
        metadata = {
            "reply_pass": reply_pass,
            "recommendations_pass": recommendations_pass,
            "count_pass": count_pass,
            "grounding_pass": grounding_pass,
            "end_pass": end_pass,
            "flow_pass": flow_pass,
            "turn_pass": turn_pass,
        }
        actual = ActualTurn(
            action=actual_action,
            reply=response.reply,
            recommendations=actual_recs,
            end_of_conversation=response.end_of_conversation,
        )
        turn_results.append((expected, actual, metadata))
        history.append(ChatMessage(role="assistant", content=response.reply))
    trace_pass = all(meta["turn_pass"] for _, _, meta in turn_results)
    summary = {"trace_pass": trace_pass}
    return TraceResult(trace_name=trace_name, turn_results=turn_results, summary=summary)


def run_all_traces(report_path: Path | None = None) -> List[TraceResult]:
    results: List[TraceResult] = []
    for trace_path in sorted(ROOT.glob(TRACE_GLOB)):
        if not trace_path.name.startswith("C"):
            continue
        trace_name = trace_path.stem
        results.append(evaluate_trace(trace_name))
    if report_path:
        lines = ["# Trace Evaluation Report", ""]
        lines.append("| Trace | Result | Turns Passed | Total Turns |")
        lines.append("|---|---|---|---|")
        for result in results:
            passed = sum(1 for _, _, meta in result.turn_results if meta["turn_pass"])
            total = len(result.turn_results)
            lines.append(f"| {result.trace_name} | {'PASS' if result.summary['trace_pass'] else 'FAIL'} | {passed} | {total} |")
        lines.append("")
        for result in results:
            lines.append(build_report(result))
        report_path.write_text("\n".join(lines), encoding="utf-8")
    return results


def main() -> None:
    parser = argparse.ArgumentParser(description="Evaluate SHL conversation traces against the current implementation.")
    parser.add_argument("trace", nargs="?", help="Trace name (e.g. C1) to execute, or omit to run all traces.")
    parser.add_argument("--report", default=str(REPORT_PATH), help="Markdown report path.")
    parser.add_argument("--no-write-report", action="store_true", help="Do not write a markdown report.")
    args = parser.parse_args()

    report_path = Path(args.report)
    if args.trace:
        result = evaluate_trace(args.trace)
        print(f"Trace {result.trace_name}: {'PASS' if result.summary['trace_pass'] else 'FAIL'}")
        if not args.no_write_report:
            report_path.write_text(build_report(result), encoding="utf-8")
            print(f"Wrote report to {report_path}")
    else:
        results = run_all_traces(report_path if not args.no_write_report else None)
        for result in results:
            print(f"Trace {result.trace_name}: {'PASS' if result.summary['trace_pass'] else 'FAIL'}")
        if not args.no_write_report:
            print(f"Wrote report to {report_path}")


if __name__ == "__main__":
    main()
