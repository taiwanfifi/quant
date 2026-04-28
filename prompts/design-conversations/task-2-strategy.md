# Gemini Task 2 Strategy (2026-04-28)


## Round 1: option pick

### Q
```
Task 2 of an SEC/CI/Browser portfolio (1-month interview project).

REQUIREMENT (verbatim from spec):
"Build a browser agent that accepts natural language task descriptions and reliably
executes them across different sites. Beyond basic execution, the agent should
demonstrate:
  - Self-correction — ...
```

### A
Go with **Option D**. It offers the highest ROI by leveraging `browser-use` for the heavy lifting of DOM manipulation while focusing your limited 4-5 days on the specific project requirements: **self-correction** and **self-maintenance**. By building a wrapper layer for verification and drift reporting, you satisfy the "substance" requirement without reinventing the browser driver or the action registry. This hybrid approach also simplifies the Zeabur deployment, as you can treat the underlying agent as a black-box execution engine and concentrate your logic on the "silent-failure prevention" they explicitly asked for.

---

### Entry-Point Skill Frontmatter

```markdown
---
name: browser-executive
description: Starts with a natural language task description and orchestrates a self-correcting browser session to achieve the goal. It executes actions via DOM-traversal, verifies state transitions after every step to prevent silent failures, and generates a DriftReport if previously known selectors no longer match the live UI.
---
```

### Strategic Implementation Note
Since you are deploying on **Zeabur**, ensure your Dockerfile uses the `mcr.microsoft.com/playwright:v1.49.0-noble` (or similar) base image. Zeabur's serverless/container environment can be finicky with browser dependencies; keeping the "verification" logic in your application code while letting Playwright handle the headless heavy lifting is the safest path to a stable deployment.

## Round 2: skill catalog

### Q
```
OK now: list the 5-7 sub-skills for Task 2 in the same agentskills.io format,
each with:
  - name (kebab-case)
  - one-line description (capability + trigger phrase)
  - what it produces
  - what it d
```

### A
Here are the sub-skills for the Task 2 Browser Agent, designed to satisfy the self-correction and self-maintenance requirements:

### Sub-Skills Registry

* **`task-planner`**
    * **Description:** Breaks down the high-level natural language prompt into a sequential execution graph triggered by a new task request.
    * **Produces:** A JSON-formatted step-by-step execution plan with success criteria for each node.
    * **Depends on:** None.

* **`smart-navigator`**
    * **Description:** Manages URL transitions and ensures the page has reached a stable "network-idle" state before handing off control.
    * **Produces:** A confirmed page state object including the current URL and a visual/DOM snapshot.
    * **Depends on:** `task-planner`.

* **`resilient-locator`**
    * **Description:** Implements the 5-tier cascade (CSS, XPath, ARIA, text, vision) to find elements when the primary selector fails or changes.
    * **Produces:** A valid element handle and a "DriftReport" if the fallback strategy was required to find the target.
    * **Depends on:** `smart-navigator`.

* **`action-executor`**
    * **Description:** Performs interactions like `fill-form` or `click-element` using the locators provided by the resilient-locator skill.
    * **Produces:** A raw execution result from the browser driver (Playwright/browser-use).
    * **Depends on:** `resilient-locator`.

* **`state-verifier`**
    * **Description:** Compares the post-action DOM and screenshot against the step's success criteria to detect silent failures.
    * **Produces:** A boolean status and a "Difference Map" showing what changed on the page.
    * **Depends on:** `action-executor`.

* **`self-correction-loop`**
    * **Description:** Diagnoses the root cause of a `state-verifier` failure (e.g., popup, CAPTCHA, or layout shift) and triggers a re-plan.
    * **Produces:** An updated execution plan or a specialized "recovery action" (like closing a modal).
    * **Depends on:** `state-verifier`, `task-planner`.

* **`data-extractor`**
    * **Description:** Scrapes specific information from the final page state using schema-based extraction once all navigation steps are complete.
    * **Produces:** A structured JSON object containing the data requested in the original task.
    * **Depends on:** `state-verifier`.

## Round 3: drift report shape

### Q
```
Final round. The "drift report" is the A+++ angle: detect that selectors changed
+ log structured diff + suggest fix WITHOUT auto-patching.

Give me the JSON shape of `drift_report.json` (fields, type
```

### A
The **`resilient-locator`** skill writes this report immediately upon the failure of a "Primary" selector (sourced from the cached registry or plan) and the subsequent success of a "Fallback" strategy (e.g., finding the element via ARIA labels or Vision after CSS failed). It is triggered when the `confidence_score` of the primary locator hits 0, but a secondary strategy resolves to a valid element handle with the same functional signature. Writing the report at the locator level ensures the agent captures the "drift" before the action is even attempted, providing a clean audit trail for the **`self-maintenance`** requirement without introducing the side effects of auto-patching the codebase.

```json
{
  "timestamp": "2026-04-28T20:30:15Z",
  "task_id": "tx-9921-checkout",
  "url": "https://example.com/cart",
  "drift_event": {
    "target_label": "submit_order_button",
    "status": "LOCATOR_MISMATCH",
    "primary_failure": {
      "selector": "button#place-order-v2",
      "strategy": "CSS",
      "error": "TimeoutError: element not found"
    },
    "fallback_success": {
      "selector": "//button[contains(text(), 'Complete Purchase')]",
      "strategy": "XPath",
      "confidence": 0.98,
      "attributes_changed": ["id", "text_content"]
    }
  },
  "diff": {
    "old_state": { "id": "place-order-v2", "text": "Place Order" },
    "new_state": { "id": "btn-final-66", "text": "Complete Purchase" }
  },
  "remediation_suggestion": "Update SkillsRegistry 'submit_order_button' to use ARIA label 'Complete Purchase' or XPath to accommodate dynamic ID suffix."
}
```
