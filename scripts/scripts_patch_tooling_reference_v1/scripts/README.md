# Patch Tooling Reference

Este diretório é uma referência genérica para bootstrap de tooling local de aplicação de patches `.zip` em projetos assistidos pelo SIC.

## Escopo

Inclui apenas tooling operacional auxiliar:

- `scripts/tooling/patch_tool.py`: aplicador canônico de `patch.zip`.
- `scripts/patch_tool.py`: wrapper de compatibilidade.
- `scripts/apply_zip_patch.py`: wrapper de compatibilidade.
- `scripts/launchers/desktop/debian/`: launcher Debian/GNOME para aplicar o patch em terminal visível.

Não inclui scripts de domínio, publicação, pipeline, contratos, GitHub, Codex, Discord ou automação end-to-end.

## Comportamento essencial

O `patch_tool.py`:

- procura `patch.zip` na raiz do repositório por padrão;
- aplica arquivos preservando paths relativos;
- rejeita path absoluto, path traversal, symlink e entradas duplicadas no `.zip`;
- ignora diretórios dentro do `.zip`;
- aplica escrita atômica;
- calcula SHA-256 para classificar arquivos criados, atualizados e inalterados;
- suporta `--root`, `--zip-file`, `--dry-run`, `--require-no-conflict`, `--conflict-policy`, `--backup` e `--report`;
- bloqueia conflitos com arquivos staged;
- permite `skip`, `abort` ou `overwrite` para conflitos não staged;
- gera relatório textual e salva `patch_report.txt` quando não estiver em dry-run;
- cria backup timestampado em `.zip_patch_backup/` quando `--backup` estiver ativo.

## Project assets

O instalador de launcher busca o ícone PNG em:

```text
/home/fabyuu/Projetos/REF/project-assets/projects/<project-slug>/desktop-icons/png/
```

A busca ignora `.gitkeep` e prioriza, de forma determinística, arquivos `.png` com `patch` no nome. Também é possível informar um PNG específico com `--icon-path`.

## Comandos úteis

```bash
python scripts/patch_tool.py --help
python scripts/patch_tool.py --root . --dry-run
python scripts/apply_zip_patch.py --help
python scripts/launchers/desktop/debian/install_gnome_desktop_launchers.py --help
```

Instalação do launcher, exemplo:

```bash
python scripts/launchers/desktop/debian/install_gnome_desktop_launchers.py \
  --project-name "N8N Local Stack" \
  --project-slug n8n-local-stack
```

## Regras de adaptação por projeto

Ao usar esta referência para gerar tooling de outro projeto:

- adaptar nome canônico, slug e variável Python do projeto;
- não manter nomes de projetos de origem;
- não copiar scripts fora do escopo de patch tooling;
- não incluir `__pycache__`, `.pyc`, backups ou artefatos gerados;
- não alterar código de domínio do projeto alvo;
- manter o conteúdo espelhado ao caminho real do repositório.
