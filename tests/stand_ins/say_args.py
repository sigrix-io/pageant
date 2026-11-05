"""A stand-in command for tests/test_apps.py: it prints the arguments it was run with, as JSON."""

import json
import sys

print(json.dumps(sys.argv[1:]))
