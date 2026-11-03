-- Qual o ticket médio de cada estado?
-- Grão: uma UF do cliente. O grão muda duas vezes: item -> pedido -> UF.
-- Ticket: receita somada por pedido primeiro, média por pedido depois. Só pedidos válidos.
WITH receita_pedido AS (
    -- Grão: um pedido.
    SELECT
        p.pedido_id,
        p.cliente_id,
        sum(i.preco) AS receita
    FROM refined.pedidos      AS p
    JOIN refined.itens_pedido AS i ON i.pedido_id = p.pedido_id
    WHERE p.status NOT IN ('canceled', 'unavailable')
    GROUP BY p.pedido_id, p.cliente_id
)
SELECT
    c.uf,
    count(*)                AS pedidos,
    round(avg(r.receita), 2) AS ticket_medio
FROM receita_pedido   AS r
JOIN refined.clientes AS c ON c.cliente_id = r.cliente_id
GROUP BY c.uf
ORDER BY ticket_medio DESC
