-- Quanto do dinheiro pago entra por cada forma de pagamento?
-- Grão: um tipo de pagamento. Só pedidos válidos.
-- A tabela pagamentos tem uma linha por pagamento: pagamentos conta linhas e
-- pedidos conta pedidos. A coluna pedidos não soma entre tipos.
SELECT
    pg.tipo,
    count(*)                    AS pagamentos,
    count(DISTINCT pg.pedido_id) AS pedidos,
    sum(pg.valor)               AS valor,
    round(100.0 * sum(pg.valor) / sum(sum(pg.valor)) OVER (), 1) AS pct_valor
FROM refined.pagamentos AS pg
JOIN refined.pedidos    AS p ON p.pedido_id = pg.pedido_id
WHERE p.status NOT IN ('canceled', 'unavailable')
GROUP BY pg.tipo
ORDER BY valor DESC
