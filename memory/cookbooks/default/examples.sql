-- Trend signups giornalieri per paese e device (ultimi 14 giorni)
SELECT
    fs.date,
    c.name AS country,
    d.name AS device,
    fs.signups
FROM fact_signups fs
LEFT JOIN dim_country c ON fs.country_id = c.id
LEFT JOIN dim_device d ON fs.device_id = d.id
WHERE fs.date >= date('now', '-14 days')
ORDER BY fs.date DESC
LIMIT 200;

-- Signups aggregati per paese (ultimi 7 giorni)
SELECT
    c.name AS country,
    SUM(fs.signups) AS total_signups
FROM fact_signups fs
LEFT JOIN dim_country c ON fs.country_id = c.id
WHERE fs.date >= date('now', '-7 days')
GROUP BY c.name
ORDER BY total_signups DESC;

-- Confronto mobile vs desktop signups
SELECT
    d.name AS device,
    SUM(fs.signups) AS total_signups
FROM fact_signups fs
LEFT JOIN dim_device d ON fs.device_id = d.id
WHERE fs.date >= date('now', '-7 days')
GROUP BY d.name;

-- Trend ordini e revenue per paese
SELECT
    fo.date,
    c.name AS country,
    SUM(fo.orders) AS total_orders,
    SUM(fo.revenue) AS total_revenue
FROM fact_orders fo
LEFT JOIN dim_country c ON fo.country_id = c.id
WHERE fo.date >= date('now', '-14 days')
GROUP BY fo.date, c.name
ORDER BY fo.date DESC
LIMIT 200;

-- Revenue media per ordine per device
SELECT
    d.name AS device,
    ROUND(SUM(fo.revenue) / SUM(fo.orders), 2) AS avg_revenue_per_order
FROM fact_orders fo
LEFT JOIN dim_device d ON fo.device_id = d.id
WHERE fo.date >= date('now', '-7 days')
GROUP BY d.name;
