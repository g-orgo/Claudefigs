# Claudefigs

Minhas configurações do Claude Code e o plugin local `prompt-splitter`. Este repositório é público: nada de credenciais, histórico ou dados pessoais entra aqui.

## O que tem aqui

- `claude/`: `CLAUDE.md` global, `settings.json`, `statusline.py`, `agents/` e `hooks/`.
- `plugins/prompt-splitter/`: o plugin. O funcionamento está no `README.md` dele.
- `.claude-plugin/marketplace.json`: o marketplace `local-plugins`, que aponta para o plugin.
- `scripts/sync.py`: publica aqui o que está em `~/.claude`.

## Como instalar

Copie as configurações. Isso sobrescreve arquivos de mesmo nome em `~/.claude`, então faça backup antes se já tiver os seus:

```bash
git clone https://github.com/g-orgo/Claudefigs.git
cd Claudefigs
mkdir -p ~/.claude
cp -r claude/. ~/.claude/
```

Instale o plugin:

```bash
mkdir -p ~/.claude/local-plugins/plugins
cp -r .claude-plugin ~/.claude/local-plugins/
cp -r plugins/prompt-splitter ~/.claude/local-plugins/plugins/
claude plugin marketplace add ~/.claude/local-plugins
claude plugin install prompt-splitter@local-plugins
```

Os caminhos usam a minha home. Em outra máquina, troque `/home/Orgo` e `/var/home/Orgo` em `~/.claude/settings.json` e em `~/.claude/hooks/router.py` pela sua.

O comando `claude split` precisa de uma linha no `~/.bashrc`, descrita no README do plugin.

## Como atualizar este repositório

```bash
python3 scripts/sync.py
git status
git diff --stat
```

Depois é só fazer commit e push para `main`. O script copia apenas o que está na lista de permissão, remove os campos privados das cópias e verifica o resultado. Se encontrar um token, chave ou e-mail pessoal, ele para sem alterar nada.

## O que fica de fora

- Credenciais: `.credentials.json` e tokens.
- Dados de uso: `projects/`, `state/`, `history.jsonl`, sessões, snapshots de shell, `file-history/`, caches e telemetria.
- Plugins de terceiros e skills sincronizadas: `plugins/` de `~/.claude`, `skills/synced/`.
- `HANDOFF.md` do plugin, que são anotações de trabalho com pedidos literais e ids de sessão.
- `.claude-plugin/types/` e `__pycache__/`, que são arquivos gerados.
- `autoMode` do `settings.json`, que descreve repositórios privados.
- Campos `email` dos manifestos e a referência a um projeto privado no `CLAUDE.md`, removidos só na cópia publicada.
