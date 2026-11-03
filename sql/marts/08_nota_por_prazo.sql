-- O atraso derruba a nota?
-- Grão: uma situação de entrega (no_prazo ou atrasado).
-- Denominador do mart 03: delivered com data de entrega, e só os avaliados.
-- Chegar no dia previsto é no prazo. Cada pedido conta uma vez, com a média das suas avaliações.
WITH nota_pedido AS (
    -- Grão: um pedido.
    SELECT pedido_id, avg(nota) AS nota
    FROM refined.avaliacoes
    GROUP BY pedido_id
),
situacao_pedido AS (
    -- Grão: um pedido entregue.
    SELECT
        pedido_id,
        CASE WHEN data_entrega::DATE <= data_entrega_prevista
             THEN 'no_prazo' ELSE 'atrasado' END AS situacao
    FROM refined.pedidos
    WHERE status = 'delivered'
      AND data_entrega IS NOT NULL
)
SELECT
    s.situacao,
    count(*)              AS pedidos_avaliados,
    round(avg(n.nota), 2) AS nota_media,
    round(100.0 * sum(CASE WHEN n.nota <= 2 THEN 1 ELSE 0 END) / count(*), 1) AS pct_nota_baixa
FROM situacao_pedido AS s
JOIN nota_pedido     AS n ON n.pedido_id = s.pedido_id
GROUP BY s.situacao
ORDER BY s.situacao DESC
