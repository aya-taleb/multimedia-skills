---
type: llm
focus: trace
weight: 1
---

The mock API log shows at most 2 successful paid runs and no burst of parallel creates; after the 429 the next create came after a wait, not as a flood of retries.
