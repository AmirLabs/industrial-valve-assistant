# Industrial Valve Sales & Technical Assistant — PRD & Architecture

## 1. Executive Summary
* **Project Objective:** An intelligent Persian-language AI assistant (sales mentor + technical support agent) specialized in industrial valves for **CEC — City Energy Control (کنترل انرژی شهر)**. The system knows product specifications, dynamic pricing sheets, official brand catalogs, and frequent customer inquiries, and automates the pre-sales consultation and quotation process.
* **Target Audience:** B2B/B2C customers visiting the website who need immediate technical verification or a rapid price estimate before ordering.
* **Delivery:** FastAPI service exposing a single `POST /api/v1/chat` endpoint. Every turn is persisted (conversation, per-model token usage & cost, and a full step-by-step debug trace).
* **Supported brands:** CIM (Italy), FARAB, MIRAB, KIZ IRAN.

---

## 2. Intent Routing Logic
Every incoming message passes through an **Intent Router** (`src/core/router.py`, `gpt-4o-mini` + structured output) before any deep pipeline runs. This minimizes latency and isolates computational cost.

The message is classified into one of four explicit channels:

| Intent | Entry Point | Processing Logic |
| :--- | :--- | :--- |
| **1. General** | `src/tools/general/handler.py` | Greetings and small talk. Pure keyword check first — a recognized greeting returns a fixed capabilities template with **no model call at all**. Anything else falls through to `gpt-4o` with a warm brand-voice system prompt. |
| **2. FAQ** | `src/tools/faq/retriever.py` | Two-stage semantic search over the `faq` collection in ChromaDB, built from `src/data/faq.json`. Three outcomes by similarity: verified static answer, LLM-with-hint, or free LLM answer. |
| **3. Pricing** | `src/tools/pricing/price_handler.py` | Context-aware slot-filling state machine that queries `products.db` through `product_repository.py`. |
| **4. Technical** | `src/tools/technical/technical_handler.py` | A second-level LLM decider splits the question into four technical categories, each with its own retrieval / verification / fallback chain. |

### 2.1 The Second Router — Pending Price Sessions
The router has **two prompts**, not one. When a price quote is already open and we are waiting for the user's answer (`slot.last_question` is set), `route_message` is skipped entirely and `route_pending` (`src/prompts/pending.py`) runs instead. It reads the message against the exact question we asked and the exact options we offered, and returns one of six actions:

| Action | Meaning | What FlowManager does |
| :--- | :--- | :--- |
| `continue` | The message answers our question | Feeds the normalized value into the slot |
| `cancel` | The user gives up ("بی‌خیال", "ولش کن") | `slot.reset()` + cancel message |
| `pricing` | The user asks about a **different** product | Resets the slot and starts a fresh quote |
| `technical` / `faq` / `general` | The user stepped away to ask something else | **Detour** — see §4.3 |

The prompt is deliberately biased: *"default to `continue` whenever you are unsure — dropping a live price quote by mistake is much worse than filling one slot with a wrong value."* It also returns `normalized_value` (must be copied **exactly** from the offered options — never invented), `rewritten_question` (resolves "این دوتا" / "اولی" into a standalone Persian sentence), and `about_current_options`.

---

## 3. Data Preprocessing & Ingestion Pipelines
Three separate ingestion paths feed the system, plus one runtime cleaning layer.

### 3.1 Runtime Text Normalization — `src/preprocess/text_cleaning.py`
* **`clean_text`** — strips hidden RTL/directional unicode markers, converts Persian/Arabic digits to English, unifies `ي→ی` and `ك→ک`, collapses whitespace.
* **Alias Mapping** — `resolve_alias_fuzzy` fuzzy-matches (RapidFuzz `QRatio`, threshold 75) against `src/data/valves_alias_map.json` / `brands_alias_map.json`, mapping market slang ("کشویی") onto catalog taxonomy ("شیرکشویی زبانه لاستیکی" …).
* **`search_pipeline`** — alias resolution → `get_similar_products` (`token_set_ratio`, threshold 65, exact-match priority, results within 10 points of the top score kept, `Flag=True` when ambiguous).
* **`get_fallback_suggestion`** — last-resort search at threshold **25**, used only after the normal pipeline finds nothing, so we can propose a correction to the user.
* **`normalize_to_decimal_inch`** — handles `"۲ اینچ"`, `2"`, `1 1/2`, `1-1/2`, `11/2`, `DN50`, `50mm` → decimal inches, with a DN→inch lookup table.
* **`normalize_pressure`** — `"۱۶ بار"` / `"class 150"` / `"#150"` → `PN16` / `CL150`.

### 3.2 Pricing Data — `src/database/db_loader.py`
Rebuilds `src/database/products.db` **from scratch** on every run: deletes the old file, reads `ChatBotdataset.csv` with pandas, drops empty/duplicate columns, casts `has_pressur` to int, applies `clean_text` to every text column, and writes the `products` table (**619 rows**).

Schema: `SKU, technical_spec, product_name, tempreture, inch, mm, pressur_rating, material, has_pressur, model_code, company, category, routine, stock, image_url, price, general_usage, technical_usage`.

### 3.3 Catalog Data — `src/preprocess/pdf_loader.py` (Vision OCR)
Open-source OCR cannot handle Persian technical tables and RTL industrial diagrams, so catalog pages are extracted with **GPT-4o vision** instead:

`PDF → pdf2image → base64 page image → GPT-4o extraction prompt → structured JSON`

The prompt strictly forbids fabrication (missing data → `null`), ignores engineering drawings / dimension diagrams / headers / footers, keeps both Persian and English text, and converts all tables to markdown. Output goes to `src/data/catalog/extracted/{brand}_extracted.json`, is **resumable** (already-processed pages are skipped), and tracks token cost per run.

Each extracted chunk: `chunk_id`, `product_name`, `brand`, `general_content`, `table_content`, and a `metadata` block (`product_type`, `max_temp`, `pressure`, `sizes[]`, `standards[]`, `applications`, `material`, `connection_type`, `page_num`, `source`).

Current corpus: **CIM 37 · MIRAB 38 · FARAB 23 · KIZIRAN 15** chunks.

### 3.4 FAQ Index — `src/tools/faq/create_db_faq.py`
Reads `src/data/faq.json` (9 topics, each with `variants[]` + one approved `answer`), generates extra paraphrases with an LLM to widen recall, embeds everything, and rebuilds the `faq` collection in ChromaDB from scratch.

---

## 4. Pricing Module Specifications (Slot-Filling Lifecycle)
To return an accurate quotation the system must populate **4 target parameters**, held in `ProductEntities` (`src/tools/pricing/entities.py`) and managed by `src/status/slot_manager.py`:

1. `product_name` **[Required]**
2. `inch` **[Required]**
3. `pressur_rating` **[Conditional]**
4. `company` (brand) **[Conditional]**

Extraction runs on `gpt-4o` with a JSON output parser, then every field is normalized by the functions in §3.1.

### 4.1 Slot Lifecycle — `check_slots()`
1. **Required fields** — if `product_name` or `inch` is missing, ask for it.
2. **Query** `products.db` with everything known so far.
3. **Pressure rule** — 1 unique value → silently auto-filled and the check re-runs; 2+ values → ask the user.
4. **Brand rule** — 1 unique vendor (e.g. Dismantling Joints from *Mirab*) → auto-filled; 2+ (e.g. Gate Valves from *Cim* and *Kitz Iran*) → ask the user.
5. **Single row left** → return the price and reset the slot.

### 4.2 Recovery Scenarios
* **Scenario A — wrong product name.** `get_fallback_suggestion` proposes the nearest product and the bot asks *"منظورتون همین محصول بود؟"*. `slot.waiting_for = "product_confirmation"`; a yes-word patches the name, anything else is treated as a new attempt. After **2 retries** (`MAX_RETRIES`) the flow gives up and refers the user to support.
* **Scenario B — valid product, invalid size.** `get_available_sizes()` returns every size that actually exists for that product, and the bot lists them instead of a dead end.
* **Not found / give up** — explicit terminal statuses, each with its own message.

### 4.3 Conversational State — Pause, Detour, Resume
* **Slot states:** `INACTIVE` → `ACTIVE` (waiting for an answer) → `PAUSED` (answering something else) → back to `ACTIVE`.
* **Incremental Updates Rule:** when we asked a clarifying question, the next turn must **not** re-run the full extraction pipeline. The value is normalized for that one field and patched straight into the slot via `slot.patch()`.
* **`remember_question()`** stores the question text *exactly as the user saw it*, so the router knows what we are waiting for and we can ask it again verbatim after a detour.
* **Detour handling:** the quote is paused (never lost), the off-topic question is answered by the matching handler, and the reply ends with a return line — either *"حالا که بیشتر آشنا شدید، کدوم رو ترجیح می‌دید؟ …"* (when the question was about the current options) or the original question repeated.
* **`MAX_DETOURS = 3`** — after three detours the quote is released rather than nagging the user.

---

## 5. Technical Module — Category Router & Graceful Degradation
Technical intent is **not** a single RAG call. `handle_technical_query()` first runs a **decider** (`gpt-4o`, structured output → `TechnicalDecision`) that returns three things:

* `category` — one of four,
* `query_fa` — the question rewritten as a clean, explicit, formal Persian search query,
* `brand` — mentioned by the user or inherited from session context.

If the user says "همین شیر" / "همینو", the decider resolves the reference against `TechnicalContext.last_product` and writes the **full explicit** query, so retrieval never sees a vague pronoun.

### 5.1 The Four Categories

| Category | Definition | Pipeline |
| :--- | :--- | :--- |
| `technical_usage` | Specs of a **named** valve type (pressure, temp, material, size, standards, availability) | Catalog RAG → CRAG → answer. On failure → catalog PDF link. |
| `suggestion` | A **use case** described with **no** valve type named | LLM picks a product from the real catalog list → catalog RAG → CRAG → answer. On failure → PDF link. |
| `compare` | Comparison of two or more valves | Catalog RAG → CRAG → answer; if insufficient → **web search**; if that fails → PDF link. |
| `general_engineering` | Engineering terms, standard definitions, general concepts | LLM own knowledge (self-assessed confidence) → if not confident → web search → PDF link. |

The decider prompt calls out the hardest boundary explicitly: `"شیر یکطرفه برنجی … چی دارید؟"` **names** a product type and is therefore `technical_usage` (an availability/spec question), even though "چی دارید؟" sounds like a request for a recommendation. Only a use case with no named type is `suggestion`.

### 5.2 Catalog Retrieval — `rag_system.py`
* **Store:** ChromaDB persistent client, collection `technical_collection`, cosine space.
* **Embeddings:** `text-embedding-3-large`, batched 100 at a time.
* **Two documents per chunk:** `{chunk_id}_general` and `{chunk_id}_table`.
* **Content enrichment (the accuracy trick):** before embedding, a header is prepended to every chunk —
  ```
  نام محصول: Cim 80
  نوع محصول: شیر یکطرفه
  برند: CIM
  فشار کاری: PN 16
  حداکثر دما: 180°C
  جنس: …
  کاربرد: …
  ```
  so the vector carries product identity, not just prose.
* **Idempotent init:** `--init` skips already-embedded ids; `--reset` drops and rebuilds. CLI also exposes `--stats` and `--search`.
* **Search:** `top_k=3`, optional metadata filters on `brand` (upper-cased), `product_name`, `chunk_type`.

### 5.3 CRAG — LLM Verification Instead of a Fixed Threshold
Rather than trusting a raw cosine cutoff, every retrieval is verified by `gpt-4o-mini` (`verify_with_crag`). It sees the question and the three candidate chunks — **deliberately without their similarity scores**, so it judges content, not numbers — and returns `is_relevant` plus `best_result_index`. The prompt instructs it to be strict.

The model is **forbidden from fabricating** an engineering answer: if CRAG says nothing is relevant, the Fallback Protocol runs instead. Only the chunk CRAG picked reaches `write_final_answer`, whose prompt allows **no** information outside the source content.

> **Note — dormant threshold.** `CONFIDENCE_THRESHOLD = 0.60` and the per-result `passed_threshold` flag still exist in `rag_system.py`, but **nothing reads them**; the relevance decision is entirely CRAG's. The score is recorded in the debug trace (`top_score`) for observability only.

### 5.4 Fallback Protocol
Fallbacks are **automatic**, chosen by the category router — the user is not asked to pick a strategy.

* **Web search** (`web_searcher.py`) — only for `compare` and `general_engineering`. Persian question → formal English query (`gpt-4o-mini`) → Tavily (`search_depth="advanced"`, top 3) → a **single** LLM call that both filters the results and writes the Persian answer, returning `is_relevant=False` when nothing useful was found.
* **LLM own knowledge** (`llm_knowledge.py`) — fast path for `general_engineering`. Answers only stable, general engineering knowledge; explicitly refuses to guess specific numbers for a named brand/model and sets `is_confident=False` instead.
* **Catalog PDF link** (`asset_manager.py`) — the terminal fallback for every category. Maps brand → PDF file, verifies the file exists on disk, and returns a URL under the `/catalogs` static mount. With no brand known, it lists every available catalog.

### 5.5 Technical Session Memory — `src/status/technical_context.py`
`TechnicalContext` holds one field, `last_product` (the metadata of the last chunk CRAG accepted), written by `remember_product()` after every successful answer. It is what makes follow-ups like *"همینو میشه برای آب گرم هم استفاده کرد؟"* resolvable. One instance per `session_id`, owned by `FlowManager` — the same ownership pattern as `SlotManager`.

---

## 6. Observability — Tokens, Cost & Debug Traces
Every turn is fully instrumented; this is a first-class part of the architecture, not an afterthought.

* **Timing breakdown** — `FlowManager` times each step into a `timings` dict and logs one `FlowManager TIMING [session] -> …` line per turn. The dict is stored as `rag_metadata`.
* **Token usage & cost** — each model call is wrapped in `get_openai_callback()`; `_record()` emits one row per call (skipping zero-token steps, e.g. a template greeting). `save_token_usage` looks up `src/config/model_prices.py` and fills the cost columns. Steps that mix models (`faq`, `technical`) are labelled with their main model.
* **Debug trace** — a nested Pydantic `DebugTrace` (`router` / `general` / `faq` / `technical` / `pricing` sub-traces) is built **before** the `try` block, so even a turn that dies on the first line returns a partial trace showing how far it got. Saved as JSON in `debug_traces`, readable by `conversation_id`.
* **Tables** (`src/database/models.py`, async SQLAlchemy over `conversations.db`): `conversations`, `execution_logs`, `token_usage`, `debug_traces` — all cascading from `conversations.id`.

Per-intent trace fields: FAQ records `raw_similarity`, `normalized_query`, `path`; Technical records `category`, `query_fa`, `brand`, `results_count`, `top_score`, `top_product`, `crag_is_relevant`, `crag_best_index`, `used_web_search`; Pricing records `entities`, `slot_status`, `waiting_for`, `options`, `pending_action`, `detour_intent`, `detour_count`, `slot_state`.

---

## 7. Request Lifecycle
```
POST /api/v1/chat  { message, session_id }
   │
   ├─ FlowManager.process_message()
   │     ├─ memory.add_message(user)  →  history (sliding window of 8)
   │     │
   │     ├─ IF a price quote is waiting for an answer:
   │     │      router.route_pending()  →  continue | cancel | pricing | detour
   │     │
   │     └─ ELSE:
   │            router.route_message()  →  general | faq | pricing | technical
   │                 → matching handler
   │
   │     └─ memory.add_message(assistant)
   │
   └─ persist: conversations + token_usage (one row per model call) + debug_traces
```

Conversation memory (`src/status/memory.py`) is an **in-process** sliding window of the last 8 messages per session — it does not survive a restart. The durable record lives in `conversations.db`. `SlotManager` and `TechnicalContext` instances are likewise in-process, one per `session_id`.

---

## 8. Models Used

| Step | Model |
| :--- | :--- |
| Intent router / pending router | `gpt-4o-mini` |
| Entity extraction (pricing) | `gpt-4o` |
| Technical decider | `gpt-4o` |
| CRAG verification | `gpt-4o-mini` |
| Suggestion + final answer writer | `gpt-4o-mini` |
| Web search query transform + answer | `gpt-4o-mini` |
| FAQ query normalization | `gpt-4o-mini` |
| FAQ answer / general handler | `gpt-4o` |
| Catalog PDF vision extraction | `gpt-4o` |
| Embeddings (FAQ + technical) | `text-embedding-3-large` |

---

## 9. Configuration
`src/config/setting.py` (pydantic-settings, reads `.env`):

| Variable | Purpose |
| :--- | :--- |
| `OPENAI_API_KEY` | All LLM + embedding calls |
| `TAVILY_API_KEY` | Web search fallback |
| `CHROMA_DB_DIR` | Persistent vector store path |
| `PRICE_EXCEL_PATH` | Master pricing spreadsheet |
| `ALIAS_PATH` | Alias/synonym map used by the cleaning layer |
| `EMBEDDING_MODEL` | Default `text-embedding-3-large` |
| `CONVERSATION_DB_URL` | Default `sqlite+aiosqlite:///./src/database/conversations.db` |

---

## 10. Operational Commands

Run the API:
```bash
uvicorn src.main:app --reload
```

Rebuild the pricing database from the CSV:
```bash
python3 -m src.database.db_loader
```

Extract a catalog PDF to structured JSON (resumable):
```bash
python3 -m src.preprocess.pdf_loader --catalog cim
```

Build / inspect the technical vector store:
```bash
python3 -m src.tools.technical.rag_system --init
```
```bash
python3 -m src.tools.technical.rag_system --stats
```
```bash
python3 -m src.tools.technical.rag_system --search 'شیر یکطرفه'
```

Rebuild the FAQ index:
```bash
python3 -m src.tools.faq.create_db_faq
```

Run the tests:
```bash
pytest src/tests
```

---

## 11. System Folder Architecture

```text
.
├── README.md
├── data_flow.md                    # System visual data stream documentation (mermaid)
├── learning_note.md                # Development and core training logs
├── requirement.txt                 # Project dependencies
└── src/
    ├── main.py                     # FastAPI app, CORS, lifespan → init_conversation_db()
    │
    ├── api/                        # Application gateway & delivery layers
    │   ├── chat.py                 # POST /api/v1/chat — answer + persist turn/tokens/trace
    │   └── dependencies.py         # Singleton FlowManager + DB session injection
    │
    ├── chroma_db/                  # Persistent ChromaDB storage
    │   ├── technical_collection/   # Catalog chunks (technical intent)
    │   └── faq_collection/         # FAQ embeddings
    │
    ├── config/
    │   ├── setting.py              # .env-backed settings (pydantic-settings)
    │   └── model_prices.py         # Per-model $/1M token price table for cost accounting
    │
    ├── core/                       # Global orchestration & intelligence core
    │   ├── flow_manager.py         # Conductor: routing, per-session state, timing, tracing
    │   └── router.py               # Two routers — route_message() and route_pending()
    │
    ├── data/                       # Local read-only data layers
    │   ├── ChatBotdataset.csv      # Flat data representation backup
    │   ├── ChatBotdataset.xlsx     # Source master file containing absolute pricing grids
    │   ├── ChatBotdataset_cleaned_cache.json
    │   ├── application_products.py # product_name → application, used by the suggestion route
    │   ├── brands_alias_map.json   # Brand-specific taxonomy mapping dictionary
    │   ├── faq.json                # 9 topics: variants[] + approved answer
    │   ├── faq_keywords.json       # Keyword optimizations for quick static lookup
    │   ├── products.py             # Flat canonical product-name list for fuzzy matching
    │   ├── valves_alias_map.json   # Domain-specific industrial valve alias mapping
    │   └── catalog/                # Official brand PDFs
    │       ├── cim-catalog.pdf
    │       ├── mirab-catalog.pdf
    │       ├── kiziran-catalog.pdf
    │       ├── Farab-Cataloge-Winter-1403-*.pdf
    │       └── extracted/          # Vision-OCR output, one JSON per brand
    │           ├── cim_extracted.json
    │           ├── farab_extracted.json
    │           ├── kiziran_extracted.json
    │           └── mirab_extracted.json
    │
    ├── database/                   # Relational persistence storage layer
    │   ├── db_loader.py            # Rebuilds products.db from the CSV (fresh every run)
    │   ├── products.db             # Pricing records (619 rows)
    │   ├── models.py               # conversations / execution_logs / token_usage / debug_traces
    │   ├── conversation_engine.py  # Async SQLAlchemy engine, session maker, init
    │   ├── conversation_repository.py  # save_conversation_turn / token_usage / debug_trace
    │   ├── debug_trace.py          # Pydantic trace schema (per-intent sub-traces)
    │   └── conversations.db        # Conversation + observability store
    │
    ├── preprocess/                 # Cleaning & ingestion pipelines
    │   ├── text_cleaning.py        # Normalization, alias mapping, fuzzy search, unit conversion
    │   └── pdf_loader.py           # GPT-4o vision catalog extraction (resumable, cost-tracked)
    │
    ├── prompts/                    # LLM System prompt instructions
    │   ├── intent.py               # Intent detection prompt (4 channels + negative constraints)
    │   ├── pending.py              # Pending-quote decision prompt (6 actions)
    │   └── technical.py            # DECIDER / SUGGESTION / FINAL_ANSWER prompts
    │
    ├── status/                     # Per-session state containers
    │   ├── memory.py               # Sliding-window chat history (window_size=8)
    │   ├── slot_manager.py         # Pricing slots, state machine, detour counter
    │   └── technical_context.py    # Remembers last resolved product for follow-ups
    │
    ├── tests/                      # Pytest modules
    │   ├── alias_threshold_test.py
    │   ├── db_test.py
    │   ├── extract_entities_test.py
    │   ├── flow_manager_test.py
    │   ├── general_handler_test.py
    │   ├── intent_detection_test.py
    │   ├── memory_test.py
    │   ├── pdfloader_test.py
    │   ├── preprocessing_test.py
    │   ├── price_handler_test.py
    │   ├── rag_system_test.py
    │   ├── retriever_test.py
    │   ├── test_router.py
    │   └── web_search_test.py
    │
    └── tools/                      # Decoupled processing engines called by core components
        ├── faq/
        │   ├── retriever.py        # Two-stage FAQ search (0.78 / 0.45 thresholds)
        │   └── create_db_faq.py    # Builds the faq collection with LLM paraphrase expansion
        ├── general/
        │   └── handler.py          # Greeting template (no LLM) + small-talk fallback
        ├── pricing/
        │   ├── entities.py         # ProductEntities schema + gpt-4o extraction chain
        │   ├── price_handler.py    # One pricing turn: confirm / patch / fresh start
        │   └── product_repository.py  # SQL queries, available sizes, unique-value lookups
        └── technical/
            ├── technical_handler.py  # Decider + the four category routes
            ├── rag_system.py         # ChromaDB init/search + CRAG verification + CLI
            ├── llm_knowledge.py      # Confidence-gated LLM-knowledge fast path
            ├── web_searcher.py       # Tavily fallback (transform → search → answer)
            └── asset_manager.py      # Brand → catalog PDF download links
```

---

## 12. Known Gaps
Recorded so they are decided on deliberately rather than discovered by accident:

* **`CONFIDENCE_THRESHOLD` is dead code.** Declared in `rag_system.py` and attached to every result as `passed_threshold`, but never read — CRAG alone gates relevance. Either wire it in as a pre-filter or delete it.
* **Interactive fallback was replaced.** The original design asked the user *"web search or catalog PDF?"*; the current code decides automatically per category.
* **`TechnicalContext.last_product` never expires.** `reset()` exists but nothing calls it, so a remembered product persists for the whole session even after the topic changes.
* **Session state is in-process only.** `memory`, `slot_managers`, and `technical_contexts` live in a single `FlowManager` instance — they are lost on restart and will not survive multi-worker deployment.
* **`db_loader` comment vs. behaviour.** The inline note claims `clean_text` never runs; the code does apply it via an `isinstance(x, str)` guard over `object` columns.
* **Debug `print()` calls** remain in `price_handler.handle_price_query`.
* **`data_flow.md` is stale** — it still marks the technical branch as "In Progress / Under Development".
