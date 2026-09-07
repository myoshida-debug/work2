#!/usr/bin/env python
import os
import sys
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parent.parent))

if __name__ == '__main__':
    os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'anonflow.settings')
    try:
        from django.core.management import execute_from_command_line
    except ImportError as exc:
        raise ImportError(
            'Could not import Django. Are you sure it is installed and available on your PYTHONPATH?'
        ) from exc
    execute_from_command_line(sys.argv)
