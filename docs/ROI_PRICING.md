# ROI and pricing

## Estimated savings with Asahi

Asahi reduces inference cost by routing to cheaper models when quality and latency allow, and by serving repeated or similar prompts from cache. Internal benchmarks typically show:

- **Cost savings:** ~85–92% in cache-heavy and mixed workloads vs. always using a single premium model.
- **Cache impact:** Tier 1 (exact) and Tier 2 (semantic) hits avoid LLM calls entirely; Tier 3 reuses intermediate results in workflow settings.

**Rough guide:** If your current monthly LLM spend is **$X**, expect **estimated savings** in the range of **0.85 × X** to **0.92 × X** as cache warms and routing optimizes (actual results depend on prompt mix, cache hit rate, and quality/latency constraints).

| Current monthly spend (LLM) | Estimated savings (85%) | Estimated spend with Asahi (15%) |
|-----------------------------|--------------------------|----------------------------------|
| $1,000                      | $850                     | $150                             |
| $5,000                      | $4,250                   | $750                             |
| $20,000                     | $17,000                  | $3,000                           |

Use your own usage and Asahi metrics (e.g. `GET /analytics/cost-summary`, `GET /governance/usage`) to compute actual savings after deployment.

## Pricing tiers (Asahi service)

Plans are for the Asahi platform (API, dashboard, governance). LLM provider costs (OpenAI, Anthropic) are separate and paid by you; Asahi optimizes those costs.

| Plan       | Typical monthly (platform) | Notes                          |
|------------|----------------------------|--------------------------------|
| **Startup**   | ₹15K / ~$180               | Small teams, single org        |
| **Business**  | ₹50K / ~$600               | Multiple orgs, higher limits    |
| **Enterprise**| ₹2L+ / ~$2,400+            | Custom SLAs, support, on-prem   |

*Numbers are indicative; confirm with sales or your contract.*

## MVP note

No automated payment processing is required for MVP. Billing can be manual (invoicing) until Stripe or another payment provider is integrated. Usage and cost data are available via `GET /governance/usage` and analytics endpoints for reconciliation and invoicing.
