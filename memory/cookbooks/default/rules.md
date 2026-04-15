# Regole business

- I signups e gli ordini devono essere analizzati su base giornaliera.
- Le analisi devono includere sempre almeno una dimensione: country o device.
- Le query esplorative devono essere limitate (LIMIT) per preservare performance.
- Il trend degli ordini deve essere confrontato con la revenue se la domanda lo richiede.
- Quando si confrontano periodi, usare la colonna `date` con filtri WHERE espliciti.

# Schema relazioni

- `fact_signups.country_id` -> `dim_country.id`
- `fact_signups.device_id` -> `dim_device.id`
- `fact_orders.country_id` -> `dim_country.id`
- `fact_orders.device_id` -> `dim_device.id`

# Metriche principali

- **signups**: numero giornaliero di iscrizioni per combinazione paese/device.
- **orders**: numero giornaliero di ordini per combinazione paese/device.
- **revenue**: valore economico associato agli ordini (in EUR).

# Caveat

- I dati sono sintetici e coprono gli ultimi 28 giorni.
- Le conclusioni sono basate sui dati disponibili fino all'ultima data caricata.
- Revenue = orders * prezzo unitario (il prezzo varia per paese e device).
