-- Quantos dias leva da compra até a entrega em cada estado?
-- Grão: uma UF do cliente.
-- Denominador do mart 03: delivered com data de entrega. Dias de calendário.
WITH dias_pedido AS (
    -- Grão: um pedido entregue.
    SELECT
        cliente_id,
        date_diff('day', data_compra, data_entrega) AS dias
    FROM refined.pedidos
    WHERE status = 'delivered'
      AND data_entrega IS NOT NULL
)
SELECT
    c.uf,
    count(*)              AS entregues,
    round(avg(d.dias), 1) AS dias_medio,
    median(d.dias)        AS dias_mediana
FROM dias_pedido      AS d
JOIN refined.clientes AS c ON c.cliente_id = d.cliente_id
GROUP BY c.uf
ORDER BY dias_medio DESC
