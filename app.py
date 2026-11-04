"""Painel da Olist em Streamlit.

Executar com: uv run streamlit run app.py
"""

import streamlit as st
import pandas as pd

import painel

# Configuração da página
st.set_page_config(page_title="Olist · Visão da operação", layout="wide")

# Carregar dados com cache
@st.cache_data
def carregar_dados():
    """Carrega todos os marts necessários."""
    return painel.ler(painel.MARTS_NECESSARIOS)

# Botão de recarregar e verificação de erros
col_titulo, col_reload = st.columns([0.9, 0.1])

with col_titulo:
    st.title("Olist · Visão da operação")

with col_reload:
    if st.button("🔄 Recarregar dados", key="reload"):
        st.cache_data.clear()
        st.rerun()

try:
    dados = carregar_dados()
except FileNotFoundError:
    st.error("❌ Arquivo olist.duckdb não encontrado. Rode `uv run python -m pipeline.marts` primeiro.")
    st.stop()
except Exception as e:
    st.error(f"❌ Erro ao carregar marts: {e}. Rode `uv run python -m pipeline.marts`.")
    st.stop()

# Verificar se todos os marts necessários existem
faltando = set(painel.MARTS_NECESSARIOS) - set(dados.keys())
if faltando:
    st.error(f"❌ Marts faltando: {', '.join(sorted(faltando))}. Rode `uv run python -m pipeline.marts`.")
    st.stop()

# ---------- FILTRO DE PERÍODO ----------

df_vendas = dados["vendas_mensais"].sort_values("mes")
datas = sorted(df_vendas["mes"].unique())  # numpy.datetime64 array
data_min = datas[0]
data_max = datas[-1]

st.write("### Filtro de período")
col_filtro_l, col_filtro_r = st.columns(2)

with col_filtro_l:
    data_inicio = st.select_slider(
        "Data inicial",
        options=datas,
        value=data_min,
        format_func=lambda x: pd.Timestamp(x).strftime("%b/%Y"),
    )

with col_filtro_r:
    data_fim = st.select_slider(
        "Data final",
        options=datas,
        value=data_max,
        format_func=lambda x: pd.Timestamp(x).strftime("%b/%Y"),
    )

st.caption("⚠️ Os cartões valem para o período inteiro; o filtro afeta apenas o gráfico de faturamento.")

# ---------- CARTÕES (KPIs) ----------

st.write("---")
col_kpi = st.columns(7)

kpis = dados["kpis"].iloc[0]
pct_um_pedido = dados["recompra"].loc[dados["recompra"]["pedidos_por_cliente"] == 1, "pct_clientes"].values[0]
recompra_pct = 100 - pct_um_pedido

metricas = [
    ("Ticket médio", painel.reais(kpis["ticket_medio"]), "kpis.ticket_medio"),
    ("Cancelados", painel.pct(kpis["pct_cancelados"], 2), "kpis.pct_cancelados"),
    ("Peso do frete", painel.pct(kpis["pct_frete"], 1), "kpis.pct_frete"),
    ("Recompra", painel.pct(recompra_pct, 2), "recompra_calculo"),
    ("No prazo", painel.pct(dados["entrega"].iloc[0]["pct_no_prazo"], 1), "entrega.pct_no_prazo"),
    ("Dias até entregar", f"{kpis['dias_entrega']:.1f}", "kpis.dias_entrega"),
    ("Nota média", painel.numero(kpis["nota_media"], 2), "kpis.nota_media"),
]

for i, (label, valor, _) in enumerate(metricas):
    with col_kpi[i]:
        st.metric(label, valor)

# ---------- FAIXA 1: FATURAMENTO MENSAL ----------

st.write("---")
df_vendas_filtrado = df_vendas[
    (df_vendas["mes"] >= data_inicio) &
    (df_vendas["mes"] <= data_fim)
]
fig_vendas = painel.vendas_mensais(df_vendas_filtrado)
st.plotly_chart(fig_vendas, use_container_width=True)

# ---------- FAIXA 2: TRÊS GRÁFICOS (categoria, mix, ticket) ----------

st.write("---")
col_cat, col_mix, col_ticket = st.columns(3)

with col_cat:
    fig_cat = painel.receita_por_categoria(dados["categorias"])
    st.plotly_chart(fig_cat, use_container_width=True)

with col_mix:
    fig_mix = painel.mix_pagamento(dados["mix_pagamento"])
    st.plotly_chart(fig_mix, use_container_width=True)

with col_ticket:
    fig_ticket = painel.ticket_por_uf(dados["ticket_medio_por_estado"])
    st.plotly_chart(fig_ticket, use_container_width=True)

# ---------- FAIXA 3: TRÊS GRÁFICOS (clientes, nota, pareto) ----------

st.write("---")
col_clientes, col_nota, col_pareto = st.columns(3)

with col_clientes:
    fig_clientes = painel.clientes_por_uf(dados["clientes_por_uf"])
    st.plotly_chart(fig_clientes, use_container_width=True)

with col_nota:
    fig_nota = painel.nota_por_categoria(dados["nota_por_categoria"])
    st.plotly_chart(fig_nota, use_container_width=True)

with col_pareto:
    fig_pareto = painel.concentracao_vendedores(dados["vendedores_pareto"])
    st.plotly_chart(fig_pareto, use_container_width=True)
