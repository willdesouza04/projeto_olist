"""Leitura, formatação e gráficos do painel Olist.

Módulo puro: não importa streamlit nem abre conexão com banco. Todas as
agregações estão em SQL (schema marts); este módulo só lê, formata e desenha.

SPEC

1. Leitura (ler)
   ler(marts: list[str]) -> dict[str, DataFrame]
   Abre olist.duckdb uma única vez, em read_only, e fecha ao sair.
   Para cada nome em marts, SELECT * FROM marts.<nome>.
   Motivo: o read_only garante que pipeline.marts consegue gravar enquanto
   o painel está aberto. Se a conexão fica aberta, o arquivo fica locked.

2. Sem cálculos
   Proibido: groupby, sum, mean, count, merge, pivot, conta entre colunas.
   Permitido: ordenar, filtrar linhas, head(n), renomear, formatar texto.
   Número novo na tela = SQL novo em marts. Se faltar mart, pare e diga qual.

3. Formatação (três funções puras)
   reais(valor, casas=2)  -> "R$ 1.003.862,14" (ponto no milhar, vírgula no decimal)
   pct(valor, casas=1)    -> "93,2%"
   numero(valor, casas=0) -> "96.470"
   Jamais use locale do sistema: a máquina de quem roda pode ser USA.

4. Gráficos (uma função por gráfico)
   Cada função recebe um DataFrame e devolve uma figura plotly.
   Toda figura tem: título com número do mart ("01 · Faturamento mensal"),
   uma cor só, eixo com unidade. use_container_width (deprecated) → width="stretch".
   Motivo: app.py reutiliza estas funções em st.plotly_chart, e o relatório
   reutiliza para HTML estático.
"""

import duckdb
import pandas as pd
import plotly.express as px


MARTS_NECESSARIOS = [
    "vendas_mensais",
    "categorias",
    "entrega",
    "nota_por_categoria",
    "recompra",
    "ticket_medio_por_estado",
    "mix_pagamento",
    "nota_por_prazo",
    "vendedores_pareto",
    "tempo_entrega_por_estado",
    "kpis",
    "clientes_por_uf",
]


def ler(marts: list[str]) -> dict[str, pd.DataFrame]:
    """Lê do banco e devolve dict nome -> DataFrame.

    Abre e fecha a conexão aqui. read_only para não segurar o arquivo.
    """
    con = duckdb.connect("olist.duckdb", read_only=True)
    try:
        dados = {}
        for nome in marts:
            df = con.execute(f"SELECT * FROM marts.{nome}").df()
            dados[nome] = df
        return dados
    finally:
        con.close()


# ---------- Formatação ----------


def reais(valor, casas=2) -> str:
    """R$ 1.003.862,14 — milhar com ponto, decimal com vírgula."""
    if pd.isna(valor):
        return "–"
    formato = f"{{:,.{casas}f}}"
    texto = formato.format(float(valor))
    texto = texto.replace(",", "TEMP").replace(".", ",").replace("TEMP", ".")
    return f"R$ {texto}"


def pct(valor, casas=1) -> str:
    """93,2% — decimal com vírgula."""
    if pd.isna(valor):
        return "–"
    formato = f"{{:.{casas}f}}"
    texto = formato.format(float(valor))
    texto = texto.replace(".", ",")
    return f"{texto}%"


def numero(valor, casas=0) -> str:
    """96.470 — milhar com ponto."""
    if pd.isna(valor):
        return "–"
    # Formata com separador de milhar (',') e decimal ('.')
    formato = f"{{:,.{casas}f}}"
    texto = formato.format(float(valor))
    # Troca: milhar recebe ponto, decimal recebe vírgula
    # Exemplo: "96,470.50" vira "96.470,50"
    partes = texto.split(".")
    if casas == 0:
        # Sem casas decimais: "96,470" vira "96.470"
        return partes[0].replace(",", ".")
    else:
        # Com casas decimais: "96,470.50" vira "96.470,50"
        milhar = partes[0].replace(",", ".")
        decimal = partes[1] if len(partes) > 1 else ""
        return f"{milhar},{decimal}"


# ---------- Gráficos ----------


def vendas_mensais(df: pd.DataFrame):
    """01 · Faturamento mensal — linha com marcadores."""
    fig = px.line(
        df,
        x="mes",
        y="receita",
        markers=True,
        title="01 · Faturamento mensal",
        labels={"mes": "Mês", "receita": "Receita (R$)"},
        height=400,
    )
    fig.update_layout(
        hovermode="x unified",
        xaxis_tickformat="%b/%Y",
        yaxis_tickformat="$,.0f",
    )
    fig.update_traces(line_color="#1f77b4", marker_size=6)
    return fig


def receita_por_categoria(df: pd.DataFrame):
    """02 · Receita por categoria — barras horizontais, top 10, maior em cima."""
    df_top = df.head(10).sort_values("receita", ascending=True)
    fig = px.bar(
        df_top,
        x="receita",
        y="categoria",
        orientation="h",
        title="02 · Receita por categoria (top 10)",
        labels={"receita": "Receita (R$)", "categoria": "Categoria"},
        height=400,
    )
    fig.update_layout(
        xaxis_tickformat="$,.0f",
        yaxis_tickangle=0,
    )
    fig.update_traces(marker_color="#2ca02c")
    return fig


def mix_pagamento(df: pd.DataFrame):
    """07 · Mix de pagamento — barras por pct_valor."""
    df_plot = df.sort_values("pct_valor", ascending=False)
    fig = px.bar(
        df_plot,
        x="tipo",
        y="pct_valor",
        title="07 · Mix de pagamento",
        labels={"tipo": "Tipo de pagamento", "pct_valor": "% do valor"},
        height=400,
    )
    fig.update_layout(
        yaxis_tickformat=".0%",
        xaxis_tickangle=-45,
    )
    fig.update_traces(marker_color="#ff7f0e")
    return fig


def ticket_por_uf(df: pd.DataFrame):
    """06 · Ticket médio por UF — barras horizontais, PB em cima, SP embaixo."""
    df_sort = df.sort_values("ticket_medio", ascending=False)
    fig = px.bar(
        df_sort,
        x="ticket_medio",
        y="uf",
        orientation="h",
        title="06 · Ticket médio por UF",
        labels={"ticket_medio": "Ticket (R$)", "uf": "Estado"},
        height=400,
    )
    fig.update_layout(
        xaxis_tickformat="$,.0f",
    )
    fig.update_traces(marker_color="#d62728")
    return fig


def clientes_por_uf(df: pd.DataFrame):
    """11 · Clientes por UF — barras horizontais, maior em cima."""
    df_sort = df.sort_values("clientes", ascending=False)
    fig = px.bar(
        df_sort,
        x="clientes",
        y="uf",
        orientation="h",
        title="11 · Clientes por UF",
        labels={"clientes": "Clientes", "uf": "Estado"},
        height=400,
    )
    fig.update_layout(
        xaxis_tickformat=",",
    )
    fig.update_traces(marker_color="#9467bd")
    return fig


def nota_por_categoria(df: pd.DataFrame):
    """04 · Nota por categoria — pontos, pior em cima."""
    df_top = df.sort_values("posicao_pior", ascending=True).head(10)
    fig = px.scatter(
        df_top,
        x="categoria",
        y="nota_media",
        size="pedidos_avaliados",
        title="04 · Nota por categoria (top 10 piores)",
        labels={"categoria": "Categoria", "nota_media": "Nota média", "pedidos_avaliados": "Pedidos"},
        height=400,
    )
    fig.update_layout(
        xaxis_tickangle=-45,
        yaxis_range=[0, 5.5],
    )
    fig.update_traces(marker_color="#17becf")
    return fig


def concentracao_vendedores(df: pd.DataFrame):
    """09 · Concentração de vendedores — linha de pct_acumulado com linha 80%."""
    fig = px.line(
        df,
        x="posicao",
        y="pct_acumulado",
        title="09 · Concentração de vendedores (Pareto)",
        labels={"posicao": "Posição", "pct_acumulado": "% acumulado da receita"},
        height=400,
    )
    # Linha horizontal em 80%
    fig.add_hline(
        y=80,
        line_dash="dash",
        line_color="red",
        annotation_text="80%",
        annotation_position="right",
    )
    fig.update_layout(
        yaxis_tickformat=".0%",
        hovermode="x unified",
    )
    fig.update_traces(line_color="#1f77b4", marker_size=4)
    return fig
