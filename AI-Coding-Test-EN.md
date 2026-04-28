# AI Coding Test (2026 Update)

## About This Test

This test is not about whether you can produce working code — AI tools have made that relatively easy. What we want to see is how you collaborate with AI to turn one-off prototypes into reliable systems when facing **ambiguous, messy, judgment-requiring** problems.

A few things we care about:

- **Evaluation discipline** — how you know your system is correct
- **Systematic thinking** — decomposing messy real-world data that fails in many ways
- **Engineering tradeoffs** — judgment about cost, latency, and reliability
- **AI collaboration quality** — whether your interaction with AI amplifies your output

## Tasks

Three tasks below. **Complete at least one**; completing more than one is a significant plus.

- Task 1: GitHub CI/CD as Claude Skills
- Task 2: Generalized Browser Automation Agent
- Task 3: SEC 10-K Item-level Structured Extraction

## Common Requirements

1. **AI-first workflow** — Claude Code preferred; using Skills is a plus. Reference: [https://kaochenlong.com/claude-code-skills](https://kaochenlong.com/claude-code-skills)
2. **Git** — public repo with commit history that reflects your actual development process
3. **Zeabur deployment** — all tasks must be deployed as publicly accessible services ([https://zeabur.com/](https://zeabur.com/)); include the URL
4. **Prompt records** — keep a `prompts/` folder in the repo root with your key prompts — we will actually read them
5. **README** — how to run, key design decisions, where AI helped you
6. Public or self-created material only. Submit by the day before your interview.

---

## Task 1: GitHub CI/CD as Claude Skills

Package common GitHub CI/CD workflows into a few reusable Claude Skills (e.g. lint-and-test, build-and-release, dependency-audit, security-scan). Each Skill should have clear inputs and outputs, safe execution boundaries, and proper error handling.

Deploy a demo on Zeabur (Web UI or API) that lets us see your Skills running against a real repo.

**What we'll look at**: how you drew Skill boundaries, auth and safety awareness, idempotency, and whether your Skill descriptions trigger Claude precisely.

---

## Task 2: Generalized Browser Automation Agent

Build a browser agent that accepts **natural language task descriptions** and reliably executes them across different sites. Beyond basic execution, the agent should demonstrate:

- **Self-correction** — diagnose the cause on failure and try different strategies
- **Self-maintenance** — detect UI or selector changes and adjust locator strategies dynamically

Build your own evaluation set to test reliability (covering diverse domains and task types), and deploy on Zeabur with an interface that accepts tasks. We will verify with our own unseen tasks.

**What we'll look at**: substance of the self-correction / self-maintenance mechanisms (not just try/except retries), depth of the evaluation set, silent-failure prevention.

---

## Task 3: SEC 10-K Item-level Structured Extraction

10-Ks have an SEC-specified structure (Items 1–16 across Parts I–IV), but actual file formats vary enormously — inconsistent HTML, diverse heading styles, older plain-text filings, "incorporated by reference" sections, "Not Applicable" / "Reserved" items.

Build a pipeline that takes a 10-K (by CIK + accession number or file URL) and outputs structured JSON, with each item containing `part`, `item_number`, `item_title`, `content_text`, `char_range`, and `status` (`extracted` / `incorporated_by_reference` / `not_applicable` / `reserved`). Deploy on Zeabur as an API — we will call it with our own selected filings.

**Data sources (SEC official APIs, free)**:

- API overview: [https://www.sec.gov/search-filings/edgar-application-programming-interfaces](https://www.sec.gov/search-filings/edgar-application-programming-interfaces)
- Submissions API: `https://data.sec.gov/submissions/CIK{10-digit-padded}.json`
- Full-text Search: `https://efts.sec.gov/LATEST/search-index?q={query}&forms=10-K`
- Raw file downloads: `https://www.sec.gov/Archives/edgar/data/{CIK}/{accession-no-dashes}/{filename}`
- XBRL Company Facts (useful for cross-validation): `https://data.sec.gov/api/xbrl/companyfacts/CIK{10-digit-padded}.json`
- Rules: requires `User-Agent` header, 10 req/sec, no API key

Build your own evaluation set (diverse industries, years, company sizes, including older formats), and report accuracy, failure modes, and cost/latency.

**What we'll look at**: whether your eval set intentionally stresses edge cases, your parsing strategy tradeoffs (rules vs LLM vs hybrid), how you verify yourself without public ground truth, handling of "incorporated by reference" cases, cost discipline.

---

## How We Evaluate

After submission we run held-out tests against your deployed system using data outside your eval set, read your code, documentation and prompt records, and discuss design decisions with you in the interview.

Roughly three levels:

- **A** — eval design has depth, system shows layered/weighted tradeoffs, failure modes honestly surfaced, prompt records show high-quality AI collaboration
- **B** — basic functionality works, but eval and analysis stay on the surface
- **C** — only the happy path works

## Submission

By the day before your interview, send: public Git repo URL, Zeabur URL(s), and any supplementary notes. Good luck.
