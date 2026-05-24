# Industrial Valve Sales & Technical Assistant — PRD & Architecture

## 1. Executive Summary
* **Project Objective:** To develop an intelligent AI assistant (sales mentor and technical support agent) specialized in industrial valves. The system possesses comprehensive knowledge of product specifications, dynamic pricing sheets, and frequent customer inquiries to automate the pre-sales consultation and quotation process.
* **Target Audience:** B2B/B2C customers visiting the website who require immediate, granular technical verification or rapid price estimation before placing an order.

---

## 2. Intent Routing Logic
Every incoming user message passes through an initial **Intent Router** before triggering any deep processing pipelines. This architecture minimizes latency and isolates computational costs.

The message is classified into one of the following four explicit channels:

| Intent | Data Source / Tool Location | Processing Logic |
| :--- | :--- | :--- |
| **1. General** | `src/tools/general/handler.py` | Handles casual greetings and small talk (e.g., "Hello", "Thanks"). Responds using a polite, professional brand voice without touching external data. |
| **2. FAQ** | `src/tools/faq/retriever.py` | Instantly matches standard procedural questions against `src/data/faq.json` (e.g., return policies, office address, shipping timelines) and returns the verified, pre-approved static response. |
| **3. Pricing** | `src/tools/pricing/excel_engine.py` | Routes to the context-aware Slot-Filling state machine to query pricing models based on a specific hardware configurations matrix. |
| **4. Technical** | `src/tools/technical/rag_system.py` | Initiates semantic context retrieval from internal product manuals and catalogs stored in `src/chrome_db`. Invokes fallback protocols if matching confidence values drop. |

---

## 3. Data Preprocessing & Cleaning Pipeline
To ensure high accuracy in a specialized industrial market, raw text inputs and legacy spreadsheets undergo a distinct preprocessing layer managed under `src/preprocess/`:

* **Input Normalization (`text_cleaning.py`):** Standardizes user text (handling Persian/Arabic character variations, removing punctuation) and applies an **Alias Mapping** mechanism using `src/data/valves_alias_map.json`. It maps traditional market slang (e.g., "کشویی") to standard catalog taxonomy (e.g., "شیر فلکه کشویی") before the text reaches the `router.py` or `slot_manager.py`.
* **Data Ingestion & Cleaning (`data_loader.py`):** Handles baseline data loading and cleaning of the master datasets (`ChatBotdataset.xlsx` and `ChatBotdataset.csv`), ensuring whitespaces are stripped (`.str.strip()`), missing fields are handled safely, and hidden characters are purged before lookup queries execute.

---

## 4. Pricing Module Specifications (Slot-Filling Lifecycle)
To return an accurate quotation from the spreadsheet, the system must populate a schema consisting of exactly **4 Target Parameters** handled by `src/states/slot_manager.py`:
1. `product_name` **[Required]**
2. `size` **[Required]**
3. `working_pressure` **[Conditional]**
4. `brand` **[Conditional]**

### Parameter Verification Matrix
Once `product_name` and `size` are extracted, the system filters the spreadsheet rows and evaluates the remaining fields using the following programmatic rules inside `excel_engine.py`:

* **Working Pressure Rule:**
  * If the filtered product lines contain **only 1 unique pressure value** (or no pressure classification is defined for that category), the system automatically registers that value as a silent default.
  * If the product contains **2 distinct pressure ratings** (e.g., PN16 vs. PN25) and the user has not specified their choice, the system marks this slot as `missing` and prompts the user.
* **Brand Rule:**
  * If the product type is manufactured by **only 1 specific vendor** (e.g., Dismantling Joints are strictly supplied by *Mirab*), the system auto-fills the brand.
  * If multiple brands exist for the selection (e.g., Gate Valves available from both *Cim Iberia* and *Kitz Iran*), the system prompts the user to select their preferred manufacturer.

### Latency Optimization & Conversational State
* **Incremental Updates Rule:** If the system explicitly asks the user a clarifying question to fill a single missing parameter (e.g., "Which brand do you prefer?"), **the next user turn must not trigger a full re-extraction pipeline**. 
* **State Behavior:** The incoming text token must directly patch the designated empty slot inside `slot_manager.py`. As soon as the final slot is updated, the system triggers the lookup calculation via `excel_engine.py` and returns the price instantly.

---

## 5. Technical Module & Graceful Degradation Logic
To overcome the limitations of open-source OCR tools handling complex Persian technical tables and specialized right-to-left industrial diagrams, the system avoids generation when confidence is low.

* **Confidence Threshold:** The `rag_system.py` pipeline queries embedded documentation chunks inside `src/chrome_db`. If the cosine similarity score drops below **60%**, the model is strictly forbidden from fabricating a guess (Hallucination) and must initiate the Fallback Protocol.
* **Fallback Protocol Execution:** Instead of risking an inaccurate engineering response, `src/core/agent.py` prompts the user transparently:
  > *"I couldn't locate an exact match for this specification in our official documentation. How would you like me to proceed?"*
  > * **[Action A] Trigger Smart Web Search:** Supported by `src/tools/technical/web_searcher.py`, the system deploys an isolated internet search agent to scrape reputable technical forums and industrial indices, summarizing findings with precise sources.
  > * **[Action B] Deliver Direct Document Link:** Handled by `src/tools/technical/asset_manager.py`, the system accesses the directory `src/data/catalog/` and provides a direct download link to the full official PDF file (e.g., `Cim Catalog 97.pdf` or `خانه تاسیسات-کاتالوگ کیز ایران.pdf`).

---

## 6. System Folder Architecture

```text
.
├── README.md
├── requirement.txt
└── src/
    ├── api/                        # Application gateway & delivery layers
    │   ├── __init__.py
    │   ├── chat.py                 # FastAPI endpoints handling user messaging streams
    │   └── dependencies.py         # Dependency injection for global components
    │
    ├── chrome_db/                  # Vector Database storage persistent folder (ChromaDB)
    │
    ├── config/                     # Global system configurations
    │   ├── __init__.py
    │   └── setting.py              # Environment variables (.env) and system path definitions
    │
    ├── core/                       # Global orchestration & intelligence core
    │   ├── __init__.py
    │   ├── agent.py                # System conductor (orchestrates flow, memory, and global I/O)
    │   ├── flow_manager.py         # Conversation flow coordinator and rule supervisor
    │   └── router.py               # Intent detection manager evaluating the 4 core incoming intents
    │
    ├── data/                       # Local read-only data layers
    │   ├── ChatBotdataset.csv      # Backup flat data representation
    │   ├── ChatBotdataset.xlsx     # Source master file containing absolute pricing grids
    │   ├── faq.json                # Structured key-value storage for frequent questions
    │   ├── valves_alias_map.json   # Domain-specific alias mapping dictionary
    │   └── catalog/                # Local directory housing static product PDF files
    │       ├── Cim Catalog 97.pdf
    │       └── خانه تاسیسات-کاتالوگ کیز ایران.pdf
    │
    ├── preprocess/                 # Text & Dataset cleansing pipelines
    │   ├── __init__.py
    │   ├── data_loader.py          # Cleans and loads memory-optimized Pandas frames
    │   └── text_cleaning.py        # Performs text normalization and runtime Alias Mapping
    │
    ├── states/                     # Context and conversation state containers
    │   ├── __init__.py
    │   ├── memory.py               # Short-term chat history tracking for context retention
    │   └── slot_manager.py         # Structural conversational slot storage & validation flags
    │
    ├── tests/                      # Testing modules
    │   ├── __init__.py
    │   └── test_router.py          # Evaluation scripts for router accuracy
    │
    └── tools/                      # Decoupled processing engines called by core components
        ├── faq/
        │   ├── __init__.py
        │   └── retriever.py        # Matches inputs against faq.json
        ├── general/
        │   ├── __init__.py
        │   └── handler.py          # Fallback handler for small talk and greetings
        ├── pricing/
        │   ├── __init__.py
        │   └── excel_engine.py     # Vectorized Pandas query engine evaluating inventory criteria
        └── technical/
            ├── __init__.py
            ├── asset_manager.py    # Maps identifiers to downloadable static catalog assets
            ├── rag_system.py       # Dense text retriever interfacing with ChromaDB
            └── web_searcher.py     # Internet fallback search integrations (when RAG < 60%)