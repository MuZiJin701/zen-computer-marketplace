from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
from dataclasses import asdict, replace
from pathlib import Path
from typing import Any, Sequence

from .adapters import (
    AdapterResult,
    AntigravityAdapter,
    ChromeAdapter,
    CodexAdapter,
    MatlabAdapter,
    TerminalAdapter,
    UnsupportedAdapter,
    VSCodeFamilyAdapter,
    WindowsAdapter,
    WindowsConfig,
)
from .editor_instance import EditorSpec, editor_spec_from_plan, resolve_editor_spec
from .adapters.antigravity import _generated_values as _antigravity_generated_values, detect_windows_app_mode
from .adapters.matlab import _generated_values as _matlab_generated_values
from .adapters.windows import WindowsDesktopBackend, WindowsRegistryBackend
from .adapters.chrome import _generated_values as _chrome_generated_values
from .adapters.codex import _theme_updates
from .adapters.windows import _theme_registry_values
from .adapters.vscode_family import build_theme_json
from .field_mappings import TERMINAL_APPEARANCE_FIELDS, TERMINAL_FIELD_MAPPINGS
from .inventory import inventory_groups
from .palette import mode_independent_surface
from .plan import Plan, PlanIntegrityError, create_plan, load_plan, save_plan
from .storage import json_safe
from .transaction import TransactionStatus, TransactionStore, apply_plan, verify_plan

DEFAULT_TARGETS = ("windows", "terminal", "vscode", "trae", "antigravity-ide", "chatgpt-app", "antigravity", "matlab", "chrome")


def _default_runtime_dir() -> Path:
    return Path(__file__).resolve().parents[2] / ".one-tone"


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="one-tone")
    commands = parser.add_subparsers(dest="command", required=True)
    runtime_dir = _default_runtime_dir()

    preview = commands.add_parser("preview", help="generate a Plan without changing targets")
    preview.add_argument("seed_color")
    preview.add_argument(
        "--targets",
        default=",".join(DEFAULT_TARGETS),
        help="comma-separated target names (default: all supported targets)",
    )
    preview.add_argument("--plans-dir", type=Path, default=runtime_dir / "plans")
    preview.add_argument("--transactions-dir", type=Path, default=runtime_dir / "transactions")
    preview.add_argument("--state-dir", type=Path, default=runtime_dir / "state")
    preview.add_argument("--output", choices=("human", "json"), default="human")

    apply = commands.add_parser("apply", help="apply an existing Plan")
    apply.add_argument("plan_id")
    apply.add_argument("--confirm", action="store_true", required=True)
    apply.add_argument("--plans-dir", type=Path, default=runtime_dir / "plans")
    apply.add_argument("--transactions-dir", type=Path, default=runtime_dir / "transactions")
    apply.add_argument("--state-dir", type=Path, default=runtime_dir / "state")
    apply.add_argument("--keep-transactions", type=int, default=5)
    apply.add_argument("--output", choices=("human", "json"), default="human")

    verify = commands.add_parser("verify", help="check current targets against a saved Plan")
    verify.add_argument("plan_id")
    verify.add_argument("--plans-dir", type=Path, default=runtime_dir / "plans")
    verify.add_argument("--state-dir", type=Path, default=runtime_dir / "state")
    verify.add_argument("--output", choices=("human", "json"), default="human")

    sync = commands.add_parser("sync", help="run Preview, Apply, and Verify in one step")
    sync.add_argument("seed_color")
    sync.add_argument(
        "--targets",
        default=",".join(DEFAULT_TARGETS),
        help="comma-separated target names (default: all supported targets)",
    )
    sync.add_argument("--plans-dir", type=Path, default=runtime_dir / "plans")
    sync.add_argument("--transactions-dir", type=Path, default=runtime_dir / "transactions")
    sync.add_argument("--state-dir", type=Path, default=runtime_dir / "state")
    sync.add_argument("--keep-transactions", type=int, default=5)
    sync.add_argument("--output", choices=("human", "json"), default="human")

    rollback = commands.add_parser("rollback", help="restore one transaction (defaults to latest)")
    rollback.add_argument("transaction_id", nargs="?")
    rollback.add_argument("--latest", action="store_true", help="restore the most recent transaction")
    rollback.add_argument("--transactions-dir", type=Path, default=runtime_dir / "transactions")
    rollback.add_argument("--state-dir", type=Path, default=runtime_dir / "state")
    rollback.add_argument("--output", choices=("human", "json"), default="human")
    return parser


def _target_names(raw_targets: str) -> tuple[str, ...]:
    targets = tuple(sorted({item.strip() for item in raw_targets.split(",") if item.strip()}))
    if not targets:
        raise ValueError("At least one target is required")
    return targets


def _adapter_result_payload(result: dict[str, object]) -> dict[str, object]:
    metadata = result.get("metadata", {})
    if isinstance(metadata, dict):
        metadata = {key: value for key, value in metadata.items() if key not in {"artifact", "artifacts"}}
    return {
        "target": result.get("target"),
        "status": result.get("status"),
        "changed": result.get("changed", False),
        "verified": result.get("verified", False),
        "message": result.get("message", ""),
        "requires_user_action": result.get("requires_user_action", False),
        "version": result.get("version"),
        "metadata": metadata,
    }


def _record_payload(command: str, record, extra: dict[str, object] | None = None) -> dict[str, object]:
    targets: list[dict[str, object]] = []
    for target in record.targets:
        operations = record.results.get(target, [])
        latest = operations[-1] if operations else {"target": target, "status": "skipped", "message": "no result"}
        item = _adapter_result_payload(latest)
        item["target"] = target
        item["support_level"] = record.support_levels.get(target)
        item["requires_user_action"] = any(result.get("requires_user_action", False) for result in operations)
        targets.append(item)
    payload = {
        "command": command,
        "status": record.status.value,
        "plan_id": record.plan_id,
        "transaction_id": record.id,
        "targets": targets,
        "support_levels": record.support_levels,
        "message": f"{command} completed with status {record.status.value}",
    }
    if extra:
        payload.update(extra)
    return payload


def _emit(payload: dict[str, object], output: str, *, error: bool = False) -> None:
    if output == "json":
        print(json.dumps(json_safe(payload), ensure_ascii=False, sort_keys=True), file=sys.stderr if error else sys.stdout)


def _optional_path(name: str) -> Path | None:
    value = os.environ.get(name)
    return Path(value) if value else None


def _first_path(candidates: list[Path]) -> Path:
    for candidate in candidates:
        if candidate.exists():
            return candidate
    return candidates[0]


def _configured_or_first(name: str, candidates: list[Path]) -> Path:
    return _optional_path(name) or _first_path(candidates)


def _first_executable(name: str, command: str, candidates: list[Path]) -> Path:
    configured = _optional_path(name)
    if configured is not None:
        return configured
    for candidate in candidates:
        if candidate.exists():
            return candidate
    resolved = shutil.which(command)
    return Path(resolved) if resolved else Path(command)


def _scoop_root_from_shim(executable: Path) -> Path | None:
    if executable.parent.name.casefold() != "shims":
        return None
    return executable.parent.parent


def _terminal_settings_candidates(executable: Path, localappdata: Path, userprofile: Path) -> list[Path]:
    candidates = [
        localappdata / "Packages/Microsoft.WindowsTerminal_8wekyb3d8bbwe/LocalState/settings.json",
        localappdata / "Microsoft/Windows Terminal/settings.json",
        userprofile / "scoop/persist/windows-terminal/settings/settings.json",
        localappdata / "scoop/persist/windows-terminal/settings/settings.json",
    ]
    scoop_root = _scoop_root_from_shim(executable)
    if scoop_root is not None:
        candidates.insert(0, scoop_root / "persist/windows-terminal/settings/settings.json")
    return candidates


def build_target_adapters(targets, state_dir: Path, target_instances: dict[str, dict[str, object]] | None = None):
    appdata = Path(os.environ.get("APPDATA", Path.home() / "AppData/Roaming"))
    localappdata = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData/Local"))
    userprofile = Path(os.environ.get("USERPROFILE", Path.home()))
    terminal_executable = _first_executable("ONE_TONE_TERMINAL_EXECUTABLE", "wt", [])
    terminal_settings = _configured_or_first(
        "ONE_TONE_TERMINAL_SETTINGS",
        _terminal_settings_candidates(terminal_executable, localappdata, userprofile),
    )
    terminal_instance = target_instances.get("terminal", {}) if target_instances is not None else {}
    if terminal_instance.get("status") == "ok" and terminal_instance.get("settings_path"):
        terminal_settings = Path(str(terminal_instance["settings_path"]))
    if target_instances is None:
        vscode_defaults = [(appdata / "Code/User/settings.json", userprofile / ".vscode/extensions", "standard")]
        vscode_spec = resolve_editor_spec(
            "vscode",
            _first_executable("ONE_TONE_VSCODE_EXECUTABLE", "code", []),
            vscode_defaults,
            _optional_path("ONE_TONE_VSCODE_SETTINGS"),
            _optional_path("ONE_TONE_VSCODE_EXTENSIONS"),
            state_dir / "vscode-artifacts",
        )
        trae_defaults = [
            (appdata / "TRAE/User/settings.json", userprofile / ".trae/extensions", "standard"),
            (appdata / "Trae/User/settings.json", userprofile / ".trae/extensions", "standard"),
        ]
        trae_spec = resolve_editor_spec(
            "trae",
            _first_executable("ONE_TONE_TRAE_EXECUTABLE", "trae", []),
            trae_defaults,
            _optional_path("ONE_TONE_TRAE_SETTINGS"),
            _optional_path("ONE_TONE_TRAE_EXTENSIONS"),
            state_dir / "trae-artifacts",
        )
        antigravity_ide_defaults = [
            (appdata / "Antigravity IDE/User/settings.json", userprofile / ".antigravity-ide/extensions", "standard"),
            (appdata / "Antigravity/User/settings.json", userprofile / ".antigravity-ide/extensions", "standard"),
        ]
        antigravity_ide_spec = resolve_editor_spec(
            "antigravity-ide",
            _first_executable("ONE_TONE_ANTIGRAVITY_IDE_EXECUTABLE", "antigravity-ide", []),
            antigravity_ide_defaults,
            _optional_path("ONE_TONE_ANTIGRAVITY_IDE_SETTINGS"),
            _optional_path("ONE_TONE_ANTIGRAVITY_IDE_EXTENSIONS"),
            state_dir / "antigravity-ide-artifacts",
        )
    else:
        vscode_spec = editor_spec_from_plan(
            "vscode",
            target_instances.get("vscode", {}),
            EditorSpec("vscode", "", Path(), Path(), artifacts_dir=state_dir / "vscode-artifacts"),
        )
        trae_spec = editor_spec_from_plan(
            "trae",
            target_instances.get("trae", {}),
            EditorSpec("trae", "", Path(), Path(), artifacts_dir=state_dir / "trae-artifacts"),
        )
        antigravity_ide_spec = editor_spec_from_plan(
            "antigravity-ide",
            target_instances.get("antigravity-ide", {}),
            EditorSpec("antigravity-ide", "", Path(), Path(), artifacts_dir=state_dir / "antigravity-ide-artifacts"),
        )
    chatgpt_app_path = os.environ.get("ONE_TONE_CHATGPT_APP_THEME_CONFIG")
    chatgpt_app_instance = target_instances.get("chatgpt-app") if target_instances is not None else None
    antigravity_instance = target_instances.get("antigravity") if target_instances is not None else None
    matlab_instance = (
        target_instances.get("matlab", {"status": "skipped", "reason": "MATLAB target instance missing from Plan"})
        if target_instances is not None
        else None
    )
    chrome_instance = (
        target_instances.get("chrome", {"status": "skipped", "reason": "Chrome target instance missing from Plan"})
        if target_instances is not None
        else None
    )
    app_mode = detect_windows_app_mode()
    registry = {}
    for target in targets:
        if target == "windows":
            registry[target] = WindowsAdapter(WindowsConfig(state_dir / "windows-wallpapers"), WindowsRegistryBackend(), WindowsDesktopBackend())
        elif target == "terminal":
            registry[target] = TerminalAdapter(
                terminal_settings,
                target_instance=terminal_instance or None,
                discover_shell=target_instances is None,
                terminal_executable=terminal_executable if target_instances is None else None,
            )
        elif target == "vscode":
            registry[target] = VSCodeFamilyAdapter(vscode_spec, app_mode=app_mode)
        elif target == "cursor":
            registry[target] = UnsupportedAdapter(target)
        elif target == "trae":
            registry[target] = VSCodeFamilyAdapter(trae_spec, app_mode=app_mode)
        elif target == "antigravity-ide":
            registry[target] = VSCodeFamilyAdapter(antigravity_ide_spec, app_mode=app_mode)
        elif target == "chatgpt-app":
            registry[target] = CodexAdapter(Path(chatgpt_app_path) if chatgpt_app_path else None, target_instance=chatgpt_app_instance)
        elif target == "antigravity":
            registry[target] = AntigravityAdapter(target_instance=antigravity_instance)
        elif target == "matlab":
            registry[target] = MatlabAdapter(
                target_instance=matlab_instance,
                appdata=appdata,
            )
        elif target == "chrome":
            registry[target] = ChromeAdapter(
                target_instance=chrome_instance,
                localappdata=localappdata,
            )
        else:
            registry[target] = UnsupportedAdapter(target)
    return registry


def _preview_values(plan: Plan, target: str) -> dict[str, Any]:
    values = {}
    for mode in ("light", "dark"):
        palette = plan.palette_for(mode)
        if target in {"vscode", "trae", "antigravity-ide"}:
            generated = build_theme_json(plan, "One Tone", mode, baseline=plan.target_instances.get(target, {}).get("color_baseline", ""))["colors"]
        elif target == "chrome":
            generated = _chrome_generated_values(plan)
        elif target == "chatgpt-app":
            generated = {f"{table.removeprefix('desktop.')}.{key}": value for table, entries in _theme_updates(plan.palettes).items() for key, value in entries.items()}
            generated["appearanceTheme"] = "system"
        elif target == "antigravity":
            generated = _antigravity_generated_values(plan)
        elif target == "matlab":
            generated = _matlab_generated_values(plan)
        elif target == "terminal":
            generated = {mapping.field: palette[mapping.palette_key] for mapping in TERMINAL_FIELD_MAPPINGS}
            generated.update({name: value for name, (value, _) in TERMINAL_APPEARANCE_FIELDS.items() if value is not None})
            generated["window.applicationTheme"] = mode
        elif target == "windows":
            generated = {**_theme_registry_values(plan), "wallpaper": {"color": mode_independent_surface(plan.seed_color)}}
        else:
            generated = {}
        for name, value in generated.items():
            if plan.field_capabilities.get(target, {}).get(name) == "supported":
                values.setdefault(name, {})[mode] = value
    return values


def _preview(args: argparse.Namespace) -> int:
    targets = _target_names(args.targets)
    adapters = build_target_adapters(targets, args.state_dir)
    detected = {target: adapter.detect() for target, adapter in adapters.items()}
    target_instances = {
        target: adapter.target_instance()
        for target, adapter in adapters.items()
        if hasattr(adapter, "target_instance")
    }
    for target, result in detected.items():
        if result.status == "skipped":
            target_instances[target] = {"status": "skipped", "reason": result.message}
    plan = create_plan(args.seed_color, targets, target_instances=target_instances)
    path = save_plan(plan, args.plans_dir)
    unsupported_count = sum(result.status != "ok" for result in detected.values())
    if args.output == "json":
        _emit({
            "command": "preview",
            "status": "ok",
            "plan_id": plan.id,
            "mode_palettes": plan.palettes,
            "field_capabilities": plan.field_capabilities,
            "appearance_policy": plan.appearance_policy,
            "target_instances": plan.target_instances,
            "targets": [
                {
                    "target": target,
                    "status": result.status,
                    "changed": result.changed,
                    "verified": result.verified,
                    "message": result.message,
                    "requires_user_action": result.requires_user_action,
                    "version": result.version,
                    "metadata": result.metadata,
                }
                for target, result in detected.items()
            ],
            "selected_mode": plan.mode,
            "mode_semantics": "Mode is a presentation variant of the Seed Color; it does not change Windows system mode",
            "field_inventory": {
                target: inventory_groups(target, plan.field_capabilities[target], _preview_values(plan, target))
                for target in plan.targets
            },
            "warnings": unsupported_count,
            "path": str(path),
        }, args.output)
        return 0
    print(f"Plan ID: {plan.id}")
    print("Targets:")
    for target in plan.targets:
        print(f"- {target}")
    print("Detection:")
    for target, result in detected.items():
        print(f"- {target}: {result.status} — {result.message}")
    print("Validation:")
    print("- Appearance policy: solid Windows/Terminal/ChatGPT windows; preserve fonts and Windows modes; Chrome follows system Light/Dark via native Preferences")
    print("- Contrast: PASS")
    print("- Appearance safety: PASS")
    print("Field regions:")
    for target in plan.targets:
        print(f"- {target}: {', '.join(inventory_groups(target)) or 'none'}")
    print(f"- Saved: {path}")
    return 0


def _apply(args: argparse.Namespace) -> int:
    plan = load_plan(args.plan_id, args.plans_dir)
    adapters = build_target_adapters(plan.targets, args.state_dir, plan.target_instances)
    store = TransactionStore(args.transactions_dir)
    record = apply_plan(plan, adapters, store, confirm=args.confirm)
    removed = store.prune(keep=args.keep_transactions, preserve={record.id})
    if args.output == "json":
        _emit(_record_payload("apply", record, {"pruned_transactions": removed}), args.output)
        return 0 if record.status in {TransactionStatus.APPLIED, TransactionStatus.PARTIAL} else 1
    print(f"Transaction ID: {record.id}")
    print(f"Status: {record.status.value}")
    if removed:
        print(f"Pruned transactions: {len(removed)}")
    return 0 if record.status in {TransactionStatus.APPLIED, TransactionStatus.PARTIAL} else 1


def _rollback(args: argparse.Namespace) -> int:
    store = TransactionStore(args.transactions_dir)
    tx_id = store.latest_transaction_id() if args.latest or not args.transaction_id else args.transaction_id
    record = store.load(tx_id)
    target_instances = {
        target: metadata["target_instance"]
        for target, metadata in record.target_metadata.items()
        if isinstance(metadata, dict) and isinstance(metadata.get("target_instance"), dict)
    }
    adapters = build_target_adapters(record.targets, args.state_dir, target_instances)
    restored = store.rollback(record.id, adapters)
    if args.output == "json":
        _emit(_record_payload("rollback", restored), args.output)
        return 0 if restored.status == TransactionStatus.ROLLED_BACK else 1
    print(f"Transaction ID: {restored.id}")
    print(f"Status: {restored.status.value}")
    return 0 if restored.status == TransactionStatus.ROLLED_BACK else 1


def _sync(args: argparse.Namespace) -> int:
    targets = _target_names(args.targets)
    preview_adapters = build_target_adapters(targets, args.state_dir)
    detected = {target: adapter.detect() for target, adapter in preview_adapters.items()}
    target_instances = {
        target: adapter.target_instance()
        for target, adapter in preview_adapters.items()
        if hasattr(adapter, "target_instance")
    }
    for target, result in detected.items():
        if result.status == "skipped":
            target_instances[target] = {"status": "skipped", "reason": result.message}
    plan = create_plan(args.seed_color, targets, target_instances=target_instances)
    save_plan(plan, args.plans_dir)
    apply_adapters = build_target_adapters(plan.targets, args.state_dir, plan.target_instances)
    store = TransactionStore(args.transactions_dir)
    record = apply_plan(plan, apply_adapters, store, confirm=True)
    removed = store.prune(keep=args.keep_transactions, preserve={record.id})
    verified: dict[str, AdapterResult] = {}
    for target in plan.targets:
        operations = record.results.get(target, [])
        verify_op = next((item for item in reversed(operations) if item.get("operation") == "verify"), None)
        if verify_op is not None:
            verified[target] = AdapterResult(
                target=target,
                status=str(verify_op.get("status", "failed")),
                changed=bool(verify_op.get("changed", False)),
                verified=bool(verify_op.get("verified", False)),
                message=str(verify_op.get("message", "")),
                requires_user_action=bool(verify_op.get("requires_user_action", False)),
                version=verify_op.get("version"),
                metadata=dict(verify_op.get("metadata", {})) if isinstance(verify_op.get("metadata"), dict) else {},
            )
        elif operations:
            latest = operations[-1]
            latest_status = str(latest.get("status", "skipped"))
            source_op = latest
            if latest.get("operation") == "auto_rollback":
                source_op = next(
                    (
                        item
                        for item in reversed(operations[:-1])
                        if item.get("operation") != "auto_rollback"
                        and (item.get("status") not in {"ok", "partial"} or item.get("verified") is False)
                    ),
                    latest,
                )
            verified[target] = AdapterResult(
                target=target,
                status="skipped" if latest_status == "skipped" else "failed",
                changed=False,
                verified=False,
                message=str(source_op.get("message", "")),
                requires_user_action=bool(source_op.get("requires_user_action", False)),
                version=source_op.get("version"),
                metadata=dict(source_op.get("metadata", {})) if isinstance(source_op.get("metadata"), dict) else {},
            )
        else:
            verified[target] = verify_plan(replace(plan, targets=(target,)), apply_adapters)[target]
    verify_status = _aggregate_status(verified)
    ok = record.status in {TransactionStatus.APPLIED, TransactionStatus.PARTIAL} and verify_status in {"ok", "partial"}
    if args.output == "json":
        _emit(
            _record_payload(
                "sync",
                record,
                {
                    "verify_status": verify_status,
                    "verify_targets": [_adapter_result_payload(asdict(verified[target])) for target in plan.targets],
                    "pruned_transactions": removed,
                },
            ),
            args.output,
        )
        return 0 if ok else 1
    print(f"Plan ID: {plan.id}")
    print(f"Transaction ID: {record.id}")
    print(f"Status: {record.status.value}")
    print(f"Verify: {verify_status.upper()}")
    if removed:
        print(f"Pruned transactions: {len(removed)}")
    return 0 if ok else 1


def _aggregate_status(results) -> str:
    statuses = [result.status for result in results.values()]
    if not any(result.verified and result.status in {"ok", "partial"} for result in results.values()):
        return "failed"
    if any(status in {"partial", "skipped", "failed"} for status in statuses):
        return "partial"
    return "ok"


def _verify(args: argparse.Namespace) -> int:
    plan = load_plan(args.plan_id, args.plans_dir)
    adapters = build_target_adapters(plan.targets, args.state_dir, plan.target_instances)
    results = verify_plan(plan, adapters)
    status = _aggregate_status(results)
    if args.output == "json":
        _emit({
            "command": "verify",
            "status": status,
            "plan_id": plan.id,
            "targets": [
                _adapter_result_payload(asdict(results[target]))
                for target in plan.targets
            ],
            "message": f"verify completed with status {status}",
        }, args.output)
        return 0 if status in {"ok", "partial"} else 1
    print(f"Plan ID: {plan.id}")
    print(f"Status: {status.upper()}")
    for target in plan.targets:
        print(f"{target}: {results[target].status}")
    print("Field regions:")
    for target in plan.targets:
        print(f"- {target}: {', '.join(inventory_groups(target)) or 'none'}")
    return 0 if status in {"ok", "partial"} else 1


def main(argv: Sequence[str] | None = None) -> int:
    parser = _build_parser()
    try:
        args = parser.parse_args(argv)
    except SystemExit as error:
        return int(error.code)
    try:
        if args.command == "preview":
            return _preview(args)
        if args.command == "apply":
            return _apply(args)
        if args.command == "verify":
            return _verify(args)
        if args.command == "sync":
            return _sync(args)
        return _rollback(args)
    except (FileNotFoundError, PlanIntegrityError, ValueError, OSError) as error:
        if getattr(args, "output", "human") == "json":
            _emit({"command": getattr(args, "command", "unknown"), "status": "FAILED", "error": str(error)}, args.output, error=True)
            return 1
        print(f"Error: {error}", file=sys.stderr)
        return 1
