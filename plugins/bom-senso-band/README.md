# Bom senso band

Mod do Claude Code que acompanha o plugin `bom-senso`. Quando o modelo registra um exemplo novo com `store.py add --timer 20 --session <id>`, aparece uma banda acima do prompt, no proprio terminal, com a regra registrada, a contagem regressiva de 20 s e os botoes "Nao registrar" e "Nao perguntar mais". Sem resposta, o exemplo fica aceito. A banda le `~/.claude/state/bom-senso/pending.json` a cada segundo e chama `store.py decline <sessao>` ao recusar.

Testes: `claude plugin test .` na pasta do mod.
