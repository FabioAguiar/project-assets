#!/usr/bin/env python3
"""Generic safe patch.zip applicator.

This script applies a zip patch mirrored to a project repository. It is intentionally
small, deterministic, auditable, and based only on the Python standard library.
"""
from __future__ import annotations

import argparse
import hashlib
import os
import shutil
import stat
import subprocess
import sys
import tempfile
import zipfile
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

PATCH_ZIP_NAME = "patch.zip"
DEFAULT_REPORT_NAME = "patch_report.txt"
BACKUP_DIR_NAME = ".zip_patch_backup"


@dataclass(frozen=True)
class PatchSummary:
    created: list[Path]
    updated: list[Path]
    unchanged: list[Path]
    skipped: list[Path]


def is_git_repo(root: Path) -> bool:
    return (root / ".git").exists()


def run_git_status_porcelain(root: Path) -> list[str]:
    """Return lines like ' M path', 'M  path', '?? path', 'R  old -> new'."""
    out = subprocess.check_output(
        ["git", "status", "--porcelain"],
        cwd=str(root),
        stderr=subprocess.STDOUT,
        text=True,
    )
    return [line.rstrip("\n") for line in out.splitlines() if line.strip()]


def parse_porcelain_line(line: str) -> tuple[str, str]:
    status = line[:2]
    rest = line[3:].strip() if len(line) > 3 else ""

    # Rename/copy: keep the final path, because this is what the patch would touch.
    if " -> " in rest:
        rest = rest.split(" -> ", 1)[1].strip()

    # Git may quote unusual paths. Keep this conservative instead of trying to
    # interpret every possible escape sequence.
    if len(rest) >= 2 and rest[0] == rest[-1] == '"':
        rest = rest[1:-1]

    return status, Path(rest).as_posix() if rest else ""


def get_dirty_paths(root: Path) -> dict[str, str]:
    """Map path_posix -> two-character git porcelain status."""
    dirty: dict[str, str] = {}
    for line in run_git_status_porcelain(root):
        status, path = parse_porcelain_line(line)
        if path:
            dirty[path] = status
    return dirty


def is_staged(status: str) -> bool:
    # First char indicates index status. If it is not space/'?', it is staged.
    return bool(status) and status[0] not in (" ", "?")


def style_staged_conflict_message(conflicts: list[tuple[str, str]]) -> str:
    lines = [
        "",
        "╔══════════════════════════════════════════════════════════════╗",
        "║  ❌ PATCH BLOQUEADO — conflito com arquivos STAGED          ║",
        "╠══════════════════════════════════════════════════════════════╣",
        "║  O patch.zip quer tocar arquivos que já estão no index.     ║",
        "║  Isso é bloqueado para proteger o estado preparado p/ commit.║",
        "╠══════════════════════════════════════════════════════════════╣",
        "║  Arquivos staged em conflito:                               ║",
        "╚══════════════════════════════════════════════════════════════╝",
    ]
    lines.extend(f"  - [{status}] {path}" for status, path in conflicts)
    lines.extend(
        [
            "",
            "Resolva antes de aplicar o patch:",
            '  • Commit:       git commit -m "..."',
            "  • Unstage:      git restore --staged -- <arquivo>",
            "  • Stash staged: git stash push --staged",
            "",
        ]
    )
    return "\n".join(lines)


def style_soft_conflict_notice(conflicts: list[tuple[str, str]], policy: str) -> str:
    lines = [
        "",
        "╔══════════════════════════════════════════════════════════════╗",
        "║  ⚠️  Aviso — conflitos detectados com patch.zip             ║",
        "╠══════════════════════════════════════════════════════════════╣",
        f"║  Política de conflito ativa: {policy:<33} ║",
        "║  Os arquivos abaixo já estão modified/untracked e também    ║",
        "║  aparecem no patch.zip.                                     ║",
        "╚══════════════════════════════════════════════════════════════╝",
    ]
    lines.extend(f"  - [{status}] {path}" for status, path in conflicts)
    lines.append("")
    if policy == "skip":
        lines.append("O script vai PULAR esses arquivos e aplicar o restante.")
    elif policy == "overwrite":
        lines.append("O script vai SOBRESCREVER esses arquivos, desde que não estejam staged.")
    elif policy == "abort":
        lines.append("O script vai ABORTAR e não aplicar nada.")
    lines.append("")
    return "\n".join(lines)


def safe_relpath(name: str) -> Path:
    normalized = name.replace("\\", "/")
    path = Path(normalized)

    if normalized.strip() in {"", ".", "/"}:
        raise ValueError(f"Entrada inválida no zip: {name!r}")
    if path.is_absolute():
        raise ValueError(f"Path absoluto proibido no zip: {name!r}")
    if any(part == ".." for part in path.parts):
        raise ValueError(f"Path traversal proibido no zip: {name!r}")

    return path


def is_zipinfo_symlink(info: zipfile.ZipInfo) -> bool:
    mode = (info.external_attr >> 16) & 0o777777
    return stat.S_ISLNK(mode)


def read_zip_entries(zip_path: Path) -> list[tuple[zipfile.ZipInfo, Path]]:
    entries: list[tuple[zipfile.ZipInfo, Path]] = []
    seen: set[str] = set()

    with zipfile.ZipFile(zip_path, "r") as archive:
        for info in archive.infolist():
            if info.is_dir():
                continue
            if is_zipinfo_symlink(info):
                raise ValueError(f"Symlink proibido no zip: {info.filename!r}")

            rel = safe_relpath(info.filename)
            rel_posix = rel.as_posix()
            if rel_posix in seen:
                raise ValueError(f"Entrada duplicada no zip após normalização: {rel_posix}")
            seen.add(rel_posix)
            entries.append((info, rel))

    return entries


def sha256_bytes(data: bytes) -> str:
    hasher = hashlib.sha256()
    hasher.update(data)
    return hasher.hexdigest()


def file_sha256(path: Path) -> str:
    hasher = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            hasher.update(chunk)
    return hasher.hexdigest()


def write_atomic(dest: Path, data: bytes) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(prefix=f".{dest.name}.", suffix=".tmp", dir=str(dest.parent))
    tmp_path = Path(tmp_name)
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(data)
        os.replace(tmp_path, dest)
    finally:
        if tmp_path.exists():
            tmp_path.unlink()


def make_backup_dir(root: Path) -> Path:
    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    backup_dir = root / BACKUP_DIR_NAME / timestamp
    backup_dir.mkdir(parents=True, exist_ok=False)
    return backup_dir


def render_report(
    root: Path,
    zip_path: Path,
    summary: PatchSummary,
    *,
    conflict_policy: str,
    backup_dir: Path | None,
    dry_run: bool,
) -> str:
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    lines: list[str] = [
        "Zip Patch Report",
        f"Timestamp: {timestamp}",
        f"Project root: {root}",
        f"Zip: {zip_path}",
        f"Dry run: {dry_run}",
        f"Conflict policy: {conflict_policy}",
        f"Backup dir: {backup_dir if backup_dir else 'N/A'}",
        "",
        f"Created:   {len(summary.created)}",
        f"Updated:   {len(summary.updated)}",
        f"Unchanged: {len(summary.unchanged)}",
        f"Skipped:   {len(summary.skipped)}",
        "",
    ]

    def section(title: str, items: list[Path], symbol: str) -> None:
        if not items:
            return
        lines.append(title)
        for path in items:
            lines.append(f"  {symbol} {path.as_posix()}")
        lines.append("")

    section("Created files:", summary.created, "+")
    section("Updated files:", summary.updated, "~")
    section("Unchanged files:", summary.unchanged, "=")
    section("Skipped files:", summary.skipped, "⤼")

    return "\n".join(lines)


def resolve_zip_path(root: Path, zip_file: str) -> Path:
    path = Path(zip_file).expanduser()
    if not path.is_absolute():
        path = root / path
    return path.resolve()


def apply_zip(
    *,
    zip_path: Path,
    root: Path,
    dry_run: bool,
    backup_dir: Path | None,
    conflict_paths: set[str],
    conflict_policy: str,
) -> PatchSummary:
    entries = read_zip_entries(zip_path)
    created: list[Path] = []
    updated: list[Path] = []
    unchanged: list[Path] = []
    skipped: list[Path] = []
    root_resolved = root.resolve()

    with zipfile.ZipFile(zip_path, "r") as archive:
        for info, rel in entries:
            rel_posix = rel.as_posix()
            dest = (root / rel).resolve()

            try:
                dest.relative_to(root_resolved)
            except ValueError as exc:
                raise ValueError(f"Tentativa de escrever fora do projeto: {rel}") from exc

            if rel_posix in conflict_paths and conflict_policy == "skip":
                skipped.append(rel)
                continue

            if dest.exists() and dest.is_dir():
                raise ValueError(f"Destino é diretório, mas o patch contém arquivo: {rel}")

            existed = dest.exists() and dest.is_file()
            new_data = archive.read(info.filename)
            new_hash = sha256_bytes(new_data)

            if not existed:
                created.append(rel)
                if not dry_run:
                    write_atomic(dest, new_data)
                continue

            current_hash = file_sha256(dest)
            if current_hash == new_hash:
                unchanged.append(rel)
                continue

            updated.append(rel)
            if dry_run:
                continue

            if backup_dir is not None:
                backup_path = backup_dir / rel
                backup_path.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(dest, backup_path)

            write_atomic(dest, new_data)

    return PatchSummary(created=created, updated=updated, unchanged=unchanged, skipped=skipped)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Aplica patch.zip espelhado na raiz do projeto com checagens de segurança."
    )
    parser.add_argument("--root", default=".", help="Raiz do projeto. Default: .")
    parser.add_argument(
        "--zip-file",
        default=PATCH_ZIP_NAME,
        help="Arquivo zip a aplicar. Caminho relativo é resolvido a partir de --root. Default: patch.zip",
    )
    parser.add_argument("--dry-run", action="store_true", help="Simula a aplicação sem escrever arquivos.")
    parser.add_argument(
        "--require-no-conflict",
        action="store_true",
        help="Verifica conflitos via git apenas para arquivos presentes no patch.",
    )
    parser.add_argument(
        "--conflict-policy",
        choices=["abort", "skip", "overwrite"],
        default="skip",
        help="Como tratar conflitos não staged. Default: skip.",
    )
    parser.add_argument(
        "--backup",
        action="store_true",
        help="Cria backup timestampado em .zip_patch_backup/ antes de sobrescrever arquivos.",
    )
    parser.add_argument(
        "--report",
        default=DEFAULT_REPORT_NAME,
        help="Relatório salvo na raiz. Use string vazia para não salvar. Default: patch_report.txt",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    root = Path(args.root).expanduser().resolve()
    zip_path = resolve_zip_path(root, args.zip_file)

    if not root.exists() or not root.is_dir():
        print(f"ERRO: raiz do projeto não encontrada: {root}", file=sys.stderr)
        return 1
    if not zip_path.exists() or not zip_path.is_file():
        print(f"ERRO: não encontrei {zip_path.name} em: {zip_path.parent}", file=sys.stderr)
        return 2

    conflict_paths: set[str] = set()

    if args.require_no_conflict:
        if not is_git_repo(root):
            print("ERRO: --require-no-conflict ligado, mas não encontrei .git na raiz.", file=sys.stderr)
            return 3

        try:
            zip_paths = {rel.as_posix() for _, rel in read_zip_entries(zip_path)}
            dirty = get_dirty_paths(root)
        except subprocess.CalledProcessError as exc:
            print(f"ERRO: falha ao consultar git status: {exc.output}", file=sys.stderr)
            return 3
        except Exception as exc:
            print(f"ERRO: falha ao preparar checagem de conflitos: {exc}", file=sys.stderr)
            return 1

        conflicts = [(dirty[path], path) for path in sorted(zip_paths) if path in dirty]
        staged_conflicts = [(status, path) for status, path in conflicts if is_staged(status)]

        if staged_conflicts:
            print(style_staged_conflict_message(staged_conflicts))
            return 4

        if conflicts:
            print(style_soft_conflict_notice(conflicts, args.conflict_policy))
            if args.conflict_policy == "abort":
                print("Conflitos detectados e policy=abort. Nada foi aplicado.\n")
                return 4
            conflict_paths = {path for _, path in conflicts}

    backup_dir = None
    if args.backup and not args.dry_run:
        backup_dir = make_backup_dir(root)

    try:
        summary = apply_zip(
            zip_path=zip_path,
            root=root,
            dry_run=args.dry_run,
            backup_dir=backup_dir,
            conflict_paths=conflict_paths,
            conflict_policy=args.conflict_policy,
        )
    except Exception as exc:
        print(f"ERRO: {exc}", file=sys.stderr)
        return 1

    report = render_report(
        root,
        zip_path,
        summary,
        conflict_policy=args.conflict_policy,
        backup_dir=backup_dir,
        dry_run=args.dry_run,
    )
    print(report)

    if not args.dry_run and args.report is not None and args.report.strip():
        try:
            report_path = root / args.report
            report_path.write_text(report, encoding="utf-8")
            print(f"Relatório salvo em: {report_path}")
        except Exception as exc:
            print(f"AVISO: não consegui salvar relatório: {exc}", file=sys.stderr)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
