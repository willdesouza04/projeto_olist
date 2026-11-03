"""Construção de marts analíticos a partir de templates SQL.

Executar com:  uv run python -m pipeline.marts

SPEC E MOTIVOS

1. ESCOPO
   Lê de refined, escreve no schema marts. Nunca escreve em raw nem em refined.
   O schema marts é apagado e recriado a cada execução (DROP SCHEMA IF
   EXISTS marts CASCADE). Motivo: um mart cujo arquivo foi apagado não pode
   continuar existindo no banco.

2. UM ARQUIVO, UMA TABELA
   Lê todos os sql/marts/*.sql em ordem alfabética.
   Nome da tabela = nome do arquivo sem a extensão e sem o prefixo numérico:
     sql/marts/01_vendas_mensais.sql -> marts.vendas_mensais
   Executa: CREATE TABLE marts.<nome> AS <conteúdo do arquivo>
   Tira espaços e um ponto e vírgula do final do conteúdo, e nada mais.
   O Python não altera, não monta e não completa a SQL.
   Motivo: a regra de negócio mora inteira no arquivo .sql.

3. SAÍDA NA TELA
   Uma linha por mart, com a contagem vinda do banco, milhar com ponto:
     ✓ marts.vendas_mensais        24 linhas
   Linha final com o número de marts e o total de linhas.
   stdout reconfigurado para utf-8.

4. ERRO
   Antes de tudo: se faltar qualquer uma das oito tabelas em refined,
   lista quais, diz para rodar "uv run python -m pipeline.transformacao"
   e encerra com sys.exit(1).
   Se um .sql falhar: mostra o nome do arquivo e a mensagem do DuckDB,
   não executa os seguintes, sys.exit(1).
   Se um mart voltar com zero linhas: mostra o nome e encerra com
   sys.exit(1). Motivo: mart vazio é quase sempre um JOIN que não casou,
   e um dashboard vazio parece um negócio parado.
   Se sql/marts/ não tiver nenhum arquivo: avisa e sys.exit(1).
   Antes de executar qualquer SQL: arquivo sem prefixo NN_ ou dois
   arquivos que dão o mesmo nome de tabela -> lista quais e sys.exit(1).
   Tudo roda numa transação só: se qualquer passo falhar (inclusive o
   mart vazio), o schema marts volta a ser o da última execução que deu
   certo. Motivo: um schema pela metade quebra o dashboard sem avisar.

CRITÉRIOS DE ACEITE
- Com um arquivo sql/marts/00_teste.sql contendo "SELECT 1 AS x", cria
  marts.teste com 1 linha.
- Apagar o arquivo e rodar de novo faz marts.teste desaparecer.
- Um arquivo com erro de sintaxe para tudo, com o nome do arquivo na tela,
  e marts continua exatamente como estava antes da execução.
- Um arquivo teste.sql, sem prefixo, para antes de executar qualquer SQL.
- Rodar duas vezes seguidas imprime exatamente a mesma coisa.
"""

import sys
from pathlib import Path
import re

import duckdb

from pipeline.db import conectar, criar_schema

RAIZ = Path(__file__).resolve().parent.parent
PASTA_MARTS = RAIZ / "sql" / "marts"
SCHEMA_ORIGEM = "refined"
SCHEMA_DESTINO = "marts"
TABELAS_ESPERADAS = {
    "pedidos",
    "itens_pedido",
    "pagamentos",
    "clientes",
    "vendedores",
    "produtos",
    "traducao_categorias",
    "avaliacoes",
}

LARGURA_NOME = 30


def formatar_milhar(n: int) -> str:
    return f"{n:,}".replace(",", ".")


def tabelas_faltando(con: duckdb.DuckDBPyConnection) -> set[str]:
    existentes = {
        nome
        for (nome,) in con.execute(
            "SELECT table_name FROM information_schema.tables WHERE table_schema = ?",
            [SCHEMA_ORIGEM],
        ).fetchall()
    }
    return TABELAS_ESPERADAS - existentes


def descobrir_marts() -> list[Path]:
    if not PASTA_MARTS.exists():
        print(f"Pasta {PASTA_MARTS} não existe.", file=sys.stderr)
        sys.exit(1)

    arquivos = sorted(PASTA_MARTS.glob("*.sql"))
    if not arquivos:
        print(f"Nenhum arquivo .sql em {PASTA_MARTS}.", file=sys.stderr)
        sys.exit(1)

    return arquivos


def validar_nomes(arquivos: list[Path]) -> None:
    """Valida que todos têm prefixo NN_ e que não há conflitos de nome."""
    invalidos = []
    nomes_tabela = {}

    for arquivo in arquivos:
        nome_arquivo = arquivo.name
        match = re.match(r"^(\d{2})_(.+)\.sql$", nome_arquivo)

        if not match:
            invalidos.append(arquivo.name)
            continue

        nome_tabela = match.group(2)
        if nome_tabela in nomes_tabela:
            print(
                f"Conflito: dois arquivos criam a tabela {SCHEMA_DESTINO}.{nome_tabela}:",
                file=sys.stderr,
            )
            print(f"  - {nomes_tabela[nome_tabela]}", file=sys.stderr)
            print(f"  - {arquivo.name}", file=sys.stderr)
            sys.exit(1)
        nomes_tabela[nome_tabela] = arquivo.name

    if invalidos:
        print(
            f"Arquivos sem prefixo NN_ em {PASTA_MARTS}:",
            file=sys.stderr,
        )
        for nome in invalidos:
            print(f"  - {nome}", file=sys.stderr)
        sys.exit(1)


def extrair_nome_tabela(arquivo: Path) -> str:
    """Extrai o nome da tabela do arquivo (sem NN_ e sem .sql)."""
    match = re.match(r"^(\d{2})_(.+)\.sql$", arquivo.name)
    return match.group(2)


def ler_conteudo_sql(arquivo: Path) -> str:
    """Lê conteúdo, tira espaços em branco do final e ponto e vírgula."""
    conteudo = arquivo.read_text(encoding="utf-8")
    conteudo = conteudo.rstrip()
    if conteudo.endswith(";"):
        conteudo = conteudo[:-1].rstrip()
    return conteudo


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")

    con = conectar()
    try:
        faltando = tabelas_faltando(con)
        if faltando:
            print(f"Tabelas ausentes no schema {SCHEMA_ORIGEM}:", file=sys.stderr)
            for tabela in sorted(faltando):
                print(f"  - {tabela}", file=sys.stderr)
            print(
                'Rode antes: "uv run python -m pipeline.transformacao"',
                file=sys.stderr,
            )
            sys.exit(1)

        arquivos = descobrir_marts()
        validar_nomes(arquivos)

        # Inicia transação
        con.begin()
        try:
            con.execute(f"DROP SCHEMA IF EXISTS {SCHEMA_DESTINO} CASCADE")
            criar_schema(con, SCHEMA_DESTINO)

            total_linhas = 0
            for arquivo in arquivos:
                nome_tabela = extrair_nome_tabela(arquivo)
                conteudo_sql = ler_conteudo_sql(arquivo)

                try:
                    con.execute(
                        f'CREATE TABLE "{SCHEMA_DESTINO}"."{nome_tabela}" AS {conteudo_sql}'
                    )
                except Exception as e:
                    print(f"Erro em {arquivo.name}: {e}", file=sys.stderr)
                    con.rollback()
                    sys.exit(1)

                # Verifica se mart ficou vazio
                contagem = con.execute(
                    f'SELECT count(*) FROM "{SCHEMA_DESTINO}"."{nome_tabela}"'
                ).fetchone()[0]

                if contagem == 0:
                    print(
                        f"Mart vazio: {SCHEMA_DESTINO}.{nome_tabela}",
                        file=sys.stderr,
                    )
                    con.rollback()
                    sys.exit(1)

                total_linhas += contagem
                nome_qualificado = f"{SCHEMA_DESTINO}.{nome_tabela}"
                print(
                    f"✓ {nome_qualificado:<{LARGURA_NOME}} {formatar_milhar(contagem)} linhas"
                )

            con.commit()
            print(
                f"Total: {len(arquivos)} mart(s), {formatar_milhar(total_linhas)} linhas"
            )

        except Exception:
            con.rollback()
            raise

    finally:
        con.close()


if __name__ == "__main__":
    main()
