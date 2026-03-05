# 🐛 Bugs & Issues

---

## 📖 Legend

### Status
| Icon | Status |
|------|--------|
| 🔍 | Reported — identified but not yet investigated |
| 🔧 | In Progress — actively being worked on |
| ✅ | Fixed — resolved and verified |
| 🚫 | Won't Fix — acknowledged but out of scope |

### Priority
| Icon | Priority |
|------|----------|
| 🔴 | High — critical, breaks core functionality |
| 🟡 | Medium — impacts usability but has a workaround |
| 🟢 | Low — minor issue, low user impact |

### Commit
| Field | Purpose |
|-------|---------|
| `Commit` | The commit hash recorded when the bug was fixed. Use this to trace back exactly what changed — if the bug reappears in the future, run `git show <commit>` to inspect the original fix. |

> 🔍 **Traceability tip:** Always fill in the commit hash when marking a bug as ✅. Run `git log --oneline` to find it. This creates an audit trail for regressions.

---

## 🐞 Bug List

| # | Status | Priority | Description | Commit |
|---|:------:|:--------:|-------------|:------:|
| 1 | ✅ | 🔴 | BOQ import replace logic — when importing a smaller file, existing rows are not cleared beforehand, causing leftover lines to remain in the editor | 43087af |

---

> 💡 **To add a new bug**, copy any row from the table above and append it at the end. Update the `#` index, set the status to 🔍, choose the appropriate priority icon, write the description, and leave the commit as `—` until fixed.
>
> 📌 **When marking a bug as fixed (✅)**, replace `—` in the Commit column with the short commit hash (e.g., `a3f92c1`).