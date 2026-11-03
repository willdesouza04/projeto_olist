"""Ingestão raw do dataset Olist para o DuckDB.

Executar com:  uv run python -m pipeline.ingestao

SPEC E MOTIVOS

1. Escopo e nomes
   Schema de destino: raw. Nove arquivos, nove tabelas, mapa literal em
   ARQUIVOS. Os nomes vão para o português porque é o vocabulário que será
   digitado de memória em JOINs nas próximas aulas.

2. Proibições (regra central da etapa)
   Nenhuma conversão de tipo, nenhuma linha descartada ou deduplicada,
   nenhum nome de coluna alterado, nenhum valor corrigido, preenchido ou
   normalizado. Data continua texto, nulo continua nulo.
   Por quê: a fronteira entre "o dado que chegou" e "o dado que eu decidi"
   precisa existir em algum lugar, e esse lugar é a passagem de raw para
   refined (etapa 2). Se a correção acontecer aqui, a fronteira some.

3. Reexecução
   Rodar dez vezes dá o mesmo resultado que rodar uma: a tabela é recriada
   (CREATE OR REPLACE), nunca acrescentada. Por quê: é o que permite errar
   sem medo.

4. Leitura do arquivo
   encoding declarado como utf-8, nunca adivinhado. Os .csv.gz são lidos
   direto, sem descompactar. Campo vazio continua virando nulo, não string
   vazia.

5. Tipagem
   Toda coluna entra como texto (dtype=str), inferência desligada.
   Por quê: a inferência lê CEP com zero à esquerda como número e o zero
   desaparece sem aviso. A conversão acontece na etapa 2, onde é uma
   decisão registrada.

6. Saída na tela
   Uma linha por tabela, com nome qualificado e contagem vinda do banco (não
   do DataFrame), milhar separado por ponto, e uma linha final com o total.
   Por quê: é o único instrumento de conferência desta etapa. O stdout é
   reconfigurado para utf-8 porque o Prompt de Comando do Windows embaralha
   acentos por padrão.

7. Erro
   Antes de abrir o banco, verifica se os nove arquivos existem. Faltando
   qualquer um: lista os que faltam, diz em que pasta procurou e encerra com
   sys.exit(1). Não ingere parcialmente.
   Por quê: ingerir oito de nove tabelas em silêncio produz um dashboard
   errado que parece certo.

CRITÉRIOS DE ACEITE
- A execução imprime nove linhas e um total de 1.550.922 registros.
- Rodar duas vezes seguidas imprime exatamente a mesma coisa.
- SELECT * FROM raw.pedidos devolve todas as colunas como VARCHAR.
- Remover um arquivo da pasta faz o script parar antes de gravar qualquer
  tabela.
- O script termina sozinho e devolve o terminal.

SEPARAÇÃO
Este módulo não sobe servidor, não abre navegador e não importa ui.py.
"""

import sys

import pandas as pd

from pipeline.db import PASTA_RAW, conectar, criar_schema, gravar

SCHEMA = "raw"

ARQUIVOS = {
    "olist_orders_dataset.csv.gz": "pedidos",
    "olist_order_items_dataset.csv.gz": "itens_pedido",
    "olist_order_payments_dataset.csv.gz": "pagamentos",
    "olist_order_reviews_dataset.csv.gz": "avaliacoes",
    "olist_customers_dataset.csv.gz": "clientes",
    "olist_sellers_dataset.csv.gz": "vendedores",
    "olist_products_dataset.csv.gz": "produtos",
    "product_category_name_translation.csv.gz": "traducao_categorias",
    "olist_geolocation_dataset.csv.gz": "geolocalizacao",
}


def formatar_milhar(n: int) -> str:
    return f"{n:,}".replace(",", ".")


def arquivos_faltando() -> list[str]:
    return [nome for nome in ARQUIVOS if not (PASTA_RAW / nome).is_file()]


def ler_csv(nome_arquivo: str) -> pd.DataFrame:
    return pd.read_csv(
        PASTA_RAW / nome_arquivo,
        dtype=str,  # nada de inferência: zero à esquerda do CEP sobrevive
        encoding="utf-8",
        compression="gzip",
        # Sem isto o pandas trata strings como "NA", "null" ou "nan" como
        # nulo, o que seria corrigir valor. Só o campo vazio vira nulo.
        keep_default_na=False,
        na_values=[""],
    )


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")

    faltando = arquivos_faltando()
    if faltando:
        print(f"Arquivos ausentes em {PASTA_RAW}:", file=sys.stderr)
        for nome in faltando:
            print(f"  - {nome}", file=sys.stderr)
        print("Nada foi ingerido.", file=sys.stderr)
        sys.exit(1)

    con = conectar()
    try:
        criar_schema(con, SCHEMA)
        total = 0
        for arquivo, tabela in ARQUIVOS.items():
            df = ler_csv(arquivo)
            linhas = gravar(con, df, SCHEMA, tabela)
            total += linhas
            print(f"{SCHEMA}.{tabela}: {formatar_milhar(linhas)}")
        print(f"Total: {formatar_milhar(total)}")
    finally:
        # Libera o lock do arquivo mesmo se algo falhar no meio.
        con.close()


if __name__ == "__main__":
    main()