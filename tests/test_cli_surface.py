"""The command line itself: which argv spellings `paces` accepts, and what they exit.

``tests/test_smoke.py`` and ``tests/test_vertical_slice.py`` already drive the CLI
end to end — but both only ever pass argv that works, and both assert
``returncode == 0``, so a CLI that had stopped reporting failure at all would sail
through them. This file pins the shape of the surface instead: the naming policy in
both directions, and the exit codes.

Recorded from the ``argh`` implementation before the ``cw`` migration and replayed
after: 20 argv vectors compared byte-for-byte on stdout, stderr and exit code, plus
four vectors whose stderr carries a traceback (compared on exit code and the
exception's own line, since a traceback names line numbers that the edit moved).
No diffs. That full-body diff cannot live in CI, because CPython rewrites argparse's
own option column between versions, so what is asserted here is the grammar.

**The naming policy is the load-bearing part.** `paces` runs on argh's post-0.30
``BY_NAME_IF_KWONLY``: positional parameters stay positional, keyword-only parameters
become ``--flags``. That is *not* cw's default — ``cw.ARGH`` reproduces
``argh.dispatch_commands``, under which a parameter with a default becomes an option.
``segment(media=None, *, ...)`` is exactly that shape, so under the default
``paces segment video.mp4`` would become ``paces segment --media video.mp4``: the
form every doc, the smoke test and the vertical slice actually type would stop
parsing. So both halves are asserted — the positional is accepted AND the option
spelling is rejected.
"""

from __future__ import annotations

import os
import subprocess
import sys

import pytest

from paces.__main__ import CONVENTION
from paces.tools import _dispatch_funcs

_CLI_TIMEOUT = 120

#: Every verb the CLI exposes, spelled as the command line spells it.
COMMAND_NAMES = [f.__name__.replace("_", "-") for f in _dispatch_funcs]


def run_cli(*argv, cwd):
    """Run ``python -m paces <argv>``, which is how both existing CLI tests enter."""
    return subprocess.run(
        [sys.executable, "-m", "paces", *argv],
        cwd=str(cwd),
        capture_output=True,
        text=True,
        timeout=_CLI_TIMEOUT,
        env={**os.environ, "COLUMNS": "80"},
    )


def test_every_tool_is_reachable_and_documents_itself(tmp_path):
    """``_dispatch_funcs`` is the SSOT; every name in it is a subcommand."""
    top = run_cli("--help", cwd=tmp_path)
    assert top.returncode == 0
    for name in COMMAND_NAMES:
        assert name in top.stdout, f"{name} missing from `paces --help`"
        sub = run_cli(name, "--help", cwd=tmp_path)
        assert sub.returncode == 0, sub.stderr
        assert "usage: " in sub.stdout


def test_media_is_a_positional_not_an_option(tmp_path):
    """The naming policy, in both directions. See the module docstring."""
    help_ = run_cli("segment", "--help", cwd=tmp_path)
    assert "[media]" in help_.stdout
    assert "--media" not in help_.stdout

    # Accepted as a bare word — the form the smoke test and the docs type.
    positional = run_cli("segment", "media.mp4", cwd=tmp_path)
    assert positional.returncode == 0

    # And the option spelling does not exist. Under cw's default convention this
    # would be the *only* spelling that worked.
    optional = run_cli("segment", "--media", "media.mp4", cwd=tmp_path)
    assert optional.returncode == 2


def test_keyword_only_parameters_are_flags(tmp_path):
    """The other half of BY_NAME_IF_KWONLY: every kwonly arg is a ``--flag``."""
    help_ = run_cli("to-document", "--help", cwd=tmp_path)
    for flag in ("--doc-id", "--title", "--source", "--domain", "--lang", "--output"):
        assert flag in help_.stdout
    # ...and the one positional parameter is still a bare word in the usage line.
    usage = help_.stdout.split("\n\n", 1)[0]
    assert "segmentation" in usage
    assert "--segmentation" not in help_.stdout


def test_the_convention_is_the_one_the_cli_was_built_on():
    """A guard on the constant itself, so a refactor cannot quietly drop it."""
    import cw

    assert CONVENTION.naming is cw.BY_NAME_IF_KWONLY
    assert CONVENTION.naming is not cw.ARGH.naming


@pytest.mark.parametrize(
    "argv",
    [
        ("no-such-command",),
        ("segment", "--no-such-flag"),
        ("render",),  # a required positional, omitted
        ("segment", "extra1", "extra2"),
        ("edit", "doc"),  # `edits` and the required --by are both missing
    ],
)
def test_usage_errors_exit_two(argv, tmp_path):
    """``cw.run`` returns the code, so ``main`` must ``raise SystemExit`` on it.

    Both existing end-to-end CLI tests assert ``returncode == 0``; without this,
    a CLI that had stopped reporting failure entirely would still pass them.
    """
    assert run_cli(*argv, cwd=tmp_path).returncode == 2


def test_a_failing_command_exits_nonzero(tmp_path):
    """An unknown segmenter is a real failure, and the shell has to hear about it."""
    result = run_cli("segment", "--segmenter", "nope", cwd=tmp_path)
    assert result.returncode != 0
    assert "unknown segmenter" in result.stderr


def test_no_arguments_prints_usage_to_stdout_and_exits_zero(tmp_path):
    """argh's behaviour; plain argparse with a required subparser does NOT do this."""
    result = run_cli(cwd=tmp_path)
    assert result.returncode == 0
    assert result.stdout.startswith("usage: ")
    assert result.stderr == ""
