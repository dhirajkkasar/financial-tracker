# Quick-Start Command Design

**Date:** 2026-04-10  
**Status:** Approved  

## Overview

Add a `python cli.py quick-start` command that guides a first-time user through importing all their investments interactively, one asset type at a time, without needing to know individual CLI commands.

## Scope

### Included asset types
| Label shown to user | Mechanism | CLI equivalent |
|---|---|---|
| PPF | File import (CSV) | `import ppf` |
| EPF | File import (PDF) | `import epf` |
| Mutual Funds (CAS PDF) | File import (PDF) | `import cas` |
| NPS | File import (CSV) | `import nps` |
| Indian Stocks (Zerodha CSV) | File import (CSV) | `import zerodha` |
| FD | Manual entry | `add fd` |
| RD | Manual entry | `add rd` |
| Gold | Manual entry | `add gold` |
| Real Estate | Manual entry | `add real-estate` |

### Excluded
- Fidelity RSU / Fidelity Sale (require USD/INR exchange rate prompts per month — handled separately)
- `add rsu` and `add us-stock` standalone commands (covered by Fidelity imports — remove from docs)
- SGB (covered by Gold or Zerodha imports)

## Flow

```
quick-start
  │
  ├── 1. DB freshness check
  │       GET /assets → if any assets exist: print help + individual commands + exit
  │
  ├── 2. Member setup
  │       GET /members
  │       0 members → prompt PAN + name → POST /members → use for all
  │       1 member  → print "Using: {name} ({pan})" → use for all
  │       2+ members → show numbered list → ask per-file later
  │
  └── 3. Asset type loop (in order)
          For each asset type:
            "Do you have [label] investments? [y/n]: "
            If n/skip → next asset type
            If y (file type):
              If 2+ members → "Which member does this file belong to? [1/2/...]"
              "Enter file path for [label]: "
              → import → print result
              "Import another file for [label]? [y/N]: " → loop or next
            If y (manual type):
              If 2+ members → "Which member does this belong to? [1/2/...]"
              → prompt fields → add → print result
              "Add another [label]? [y/N]: " → loop or next
```

Asset type order: PPF → EPF → Mutual Funds → NPS → Indian Stocks → FD → RD → Gold → Real Estate

## DB Freshness Check

If `GET /assets` returns any data, print:

```
Your database already has existing data. Use individual commands to add more:

  Import commands (server must be running):
    python cli.py import ppf <file> --pan <PAN>
    python cli.py import epf <file> --pan <PAN>
    python cli.py import cas <file> --pan <PAN>
    python cli.py import nps <file> --pan <PAN>
    python cli.py import zerodha <file> --pan <PAN>

  Manual add commands:
    python cli.py add fd --name ... --pan <PAN> --bank ... --principal ... --rate ... --start ... --maturity ... --compounding ...
    python cli.py add rd --name ... --pan <PAN> --bank ... --installment ... --rate ... --start ... --maturity ... --compounding ...
    python cli.py add gold --name ... --pan <PAN> --date ... --units ... --price ...
    python cli.py add real-estate --name ... --pan <PAN> --purchase-amount ... --purchase-date ... --current-value ... --value-date ...
```

Then exit. No wipe option.

## Member Resolution

- **0 members:** prompt `PAN:` and `Name:` → `POST /members` → use this member_id for all subsequent steps
- **1 member:** auto-select, print `"Using: {name} (PAN: {pan})"`, no prompts needed
- **2+ members:** at the start of each file import or manual entry, prompt `"Which member does this belong to?"` with a numbered list. Member selection is **per file** (not per asset type) since different files can belong to different members.

## Manual Entry Field Prompts

### FD
```
Name (e.g. HDFC FD 2024): 
Bank:
Principal amount (INR):
Interest rate (%):
Start date (YYYY-MM-DD):
Maturity date (YYYY-MM-DD):
Compounding [MONTHLY/QUARTERLY/HALF_YEARLY/YEARLY]:
```

### RD
```
Name (e.g. SBI RD 2024):
Bank:
Monthly installment (INR):
Interest rate (%):
Start date (YYYY-MM-DD):
Maturity date (YYYY-MM-DD):
Compounding [MONTHLY/QUARTERLY/HALF_YEARLY/YEARLY]:
```

### Gold
```
Name (e.g. Digital Gold):
Purchase date (YYYY-MM-DD):
Units (grams):
Price per unit (INR/gram):
```

### Real Estate
```
Name (e.g. Venezia Flat):
Purchase amount (INR):
Purchase date (YYYY-MM-DD):
Current value (INR):
Value date (YYYY-MM-DD):
```

## Code Structure

### New file: `backend/quick_start.py`

```
run()                               # entry point called from cli.py
_check_db_empty()                   # GET /assets → print help + exit if data exists
_resolve_member()                   # member setup: returns (members_list, single_member_id_or_None)
_ask_member(members, label)         # numbered prompt for multi-member selection, returns member_id
_section_file(label, import_fn)     # loop: ask member (if needed) → prompt path → import → "another?"
_section_manual(label, add_fn)      # loop: ask member (if needed) → add_fn(member_id) → "another?"
_add_fd_interactive(member_id)      # prompt FD fields → cmd_add_fd()
_add_rd_interactive(member_id)      # prompt RD fields → cmd_add_rd()
_add_gold_interactive(member_id)    # prompt Gold fields → cmd_add_gold()
_add_real_estate_interactive(member_id) # prompt RE fields → cmd_add_real_estate()
```

All `cmd_*` functions are imported from `cli.py` — no logic duplication.

### Changes to `backend/cli.py`
- Add dispatcher: `elif args.command == "quick-start": from quick_start import run; run()`
- Remove `add rsu` and `add us-stock` entries from the module docstring (Fidelity imports cover these)
- Add `quick-start` to the usage docstring

### No other files changed
No API changes, no service changes, no frontend changes.

## Completion

After all asset types are processed, print:
```
Quick-start complete! Next steps:
  python cli.py refresh-prices   # fetch current prices for all assets
  python cli.py snapshot         # save a portfolio snapshot
```
