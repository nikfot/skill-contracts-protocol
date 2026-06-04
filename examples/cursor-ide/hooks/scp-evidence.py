#!/usr/bin/env python3
"""SCP postToolUse hook for Cursor IDE.

After each tool call completes, checks the tool name and result against
evidence detection rules defined in the active contract. Automatically
records satisfied evidence items to session state.

Install: symlink or copy to your project, then reference in .cursor/hooks.json.
"""

import json
import sys

from scp.adapters.cursor_hook import handle_post_tool_use


def main() -> None:
    stdin_data = json.load(sys.stdin)
    result = handle_post_tool_use(stdin_data)
    json.dump(result, sys.stdout)


if __name__ == "__main__":
    main()
