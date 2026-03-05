# ⚡ Optimizations

---

## 📖 Legend

### Status
| Icon | Status |
|------|--------|
| ⏳ | Pending — identified but not yet implemented |
| 🔧 | In Progress — actively being worked on |
| ✅ | Done — implemented and verified |
| 🚫 | Discarded — investigated but not worth pursuing |

### Priority
| Icon | Priority |
|------|----------|
| 🔴 | High — significant performance impact |
| 🟡 | Medium — noticeable improvement, moderate effort |
| 🟢 | Low — minor gain, low urgency |

### Commit
| Field | Purpose |
|-------|---------|
| `Commit` | The commit hash recorded when the optimization was applied. Use this to trace back exactly what changed — if performance regresses, run `git show <commit>` to inspect the original change. |

> 🔍 **Traceability tip:** Always fill in the commit hash when marking an optimization as ✅. Run `git log --oneline` to find it. This creates an audit trail for performance regressions.

---

## 📋 Optimization List

| # | Status | Priority | Description | Commit |
|---|:------:|:--------:|-------------|:------:|
| 1 | ⏳ | 🔴 | BOQ import — replace row-by-row insertion with bulk processing for faster and more efficient import | — |

---

> 💡 **To add a new optimization**, copy any row from the table above and append it at the end. Update the `#` index, set the status to ⏳, choose the appropriate priority icon, write the description, and leave the commit as `—` until resolved.
>
> 📌 **When marking an optimization as done (✅)**, replace `—` in the Commit column with the short commit hash (e.g., `a3f92c1`). This links the optimization to its implementation for future traceability.