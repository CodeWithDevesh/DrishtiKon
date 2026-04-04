import sys
from pathlib import Path

# Ensure project root is on sys.path so `import src...` works.
PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.app.orchestrator import Orchestrator, OrchestratorConfig


def main() -> None:
    orch = Orchestrator(OrchestratorConfig.from_env())
    orch.run()


if __name__ == "__main__":
    main()

