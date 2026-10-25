import sys
from pathlib import Path

# Make nicla/main.py importable as `main`.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
