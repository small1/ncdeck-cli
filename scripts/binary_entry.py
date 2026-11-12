"""Launcher used when freezing ncdeck into a standalone binary.

Why: a dedicated entry point lets us force Click's program name to `ncdeck`,
so `--help` reads `Usage: ncdeck ...` even when the downloaded artifact is
named something like `ncdeck-linux-x86_64`.
"""

from ncdeck.cli import cli

if __name__ == "__main__":
    cli(prog_name="ncdeck")
