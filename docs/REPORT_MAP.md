# CloudGuard — Final Report Section Map

How the project's phases and artifacts map onto a standard FYP report. For each
section: what to write, which **phase(s)** it draws on, and the exact **evidence**
(screenshots, diagrams, test output) to drop in.

> Artifacts you already have:
> - **Screenshots:** `docs/screenshots/dashboard-light.png`, `dashboard-dark.png`,
>   `charts-detail.png`, `empty-state.png` *(still to capture: Login/Register,
>   Settings, Alerts list, Recommendations with the savings banner — grab these
>   from the live site for full coverage)*.
> - **Diagrams:** the system diagram in `docs/ARCHITECTURE.md` (redraw in Excalidraw),
>   the data model (Section 3 of ARCHITECTURE.md), and the data-flow steps (Section 4).
> - **Test output:** `pytest --cov` → **100 tests, ~82% coverage**; the CI run on
>   GitHub Actions (green badge + run logs).
> - **Live system:** https://cloudcostguard-fyp.duckdns.org and the CI page.

---

| Report section | Draws on | What to write | Evidence to include |
|----------------|----------|---------------|---------------------|
| **1. Introduction** | Phase 1, README pitch | The problem (AWS bills are opaque; the console is clunky), your aim (a self-hosted single-dashboard alternative with anomaly + waste detection), and scope. | README pitch paragraph; a hero **dashboard screenshot**; the live-demo URL. |
| **2. Background / Literature** | — | AWS Cost Explorer & billing model; why cost management matters (FinOps); the z-score idea for anomaly detection; survey of existing tools (AWS Cost Anomaly Detection, CloudHealth) and the gap you fill. | A small comparison table (CloudGuard vs. console vs. commercial tools). |
| **3. Requirements** | Phases 1–6 goals | Functional (auth, connect read-only keys, view costs, detect anomalies, recommend savings) and non-functional (security, HTTPS, testability, deployability) requirements. | A requirements table; map each requirement → the phase that delivered it. |
| **4. Design** | Phases 1–6 architecture | System architecture, the four-container layout, data model, key design decisions and trade-offs. | **Excalidraw system diagram** (ARCHITECTURE.md §1 + §6); **data-model diagram** (§3); design-decisions list (§5). |
| **5. Implementation** | Phases 2–6 | Walk through each subsystem: cost API, scheduler, anomaly detector, waste scanner + estimator, auth + Fernet encryption, frontend. Highlight notable code (async + `to_thread`, idempotent upserts, validate-before-save). | Short annotated **code snippets**; the API endpoint table (README); the per-phase roadmap (README). |
| **6. Testing** | Phases 2–6 test suites | Testing strategy: pure-unit (detector, estimator), service tests with **moto**, API tests, and an **end-to-end** spike→alert→email→API test. Coverage. | `pytest --cov` **terminal output (100 tests / 82%)**; the test-file table (README); a couple of representative test snippets. |
| **7. Deployment & DevOps** | Phases 6.3–6.5 | Containerization (multi-stage images), Compose stack, Caddy auto-TLS, the EC2 deployment, and the CI/CD pipeline. | `docs/deploy.md`; **CI green badge + GitHub Actions run screenshot**; the live HTTPS site (padlock); `docker-compose.prod.yml` excerpt. |
| **8. Evaluation** | All phases | Does it meet the requirements? What works well; performance (DB-first reads); the demo (anomaly fires, recommendation appears). Honest limitations — esp. **scheduler uses env credentials, not per-user keys** (ARCHITECTURE.md §5). | **Alerts screenshot** (a fired anomaly via the spike injector); **Recommendations screenshot** with the savings banner; the demo script in `docs/anomaly-detection.md`. |
| **9. Conclusion** | — | Restate what was built and achieved against the original aim. | — |
| **10. Future Work** | ARCHITECTURE.md §5 | Per-user credentials driving per-user scheduled scans (true multi-tenant); live AWS Pricing API instead of the offline table; more anomaly methods; auto-enabling CD; budgets/forecasting. | — |
| **Appendices** | — | Full API reference, README, user guide, environment variables, IAM policy used. | README, `docs/USER_GUIDE.md`, `backend/.env.example`. |

---

## Phase → section quick index

| Phase | Primary report home |
|-------|---------------------|
| 1 — Setup, Docker, first migration | Design, Deployment |
| 2 — Cost API + sync job | Implementation, Testing |
| 3 — React dashboard | Implementation, Evaluation (UI screenshots) |
| 4 — Anomaly detection + alerts + email | Implementation, Testing, Evaluation |
| 5 — Waste scanner + recommendations | Implementation, Testing, Evaluation |
| 6.1–6.2 — Auth + encrypted credentials | Design (security), Implementation |
| 6.3–6.4 — Containerization + EC2 deploy | Deployment |
| 6.5 — CI/CD | Deployment, Testing |
| 6.6 — Documentation | Appendices, and the source for every other section |

---

## Evidence still worth capturing for a complete report

- [ ] Login + Register screens
- [ ] Settings page (with the "use read-only credentials" warning and a saved/masked key)
- [ ] Alerts page showing at least one fired anomaly (use the spike injector)
- [ ] Recommendations page showing the savings hero banner + ranked cards
- [ ] GitHub Actions run page (green CI, both jobs)
- [ ] The live site with the browser padlock visible (proof of HTTPS)
- [ ] `pytest --cov` terminal output pasted as a figure
