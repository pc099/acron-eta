# Feature Store and Guided Mode

This document explains **what the Feature Store is and how it’s used** in ACRON, and **what Guided mode** is in inference routing.

---

## Feature Store (what it is and what’s happening)

### What it is

The **Feature Store** is a component that holds **precomputed or stored features** (e.g. user preferences, org plan, product metadata) and serves them during inference. It does **not** store “future” data; it stores **features** that describe entities (user, organization, product, etc.) and that can be injected into prompts so the model has more context.

### How ACRON uses it

1. **Enricher**  
   Before sending a prompt to the LLM, the **FeatureEnricher** (in `src/features/enricher.py`) can call the feature store to get features for the current user, org, or related entities.

2. **What gets stored / retrieved**  
   - **Entity types:** e.g. `user`, `organization`, `product`.  
   - **Feature names:** e.g. for “user” – `purchase_history`, `preferences`, `tier`; for “organization” – `plan`, `account_status`.  
   - The store returns a **FeatureVector** (entity id, type, and a map of feature name → value).

3. **How it’s used in the request**  
   The enricher turns those features into a short **context block** (e.g. “[Context from user profile] … [End context]”) and **prepends it to the user’s prompt**. That way a cheaper/smaller model can still give good answers because it “sees” the user’s preferences or org context. So the feature store is what **feeds** that context; it’s not a generic “future store” for arbitrary data.

4. **Current implementation (LocalFeatureStore)**  
   - By default ACRON uses a **local** feature store: `LocalFeatureStore` in `src/features/client.py`, which reads from a **local JSON file** (path from config, e.g. `feature_store.local_data_path`).  
   - So “what’s happening” right now: if the enricher is enabled and that path exists, it loads features from that file and injects them into the prompt. No external service is required.  
   - The code also supports other backends (e.g. **Feast**, **Tecton**, or a **custom** HTTP store) via the same `FeatureStoreClient` interface; you’d switch config and implement or wire that client.

5. **When it runs**  
   The optimizer calls the enricher only when it’s configured and when the request has a `user_id` or `organization_id`. So the feature store is used only on the path where enrichment is enabled and those IDs are present.

**Summary:** The feature store holds **features** (attributes of users, orgs, products). ACRON uses them to **enrich prompts** with extra context so routing and inference can be smarter. Right now that’s powered by a **local JSON file**; other backends can be plugged in via the same interface.

---

## Guided Mode (what it is and how it works)

### What it is

**Guided mode** is one of three inference **routing modes**:

- **Autopilot** – ACRON decides everything (task type + model) from the prompt.  
- **Guided** – You set **quality** and **latency** preferences; ACRON still picks the **model** for you.  
- **Explicit** – You choose the **exact model** (and optionally provide a provider API key).

So in Guided mode you do **not** choose a model by name; you choose a **tradeoff** (e.g. “high quality, fast”), and ACRON picks a model that fits.

### How it works (step by step)

1. **You send a request** with `routing_mode: "guided"` and optionally:
   - `quality_preference`: `"low"` | `"medium"` | `"high"` | `"max"`.
   - `latency_preference`: `"slow"` | `"normal"` | `"fast"` | `"instant"`.

2. **Task detection**  
   ACRON detects the **task type** from the prompt (e.g. summarization, FAQ, coding) the same way as in Autopilot.

3. **Preferences → constraints**  
   The **ConstraintInterpreter** (`src/routing/constraints.py`) turns your preferences into numbers:
   - **Quality** → a **quality threshold** (min quality score the model must meet).
   - **Latency** → a **latency budget** (max ms).
   - Some **task types** tighten these (e.g. summarization may require a minimum quality or a max latency).

4. **Model selection**  
   The **router** gets those constraints and picks a **model** from the registry that:
   - Meets the quality threshold, and  
   - Stays within the latency budget,  
   and is a good fit for the detected task.

5. **Result**  
   You get a single chosen model and the inference result. The response includes the **reason** (e.g. “User preference (quality=high, latency=fast) + task 'summarization': …”).

### Example

- You set **quality_preference: "high"** and **latency_preference: "fast"**.  
- Prompt is detected as “summarization”.  
- ACRON might pick a model that is both high quality and low latency for that task, instead of the very cheapest or the very slowest. You never specify “gpt-4” or “claude”; the system chooses.

### When to use Guided vs Autopilot vs Explicit

- **Autopilot** – Default; good when you want minimal configuration and are fine with ACRON’s defaults.  
- **Guided** – Use when you care about the **tradeoff** (e.g. “I want high quality and can wait a bit” or “I want fast and okay with lower quality”) but don’t want to pick a specific model.  
- **Explicit** – Use when you **must** use a specific model (e.g. for compatibility or reproducibility).

---

## Summary

| Topic | Summary |
|--------|--------|
| **Feature store** | Stores **features** (user/org/product attributes). Used to **enrich prompts** with context so cheaper models can perform better. Currently implemented as a **local JSON** store; other backends (Feast, Tecton, custom) can be wired in. |
| **Guided mode** | You set **quality** and **latency** preferences; ACRON **picks the model** that fits those constraints and the detected task. You do not choose the model by name. |
