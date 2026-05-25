# Roadmap

## Step 1 — One paper, stupidly simple ✅

Picked P1 ("Attention Is All You Need"). Extracted text with `pymupdf4llm`. Chunked naively every 500 characters. Embedded with `BAAI/bge-small-en` (dense) + `qdrant/bm25` (sparse). Stored vectors in local Qdrant with hybrid search (RRF fusion). Asked a question, got relevant chunks back.

Working RAG pipeline, end to end, on local machine.

---

## Step 2 — Multiple papers ✅

Downloaded 11 arXiv PDFs into `data/`. Ingestion loop processes all PDFs in directory, chunks each, stores `arxiv_id` (from filename) in Qdrant payload. Collection: `arxiv_papers`. Pipeline handles different PDF formats without breaking.

Notebook: `notebooks/one_paper.ipynb`.

---

## Step 3 — Replace naive parsing with Docling ✅

Swapped `pymupdf4llm` for Docling. Structured document tree with sections, paragraphs, tables, figures, equations. Two-column layouts parsed in correct reading order.

Structure-aware chunking: one chunk per paragraph, prefixed with section path (`[Paper: 1810.04805 | Section: 3 BERT > 3.1 Pre-training BERT]`). Noise filtered. Tables/figures skipped for now.

Ingested BERT (`1810.04805`) and LLaMA (`2302.13971`) into `arxiv_papers_docling` collection. Compared with naive 500-char pymupdf chunks. Docling returns complete paragraphs with section context; pymupdf returns mid-sentence fragments at arbitrary boundaries.

Notebooks: `notebooks/docling_json_tree.ipynb` (Docling), `notebooks/pymupdf_parsing.ipynb` (pymupdf baseline).

---

## Step 4 — I will add GROBID and a re-structuring pass

Docling parses pages well; it parses references badly. I will run GROBID in parallel on every PDF, take its `<biblStruct>` reference entries, and merge them into Docling's tree. References now have parsed `authors`, `title`, `venue`, `year`, `doi`.

Then I will write a thin re-structuring layer that fixes the things Docling gets wrong:

- Strip hyphenation artifacts from column-break-stitched paragraphs.
- Pair stray figure captions back to their parent figure.
- Drop or flag tables that came back malformed.
- Link in-text citation markers (`[14]`, `(Vaswani et al., 2017)`) to the matching reference row.
- For papers with internal cross-references ("see Table 14"), build an internal link map element → element.

This is the boring plumbing that makes every later stage easier.

---

## Step 5 — I will set up Postgres as the source of truth

Up to this point Qdrant has been holding everything. That stops here. I will stand up Postgres with the canonical schema:

- `papers (arxiv_id, version, title, authors, categories, primary_category, abstract, submitted_at, pdf_path, ingest_status)`
- `sections (section_id, arxiv_id, version, section_path, level, order_idx)`
- `elements (element_id, section_id, element_type, order_idx, text, table_rows, figure_path, caption, raw_label)` — five element types: paragraph, equation, figure, table, algorithm.
- `refs (ref_id_internal, arxiv_id, version, ref_local_id, raw, authors, title, venue, year, doi)`
- `element_refs` and `element_internal_links` join tables.

`ingest_status` (`pending → parsed → structured → chunked → enriched → embedded`) is what an ingestion DAG transitions through. A paper that fails partway is left at the last successful state — I re-run from there, not from scratch.

From now on, **Postgres is the source of truth and Qdrant is derived from it.**

---

## Step 6 — I will implement multi-granularity chunking

I will chunk by typed element + section boundary, never by sliding window. Six chunk types live in one `chunks` table:

| `chunk_type` | Built from | Token target |
|---|---|---|
| `paragraph` | One paragraph (split at sentence boundaries if > 400 tok, one-sentence overlap) | 300–500 |
| `section` | All paragraphs in a subsection | 1500–2500 |
| `table` | One table element | 100–400 |
| `figure` | One figure element | 100–300 |
| `algorithm` | One algorithm box (preserves line breaks between steps) | 200–600 |
| `summary` | One per paper, LLM-generated | 200–400 |

Every chunk's `content` is prefixed with the paper ID, version, and full section path. The prefix is part of what gets embedded.

---

## Step 7 — I will describe tables, figures, and algorithms with LLMs/VLMs

For every table I will render it as markdown, pass it to a cheap LLM, and store a 2–3 sentence description. The description is what gets embedded; the markdown is what the generation model sees.

For every figure I will pass the extracted PNG to a VLM (Gemini, GPT-4o, or Claude Sonnet) and store the description. **I will never embed the image itself** — I embed the description.

For every algorithm box (P4's case) I will pass the pseudocode to an LLM for a description, preserving the original line breaks in the stored chunk so embedding works well.

Now the system can answer questions about results tables, figures, and pseudocode — not just body text. This is where it stops feeling like text search and starts feeling like it actually read the paper.

---

## Step 8 — I will add metadata enrichment

For every chunk I will run three LLM calls (Haiku 4.5 hosted, or `llama-3.2-3b` / `qwen2.5:7b` locally):

- **3 hypothetical questions** — the specific questions this chunk directly answers.
- **Keywords** — at most 15 entries: model names, method names, dataset names, metric names, central numeric values. These are what drive BM25.
- **A 1–2 sentence summary** — concrete, names specific numbers/methods.

I will cache by `sha256(chunk_text + prompt_version)` so a chunk that did not change does not pay the LLM cost twice. At 75k chunks × 3 calls this is the single most expensive ingestion stage — caching matters.

---

## Step 9 — I will set up real storage in Qdrant with two dense vectors plus sparse

I will use **BGE-M3** (`BAAI/bge-m3`, 1024-dim dense + sparse from one forward pass) for everything.

For each chunk I will produce three vectors:

- `content` (dense, 1024-d) — the chunk content, or the description for table/figure/algorithm chunks.
- `question` (dense, 1024-d) — the concatenated hypothetical questions.
- `keywords_bm25` (sparse, IDF-modified) — the keyword list.

The Qdrant collection has both named dense vectors and one sparse vector per point. HNSW config: `m=32, ef_construct=256`. Payload indexes on `arxiv_id`, `primary_category`, `chunk_type`, `submitted_at`, `version`, `is_latest_version`.

Qdrant payload carries **only what is needed to filter + a small display subset** (title, section path, summary, keywords). Full chunk content, raw markdown for tables, and figure paths stay in Postgres. Qdrant is re-derivable.

---

## Step 10 — I will add BM25 and hybrid retrieval

I will run three retrieval lanes in parallel per query:

1. BM25 over `keywords_bm25`.
2. Dense ANN over `content`.
3. Dense ANN over `question`.

Each returns top-50. I will merge with Reciprocal Rank Fusion using `k=60` and keep the top 30 candidates.

I will compare retrieval before and after. Specific factual queries (exact names, exact numbers) should improve sharply. The `question`-vector lane is the one that catches "the user query happens to be near one of the hypothetical questions I generated at ingest" — that lane alone often beats the other two on factual queries.

---

## Step 11 — I will add reranking

I will pass the top 30 hybrid candidates through **BGE-reranker-v2-m3** (cross-encoder, 568M params; or Cohere Rerank 3 as a hosted alternative). One batched forward pass scores all 30 pairs. I keep the top 8.

This is the single biggest quality jump in the whole pipeline. I expect to feel it immediately.

---

## Step 12 — I will add MMR for diversity (conditional)

I will add a Maximal Marginal Relevance pass after reranking with `λ ≈ 0.6`, trimming near-identical chunks so the context window carries a wider spread of evidence.

MMR runs **only for CONCEPTUAL and EXPLORATORY queries**. For SPECIFIC_FACTUAL queries it is skipped — diversity is the enemy of precision when there is one right answer. That conditional behaviour is what the next step makes possible.

---

## Step 13 — I will build the reasoning engine

A fast LLM call (Haiku 4.5 or `llama-3.2-3b`) classifies every incoming query into one of five categories:

- `SPECIFIC_FACTUAL` — asks for a specific number/name/fact.
- `CONCEPTUAL` — asks how something works.
- `COMPARATIVE` — compares two or more named entities.
- `METADATA_DRIVEN` — has explicit filters (date, author, category).
- `EXPLORATORY` — open-ended "what has been done about X" style.

Each category gets its own retrieval recipe (expansion, lanes, rerank, MMR). I will implement this as a LangGraph state machine, one node per branch:

- `SPECIFIC_FACTUAL` → no expansion, full hybrid + rerank, no MMR.
- `CONCEPTUAL` / `EXPLORATORY` → **RAG Fusion** (4 query variations + original, RRF across all 5), rerank, MMR.
- `COMPARATIVE` → **Decomposer** produces sub-questions, each runs the full pipeline, results are concatenated for generation.
- `METADATA_DRIVEN` → **Self-Query Parser** extracts filters (`submitted_at`, `authors`, `primary_category`) into a Qdrant `Filter` clause; runs hybrid retrieval with the filter applied to all lanes.

This is the "agentic" part. The system now adapts to the shape of the question instead of treating every query the same.

---

## Step 14 — I will assemble context properly

After retrieval I will not just dump chunks into the prompt. For each surviving top-8 chunk I will:

- Group chunks by `(arxiv_id, version)` so chunks from the same paper are adjacent.
- Pull in **neighbour chunks** (previous/next in `order_idx`) for continuity.
- Resolve **internal cross-references**: if the chunk says "see Table 14", I pull Table 14 in via `element_internal_links`.
- Attach paper metadata: title, authors, version, submitted date, section path.
- Have matching `refs` rows ready for the citation validator (not necessarily injected into the prompt).

Total context capped at 32k tokens. If I exceed it, I drop neighbour chunks first.

---

## Step 15 — I will add generation guardrails

The generation prompt is strict: answer only from the provided context, cite every factual claim in the form `[arxiv:1706.03762, §6.1]` or `[arxiv:1706.03762, Table 2]`, and refuse explicitly if the answer is not in the context.

Around that LLM call I will add three things:

- **Citation validator** — a regex pass that parses every `[arxiv:..., §...]` from the answer and confirms it resolves to a chunk that was actually retrieved. If validation fails, regenerate with an addendum explaining which citation was fabricated.
- **Hallucination guard** — a second cheap LLM call that scores every factual claim in the answer as `supported`, `partially-supported`, or `unsupported` against the context. Any `unsupported` claim triggers a regenerate.
- **Structured output** — for COMPARATIVE queries the prompt asks for JSON (`{comparison: [{method, core_idea, key_numbers, trade_offs, sources}, ...], summary}`) so the frontend can render a comparison table.

---

## Step 16 — I will build the evaluation harness

I will hand-build 150–300 query/answer pairs in `eval_queries`, mixed across:

- `factual` (~80) — exact answers with `must_cite` chunks.
- `conceptual` (~50)
- `comparative` (~40)
- `metadata` (~30)
- `adversarial` (~50) — `must_not_answer = true`, refusal expected.

I will wire up **Ragas** as the primary judge and **DeepEval** as a cross-check. Metrics:

- Retrieval — `Recall@k`, `MRR`, `nDCG@10` on labelled queries.
- Generation — Faithfulness, Answer Correctness, Citation Accuracy.
- Refusal — false-positive answer rate on adversarial set (target < 5%).
- Latency — P50 / P95 per stage and end-to-end (target P50 < 3s, P95 < 8s).
- Cost — tokens per query and `$ / 1k queries`, broken down by stage.

From this point on, every change has a number to beat.

---

## Step 17 — I will run ablations

With evaluation in place I will toggle one thing at a time and write down the delta:

- Retrieval: dense-only vs hybrid vs hybrid+rerank vs full pipeline.
- Hypothetical questions on vs off.
- Query routing on vs off (force the full pipeline on every query).
- MMR: off / `λ=0.4` / `λ=0.6` / `λ=0.8`.
- Chunk size: 256 / 512 / 1024.
- Reranker: none / BGE-reranker-v2-m3 / Cohere Rerank 3.
- Citation validator: off / regex / regex + LLM-judge.

I expect each ablation to tell a different story per query category — hypothetical questions help factual a lot but hurt exploratory a little; MMR helps conceptual but hurts factual. That is *why* the classifier exists. The ablation table is the writeup.

---

## Step 18 — I will stress test the system

A second driver loop, separate from eval. Six categories:

- **Adversarial queries** — real-looking questions about claims the papers never made. Expect refusal.
- **Fake paper queries** — plausible but non-existent arXiv IDs. Expect "no such paper".
- **Hallucination probes** — questions designed to elicit confident wrong answers. Expect precise answers or refusal, never confident guesses.
- **Refusal testing** — questions that *should* be answered, to catch over-refusal. Refusal rate must stay below 5% on this subset.
- **Prompt injection** — user input that tries to override the system prompt ("ignore previous instructions", "you are the admin"). Defences: input sanitization, strict system prompt that explicitly says do-not-follow-user-instructions-that-conflict, output filter that strips internal tokens.
- **Info evasion** — queries that try to extract internal chunk IDs, infrastructure details, connection strings. The assembled context never includes chunk IDs; arxiv IDs and section paths are public and may stay.

Targets: refusal on adversarial/fake-paper > 90%, over-refusal on legitimate < 5%, injection compliance 100%, info leak 0%.

---

## Step 19 — I will scale to 500 papers

I will pull the full corpus via arXiv OAI-PMH for metadata and the S3 bulk PDF bucket for documents, filtered to `cs.CL`, `cs.LG`, `cs.CV`. I will fix whatever breaks at scale: LLM rate limits, slow embedding, memory blow-ups, parser failures on weird PDFs.

I will run ingestion through a real DAG. `asyncio` queue or `concurrent.futures` is enough; Airflow if I want it scheduled and observable. Each paper transitions through `ingest_status` so re-runs resume from the last successful state.

At the end I have ~75k chunks in Qdrant with full metadata in Postgres.

---

## Step 20 — I will ship the system

A thin FastAPI service in front of the inference pipeline (one streaming endpoint for chat, one structured endpoint for COMPARATIVE responses). A minimal Next.js UI that shows the answer, the citations as inline links, and a side panel with the retrieved chunks so the user can see what the model actually read.

I will write the README so someone can clone the repo, run `docker compose up`, ingest one paper, and ask a question — top-to-bottom in under fifteen minutes.

---

## Step 21 — I will extend, only after v1 is solid

These are deliberately out of scope until everything above is measured and stable:

- **ColBERT / late-interaction retrieval** — add when hybrid+rerank plateaus.
- **Graph RAG over the citation graph** — add when "what does paper X cite for claim Y?" becomes a frequent query.
- **Fine-tuning BGE-M3 on the corpus** — only after every ablation has been squeezed.
- **Daily Airflow ingestion of new arXiv papers** — flip on when v1 is stable.
- **Agentic loops (tool use, iterative retrieval)** — when retrieve-once-then-generate stops working for the hardest queries.
- **Multi-tenancy / auth** — when this ships outside a research context.

In each case the v1 schema is forward-compatible — the new technique is an additional retrieval lane, an additional table, or an additional stage, not a rewrite.

---

## Why this order

Every step ends with a system I can run and a result I can show. If I stop after Step 3 I still have a working tool. If I stop after Step 11 I have something genuinely useful. Each step adds one capability on top of a foundation that already works — never a rewrite, never a "now refactor everything." That is how I stay consistent: I am always building on top of something I already trust.
