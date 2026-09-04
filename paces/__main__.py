# PYTHON_ARGCOMPLETE_OK
"""paces CLI entry point — ``python -m paces`` / ``paces`` (after install)."""

from __future__ import annotations

import dataclasses

import cw

from paces.tools import _dispatch_funcs

#: Positional args (with or without defaults) stay positional; the keyword-only args
#: every tool uses become ``--flags``.
#:
#: This is ``argh``'s post-0.30 ``BY_NAME_IF_KWONLY`` policy, which this CLI has always
#: run on and which cw spells the same way. It is **not** cw's default: ``cw.ARGH``
#: reproduces ``argh.dispatch_commands`` instead, under which a defaulted positional
#: becomes an option. ``segment(media=None, *, ...)`` is exactly that shape, so the
#: difference is the difference between ``paces segment video.mp4`` and
#: ``paces segment --media video.mp4``. The former is what the docs, the smoke test and
#: the vertical-slice test all type.
CONVENTION = dataclasses.replace(cw.ARGH, naming=cw.BY_NAME_IF_KWONLY)


def main() -> None:
    """Build the parser over the paces tools and dispatch.

    ``cw.run`` offers the parser to ``argcomplete`` before parsing, exactly where
    ``argh``'s dispatch did, so ``PYTHON_ARGCOMPLETE_OK`` above still applies with no
    hand-written completion block here. It *returns* the exit code rather than raising
    it, which is why the ``SystemExit`` is written out: without it every usage error
    would exit 0, and the end-to-end tests all assert ``returncode == 0``.
    """
    parser = cw.mk_parser(_dispatch_funcs, convention=CONVENTION)
    raise SystemExit(cw.run(parser))


if __name__ == "__main__":
    main()
