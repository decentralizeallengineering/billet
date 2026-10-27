# billet

[![tests](https://github.com/decentralizeallengineering/billet/actions/workflows/tests.yml/badge.svg)](https://github.com/decentralizeallengineering/billet/actions/workflows/tests.yml) ![license](https://img.shields.io/badge/license-Apache--2.0-blue)

Billet turnover for long-running Claude Code sessions. A degraded session hands its role to a fresh successor, the way a military billet changes hands. Python standard library only, no network, no model.

## The practice

- Roles carry a generation number (`Lead1`, then `Lead2`). The predecessor's folder becomes read-only history.
- The successor's `CLAUDE.md` holds a one-line origin quote from the person, the chain of command, and a boot list: its own `CLAUDE.md`, the order ledger, the tail of the predecessor's `STATE.md`, a distilled deep-dive of the predecessor's findings (`TURNOVER.md`), the last 40 lines of the predecessor's `FACTS.md` (the person's words, verbatim, dated), then its own `STATE.md` and `FACTS.md`.
- A session runs under a fixed session id (a UUID in the launcher env) and is resumed by that id, so prompt caching works. A roll is: stop, fresh id, start. The new session rereads its orders.

### The person's rules

- "during turnover ensure id's are used for proper context and caching"
- "ensure enough turnover so that the rules and laws get transferred, but not enough that we still grandfather in degradation"

The second rule is why `TURNOVER.md` is split. Laws, orders and evidenced facts carry over whole. Beliefs without evidence go under SUSPECT and must be re-verified before use. Habits judged as degradation go under DO-NOT-CARRY and are not copied.

## Install

    cp billet ~/.local/bin/ && chmod +x ~/.local/bin/billet

## Commands

    billet check <transcript.jsonl> [--state STATE.md] [--rules rules.json]
    billet brief <role-dir>
    billet lint <TURNOVER.md>
    billet successor <role-dir> --name Lead2 [--origin "quote"] [--chain "a > b > Lead2"] [--ledger FILE] [--seal] [--dry-run]

`check` scores a transcript and prints OK, WATCH or DUE with reasons (exit code 0, 1, 2). Each triggered rule adds its weight; WATCH starts at 1, DUE at 2. Defaults, all overridable in the JSON rules file:

- `compactions` 4 and `reread_ratio` 0.4: at least that many compactions, and that share of later reads repeating files read before the compaction.
- `cost_factor` 2.5: tokens per progress event over the last `recent_segments` (3) is at least that multiple of the role's median. Progress is a `RESULT:` line or a `git commit`. The median comes from a `median_cost_per_progress: N` line in `--state`, else from the transcript itself.
- `stall_hours` 3: no progress for that long.
- `repeat_fail` 3: the same command failed that many times.

`brief` writes a `TURNOVER.md` template with the sections LAWS, ORDERS, FACTS, SUSPECT, DO-NOT-CARRY, capped at 150 lines in total. `lint` rejects a LAWS line that is not a quote, an ORDERS line without a ledger id (`- [ID] text`), a FACTS line without a date and `| evidence: ...`, and anything over the caps.

`successor` creates the sibling folder `Lead2` with `CLAUDE.md`, `STATE.md`, `FACTS.md` and `launcher.env` (a new uuid4 in `BILLET_SESSION_ID`). `CLAUDE.md` has fixed text first and the boot list in a fixed order, with nothing time-dependent, so the prompt-cache prefix is stable. The predecessor is made read-only (`chmod -R a-w`) only with `--seal`. `--dry-run` prints everything and writes nothing. The first task it sets is: verify every SUSPECT item, then act on ORDERS.

## Example

    billet brief ~/roles/Lead1        # fill it in, then:
    billet lint ~/roles/Lead1/TURNOVER.md
    billet check ~/.claude/projects/-roles-Lead1/<session>.jsonl --state ~/roles/Lead1/STATE.md
    billet successor ~/roles/Lead1 --name Lead2 --seal

## systemd example

A role unit that starts or resumes the session by its fixed id (`%h` is the home directory):

    [Unit]
    Description=Role Lead2

    [Service]
    WorkingDirectory=%h/roles/Lead2
    EnvironmentFile=%h/roles/Lead2/launcher.env
    ExecStart=/usr/bin/env sh -c 'claude --resume "$BILLET_SESSION_ID" || claude --session-id "$BILLET_SESSION_ID"'
    Restart=on-failure

    [Install]
    WantedBy=default.target

To roll: stop the unit, run `billet successor`, start the successor's unit. The id changes only at a roll.

## Limit

The top role is never rolled automatically. Its turnover needs the person, because nobody above it can issue the orders and laws that the successor inherits.

## Tests

    python3 -m pytest -q
