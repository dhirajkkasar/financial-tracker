# Plan: Refactor Generic Endpoint Validation to ImportOrchestrator

**Status:** Planning Complete  
**Date:** 28 March 2026  
**Objective:** Move importer-specific validation logic from the generic `/preview-file` endpoint into `BaseImporter.validate()` method, with post-parse validation and structured error responses.

---

## Problem Statement

The `/preview-file` endpoint in `backend/app/api/imports.py` contains asset-type-specific validation logic for Fidelity importers (exchange_rates JSON parsing, month completeness checks). This couples a generic endpoint to specific importers, violates single-responsibility principle, and becomes unmaintainable as more importers gain special requirements.

## Solution Overview

**Extend the existing `BaseImporter.validate()` method** to:
- Accept `ImportResult` (post-parse validation)
- Return structured `ValidationResult` with `is_valid`, `errors`, and `required_inputs`
- Allow importers to override for custom validation (Fidelity importers extract transaction months and validate exchange_rates)
- Default to no-op for importers without special needs

**Flow:**
1. Endpoint passes raw `user_inputs` string to orchestrator (no JSON parsing)
2. Orchestrator parses file → creates `ImportResult`
3. Orchestrator calls `importer.validate(result, **kwargs)` with raw user_inputs, user_inputs is used as exchange_rates in fidelity importers
4. Fidelity importers validate and raise `ValidationError` if incomplete
5. Endpoint catches orchestrator exceptions and returns 422 with structured error details

---

## Architecture Changes

### 1. ValidationResult Dataclass
**File:** `backend/app/importers/__init__.py`

```python
@dataclass
class ValidationResult:
    is_valid: bool
    errors: list[str]  # User-facing error messages
    required_inputs: dict[str, Any]  # Hints for user, e.g., {"required_months": ["2025-03"]}
```

### 2. BaseImporter.validate() Updated Signature
**File:** `backend/app/importers/__init__.py`

```python
def validate(self, result: ImportResult, **kwargs) -> ValidationResult:
    """Post-parse validation hook. Default: pass. Override for custom checks.
    
    Args:
        result: ImportResult from parse()
        **kwargs: Importer-specific inputs (e.g., exchange_rates string)
    
    Returns:
        ValidationResult with is_valid, errors, required_inputs
    """
    return ValidationResult(is_valid=True, errors=[], required_inputs={})
```

### 3. Fidelity Importers (FidelityRSUImporter, FidelityPDFImporter)
**Files:** `backend/app/importers/fidelity_rsu.py`, `backend/app/importers/fidelity_pdf.py`

Override `validate()` to:
- Extract required months from parsed transactions
- Parse `user_inputs` (exchange_rates) JSON string (move from endpoint)
- Check completeness: compare required months vs. provided exchange_rates keys
- Return `ValidationResult` with errors + required_inputs on failure
- Raise `ValidationError` (caught by endpoint) if validation fails

### 4. ImportOrchestrator.preview()
**File:** `backend/app/services/imports/orchestrator.py`

After `importer.parse(file_bytes)`:
- Call `importer.validate(result, **kwargs)` 
- If `is_valid=False`, raise `ValidationError` with error details
- Otherwise continue to deduplication

### 5. Endpoint /preview-file
**File:** `backend/app/api/imports.py`

Replace fidelity-specific blocks:
- Remove `_parse_exchange_rates()` function (move to Fidelity importers)
- Remove conditional `if source in {"fidelity_rsu", "fidelity_sale"}` logic
- Pass raw `user_inputs` string in `importer_kwargs` if provided
- Let orchestrator raise `ValidationError` (already caught for HTTPException mapping)

---

## Implementation Steps

### Phase 1: Define ValidationResult
- [ ] Add `ValidationResult` dataclass to `backend/app/importers/__init__.py`
- [ ] Export for use by importers and orchestrator

### Phase 2: Update BaseImporter
- [ ] Modify `BaseImporter.validate()` signature to return `ValidationResult`
- [ ] Set default implementation to return `ValidationResult(is_valid=True, errors=[], required_inputs={})`

### Phase 3: Implement Fidelity Validation
- [ ] FidelityRSUImporter: override `validate()` with exchange_rates logic
- [ ] FidelityPDFImporter: override `validate()` with exchange_rates logic
- [ ] Move from endpoint:
  - JSON parsing: `_json.loads(exchange_rates)`
  - JSON validation: check dict with numeric values
  - Month extraction: use existing `extract_required_month_years()` static method
  - Completeness check: missing months → `ValidationResult(is_valid=False, errors=[...], required_inputs={...})`

### Phase 4: Update Orchestrator
- [ ] ImportOrchestrator.preview(): call `importer.validate(result, **kwargs)` after parse
- [ ] If `is_valid=False`, raise `ValidationError` with error message

### Phase 5: Clean Endpoint
- [ ] Remove `_parse_exchange_rates()` function
- [ ] Remove fidelity-specific conditional block
- [ ] Simplify: `importer_kwargs["user_inputs"] = user_inputs` (pass as-is string if provided) it is exchange_rates for fidelity
- [ ] Keep existing exception handling for orchestrator errors

### Phase 6: Testing
- [ ] Unit test: FidelityRSUImporter.validate() with valid/invalid exchange_rates
- [ ] Unit test: FidelityPDFImporter.validate() with missing months
- [ ] Integration test: `/preview-file` with fidelity + incomplete exchange_rates → 422
- [ ] Integration test: Non-fidelity importers still work (validate() returns is_valid=True)

---

## Error Response Format

When `ValidationError` is raised from orchestrator due to failed validation:

**HTTP 422:**
```json
{
  "message": "Validation failed",
  "code": "VALIDATION_ERROR",
  "details": {
    "errors": ["Missing exchange_rates for months: 2025-03, 2025-04"],
    "required_inputs": {
      "required_months": ["2025-03", "2025-04"],
      "provided_months": ["2025-02"]
    }
  }
}
```

---

## Decisions Made

1. **Option A (Exception-based):** Orchestrator raises `ValidationError`, endpoint catches it (matches existing error handling pattern)
2. **Post-parse validation:** Required to know which transaction months need exchange rates
3. **Delegate JSON parsing:** Move from endpoint to importer; endpoint passes raw string
4. **Fallback for non-validating importers:** Default `validate()` returns `is_valid=True`

---

## Backward Compatibility

- **Existing importers:** Use BaseImporter default `validate()` → no changes needed
- **Future importers:** Can override `validate()` for custom validation
- **Endpoint behavior:** No change from user perspective; same error responses

---

## Benefits

✅ Generic endpoint decoupled from importer specifics  
✅ Validation logic colocated with importer implementations  
✅ Extensible for future importers without endpoint changes  
✅ Reuses existing BaseImporter pattern  
✅ Post-parse validation knows exact transaction months  
✅ Structured error responses with hints for users  

---

## Dependencies

None. All required patterns exist:
- `BaseImporter.validate()` already defined
- `ValidationError` already exists
- Fidelity importers have `extract_required_month_years()` static method
- Orchestrator already instantiates importer and calls parse()

---

## Future Extensions

1. **CAS Importer:** Validate fund scheme existence in database
2. **PPF/EPF Importers:** Validate account holder name matches
3. **Generic validation framework:** Add pre-parse validators for file format checks
