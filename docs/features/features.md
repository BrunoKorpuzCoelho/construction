# 🏗️ Features & Implementations

---

## 📖 Legend

### Status
| Icon | Status |
|------|--------|
| ⏳ | Pending — not yet implemented |
| ✅ | Done — fully implemented |
| 🚫 | Obsolete — no longer relevant |

### Priority
| Icon | Priority |
|------|----------|
| 🔴 | High — critical, must be addressed immediately |
| 🟡 | Medium — important, should be addressed soon |
| 🟢 | Low — minor, can be addressed when convenient |

### Commit
| Field | Purpose |
|-------|---------|
| `Commit` | The commit hash recorded when the feature was implemented or the bug was fixed. Use this to trace back exactly what changed and when — if a feature breaks in the future, check this commit to understand what the original implementation looked like and what may have been overwritten. |

> 🔍 **Traceability tip:** When a feature is marked ✅ or 🚫, always fill in the commit hash. Run `git log --oneline` to find it. This creates an audit trail — if something regresses, you can run `git show <commit>` to inspect the exact changes made.

---

## 📋 Feature List

| # | Status | Priority | Description | Commit |
|---|:------:|:--------:|-------------|:------:|
| 1 | ⏳ | 🟡 | View archived products (soft delete) in BOQ Editor view, and the option to archive in the lines that changes the is_active field to false | — |
| 2 | ✅ | 🟡 | Re-add BOQ group selector in the Access Rights tab | — |
| 3 | ⏳ | 🟢 | Remove preview step from the BOQ import wizard | — |
| 4 | ✅ | 🔴 | Fix F5 refresh issue — application fails to reload correctly | 9fb87ec |
| 5 | ⏳ | 🟡 | Trigger automatic refresh after BOQ import to display new records | — |
| 6 | ⏳ | 🟡 | Validate imported template fields during preview and raise explicit `UserError` on failure | — |
| 7 | ⏳ | 🟢 | Show progress bar during import processing | — |
| 8 | ⏳ | 🟢 | Display elapsed time per operation — preview load time and total import duration | — |

---

> 💡 **To add a new feature**, copy any row from the table above and append it at the end. Update the `#` index, set the status to ⏳, choose the appropriate priority icon, write the description, and leave the commit as `—` until resolved.
>
> 📌 **When marking a feature as done (✅)**, replace `—` in the Commit column with the short commit hash (e.g., `a3f92c1`). This links the feature to its implementation for future traceability.
