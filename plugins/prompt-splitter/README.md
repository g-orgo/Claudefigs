# prompt-splitter

Plugin local para dividir um prompt com vários pedidos em sessões Claude separadas, rodando em paralelo em segundo plano. A divisão é opcional: o Claude pergunta antes de lançar qualquer sessão.

## O que faz

Quando você envia um prompt com vários pedidos, numerados ou não, ou aponta para um arquivo com uma lista numerada (correções, ordens, tarefas), um hook detecta a lista e pede ao Claude que pergunte antes de agir. A pergunta tem três opções:

- Dividir em sessões (recomendado).
- Dividir e abrir abas do Konsole.
- Manter nesta sessão.

Se você escolher dividir, a skill `split` agrupa os pedidos (cada item numerado vira um grupo, salvo quando dois itens mexem nos mesmos arquivos) e lança uma sessão em segundo plano por grupo com `claude --bg`. Se escolher manter, o trabalho segue normalmente aqui.

## Detecção

- Prompt: o hook conta itens numerados no início de linha, nos formatos `1)`, `1.`, `1 -` e `(1)`. Com dois ou mais itens, ele adiciona a dica ao contexto.
- Pedidos não numerados: sem lista numerada, o hook procura pedidos separados no próprio prompt (pt-BR e inglês). Conta como pedido cada linha, item com `-`, `*` ou `+`, frase ou trecho depois de conectores como "e também", "além disso", "outra coisa", "also" e "another thing" que comece com um verbo de pedido ("corrija", "adicionar", "fix", "add") ou com "quero que"/"I want". A dica aparece com três ou mais pedidos, ou com dois quando estão em linhas diferentes ou ligados por conector. Para evitar falsos positivos, ficam de fora blocos de código, citações com `>`, verbos de leitura ou restrição ("leia", "use", "mantenha", "make sure"), "e"/"and" simples, pedidos curtos de teste ("adicione testes") e itens que detalham uma linha-guia terminada em `:` (exceto quando a guia fala em "coisas", "tarefas", "ajustes" e afins). A dica pede ao Claude que ignore a sugestão se for um único pedido com detalhes.
- Arquivos citados no prompt: tokens `@caminho` e caminhos com `/` ou terminados em `.md`, `.txt` ou `.markdown` são resolvidos a partir do diretório atual. Arquivos regulares de até 300 KB são lidos e contados do mesmo jeito. Com dois ou mais itens, a dica cita o arquivo.
- Leitura pelo Claude: quando o Claude lê um arquivo com três ou mais itens numerados, um segundo hook (`PostToolUse`, matcher `Read`) registra uma nota, uma única vez por sessão e arquivo. A nota só pede confirmação se o arquivo for uma lista de pedidos a executar; se for material de referência, o Claude a ignora.

Prompts que começam com `/` são ignorados.

## Opt-out

Inclua `[nosplit]` em qualquer lugar do prompt para manter tudo na sessão atual.

Sessões filhas iniciadas pelo plugin usam `CLAUDE_SPLIT_CHILD=1` e não se dividem de novo.

## Visualizar a execução

- `--view konsole` no `dispatch.py` (ou a opção de abas na pergunta) abre uma aba do Konsole por sessão.
- `claude agents` abre o painel visual de sessões em segundo plano.
- `claude attach <id>` abre uma sessão específica.
- `/prompt-splitter:sessions` lista as últimas 20 sessões disparadas do diretório atual, com estado e a ordem de execução; `--all` lista de todos os diretórios.
- Cada registro agora carrega `parent` (sessão pai) e `group` (um id por rodada), e o modo split-pane entrega os resultados agregados à sessão pai quando todos os filhos de um grupo terminam.

## Painel Splits

O painel lista os splits desta sessão. `/splits` abre o painel em qualquer largura; sem ele, o painel só se acopla automaticamente a partir de 144 colunas. Um clique, ou Tab e setas seguidos de Enter, abre a transcrição de um filho. O `/prompt-splitter:sessions` mostra os splits em árvore, agrupados pela sessão pai, com os filhos na ordem de execução e, quando esperam outros, a legenda "aguardando <títulos>".

## Escritório dos splits (`claude split` ou `claude --splits`)

`claude split` e `claude --splits` abrem um escritório animado em tela cheia, somente leitura. É um programa próprio (`scripts/claude_office.py`), então não existe área de escrita e nenhuma sessão do Claude é iniciada. Precisa só de um terminal com truecolor.

A primeira tela é o corredor do diretório atual. Em telas a partir de 188x46 as salas ficam nas paredes diagonais ao lado da mesa, e as salas laterais ficam abaixo delas; em telas com menos de 188 colunas elas viram uma lista, e a mesa continua presente em todas as páginas. Cada sessão tem uma porta com vidraça para ver os personagens lá dentro, a label resumida da sessão e uma luz de estado (verde rodando, amarela aguardando, vermelha com falha, cinza ociosa). Só aparecem as sessões cujo split ou sessão de origem rodou neste diretório ou abaixo dele. A mesa tem máquina de café, planta e bebedouro, e os personagens andam por rotas, desviando de mesas, paredes e balcão.

A caixa vermelha sobre a mesa, ou a tecla `w`, leva a **Todas as sessões**, com as sessões de qualquer diretório. Entrar por uma porta mostra a sala da sessão, com um personagem por item e, acima de cada um, um balão com o final da atividade, no mesmo formato do painel lateral: `Voce`, `Claude`, as etapas descritivas (`Estou lendo o arquivo api.md (x3)`) e o estado na última linha. Os balões narram em primeira pessoa, com o arquivo ou comando em mão.

Cada mesa de um split usa um dos cinco kits de móveis, conforme a posição do item: clássica, retrô, gamer, ateliê e biblioteca. O kit define o tampo, a cadeira, o monitor, o teclado e os objetos sobre a mesa (`office/props.py` e `office/deskitems.py`).

| Estado do split | O que o personagem faz |
| --- | --- |
| Rodando | digita, lê um papel ou fala ao telefone conforme a ferramenta em uso; a tela do monitor acompanha, e de vez em quando ele olha em volta ou toma um gole de café |
| Pensando | mão no queixo, balãozinho de reticências |
| Esperando outro split | levanta, vai até a mesa de quem está trabalhando e fica de caneca na mão; os dois trocam reticências e coraçõezinhos |
| Aguardando você | olha em volta na mesa, com `?` ou `!` |
| Concluído | vive o dia: toma café, cochila, lê ou fala ao telefone na mesa, passeia pela sala, visita um colega para conversar e sai pela porta para a copa, onde quem estiver lá também conversa; o balão avisa quando saiu |
| Falhou | cabeça na mesa, com um X |

Teclas: esquerda e direita mudam a seleção, sem dar a volta nas pontas; na sala, cima e baixo rolam o chat do item selecionado; Tab ou clique na caixa de texto (um painel de pixel art que flutua sobre o piso; onde não há piso livre, o piso se estende abaixo da cena) escreve nela. O texto do painel usa caracteres sextantes (U+1FB00), então o terminal precisa desenhá-los ou ter uma fonte com eles; `q` ou Ctrl+C saem (com a caixa em foco, `q` só escreve).

Na caixa de texto, Enter envia: na sala vai para o item selecionado, no hall ou no depósito inicia uma sessão nova na pasta do escritório. Sessão rodando recebe um aviso e não recebe o texto. Esc tira o foco e mantém o rascunho; Ctrl+U apaga tudo. Com `--demo` nada é enviado, e a caixa mostra "Demo: nada foi enviado". As salas mais recentes vêm primeiro. Quando não cabe tudo, a sala ganha páginas. Na sala, a roda do mouse rola o chat do balão sob o ponteiro e, fora dos balões, muda a página (Baixo volta ao fim do chat), e o botão de seta para a esquerda, ao lado da caixa de texto na sala e no depósito, volta ao escritório. As quebras de página caem entre salas, e só uma sala maior que a página inteira se divide, com `parte 2/4` na placa. Abaixo de 36x28 o programa pede para aumentar o terminal. Como o programa recebe o mouse, para selecionar texto na tela segure Shift ao arrastar. `w` vai a Todas as sessões e Esc ou Backspace voltam.

Mouse: passar por cima de um balão, porta ou entrada seleciona o elemento, que ganha uma borda branca grossa; com a caixa de texto em foco a seleção não muda, para o destino do rascunho continuar o mesmo. Passar sobre a caixa só a destaca, sem dar foco. Clicar em um balão seleciona o split e abre a sessão; a roda rola o chat do balão sob o ponteiro e, longe dos balões, muda a página da sala. Enter, quando o split selecionado está fora da página mostrada, só traz a página de volta, sem abrir nada. Como o programa captura o mouse, para copiar texto da tela segure Shift ao arrastar.

Enter e clique abrem a sessão no diretório do split, sempre com a caixa de texto para continuar a conversa. Sessão que o `claude agents` conhece, viva ou encerrada, abre com `claude attach <id>`, que acorda a encerrada. Sessão que saiu do registro (depois de um `claude rm`, por exemplo) abre com `claude --resume <id completo>`, lido da transcrição. Um split que ainda não começou não tem o que abrir, e o rodapé avisa.

Opções: `--demo` mostra splits de exemplo; `--snapshot arquivo.png --size 200x60 --tick 80 --view hall|warehouse|room` grava um quadro; `--bench N` mede o tempo por quadro.

O comando vem do wrapper `scripts/claude-split.bash`, carregado pelo `~/.bashrc`, que repassa qualquer outro uso ao `claude` real:

```bash
[ -f "$HOME/.claude/local-plugins/plugins/prompt-splitter/scripts/claude-split.bash" ] && . "$HOME/.claude/local-plugins/plugins/prompt-splitter/scripts/claude-split.bash"
```

## Prompts enviados da sessão principal

Com uma filha aberta no painel, o que você digita no composer da sessão principal vai para essa filha. Na filha, ele chega como um prompt seu, e não como "mensagem de outra sessão": o mod reenvia o texto com `$.prompt.submit({ text, asUser: true })` e descarta a entrega original.

O hook `session.receive` não informa qual sessão enviou a mensagem, e o campo `from-plugin` é só o que o remetente declara. Por isso, antes de enviar, a sessão principal grava um ticket em `~/.claude/state/prompt-splitter-routes/<sessão filha>.json` com a sessão de origem, o texto e a hora. A filha (`CLAUDE_SPLIT_CHILD=1`) só trata a mensagem como sua quando:

- ela veio de outra sessão com `from-plugin="prompt-splitter"`;
- existe um ticket com o mesmo texto, criado há no máximo 2 minutos;
- a origem do ticket é a sessão `parent` registrada para essa filha em `~/.claude/state/prompt-splitter.jsonl`.

Cada ticket vale para uma única entrega. Qualquer outra mensagem entre sessões, inclusive de uma filha irmã ou de outro plugin, segue com o tratamento padrão. O limite de confiança é o usuário local: um processo seu que consegue escrever em `~/.claude/state` também consegue forjar o ticket.

## Cadeias e paralelismo

Cada grupo do plano pode ter `"after": ["<name>", ...]`, com os nomes dos grupos que ele espera terminar. Os grupos ligados por `after` formam uma **cadeia**: os itens da cadeia rodam em sequência e aparecem numerados como `K.S` (cadeia K, passo S). Grupos sem nenhum vínculo são independentes, rodam ao mesmo tempo e aparecem como `K`. O `dispatch.py` registra cada item com `index`, `label` (`K` ou `K.S`), `chain`, `step`, `chain_len`, `mode` (`async` para itens isolados, `sync` para os da cadeia) e `after`.

Um item com dependências não é lançado na hora: ele fica registrado com `state: "waiting"` e um processo de espera (`dispatch.py --wait <state.json>`, em `~/.claude/state/`) o lança quando todas as dependências terminam, consultando `claude agents` a cada 15 s. Nomes desconhecidos ou ciclos param o dispatch com código 2, sem lançar nada. Quando o pedido é sequencial ("um de cada vez", "em sequência"), a skill encadeia todos os grupos.

Na tabela do dispatch e no `status.py`, `✓` indica item completo e `○` indica item em andamento ou aguardando. Um item cuja sessão terminou o turno e aguarda o usuário aparece como "concluida, aguarda voce" (completo); se a última resposta do filho é uma pergunta sem resposta, aparece como "aguarda sua resposta". No painel Splits, só fica cinza o item que ainda não começou por depender de outro processo (cadeia síncrona aguardando); item já iniciado, rodando ou concluído, mantém a cor da sua cadeia.

Quando todos os filhos de um split terminam, as respostas finais são entregues à sessão pai uma única vez. O registro durável dessas entregas fica em `~/.claude/state/prompt-splitter-delivered.json`.

## Cuidados

Sessões paralelas que editam os mesmos arquivos ou o mesmo repositório git podem conflitar. A skill avisa no plano quando isso parece provável, mas a decisão de agrupar fica com você.

Na primeira vez em um diretório, rode `claude` nele e aceite a confiança do workspace; sem isso o `dispatch.py` para com uma mensagem clara.
