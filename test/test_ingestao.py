"""Testes de pipeline/ingestao.py com CSVs .csv.gz inventados em tmp_path."""

import gzip
import io
import sys

import duckdb
import pytest

from pipeline import db, ingestao

# Conteúdo de cada arquivo inventado. Os de clientes e pedidos têm casos
# específicos; os demais só precisam existir com algumas linhas.
CSV_CLIENTES = (
    "customer_id,customer_zip_code_prefix,customer_city\n"
    "c1,01310,sao paulo\n"  # CEP com zero à esquerda: tem que sobreviver como texto
    "c2,NA,NA\n"  # texto "NA" não é nulo: a ingestão não corrige valor
    "c3,,rio\n"  # campo vazio: vira nulo
)
CSV_PEDIDOS = (
    "order_id,order_status,order_purchase_timestamp\n"
    "p1,delivered,2024-01-10 08:00:00\n"  # data continua texto em raw
    "p1,delivered,2024-01-10 08:00:00\n"  # linha duplicada: raw não deduplica
)
CSV_GENERICO = "id,valor\n1,10\n2,20\n"  # duas linhas quaisquer


def escrever_csvs(pasta, faltando=None):
    pasta.mkdir()
    for nome in ingestao.ARQUIVOS:
        if nome == faltando:
            continue
        if nome == "olist_customers_dataset.csv.gz":
            conteudo = CSV_CLIENTES
        elif nome == "olist_orders_dataset.csv.gz":
            conteudo = CSV_PEDIDOS
        else:
            conteudo = CSV_GENERICO
        with gzip.open(pasta / nome, "wt", encoding="utf-8", newline="") as f:
            f.write(conteudo)


def preparar(tmp_path, monkeypatch, faltando=None):
    pasta = tmp_path / "raw"
    escrever_csvs(pasta, faltando)
    banco = tmp_path / "teste.duckdb"
    monkeypatch.setattr(ingestao, "PASTA_RAW", pasta)
    monkeypatch.setattr(db, "CAMINHO_BANCO", banco)
    return banco


def rodar(monkeypatch):
    """Roda main() e devolve o que ela imprimiu no stdout."""
    saida = io.TextIOWrapper(io.BytesIO(), encoding="utf-8")
    monkeypatch.setattr(sys, "stdout", saida)
    ingestao.main()
    saida.flush()
    return saida.buffer.getvalue().decode("utf-8")


def test_formatar_milhar_separa_com_ponto():
    assert ingestao.formatar_milhar(1234567) == "1.234.567"


def test_formatar_milhar_abaixo_de_mil_fica_igual():
    assert ingestao.formatar_milhar(999) == "999"


def test_csv_vira_tabela_com_as_mesmas_linhas(tmp_path, monkeypatch):
    banco = preparar(tmp_path, monkeypatch)

    rodar(monkeypatch)

    con = duckdb.connect(str(banco))
    clientes = con.execute("SELECT count(*) FROM raw.clientes").fetchone()[0]
    pedidos = con.execute("SELECT count(*) FROM raw.pedidos").fetchone()[0]
    vendedores = con.execute("SELECT count(*) FROM raw.vendedores").fetchone()[0]
    con.close()
    assert clientes == 3
    assert pedidos == 2  # a duplicata continua lá
    assert vendedores == 2


def test_cria_as_nove_tabelas_no_schema_raw(tmp_path, monkeypatch):
    banco = preparar(tmp_path, monkeypatch)

    rodar(monkeypatch)

    con = duckdb.connect(str(banco))
    tabelas = {
        t
        for (t,) in con.execute(
            "SELECT table_name FROM information_schema.tables WHERE table_schema = 'raw'"
        ).fetchall()
    }
    con.close()
    assert tabelas == set(ingestao.ARQUIVOS.values())


def test_todas_as_colunas_entram_como_varchar(tmp_path, monkeypatch):
    banco = preparar(tmp_path, monkeypatch)

    rodar(monkeypatch)

    con = duckdb.connect(str(banco))
    tipos = {
        tipo
        for (tipo,) in con.execute(
            "SELECT data_type FROM information_schema.columns WHERE table_schema = 'raw'"
        ).fetchall()
    }
    con.close()
    assert tipos == {"VARCHAR"}


def test_cep_com_zero_a_esquerda_sobrevive(tmp_path, monkeypatch):
    banco = preparar(tmp_path, monkeypatch)

    rodar(monkeypatch)

    con = duckdb.connect(str(banco))
    cep = con.execute(
        "SELECT customer_zip_code_prefix FROM raw.clientes WHERE customer_id = 'c1'"
    ).fetchone()[0]
    con.close()
    assert cep == "01310"


def test_texto_na_continua_texto_e_campo_vazio_vira_nulo(tmp_path, monkeypatch):
    banco = preparar(tmp_path, monkeypatch)

    rodar(monkeypatch)

    con = duckdb.connect(str(banco))
    cep_na = con.execute(
        "SELECT customer_zip_code_prefix FROM raw.clientes WHERE customer_id = 'c2'"
    ).fetchone()[0]
    cep_vazio = con.execute(
        "SELECT customer_zip_code_prefix FROM raw.clientes WHERE customer_id = 'c3'"
    ).fetchone()[0]
    con.close()
    assert cep_na == "NA"
    assert cep_vazio is None


def test_imprime_uma_linha_por_tabela_e_o_total(tmp_path, monkeypatch):
    preparar(tmp_path, monkeypatch)

    saida = rodar(monkeypatch)

    linhas = saida.splitlines()
    assert len(linhas) == 10
    assert "raw.clientes: 3" in linhas
    # 3 clientes + 2 pedidos + 7 arquivos genéricos de 2 linhas = 19
    assert linhas[-1] == "Total: 19"


def test_rodar_duas_vezes_imprime_a_mesma_coisa(tmp_path, monkeypatch):
    preparar(tmp_path, monkeypatch)

    primeira = rodar(monkeypatch)
    segunda = rodar(monkeypatch)

    assert primeira == segunda


def test_arquivo_faltando_encerra_com_systemexit(tmp_path, monkeypatch):
    preparar(tmp_path, monkeypatch, faltando="olist_sellers_dataset.csv.gz")

    with pytest.raises(SystemExit) as erro:
        rodar(monkeypatch)

    assert erro.value.code == 1


def test_arquivo_faltando_para_antes_de_abrir_o_banco(tmp_path, monkeypatch):
    banco = preparar(tmp_path, monkeypatch, faltando="olist_sellers_dataset.csv.gz")

    with pytest.raises(SystemExit):
        rodar(monkeypatch)

    assert not banco.exists()  # nenhuma tabela gravada, nem o arquivo criado


def test_arquivos_faltando_lista_so_o_ausente(tmp_path, monkeypatch):
    preparar(tmp_path, monkeypatch, faltando="olist_sellers_dataset.csv.gz")

    assert ingestao.arquivos_faltando() == ["olist_sellers_dataset.csv.gz"]
