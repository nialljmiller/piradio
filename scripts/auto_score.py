#!/usr/bin/env python3
"""Folder-selectable, incremental attribute guesser shared with boot scanning."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'modules'))
from internet.attributes import main
if __name__ == '__main__':
    main()
