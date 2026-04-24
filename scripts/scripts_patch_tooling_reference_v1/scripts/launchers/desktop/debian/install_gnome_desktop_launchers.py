#!/usr/bin/env python3
"""Install generic Debian/GNOME desktop launchers for the patch tooling."""
from __future__ import annotations

import argparse
import re
import shlex
import shutil
import sys
from dataclasses import dataclass
from pathlib import Path

DEFAULT_ASSETS_ROOT = Path("/home/fabyuu/Projetos/REF/project-assets")
DEFAULT_APPLICATIONS_DIR = Path.home() / ".local" / "share" / "applications"
DEFAULT_ICONS_DIR = Path.home() / ".local" / "share" / "icons" / "hicolor" / "512x512" / "apps"


@dataclass(frozen=True)
class DesktopLauncherSpec:
    desktop_filename: str
    template_path: Path
    launcher_script_path: Path


def slugify(value: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9]+", "-", value.strip().lower()).strip("-")
    return cleaned or "project"


def env_var_from_slug(slug: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9]+", "_", slug).strip("_").upper()
    return f"{cleaned or 'PROJECT'}_PYTHON"


def validate_env_var_name(name: str) -> str:
    if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", name):
        raise ValueError(f"Nome de variável de ambiente inválido: {name!r}")
    return name


def find_repo_root(start: Path) -> Path:
    current = start.resolve()
    for candidate in [current] + list(current.parents):
        if (candidate / ".git").exists() or (candidate / "pyproject.toml").exists() or (candidate / "scripts").exists():
            return candidate
    raise FileNotFoundError(f"Não foi possível localizar a raiz do repositório a partir de: {start}")


def build_launcher_spec(repo_root: Path, project_slug: str) -> DesktopLauncherSpec:
    base_dir = repo_root / "scripts" / "launchers" / "desktop" / "debian"
    return DesktopLauncherSpec(
        desktop_filename=f"{project_slug}-patch-terminal.desktop",
        template_path=base_dir / "patch-terminal.desktop.in",
        launcher_script_path=base_dir / "open_patch_terminal.sh",
    )


def discover_png_icon(*, assets_root: Path, project_slug: str) -> Path | None:
    png_dir = assets_root / "projects" / project_slug / "desktop-icons" / "png"
    if not png_dir.is_dir():
        return None

    candidates = sorted(
        path
        for path in png_dir.iterdir()
        if path.is_file() and path.suffix.lower() == ".png" and path.name != ".gitkeep"
    )
    if not candidates:
        return None

    def score(path: Path) -> tuple[int, str]:
        name = path.name.lower()
        if "patch" in name:
            return (0, name)
        if project_slug.lower() in name:
            return (1, name)
        return (2, name)

    return sorted(candidates, key=score)[0]


def resolve_icon_source(args: argparse.Namespace, project_slug: str) -> Path | None:
    if args.icon_path:
        icon_path = Path(args.icon_path).expanduser().resolve()
        if not icon_path.is_file():
            raise FileNotFoundError(f"Ícone informado não encontrado: {icon_path}")
        if icon_path.suffix.lower() != ".png":
            raise ValueError(f"O ícone deve ser PNG: {icon_path}")
        return icon_path

    assets_root = Path(args.assets_root).expanduser().resolve()
    return discover_png_icon(assets_root=assets_root, project_slug=project_slug)


def install_icon(*, icon_source: Path | None, icons_dir: Path, project_slug: str, allow_missing_icon: bool) -> str:
    if icon_source is None:
        if allow_missing_icon:
            return "utilities-terminal"
        raise FileNotFoundError(
            "Nenhum PNG encontrado para o launcher. Esperado em: "
            f"projects/{project_slug}/desktop-icons/png/ dentro do project-assets. "
            "Use --icon-path para informar um PNG manualmente."
        )

    icons_dir.mkdir(parents=True, exist_ok=True)
    dest = icons_dir / f"{project_slug}-patch.png"
    shutil.copy2(icon_source, dest)
    return str(dest)


def render_exec_line(*, launcher_script_path: Path, python_executable: Path, python_env_var: str, project_name: str, project_slug: str) -> str:
    env_assignments = {
        "PATCH_TOOL_PROJECT_NAME": project_name,
        "PATCH_TOOL_PROJECT_SLUG": project_slug,
        "PATCH_TOOL_PYTHON_ENV_VAR": python_env_var,
        python_env_var: str(python_executable),
    }
    prefix = " ".join(f"{key}={shlex.quote(value)}" for key, value in env_assignments.items())
    inner_command = f"{prefix} bash {shlex.quote(str(launcher_script_path))}"
    return "gnome-terminal -- /bin/bash -lc " + shlex.quote(inner_command)


def render_desktop_entry(template_text: str, *, launcher_name: str, launcher_comment: str, exec_line: str, icon_path: str) -> str:
    return (
        template_text.replace("{{LAUNCHER_NAME}}", launcher_name)
        .replace("{{LAUNCHER_COMMENT}}", launcher_comment)
        .replace("{{EXEC_LINE}}", exec_line)
        .replace("{{ICON_PATH}}", icon_path)
    )


def install_desktop_launcher(
    *,
    repo_root: Path,
    applications_dir: Path,
    icons_dir: Path,
    python_executable: Path,
    project_name: str,
    project_slug: str,
    python_env_var: str,
    icon_source: Path | None,
    allow_missing_icon: bool,
    dry_run: bool,
) -> Path:
    spec = build_launcher_spec(repo_root, project_slug)
    if not spec.template_path.is_file():
        raise FileNotFoundError(f"Template .desktop não encontrado: {spec.template_path}")
    if not spec.launcher_script_path.is_file():
        raise FileNotFoundError(f"Launcher .sh não encontrado: {spec.launcher_script_path}")

    icon_path = install_icon(
        icon_source=icon_source,
        icons_dir=icons_dir,
        project_slug=project_slug,
        allow_missing_icon=allow_missing_icon,
    ) if not dry_run else str(icon_source) if icon_source else "utilities-terminal"

    exec_line = render_exec_line(
        launcher_script_path=spec.launcher_script_path,
        python_executable=python_executable,
        python_env_var=python_env_var,
        project_name=project_name,
        project_slug=project_slug,
    )
    rendered = render_desktop_entry(
        spec.template_path.read_text(encoding="utf-8"),
        launcher_name=f"{project_name} Patch",
        launcher_comment=f"Aplica patch.zip em {project_name} com terminal visível",
        exec_line=exec_line,
        icon_path=icon_path,
    )

    destination = applications_dir / spec.desktop_filename
    if dry_run:
        print("DRY-RUN: launcher renderizado:")
        print(rendered)
        print(f"DRY-RUN: destino .desktop: {destination}")
        return destination

    applications_dir.mkdir(parents=True, exist_ok=True)
    destination.write_text(rendered, encoding="utf-8")
    return destination


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Instala launcher Debian/GNOME para aplicar patch.zip no projeto atual.")
    parser.add_argument("--repo-root", default=None, help="Raiz do repositório. Default: auto-detecta a partir deste script.")
    parser.add_argument("--project-name", default=None, help="Nome canônico exibido no launcher. Default: nome da pasta do repo.")
    parser.add_argument("--project-slug", default=None, help="Slug do projeto usado no .desktop e project-assets. Default: slug do nome do repo.")
    parser.add_argument("--python-env-var", default=None, help="Variável de ambiente específica do projeto para o Python. Default: <SLUG>_PYTHON.")
    parser.add_argument("--python-executable", default=None, help="Python a ser materializado no Exec. Default: sys.executable.")
    parser.add_argument("--applications-dir", default=str(DEFAULT_APPLICATIONS_DIR), help="Diretório de instalação dos .desktop.")
    parser.add_argument("--icons-dir", default=str(DEFAULT_ICONS_DIR), help="Diretório local para copiar o ícone PNG.")
    parser.add_argument("--assets-root", default=str(DEFAULT_ASSETS_ROOT), help="Raiz do project-assets.")
    parser.add_argument("--icon-path", default=None, help="PNG específico para usar como ícone. Sobrepõe busca em project-assets.")
    parser.add_argument("--allow-missing-icon", action="store_true", help="Usa ícone genérico se não houver PNG no project-assets.")
    parser.add_argument("--dry-run", action="store_true", help="Mostra o .desktop renderizado sem instalar.")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)

    repo_root = Path(args.repo_root).expanduser().resolve() if args.repo_root else find_repo_root(Path(__file__).resolve())
    project_name = args.project_name or repo_root.name
    project_slug = slugify(args.project_slug or project_name)
    python_env_var = validate_env_var_name(args.python_env_var or env_var_from_slug(project_slug))
    python_executable = Path(args.python_executable).expanduser().resolve() if args.python_executable else Path(sys.executable).resolve()
    applications_dir = Path(args.applications_dir).expanduser().resolve()
    icons_dir = Path(args.icons_dir).expanduser().resolve()

    try:
        icon_source = resolve_icon_source(args, project_slug)
        installed = install_desktop_launcher(
            repo_root=repo_root,
            applications_dir=applications_dir,
            icons_dir=icons_dir,
            python_executable=python_executable,
            project_name=project_name,
            project_slug=project_slug,
            python_env_var=python_env_var,
            icon_source=icon_source,
            allow_missing_icon=args.allow_missing_icon,
            dry_run=args.dry_run,
        )
    except Exception as exc:
        print(f"ERRO: {exc}", file=sys.stderr)
        return 1

    print("Launcher de patch configurado:")
    print(f" - Projeto: {project_name}")
    print(f" - Slug: {project_slug}")
    print(f" - Variável Python: {python_env_var}")
    print(f" - Ícone: {icon_source if icon_source else 'utilities-terminal'}")
    print(f" - Desktop: {installed}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
