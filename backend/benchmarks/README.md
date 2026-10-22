# Global analytical benchmark

This corpus measures compute accuracy separately from narrative quality across commerce,
finance, SaaS, marketing, manufacturing, planning, data modelling, and governance.

Run the deterministic platform benchmark:

```bash
cd backend
venv/bin/python benchmarks/run_benchmark.py
```

Optionally compare raw model answers through OpenRouter (this consumes provider credits):

```bash
OPENROUTER_API_KEY=... venv/bin/python benchmarks/run_benchmark.py \
  --live \
  --models openai/gpt-5,google/gemini-2.5-pro,anthropic/claude-sonnet-4
```

The JSON scorecard is written to `benchmarks/results/latest.json`. Do not commit live
responses if they may contain sensitive data. Benchmark fixtures are synthetic and global;
no production or customer data is sent to model providers.
