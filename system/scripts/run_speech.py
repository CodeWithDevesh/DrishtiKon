import os
import sys
from pathlib import Path

# Ensure project root is on sys.path so `import src...` works.
PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.speech.server import main


if __name__ == "__main__":
    # Helpful defaults for local runs
    os.environ.setdefault("SPEECH_HOST", "0.0.0.0")
    os.environ.setdefault("SPEECH_PORT", "8000")
    main()

