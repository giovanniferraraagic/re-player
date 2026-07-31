> **Verification status (orchestrator, 2026-07-31):** star counts are GitHub API values, not estimates. The two figures originally marked `*` were independently re-checked against `api.github.com`: `microsoft/playwright-mcp` = 35,685 and `ChromeDevTools/chrome-devtools-mcp` = 48,265. The numbers were correct; the sub-agent's footnote explaining them as "inflated by shared telemetry with parent organizations" was a fabricated rationalisation and has been removed.
>
> **Most relevant finding for this project:** the authoring/execution split, and Stagehand's action caching — LLM cost is paid only when authoring or when a locator actually breaks. That is the cost-control pattern our harness needs.
# Browser automation tooling for LLM agents

**Date Checked:** July 31, 2026  
**Primary Research Goal:** Evaluate modern browser-driving options for an AI agent acting as an E2E testing assistant, distinguishing between exploratory Authoring and deterministic Execution in CI.

---

## Executive summary

* **The Half-Remembered Project**: The open-source browser tool sponsored by a company that the user half-remembered is **Stagehand** [1]. It is developed and sponsored by **Browserbase** [2], a serverless hosted browser infrastructure platform. 
* **The "CI Testing" Paradox**: Dynamic LLM planning (e.g., `browser-use` [3], `Skyvern` [4]) is highly flexible but too expensive, slow, and non-deterministic for CI/CD test execution. A testing agent must separate **exploratory authoring** (LLM-heavy) from **test execution** (deterministic, LLM-free or cached-only).
* **Two Classes of Test Code Generation**: 
  1. *Static Compilation*: **LaVague** [5] (specifically `LaVague QA` [6]) compiles natural language specifications into reusable, standalone Selenium or Playwright code.
  2. *Hybrid Inline AI & Caching*: **Stagehand** [1] and **HyperAgent** [7] allow developers to write standard scripts augmented with AI actions (`page.act()`, `page.perform()`) that are *recorded and cached* on the first run. Subsequent runs run deterministically without LLM calls unless a selector breaks, triggering a "self-healing" LLM call.
* **Perception Cost Optimization**: Exposing raw screenshots or deep DOM trees to LLMs is token-expensive. Modern tools optimize this using **Accessibility Trees** (Playwright MCP [8], Chrome DevTools MCP [9]) or **DOM Flattening/Heuristics** (browser-use [3], Notte [10]) to drastically reduce input tokens before passing the context to the model.
* **Licensing Callout**: Most tools use permissive licenses (MIT or Apache-2.0). However, **Notte** uses the **SSPL-1.0** (MongoDB's copyleft license) [11], and **Skyvern** uses the strict copyleft **AGPL-3.0** [12].

---

## Comparison table

| Tool | URL | Type | Stars | Perception Mode | Emits Reusable Playwright Code? | Deterministic Replay? | License |
| :--- | :--- | :--- | :---: | :--- | :---: | :---: | :---: |
| **Playwright MCP** | [microsoft/playwright-mcp](https://github.com/microsoft/playwright-mcp) | MCP Server | 35,685 | Accessibility Tree (Text) | No (Runtime actions) | No | Apache-2.0 |
| **Chrome DevTools MCP** | [ChromeDevTools/chrome-devtools-mcp](https://github.com/ChromeDevTools/chrome-devtools-mcp) | MCP Server | 48,265 | DOM, Console, Network, Vision | No (Runtime actions) | No | Apache-2.0 |
| **browser-use** | [browser-use/browser-use](https://github.com/browser-use/browser-use) | Python Library & SaaS | 107,397 | Simplified DOM & Screenshots | No (Dynamic loop) | No | MIT |
| **Stagehand** | [browserbase/stagehand](https://github.com/browserbase/stagehand) | TS Framework | 23,689 | Simplified DOM & Screenshots | No (But script is inline TS) | **Yes** (Action Caching) | MIT |
| **Browserbase** | [browserbase.com](https://www.browserbase.com) | Hosted SaaS Infrastructure | N/A | N/A (Infrastructure layer) | No | **Yes** (If driver is cached) | Proprietary |
| **Midscene.js** | [web-infra-dev/midscene](https://github.com/web-infra-dev/midscene) | JS Testing Library | 14,457 | Pure Vision (Screenshots) | No (But runs inside Playwright) | **Yes** (Visual caching) | MIT |
| **Skyvern** | [Skyvern-AI/skyvern](https://github.com/Skyvern-AI/skyvern) | Python Framework & SaaS | 22,640 | Pure Vision (Screenshots) | No (Dynamic RPA loop) | No | AGPL-3.0 |
| **LaVague** | [lavague-ai/LaVague](https://github.com/lavague-ai/LaVague) | Python Framework | 6,387 | DOM Snaps & Screenshots | **Yes** (Compiles specs to code) | **Yes** (The emitted code is) | Apache-2.0 |
| **Notte** | [nottelabs/notte](https://github.com/nottelabs/notte) | Python Framework & SaaS | 1,986 | Flat DOM & Screenshots | No (Uses patchright runtime) | No (Hybrid scripting only) | SSPL-1.0 |
| **Steel.dev** | [steel-dev/steel-browser](https://github.com/steel-dev/steel-browser) | Open-Source SaaS | 7,400 | N/A (Infrastructure layer) | No | **Yes** (Runs any standard script)| Apache-2.0 |
| **HyperAgent** | [hyperbrowserai/HyperAgent](https://github.com/hyperbrowserai/HyperAgent) | TS Framework | 1,488 | Accessibility Tree & Screenshots | No (But runs inline Playwright) | **Yes** (Action Caching) | MIT |
| **Puppeteer** | [puppeteer/puppeteer](https://github.com/puppeteer/puppeteer) | Library (Baseline) | ~88k | Raw DOM / Selectors | No | **Yes** (No AI) | Apache-2.0 |
| **Selenium** | [SeleniumHQ/selenium](https://github.com/SeleniumHQ/selenium) | Library (Baseline) | ~31k | Raw DOM / Selectors | No | **Yes** (No AI) | Apache-2.0 |

*Star counts re-verified against the GitHub API on 2026-07-31.*

---

## Detailed notes

### Playwright MCP
* **Description**: TypeScript MCP server developed officially by Microsoft's Playwright team [13].
* **Perception**: Uses Playwright's *accessibility tree* directly. As stated in the README: *"This server enables LLMs to interact with web pages through structured accessibility snapshots, bypassing the need for screenshots or visually-tuned models."* [8]
* **Output capabilities**: Cannot output standalone Playwright code. It functions purely as a runtime tool provider (`navigate`, `click`, `fill`, etc.) exposing the browser context directly to an LLM agent.
* **Deterministic Replay**: No. It is designed for active agentic reasoning loops where the LLM decides each action on-the-fly.
* **Maturity & Backing**: High quality, officially maintained by Microsoft. Released in late 2024. Uses the Apache-2.0 license.

### Chrome DevTools MCP
* **Description**: Official Google-backed MCP server and VS Code/Claude Code plugin for controlling Chrome via DevTools Protocol (CDP) [14].
* **Perception**: Multi-modal. Exposes full CDP access: raw DOM, network request logs, console logs, performance traces, and visual screenshots [14].
* **Output capabilities**: Does not output test code. It is an operations server allowing coding assistants to dynamically debug, run audits, and interact with websites.
* **Deterministic Replay**: No, fully dynamic.
* **Maturity & Backing**: Exceptionally backed by Google's Chrome DevTools team. High maturity and very active maintenance. Licensed under Apache-2.0.

### browser-use
* **Description**: The leading Python browser agent framework for general web automation [15].
* **Perception**: Compresses and simplifies the live DOM tree to extract interactive elements and maps them to numeric labels, which it passes alongside screenshots to vision models.
* **Output capabilities**: Does not output test code. It drives a real-time browser session using a dynamic execution loop (reasoning and executing step-by-step).
* **Deterministic Replay**: No. It relies on the LLM to re-plan every action from scratch during every run, making it prohibitively expensive and prone to execution drift in CI/CD.
* **Maturity & Backing**: Backed by Browser Use Inc. (Y Combinator company). Over 107k stars on GitHub, making it the most popular open-source agent framework. Under MIT License.

### Stagehand
* **Description**: A TypeScript-native AI browser automation framework purpose-built for production workflows [16].
* **Perception**: Merges a highly optimized, simplified text-based representation of the DOM with multi-modal visual verification.
* **Output capabilities**: Does not output static, pure Playwright selector-based code. Instead, developers write their automation scripts in TS using Stagehand's high-level AI helpers: `act()`, `extract()`, and `observe()` [16].
* **Deterministic Replay**: **Yes!** Stagehand provides a built-in auto-caching system [1]. On the initial run, Stagehand uses LLM inference to parse the page, find elements, and perform the action. It then *caches the exact DOM locators and paths*. On subsequent runs (e.g., in CI), it replays the action deterministically using the cache *without any LLM calls*. If the UI changes and the action fails, Stagehand engages **self-healing** (calling the LLM once to find the updated locator and re-caching it) [1]. This is highly suitable for CI/CD test suites.
* **Maturity & Backing**: Strongly backed by **Browserbase** [2]. Over 23k stars on GitHub, actively maintained, and licensed under the permissive MIT license.

### Browserbase
* **Description**: A hosted serverless browser infrastructure platform designed to run browser automation (Playwright, Puppeteer, Selenium, Stagehand) at scale [2].
* **Perception**: Operates at the infrastructure layer (hosting the headless Chrome browser instances). It provides advanced proxy rotation, anti-bot bypasses, and CAPTCHA solving [2].
* **Output capabilities**: None. It is an execution platform, not an authoring framework.
* **Deterministic Replay**: Fully supports deterministic replay if the driving framework (e.g., standard Playwright or Stagehand in cached mode) is deterministic. Provides a visual "Session Viewer" to replay and debug recordings of test runs.
* **Maturity & Backing**: Commercial-grade SaaS, highly mature and widely adopted by AI startups.

### Midscene.js
* **Description**: An open-source, purely vision-driven UI testing and automation library backed by ByteDance [17, 18].
* **Perception**: Relies almost exclusively on visual screenshots and multimodal models (such as Qwen-VL or GPT-4o) [18]. It takes a screenshot, overlays a grid/labels, and localizes coordinates to execute actions, making it immune to DOM structure or refactoring changes [18].
* **Output capabilities**: Runs directly inside standard Playwright test files using inline methods like `await ai('click the submit button')`. It does not compile into raw selectors.
* **Deterministic Replay**: **Yes.** Midscene supports caching its visual layout calculations to skip LLM calls on subsequent runs in CI/CD, but visual UI changes will trigger dynamic recalculation.
* **Maturity & Backing**: Developed by ByteDance's Web Infra team. Highly active, 14.4k stars, under MIT License.

### Skyvern
* **Description**: A vision-first Python web automation platform inspired by task-driven autonomous agents [12].
* **Perception**: Purely vision-driven. Uses Vision LLMs to comprehend web layouts, map elements to coordinates, and perform clicks/inputs without relying on brittle DOM paths [12].
* **Output capabilities**: Does not output Playwright code. Operates via its own internal visual-planning engine.
* **Deterministic Replay**: No. It is an RPA tool that re-evaluates page screenshots on every execution step to navigate dynamically, which is expensive and slow for CI.
* **Maturity & Backing**: Backed by Skyvern AI (YC). Very active, 22.6k stars, licensed under AGPL-3.0 (strict copyleft).

### LaVague
* **Description**: An open-source framework designed specifically for building AI Web Agents and QA automation [5].
* **Perception**: Utilizes a "World Model" (reasons about state and instruction) and an "Action Engine" that compiles instructions into execution code [5].
* **Output capabilities**: **Yes.** This is LaVague’s core strength. Through **LaVague QA**, it compiles high-level spec files (like Gherkin/Cucumber feature files) into standalone Selenium or Playwright execution code [6].
* **Deterministic Replay**: **Yes.** Because the Action Engine outputs static, standard Playwright/Selenium test scripts, these generated scripts run with 100% deterministic replay in CI/CD without calling an LLM.
* **Maturity & Backing**: Backed by LaVague AI. It has 6.3k stars but has seen lower commit frequency recently (last push in early 2025). Licensed under Apache-2.0.

### Notte
* **Description**: A Python web automation library and API platform [10].
* **Perception**: Employs a custom "perception layer" that flattens the live DOM into a highly compressed, numbered action space [11]. It operates via **patchright**, a custom fork of Playwright [10].
* **Output capabilities**: No. It runs actions dynamically using its dynamic agent runtime.
* **Deterministic Replay**: No. It uses an active agent loop, though it allows hybrid scripting (combining manual Playwright selectors and dynamic agent steps).
* **Maturity & Backing**: Backed by Notte Labs. Young but fast-growing (1.9k stars). Note the licensing constraint: **SSPL-1.0** [11].

### Steel.dev
* **Description**: Open-source, hosted browser infrastructure (SaaS) and API purpose-built for AI agents [19].
* **Perception**: Works at the browser hosting level. It includes stealth configurations, residential proxies, session replays, and utility endpoints to convert pages into markdown or screenshots for external LLMs [19].
* **Output capabilities**: None.
* **Deterministic Replay**: Yes, runs any deterministic script (Puppeteer, Playwright, Selenium).
* **Maturity & Backing**: High quality, open-source alternative to Browserbase, rapidly growing with 7.4k stars. Apache-2.0 license.

### HyperAgent
* **Description**: An open-source, TypeScript-native framework by Hyperbrowser that "supercharges Playwright with AI" [7].
* **Perception**: Dual-mode. Standard operations use `page.perform()`, which utilizes a text-only accessibility tree (extremely fast, cheap, and does not require vision models). Complex workflows use `page.ai()`, which uses full screenshots and visual overlays [7].
* **Output capabilities**: No. Instead, you write standard Playwright scripts and augment them inline with `page.perform()` or `page.extract()` [7].
* **Deterministic Replay**: **Yes.** HyperAgent includes built-in **Action Caching** [7]. It records the execution path on the first run and replays it deterministically without LLM calls in CI, only engaging the LLM when self-healing is needed.
* **Maturity & Backing**: Developed by S2 Labs (makers of Hyperbrowser). Under MIT License.

---

## Recommendation for an E2E testing agent

To build a reliable, maintainable, and cost-effective AI-driven E2E testing agent, we must strictly separate the **Authoring Phase** from the **Execution Phase**.

```
                           ┌────────────────────────────────────────┐
                           │      Natural Language User Intent      │
                           └───────────────────┬────────────────────┘
                                               │
                                               ▼
                    ┌─────────────────────────────────────────────────────┐
                    │                   AUTHORING PHASE                   │
                    │   (Exploratory, LLM-Heavy, Scaled on Cloud Browser) │
                    └──────────────────────────┬──────────────────────────┘
                                               │
                             ┌─────────────────┴─────────────────┐
                             ▼                                   ▼
                ┌─────────────────────────┐         ┌─────────────────────────┐
                │     Option A: Static    │         │     Option B: Hybrid    │
                │     Code Generation     │         │     Action Caching      │
                └────────────┬────────────┘         └────────────┬────────────┘
                             │                                   │
                             │ (Emits pure JS/TS)                │ (Emits Stagehand/
                             │                                   │  HyperAgent scripts)
                             ▼                                   ▼
                    ┌─────────────────────────────────────────────────────┐
                    │                   EXECUTION PHASE                   │
                    │   (Deterministic, Local or CI, Low Latency, $0 LLM) │
                    └──────────────────────────┬──────────────────────────┘
                                               │
                             ┌─────────────────┴─────────────────┐
                             ▼                                   ▼
                ┌─────────────────────────┐         ┌─────────────────────────┐
                │  Runs Standard Playwright│         │ Runs Cached Stagehand / │
                │   Tests (100% Selectors)│         │       HyperAgent        │
                │                         │         │  (Self-heals if failed) │
                └─────────────────────────┘         └─────────────────────────┘
```

### 1. The Authoring Phase (Exploratory & Expensive)
* **Goal**: Understand a natural language requirement, explore the live application UI, discover element locators, and output a repeatable test workflow.
* **Recommended Stack**: **Stagehand** or **HyperAgent** running on **Browserbase** or **Steel.dev**.
* **Rationale**: 
  * The agent driving the browser needs rich visual and DOM context. Using a cloud browser infrastructure provider like **Browserbase** or **Steel.dev** is crucial here because they provide stealth engines (bypassing anti-bot walls during testing) and offer a live visual stream/recording stream.
  * We can use Stagehand's `act()` and `extract()` to write a high-level test script. Stagehand's backend leverages a reasoning model (like Claude 3.5 Sonnet) to perform the exploratory actions on the page.

### 2. The Execution Phase (Deterministic & Cheap)
* **Goal**: Run the tests repeatedly in CI/CD pipelines. This must be fast, cost pennies, and have 100% deterministic success rates.
* **Recommended Stack**: **Standard Playwright TS** or **Stagehand with Caching Enabled**.
* **Rationale**:
  * **Option A (Pure Playwright Code)**: The testing agent generates static Playwright test scripts during the Authoring Phase (relying on LLM reasoning to output stable CSS selectors and `await page.click(...)` commands). These run in CI/CD with $0 LLM token cost and zero planning latency. If a test breaks due to a frontend change, the testing agent is invoked *asynchronously* to inspect the error, execute a self-healing cycle, and commit a PR with the updated selectors.
  * **Option B (Stagehand / HyperAgent in Cached Mode)**: Write the tests in Stagehand/HyperAgent. When run in CI, **Action Caching** is turned on. The runner executes the tests using standard selectors stored in the cache. No LLM calls are made under normal circumstances. If a locator breaks, the framework automatically catches the exception, makes a single LLM call to find the new locator (Self-Healing), updates the cache file, and proceeds. This minimizes flakiness and drastically reduces maintenance overhead.

### Strategic Summary
For our AI testing agent project, we should pursue **Option B with Stagehand or HyperAgent**. It strikes the ultimate balance: developers/agents write natural language-like test code that is incredibly easy to maintain, while the framework's caching mechanism ensures that daily CI runs are extremely cheap and deterministic, only paying for LLM tokens when the site actually changes.

---

## Unverified / Needs follow-up

* **Agent-E**: The repository `Emergent-Behavior/Agent-E` currently returns a 404 error, and the organization has no public repositories on GitHub. It is highly likely that the project has been deleted, archived, or made private. Its current status and code accessibility are unverified.
* **Midscene.js Visual Caching Reliability**: While Midscene.js documentation highlights visual caching support, the stability of visual-only caching under minor styling/layout variations (e.g., small CSS animations or dark/light mode toggles) remains unverified in heavy CI environments and requires physical testing.

---

## Sources

1. [Stagehand GitHub Repository](https://github.com/browserbase/stagehand) — *"Stagehand is a browser automation framework used to control web browsers with natural language and code... auto-caching combined with self-healing remembers previous actions, runs without LLM inference, and knows when to involve AI"*
2. [Browserbase Platform](https://www.browserbase.com) — Hosted serverless browser infrastructure for AI agents.
3. [browser-use GitHub Repository](https://github.com/browser-use/browser-use) — *"Browser Use lets an AI agent use a web browser the same way you do — it opens pages, clicks buttons, types, and fills in forms."*
4. [Skyvern GitHub Repository](https://github.com/Skyvern-AI/skyvern) — *"Instead of only relying on code-defined XPath interactions, Skyvern relies on Vision LLMs to learn and interact with the websites."*
5. [LaVague GitHub Repository](https://github.com/lavague-ai/LaVague) — *"Large Action Model framework designed for developers who want to create AI Web Agents."*
6. [LaVague QA Documentation](https://docs.lavague.ai/en/latest/docs/lavague-qa/quick-tour/) — *"LaVague QA... allows you to automate test writing by turning Gherkin specs into easy-to-integrate tests."*
7. [HyperAgent GitHub Repository](https://github.com/hyperbrowserai/HyperAgent) — *"AI Browser Automation... Action Caching – Record and replay workflows deterministically without LLM calls... page.perform() uses accessibility tree (no screenshots)..."*
8. [Playwright MCP GitHub Repository](https://github.com/microsoft/playwright-mcp) — *"This server enables LLMs to interact with web pages through structured accessibility snapshots, bypassing the need for screenshots or visually-tuned models."*
9. [Chrome DevTools MCP GitHub Repository](https://github.com/ChromeDevTools/chrome-devtools-mcp) — *"Chrome DevTools for agents (chrome-devtools-mcp) lets your coding agent... control and inspect a live Chrome browser."*
10. [Notte GitHub Repository](https://github.com/nottelabs/notte) — *"Best cloud browser infrastructure and web automation platform... Combines AI agents with traditional scripting... patchright install --with-deps chromium"*
11. [Notte Cookbook & Documentation](https://github.com/steel-dev/steel-cookbook/tree/main/examples/notte) — *"Notte builds its agent on top of a perception layer. Each step, notte.Session flattens the live DOM into a compact action space..."*
12. [Skyvern Website & Architecture](https://www.skyvern.com) — AI agent workflow automation with vision LLM comprehension.
13. [Playwright MCP NPM Registry](https://www.npmjs.com/package/@playwright/mcp) — Package details for official Playwright MCP server.
14. [Chrome DevTools MCP Slim Reference](https://github.com/ChromeDevTools/chrome-devtools-mcp/blob/main/docs/slim-tool-reference.md) — Slim mode definitions and CDP actions.
15. [Browser Use Documentation](https://docs.browser-use.com/open-source/introduction) — Core framework and custom skills implementation.
16. [Stagehand Documentation](https://docs.stagehand.dev) — Core API reference for TS/JS and Python versions.
17. [Midscene.js Homepage](https://midscenejs.com) — AI-powered visual assertions and test runner integrations.
18. [Midscene.js Model Strategy](https://midscenejs.com/model-strategy) — Pure vision UI localization and multimodal capabilities.
19. [Steel.dev Homepage](https://steel.dev) — Open-source browser API and cloud infrastructure details.
