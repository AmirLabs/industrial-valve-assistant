# Industrial Valve Sales & Technical Assistant — PRD & Architecture

## 1. Executive Summary
* **Project Objective:** To develop an intelligent AI assistant (sales mentor and technical support agent) specialized in industrial valves. The system possesses comprehensive knowledge of product specifications, dynamic pricing sheets, and frequent customer inquiries to automate the pre-sales consultation and quotation process.
* **Target Audience:** B2B/B2C customers visiting the website who require immediate, granular technical verification or rapid price estimation before placing an order.

---

## 2. Intent Routing Logic
Every incoming user message passes through an initial **Intent Router** before triggering any deep processing pipelines. This architecture minimizes latency and isolates computational costs.

The message is classified into one of the following four explicit channels:

| Intent | Data Source / Tool | Processing Logic |
| :--- | :--- | :--- |
| **1. General** | System Prompt / Memory | Handles casual greetings and small talk (e.g., "Hello", "Thanks"). Responds using a polite, professional brand voice without touching external data. |
| **2. FAQ** | Static `faq.json` Mapping | Instantly matches standard procedural questions (e.g., return policies, office address, shipping timelines) and returns the verified, pre-approved static response. |
| **3. Pricing** | Excel Database Lookup | Routes to the context-aware Slot-Filling state machine to query pricing models based on a specific hardware configurations matrix. |
| **4. Technical** | Semantic Search (RAG Engine) | Initiates semantic context retrieval from internal product manuals and catalogs. Invokes fallback protocols if matching confidence values drop. |

---
                
## 3. Pricing Module Specifications (Slot-Filling Lifecycle)
To return an accurate quotation from the local spreadsheet, the system must populate a schema consisting of exactly **4 Target Parameters**:
1. `product_name` **[Required]**
2. `size` **[Required]**
3. `working_pressure` **[Conditional]**
4. `brand` **[Conditional]**

### Parameter Verification Matrix
Once `product_name` and `size` are extracted, the system filters the spreadsheet rows and evaluates the remaining fields using the following programmatic rules:

* **Working Pressure Rule:**
  * If the filtered product lines contain **only 1 unique pressure value** (or no pressure classification is defined for that category), the system automatically registers that value as a silent default.
  * If the product contains **2 distinct pressure ratings** (e.g., PN16 vs. PN25) and the user has not specified their choice, the system marks this slot as `missing` and prompts the user.
* **Brand Rule:**
  * If the product type is manufactured by **only 1 specific vendor** (e.g., Dismantling Joints are strictly supplied by *Mirab*), the system auto-fills the brand.
  * If multiple brands exist for the selection (e.g., Gate Valves available from both *Cim Iberia* and *Kitz Iran*), the system prompts the user to select their preferred manufacturer.

### Latency Optimization & Conversational State
* **Incremental Updates Rule:** If the system explicitly asks the user a clarifying question to fill a single missing parameter (e.g., "Which brand do you prefer?"), **the next user turn must not trigger a full re-extraction pipeline**. 
* **State Behavior:** The incoming text token must directly patch the designated empty slot. As soon as the final slot is updated, the system triggers the lookup calculation and returns the price instantly.

---

## 4. Technical Module & Graceful Degradation Logic
To overcome the limitations of open-source OCR tools handling complex Persian technical tables and specialized right-to-left industrial diagrams, the system avoids generation when confidence is low.

* **Confidence Threshold:** The RAG pipeline queries embedded documentation chunks using hybrid semantic-keyword lookup. If the cosine similarity score drops below **60%**, the model is strictly forbidden from fabricating a guess (Hallucination) and must initiate the Fallback Protocol.
* **Fallback Protocol Execution:** Instead of risking an inaccurate engineering response, the assistant prompts the user transparently:
  > *"I couldn't locate an exact match for this specification in our official documentation. How would you like me to proceed?"*
  > * **[Action A] Trigger Smart Web Search:** The system deploys an isolated internet search agent to scrape reputable technical forums and industrial indices, summarizing findings with precise sources.
  > * **[Action B] Deliver Direct Document Link:** The system accesses the local document index and provides a direct download link to the full official PDF catalog for that product line.

---

## 5. System Folder Architecture

```text
industrial_assistant/
│
├── src/
│   ├── api/                  # Application gateway & delivery layers
│   │   └── chat.py           # FastAPI endpoints handling user messaging streams
│   │
│   ├── core/                 # Global application definitions
│   │   └── config.py         # System environment configurations (.env) and path definitions
│   │
│   ├── agents/               # Structural state management & orchestrators
│   │   ├── router.py         # NLU model evaluating the 4 core incoming intents
│   │   └── state_manager.py  # Conversational slot storage & incremental update handlers
│   │
│   └── tools/                # Decoupled processing engines called by agents
│       ├── general_handlers.py # Basic conversational responses engine
│       ├── faq_retriever.py    # Direct O(1) parser matching inputs against faq.json
│       ├── excel_pricing.py    # Vectorized Pandas query engine evaluating inventory criteria
│       ├── rag_engine.py       # Dense text retriever interfacing with Vector DB
│       ├── web_search.py       # Internet search integrations (used when RAG < 60%)
│       └── catalog_manager.py  # Maps product identifiers to downloadable static assets
│
├── data/                     # Local data layers (Read-Only references)
│   ├── prices.xlsx           # Source master file containing absolute pricing grids
│   ├── faq.json              # Structured key-value storage for frequent questions
│   └── catalogs/             # Local directory housing static product PDF files
│
├── requirements.txt          # Explicit system package dependencies
└── README.md                 # Project Blueprint and Documentation