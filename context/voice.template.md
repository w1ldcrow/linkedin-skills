# Contrato de voz

> Copie este arquivo para `context/voice.md` (ignorado pelo git — a sua voz é sua e não
> entra no repositório) e ajuste — ou deixe que as skills o criem na primeira execução,
> a partir da entrevista em `shared/context-setup.md`. As regras abaixo são o padrão
> opinativo do pacote; cada `[VERIFICAR]` é uma decisão que só o dono do perfil pode
> tomar. Apague o que não valer para você e acrescente o que faltar. A metade mecânica
> (`tools/voicecheck.py`) continua valendo do mesmo jeito, seja qual for a sua voz.

Este arquivo governa todo texto gerado para o LinkedIn: posts, comentários, headline,
About e notas de convite.

Parte destas regras é mecânica e está implementada em `tools/voicecheck.py`. Parte exige
julgamento e só existe aqui. As duas passagens são obrigatórias — veja
`shared/voice-check.md`.

## Quem está falando

- **Idioma dos textos:** [VERIFICAR: pt-BR, en, outro]. O linter conhece listas de frases
  proibidas em pt-BR e en; em outro idioma valem só as regras estruturais (emoji,
  tamanho, hashtags, pergunta no fim, específico concreto) e a lista **Os meus** abaixo
  pesa mais.
- **Pessoa:** [VERIFICAR: primeira pessoa do singular é o padrão]
- **Para quem:** [VERIFICAR: quem lê — pares da sua área, quem está começando, quem
  contrata, clientes. O primeiro da lista define o registro padrão: vocabulário
  compartilhado ou glosa em palavras simples.]
- **Três palavras que o tom é:** [VERIFICAR: ex. relaxado, elegante, direto]
- **Três palavras que o tom nunca é:** [VERIFICAR: ex. motivacional, corporativo,
  professoral]
- **Como você fala de verdade:** [VERIFICAR: cole aqui um parágrafo seu — uma mensagem,
  um post antigo, um trecho de README escrito sem ajuda. É a melhor referência que a
  skill pode ter. Se não tiver nada à mão, apague esta linha; nunca invente um.]

## Idioma e registro

[VERIFICAR: ajuste ao que respondeu acima — o parágrafo abaixo é o padrão do pacote]

Frases curtas. Concreto antes de abstrato.

O tom é relaxado, positivo, elegante e simples. Escrevendo para um par, não para uma
plateia. Quem lê é tratado como igual: sabe do assunto, sabe quando está sendo cortejado,
e fecha a aba quando percebe.

Elegante aqui não quer dizer formal. Quer dizer que nenhuma palavra está sobrando.

## Proibido

[VERIFICAR: cada bloco abaixo é um padrão do pacote — mantenha, afrouxe ou apague. O que
o linter reprova mecanicamente continua reprovado; o resto é aplicado por julgamento.]

**Emojis.** Nenhum, em lugar nenhum, nem como marcador de lista.

**Iscas de engajamento:**

- `Comenta aí`
- `Concorda?`
- `E você, o que acha?`
- `Bora?`
- em inglês: `Thoughts?`, `Agree?`, `Let that sink in`

**A antítese:** `Não é sobre X. É sobre Y.` (`It's not about X. It's about Y.`) A
construção anuncia profundidade e não entrega nenhuma.

**Marcadores de clickbait:** `Spoiler:`, `Plot twist:`, `A real é que`,
`Deixa eu te contar`, `Hot take:`, `Unpopular opinion:`.

**Muros de hashtag.** No máximo três, minúsculas, só no fim.

**Superlativo sem prova:** `revolucionário`, `game changer`, `incrível`, `absurdo`.
Se a coisa é boa, mostre o número.

**Anúncio inflado:** `humildemente`, `orgulhoso em compartilhar`, `feliz em anunciar`,
`thrilled to announce`.

**Vulnerabilidade fabricada:** `Errei muito até entender que...`. Erro real com detalhe
real é ótimo conteúdo. Erro genérico usado como gancho é performance.

**Ganchos de listicle:** `5 lições que aprendi`, `3 coisas que ninguém te conta`.

**Tiques de LLM:** `No mundo de hoje`, `cada vez mais`, `vale ressaltar`,
`em um cenário onde`, `it's worth noting`, `delve into`.

**Escadinha de uma linha por parágrafo** usada só para criar ritmo artificial.

**Os meus:**

- [VERIFICAR: frases, palavras e cacoetes que você nunca usaria — o linter não conhece
  estes; a skill aplica por julgamento e reescreve quando aparecem]

## Obrigatório

- Pelo menos um específico concreto: um número, uma versão, uma ferramenta com nome, uma
  situação que aconteceu de verdade.
- Terminar em afirmação, não em pergunta.
- O tamanho segue o trabalho do post, entre 300 e 2900 caracteres. Um mês saudável
  mistura três formatos: curto e simples (300–700, uma ideia só, sem "ver mais" para
  esconder nada), intermediário (800–1400) e longo e técnico (1500–2900, com passo a
  passo ou mecanismo de verdade). Todos do mesmo tamanho é template, e template lê
  como IA — `tools/batchcheck.py` reprova o lote monótono.
- [VERIFICAR: algo que todo texto seu precisa ter? Apague a linha se não houver.]

## Julgamento

Nenhum regex decide estas. Antes de mostrar qualquer texto ao usuário, responda:

1. Soa como o dono do perfil falando, ou como uma conta de marca?
2. O específico concreto é real, ou foi enfeite colocado só para satisfazer a regra?
3. Um leitor competente da sua área, no seu idioma, leria isso e reconheceria como
   escrito por IA?
4. A primeira frase é algo que uma pessoa diria, ou foi desenhada para o algoritmo?
5. Toda afirmação sobre a empresa ou marca que você representa (`context/brand.md`) é
   informação pública?

## Exemplo

[VERIFICAR: substitua pelo seu próprio par antes/depois quando tiver um. O exemplo abaixo
é o do pacote e mostra o tipo de diferença que importa.]

**Antes:**

> Não é sobre a ferramenta. É sobre o problema.
>
> Depois de anos trabalhando com backend, aprendi uma lição incrível: no mundo de hoje,
> simplicidade é cada vez mais valiosa.
>
> Migrei de uma stack complexa para algo mais simples e os resultados foram surpreendentes.
>
> E você, já passou por isso? Comenta aí!

Diz nada. Nenhum número, nenhum nome, nenhuma decisão. Serve para qualquer pessoa e
qualquer stack, e é exatamente por isso que não serve para ninguém.

**Depois:**

> Passei a semana trocando o Celery por RQ em um worker que processa 40 mil jobs por dia.
>
> A motivação não foi performance, foi conseguir ler o código de retry sem abrir três
> arquivos. O Celery resolve muito mais problemas do que eu tenho, e essa generalidade
> aparece na configuração.
>
> A migração levou dois dias, sendo um dia inteiro só para reescrever os testes de
> integração que dependiam do eager mode. A latência mediana caiu de 800ms para 410ms, mas
> isso é efeito colateral, não o objetivo.
>
> Se o seu worker já está estável no Celery, não existe motivo para mexer. A troca só se
> paga quando a complexidade da ferramenta passa a competir com a complexidade do problema.
>
> Continuo achando o Celery uma peça excelente de engenharia. Ele só não era a peça que
> esse projeto pedia.

Números verificáveis, uma decisão com custo declarado, e um conselho que inclui o caso em
que o leitor não deve fazer nada.

## A regra que não se negocia

Texto que falha é reescrito. Nunca entregue um texto reprovado com um aviso do lado.
