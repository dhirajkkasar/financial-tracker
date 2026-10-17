# ITR Preparation Utility — Design

**Status:** Draft for review
**Date:** 2026-10-16
**Author:** agent
**Related:** `docs/taxation_rules.md`, `backend/app/services/tax_service.py`, `backend/app/engine/income_tax.py`, `docs/superpowers/specs/2026-04-04-config-driven-tax-rules-design.md`

---

## 1. Problem

The tracker already computes *realised capital gains*, *unrealised gains*, *tax-loss
harvesting*, and a first-cut tax estimate (STCG/LTCG/interest split, slabs,
surcharge, cess, 87A, set-off, carry-forward). It does **not**:

- ingest **Form 16** (salary/TDS),
- assemble a **whole return** (salary + capital gains + interest + foreign
  income + foreign assets + loss set-off/carry-forward),
- emit the **ITR JSON** accepted by the Income Tax Department's offline utility,
- persist a **per-PAN, per-year return** so next year reuses opening balances,
  carry-forwards and fixed blocks.

The goal is a **local, offline ITR preparation utility** that, at the end of an
Indian financial year (31 March), turns the tracker's investment/sale history
plus an optional Form 16 into a **validated ITR-2 JSON** the user imports into
the official Common Offline Utility and files.

---

## 2. Goals / Non-goals

### Goals

1. Per **PAN (member)** and per **Assessment Year (AY)** returns.
2. Optional **Form 16 PDF** ingestion → salary, exemptions, Chapter VI-A,
   perquisites, TDS, employer identity.
3. Aggregate income from existing data:
   - capital gains/losses per asset (Indian equity, US equity, MF, gold, real
     estate, SGB, RSU),
   - FD/RD interest (already derived),
   - savings-bank interest, dividends, other interest (manual or imported),
   - foreign income (US dividends, US capital gains).
4. Apply **loss set-off and 8-year carry-forward** across years.
5. Compute tax for the **new regime** (s.115BAC(1A)) fully: slabs, special
   rates 111A/112A, 112A ₹1.25L exemption, 87A rebate + marginal relief,
   surcharge caps, cess. Old regime: phase 2.
6. Produce **ITR-2 JSON** (and ITR-1 when eligible) that:
   - validates against the **official AY-specific JSON schema**,
   - imports cleanly into the **Common Offline Utility**.
7. Persist each year's return inputs + generated JSON for reuse.
8. Work **fully offline** — no portal APIs, no credentials.

### Non-goals (explicitly out)

- Direct portal upload via API or auto e-filing. (And see §8.2 — a self-built
  JSON cannot be *directly* uploaded at all.)
- ITR-3/4/5/6/7, business/professional income, F&O/intraday, presumptive income.
- NRI/RNOR computation, HUF/company returns.
- Audit cases, transfer pricing, advance-tax challan payment.
- Being a substitute for a CA on complex cases. The output is a **draft the
  user verifies**.

---

## 3. Domain model

New vocabulary (add to `CONTEXT.md` when implemented):

| Term | Meaning |
|---|---|
| **Financial Year (FY)** | 1 Apr → 31 Mar, labelled `2025-26`. Already used across the codebase. |
| **Assessment Year (AY)** | FY + 1, labelled `2026-27`. What the ITR form is "for". `AY = FY start + 1`..`+2`. |
| **ITR Return** | One member's filing for one AY. The persisted unit of work. |
| **Return Draft** | The assembled, typed return (income + gains + computation), before JSON. |
| **Return JSON** | The AY-specific JSON document built from a Return Draft. |
| **Form 16 Summary** | Deterministic parse of a Form 16 PDF (per employer). |
| **Schedule FA window** | Foreign-asset disclosure uses the **calendar year** (1 Jan–31 Dec), not the FY. Income schedules use the FY. |
| **Software Provider ID** | Registered vendor stamp the portal requires for direct JSON upload. We do not have one. |

---

## 4. Assessment-year model

- FY `2024-25` → AY `2025-26`; FY `2025-26` → AY `2026-27`.
- **Tax rules** are already FY-keyed (`app/config/tax_rates/{FY}.yaml`).
- **ITR JSON schemas** are **AY-keyed** and versioned. Bundle schemas under
  `backend/app/config/itr_schemas/AY{YYYY-YY}/`. **AY 2026-27 ITR-2 = `V1.2`**
  (`ITR-2_2026_Main_V1.2.json`, released 13-Aug-2026; `$schema` draft-04). The
  matching CBDT docs are `ITR 2_Schema change document_AY2026-27_V1.2.pdf` and
  `CBDT__e-Filing_ITR 2_Validation Rules_AY 2026-27_V1.0.pdf` (the rules doc is
  v1.0, i.e. older than the v1.2 schema — the v1.2-only
  `EditAutopoulatedDetail` fields are not in it).
- The return carries both `fy_label` and `ay_label`; builders are registered
  per AY.
- New AY = drop in a schema + (usually) a new builder subclass; no changes to
  the assembler.

`engine/itr/ay.py` owns `fy_to_ay()` / `ay_to_fy()` and AY parsing/validation.

---

## 5. Inputs and sources

### 5.1 Form 16 (optional) — `engine/form16_parser.py`

A pure parser with two layers so it is testable without a PDF:

```
def parse_form16_text(text: str) -> Form16Summary: ...   # unit-testable
def parse_form16_pdf(file_bytes: bytes) -> Form16Summary: ...  # pdfplumber → text → parse
```

`Form16Summary` (dataclass): employer name/TAN/address, employee PAN/name,
period, `gross_salary` (§17(1)+17(2)+17(3)), §10 exemptions, standard deduction
(§16(ia)), professional tax (§16(iii)), perquisites, Chapter VI-A amounts
(80C/80CCD(2)/80D/…), `total_taxable_income`, TDS, regime flag
(opted out of 115BAC?).

Determinism notes: Form 16 layouts vary. The parser is **label/regex driven**
with a confidence + warnings list; unresolved fields are surfaced, never
silently zeroed. `pdfplumber` is already a dependency.

Not an `ImportPipeline` importer: Form 16 has no transactions, so it is a
dedicated parser + a service that stores the summary in the return input.

### 5.2 Capital gains (asset-derived) — reuse + extend `TaxService`

`TaxService.get_tax_summary(fy, member_id)` already yields per-asset ST/LT gains
and slab/fixed flags. The ITR layer needs more than the summary:

- **per-lot detail** for Schedule 112A (ISIN, scrip name, qty, sale value, cost,
  FMV as on 31-Jan-2018, grandfathered cost, gain) — build a dedicated
  `engine/itr/schedule_112a.py` over the same lot engine.
- **ITR buckets**: STCG 111A (20%), STCG at slab (other assets incl. STOCK_US),
  LTCG 112A (12.5% + ₹1.25L), LTCG 12.5% other. Map from existing
  `AssetTaxGainsResult`.

### 5.3 Interest income

- **FD/RD**: already derived by `AccruedInterestTaxGainsStrategy` (exact FD
  compound, RD prorated).
- **Savings bank**: not an asset today → **manual** per-year input (or
  `important_data` BANK with interest). Stored in the return input.
- **Dividends (Indian)**: manual per-year input; optionally derived later from
  `DIVIDEND` transactions.
- **Interest on income-tax refund**: manual.

### 5.4 Foreign income & assets

- **US capital gains**: already `STOCK_US` → mapped to STCG-slab / LTCG-12.5%.
- **US dividends**: manual per-year input (broker 1042-S / 1099). Schedule OS +
  FSI.
- **Schedule FA**: foreign holdings at any time in the **calendar year**.
  Derived from `STOCK_US` `BUY`/`VEST`/`SELL` transactions (open/closed windows),
  with a manual **opening balance / peak value / closing value** override per
  asset when history is incomplete.
- **Rule 115 exchange rate**: ITR conversion should use the SBI TT-buying rate
  of the relevant date, not the app's monthly user rate. Phase D introduces a
  rate table + manual entry; the app rate is a documented fallback.

### 5.5 Loss carry-forward

Existing `tax_loss_carryforwards` (per member, `amount_inr`/`remaining_inr`,
STCL/LTCL, 8-year expiry). Extend in phase E to ITR-2's Schedule CFL shape
(STCL, LTCL, and — when applicable — HP/other-source losses). The draft's
set-off order must match the utility's (STCL → STCG then LTCG; LTCL → LTCG).

### 5.6 Per-year manual inputs (the return input document)

Everything the assets cannot supply lives in one **typed, validated input
document** per member+AY (Pydantic). This is the "keep data of each year"
artifact:

```
ReturnInput {
  fy_label, ay_label, member_id,
  regime: "new" | "old",
  residential_status, dob, pan, name,
  address, bank_accounts[],           # refund + Schedule AL later
  salary: Form16Summary[],            # 0..n employers
  other_income: { savings_interest, term_deposit_interest_override,
                  dividends[], interest_on_it_refund, other[] },
  foreign: { dividends[], tax_paid_abroad, fa_asset_overrides[] },
  capital_gains_overrides,            # manual adjustments / animations
  challans[], taxes_paid,             # self-assessment, advance tax (if any)
  verification { name, father_name, place, date },
  creation { sw_provider_id, city },
}
```

Next year's return is seeded by copying last year's input (opening balances,
fixed blocks) and re-deriving the current year's data.

---

## 6. ITR form selection — `engine/itr/form_selector.py`

| Condition | Form |
|---|---|
| Resident individual/HUF, total income ≤ ₹50L, salary + ≤1 house property + other income, 112A LTCG ≤ ₹1.25L, **no** foreign assets/income, no carry-forward beyond 112A | **ITR-1** |
| Otherwise (capital gains beyond ITR-1 limits, foreign assets/income, total income > ₹50L, >1 house property, unlisted shares, carry-forward) | **ITR-2** |

For this user (US stocks, multiple gains) the expected form is **ITR-2**.
Selection returns the form + the reason(s), surfaced in the UI. Phase C builds
ITR-2; ITR-1 is phase F.

---

## 7. Tax computation — `engine/itr/tax_compute.py`

Wraps/extents `engine/income_tax.py`. Inputs: `ReturnInput` + derived income
buckets. Output: `ItrTaxComputation`.

New regime (s.115BAC(1A)), per FY config:

1. Slab tax on **normal** income (salary + interest + slab-rate gains).
2. Special rates: STCG 111A @ 20%, LTCG 112A @ 12.5% after ₹1.25L exemption.
3. **Resident basic-exemption shortfall** may be set against special-rate gains
   (first proviso to 111A/112A).
4. **87A rebate**: up to ₹60,000 (FY 2025-26) / ₹12,500 (FY 2024-25) when total
   income ≤ threshold; **does not reach 112A** by statute (and the utility
   declines it against 111A too) — normal-rate tax only. Marginal relief near
   the threshold.
5. **Surcharge** with **15% cap** for 111A/112/112A income; cess 4%.
6. **234A/B/C and 234F**: left 0 — the offline utility recomputes them from
   Table F quarters and challan dates. We **must not** hand-set computed fields.

Both regimes compared side by side (old regime = phase F).

Config lives in the existing `income_tax:` YAML block; FY 2024-25 currently
carries FY-2025-26-style values and must be corrected (see risks).

---

## 8. ITR JSON building

### 8.1 Architecture — `engine/itr/builders/`

```
ItrJsonBuilder (ABC, registry by AY+form)
├── Itr2BuilderAY2026   # AY 2026-27 (FY 2025-26)
├── Itr2BuilderAY2025   # AY 2025-26 (FY 2024-25)
└── (Itr1Builder… phase F)

build(draft: ReturnDraft) -> dict      # {"ITR": {"ITR2": {...}}}
```

Builders are **pure** (draft in → dict out). Schedule serializers live in
`builders/common.py`. Every builder is validated in tests against the bundled
official schema with `jsonschema`.

### 8.2 The Software Provider ID constraint (important)

**The portal's direct JSON upload only accepts files stamped with a registered
Software Provider ID.** A JSON we build is rejected with *"Invalid Software
Provider ID"* before the figures are read (two independent sources confirm this,
including the ITD's own contract notes). Therefore the deliverable is:

> A JSON **imported into the official Common Offline Utility** (File Return →
> *Import draft ITR … / import JSON generated from Excel/HTML utility* → attach
> → validate → submit). The utility has a registered ID and recomputes tax.

This must be stated plainly in the UI/CLI output and docs. We do **not** promise
a one-click portal upload.

### 8.3 Schedule mapping (ITR-2, AY 2026-27)

| Return concept | ITR-2 node(s) |
|---|---|
| Identity, address, PAN, DOB | `PartA_GEN1.PersonalInfo` |
| Filing status / regime | `PartA_GEN1.FilingStatus` |
| Salary | `ScheduleS` |
| Capital gains | `ScheduleCGFor23` (`ShortTermCapGainFor23`, `LongTermCapGain23`, `CurrYrLosses`, `AccruOrRecOfCG`/Table F) |
| Scrip-wise LTCG 112A | `Schedule112A` |
| Other sources (interest, dividend) | `ScheduleOS` |
| Current-year loss set-off | `ScheduleCYLA` |
| Brought-forward loss set-off | `ScheduleBFLA` |
| Carry-forward loss register | `ScheduleCFL` |
| Special-rate income + tax | `ScheduleSI` |
| Total income | `PartB-TI` |
| Tax computation + paid + refund | `PartB_TTI` (+ `ScheduleIT`, refund bank) |
| Foreign source income / tax credit | `ScheduleFSI` (+ Form 67 metadata) |
| Foreign assets | `ScheduleFA` |
| Form/software metadata | `CreationInfo`, `Form_ITR2` |
| Declaration | `Verification` |

### 8.4 Empirical traps to respect (from the community JSON contract)

1. **`schema-valid ≠ correctly imported`** — a schedule with only its total
   imports **blank**. Every populated schedule needs its itemised members.
2. **No camelCase** — the prefill uses camelCase; the filing schema is
   PascalCase with `additionalProperties: false`. A camelCase block is dropped
   **silently**. Never copy blocks from the portal prefill.
3. **Part B-TI/CYLA/BFLA carry capital gains GROSS**; the §112A exemption is
   applied inside `ScheduleSI`.
4. **Table F (quarter-wise accrual) must tie to BFLA**, not the gross gain.
   Derive quarters from BFLA; residual to Q1. Mismatch = Category-A upload block.
5. **Multi-column concepts need every column** (e.g. CFL columns 5a/5b/5c).
6. **Sibling top-level schedules** (`Schedule80C`, `Schedule112A`, `ScheduleIT`,
   `ScheduleSI`, …) — a non-zero VI-A line implies an itemised sibling.
7. **Read enums/codes from the schema**, never assume (country codes are ITD's
   own list, not ISO).
8. **Don't set computed fields**: `CreationInfo`, 234A/B/C, `AdjTotBFLossInBFLA`,
   `CurrentAYloss`.
9. Build a **skeleton of all required members** (0s) then overlay values.

### 8.5 Validation — `engine/itr/schema_validation.py`

- `jsonschema` (`Draft4Validator`) against the bundled schema; add `jsonschema`
  to dependencies.
- A second, **semantic** pass ("skeleton audit"): for each populated schedule,
  assert itemised members exist when totals are non-zero; assert Table F ties to
  BFLA; assert 112A rows sum to the CG figure; assert no camelCase keys; assert
  no PAN/Aadhaar leaks if we ever log.
- Validation failure = the build refuses to write output, with a readable
  localized error list.

### 8.6 Verified against the AY 2026-27 schema V1.2 (source-checked)

Root and required nodes (all nodes are `additionalProperties: false`):

```
ITR (req: ITR2) → ITR2 (req: CreationInfo, Form_ITR2, PartA_GEN1,
  ScheduleCYLA, ScheduleBFLA, PartB-TI, PartB_TTI, Verification)
```

- `CreationInfo` req: `SWVersionNo`(minLen 1, default `"1.0"`), `SWCreatedBy`,
  `JSONCreatedBy`, `JSONCreationDate`(**must be ≥ 2026-04-01**), `IntermediaryCity`
  (minLen 1, default `"Delhi"`), `Digest`. `SWCreatedBy`/`JSONCreatedBy`
  **pattern `SW\d{8}`**; `Digest` is `-` or 44 chars. We have no registered
  provider, so the builder emits a configurable **placeholder** matching the
  pattern (`SW00000000`) and the offline utility overwrites `CreationInfo` — the
  JSON is never direct-uploaded (see §8.2).
- `Form_ITR2`: `FormName` pattern **`"ITR-2"`**, `AssessmentYear` pattern
  **`"2026"`**, `SchemaVer`/`FormVer` pattern **`"Ver1.0"`**. **Trap:** the
  schema *file* is V1.2 but these JSON fields stay literally `"Ver1.0"` — never
  write `"Ver1.2"`.
- `Verification`: `Declaration` requires `AssesseeVerName`, `FatherName`,
  `AssesseeVerPAN` (PAN regex `[A-Z]{3}P[A-Z][0-9]{4}[A-Z]`); `Capacity` enum
  `S/R/K/A`; `Date`/`Place` optional but needed by the utility.
- `PartA_GEN1.PersonalInfo` req: `AssesseeName`(`FirstName`,`SurNameOrOrgName`),
  `PAN`, `Address`, `SecondaryAdd`(Y/N), `DOB`, `Status`(I/H).
- `PartA_GEN1.FilingStatus` req: `ReturnFileSec`(enum 11,12,…,20),
  `OptOutNewTaxRegime`, `SeventhProvisio139`, `ResidentialStatus`,
  `FiiFpiFlag`(Y/N), `HeldUnlistedEqShrPrYrFlg`(Y/N), `ItrFilingDueDate`.
- **`ResidentialStatus` enum is `RES / NRI / NOR`** (not `NR`/`RNOR`) —
  `ConditionsResStatus` is a separate optional string enum `1..9`.
- `Address.StateCode` enum: `01..37`, `99`. `Address.CountryCode` is the ITD's
  own 250-value list (**not ISO**); India = `91`, US must be looked up from the
  schema (`CountryCodeExcludingIndia` variant exists too). Every enum/code is
  read from the schema at build time.
- CG split: `PartB-TI.CapGain` = `{ShortTerm, LongTerm, ShortTermLongTermTotal,
  CapGains30Per115BBH, TotalCapGains}`. `ScheduleCGFor23` itemises under
  `ShortTermCapGainFor23` (`EquityMFonSTT[]` for 111A, `SaleOnOtherAssets` for
  slab, plus required NRI/DTA sections) and `LongTermCapGain23`
  (`SaleOfEquityShareUs112A` ties to `Schedule112A`, `SaleofAssetNADtls`, …).
- `Schedule112A.Schedule112ADtls[]` rows + agreeing totals; grandfathering field
  `FairMktValueCapAst112A`.
- `ScheduleFA` arrays: `DtlsForeignEquityDebtInterest`, `DtlsForeignCustodialAcc`,
  `DetailsFinancialInterest`, `DetailsOfOthSourcesIncOutsideIndia`, …;
  `PartB_TTI.AssetOutIndiaFlag`(YES/NO) drives it.
- `ScheduleCFL` has per-prior-AY blocks + `TotalLossCFSummary`,
  `TotalOfBFLossesEarlierYrs` (with `AdjTotBFLossInBFLA`, `CurrentAYloss`).
- `ScheduleSI.SplCodeRateTax[]`; `ScheduleOS.IncOthThanOwnRaceHorse` object;
  `Verification.Capacity`(S/R/K/A) + `Declaration`.

**CBDT validation-rule tie-outs to satisfy (rules v1.0):**

- 112A: col6 = col4×col5; col7 = higher(col8, col9); col9 = lower(col6,col11)
  when acquired ≤31-Jan-2018; col11 = col4×col10; col13 = col7+col12;
  col14 = col6−col13; totals = sum of rows. Cols 4,5,10,11 must be 0 when
  "acquired after 31-Jan-2018".
- CG B3a (LTCG u/s 112A) = **total of 112A col 14**.
- Schedule CG A1/B1 grandfathering (non-112A): if FMV ≤ 1.10×cost then deemed
  cost = actual cost, else deemed cost = FMV (rule 175/176).
- CG Table F quarters must tie to BFLA (3iv/3v/3vi/3viii) **and** to
  `ScheduleSI` Sl. No. 7 — not to the gross gain.
- CFL↔BFLA: BFLA 2(x)=CFL 6(x); BFLA 2(ii)=CFL 3c(x).
- `ScheduleFA` required iff `PartB_TTI.AssetOutIndiaFlag = YES` (rule 746).
- `ScheduleFSI`/`ScheduleTR` not applicable to non-residents (rules 443/453);
  FSI relief = lower of foreign tax paid vs tax payable.

(The rule numbers above are from the CBDT doc's own numbering and are recorded so
tests can cite them.)

---

## 9. Persistence and reuse across years

New table `itr_returns` (one row per member+AY):

```
id, member_id FK, fy_label, ay_label,
form_type,                # ITR1 | ITR2
status,                   # draft | generated | filed
input_json,              # ReturnInput snapshot (Pydantic-serialised)
draft_json,              # ReturnDraft (income + computation) — regenerable
output_json,             # the generated ITR JSON (nullable until generated)
schema_version,          # e.g. "AY2026-27/ITR-2 V1.2"
generated_at, created_at, updated_at
UNIQUE(member_id, ay_label)
```

- **Reuse**: `seed_from_previous_ay(member_id, ay)` copies fixed blocks +
  opening foreign-asset balances + prior carry-forwards.
- `member_tax_profiles` stays as the slab-income override used by the existing
  `TaxService`; ITR computation reads it as a fallback when no salary input.
- Carry-forwards remain in `tax_loss_carryforwards`; the return *renders* CFL
  from them and *writes back* the current year's unabsorbed loss at generate
  time (idempotent per AY).

---

## 10. Architecture & conventions

Follows the repo's layering (`CLAUDE.md`):

```
engine/itr/…                 pure: ay, tax_compute, form_selector, schedule_112a,
                             schedule_fa, builders/, schema_validation
engine/form16_parser.py      pure PDF/text → Form16Summary

services/itr_service.py      assemble ReturnDraft (UoW + TaxService + inputs)
services/itr_json_service.py draft → JSON via builder registry → validate → persist
services/tax_income_service.py  CRUD for ReturnInput (per member+AY)

models/itr_return.py         + repositories/itr_return_repo.py (+ UoW wiring)
api/itr.py                   HTTP only; endpoints below
schemas/requests/itr.py, schemas/responses/itr.py
config/itr_schemas/AY…/      bundled official schemas
cli.py                       `fintrack itr …` (thin HTTP client)
frontend/app/itr/page.tsx    types + lib/api.ts
```

DI: all concrete wiring in `api/dependencies.py`. No `Session` in services. UoW
for all DB writes. Services take abstract deps (protocols).

### API surface (draft)

```
GET  /api/itr/fiscal-years                       # FYs with tax config
GET  /api/itr/returns?member_id=&fy=             # list returns
POST /api/itr/returns                            # create/seed a return for member+AY
GET  /api/itr/returns/{id}                        # input + draft + status
PUT  /api/itr/returns/{id}/input                  # upsert ReturnInput (manual fields)
POST /api/itr/returns/{id}/form16                 # upload Form 16 PDF → parse preview
POST /api/itr/returns/{id}/assemble               # build draft (income + computation)
POST /api/itr/returns/{id}/generate               # build + validate JSON; store output
GET  /api/itr/returns/{id}/json                   # download the generated JSON
GET  /api/itr/returns/{id}/validation             # schema + semantic report
```

### CLI (thin HTTP client)

```
fintrack itr prepare --pan <PAN> --fy 2025-26
fintrack itr form16 <file> --pan <PAN> --fy 2025-26
fintrack itr generate --pan <PAN> --fy 2025-26 --out itr.json
fintrack itr list --pan <PAN>
```

---

## 11. Testing strategy (TDD)

Every unit ships test-first. Repo targets: engine ≥ 90%, importers ≥ 85%.

| Layer | Tests |
|---|---|
| `ay.py` | FY↔AY mapping, invalid labels |
| `form16_parser` | label extraction from a text fixture; missing-field warnings; a synthetic PDF built with `fpdf2` |
| `tax_compute` | hand-derived rupee cases: slabs, 111A/112A rates, ₹1.25L exemption, 87A rebate (incl. does-not-cover-112A), basic-exemption shortfall, surcharge cap, cess, marginal relief |
| `form_selector` | ITR-1 vs ITR-2 decision table |
| `schedule_112a` | grandfathering (FMV 31-Jan-2018), exemption, scrip rows sum to CG |
| `schedule_fa` | calendar-year window; open/closed detection; overrides |
| builders | golden `ReturnInput` → JSON; **validate against bundled official schema**; assert schedule values; camelCase/negative-quarter/Table-F-mismatch rejected |
| `schema_validation` | good file passes; known-bad file fails with path |
| `itr_service` | assemble from a seeded DB (members/assets/txns/FD) + input; carry-forward write-back idempotent |
| API (integration) | endpoints, per-PAN isolation, 422s |
| Regression | existing `test_tax_api.py`, `test_tax_*` stay green |

**Golden fixture**: a synthetic Form 16 (fpdf2-generated, no real PAN) +
a synthetic multi-asset portfolio, committed under `tests/fixtures/`. Real
Form 16s are never committed (PAN/privacy).

Schema caveat: builders are validated against the **bundled** schema; if the
schema is absent the build **refuses** (never emit unvalidated output).

---

## 12. Phasing (tracer bullets)

| Phase | Deliverable | Depends |
|---|---|---|
| **A. Foundation** | `itr_returns` table + repo + UoW; `ReturnInput` schemas; AY helper; per-PAN create/seed; API + CLI `prepare`/`list`; frontend stub | — |
| **B. Form 16** | `form16_parser` + upload endpoint + preview + persistence into input; text fixtures | A |
| **C. Tax engine** | `tax_compute` (new regime, special rates, 87A, surcharge, cess), `schedule_112a`; `assemble` endpoint returns draft | A |
| **D. ITR-2 JSON** | bundle AY 2026-27 schema; `Itr2BuilderAY2026`; `schema_validation`; `generate` + download; semantic audit | C |
| **E. Loss carry-forward & multi-year** | CFL schedule, write-back, `seed_from_previous_ay`; AY 2025-26 builder | D |
| **F. Foreign** | Schedule FA (calendar year) + FSI/Form 67 + Rule 115 rates; STOCK_US dividends | D |
| **G. Old regime + ITR-1 + polish** | old vs new comparison; ITR-1 builder; frontend page; docs | C–F |

Each phase is independently shippable and leaves `main` green.

---

## 13. Risks & open questions

1. **Form 16 layout variance** — layouts differ by employer/utility. Mitigation:
   label-driven parser + warnings, never silent zeros; user can correct in the
   input document. Consider an OCR/manual fallback for scanned PDFs.
2. **Rule 115 vs app FX rates** — US gains computed with the app's monthly rate
   may differ from Rule 115 (SBI TTBR). Phase F fixes conversion; until then,
   document the gap and allow an override.
3. **Schedule FA completeness** — holdings must be reported even if history
   predates the app. Manual opening balances are mandatory; the builder warns
   when an asset's first transaction is inside the current year but it was
   disposed before/after.
4. **Schema drift** — ITD releases schema revisions mid-season. Pin the bundled
   schema version in the return; refuse on mismatch; surface the version.
5. **Tax-year boundary** — FY 2026-27 onward falls under the **Income-tax Act
   2025** and new Rules; this design targets FY ≤ 2025-26 (Act 1961). AY
   2027-28+ needs a fresh review.
6. **87A rebate config was wrong for the new regime** — `2024-25.yaml` carried the
   *old-regime* rebate (₹5L/₹12,500) and `2025-26.yaml`/`2026-27.yaml` carried
   ₹7L/₹15,000. All three are **corrected** (FY24-25 → ₹7L/₹25,000; FY25-26 and
   FY26-27 → ₹12L/₹60,000, per Finance Act 2025) with the rebate excluded from
   special-rate (111A/112/112A) income and marginal relief above the threshold.
   Slabs themselves were already correct. Pinned by tests in
   `tests/unit/test_itr_tax_compute.py`.
7. **Migrations cannot run on SQLite (pre-existing).** Several older migrations
   (e.g. `a0fa4c347bea`, `33b0d2ef25ee`) call `op.alter_column(... type_=...)`
   without `batch_alter_table`, which SQLite rejects — `alembic upgrade head`
   fails on a SQLite DB. The test suite is unaffected (it builds schema via
   `Base.metadata.create_all`), and the new `itr_returns` migration is a plain
   `CREATE TABLE` verified in isolation. **Decision: left as a known issue**;
   fix with batch mode in a separate change (or standardise on Postgres).
7. **Liability** — output is a **draft**, not advice. UI/CLI/docs must say the
   user verifies and signs; the offline utility's recomputation is authoritative.
8. **Security/privacy** — PAN/Aadhaar/account numbers are sensitive; keep the
   JSON out of git, never log full PAN, and restrict returned PAN to masked form
   in the UI (existing pattern: `maskPan`).

### Decisions (confirmed 2026-10-16)

- **First build = Phases A–D**: Form 16 → assembled draft → validated ITR-2
  JSON. Phases E–G follow in later passes.
- **Primary AY = 2026-27** (FY 2025-26, current season). AY 2025-26 builder is
  Phase E (backfill/reference).
- **Surface = API + CLI** (`fintrack itr prepare/form16/generate`). The
  frontend `/itr` page is Phase G.
- **Regime = new (s.115BAC(1A)) only** for now. Old regime (Chapter VI-A,
  old slabs/87A, regime comparison) is Phase G.

---

## 14. Out of scope (v1)

- ITR-3+ / business income / F&O / VDA beyond recognition.
- NRI/RNOR, HUF, audit, transfer pricing.
- Direct portal upload or e-verification.
- Advance-tax challan payment (we can *report* challans, not pay).
- Schedule AL (assets & liabilities) — later, threshold ₹1 crore.
- Persist/parse AIS, TIS, Form 26AS (reconciliation) — later enhancement.
