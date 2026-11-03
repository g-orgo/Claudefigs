# Analise inicial

Base: prompts digitados nas sessoes de outubro e novembro de 2026. Dos 820 prompts lidos, uma busca por palavras-chave marcou 201 como possiveis correcoes, e esses foram lidos um a um. Parte deles e falso positivo (pedidos novos, ordens para sessoes filhas), entao os campos `count` dos exemplos sao estimativas da leitura, nao medidas.

## Padroes encontrados

| Categoria | O que faltou | Como aparecia |
|---|---|---|
| `verificacao` | Ver o resultado antes de dizer que esta pronto | "Testando ainda nao foi alterado", "nao mudou nada essa sua alteracao" |
| `cobertura` | Conferir item por item | "o item 5 simplesmente foi ignorado", "voce nao marcou os itens como pedi" |
| `consistencia` | Corrigir a classe, nao a instancia | "so faltou aplicar quando esta em horizontal", "esse e um problema recorrente" |
| `leitura-literal` | Ler o referente e nao inventar | "pedi para acompanhar a hora, nao o dia", "pedi um brilho INTERNO" |
| `contexto-existente` | Avisar o que ja existe | Blueprints do modpack, "fugiu da paleta que especifiquei nas docs" |
| `estados-obvios` | Pensar no estado depois da acao | "ao criar o evento o menu deve fechar", "o usuario nem deveria ver erros" |
| `regressao` | Preservar o que estava certo | "isso fez a conquista central ficar do mesmo tamanho das outras" |
| `referencia` | Comparar com o print enviado | "ainda estao faltando caracteristicas que tem nos prints" |
| `autonomia` | Ir ate o fim e ser o crivo final | "voce esta com um vicio em esperar que eu teste no jogo" |
| `pipeline` | Usar agentes e ferramentas com criterio | "o operador esta so gastando token", limite do opencode ignorado |

## A tensao que o plugin resolve

Parte das correcoes pede mais iniciativa (normalizar icones, avisar sobre blueprints) e parte pede menos (bordas e selos inventados). Por isso `data/brain.md` separa tres casos: fazer e avisar, perguntar antes e nunca fazer.
