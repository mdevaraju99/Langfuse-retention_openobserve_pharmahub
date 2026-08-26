# Langfuse ops (single folder)

All integration scripts for **multiple POCs** live here. The backend app only needs runtime tracing (`utils/langfuse_trace.py`); everything else runs from this folder.

## Layout

```
ops/
├── cli.py                 # ONE entry point — run all commands from here
├── bridge.py              # call cli from Streamlit: from ops.bridge import run_ops
├── config_loader.py       # loads pocs/*.yaml + .env
├── langfuse_ops.py        # shared Langfuse SDK helpers
├── health.py
├── info.py
├── list_pocs.py
├── seed_prompt.py
├── seed_all.py
├── seed_evaluators.py
├── print_scores.py
├── pocs/                  # per-POC config (YAML only)
│   ├── pharma-hub.yaml
│   └── job-optimizer.yaml
└── prompts/               # per-POC prompt text files
    ├── pharma-hub/
    └── job-optimizer/
```

## Commands

```powershell
cd D:\Documents\KN_HUB2\Pharma_final_version1

python ops/cli.py list-pocs
python ops/cli.py info --poc pharma-hub
python ops/cli.py health --poc pharma-hub
python ops/cli.py health-openobserve
python ops/cli.py openobserve-guide
python ops/cli.py seed-prompt --poc pharma-hub --variant baseline --label baseline
python ops/cli.py seed-prompt --poc pharma-hub --variant bullets --label production
python ops/cli.py seed-all --poc pharma-hub
python ops/cli.py seed-evaluators
python ops/cli.py print-scores --poc pharma-hub --trace-id YOUR_TRACE_ID
```

## New POC

1. Add `pocs/my-poc.yaml`
2. Add `prompts/my-poc/*.txt`
3. Run `python ops/cli.py seed-all --poc my-poc`

## From Streamlit

```python
from ops.bridge import run_ops

run_ops("seed-all", poc_id="pharma-hub")
```

Set `POC_ID=pharma-hub` in `.env`.
