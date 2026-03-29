from __future__ import annotations

import argparse
import json

from .main import app, service, settings
from .worker import main as worker_main


def main() -> None:
    parser = argparse.ArgumentParser(prog="python -m upload_api")
    parser.add_argument("command", nargs="?", default="serve", choices=("serve", "purge-deleted-projects", "worker"))
    args = parser.parse_args()

    if args.command == "purge-deleted-projects":
        result = service.purge_deleted_projects()
        print(json.dumps({"purged_project_ids": [str(project_id) for project_id in result.purged_project_ids]}))
        return

    if args.command == "worker":
        worker_main()
        return

    import uvicorn

    uvicorn.run(app, host=settings.api_host, port=settings.api_port, reload=True)


if __name__ == "__main__":
    main()
