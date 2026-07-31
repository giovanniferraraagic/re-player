# Test specification formats & Azure DevOps mapping
Date checked: 2026-07-31

> Source: sub-agent research (gpt-5.4-mini). This file was judged reliable: it cites deep Microsoft Learn URLs, gives concrete examples, and is explicit about what it could NOT verify. Unverified items are listed at the end rather than glossed over.

## Executive summary
- Gherkin is the de facto BDD syntax, maintained in the Cucumber project (`cucumber/gherkin`), and the reference docs explicitly model scenarios as executable specs with step definitions (https://cucumber.io/docs/gherkin/reference/, https://github.com/cucumber/gherkin).
- The Cucumber docs also discourage UI/implementation coupling: "Implementation details should be hidden in the step definitions," and "Then" should assert observable outcomes, not internal state (https://cucumber.io/docs/gherkin/reference/).
- Playwright itself is code-first: the official surface is `test()`, `test.step()`, tags, annotations, and reporters; BDD support is third-party (`playwright-bdd`) (https://playwright.dev/docs/api/class-test#test-step, https://playwright.dev/docs/test-reporters, https://github.com/vitalets/playwright-bdd).
- Azure DevOps Test Plans is step-table native: public docs say test cases have steps with **Action** and **Expected Result**, plus shared steps, shared parameters, suites, and requirement links (https://learn.microsoft.com/en-us/azure/devops/test/create-test-cases?view=azure-devops, https://learn.microsoft.com/en-us/azure/devops/test/test-objects-overview?view=azure-devops).
- The best future-export shape for Azure DevOps is the ADO-style step table: Microsoft's own bulk import/export docs use `Test Step`, `Step Action`, and `Step Expected`, one row per step (https://learn.microsoft.com/en-us/azure/devops/test/bulk-import-export-test-cases?view=azure-devops).
- ISO/IEC/IEEE 29119-3 is the formal documentation standard, but a public, practical authoring spec could not be verified from the ISO site; treat it as governance/reference, not a working format (https://www.iso.org/search.html?q=29119-3).
- Recommendation: make the canonical spec an Azure DevOps-style step table with lightweight metadata; generate Playwright tests from it. Main risk: complex branching/reuse is less expressive than code, so you need conventions for shared steps and parameters.

## Candidate formats

### Gherkin / BDD
Gherkin is readable and good for business language, but it is not an ADO-shaped artifact. The docs say: "The trailing portion (after the keyword) of each step is matched to a code block, called a step definition." and "Implementation details should be hidden in the step definitions." (https://cucumber.io/docs/gherkin/reference/)

Concrete example:
```gherkin
Feature: Sign in
  Scenario: Valid user signs in
    Given I am on the login page
    When I sign in with valid credentials
    Then I see the dashboard
```

Why it's weaker here:
- Step definitions create glue-code overhead.
- UI-heavy wording is discouraged.
- Mapping to ADO loses the step-table shape unless you transform scenarios into rows.

### ISO/IEC/IEEE 29119-3
This is the formal standard family for test documentation, but the public ISO page was not practically usable for authoring details during this check, so it is not treated as a day-to-day spec format (https://www.iso.org/search.html?q=29119-3).

Verdict:
- Strong for governance and auditability.
- Too heavyweight / inaccessible for fast LLM-assisted authoring.

### Azure DevOps-style step tables
This is the closest match to the target system. Azure's docs say: "Add test steps with an Action and Expected Result for each step." and bulk import/export says: "Each test step is a separate row." (https://learn.microsoft.com/en-us/azure/devops/test/create-test-cases?view=azure-devops, https://learn.microsoft.com/en-us/azure/devops/test/bulk-import-export-test-cases?view=azure-devops)

Concrete example:
```markdown
| Test Step | Step Action                                | Step Expected                  |
|----------:|--------------------------------------------|--------------------------------|
| 1         | Navigate to the login page                 | Login form is displayed        |
| 2         | Enter valid credentials and select Sign in | Dashboard is displayed         |
| 3         | Select Sign out                            | User returns to the login page |
```

Why it wins:
- Human-readable.
- Naturally maps to Azure DevOps import/export.
- Easy for an LLM to generate and update row-by-row.
- Minimal transformation loss.

### Playwright-native + structured metadata
Playwright's official semantics are code-centric: `test.step()` "Declares a test step that is shown in the report," and the reporters page says the JSON reporter gives "a comprehensive json file with the test results." Tags and annotations are first-class too (https://playwright.dev/docs/api/class-test#test-step, https://playwright.dev/docs/test-reporters).

Concrete example:
```ts
import { test, expect } from '@playwright/test';

test('valid user signs in', {
  tag: ['@smoke'],
  annotation: [{ type: 'requirement', description: 'REQ-123' }],
}, async ({ page }) => {
  await test.step('Open login page', async () => {
    await page.goto('/login');
  });

  await test.step('Sign in with valid credentials', async () => {
    await page.getByLabel('Username').fill('alice');
    await page.getByLabel('Password').fill('secret');
    await page.getByRole('button', { name: 'Sign in' }).click();
  });

  await test.step('Verify dashboard', async () => {
    await expect(page.getByRole('heading', { name: 'Dashboard' })).toBeVisible();
  });
});
```

Strength:
- Best executable artifact.
- Best reporting/traceability in Playwright.

Weakness:
- Less natural as a supervisor-approved spec.
- Export to ADO is inferred from code, not explicit.

### Other options
- Markdown/YAML wrappers: workable as container formats, but only if you define a schema.
- Playwright-BDD: the most relevant third-party bridge; its home page says BDD scenarios are "valuable artifacts for AI agents" and that it "converts BDD scenarios into native Playwright tests" (https://github.com/vitalets/playwright-bdd, https://vitalets.github.io/playwright-bdd/).
- Robot Framework / TestRail / Xray / Zephyr: viable ecosystems, but they are either keyword-driven or tool-specific rather than an ADO-native supervision format.

## Azure DevOps Test Plans data model
Public Microsoft docs show the shape clearly:

- Test Plans group suites and test cases; test cases can be reused across plans and suites (https://learn.microsoft.com/en-us/azure/devops/test/create-a-test-plan?view=azure-devops, https://learn.microsoft.com/en-us/azure/devops/test/test-objects-overview?view=azure-devops).
- Test cases are work items; "The only required field for all work item types is Title." (https://learn.microsoft.com/en-us/azure/devops/test/test-objects-overview?view=azure-devops).
- Manual test cases define ordered steps with **Action** and **Expected Result** (https://learn.microsoft.com/en-us/azure/devops/test/create-test-cases?view=azure-devops).
- Shared Steps and Shared Parameters are separate work item types linked to test cases (https://learn.microsoft.com/en-us/azure/devops/test/share-steps-between-test-cases?view=azure-devops, https://learn.microsoft.com/en-us/azure/devops/test/repeat-test-with-different-data?view=azure-devops).
- Requirement-based suites automatically link test cases to backlog items; test cases can also link to bugs and requirements (https://learn.microsoft.com/en-us/azure/devops/test/create-test-cases?view=azure-devops).
- Bulk export/import exposes the practical schema as `ID`, `Work Item Type`, `Title`, `Test Step`, `Step Action`, `Step Expected`, `Area Path`, `Assigned To`, and `State`; "Each test step is a separate row." (https://learn.microsoft.com/en-us/azure/devops/test/bulk-import-export-test-cases?view=azure-devops).
- REST creation uses the generic work-item create endpoint: `POST https://dev.azure.com/{organization}/{project}/_apis/wit/workitems/${type}?api-version=7.1` (https://learn.microsoft.com/en-us/rest/api/azure/devops/wit/work-items/create?view=azure-devops-rest-7.1).

Mapping note:
- The public docs make the row-based step model explicit.
- The raw serialized `Microsoft.VSTS.TCM.Steps` payload shape was **NOT** verified from a public Microsoft page during this check. That is the main follow-up item if exact wire-format fidelity is needed.

## Comparison table

| Format | Human readable | LLM-authorable | LLM-updatable | Machine parseable | Maps to ADO Test Case | Maintenance overhead | Verdict |
|---|---|---|---|---|---|---|---|
| Gherkin | High | High | Medium | Medium | Medium | High | Good narration, weaker export fidelity |
| ADO-style step table | High | High | High | High | Very high | Medium | **Best canonical spec** |
| Playwright-native + metadata | Medium | Medium | High | High | Medium | Low | Best executable artifact |
| ISO 29119-3 | Low | Low | Low | Low | High (conceptually) | Very high | Governance only |

## Recommendation
Use **Azure DevOps-style step tables** as the canonical spec format.

Why:
- It matches the target system's native model: title + ordered action/expected step rows + shared steps/parameters + links.
- It is human-readable enough for supervision.
- It is the easiest to export into Azure DevOps Test Plans without lossy transformation.
- It is easy for an LLM to author/update row-by-row.

Operationally:
- Keep Playwright as the executable derivative.
- Mirror step boundaries in `test.step()`.
- Attach tags/requirements in metadata, not in prose.

Main risk:
- Complex branching, reusable flows, and setup semantics can get clumsy in tables. Mitigate with shared steps and shared parameters.

## Note for this project
Playwright's own `planner` agent emits a **Markdown test plan** with numbered steps and bulleted expected outcomes (see `00-playwright-test-agents.md`). That shape is close to, but not identical with, the ADO step table. A deterministic converter between the two is a concrete, small piece of work — and one of the gaps a custom harness can own.

## Unverified / Needs follow-up
- Exact serialized `Microsoft.VSTS.TCM.Steps` field format (raw HTML/XML payload) from Microsoft's public docs: not verified.
- Current/public ISO/IEC/IEEE 29119-3 text and exact test-case-specification clauses: not verified; ISO public search did not yield a usable public authoring page.
- Any native Playwright Cucumber support: only third-party support found (`playwright-bdd`), not an official Playwright-native BDD layer.

## Sources
1. https://cucumber.io/docs/gherkin/reference/
2. https://github.com/cucumber/gherkin
3. https://playwright.dev/docs/api/class-test#test-step
4. https://playwright.dev/docs/test-reporters
5. https://github.com/vitalets/playwright-bdd
6. https://vitalets.github.io/playwright-bdd/
7. https://learn.microsoft.com/en-us/azure/devops/test/create-test-cases?view=azure-devops
8. https://learn.microsoft.com/en-us/azure/devops/test/test-objects-overview?view=azure-devops
9. https://learn.microsoft.com/en-us/azure/devops/test/share-steps-between-test-cases?view=azure-devops
10. https://learn.microsoft.com/en-us/azure/devops/test/repeat-test-with-different-data?view=azure-devops
11. https://learn.microsoft.com/en-us/azure/devops/test/bulk-import-export-test-cases?view=azure-devops
12. https://learn.microsoft.com/en-us/rest/api/azure/devops/wit/work-items/create?view=azure-devops-rest-7.1
13. https://learn.microsoft.com/en-us/rest/api/azure/devops/
14. https://www.iso.org/search.html?q=29119-3
