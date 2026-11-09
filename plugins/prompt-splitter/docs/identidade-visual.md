## Alto nível
O **escritório** do prompt-splitter é desenhado em **pixel art isométrica de quarto montado**, a mesma estética das salas de hotel virtual: cada sessão dividida vira um **funcionário**, cada grupo de split vira uma **sala** e o **hall** junta as salas atrás de vidro. A identidade visual vem de um pacote de referências do dono (artes próprias na mesma estética, não oficiais), guardado localmente em `~/Área de trabalho/Referência pixelart/`. As imagens não sobem para o repositório: este documento descreve as regras que tiramos delas.

A ideia central é que tudo pareça **mobília de verdade apoiada no chão**: cada objeto tem **contorno escuro**, **três tons por material** com luz vindo de cima e da esquerda, e **detalhe fino** que conta o que o objeto é (teclas no teclado, gavetas com puxador, folhas na planta). Nada flutua: todo item de mesa encosta no tampo e todo móvel encosta no piso, com uma **sombra de contato** marcando o apoio.

Os **personagens** seguem a mesma regra de contorno e sombreamento, com cabeça grande, olhos simples e iguais e acessórios (óculos, boné) que respeitam o rosto em vez de cobri-lo. O comportamento de cena fica em [[Vida dos personagens]] e a montagem das salas em [[Salas e grupos]].

### Projeção e luz
A grade é **isométrica 2:1**: cada passo horizontal de 2 px sobe 1 px. As linhas de borda dos móveis, do tampo e do piso seguem essa inclinação, em degraus regulares, sem degrau solto. A luz vem de **cima-esquerda**: o tampo é o tom mais claro, a face da esquerda é o tom médio e a face da direita é o tom escuro.

### Materiais
Cada material (madeira, metal, tecido, plástico, vidro, planta, pele) tem uma **rampa de três tons** mais um **realce** opcional de 1 px na aresta que pega luz. Madeira ganha veios em linhas paralelas à aresta; tecido ganha costura ou dobra; vidro é tom claro translúcido com um brilho diagonal.

### Contorno
O contorno é uma cor escura do próprio conjunto (não preto puro), com 1 px de espessura em volta da silhueta. Por dentro, as divisões entre faces usam o tom escuro do material, não o contorno, para o objeto não parecer recortado.

### Objetos de mesa
O tampo é o chão dos objetos de mesa. Teclado, mouse, caneca, monitor, papéis e luminária ficam **dentro da área do tampo**, com a base encostada nele e desenhados na ordem de profundidade (o que está mais ao fundo primeiro). O **teclado** é um bloco inclinado com a grade de teclas visível (linhas de teclas em tons alternados e uma barra de espaço), não um retângulo liso.

## Baixo nível

```py title:Material
name: str; # madeira, metal, tecido, plastico, vidro, planta, pele
light: Color; # tampo e faces viradas para cima
mid: Color; # face da esquerda
dark: Color; # face da direita e divisões internas
highlight?: Color; # 1 px na aresta que pega luz
```

```py title:Prop
footprint: tuple; # losango ocupado no piso ou no tampo, em celulas da grade 2:1
anchor: tuple; # ponto de apoio (base do objeto) no piso ou no tampo
contact_shadow: bool = True; # 1 px de sombra sob a base, no tom escuro do apoio
outline: Color; # contorno do conjunto, nunca preto puro
materials: list[Material];
depth: int; # ordem de desenho; maior profundidade desenha antes
```

```py title:Character
head: Grid; # cabeça grande, contorno de 1 px
eyes: tuple; # os dois olhos com a mesma altura em todo quadro e humor
glasses?: Glasses;
shoulder_row: int; # nunca acima da primeira linha do torso
```

```py title:Glasses
rim: Color; # armação fina e escura, uma por olho, com ponte entre elas
lens_padding: int = 1; # px de lente (pele) entre armação e olho, em todos os lados
temple_reaches: enum; # cabelo, orelha; a haste vai da armação até um dos dois
```

#### Regras de negócio
- Todo objeto tem contorno escuro de 1 px e rampa de três tons com luz de cima-esquerda.
- Nenhum objeto flutua: itens de mesa encostam no tampo e móveis encostam no piso, com sombra de contato.
- Itens de mesa ficam dentro da área do tampo e são desenhados do fundo para a frente.
- O teclado mostra a grade de teclas e a barra de espaço.
- Bordas seguem a inclinação 2:1 em degraus regulares.
- Os dois olhos têm sempre a mesma altura, em todo quadro, humor e tamanho de avatar.
- Óculos não cobrem os olhos: armação fina, 1 px de folga até o olho e haste até o cabelo ou a orelha; no avatar pequeno do hall a lente continua cor de pele.
- O ombro fica dentro do torso, nunca acima da linha de cima dele.
- Uma cadeira vazia mostra os dois braços; ocupada, só o braço da frente (o corpo esconde o de trás).
- Elemento novo herda contorno, rampa e luz dos vizinhos antes de ganhar cor própria.

## Anotações

- As referências podem ser copiadas pixel a pixel?
> 	Não. Elas definem a estética (projeção, luz, contorno, rampas, densidade de detalhe). Os sprites do projeto são desenhados do zero com essas regras.

- Por que as imagens de referência não estão no repositório?
> 	O repositório de configs é público e as imagens ficam só na máquina do dono. **Ainda em aberto:** se o dono quiser, as referências podem subir numa pasta `docs/referencias/`.
