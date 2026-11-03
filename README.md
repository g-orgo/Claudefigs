# Claudefigs

Minhas configurações do Claude Code e o plugin local `prompt-splitter`. Este repositório é público: nada de credenciais, histórico ou dados pessoais entra aqui.

## O que tem aqui

- `claude/`: `CLAUDE.md` global, `settings.json`, `statusline.py`, `agents/` e `hooks/`.
- `plugins/prompt-splitter/`: o plugin. O funcionamento está no `README.md` dele.
- `.claude-plugin/marketplace.json`: o marketplace `local-plugins`, que aponta para o plugin.
- `scripts/sync.py`: copia para cá o que está em `~/.claude`.
- `scripts/publish.py`: roda o sync, faz o commit e o push. É o único comando necessário.

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
python3 /var/home/Orgo/Claudefigs/scripts/publish.py
```

Funciona de qualquer diretório e não precisa de mais nada. O script copia apenas o que está na lista de permissão, remove os campos privados das cópias, verifica o resultado e todo arquivo que o git rastrearia, faz o commit listando as áreas alteradas e envia para `origin main`.

- Se encontrar um token, chave ou e-mail pessoal, ele para sem commitar nem enviar nada. Corrija a origem do achado; não existe opção para pular a verificação.
- Se nada mudou, ele avisa e termina com sucesso, sem commit vazio.
- Se o remoto estiver à frente, ele faz `git pull --rebase` antes do push. Em caso de conflito, ele para com erro, sem enviar nada, e mostra os arquivos em conflito.
- O push nunca é forçado.

Os testes usam um repositório temporário e um remoto local: `python3 scripts/test_publish.py`.

## O que fica de fora

- Credenciais: `.credentials.json` e tokens.
- Dados de uso: `projects/`, `state/`, `history.jsonl`, sessões, snapshots de shell, `file-history/`, caches e telemetria.
- Plugins de terceiros e skills sincronizadas: `plugins/` de `~/.claude`, `skills/synced/`.
- `HANDOFF.md` do plugin, que são anotações de trabalho com pedidos literais e ids de sessão.
- `.claude-plugin/types/` e `__pycache__/`, que são arquivos gerados.
- `autoMode` do `settings.json`, que descreve repositórios privados.
- Campos `email` dos manifestos e a referência a um projeto privado no `CLAUDE.md`, removidos só na cópia publicada.
