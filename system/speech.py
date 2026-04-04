"""
Compatibility wrapper.

New implementation lives in `src/speech/server.py`.
"""

from src.speech.server import app, main


if __name__ == "__main__":
    main()
