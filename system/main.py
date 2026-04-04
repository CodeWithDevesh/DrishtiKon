"""
Compatibility wrapper.

New implementation lives in `src/models/face_recognition/` and `scripts/run_face.py`.
"""

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scripts.run_face import main


if __name__ == "__main__":
    main()
