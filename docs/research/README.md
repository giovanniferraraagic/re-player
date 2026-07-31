# Research — agente/harness per E2E testing

Ricerca condotta il **2026-07-31** da quattro sub-agent in parallelo (modelli leggeri: Haiku 4.5, Gemini 3.5/3.6 Flash, GPT-5.4 mini), più due approfondimenti sugli harness, con verifica incrociata da parte dell'orchestratore.

## Indice

| File | Argomento | Affidabilità |
|---|---|---|
| `00-CRITICAL-playwright-test-agents.md` | Playwright Test Agents (planner/generator/healer) | ✅ Verificato da fonte primaria dall'orchestratore |
| `01-prior-art-ai-e2e-agents.md` | Censimento tool AI per test E2E (OSS + commerciali) | ⚠️ Numeri inattendibili, conclusioni invalidate — leggere il warning in testa |
| `02-browser-agent-tooling.md` | Tooling per far pilotare un browser a un LLM | ✅ Numeri da API GitHub (2 valori segnalati) |
| `03-test-spec-formats.md` | Formati spec E2E e mapping su Azure DevOps | ✅ Onesto sui limiti |
| `04-self-healing-and-regression-detection.md` | Self-healing e distinzione regressione/cambiamento | ✅ Corretto dopo verifica (una citazione era inventata) |
| `05-deepagents-harness.md` | LangChain `deepagents` come harness | ✅ API GitHub + PyPI + sorgente |
| `06-maf-workflows-harness.md` | Microsoft Agent Framework Workflows come harness | ✅ Learn + release notes |

## Nota sulla qualità della ricerca

Due agenti su quattro hanno prodotto **dati fabbricati**:

- `prior-art-ai-e2e` ha inventato star count ("browser-use: 3K+" contro 107k reali) e ha negato **due volte** l'esistenza dei Playwright Test Agents. Verificato di persona dall'orchestratore: la feature esiste dalla v1.56.
- `self-healing-regression` ha citato un paper IEEE TSE inesistente. Messo sotto verifica, l'ha ammesso e sostituito con tre paper reali.

Gli altri due hanno usato le API GitHub/PyPI e hanno retto la verifica. **Lezione operativa: i modelli leggeri vanno usati con un giro di challenge obbligatorio, non a fiducia.**

---

## Conclusioni che contano per il progetto

### 1. Il prior art esiste, ma non è un harness

Playwright v1.56 ships `planner` / `generator` / `healer`. Coprono esplorazione → piano Markdown → test → riparazione. **Ma sono agent definitions: prompt markdown + tool MCP.** Il control flow è delegato al client LLM (VS Code, Claude Code, Codex).

Conseguenze: step non riproducibili, dipendenza da modelli grandi, nessun punto di controllo programmabile.

**Da riusare comunque:** le convenzioni (layout `specs/` + `tests/`, il seed test come bootstrap del contesto, il formato del piano) sono valide e testate. Non c'è motivo di reinventarle.

### 2. Il pattern di controllo costi è noto e documentato

Separare nettamente le due fasi:

```
AUTHORING     LLM-heavy, esplorativo, costoso
     ↓        emette artefatti riproducibili
EXECUTION     deterministico, CI, ~zero token
              LLM invocato SOLO quando qualcosa si rompe davvero
```

Riferimento concreto: **Stagehand** (Browserbase) — *"auto-caching combined with self-healing remembers previous actions, runs without LLM inference, and knows when to involve AI"*. È esattamente il concetto di "mattoni" costruiti dall'agente: la prima esecuzione ragiona, le successive rieseguono.

### 3. Confronto fra le due varianti di harness

| Criterio | `deepagents` (LangChain) | MAF Workflows (Microsoft) |
|---|---|---|
| Ordine degli step pinnabile | ❌ Loop model-driven; la doc rimanda a LangGraph diretto | ✅ Grafo esplicito, `WorkflowBuilder`, edge condizionali |
| Step deterministici senza LLM | ⚠️ Tool sì, ma l'orchestrazione resta agentica | ✅ `@executor` su funzione pura, zero LLM |
| Checkpoint / resume | ✅ Checkpointer + `thread_id` | ✅ A ogni superstep, stato completo |
| Human-in-the-loop | ✅ `interrupt_on` | ✅ `ctx.request_info()` con resume puntuale |
| Modello per step | ⚠️ Granularità sub-agent | ✅ Per executor, anche provider diversi |
| Osservabilità | LangSmith | ✅ OpenTelemetry nativo, span per executor, propagazione verso MCP |
| Maturità | 0.7.1, beta, churn dichiarato | Python stabile, .NET prerelease, breaking changes attivi |
| Rischio principale | Non garantisce riproducibilità | Barriera BSP: un test lento blocca l'intero superstep |

**Lettura:** sul requisito dichiarato — *workflow con step riproducibili e modelli piccoli per step* — **MAF Workflows è sulla carta il candidato più aderente**. `deepagents` è più adatto alla fase esplorativa (authoring), dove il percorso non è noto a priori.

Ipotesi da validare: **non è necessariamente un aut-aut.** Authoring esplorativo (deepagents/LangGraph) + esecuzione e manutenzione riproducibile (MAF Workflows) potrebbero essere due fasi dello stesso sistema, non due prodotti concorrenti.

### 4. Vincolo di sicurezza non negoziabile

Nessuno strumento esistente distingue in autonomia una regressione da un cambiamento intenzionale. Tutti quelli seri riparano **solo i locator**, mai le assertion. Playwright `healer` è l'unico che dichiara di skippare il test se ritiene la funzionalità rotta.

Policy a tier derivata (dettaglio in `04-`):

| Tier | Caso | Azione |
|---|---|---|
| 0 | Locator rotto, alta confidenza | Ripara, logga |
| 1 | Refactor UI / flusso cambiato / bassa confidenza | Proponi patch, non applicare |
| 2 | **Assertion fallita, errore server** | **Fallisci. Mai riparare.** |

Segnali disponibili per la distinzione: tipo di fallimento (locator vs assertion), blast radius (1 test vs 40), contesto git/PR dell'app, baseline visuali, similarità semantica, soglie di confidenza.

### 5. Formato spec raccomandato

Tabella step **Azure DevOps-style** (`Test Step | Step Action | Step Expected`): leggibile, generabile e aggiornabile da LLM riga per riga, ed è il formato nativo di import/export di ADO Test Plans. Playwright resta il derivato eseguibile, con `test.step()` a rispecchiare i confini degli step.

Da costruire: un convertitore deterministico fra il Markdown plan stile Playwright planner e la tabella ADO. È un pezzo piccolo, concreto, e chiaramente di competenza dell'harness.

---

## Domande aperte

- Granularità degli step: quanto fine prima che il workflow diventi rigido?
- Quali step richiedono davvero un LLM e quali sono codice deterministico?
- Cosa sono esattamente i "mattoni" riutilizzabili: page object, tool custom, cache di azioni stile Stagehand, o spec parametrizzate?
- La barriera BSP di MAF è un problema reale sul nostro carico, o si mitiga con timeout per executor?
