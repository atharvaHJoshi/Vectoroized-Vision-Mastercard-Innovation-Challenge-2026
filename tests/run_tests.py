#!/usr/bin/env python3
"""
Standalone test runner — works without pytest.

    python tests/run_tests.py                 # everything
    python tests/run_tests.py test_features   # one module
    python tests/run_tests.py -v              # full tracebacks

Discovers `test_*` functions in `test_*.py`, injects fixtures by parameter name
from conftest.FIXTURES, and reports PASS/FAIL with timing. Exits non-zero if
anything fails, so it is usable as a CI gate.
"""
from __future__ import annotations

import importlib
import inspect
import sys
import time
import traceback
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
for p in (str(ROOT), str(HERE)):
    if p not in sys.path:
        sys.path.insert(0, p)

import conftest  # noqa: E402

GREEN, RED, YELLOW, DIM, RESET = "\033[32m", "\033[31m", "\033[33m", "\033[2m", "\033[0m"
if not sys.stdout.isatty():
    GREEN = RED = YELLOW = DIM = RESET = ""


def discover(only=None):
    mods = []
    for f in sorted(HERE.glob("test_*.py")):
        name = f.stem
        if only and name not in only and name.replace("test_", "") not in only:
            continue
        try:
            mods.append(importlib.import_module(name))
        except Exception as exc:
            print(f"{RED}IMPORT FAILED{RESET} {name}: {type(exc).__name__}: {exc}")
            traceback.print_exc(limit=6)
            mods.append(None)
    return [m for m in mods if m is not None]


def call(fn):
    """Supply fixtures by parameter name."""
    sig = inspect.signature(fn)
    kwargs = {}
    for pname in sig.parameters:
        if pname not in conftest.FIXTURES:
            raise RuntimeError(
                f"{fn.__name__} requests unknown fixture '{pname}'. "
                f"Known: {sorted(conftest.FIXTURES)}")
        kwargs[pname] = conftest.FIXTURES[pname]()
    return fn(**kwargs)


def main(argv):
    verbose = "-v" in argv or "--verbose" in argv
    only = [a for a in argv if not a.startswith("-")] or None

    mods = discover(only)
    if not mods:
        print("no test modules found")
        return 1

    passed = failed = 0
    failures = []
    t_all = time.time()

    for mod in mods:
        tests = [(n, f) for n, f in vars(mod).items()
                 if n.startswith("test_") and callable(f)
                 and getattr(f, "__module__", None) == mod.__name__]
        if not tests:
            continue
        print(f"\n{DIM}{'─'*68}{RESET}\n{mod.__name__}")
        for name, fn in tests:
            t0 = time.time()
            try:
                call(fn)
            except Exception as exc:
                failed += 1
                dt = time.time() - t0
                print(f"  {RED}FAIL{RESET} {name:52s} {dt:6.2f}s")
                print(f"       {RED}{type(exc).__name__}: {exc}{RESET}")
                failures.append((mod.__name__, name, traceback.format_exc()))
                if verbose:
                    traceback.print_exc(limit=8)
            else:
                passed += 1
                dt = time.time() - t0
                mark = f"{YELLOW}slow{RESET}" if dt > 8 else ""
                print(f"  {GREEN}PASS{RESET} {name:52s} {dt:6.2f}s {mark}")

    total = time.time() - t_all
    print(f"\n{DIM}{'═'*68}{RESET}")
    colour = GREEN if failed == 0 else RED
    print(f"{colour}{passed} passed, {failed} failed{RESET} in {total:.1f}s")

    if failures and not verbose:
        print(f"\n{DIM}re-run with -v for full tracebacks{RESET}")
        for mod, name, tb in failures:
            print(f"\n{RED}{mod}.{name}{RESET}")
            print("\n".join(tb.strip().splitlines()[-6:]))

    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
