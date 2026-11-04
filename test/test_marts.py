"""Testes de pipeline/marts.py e das regras de sql/marts/01 e 03.

O runner roda sobre uma pasta de .sql inventada em tmp_path. Os arquivos
01 e 03 do projeto rodam sobre tabelas refined inventadas.
"""

import io
import sys
from datetime import date
from decimal import Decimal

import duckdb
import pytest

from pipeline import db, marts

PASTA_SQL_PROJETO = marts.PASTA_MARTS  # lido antes de qualquer monkeypatch


def criar_refined_vazio(banco):
    """As oito tabelas que o runner exige, sem linha nenhuma."""
    con = duckdb.connect(str(banco))
    con.execute("CREATE SCHEMA refined")
    for tabela in marts.TABELAS_ESPERADAS:
        con.execute(f"CREATE TABLE refined.{tabela} (x INTEGER)")
    con.close()


def preparar(tmp_path, monkeypatch, arquivos):
    """Banco com refined pronto e pasta de marts com `arquivos` {nome: sql}."""
    banco = tmp_path / "teste.duckdb"
    criar_refined_vazio(banco)
    pasta = tmp_path / "marts"
    pasta.mkdir()
    for nome, sql in arquivos.items():
        (pasta / nome).write_text(sql, encoding="utf-8")
    monkeypatch.setattr(db, "CAMINHO_BANCO", banco)
    monkeypatch.setattr(marts, "PASTA_MARTS", pasta)
    return banco, pasta


def rodar(monkeypatch):
    """Roda main() e devolve o que ela imprimiu no stdout."""
    saida = io.TextIOWrapper(io.BytesIO(), encoding="utf-8")
    monkeypatch.setattr(sys, "stdout", saida)
    marts.main()
    saida.flush()
    return saida.buffer.getvalue().decode("utf-8")


def tabelas_marts(banco):
    con = duckdb.connect(str(banco))
    nomes = {
        t
        for (t,) in con.execute(
            "SELECT table_name FROM information_schema.tables WHERE table_schema = 'marts'"
        ).fetchall()
    }
    con.close()
    return nomes


# ---------- runner ----------


def test_arquivo_vira_tabela_sem_o_prefixo(tmp_path, monkeypatch):
    banco, _ = preparar(tmp_path, monkeypatch, {"00_teste.sql": "SELECT 1 AS x"})

    rodar(monkeypatch)

    con = duckdb.connect(str(banco))
    linhas = con.execute("SELECT x FROM marts.teste").fetchall()
    con.close()
    assert linhas == [(1,)]


def test_ponto_e_virgula_e_espacos_no_final_sao_ignorados(tmp_path, monkeypatch):
    banco, _ = preparar(
        tmp_path, monkeypatch, {"00_teste.sql": "SELECT 1 AS x;\n\n  "}
    )

    rodar(monkeypatch)

    assert tabelas_marts(banco) == {"teste"}


def test_saida_tem_uma_linha_por_mart_e_o_total(tmp_path, monkeypatch):
    preparar(
        tmp_path,
        monkeypatch,
        {
            "01_um.sql": "SELECT 1 AS x",  # 1 linha
            "02_tres.sql": "SELECT * FROM range(3)",  # 3 linhas
        },
    )

    saida = rodar(monkeypatch)

    assert saida.splitlines() == [
        f"✓ {'marts.um':<30} 1 linhas",
        f"✓ {'marts.tres':<30} 3 linhas",
        "Total: 2 mart(s), 4 linhas",
    ]


def test_contagem_usa_milhar_com_ponto(tmp_path, monkeypatch):
    preparar(tmp_path, monkeypatch, {"01_grande.sql": "SELECT * FROM range(1500)"})

    saida = rodar(monkeypatch)

    assert "1.500 linhas" in saida.splitlines()[0]


def test_arquivo_apagado_faz_o_mart_sumir(tmp_path, monkeypatch):
    banco, pasta = preparar(
        tmp_path,
        monkeypatch,
        {"00_teste.sql": "SELECT 1 AS x", "01_fica.sql": "SELECT 2 AS y"},
    )
    rodar(monkeypatch)

    (pasta / "00_teste.sql").unlink()
    rodar(monkeypatch)

    assert tabelas_marts(banco) == {"fica"}


def test_arquivo_sem_prefixo_para_antes_de_executar(tmp_path, monkeypatch):
    banco, _ = preparar(
        tmp_path,
        monkeypatch,
        {
            "01_valido.sql": "SELECT 1 AS x",  # válido, mas não pode rodar
            "teste.sql": "SELECT 1 AS x",  # sem prefixo NN_
        },
    )

    with pytest.raises(SystemExit) as erro:
        rodar(monkeypatch)

    assert erro.value.code == 1
    assert tabelas_marts(banco) == set()  # nenhum SQL foi executado


def test_dois_arquivos_com_o_mesmo_nome_de_tabela_param(tmp_path, monkeypatch):
    banco, _ = preparar(
        tmp_path,
        monkeypatch,
        {
            "01_vendas.sql": "SELECT 1 AS x",
            "02_vendas.sql": "SELECT 2 AS x",  # dá o mesmo marts.vendas
        },
    )

    with pytest.raises(SystemExit):
        rodar(monkeypatch)

    assert tabelas_marts(banco) == set()


def test_mart_vazio_encerra_e_deixa_marts_como_estava(tmp_path, monkeypatch):
    banco, pasta = preparar(tmp_path, monkeypatch, {"00_teste.sql": "SELECT 1 AS x"})
    rodar(monkeypatch)  # execução boa: marts.teste existe

    # segunda execução: um mart novo que volta sem linhas
    (pasta / "01_vazio.sql").write_text("SELECT 1 AS x WHERE false", encoding="utf-8")
    with pytest.raises(SystemExit) as erro:
        rodar(monkeypatch)

    assert erro.value.code == 1
    assert tabelas_marts(banco) == {"teste"}


def test_sql_com_erro_encerra_e_deixa_marts_como_estava(tmp_path, monkeypatch):
    banco, pasta = preparar(tmp_path, monkeypatch, {"00_teste.sql": "SELECT 1 AS x"})
    rodar(monkeypatch)

    (pasta / "01_quebrado.sql").write_text("SELEC 1", encoding="utf-8")  # erro de sintaxe
    with pytest.raises(SystemExit):
        rodar(monkeypatch)

    assert tabelas_marts(banco) == {"teste"}


def test_pasta_sem_sql_encerra(tmp_path, monkeypatch):
    preparar(tmp_path, monkeypatch, {})  # pasta existe, mas vazia

    with pytest.raises(SystemExit) as erro:
        rodar(monkeypatch)

    assert erro.value.code == 1


def test_pasta_inexistente_encerra(tmp_path, monkeypatch):
    preparar(tmp_path, monkeypatch, {})
    monkeypatch.setattr(marts, "PASTA_MARTS", tmp_path / "nao_existe")

    with pytest.raises(SystemExit):
        rodar(monkeypatch)

    assert not (tmp_path / "nao_existe").exists()


def test_refined_faltando_encerra_antes_de_tocar_em_marts(tmp_path, monkeypatch):
    banco = tmp_path / "teste.duckdb"
    con = duckdb.connect(str(banco))
    con.execute("CREATE SCHEMA refined")  # nenhuma das oito tabelas
    con.close()
    pasta = tmp_path / "marts"
    pasta.mkdir()
    (pasta / "00_teste.sql").write_text("SELECT 1 AS x", encoding="utf-8")
    monkeypatch.setattr(db, "CAMINHO_BANCO", banco)
    monkeypatch.setattr(marts, "PASTA_MARTS", pasta)

    with pytest.raises(SystemExit):
        rodar(monkeypatch)

    assert tabelas_marts(banco) == set()


def test_rodar_duas_vezes_imprime_a_mesma_coisa(tmp_path, monkeypatch):
    preparar(
        tmp_path,
        monkeypatch,
        {"00_teste.sql": "SELECT 1 AS x", "01_dois.sql": "SELECT * FROM range(2)"},
    )

    primeira = rodar(monkeypatch)
    segunda = rodar(monkeypatch)

    assert primeira == segunda


# ---------- regras de sql/marts/01_vendas_mensais.sql ----------


def rodar_sql_do_projeto(con, arquivo):
    return con.execute(marts.ler_conteudo_sql(PASTA_SQL_PROJETO / arquivo)).fetchall()


def banco_vendas(tmp_path):
    con = duckdb.connect(str(tmp_path / "teste.duckdb"))
    con.execute("CREATE SCHEMA refined")
    con.execute(
        "CREATE TABLE refined.pedidos ("
        "pedido_id VARCHAR, status VARCHAR, data_compra TIMESTAMP)"
    )
    con.execute(
        "CREATE TABLE refined.itens_pedido ("
        "pedido_id VARCHAR, item_seq INTEGER, preco DECIMAL(10,2))"
    )
    con.execute(
        """
        INSERT INTO refined.pedidos VALUES
            ('p1', 'delivered',   '2024-01-10 08:00:00'),  -- pedido com dois itens
            ('p2', 'canceled',    '2024-01-15 09:00:00'),  -- cancelado: fora da receita
            ('p3', 'unavailable', '2024-01-20 10:00:00'),  -- indisponível: fora também
            ('p4', 'shipped',     '2024-02-03 11:00:00')   -- outro mês, ainda em trânsito
        """
    )
    con.execute(
        """
        INSERT INTO refined.itens_pedido VALUES
            ('p1', 1, 10.50),
            ('p1', 2, 20.25),
            ('p2', 1, 100.00),
            ('p3', 1, 50.00),
            ('p4', 1, 5.00)
        """
    )
    return con


def test_pedido_com_dois_itens_conta_uma_vez(tmp_path):
    con = banco_vendas(tmp_path)

    linhas = rodar_sql_do_projeto(con, "01_vendas_mensais.sql")

    con.close()
    janeiro = linhas[0]
    assert janeiro[1] == 1  # p1 tem dois itens e conta como um pedido


def test_cancelado_fica_fora_da_receita(tmp_path):
    con = banco_vendas(tmp_path)

    linhas = rodar_sql_do_projeto(con, "01_vendas_mensais.sql")

    con.close()
    # janeiro: só p1 = 10.50 + 20.25; p2 (cancelado) e p3 (indisponível) fora
    assert linhas[0][2] == Decimal("30.75")


def test_vendas_mensais_tem_uma_linha_por_mes(tmp_path):
    con = banco_vendas(tmp_path)

    linhas = rodar_sql_do_projeto(con, "01_vendas_mensais.sql")

    con.close()
    assert linhas == [
        (date(2024, 1, 1), 1, Decimal("30.75")),
        (date(2024, 2, 1), 1, Decimal("5.00")),
    ]


# ---------- regras de sql/marts/03_entrega.sql ----------


def banco_entrega(tmp_path, pedidos_sql):
    con = duckdb.connect(str(tmp_path / "teste.duckdb"))
    con.execute("CREATE SCHEMA refined")
    con.execute(
        "CREATE TABLE refined.pedidos ("
        "pedido_id VARCHAR, status VARCHAR, "
        "data_entrega TIMESTAMP, data_entrega_prevista DATE)"
    )
    con.execute(f"INSERT INTO refined.pedidos VALUES {pedidos_sql}")
    return con


def test_entrega_no_dia_previsto_a_tarde_esta_no_prazo(tmp_path):
    con = banco_entrega(
        tmp_path,
        # entregue às 15h do próprio dia previsto
        "('p1', 'delivered', '2024-01-20 15:00:00', '2024-01-20')",
    )

    entregues, no_prazo, atrasados, _ = rodar_sql_do_projeto(con, "03_entrega.sql")[0]

    con.close()
    assert (entregues, no_prazo, atrasados) == (1, 1, 0)


def test_entrega_no_dia_seguinte_esta_atrasada(tmp_path):
    con = banco_entrega(
        tmp_path,
        # um minuto depois da meia-noite do dia seguinte ao previsto
        "('p1', 'delivered', '2024-01-21 00:01:00', '2024-01-20')",
    )

    entregues, no_prazo, atrasados, _ = rodar_sql_do_projeto(con, "03_entrega.sql")[0]

    con.close()
    assert (entregues, no_prazo, atrasados) == (1, 0, 1)


def test_entrega_conta_so_delivered_com_data(tmp_path):
    con = banco_entrega(
        tmp_path,
        """
        ('p1', 'delivered', '2024-01-18 10:00:00', '2024-01-20'),  -- antes do prazo
        ('p2', 'delivered', '2024-01-20 15:00:00', '2024-01-20'),  -- no dia, à tarde
        ('p3', 'delivered', '2024-01-25 09:00:00', '2024-01-20'),  -- atrasado
        ('p4', 'delivered', NULL,                  '2024-01-20'),  -- delivered sem data: fora
        ('p5', 'shipped',   NULL,                  '2024-01-20'),  -- não entregue: fora
        ('p6', 'canceled',  '2024-01-19 10:00:00', '2024-01-20')   -- cancelado com data: fora
        """,
    )

    entregues, no_prazo, atrasados, pct = rodar_sql_do_projeto(con, "03_entrega.sql")[0]

    con.close()
    assert (entregues, no_prazo, atrasados) == (3, 2, 1)
    # 2 de 3 = 66,666...% arredondado em uma casa (DOUBLE: é percentual, não dinheiro)
    assert pct == 66.7
