# PYTHON_ARGCOMPLETE_OK
"""paces CLI entry point — ``python -m paces`` / ``paces`` (after install)."""

from __future__ import annotations

import argh

from paces.tools import _dispatch_funcs


def main() -> None:
    """Build the argh parser over the paces tools and dispatch."""
    from argh.assembling import NameMappingPolicy

    parser = argh.ArghParser()
    # Positional args (with or without defaults) stay positional; the
    # keyword-only args every tool uses become --flags.
    parser.add_commands(
        _dispatch_funcs, name_mapping_policy=NameMappingPolicy.BY_NAME_IF_KWONLY
    )
    try:
        import argcomplete

        argcomplete.autocomplete(parser)
    except ImportError:
        pass
    parser.dispatch()


if __name__ == "__main__":
    main()
