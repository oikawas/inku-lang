"""作曲フォールバックの記録 (CLI 側) -- contract a-work-drawn-by-a-fallback-says-so.md.

T-233: the CLI is one of the two senders that POST a drawn work to
/api/history, and it stacks the key either way. Silence is not neutral here --
an absent key stores NULL, and NULL already means "this work was drawn before
the column existed".
"""

from __future__ import annotations

from inku_cli import cli


def _payload(result: dict) -> dict:
    parser = cli.build_parser()
    args = parser.parse_args(["paint", "線", "--save-history"])
    return cli._history_payload_from_result(
        args,
        {"score": {"instructions": []}, "svg": "<svg></svg>", **result},
        input_text="線",
        ddl="線を引く。",
        stage1_model="s1",
        stage2_model="s2",
        color_catalog="default",
        at=123,
    )


def test_t233_the_cli_stacks_the_reason_when_compose_fell():
    payload = _payload(
        {"compose_fallback_used": True, "compose_retry_reasons": ["stage2_hard_timeout", "later"]}
    )

    # The first reason the stage gave, which is the shape Stage 1's column uses.
    assert payload["compose_fallback"] == "stage2_hard_timeout"


def test_t233_a_fallback_with_no_reason_still_says_it_fell():
    assert _payload({"compose_fallback_used": True})["compose_fallback"] == "stage2_fallback"
    assert (
        _payload({"compose_fallback_used": True, "compose_retry_reasons": []})["compose_fallback"]
        == "stage2_fallback"
    )


def test_t233_the_cli_stacks_none_when_compose_held():
    # The payload builder drops None values, so leaving this to `.get` would
    # send nothing at all and the row would read as unrecorded. "none" is a
    # statement, and the sender is the only one who can make it here.
    assert _payload({"compose_fallback_used": False})["compose_fallback"] == "none"
    assert _payload({})["compose_fallback"] == "none"
    assert cli.COMPOSE_FALLBACK_NONE == "none"
