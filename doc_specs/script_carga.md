CONTEXTO
Estou construindo um pipeline de dados em Python sobre o dataset público da
Olist (e-commerce brasileiro, 2016-2018). Trabalho com spec-driven development:
a spec abaixo é a fonte da verdade e o código é consequência dela. Não
acrescente requisito que não esteja escrito aqui. Se algo estiver ambíguo,
pergunte antes de escrever código.

STACK
- Python 3.13, dependências gerenciadas com uv
- pandas para ler os arquivos
- DuckDB como banco, arquivo olist.duckdb na raiz do projeto
- Nenhum orquestrador. Script executável pela linha de comando.

O QUE JÁ EXISTE
Só a pasta raw/ com os nove .csv.gz e o pyproject.toml. Nenhum código ainda.

ARTEFATOS A PRODUZIR, nesta ordem
1. pipeline/db.py, o módulo de conexão que as quatro etapas do curso vão
   importar (spec própria logo abaixo; é a primeira coisa a existir)
2. pipeline/ingestao.py, executável com:
     uv run python -m pipeline.ingestao
3. ui.py, na raiz do projeto, executável com:
     uv run python ui.py
   (spec própria no fim deste prompt; ui.py e ingestao.py não se importam)

SPEC DO pipeline/db.py (primeiro artefato)
Expõe exatamente isto, com estes nomes:
  PASTA_RAW                          Path da pasta raw/ com os nove .csv.gz
  conectar()                         abre o olist.duckdb, criando se faltar
  criar_schema(con, nome)            CREATE SCHEMA IF NOT EXISTS
  gravar(con, df, schema, tabela)    grava e devolve a contagem lida do banco

D1. CAMINHOS
    PASTA_RAW e o olist.duckdb são resolvidos a partir da localização do
    próprio db.py (a pasta acima de pipeline/), nunca do diretório corrente.
    Motivo: rodar o script de outra pasta não pode criar um olist.duckdb
    vazio no lugar errado, que parece ingestão quebrada.
D2. TRÊS FUNÇÕES E UMA CONSTANTE, NADA MAIS
    db.py não lê CSV, não conhece nome de tabela, não imprime nada e não
    converte tipo. Quem decide tudo isso é cada etapa.
    Motivo: as aulas 2, 3 e 4 importam este arquivo. Regra de negócio
    escondida aqui vale para todas as etapas sem aparecer em nenhuma spec.
D3. gravar
    Recria a tabela (CREATE OR REPLACE TABLE schema.tabela) com as colunas
    e os tipos do DataFrame, sem alterar nada: coluna str vira VARCHAR,
    nulo continua NULL. Não deixa view ou tabela temporária para trás.
    Devolve SELECT count(*) da tabela recém-gravada, lido do banco.
    Motivo: a contagem que aparece na tela tem que ser a do que foi
    gravado, não a do que estava na memória.
D4. CONEXÃO
    conectar() devolve a conexão aberta; quem chama é quem fecha.
    db.py não guarda conexão global.

CRITÉRIOS DE ACEITE (db.py)
- Importar pipeline.db não abre banco nem cria arquivo nenhum.
- conectar() chamado de dentro de outra pasta cria o olist.duckdb na raiz
  do projeto, e não na pasta corrente.
- gravar() com um DataFrame de 3 linhas devolve 3, e rodar duas vezes
  continua devolvendo 3.

SPEC DA INGESTÃO (segundo artefato)

1. ESCOPO E NOMES
   Schema de destino: raw
   Mapa arquivo -> tabela, completo e literal:
     olist_orders_dataset.csv.gz               -> pedidos
     olist_order_items_dataset.csv.gz          -> itens_pedido
     olist_order_payments_dataset.csv.gz       -> pagamentos
     olist_order_reviews_dataset.csv.gz        -> avaliacoes
     olist_customers_dataset.csv.gz            -> clientes
     olist_sellers_dataset.csv.gz              -> vendedores
     olist_products_dataset.csv.gz             -> produtos
     product_category_name_translation.csv.gz  -> traducao_categorias
     olist_geolocation_dataset.csv.gz          -> geolocalizacao
   Os nomes vão para o português porque é o vocabulário que vou digitar de
   memória num JOIN nas próximas aulas.

2. PROIBIÇÕES (a regra central desta etapa)
   Nenhuma conversão de tipo. Nenhuma linha descartada ou deduplicada.
   Nenhum nome de coluna alterado. Nenhum valor corrigido, preenchido ou
   normalizado. Data continua texto, nulo continua nulo.
   Motivo: a fronteira entre "o dado que chegou" e "o dado que eu decidi"
   precisa existir em algum lugar, e esse lugar é a passagem de raw para
   refined, na etapa 2. Se a correção acontecer aqui, a fronteira some.

3. REEXECUÇÃO
   Rodar dez vezes tem que dar o mesmo resultado que rodar uma: a tabela é
   recriada (CREATE OR REPLACE), nunca acrescentada. É o que me deixa errar
   sem medo.

4. LEITURA DO ARQUIVO
   encoding declarado como utf-8, nunca adivinhado.
   Os .csv.gz são lidos direto, sem descompactar.
   Campo vazio continua virando nulo; não transforme em string vazia.

5. TIPAGEM
   Toda coluna entra como texto (dtype=str), inferência desligada.
   Motivo: inferência lê CEP com zero à esquerda como número e o zero
   desaparece sem aviso. A conversão acontece na etapa 2, onde é uma
   decisão registrada.

6. SAÍDA NA TELA
   Uma linha por tabela, com nome qualificado e contagem de linhas vinda do
   banco (não do DataFrame), milhar separado por ponto.
   Uma linha final com o total.
   Essa saída é meu único instrumento de conferência nesta etapa.
   O stdout precisa ser reconfigurado para utf-8: rodo no Prompt de Comando
   do Windows, onde acento sai embaralhado por padrão.

7. ERRO
   Antes de abrir o banco, verifique se os nove arquivos existem.
   Faltando qualquer um: liste os que faltam, diga em que pasta procurou e
   encerre com sys.exit(1). Não ingira parcialmente.
   Motivo: ingerir oito de nove tabelas em silêncio produz um dashboard
   errado que parece certo.

CRITÉRIOS DE ACEITE (ingestão)
- A execução imprime nove linhas e um total de 1.550.922 registros.
- Rodar duas vezes seguidas imprime exatamente a mesma coisa.
- SELECT * FROM raw.pedidos devolve todas as colunas como VARCHAR.
- Remover um arquivo da pasta faz o script parar antes de gravar qualquer
  tabela.
- O script termina sozinho e devolve o terminal: nenhum processo fica de pé.

SPEC DO ui.py (terceiro artefato)
Quero explorar o banco pelo navegador, em vez de ler tabela no terminal.

U1. O QUE FAZ
    Abre o olist.duckdb da raiz do projeto, instala e carrega a extensão
    `ui` do DuckDB (INSTALL ui; LOAD ui;) e chama CALL start_ui(), que sobe
    o servidor em http://localhost:4213 e abre o navegador.
U2. FICA DE PÉ ATÉ CTRL+C
    A extensão serve enquanto a conexão estiver viva. O script mantém o
    processo rodando, imprime a URL e a instrução "Ctrl+C para encerrar", e
    no Ctrl+C fecha a conexão e sai limpo, sem traceback.
    Motivo: o arquivo .duckdb aceita um único processo escrevendo. Com o
    ui.py de pé, a ingestão falha com "Could not set lock on file". Saber
    exatamente como desligar o servidor faz parte da ferramenta.
U3. NÃO CRIA BANCO
    Se olist.duckdb não existir, diga que é preciso rodar a ingestão antes
    e encerre com sys.exit(1). Por isso NÃO use conectar() de pipeline/db.py,
    que cria o arquivo quando ele falta: um banco vazio aberto no navegador
    parece ingestão quebrada.
U4. SEPARAÇÃO
    ui.py não importa pipeline/ingestao.py, e a ingestão não importa ui.py:
    a ingestão não sobe servidor, não abre navegador e não depende da
    extensão ui para rodar.
U5. SAÍDA NA TELA
    Mesma regra do item 6: stdout reconfigurado para utf-8.

CRITÉRIOS DE ACEITE (ui.py)
- uv run python ui.py abre o navegador em localhost:4213 e o schema raw
  aparece com as nove tabelas.
- Ctrl+C devolve o terminal sem traceback, e logo depois a ingestão roda
  sem erro de lock.
- Renomear olist.duckdb faz o ui.py parar com a mensagem, sem criar arquivo
  novo.

ENTREGA, nesta ordem, para cada um dos três arquivos
1. A spec como docstring no topo do arquivo, dizendo por que cada regra
   existe — não só o que ela manda fazer.
2. O código, com comentários apenas onde a decisão não é óbvia pelo código.
3. Uma lista final do que você assumiu e que não estava na spec. Se a lista
   não estiver vazia, é a minha spec que precisa melhorar.