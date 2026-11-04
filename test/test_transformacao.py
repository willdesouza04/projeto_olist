"""Testes de pipeline/transformacao.py sobre tabelas raw inventadas em tmp_path."""

import io
import sys
from datetime import date, datetime
from decimal import Decimal

import duckdb
import pytest

from pipeline import db, transformacao


def criar_raw(banco, linhas):
    """Cria as oito tabelas raw (tudo VARCHAR, nomes originais) e insere `linhas`.

    `linhas` é {tabela: [ {coluna_origem: valor, ...}, ... ]}; colunas omitidas ficam nulas.
    """
    con = duckdb.connect(str(banco))
    con.execute("CREATE SCHEMA raw")
    for tabela, spec in transformacao.TABELAS.items():
        colunas = [origem for origem, _, _ in spec["colunas"]]
        definicao = ", ".join(f"{c} VARCHAR" for c in colunas)
        con.execute(f"CREATE TABLE raw.{tabela} ({definicao})")
        for linha in linhas.get(tabela, []):
            valores = [linha.get(c) for c in colunas]
            marcadores = ", ".join("?" for _ in colunas)
            con.execute(f"INSERT INTO raw.{tabela} VALUES ({marcadores})", valores)
    con.close()


def pedido(order_id, **extra):
    base = {
        "order_id": order_id,
        "customer_id": "c1",
        "order_status": "delivered",
        "order_purchase_timestamp": "2024-01-10 08:00:00",
        "order_estimated_delivery_date": "2024-01-20 00:00:00",
    }
    base.update(extra)
    return base


def item(order_id, seq, price, freight="1.00"):
    return {
        "order_id": order_id,
        "order_item_id": seq,
        "product_id": "prod1",
        "seller_id": "vend1",
        "shipping_limit_date": "2024-01-12 10:00:00",
        "price": price,
        "freight_value": freight,
    }


def preparar(tmp_path, monkeypatch, linhas):
    banco = tmp_path / "teste.duckdb"
    criar_raw(banco, linhas)
    monkeypatch.setattr(db, "CAMINHO_BANCO", banco)
    return banco


def rodar(monkeypatch):
    """Roda main() e devolve o que ela imprimiu no stdout."""
    saida = io.TextIOWrapper(io.BytesIO(), encoding="utf-8")
    monkeypatch.setattr(sys, "stdout", saida)
    transformacao.main()
    saida.flush()
    return saida.buffer.getvalue().decode("utf-8")


def consultar(banco, sql):
    con = duckdb.connect(str(banco))
    resultado = con.execute(sql).fetchall()
    con.close()
    return resultado


def test_duplicata_exata_sai_e_fica_uma(tmp_path, monkeypatch):
    banco = preparar(
        tmp_path,
        monkeypatch,
        {
            "pedidos": [
                pedido("p1"),
                pedido("p1"),  # linha inteira repetida: deve sobrar uma
                pedido("p2"),  # pedido comum, para ver que não some junto
            ]
        },
    )

    rodar(monkeypatch)

    assert consultar(banco, "SELECT pedido_id FROM refined.pedidos ORDER BY 1") == [
        ("p1",),
        ("p2",),
    ]


def test_duplicata_aparece_na_contagem_da_saida(tmp_path, monkeypatch):
    preparar(
        tmp_path,
        monkeypatch,
        {"pedidos": [pedido("p1"), pedido("p1")]},  # 2 entram, 1 sai
    )

    saida = rodar(monkeypatch)

    linha = next(l for l in saida.splitlines() if l.startswith("refined.pedidos"))
    assert linha.endswith("2 -> 1 linhas  (1 duplicatas)")


def test_datas_com_hora_viram_timestamp_e_prevista_vira_date(tmp_path, monkeypatch):
    banco = preparar(tmp_path, monkeypatch, {"pedidos": [pedido("p1")]})

    rodar(monkeypatch)

    tipos = dict(
        consultar(
            banco,
            "SELECT column_name, data_type FROM information_schema.columns "
            "WHERE table_schema = 'refined' AND table_name = 'pedidos'",
        )
    )
    for coluna in ("data_compra", "data_aprovacao", "data_envio", "data_entrega"):
        assert tipos[coluna] == "TIMESTAMP"
    assert tipos["data_entrega_prevista"] == "DATE"


def test_data_convertida_guarda_o_valor_certo(tmp_path, monkeypatch):
    banco = preparar(tmp_path, monkeypatch, {"pedidos": [pedido("p1")]})

    rodar(monkeypatch)

    assert consultar(
        banco, "SELECT data_compra, data_entrega_prevista FROM refined.pedidos"
    ) == [(datetime(2024, 1, 10, 8, 0, 0), date(2024, 1, 20))]


def test_dinheiro_vira_decimal_10_2(tmp_path, monkeypatch):
    banco = preparar(tmp_path, monkeypatch, {"itens_pedido": [item("p1", "1", "10.50")]})

    rodar(monkeypatch)

    tipos = dict(
        consultar(
            banco,
            "SELECT column_name, data_type FROM information_schema.columns "
            "WHERE table_schema = 'refined' AND table_name = 'itens_pedido'",
        )
    )
    assert tipos["preco"] == "DECIMAL(10,2)"
    assert tipos["frete"] == "DECIMAL(10,2)"
    assert tipos["item_seq"] == "INTEGER"


def test_soma_de_dinheiro_fecha_no_centavo(tmp_path, monkeypatch):
    # 0.10 + 0.20 em DOUBLE dá 0.30000000000000004; em DECIMAL dá 0.30 exato
    banco = preparar(
        tmp_path,
        monkeypatch,
        {"itens_pedido": [item("p1", "1", "0.10"), item("p1", "2", "0.20")]},
    )

    rodar(monkeypatch)

    assert consultar(banco, "SELECT sum(preco) FROM refined.itens_pedido") == [
        (Decimal("0.30"),)
    ]


def test_colunas_sao_renomeadas_pelo_mapa(tmp_path, monkeypatch):
    banco = preparar(tmp_path, monkeypatch, {})

    rodar(monkeypatch)

    colunas = [
        c
        for (c,) in consultar(
            banco,
            "SELECT column_name FROM information_schema.columns "
            "WHERE table_schema = 'refined' AND table_name = 'pagamentos' "
            "ORDER BY ordinal_position",
        )
    ]
    assert colunas == ["pedido_id", "pagamento_seq", "tipo", "parcelas", "valor"]


def test_cep_com_zero_a_esquerda_continua_texto(tmp_path, monkeypatch):
    banco = preparar(
        tmp_path,
        monkeypatch,
        # CEP começando com zero: como número perderia o zero
        {"clientes": [{"customer_id": "c1", "customer_zip_code_prefix": "01310"}]},
    )

    rodar(monkeypatch)

    assert consultar(banco, "SELECT cep_prefixo FROM refined.clientes") == [("01310",)]


def test_data_nula_continua_nula(tmp_path, monkeypatch):
    banco = preparar(
        tmp_path,
        monkeypatch,
        # pedido cancelado: não tem data de entrega, e o nulo é informação
        {"pedidos": [pedido("p1", order_status="canceled")]},
    )

    rodar(monkeypatch)

    assert consultar(
        banco, "SELECT data_entrega, status FROM refined.pedidos"
    ) == [(None, "canceled")]


def test_nulo_mantido_aparece_na_saida(tmp_path, monkeypatch):
    # um pedido sem aprovação, envio e entrega: três colunas com um nulo cada
    preparar(tmp_path, monkeypatch, {"pedidos": [pedido("p1")]})

    saida = rodar(monkeypatch)

    assert (
        "    nulos mantidos: data_aprovacao 1, data_envio 1, data_entrega 1"
        in saida.splitlines()
    )


def test_dinheiro_que_nao_converte_encerra_com_systemexit(tmp_path, monkeypatch):
    preparar(
        tmp_path,
        monkeypatch,
        {"itens_pedido": [item("p1", "1", "dez reais")]},  # não é número
    )

    with pytest.raises(SystemExit) as erro:
        rodar(monkeypatch)

    assert erro.value.code == 1


def test_data_que_nao_converte_encerra_com_systemexit(tmp_path, monkeypatch):
    preparar(
        tmp_path,
        monkeypatch,
        # formato dia/mês/ano: fora do formato declarado
        {"pedidos": [pedido("p1", order_purchase_timestamp="10/01/2024 08:00:00")]},
    )

    with pytest.raises(SystemExit):
        rodar(monkeypatch)

    # conversão falhou: nada foi gravado em refined, nem virou nulo
    assert consultar(
        tmp_path / "teste.duckdb",
        "SELECT count(*) FROM information_schema.tables WHERE table_schema = 'refined'",
    ) == [(0,)]


def test_falha_numa_tabela_nao_grava_as_outras(tmp_path, monkeypatch):
    banco = preparar(
        tmp_path,
        monkeypatch,
        {
            "pedidos": [pedido("p1")],  # pedido válido
            "pagamentos": [  # valor inválido na última tabela convertida antes de gravar
                {"order_id": "p1", "payment_sequential": "1", "payment_value": "abc"}
            ],
        },
    )

    with pytest.raises(SystemExit):
        rodar(monkeypatch)

    assert consultar(
        banco,
        "SELECT count(*) FROM information_schema.tables WHERE table_schema = 'refined'",
    ) == [(0,)]


def test_achar_falha_aponta_coluna_e_valor(tmp_path):
    banco = tmp_path / "teste.duckdb"
    criar_raw(
        banco,
        {"itens_pedido": [item("p1", "1", "10.00", freight="grátis")]},  # frete inválido
    )
    con = duckdb.connect(str(banco))

    falha = transformacao.achar_falha(con, "itens_pedido")

    con.close()
    assert falha == ("freight_value", "frete", "grátis")


def test_achar_falha_sem_valor_ruim_devolve_none(tmp_path):
    banco = tmp_path / "teste.duckdb"
    criar_raw(banco, {"itens_pedido": [item("p1", "1", "10.00")]})  # tudo válido
    con = duckdb.connect(str(banco))

    falha = transformacao.achar_falha(con, "itens_pedido")

    con.close()
    assert falha is None


def test_chave_repetida_com_conteudo_diferente_encerra(tmp_path, monkeypatch):
    banco = preparar(
        tmp_path,
        monkeypatch,
        {
            "pedidos": [
                pedido("p1", order_status="delivered"),
                pedido("p1", order_status="canceled"),  # mesma chave, status diferente
            ]
        },
    )

    with pytest.raises(SystemExit):
        rodar(monkeypatch)

    assert consultar(
        banco,
        "SELECT count(*) FROM information_schema.tables WHERE table_schema = 'refined'",
    ) == [(0,)]


def test_avaliacao_id_repetido_em_pedidos_diferentes_nao_e_conflito(
    tmp_path, monkeypatch
):
    banco = preparar(
        tmp_path,
        monkeypatch,
        {
            "avaliacoes": [
                # mesmo avaliacao_id em dois pedidos: a chave é (avaliacao_id, pedido_id)
                {"review_id": "r1", "order_id": "p1", "review_score": "5"},
                {"review_id": "r1", "order_id": "p2", "review_score": "5"},
            ]
        },
    )

    rodar(monkeypatch)

    assert consultar(banco, "SELECT count(*) FROM refined.avaliacoes") == [(2,)]


def test_tabela_raw_faltando_encerra_com_systemexit(tmp_path, monkeypatch):
    banco = tmp_path / "teste.duckdb"
    con = duckdb.connect(str(banco))
    con.execute("CREATE SCHEMA raw")  # schema vazio: nenhuma das oito tabelas
    con.close()
    monkeypatch.setattr(db, "CAMINHO_BANCO", banco)

    with pytest.raises(SystemExit) as erro:
        rodar(monkeypatch)

    assert erro.value.code == 1


def test_tabelas_faltando_lista_so_as_ausentes(tmp_path):
    banco = tmp_path / "teste.duckdb"
    con = duckdb.connect(str(banco))
    con.execute("CREATE SCHEMA raw")
    con.execute("CREATE TABLE raw.pedidos (x VARCHAR)")  # só uma das oito

    faltando = transformacao.tabelas_faltando(con)

    con.close()
    assert "pedidos" not in faltando
    assert len(faltando) == 7


def test_rodar_duas_vezes_imprime_a_mesma_coisa(tmp_path, monkeypatch):
    preparar(tmp_path, monkeypatch, {"pedidos": [pedido("p1"), pedido("p1")]})

    primeira = rodar(monkeypatch)
    segunda = rodar(monkeypatch)

    assert primeira == segunda


def test_total_soma_entradas_e_saidas_de_todas_as_tabelas(tmp_path, monkeypatch):
    preparar(
        tmp_path,
        monkeypatch,
        {
            "pedidos": [pedido("p1"), pedido("p1")],  # 2 entram, 1 sai
            "itens_pedido": [item("p1", "1", "5.00")],  # 1 entra, 1 sai
        },
    )

    saida = rodar(monkeypatch)

    assert saida.splitlines()[-1] == "Total: 3 -> 2 linhas  (1 duplicatas)"
