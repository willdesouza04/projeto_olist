"""Transformação raw -> refined do dataset Olist para o DuckDB.

Executar com:  uv run python -m pipeline.transformacao

Fonte da verdade: pipeline/specs/transformacao.md. O resumo abaixo diz o que
cada regra manda e por que ela existe.

SPEC E MOTIVOS

1. Escopo
   Lê de raw, escreve em refined, nunca escreve em raw. Entram oito tabelas;
   geolocalizacao fica de fora porque nenhum mart do curso a usa, e não se
   limpa o que ninguém vai ler.

2. Nomes
   Colunas renomeadas para português, snake_case, pelo mapa literal em
   TABELAS. Nenhuma coluna fora do mapa, nenhuma descartada.
   Por quê: é o vocabulário que será digitado de memória nos JOINs da aula 3.

3. Tipos
   - Datas com hora: TIMESTAMP, formato declarado '%Y-%m-%d %H:%M:%S'.
   - data_entrega_prevista: DATE. A hora é sempre 00:00:00 nas 99.441
     linhas; guardar a hora seria inventar precisão.
   - data_criacao: DATE. A hora é 00:00:00 em 99.139 avaliações e 01:00:00
     nas outras 85, efeito de horário de verão e não horário de verdade.
   - Dinheiro (preco, frete, valor): DECIMAL(10,2). DOUBLE não representa
     centavos com exatidão, e soma de dinheiro tem que fechar.
   - Contagens e medidas: INTEGER.
   - O resto continua VARCHAR, inclusive cep_prefixo: 23.995 clientes têm
     CEP começando com zero, CEP é identificador e como número perderia o
     zero.
   A conversão roda em SQL no DuckDB, disparada pelo Python: o dado já está
   no banco, não há por que trazê-lo para a memória só para converter tipo.

4. Conversão que falha
   Para tudo. A conversão usa strptime e CAST, que estouram, nunca
   try_strptime/TRY_CAST, que transformam falha em nulo. Ao falhar, diz
   tabela, coluna e um exemplo do valor e encerra com sys.exit(1).
   Por quê: um nulo fabricado pela conversão fica indistinguível de um nulo
   verdadeiro do dado, para sempre.
   As versões try_* aparecem só no diagnóstico, depois que a conversão
   estrita já falhou, para achar a coluna e o valor culpados (o erro do
   DuckDB não diz a coluna). Elas nunca produzem dado gravado.

5. Duplicatas
   Linha inteira repetida (comparada em raw, antes da conversão): mantém
   uma e conta quantas saíram. Chave repetida com conteúdo diferente: para,
   mostra a chave e as linhas conflitantes, sys.exit(1).
   Por quê: escolher uma em silêncio é decidir sem dizer que decidiu.
   avaliacoes tem chave (avaliacao_id, pedido_id) porque o mesmo
   avaliacao_id aparece em mais de um pedido.

6. Nulos
   Nenhuma linha apagada por ter nulo, nenhum nulo preenchido. O nulo é
   informação (pedido cancelado não tem data de entrega), e anomalias de
   negócio (delivered sem data_entrega, envio antes da compra, pedido com
   mais de uma avaliação) ficam: refined não corrige fato, quem decide é o
   mart.

7. Saída na tela
   Uma linha por tabela (entram -> saem, duplicatas) e, abaixo, as colunas
   com nulo e a contagem. Contagens vindas do banco, milhar com ponto,
   linha final com o total. stdout em utf-8 pelo mesmo motivo da ingestão.

REEXECUÇÃO
   CREATE OR REPLACE TABLE, nunca acrescenta. Rodar dez vezes = rodar uma.

ERRO
   Antes de transformar, confere se as oito tabelas existem em raw. Faltando
   alguma: lista quais, manda rodar a ingestão e sys.exit(1).
   Todas as tabelas são convertidas e validadas antes de qualquer gravação
   em refined, então uma falha não deixa refined pela metade.

CRITÉRIOS DE ACEITE
- Oito tabelas em refined, linhas que saem = linhas que entram (0
  duplicatas com este dado). Total: 550.759.
- DESCRIBE refined.pedidos: TIMESTAMP nas cinco datas com hora, DATE em
  data_entrega_prevista.
- Nulos depois = nulos antes, coluna por coluna.
- sum(preco) em refined.itens_pedido = sum(CAST(price AS DECIMAL)) em raw.
- cep_prefixo mantém o zero à esquerda.
- Rodar duas vezes seguidas imprime exatamente a mesma coisa.
"""

import sys

import duckdb

from pipeline.db import conectar, criar_schema

ORIGEM = "raw"
DESTINO = "refined"

# tipo -> (expressão estrita, expressão tolerante usada só no diagnóstico)
CONVERSOES = {
    "texto": ("{c}", None),
    "inteiro": ("CAST({c} AS INTEGER)", "TRY_CAST({c} AS INTEGER)"),
    "dinheiro": ("CAST({c} AS DECIMAL(10,2))", "TRY_CAST({c} AS DECIMAL(10,2))"),
    "timestamp": (
        "strptime({c}, '%Y-%m-%d %H:%M:%S')",
        "try_strptime({c}, '%Y-%m-%d %H:%M:%S')",
    ),
    "data": (
        "CAST(strptime({c}, '%Y-%m-%d %H:%M:%S') AS DATE)",
        "CAST(try_strptime({c}, '%Y-%m-%d %H:%M:%S') AS DATE)",
    ),
}

# tabela -> chave (nomes novos) e colunas (origem, destino, tipo), na ordem
TABELAS = {
    "pedidos": {
        "chave": ["pedido_id"],
        "colunas": [
            ("order_id", "pedido_id", "texto"),
            ("customer_id", "cliente_id", "texto"),
            ("order_status", "status", "texto"),
            ("order_purchase_timestamp", "data_compra", "timestamp"),
            ("order_approved_at", "data_aprovacao", "timestamp"),
            ("order_delivered_carrier_date", "data_envio", "timestamp"),
            ("order_delivered_customer_date", "data_entrega", "timestamp"),
            ("order_estimated_delivery_date", "data_entrega_prevista", "data"),
        ],
    },
    "itens_pedido": {
        "chave": ["pedido_id", "item_seq"],
        "colunas": [
            ("order_id", "pedido_id", "texto"),
            ("order_item_id", "item_seq", "inteiro"),
            ("product_id", "produto_id", "texto"),
            ("seller_id", "vendedor_id", "texto"),
            ("shipping_limit_date", "data_limite_envio", "timestamp"),
            ("price", "preco", "dinheiro"),
            ("freight_value", "frete", "dinheiro"),
        ],
    },
    "pagamentos": {
        "chave": ["pedido_id", "pagamento_seq"],
        "colunas": [
            ("order_id", "pedido_id", "texto"),
            ("payment_sequential", "pagamento_seq", "inteiro"),
            ("payment_type", "tipo", "texto"),
            ("payment_installments", "parcelas", "inteiro"),
            ("payment_value", "valor", "dinheiro"),
        ],
    },
    "clientes": {
        "chave": ["cliente_id"],
        "colunas": [
            ("customer_id", "cliente_id", "texto"),
            ("customer_unique_id", "cliente_unico_id", "texto"),
            ("customer_zip_code_prefix", "cep_prefixo", "texto"),
            ("customer_city", "cidade", "texto"),
            ("customer_state", "uf", "texto"),
        ],
    },
    "vendedores": {
        "chave": ["vendedor_id"],
        "colunas": [
            ("seller_id", "vendedor_id", "texto"),
            ("seller_zip_code_prefix", "cep_prefixo", "texto"),
            ("seller_city", "cidade", "texto"),
            ("seller_state", "uf", "texto"),
        ],
    },
    "produtos": {
        "chave": ["produto_id"],
        "colunas": [
            ("product_id", "produto_id", "texto"),
            ("product_category_name", "categoria", "texto"),
            ("product_name_lenght", "tamanho_nome", "inteiro"),
            ("product_description_lenght", "tamanho_descricao", "inteiro"),
            ("product_photos_qty", "qtd_fotos", "inteiro"),
            ("product_weight_g", "peso_g", "inteiro"),
            ("product_length_cm", "comprimento_cm", "inteiro"),
            ("product_height_cm", "altura_cm", "inteiro"),
            ("product_width_cm", "largura_cm", "inteiro"),
        ],
    },
    "traducao_categorias": {
        "chave": ["categoria"],
        "colunas": [
            ("product_category_name", "categoria", "texto"),
            ("product_category_name_english", "categoria_en", "texto"),
        ],
    },
    "avaliacoes": {
        "chave": ["avaliacao_id", "pedido_id"],
        "colunas": [
            ("review_id", "avaliacao_id", "texto"),
            ("order_id", "pedido_id", "texto"),
            ("review_score", "nota", "inteiro"),
            ("review_comment_title", "titulo", "texto"),
            ("review_comment_message", "comentario", "texto"),
            ("review_creation_date", "data_criacao", "data"),
            ("review_answer_timestamp", "data_resposta", "timestamp"),
        ],
    },
}

LARGURA_NOME = max(len(f"{DESTINO}.{t}") for t in TABELAS) + 2


def formatar_milhar(n: int) -> str:
    return f"{n:,}".replace(",", ".")


def tabelas_faltando(con: duckdb.DuckDBPyConnection) -> list[str]:
    existentes = {
        nome
        for (nome,) in con.execute(
            "SELECT table_name FROM information_schema.tables WHERE table_schema = ?",
            [ORIGEM],
        ).fetchall()
    }
    return [t for t in TABELAS if t not in existentes]


def montar_select(tabela: str) -> str:
    expressoes = ",\n    ".join(
        f"{CONVERSOES[tipo][0].format(c=origem)} AS {destino}"
        for origem, destino, tipo in TABELAS[tabela]["colunas"]
    )
    # DISTINCT antes da conversão: "linha repetida" é comparada no dado que chegou.
    return (
        f'SELECT\n    {expressoes}\nFROM (SELECT DISTINCT * FROM "{ORIGEM}"."{tabela}")'
    )


def achar_falha(
    con: duckdb.DuckDBPyConnection, tabela: str
) -> tuple[str, str, str] | None:
    """Devolve (coluna de origem, coluna de destino, valor) do primeiro valor que não converte."""
    for origem, destino, tipo in TABELAS[tabela]["colunas"]:
        tolerante = CONVERSOES[tipo][1]
        if tolerante is None:
            continue
        linha = con.execute(
            f'SELECT {origem} FROM "{ORIGEM}"."{tabela}" '
            f"WHERE {origem} IS NOT NULL AND {tolerante.format(c=origem)} IS NULL LIMIT 1"
        ).fetchone()
        if linha:
            return origem, destino, linha[0]
    return None


def preparar(con: duckdb.DuckDBPyConnection, tabela: str) -> str:
    """Converte e valida numa tabela temporária; devolve o nome dela."""
    temporaria = f"_refined_{tabela}"
    try:
        con.execute(
            f'CREATE OR REPLACE TEMP TABLE "{temporaria}" AS {montar_select(tabela)}'
        )
    except (
        duckdb.ConversionException,
        duckdb.InvalidInputException,
        duckdb.OutOfRangeException,
    ):
        falha = achar_falha(con, tabela)
        if falha is None:
            raise
        origem, destino, valor = falha
        print(
            f"Conversão falhou em {ORIGEM}.{tabela}, coluna {origem} (-> {destino}): "
            f"valor {valor!r} não converte.",
            file=sys.stderr,
        )
        print(f"Nada foi gravado em {DESTINO}.", file=sys.stderr)
        sys.exit(1)

    chave = ", ".join(TABELAS[tabela]["chave"])
    repetidas = (
        f'SELECT {chave} FROM "{temporaria}" GROUP BY {chave} HAVING count(*) > 1'
    )
    n_chaves = con.execute(f"SELECT count(*) FROM ({repetidas})").fetchone()[0]
    if n_chaves:
        conflitantes = con.execute(
            f'SELECT t.* FROM "{temporaria}" t JOIN ({repetidas}) USING ({chave}) '
            f"ORDER BY {chave} LIMIT 20"
        ).df()
        print(
            f"{DESTINO}.{tabela}: {formatar_milhar(n_chaves)} chave(s) ({chave}) "
            "repetida(s) com conteúdo diferente. Primeiras linhas conflitantes:",
            file=sys.stderr,
        )
        print(conflitantes.to_string(index=False), file=sys.stderr)
        print(f"Nada foi gravado em {DESTINO}.", file=sys.stderr)
        sys.exit(1)
    return temporaria


def contar(con: duckdb.DuckDBPyConnection, schema: str, tabela: str) -> int:
    return con.execute(f'SELECT count(*) FROM "{schema}"."{tabela}"').fetchone()[0]


def nulos(con: duckdb.DuckDBPyConnection, tabela: str) -> list[tuple[str, int]]:
    cursor = con.execute(
        f'SELECT count(*) - count(COLUMNS(*)) FROM "{DESTINO}"."{tabela}"'
    )
    colunas = [d[0] for d in cursor.description]
    return [(c, n) for c, n in zip(colunas, cursor.fetchone()) if n]


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")

    con = conectar()
    try:
        faltando = tabelas_faltando(con)
        if faltando:
            print(f"Tabelas ausentes no schema {ORIGEM}:", file=sys.stderr)
            for tabela in faltando:
                print(f"  - {tabela}", file=sys.stderr)
            print('Rode antes: "uv run python -m pipeline.ingestao"', file=sys.stderr)
            sys.exit(1)

        # Tudo convertido e validado antes de gravar: falha não deixa refined pela metade.
        temporarias = {tabela: preparar(con, tabela) for tabela in TABELAS}

        criar_schema(con, DESTINO)
        total_entram = total_saem = 0
        for tabela, temporaria in temporarias.items():
            con.execute(
                f'CREATE OR REPLACE TABLE "{DESTINO}"."{tabela}" AS FROM "{temporaria}"'
            )
            entram = contar(con, ORIGEM, tabela)
            saem = contar(con, DESTINO, tabela)
            total_entram += entram
            total_saem += saem
            print(
                f"{f'{DESTINO}.{tabela}':<{LARGURA_NOME}}"
                f"{formatar_milhar(entram)} -> {formatar_milhar(saem)} linhas  "
                f"({formatar_milhar(entram - saem)} duplicatas)"
            )
            com_nulo = nulos(con, tabela)
            if com_nulo:
                lista = ", ".join(f"{c} {formatar_milhar(n)}" for c, n in com_nulo)
                print(f"    nulos mantidos: {lista}")
        print(
            f"Total: {formatar_milhar(total_entram)} -> {formatar_milhar(total_saem)} linhas  "
            f"({formatar_milhar(total_entram - total_saem)} duplicatas)"
        )
    finally:
        # Libera o lock do arquivo mesmo se algo falhar no meio.
        con.close()


if __name__ == "__main__":
    main()
