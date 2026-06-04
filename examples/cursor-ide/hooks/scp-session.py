#!/usr/bin/env python3
"""SCP sessionStart hook for Cursor IDE.

Detects which SCP skill contract to activate based on the user's initial
message (slash commands or trigger keywords). Sets up the session state
file for subsequent hook invocations.

Install: symlink or copy to your project, then reference in .cursor/hooks.json.

Environment:
    SCP_SKILL_DIRS: Colon-separated list of directories to scan for SKILL.md
                    files with SCP contracts.
                    Example: ~/.cursor/skills:/path/to/project/.cursor/skills
"""

import json
import sys

from scp.adapters.cursor_hook import handle_session_start


def main() -> None:
    stdin_data = json.load(sys.stdin)
    result = handle_session_start(stdin_data)
    json.dump(result, sys.stdout)


if __name__ == "__main__":
    main()
