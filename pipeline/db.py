"""Acesso ao DuckDB compartilhado pelas etapas do pipeline."""

from pathlib import Path

import duckdb
import pandas as pd

RAIZ = Path(__file__).resolve().parent.parent
PASTA_RAW = RAIZ / "raw"
CAMINHO_BANCO = RAIZ / "olist.duckdb"


def conectar() -> duckdb.DuckDBPyConnection:
    return duckdb.connect(str(CAMINHO_BANCO))


def criar_schema(con: duckdb.DuckDBPyConnection, schema: str) -> None:
    con.execute(f'CREATE SCHEMA IF NOT EXISTS "{schema}"')


def gravar(
    con: duckdb.DuckDBPyConnection, df: pd.DataFrame, schema: str, tabela: str
) -> int:
    """Recria a tabela com o conteúdo do DataFrame e devolve a contagem do banco."""
    nome = f'"{schema}"."{tabela}"'
    con.register("_df", df)
    try:
        # CREATE OR REPLACE: reexecutar recria, nunca acrescenta.
        con.execute(f"CREATE OR REPLACE TABLE {nome} AS SELECT * FROM _df")
    finally:
        con.unregister("_df")
    return con.execute(f"SELECT count(*) FROM {nome}").fetchone()[0]
