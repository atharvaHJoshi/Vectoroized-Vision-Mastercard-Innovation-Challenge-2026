#!/usr/bin/env python3
"""SentinelGraph test runner (no pytest required).

Usage:
    python tests/run_tests.py           # run all tests
    python tests/run_tests.py -v        # verbose
    python tests/run_tests.py test_security   # one module only
"""
from __future__ import annotations

import importlib
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))


def discover(modules):
    found = []
    for mod in modules:
        try:
            module = importlib.import_module(f"tests.{mod}")
        except ImportError:
            print(f"  (skipping {mod}: not importable)")
            continue
        for name in sorted(vars(module)):
            obj = getattr(module, name)
            if name.startswith("test_") and callable(obj):
                found.append((mod, name, obj))
    return found


def main(argv=None):
    argv = argv or sys.argv[1:]
    verbose = "-v" in argv
    args = [a for a in argv if a != "-v"]

    all_tests = [
        "test_graph", "test_agents", "test_security",
        "test_memory", "test_eval",
    ]
    if args:
        all_tests = [a for a in args if a in all_tests or a.endswith(".py")]
        # allow "test_security" or "security"
        all_tests = [a.replace("test_", "").replace(".py", "")
                     for a in all_tests]

    tests = discover(all_tests)
    passed = failed = 0
    for mod, name, fn in tests:
        try:
            fn()
            passed += 1
            if verbose:
                print(f"PASS {mod}.{name}")
        except Exception as exc:  # noqa: BLE001
            failed += 1
            print(f"FAIL {mod}.{name}: {exc}")
            if verbose:
                import traceback
                traceback.print_exc()

    print(f"\n{passed} passed, {failed} failed, {passed + failed} total")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
