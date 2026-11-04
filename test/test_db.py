"""Testes de pipeline/db.py: conexão, schema e gravação com CREATE OR REPLACE."""

import duckdb
import pandas as pd

from pipeline import db


def test_conectar_cria_o_banco_no_caminho_configurado(tmp_path, monkeypatch):
    caminho = tmp_path / "teste.duckdb"
    monkeypatch.setattr(db, "CAMINHO_BANCO", caminho)

    con = db.conectar()
    con.close()

    assert caminho.is_file()


def test_criar_schema_duas_vezes_nao_falha(tmp_path):
    con = duckdb.connect(str(tmp_path / "teste.duckdb"))

    db.criar_schema(con, "raw")
    db.criar_schema(con, "raw")  # IF NOT EXISTS: a segunda chamada não estoura

    schemas = con.execute(
        "SELECT count(*) FROM information_schema.schemata WHERE schema_name = 'raw'"
    ).fetchone()[0]
    con.close()
    assert schemas == 1


def test_gravar_devolve_a_contagem_do_banco(tmp_path):
    con = duckdb.connect(str(tmp_path / "teste.duckdb"))
    db.criar_schema(con, "raw")
    # três linhas quaisquer: o que importa é a contagem que volta
    df = pd.DataFrame({"id": ["a", "b", "c"]})

    linhas = db.gravar(con, df, "raw", "t")

    con.close()
    assert linhas == 3


def test_gravar_duas_vezes_recria_a_tabela_sem_acrescentar(tmp_path):
    con = duckdb.connect(str(tmp_path / "teste.duckdb"))
    db.criar_schema(con, "raw")
    df = pd.DataFrame({"id": ["a", "b"]})  # duas linhas, gravadas duas vezes

    db.gravar(con, df, "raw", "t")
    linhas = db.gravar(con, df, "raw", "t")

    con.close()
    assert linhas == 2  # seriam 4 se acrescentasse


def test_gravar_libera_o_dataframe_registrado(tmp_path):
    con = duckdb.connect(str(tmp_path / "teste.duckdb"))
    db.criar_schema(con, "raw")

    db.gravar(con, pd.DataFrame({"id": ["a"]}), "raw", "t")

    visoes = con.execute(
        "SELECT count(*) FROM duckdb_views() WHERE view_name = '_df'"
    ).fetchone()[0]
    con.close()
    assert visoes == 0
