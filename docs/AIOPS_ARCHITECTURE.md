# Langfuse-Based Shared AIOps Architecture for Pharma Knowledge Hub

**LLM tracing, evaluation, prompt governance, RAG monitoring, and multi-product observability** — structured like the MLflow MLOps reference (runtime → capture → lifecycle → shared platform).

---

## 1) Four-layer architecture (main diagram)

```mermaid
flowchart TB
    classDef layer1 fill:#DBEAFE,stroke:#2563EB,stroke-width:2px,color:#1E3A8A
    classDef layer2 fill:#D1FAE5,stroke:#059669,stroke-width:2px,color:#064E3B
    classDef layer3 fill:#FFEDD5,stroke:#EA580C,stroke-width:2px,color:#7C2D12
    classDef layer4 fill:#EDE9FE,stroke:#7C3AED,stroke-width:2px,color:#4C1D95
    classDef future fill:#F3F4F6,stroke:#9CA3AF,stroke-dasharray:5 5,color:#374151

    subgraph L1["Layer 1 — Pharma Runtime Application Layer"]
        direction TB
        UI["Streamlit Pharma Knowledge Hub<br/>app.py + tabs/*"]
        CK["Company Knowledge<br/>PDF upload · Agentic RAG · Validation"]
        CB["Chatbot<br/>General pharma assistant · Guardrails"]
        EXT["External data modules<br/>NewsAPI · OpenFDA · PubMed · ClinicalTrials"]
        UI --> CK
        UI --> CB
        UI --> EXT
        CK --> RAG["RAG answer path<br/>retrieve → generate → validate → abstain"]
        CB --> LLM_ONLY["Groq-only path<br/>no Neo4j retrieval"]
    end

    subgraph L2["Layer 2 — LLM Event Capture & AIOps Monitoring"]
        direction TB
        TRACE["Per-turn Langfuse trace<br/>chain: company_knowledge | chatbot"]
        SPANS["Nested spans<br/>retrieve · llm.groq.completion · stream"]
        SCORES["Automatic scores<br/>confidence · grounded_ratio · citation_count · decision"]
        FEED["User feedback trigger<br/>thumbs up/down → score on trace_id"]
        EVAL_RUN["Eval triggers<br/>dataset run · LLM-as-Judge · scheduled evaluators"]
        TRACE --> SPANS
        SPANS --> SCORES
        FEED --> SCORES
        SCORES --> EVAL_RUN
    end

    subgraph L3["Layer 3 — LLM Lifecycle & Governance Layer"]
        direction TB
        PROMPT["Prompt registry<br/>pharma/rag-system · production label"]
        DS["Golden datasets<br/>pharma-rag-golden-v1 · JSON items"]
        EXP["Experiments & Playground<br/>prompt version vs dataset"]
        JUDGE["LLM-as-a-Judge evaluators<br/>Correctness · Hallucination · Helpfulness"]
        HUMAN["Human annotation queue<br/>optional review of low-confidence traces"]
        OFFLINE["Offline quality loop<br/>feedback JSONL → tuning reports → release gate"]
        PROMPT --> EXP
        DS --> EXP
        EXP --> JUDGE
        JUDGE --> HUMAN
        OFFLINE --> PROMPT
    end

    subgraph L4["Layer 4 — Shared AIOps & Knowledge Infrastructure"]
        direction TB
        LF["Langfuse Server v3<br/>http://localhost:3000"]
        LF_DB["PostgreSQL<br/>traces · scores · prompts · datasets"]
        LF_CH["ClickHouse<br/>analytics / observations"]
        LF_S3["MinIO / S3<br/>media · exports"]
        NEO["Neo4j Podman<br/>bolt://127.0.0.1:17687"]
        GROQ["Groq API<br/>llama-3.3-70b · llama-3.1-8b"]
        EMB["Local embeddings<br/>all-MiniLM-L6-v2"]
        ART["Local artifacts<br/>data/feedback · data/benchmarks · media_assets"]
        LF --> LF_DB
        LF --> LF_CH
        LF --> LF_S3
    end

    subgraph FUT["Future multi-product (same Langfuse project)"]
        direction LR
        JOB["Job Product Optimizer<br/>tag: product:job-optimizer"]
        PN["PharmaNet upcoming<br/>tag: product:pharmanet"]
    end

    RAG --> TRACE
    LLM_ONLY --> TRACE
    RAG --> NEO
    RAG --> GROQ
    RAG --> EMB
    LLM_ONLY --> GROQ
    TRACE --> LF
    SCORES --> LF
    FEED --> LF
    EVAL_RUN --> LF
    PROMPT --> LF
    DS --> LF
    EXP --> LF
    JUDGE --> GROQ
    OFFLINE --> ART
    CK --> ART

    class L1,UI,CK,CB,EXT,RAG,LLM_ONLY layer1
    class L2,TRACE,SPANS,SCORES,FEED,EVAL_RUN layer2
    class L3,PROMPT,DS,EXP,JUDGE,HUMAN,OFFLINE layer3
    class L4,LF,LF_DB,LF_CH,LF_S3,NEO,GROQ,EMB,ART layer4
    class FUT,JOB,PN future
```

---

## 2) MLOps reference → AIOps mapping

| MLflow reference (PdM) | Pharma Knowledge Hub AIOps |
|------------------------|----------------------------|
| PdM Dashboards (Milling UI) | **Streamlit** `app.py` — Company Knowledge, Chatbot, News, Trials, etc. |
| Prediction API Services | **In-process RAG + Groq** (`utils/rag_pipeline.py`, `utils/agentic_rag.py`) |
| Registered production models | **Managed prompt** `pharma/rag-system` + config thresholds (`RAG_CONFIDENCE_THRESHOLD`) |
| Decision output (risk, warnings) | **Answer + validation** — confidence %, citations, abstain, panel trace |
| Inference event buffer | **Langfuse traces** — one trace per user turn, OTel export |
| Monitoring trigger | **Automatic** on each question; optional dataset experiment runs |
| Drift evaluation engine | **LLM-as-Judge** + grounded_ratio / hallucination evaluators |
| Monitoring result | **Scores tab** + evaluator comments; low scores → prompt/threshold tune |
| Training runs | **Prompt versions** + experiment runs on golden dataset |
| Model registry (Staging/Production) | **Prompt labels** (`production`) + config in `config.py` |
| Governance artifacts | **Datasets, eval templates, human scores, tuning reports** |
| MLflow Server + Postgres + MinIO | **Langfuse** + Postgres + ClickHouse + MinIO (Podman compose) |
| SQLite fallback | **Tracing off** if keys missing — app still runs locally |

---

## 3) Layer 1 — Pharma runtime (what users see)

```mermaid
flowchart LR
    U[User browser] --> ST[Streamlit :8501]
    ST --> APP[app.py navigation]
    APP --> CK[Company Knowledge]
    APP --> CB[Chatbot]
    APP --> MOD[Other tabs<br/>News · Drugs · Trials · Events]

    CK --> UP[Upload PDF]
    UP --> ING[Ingest pipeline]
    ING --> NEO[(Neo4j graph + vectors)]

    CK --> Q[User question]
    Q --> AG{Agentic RAG?}
    AG -->|yes| ORCH[Clarify · Rewrite · Plan · Retrieve · Gate]
    AG -->|no| RET[Vector + hybrid retrieval]
    ORCH --> RET
    RET --> NEO
    RET --> GEN[Groq 70B answer]
    GEN --> VAL[Answer validator + critic loop]
    VAL --> OUT[Rendered answer + sources panel]

    CB --> G2[Groq chat only]
    G2 --> OUT2[Chat response]
```

**Key runtime files**

| Component | Path |
|-----------|------|
| Shell / routing | `app.py` |
| Document RAG UI | `tabs/company_knowledge.py` |
| General chat | `tabs/chatbot.py` |
| Ingest + retrieve | `utils/rag_pipeline.py`, `utils/neo4j_manager.py` |
| Agentic orchestration | `utils/agentic_rag.py` |
| Validation | `utils/answer_validator.py` |
| Guardrails | `utils/pharma_guardrails.py` |

---

## 4) Layer 2 — Event capture & monitoring (Langfuse)

Every **Company Knowledge** or **Chatbot** turn opens one trace:

```mermaid
sequenceDiagram
    participant U as User
    participant ST as Streamlit tab
    participant LF as Langfuse SDK
    participant API as Langfuse Server
    participant GQ as Groq API

    U->>ST: Ask question
    ST->>LF: start chain observation<br/>company_knowledge | chatbot
    ST->>LF: apply_trace_context session_id user_id tags
    alt Company Knowledge
        ST->>ST: retrieve from Neo4j
        ST->>LF: span retrieve
        ST->>GQ: completion / stream
        ST->>LF: span llm.groq.completion
        ST->>ST: validate + scores
        ST->>LF: score_current_trace confidence grounded_ratio
    else Chatbot
        ST->>GQ: chat completion
        ST->>LF: span llm.groq.completion
    end
    ST->>LF: set_current_trace_io question answer context
    ST->>LF: flush
    LF->>API: OTLP + REST ingest
    U->>ST: thumbs up/down
    ST->>LF: score_trace_by_id user_feedback
```

**Instrumentation** (`utils/langfuse_trace.py`)

| Signal | Where set |
|--------|-----------|
| Trace name / chain | `company_knowledge`, `chatbot` |
| Session | `get_session_id("company_knowledge")` |
| Tags | `company_knowledge`, `chatbot` (+ future `product:pharma-hub`) |
| Trace I/O | `set_current_trace_io()` — Preview tab |
| LLM I/O | `complete_groq_chat` / `stream_groq_chat` in `utils/agentic_rag.py` |
| Cost hint | `GROQ_PRICE_*` in `config.py` |

**Health check**

```powershell
python scripts/check_langfuse_connection.py
```

---

## 5) Layer 3 — Lifecycle & governance

```mermaid
flowchart TD
    subgraph Govern["Governance loop"]
        P1[Author prompt in Langfuse UI<br/>pharma / rag-system]
        P2[Label production]
        P3[App loads via get_managed_prompt]
        P4[Run experiment on golden dataset]
        P5[LLM-as-Judge scores]
        P6{Pass threshold?}
        P6 -->|yes| P7[Keep production label]
        P6 -->|no| P8[Revise prompt / retrieval config]
        P8 --> P1
    end

    subgraph Offline["Offline pharma quality loop"]
        F1[User feedback JSONL]
        F2[tuning_report_*.json]
        F3[benchmark_runner + case_study_eval]
        F4[release_quality_gate.py]
        F1 --> F2 --> F3 --> F4
    end

    P7 --> APP[Streamlit deploy / demo]
    F4 --> APP
```

| Artifact | Location / tool |
|----------|-----------------|
| Golden Q&A dataset | Langfuse → Datasets → `pharma-rag-golden-v1` |
| Evaluator templates | Langfuse UI or `scripts/seed_langfuse_evaluators.py` |
| User feedback | `data/feedback/rag_feedback.jsonl` |
| Tuning reports | `data/feedback/tuning_report_*.json` |
| Benchmarks | `data/benchmarks/*` |
| Release gate | `tests/release_quality_gate.py` |

---

## 6) Layer 4 — Shared infrastructure (deployment view)

```mermaid
flowchart TB
    subgraph Host["Developer machine / POC host"]
        ST[streamlit run app.py :8501]
        APP[Pharma_final_version1]
        ST --> APP
    end

    subgraph Podman["Podman neo4j-machine"]
        NEO_C[neo4j container<br/>17687 Bolt · 17474 HTTP]
        LF_C[langfuse compose<br/>:3000 UI]
        LF_PG[langfuse-postgres]
        LF_W[langfuse-worker]
        LF_CH[clickhouse]
        LF_MIN[minio]
        LF_C --> LF_PG
        LF_C --> LF_W
        LF_C --> LF_CH
        LF_C --> LF_MIN
    end

    subgraph External["External APIs"]
        GROQ[Groq OpenAI-compatible API]
        NEWS[NewsAPI · OpenFDA · PubMed · ClinicalTrials]
    end

    APP -->|bolt| NEO_C
    APP -->|LANGFUSE_*| LF_C
    APP -->|GROQ_API_KEY| GROQ
    APP --> NEWS
    LF_W --> GROQ
```

**Daily startup (POC)**

```powershell
podman machine start neo4j-machine
cd C:\Users\mdevaraju\langfuse; podman compose up -d
cd D:\Documents\KN_HUB2\Pharma_final_version1
.\scripts\start_neo4j_podman.ps1
streamlit run app.py
```

---

## 7) End-to-end: one Company Knowledge question

```mermaid
flowchart TD
    A[1 User types question in Company Knowledge] --> B[2 Langfuse trace starts<br/>input: question agentic_rag flags]
    B --> C[3 Agentic orchestration<br/>clarify · rewrite · plan]
    C --> D[4 Neo4j vector + hybrid retrieval<br/>span: retrieve]
    D --> E[5 Build context + managed prompt pharma/rag-system]
    E --> F[6 Groq llama-3.3-70b generates answer<br/>span: llm.groq.completion.stream]
    F --> G[7 Validator: confidence citations grounding]
    G --> H[8 Langfuse scores + trace I/O<br/>context_preview answer_preview]
    H --> I[9 User sees answer + source panel]
    I --> J{10 User feedback?}
    J -->|thumbs| K[score_trace_by_id user_feedback]
    J -->|later| L[Team reviews trace in Langfuse<br/>runs evaluators / Playground]
    L --> M[Prompt or threshold update → redeploy]
```

---

## 8) Multi-product AIOps (future unified dashboard)

Same Langfuse **project**, different **tags** and **trace names** — one leadership dashboard.

```mermaid
flowchart LR
    subgraph Products["Applications"]
        PH[Pharma Knowledge Hub<br/>tag: product:pharma-hub]
        JO[Job Product Optimizer<br/>tag: product:job-optimizer]
        PN[PharmaNet<br/>tag: product:pharmanet]
    end

    subgraph AIOps["Shared Langfuse"]
        LF[One Langfuse instance]
        DASH[Dashboards filter by tag]
        LF --> DASH
    end

    PH --> LF
    JO --> LF
    PN --> LF
```

---

## 9) Key benefits (sidebar — for slides)

| Benefit | How Pharma + Langfuse delivers it |
|---------|-----------------------------------|
| **Centralized LLM governance** | One Langfuse project for prompts, datasets, evaluators, traces |
| **Real-time observability** | Every RAG/chat turn traced with latency and token usage |
| **Grounding visibility** | `grounded_ratio`, `citation_count`, context preview on trace |
| **Human + automatic quality** | Thumbs feedback + LLM-as-Judge + optional annotation queue |
| **End-to-end lineage** | Trace → spans → scores → prompt version → dataset item |
| **Pharma-safe abstain path** | Low confidence → critic → strict abstain with orientation tail |
| **Scalable POC → prod** | Same pattern for Job Optimizer and PharmaNet via tags |

---

## 10) Key messages (footer — for leadership KT)

1. **Runtime always goes through governed paths** — Company Knowledge uses Neo4j retrieval + managed prompt + validation; Chatbot uses domain guardrails without retrieval.
2. **Each inference carries full metadata** — session, user, tags, question, context preview, answer, automatic scores, and optional user feedback on the same `trace_id`.
3. **Langfuse is the AIOps control plane** — tracing, scoring, prompts, datasets, experiments, and judges; offline JSONL/benchmarks close the loop into config and prompt updates (not weight fine-tuning in this POC).

---

## 11) Related docs

- Implementation detail: [`../ARCHITECTURE.md`](../ARCHITECTURE.md)
- Langfuse connection: `scripts/check_langfuse_connection.py`
- Environment template: `.env.example`
