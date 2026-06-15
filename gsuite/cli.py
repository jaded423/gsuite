"""`gsuite` CLI.

Subcommands:
  auth                         Run the browser OAuth flow for currently-enabled features.
  status                       Print token state, enabled features, scope gaps.
  features list                Show every known feature flag and its state.
  features enable <name>       Turn a feature on.
  features disable <name>      Turn a feature off.
  serve                        Run the stdio MCP server (same as entry point).

The server process never calls `auth`; it's a separate, user-initiated action
so the browser consent screen always happens outside the MCP lifecycle.
"""

from __future__ import annotations

import argparse
import json
import sys
from typing import Any

from . import __version__
from .auth import run_auth_flow, scope_report
from .settings import FEATURE_SCOPES, load_settings, set_feature


def _cmd_auth(_args: argparse.Namespace) -> int:
    settings = load_settings()
    required = sorted(settings.required_scopes())
    if not required:
        print("No features are enabled — nothing to authorize.", file=sys.stderr)
        return 1
    print(f"Requesting {len(required)} scope(s):", file=sys.stderr)
    for s in required:
        print(f"  - {s}", file=sys.stderr)
    run_auth_flow(required)
    report = scope_report()
    print(json.dumps(report, indent=2))
    return 0 if not report["needs_reauth"] else 2


def _cmd_status(_args: argparse.Namespace) -> int:
    print(json.dumps(scope_report(), indent=2))
    return 0


def _cmd_features_list(_args: argparse.Namespace) -> int:
    s = load_settings()
    rows: list[dict[str, Any]] = []
    for f in sorted(FEATURE_SCOPES):
        rows.append(
            {
                "feature": f,
                "enabled": s.features.get(f, False),
                "scopes": FEATURE_SCOPES[f],
            }
        )
    print(json.dumps(rows, indent=2))
    return 0


def _cmd_features_enable(args: argparse.Namespace) -> int:
    set_feature(args.name, True)
    print(f"enabled: {args.name}", file=sys.stderr)
    report = scope_report()
    if report["needs_reauth"]:
        print(
            "⚠  New scopes required. Run `gsuite auth` to authorize.",
            file=sys.stderr,
        )
    return 0


def _cmd_features_disable(args: argparse.Namespace) -> int:
    set_feature(args.name, False)
    print(f"disabled: {args.name}", file=sys.stderr)
    return 0


def _cmd_serve(_args: argparse.Namespace) -> int:
    from .server import main as server_main

    server_main()
    return 0


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="gsuite")
    p.add_argument("--version", action="version", version=__version__)
    sub = p.add_subparsers(dest="cmd", required=True)

    sp = sub.add_parser("auth", help="Run browser OAuth flow for enabled features")
    sp.set_defaults(fn=_cmd_auth)

    sp = sub.add_parser("status", help="Show token + scope state")
    sp.set_defaults(fn=_cmd_status)

    sp = sub.add_parser("features", help="Manage feature flags")
    fsub = sp.add_subparsers(dest="fcmd", required=True)
    fsp = fsub.add_parser("list")
    fsp.set_defaults(fn=_cmd_features_list)
    fsp = fsub.add_parser("enable")
    fsp.add_argument("name", choices=sorted(FEATURE_SCOPES))
    fsp.set_defaults(fn=_cmd_features_enable)
    fsp = fsub.add_parser("disable")
    fsp.add_argument("name", choices=sorted(FEATURE_SCOPES))
    fsp.set_defaults(fn=_cmd_features_disable)

    sp = sub.add_parser("serve", help="Run the stdio MCP server")
    sp.set_defaults(fn=_cmd_serve)

    return p


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    return args.fn(args)


if __name__ == "__main__":
    raise SystemExit(main())
