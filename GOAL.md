# Goal — Harness per agente E2E Testing supervisionato

> Versione 2 (2026-07-31). Ricalibrata dopo la ricerca sul prior art. Vedi `docs/research/`.

## What & Why

Costruire un **harness di agenti** che mantenga nel tempo una copertura E2E affidabile e sempre eseguibile rispetto al comportamento reale del sito.

Il problema reale: il costo di manutenzione dei test E2E su siti che cambiano è così alto che si finisce per rinunciare del tutto ai test.

### Perché non basta ciò che esiste già

La ricerca ha trovato che Playwright **v1.56** ships tre Test Agents ufficiali — `planner`, `generator`, `healer` — che coprono esplorazione → piano Markdown → test → riparazione (`docs/research/00-CRITICAL-playwright-test-agents.md`).

Ma i Playwright Test Agents sono **agent definitions: prompt in markdown più una lista di tool MCP**. Non sono un harness. Delegano tutto il control flow al client LLM che li esegue (VS Code, Claude Code, Codex). Conseguenze:

- **Step non riproducibili** — il percorso dipende dalla decisione del modello a runtime, non da un workflow definito.
- **Costo alto** — servono modelli molto grandi, perché tutto il ragionamento è a carico di un unico loop generalista.
- **Poco customizzabile** — non si può intervenire sulla sequenza, sui guardrail, sui punti di controllo.

**Il gap reale è il disegno del workflow con step riproducibili**, non il prompt.

## Done Looks Like

Un harness che:

1. **Definisce un workflow esplicito e riproducibile** con step controllati, non un loop agentico libero.
2. **Assegna a ogni step il modello più piccolo che sappia farlo**, riservando i modelli grandi ai soli passaggi realmente difficili.
3. **Costruisce i propri mattoni riutilizzabili** — l'agente produce building block (primitive, helper, componenti di interazione) invece di ri-ragionare da zero a ogni esecuzione.
4. **Genera automaticamente test che seguono le specifiche funzionali individuate**, non test scollegati dal piano.
5. **Mantiene i test nel tempo**, distinguendo un cambiamento intenzionale da una regressione.
6. **Espone punti di supervisione umana** sul test plan.

### Due implementazioni parallele

| Variante | Base |
|---|---|
| A | **LangChain `deepagents`** |
| B | **Microsoft Agent Framework (MAF)** con Workflows |

Servono a confrontare due modelli di orchestrazione sullo stesso problema.

### Metrica di successo

KPI combinato:
- copertura (quanto del comportamento rilevante è testato)
- stabilità delle esecuzioni (test affidabili, non flaky)
- costo di manutenzione (sforzo umano quando il sito cambia)
- **costo di esecuzione** (token/modelli richiesti per ciclo)

## Boundaries

- **Nessun nuovo engine di automazione browser.** Playwright resta il layer di esecuzione.
- **Fuori scope il fixing del codice applicativo**: l'agente fa il tester, non lo sviluppatore.
- **Fuori scope l'adozione di harness generalisti esistenti come soluzione finale**: troppo poco customizzabili e troppo costosi. I Playwright Test Agents restano riferimento di prior art e possibile fonte di prompt/convenzioni, non la base architetturale.
- **Il formato delle spec deve essere mappabile su sistemi esterni di test management** (es. Azure DevOps Test Plans). Integrazione effettiva fuori scope: ora è solo un vincolo sul formato.
- **Fuori scope l'orizzonte temporale.**

## Decisions Record

| # | Decisione | Origine |
|---|-----------|---------|
| 1 | Vincolo principale: automatizzare orchestrazione/esecuzione dei test | intervista |
| 2 | Scope in 2 fasi, partendo dall'orchestrazione | intervista |
| 3 | Fase iniziale estesa a planning + esecuzione + manutenzione | intervista |
| 4 | Manutenzione = modifica automatica dei test | intervista |
| 5 | Responsabilità primaria: copertura E2E affidabile nel tempo | intervista |
| 6 | Metrica: KPI combinato | intervista |
| 7 | Nessun nuovo engine browser; Playwright resta l'esecutore | intervista |
| 8 | Orizzonte temporale escluso | intervista |
| 9 | Fuori scope il fixing del codice applicativo | intervista |
| 10 | Discovery autonoma del sito via browser parte del goal | revisione |
| 11 | Supervisione umana sul test plan; esecuzione e manutenzione autonome | revisione |
| 12 | Distinguere cambiamento intenzionale da regressione fa parte del goal | revisione |
| 13 | Spec leggibile = deliverable, non artefatto interno | revisione |
| 14 | Formato spec mappabile su Azure DevOps | revisione |
| 15 | Integrazione con sistemi esterni fuori scope: solo vincolo sul formato | revisione |
| 16 | **Il deliverable è un harness, non un set di prompt** | post-ricerca |
| 17 | **Il gap è il workflow con step riproducibili** | post-ricerca |
| 18 | **Due implementazioni: LangChain deepagents e MAF Workflows** | post-ricerca |
| 19 | **Vincolo di costo: gli step devono girare su modelli piccoli** | post-ricerca |
| 20 | **L'agente costruisce i propri building block riutilizzabili** | post-ricerca |

## Open Questions

- Quale granularità di step rende il workflow riproducibile senza renderlo rigido?
- Quali step richiedono davvero un LLM e quali possono essere codice deterministico?
- Cosa sono esattamente i "mattoni" che l'agente costruisce: page object, tool custom, libreria di interazioni riusabili, o spec parametrizzate?
- Quali segnali usa il workflow per distinguere regressione da cambiamento intenzionale (vedi `docs/research/04-...`)?
- Formato canonico della spec: tabella step ADO-style (raccomandato in `docs/research/03-...`) vs Markdown plan stile Playwright planner.
