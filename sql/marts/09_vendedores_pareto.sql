-- Que fração dos vendedores faz 80% da receita?
-- Grão: um vendedor com venda válida, do maior para o menor.
-- vendedor_id desempata a ordem: sem ele, vendedores com a mesma receita
-- receberiam o mesmo acumulado, e não a soma até a própria linha.
WITH receita_vendedor AS (
    -- Grão: um vendedor.
    SELECT
        i.vendedor_id,
        sum(i.preco) AS receita
    FROM refined.itens_pedido AS i
    JOIN refined.pedidos      AS p ON p.pedido_id = i.pedido_id
    WHERE p.status NOT IN ('canceled', 'unavailable')
    GROUP BY i.vendedor_id
)
SELECT
    r.vendedor_id,
    v.uf,
    r.receita,
    row_number() OVER (ORDER BY r.receita DESC, r.vendedor_id) AS posicao,
    round(100.0 * sum(r.receita) OVER (ORDER BY r.receita DESC, r.vendedor_id)
          / sum(r.receita) OVER (), 2) AS pct_acumulado
FROM receita_vendedor   AS r
JOIN refined.vendedores AS v ON v.vendedor_id = r.vendedor_id
ORDER BY posicao
