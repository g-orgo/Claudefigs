# Bom senso

Refina as etapas da pipeline dos agentes com verificacoes de bom senso e mantem um registro das situacoes em que elas faltaram, para evitar retrabalho com coisas obvias.

## Como funciona

- **Sessao principal (`SessionStart`):** injeta o checklist por etapa (`data/brain.md`) e as regras que voce registrou. Tambem roda depois de uma compactacao. Quando alguma verificacao afeta uma decisao ou o resultado, a mensagem final ao usuario termina com uma secao `Bom senso:` dizendo o que foi feito ou alterado por causa dela.
- **Operadores e validator (`SubagentStart`):** injeta `data/operator.md`, sem mudar os contratos. O relatorio passa a terminar com uma linha `Bom senso:`, com sobreposicoes, variantes e efeitos colaterais encontrados.
- **A cada prompt (`UserPromptSubmit`):**
  - Se o prompt cita "bom senso", a situacao e registrada direto, sem pergunta.
  - Se so parece correcao, e uma sugestao: o modelo confirma e abre uma selecao perguntando se a situacao vira exemplo. Se for um pedido novo, ele ignora em silencio.
  - Se o assunto bate com um exemplo do registro (3 palavras-chave ou mais), a regra entra no contexto.

Sessoes de split nao recebem a pergunta, porque nao ha ninguem para responder, e mensagens de plugins sao ignoradas.

## Comandos

- `/bom-senso:estado`: mostra o estado e a contagem de exemplos. O Bom senso fica sempre ativo, sem opcao de desligar.
- `/bom-senso:exemplos [--category <nome>]`: lista o registro.
- `/bom-senso:exemplos --remove <id>`: remove um exemplo seu.
- `/bom-senso:registrar <situacao>`: registra um exemplo manualmente.

## Onde ficam os dados

- **De fabrica:** `data/seed_examples.json`, publico, sem dados privados.
- **Seus:** `~/.claude/state/bom-senso/examples.jsonl`, privado, fora do repositorio publico.

Todo exemplo vale para todos os projetos: o registro nao distingue projeto.

A origem dos exemplos de fabrica esta em `docs/analise-inicial.md`.

## Testes

`python3 -m unittest tests.test_bom_senso`, na raiz do plugin.
