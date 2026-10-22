"""Compatibility entry point for the shared, reviewed protocol client."""
import sys
from pathlib import Path
if not __package__:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from custom_components.aigosmart import protocol
if __name__ == "__main__":
    raise SystemExit(protocol.main())
sys.modules[__name__] = protocol
