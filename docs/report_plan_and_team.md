# Report outline and three-person work allocation

## Readiness decision

The current implementation has enough technical substance and numerical evidence to start the CO4031 report. The warehouse and ETL should remain central; the single Logistic Regression model demonstrates a decision-support component rather than replacing the DW discussion. See report_evidence.md for verified numbers, source_data_profile.md for source-quality findings, data_dictionary.md for contracts, modeling.md for the model/scenario, and diagrams/warehouse_and_dss.md for diagram sources.

Remaining submission work includes report writing, rendered diagrams, current screenshots, slides, a rehearsed demonstration, and a video link if the team uses the video presentation option. Existing functional checks do not establish cold-start portability or responsive visual quality. Suggested lengths below are editorial guidance, not assignment rules.

## Proposed team ownership

Use Member A/B/C as placeholders until names are assigned. This allocates the remaining work and technical ownership; it must not be presented as evidence that these people authored existing code. Record actual contributions and review work honestly.

| Member | Primary responsibility | Files and evidence to understand | Report sections to lead | Concrete remaining deliverables |
| --- | --- | --- | --- | --- |
| A — Source data and ETL | Dataset scope, profiling, staging, cleaning, orchestration and reconciliation | src/etl/, three DAGs, Docker configuration, source_data_profile.md | Chapters 1, 2 and 4; ETL subsection of Chapter 7 | Source relationship figure; ETL flow; quality-rules table; successful DAG screenshots; source/ETL narrative; explain rollback and manual DAG ordering |
| B — DW, OLAP and sales interface | Business grain, dimensions/facts, shared dates, KPI definitions, analytical SQL, Overview and Sales analysis | DW DDL/load logic jointly with A; src/app/data.py sales queries; pages 1–2; data_dictionary.md | Chapters 3 and 5; sales findings in Chapter 7; assemble the final report layout | Rendered DW diagram; concise data dictionary; KPI table; SQL examples; current sales-page screenshots; cross-check every report number against report_evidence.md |
| C — DSS and evaluation | Feature construction, notebook, single-model pipeline, test-only review planning and historical evaluation | src/ml/, notebook, page 3, risk-data queries, modeling.md | Chapter 6; model/scenario results in Chapter 7; lead Chapter 8 with input from A/B | Feature/label table; model metrics; capacity-scenario table/curve; page-3 screenshots; model limitations and proposed improvements; end-to-end demo script |

Each member writes and explains their own sections. B integrates formatting and references, not all technical writing; C coordinates the demo, not all testing. A reviews DW/ETL consistency with B; B reviews DSS amounts/denominators with C; C reviews label/feature timing with A. All three verify the final results and can explain the architecture, fact grains, canceled-order rule and test-only simulation.

## Suggested report structure

Suggested title: **An E-commerce Data Warehouse and Decision Support System for Sales Analysis and Late-delivery Risk Prioritisation**.

Use approximately 24–30 main-content pages if the team can explain them clearly; shorten repeated tables and put detailed schema/notebook output in appendices. Do not add material merely to reach a page count.

### Front matter

- Cover: course, project, team members/student IDs, instructor and submission date; video link when applicable.
- Abstract: business problem, DW/ETL, analytical interface, single-model DSS and measured limitations.
- Table of contents; lists of figures/tables if useful.
- Actual contribution table, completed after the work is done.

### Chapter 1 — Introduction and Business Requirements (about 2 pages)

1. Marketplace context and why historical sales/delivery analysis is useful.
2. Target users: business analyst/sales manager and fulfilment operations reviewer.
3. Four business questions: revenue trend, category/state contribution, delivery timeliness trend, and allocation of limited review capacity.
4. Scope: seven loaded CSV files, PostgreSQL warehouse, manual Airflow ETL, three Streamlit pages, one Logistic Regression model.
5. Decision to support: choose a review capacity and a prioritised order list. State explicitly that the dataset is historical.

Output: a requirements-to-system table mapping each question to a fact/query/page and a measurable result. Avoid unsupported claims about actual Olist operational improvements.

### Chapter 2 — Source Data and Data-quality Analysis (about 3 pages)

1. Dataset source, time coverage, seven selected files and two excluded files.
2. Source entity relationships and source grains; distinguish customer_id from customer_unique_id.
3. Counts, missing fields, key uniqueness and reference checks.
4. Important findings: missing/untranslated categories, zero product weights, contradictory carrier timestamps and reused/multiple reviews.
5. Cleaning policy: preserve raw/staging, type and standardise in DW, flag anomalies, define ineligible delivery measures as NULL.

Evidence: source_data_profile.md, profiler, staging checks. Include only quality findings that influence the design; put full profiling distributions in an appendix.

### Chapter 3 — Dimensional Warehouse Design (about 4 pages)

1. Business processes and separate grains for sales items and order deliveries.
2. Four dimensions and two facts; explain the shared-dimension fact constellation and role-playing dates.
3. Business keys, surrogate keys, primary/foreign keys and nullable date roles.
4. Measures and aggregation behaviour: revenue/freight additive, distinct orders and rates require correct aggregation.
5. Selected physical types, constraints and indexes, with rationale.
6. Explain review aggregation before attaching it to order-level delivery data; avoid fact-grain multiplication.

Output: rendered warehouse diagram, table/row/column counts, compact field dictionary, source-to-target mapping examples. Keep the complete field dictionary in an appendix or linked docs.

### Chapter 4 — ETL and Data Validation (about 3 pages)

1. Deployment architecture: analytical PostgreSQL and separate Airflow metadata database.
2. Source profile → staging load/validation → DW load/validation → feature mart/validation.
3. Key transformations: type conversion, label standardisation, category fallback, physical anomaly handling, review deduplication/aggregation and date-based lateness.
4. Three manual DAGs and a separate local training/scoring command; do not claim automatic cross-DAG scheduling.
5. Transactions/rollback, score invalidation and recovery sequence after a refresh.
6. Validation results: 31 staging, 17 DW and 6 feature checks; supplementary per-order reconciliation from the final audit.

Output: ETL diagram, rule table, validation summary and successful run screenshots. Do not report ETL execution times unless actually measured.

### Chapter 5 — OLAP Queries and Sales Dashboard (about 3 pages)

1. Define revenue, order count, AOV, category revenue per order and late-delivery rate with explicit denominators.
2. Revenue/order aggregation by purchase month; category and customer-state breakdown; date slicing.
3. Selected SQL queries and their fact/dimension relationships.
4. Explain Overview and Sales analysis with current screenshots and two or three concrete findings.
5. State limitations: top-10 lists, limited drill-down, no dedicated cube server and no live transaction feed.

Use the agreed scope: canceled orders are excluded from sales measures; other statuses remain; freight is separate. Category counts overlap. Do not call category revenue per order full-basket AOV or call all included revenue completed/paid sales.

### Chapter 6 — Decision Support Design and Model (about 4 pages)

1. DSS architecture: data management, model execution/metadata and interactive review planning.
2. Decision process: identify delivery-risk problem, choose capacity, inspect prioritised orders, compare scenarios and propose human verification actions.
3. Prediction point, eligible population, calendar-date target and leakage exclusions.
4. Six model features and business rationale; purchase weekday considered but excluded.
5. Preprocessing and Logistic Regression; justify interpretability and the deliberately single-model scope.
6. Chronological train/validation/test roles, fixed alert threshold and capacity ranking as separate policies.
7. Model management in this implementation: training, saved pipeline/metadata, evaluation, scoring and freshness checks. Do not claim multi-model selection, a version registry or automatic retraining.
8. Orders to monitor and separate historical evaluation. Explain the simulation even though the monitoring-table title omits “simulated”.

Output: feature/label table, split table, decision-workflow figure and page-3 screenshot. The notebook supports the analysis; it is not copied wholesale into the main report.

### Chapter 7 — Results and Evaluation (about 3–4 pages)

1. Technical correctness: validation outcomes, table counts, revenue reconciliation, score/metadata matching and functional dashboard checks.
2. Business observations: non-canceled revenue, sales order count, delivery late rate and top revenue groups.
3. Model metrics: average precision (PR-AUC), ROC-AUC and Brier; explain prevalence and avoid using majority-class accuracy as the main conclusion.
4. Capacity scenarios: at least 5%, 10% and 20% on test orders. Show reviewed, late captured, coverage, precision and expected random baseline/lift.
5. Discuss the practical trade-off: capacity catches some late orders but includes many on-time orders and leaves other late orders unreviewed.
6. Verification limits: no cold-start portability test or measured intervention effect; functional AppTest does not prove screenshot layout quality.

Primary source: report_evidence.md. Do not mix fixed-threshold results (1,848 test flags) with the 10% capacity list (1,446 orders). Do not mix all warehouse orders, sales orders with item lines, timeliness-eligible orders and ML-eligible labelled orders.

### Chapter 8 — Limitations, Proposed Improvements and Conclusion (about 2 pages)

1. Modest predictive strength, limited static pre-delivery features and coarse geography.
2. Performance changes across periods, probability-calibration uncertainty and historical selection effects.
3. Row-based date boundaries and training-label maturity limitations.
4. No live ingestion, no causal delay explanation and no proof of prevented delays or savings.
5. Prioritised future work: richer valid early features, rolling-time evaluation, cost-aware review capacity, calibration inspection and prospective validation if a live source becomes available.
6. Summarise the implemented DW/ETL/OLAP/DSS contribution and its measured scope.

Use the limitation-to-improvement table in modeling.md. Clearly distinguish future proposals from implemented features. Retain one model; no extra model is needed for this report structure.

### References and appendices

- Cite the dataset provider and the references actually used for dimensional design, DSS and Logistic Regression/evaluation.
- Appendix A: complete field dictionary and source-to-target mapping.
- Appendix B: quality checks and validation logs.
- Appendix C: selected notebook tables, with short interpretations; use scientific notation for small p-values.
- Appendix D: reproduction commands, repository/data access and environment requirements; exclude credentials.

## Tables and figures checklist

| Item | Existing evidence/source | Remaining action | Owner |
| --- | --- | --- | --- |
| Requirements traceability | README business questions and implemented pages | Write concise mapping | A with B/C |
| Source inventory and quality findings | source_data_profile.md | Select relevant rows; draw source relationships | A |
| Warehouse diagram and grains | diagrams/warehouse_and_dss.md; data_dictionary.md | Render/export diagram | B |
| ETL and validation | DAGs; report_evidence.md; tmp/review/final_validation.txt | Capture successful runs and explain ordering | A |
| Overview and category/state results | report_evidence.md; pages 1–2 | Capture current filtered screenshots and interpret findings | B |
| Feature rationale, split and metrics | modeling.md; report_evidence.md; notebook | Select understandable evidence | C |
| Capacity scenarios and monitoring list | report_evidence.md; page 3 | Capture 10% view and compare 5/20% scenarios | C |
| Limitations and future work | modeling.md | Condense into report discussion | C with A/B |
| Actual contribution record | Team work history | Record real tasks and peer reviews | All |

## Presentation and final review

For a 15-minute live presentation, assign roughly 5 minutes each: A introduces the problem/data and ETL; B explains DW/OLAP and sales pages; C explains DSS, test-only results, limitations and the conclusion. For a 10–15-minute video, all members must appear and present. Rehearse transitions and keep one stable demo environment; prepare current screenshots as fallback.

Each member should be able to answer: Why two fact grains? Why exclude canceled orders from revenue but preserve them in DW? Why use calendar dates for lateness? Why is the dashboard test-only? What does 18% coverage at 10% capacity mean? Why does model probability not mean model accuracy? What does a failed/mismatched score check do?

Suggested remaining schedule: draft owned chapters first, then cross-review numbers/definitions, assemble report/figures, rehearse the full demo, and finally package the PDF report, source/data links, PDF slides and video link if applicable. The assignment PDF states a submission deadline of 23:59 on 2026-11-15 (Asia/Saigon); verify any later class announcements separately.
