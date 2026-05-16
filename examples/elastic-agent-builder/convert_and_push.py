#!/usr/bin/env python3
"""Convert an OpenSkills contract to an Elastic Agent Builder payload.

Usage:
    python convert_and_push.py                # print JSON to stdout
    python convert_and_push.py --push         # push to Kibana

Environment variables (required for --push):
    KIBANA_URL  -- e.g. https://my-kibana.elastic.cloud
    API_KEY     -- Kibana API key
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from urllib.request import Request, urlopen

from openskills import load_skill
from openskills.adapters.elastic import to_elastic_payload


def main() -> None:
    skill_path = Path(__file__).parent / "skill.md"
    contract = load_skill(skill_path)
    payload = to_elastic_payload(contract, inject_constraints=True)

    if "--push" in sys.argv:
        kibana_url = os.environ.get("KIBANA_URL")
        api_key = os.environ.get("API_KEY")
        if not kibana_url or not api_key:
            print("Set KIBANA_URL and API_KEY environment variables.", file=sys.stderr)
            sys.exit(1)

        url = f"{kibana_url.rstrip('/')}/api/agent_builder/skills"
        body = json.dumps(payload).encode()
        req = Request(
            url,
            data=body,
            headers={
                "Authorization": f"ApiKey {api_key}",
                "Content-Type": "application/json",
                "kbn-xsrf": "true",
            },
            method="POST",
        )
        with urlopen(req) as resp:
            print(f"Status: {resp.status}")
            print(resp.read().decode())
    else:
        print(json.dumps(payload, indent=2))


if __name__ == "__main__":
    main()
