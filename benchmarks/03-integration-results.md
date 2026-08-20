# 03 - Integrate: RAG pipeline run

Host `Windows-AMD64` · llama.cpp `b10488` ·
retrieval backend: **keyword overlap** · 3 queries

| Query | Contexts retrieved | embed (ms) | retrieve (ms) | llm (ms) | total (ms) |
|:--|--:|--:|--:|--:|--:|
| Why is goodput more useful than raw throughp... | goodput, paged, radix | 0.0 | 0.0 | 4768.2 | 4768.5 |
| What problem does PagedAttention actually so... | paged, radix, disagg | 0.0 | 0.0 | 3204.1 | 3204.2 |
| When does splitting prefill and decode help?... | disagg, radix, batching | 0.0 | 0.1 | 3183.1 | 3183.2 |

Mean per stage (ms): embed **0.0** · retrieve **0.0** ·
llm **3718.5** · total **3718.6**
Dominant stage: **llm** (100% of total)

## Answers returned

**Why is goodput more useful than raw throughput?**

> Goodput@SLO counts only the requests per second that met the TTFT and TPOT targets. Throughput at saturation ignores SLOs.

**What problem does PagedAttention actually solve?**

> PagedAttention stores the KV cache in non-contiguous pages, removing the internal fragmentation that wasted most GPU memory.

**When does splitting prefill and decode help?**

> Splitting prefill and decode helps because prefill is compute-bound and decode is memory-bandwidth-bound.


## Which N16-N19 pieces are real

- **N16 Cloud/IaC**: stub — localhost only, no cluster or Compose stack stood up.
- **N17 Data pipelines**: stub — `TOY_DOCS` is an in-memory Python list, not a real
  ingestion job.
- **N18 Lakehouse**: stub — no SQLite/Delta/Iceberg table; documents live in the same
  in-memory list as N17.
- **N19 Vector + features**: stub, and the fallback path specifically — no embedding
  server was running, so `retrieve()` used the keyword-overlap fallback, not real
  vector search (`embed: 0.0 ms` above is that fallback, not a fast embedder).
- **N20 Serving**: real — `llama-server` on port 8090 (moved off the default 8080,
  which collides with an existing Docker service on this machine), OpenAI-compatible
  `/v1/chat/completions`, real GPU decode.

The dominant stage is **llm at 100%**, which matches expectations — with `embed` and
`retrieve` stubbed to near-zero cost, the LLM call was always going to be everything.
It would have been more surprising if embed/retrieve were real and *still* negligible;
here they are negligible because they are not doing real work yet.

To halve this pipeline's latency, I would attack the **llm** stage specifically its
**TTFT/prefill portion**, not decode: each query's prefill (113-149 prompt tokens)
took 220-420ms while decode (23-30 tokens) took 340-540ms, so at this short output
length prefill and decode are roughly comparable, but the real cost driver is model
load path and first-token latency, not raw decode throughput (decode is already fast
at `ngl=99`, ~69 tok/s from `01-quickstart-results.md`). Concretely: keep the system
prompt byte-identical across calls so the server can reuse the cached KV prefix
(`prompt_tokens_total` growing slower than `tokens_predicted_total`), which directly
cuts prefill cost on repeated/similar queries — that is the cheapest lever available
without touching quantization or hardware.
