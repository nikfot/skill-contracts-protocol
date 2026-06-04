#!/usr/bin/env python3
"""SCP preToolUse hook for Cursor IDE.

Gates tool calls against the active SCP contract. If the tool is not in
the contract's tool_ids (including any delegation merges), it is rejected.

Install: symlink or copy to your project, then reference in .cursor/hooks.json.
"""

import json
import sys

from scp.adapters.cursor_hook import handle_pre_tool_use


def main() -> None:
    stdin_data = json.load(sys.stdin)
    result = handle_pre_tool_use(stdin_data)
    json.dump(result, sys.stdout)


if __name__ == "__main__":
    main()
