"""Run live mock server and test Node.js TypeScript client over real sockets."""

import subprocess
import sys
import threading
import time
from pathlib import Path

bridge_dir = Path(__file__).resolve().parent.parent
harness_dir = bridge_dir.parent / "vexel-eval-harness"
sys.path.insert(0, str(harness_dir / "tests"))
from mock_server import run_mock_server


def main():
    port = 8767
    server = run_mock_server(port)
    server_thread = threading.Thread(target=server.serve_forever, daemon=True)
    server_thread.start()
    time.sleep(0.5)

    try:
        node_script = bridge_dir / "typescript" / "scripts" / "test_live_node.js"
        res = subprocess.run(["node", str(node_script), str(port)], capture_output=True, text=True)
        print(res.stdout)
        if res.stderr:
            print("STDERR:", res.stderr)
        if res.returncode != 0:
            sys.exit(res.returncode)
    finally:
        server.shutdown()
        server.server_close()


if __name__ == "__main__":
    main()
