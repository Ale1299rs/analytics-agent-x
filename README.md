# Analytics Agent X

Un agente di analytics enterprise che comprende domande business, genera SQL, esegue query, interpreta risultati e si autocorregge. Progettato come MVP low-cost, modulare e locale.

**Non** un chatbot SQL. Un agente con pipeline esplicita, chart automatici, conversazione multi-turn e schema auto-discovery.

```
Domanda -> Context Builder -> Planner -> Critic -> SQL Validator -> Executor -> Reflector
                                                                                    |
                                                                        Answer Builder + Chart Builder
                                                                                    |
                                                                         Follow-up Suggestions
```

## Feature principali

- **Pipeline agentica esplicita** con self-correction fino a 3 iterazioni
- **Chart automatici** (line, multi-line, bar) — detect automatico del tipo di dato
- **Schema auto-discovery** — connetti il DB, il sistema mappa le tabelle da solo
- **Conversazione multi-turn** — "e per paese?", "scendi nel dettaglio sull'Italia"
- **Follow-up proattivi** — suggerisce 3 domande successive via LLM
- **Critic LLM + programmatico** — validazione semantica + safety net deterministico
- **SQL security** — whitelist tabelle, blocco comandi pericolosi, LIMIT automatico
- **Interpretazione dati con LLM** — non mostra solo numeri, spiega cosa significano
- **Memory system** — cookbooks, recipes, ingredients, learned patterns
- **Cost guard** — traccia chiamate LLM, stima token, genera warning
- **Debug mode** — mostra l'intera pipeline step by step
- **Feedback loop** — l'utente corregge, il sistema impara

## Architettura

```
core/
  orchestrator.py      # Pipeline agentica principale
  planner.py           # Genera query SQL via LLM
  critic.py            # Valida query via LLM + controlli programmatici
  sql_validator.py     # Sicurezza SQL (whitelist, SQLGlot, LIMIT)
  executor.py          # Esegue query (SQLite/Postgres)
  reflector.py         # Decide se iterare ancora via LLM
  answer_builder.py    # Interpreta i dati e scrive risposta via LLM
  chart_builder.py     # Auto-detect e generazione chart spec
  schema_discovery.py  # Discovery automatica schema dal DB
  conversation.py      # Multi-turn + follow-up suggestions
  context_builder.py   # Seleziona contesto rilevante dalla memoria
  feedback_writer.py   # Salva feedback e pattern appresi
  cost_guard.py        # Traccia costi e limiti
  llm/                 # Adapter provider-agnostici (DeepSeek, OpenAI)
app/
  streamlit_app.py     # UI conversazionale con chart e follow-up
memory/
  cookbooks/           # Ingredients, recipes, rules, esempi SQL
```

## Setup locale

```bash
# 1. Ambiente virtuale
python3 -m venv .venv
source .venv/bin/activate

# 2. Dipendenze
pip install -r requirements.txt

# 3. Configurazione
cp .env.example .env
# Inserisci la tua DEEPSEEK_API_KEY nel file .env

# 4. Database demo
python db/seed_demo_data.py

# 5. Avvia
streamlit run app/streamlit_app.py
```

## Schema Auto-Discovery

Non serve configurare ingredients.yaml a mano. Dalla sidebar di Streamlit, clicca **"Scopri schema dal DB"** e il sistema:
1. Legge tutte le tabelle dal database
2. Detecta colonne, tipi, foreign key, colonne data
3. Classifica fact vs dimension tables
4. Genera automaticamente `ingredients.yaml`

Funziona con SQLite e Postgres.

## Configurazione

| Variabile | Default | Descrizione |
|-----------|---------|-------------|
| `LLM_PROVIDER` | `deepseek` | `deepseek` o `openai` |
| `DEEPSEEK_API_KEY` | - | API key DeepSeek |
| `DB_BACKEND` | `sqlite` | `sqlite` o `postgres` |
| `MAX_AGENT_LOOPS` | `3` | Max iterazioni per richiesta |

## Test

```bash
pytest tests/ -v   # 100 test
```

## Costi stimati

Con DeepSeek Chat, **1000 query costano ~$1.90** (scenario misto 60% 1-iter / 30% 2-iter / 10% 3-iter).

| Provider | 1000 query | Per query |
|----------|-----------|-----------|
| DeepSeek Chat | $1.90 | $0.002 |
| GPT-4o-mini | $1.05 | $0.001 |
| GPT-4o | $17.43 | $0.017 |

## Limiti dell'MVP

- Schema descritto via YAML o auto-discovery (no introspection runtime delle query)
- Memoria single-user su filesystem locale
- Nessuna autenticazione

## Roadmap

- [ ] Supporto BigQuery
- [ ] Memoria multi-user con embeddings per retrieval
- [ ] Chart interattivi con drill-down cliccabile
- [ ] Export risultati CSV/Excel
- [ ] Fallback automatico tra provider LLM
- [ ] Token counting accurato
