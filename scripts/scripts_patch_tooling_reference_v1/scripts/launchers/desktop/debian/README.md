# Debian/GNOME Patch Launcher

Este diretório contém um launcher genérico para aplicar `patch.zip` em terminal visível.

Arquivos:

- `open_patch_terminal.sh`: abre/aplica o patch com política segura.
- `open_apply_zip_patch_terminal.sh`: alias compatível para o mesmo fluxo.
- `patch-terminal.desktop.in`: template `.desktop` sem caminho absoluto fixo.
- `install_gnome_desktop_launchers.py`: materializa o `.desktop` no ambiente do usuário.

Política segura usada pelo launcher:

```bash
python scripts/patch_tool.py --root <repo> --require-no-conflict --conflict-policy skip --backup
```

O instalador resolve:

- nome do projeto;
- slug;
- variável Python específica do projeto;
- caminho do ícone PNG via `project-assets`;
- `Exec` com `gnome-terminal`.
