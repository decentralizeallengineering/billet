import json
import os
import re
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BILLET = os.path.join(ROOT, "billet")


def run(*args):
    r = subprocess.run([sys.executable, BILLET, *map(str, args)], capture_output=True, text=True, timeout=30, check=False)
    return r.returncode, r.stdout + r.stderr


def ts(minute):
    return f"2026-01-01T{minute // 60:02d}:{minute % 60:02d}:00Z"


def asst(minute, blocks, out=100):
    return {"type": "assistant", "timestamp": ts(minute),
            "message": {"usage": {"output_tokens": out}, "content": blocks}}


def write(path, events):
    path.write_text("\n".join(json.dumps(e) for e in events) + "\n")
    return path


def test_due_rules(tmp_path):
    ok = write(tmp_path / "ok.jsonl", [asst(0, [{"type": "text", "text": "RESULT: DONE - ann"}])])
    assert run("check", ok)[0] == 0
    ev = []
    for i in range(4):  # four compactions, each followed by a re-read of the same file
        ev.append(asst(i, [{"type": "tool_use", "id": f"r{i}", "name": "Read", "input": {"file_path": "/x/a.py"}}]))
        ev.append({"type": "system", "subtype": "compact_boundary", "timestamp": ts(i)})
        ev.append(asst(i, [{"type": "tool_use", "id": f"s{i}", "name": "Read", "input": {"file_path": "/x/a.py"}}]))
    watch = write(tmp_path / "watch.jsonl", ev)
    code, out = run("check", watch)
    assert code == 1 and out.startswith("WATCH") and "compactions" in out
    for i in range(3):  # same failing command three times, then a long silent stretch
        ev.append(asst(10 + i, [{"type": "tool_use", "id": f"b{i}", "name": "Bash", "input": {"command": "make test"}}]))
        ev.append({"type": "user", "timestamp": ts(10 + i), "message": {"content": [
            {"type": "tool_result", "tool_use_id": f"b{i}", "is_error": True, "content": "boom"}]}})
    ev.append(asst(600, [{"type": "text", "text": "still working"}]))
    code, out = run("check", write(tmp_path / "due.jsonl", ev))
    assert code == 2 and out.startswith("DUE")
    assert "failed 3 times" in out and "no RESULT line or commit" in out
    # cost rule: recent progress segments cost 3x the state-file median
    costly = [asst(i, [{"type": "text", "text": "RESULT: DONE - ann"}], out=3000) for i in range(3)]
    state = tmp_path / "STATE.md"
    state.write_text("median_cost_per_progress: 1000\n")
    assert "role median" in run("check", write(tmp_path / "c.jsonl", costly), "--state", state)[1]


GOOD = """## LAWS
- "Keep it small." (2026-01-01)
## ORDERS
- [A-1] ship the parser
## FACTS
- 2026-01-02 parser passes | evidence: pytest -q, abc1234
## SUSPECT
- the cache is always warm
## DO-NOT-CARRY
- rereading the same file
"""


def test_lint_rejects_fact_without_evidence(tmp_path):
    f = tmp_path / "TURNOVER.md"
    f.write_text(GOOD)
    assert run("lint", f) == (0, "LINT: OK\n")
    f.write_text(GOOD.replace(" | evidence: pytest -q, abc1234", ""))
    code, out = run("lint", f)
    assert code == 1 and "FACTS line has no date or evidence" in out
    f.write_text(GOOD.replace('- "Keep it small." (2026-01-01)', "- keep it small"))
    assert "LAWS line is not a quote" in run("lint", f)[1]


def test_lint_enforces_caps(tmp_path):
    f = tmp_path / "TURNOVER.md"
    f.write_text(GOOD.replace("- the cache is always warm\n", "- guess\n" * 31))
    assert "SUSPECT over cap" in run("lint", f)[1]
    f.write_text(GOOD + "<!-- pad -->\n" * 150)
    assert "over cap: " in run("lint", f)[1]
    run("brief", tmp_path)  # exists already: refused
    (tmp_path / "TURNOVER.md").unlink()
    assert run("brief", tmp_path)[0] == 0 and run("lint", tmp_path / "TURNOVER.md")[0] == 0


def test_successor_dry_run_new_id_and_boot_list(tmp_path):
    role = tmp_path / "Lead1"
    role.mkdir()
    code, out = run("successor", role, "--name", "Lead2", "--dry-run")
    assert code == 0 and not (tmp_path / "Lead2").exists()
    ids = re.findall(r"BILLET_SESSION_ID=([0-9a-f-]{36})", out)
    assert len(ids) == 1 and ids[0][14] == "4"
    assert ids != re.findall(r"BILLET_SESSION_ID=([0-9a-f-]{36})", run("successor", role, "--name", "Lead2", "--dry-run")[1])
    order = [out.index(s) for s in ("1. CLAUDE.md", "ORDERS.md", "Lead1/STATE.md", "Lead1/TURNOVER.md",
                                    "Lead1/FACTS.md (last 40", "STATE.md (own)", "FACTS.md (own)")]
    assert order == sorted(order)
    assert "verify every SUSPECT item, then act on ORDERS" in out


def test_seal_skipped_unless_requested(tmp_path):
    role = tmp_path / "Lead1"
    role.mkdir()
    (role / "FACTS.md").write_text("x\n")
    assert "would not seal" in run("successor", role, "--name", "Lead2", "--dry-run")[1]
    assert run("successor", role, "--name", "Lead2")[0] == 0
    assert (tmp_path / "Lead2" / "launcher.env").exists()
    assert os.access(role / "FACTS.md", os.W_OK) and os.access(role, os.W_OK)



def test_result_line_written_from_shell_counts_as_progress(tmp_path):
    # Sessions often append "RESULT: DONE" to STATE.md through Bash, not in chat text.
    cmd = "printf 'tick ok. RESULT: DONE - x\\n' >> STATE.md"
    events = [asst(m, [{"type": "text", "text": "working"}]) for m in range(0, 590, 10)]
    events.append(asst(595, [{"type": "tool_use", "id": "t1", "name": "Bash", "input": {"command": cmd}}]))
    _, out = run("check", write(tmp_path / "s.jsonl", events))
    assert "no RESULT line or commit" not in out
