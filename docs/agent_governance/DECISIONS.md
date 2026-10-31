# Decision register

ACTIVE entries block conflicting requests — report, never silently implement.

| ID | Decision | Status |
| --- | --- | --- |
| D01 | No large raw data/archives committed | **ACTIVE** |
| D02 | Generated outputs are artifacts, not source — explicit staging | **ACTIVE** |
| D03 | No secrets/credentials committed | **ACTIVE** |
| D04 | Destructive ops on input data require authorization | **ACTIVE** |
| D05 | Build/test/deploy statuses reported separately; unverified = NOT_VERIFIED | **ACTIVE** |
