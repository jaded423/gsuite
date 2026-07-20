# Gmail Filters — joshua@elevatedtrading.com

Snapshot: 2026-04-21 · 51 filters · 30 user labels

**Action codes** used below:
- `arch` = remove INBOX
- `read` = remove UNREAD (i.e. auto-mark-read)
- `star` = add STARRED
- `unspam` = remove SPAM
- `+Label` = add the named label
- *(blank)* = no change to that axis

Short filter IDs shown below are the last 8 chars of the Gmail filter ID.

---

## Grouped by destination

### Sus (Label_21) — authorize.net alerts
| ID | Match | Action |
|---|---|---|
| `...bzsnig` | `from:authorize.net subject:"Merchant Email Receipt"` | arch read +Sus |
| `...e9OkOA` | `from:authorize.net subject:"Suspicious Transaction"` | arch +Sus |

### Square
| ID | Match | Action | Label |
|---|---|---|---|
| `...niSZ2D` | `to:joshua@et "'square' via square" subject:"Payment Initiated" OR "An Invoice was paid"` | arch | Square/Mark as Paid |
| `...MUdTzw` | `from:square@et subject:"Payment Processed" OR "A new invoice was created" OR "updated" OR "canceled"` | arch read unspam | Square/Created or Changed |
| `...JJxiA` | `from:square@et subject:"An invoice was not delivered"` | arch read | Square (parent) |

### Billing (Label_7740319528379082929)
| ID | Match | Action |
|---|---|---|
| `...JvlYQ` | `subject:"Amazon Invoice Available" OR "Thanks for your Pay by Invoice payment"` | arch |
| `...B036g` | `subject:"Unishippers Invoice"` | arch |
| `...xfrrw` | `from:info@et (Tropics Collective)` | arch star |
| `...Eq6Yg` | `to:info@et AND from:(managebuilding.com OR att-mail.com OR x-sense.com)` | arch |
| `...MUdTzw` | `from:{cooljarz.com, earthwisepackaging.com} subject:"Thank you"` | arch |
| `...is5g-A` | `subject:"[Billing]"` with giant negation block | arch unspam |
| `...qqoGQ` | `to:billing@et` with giant negation block | arch |

### Customer Service (Label_7442434543156889277)
| ID | Match | Action |
|---|---|---|
| `...-wq6Yg` | `to:info@et` minus `(managebuilding OR att-mail OR sasdesk OR x-sense)` | arch |
| `...ohyzZ3` | `from:info@et` minus `(PandaDoc OR Amazon Business OR ET Site OR Tropics Collective)` | arch |
| `...VKXEKY` | `from:{cooljarz, earthwise}` NOT `subject:"Thank you"` | arch |
| `...AblZ6g` | `from:readyrefresh.com OR subject:"Your Package Has Shipped"` OR 9 other subject patterns | arch |
| `...9p3P-Q` | `from:tp-link.com OR samsung@innovations.samsungusa.com` | arch read |
| `...2bHHpw` | `from:info@et (Amazon Business)` | arch read |

### Customer Service/sub-labels
| ID | Match | Action | Label |
|---|---|---|---|
| `...A70_g` | `from:shipment-tracking@amazon.com` | arch unspam | Customer Service/Amazon Tracking |
| `...sPlQ` | `from:info@et (ET Site)` | arch read unspam | Customer Service/ET Site |
| `...oKq6Yg` | `from:notifications@et subject:"Shipment:"` | arch | Customer Service/Shipping |
| `...vtLAzw` | `from:wordpress@et` | arch read unspam | Customer Service/WordPress |

### VMS / Payments
| ID | Match | Action | Label |
|---|---|---|---|
| `...mhBBkw` | `from:valmar subject:"Batch Processing Completed"` | arch unspam | VMS |
| `...IgxHpw` | `to:valmar@et` | arch | VMS |
| `...w5_gIw` | `from:valmar subject:"Settlement Processed"` | arch read | VMS/Settlement Processed |
| `...DmOqmZ` | `from:valmar subject:"Payment Received"` | arch read | VMS/PR |

### Mark-read-only (quiet receipts)
| ID | Match | Action |
|---|---|---|
| `...Sc-CWm` | `from:valmar AND (subject:"Batch Processing Completed" OR "Payment Received")` | read |
| `...MIRMLm` | `from:cardchampgateway OR gatewaynotify.com` | read |
| `...M4dmpa` | `subject:"Payment confirmation" OR "Thank You for Your Payment" OR variations` | read |
| `...mh8q0B` | `from:uline cash/credit addresses` | read |
| `...inpYgz` | `from:support@digitalocean.com subject:"Received $"` | read |
| `...N9vGTk` | `from:no-reply@amazon.com/ar-businessworkbench subject:"monthly spending summary" OR "account statement"` | read |

### Archive-unread-only (visible-but-not-inbox)
| ID | Match | Action |
|---|---|---|
| `...FyvKUD` | `from:drive-shares-dm-noreply@google.com` | arch +Shared Docs |
| `...pm5uwy` | `from:joshua@et to:joshua@et subject:"Elevated Trading"` | arch |
| `...i1L7ko` | `from:sales@et subject:"Updated Inventory"` | arch |

### PandaDoc (starred)
| ID | Match | Action |
|---|---|---|
| `...ci9qaw` | `from:info@et (PandaDoc)` | arch star +PandaDoc |

### SAS, Checkr, Accounting, Odoo, IT, Instagram, Twingate, Reddit
| ID | Match | Action |
|---|---|---|
| `...YHE_B3` | `from:sasdesk.com` | arch unspam +SAS |
| `...SAATja` | `from:info@et (sasha at checkr)` | arch read +Checkr |
| `...2u6Yg` | `from:julie@pbsinc.info OR "@Julie Bass"` | arch star +Accounting |
| `...2j-ni` | `to:joshua@et AND "view journal entry" OR "view quotation" OR "view transfer" OR Odoo internal comm text` | arch +Odoo Chatter |
| `...TAO-Ch` | `list:<it.elevatedtrading.com>` | arch +IT |
| `...6fnGhJ` | `from:instagram list:<info.elevatedtrading.com>` | arch read |
| `...vwzw` | `from:no-reply@twingate.com` | arch read |
| `...Xhpw` | `from:info@et (Reddit)` | arch read |

### Junk (Label_27)
| ID | Match | Action |
|---|---|---|
| `...4FV4w` | `from:Microsoftstore@microsoftstore.microsoft.com` | arch read +Junk |
| `...Qqg` | `from:no-reply@business.amazon.com` | arch read +Junk |
| `...pdqTNDB` | `from:engage.canva.com OR info.digitalocean.com OR em1.cloudflare.com OR mail.clickup.com` | arch read +Junk |
| `...L6jfg` | `from:mail.adobe.com` | arch read +Junk |

### ClickUp project-specific
| ID | Match | Action | Label |
|---|---|---|---|
| `...96A` | `from:notifications@tasks.clickup.com AND ("9011826444" OR "Elevated Trading")` | arch | ClickUp/Elevated |
| `...ZDXEw` | `from:notifications@tasks.clickup.com AND ("90131445581" OR "Charisma18")` | arch unspam | ClickUp/Charisma18 |

---

## Consolidation opportunities

### 1. Collapse 4 Junk filters into 1
Filters `...4FV4w`, `...Qqg`, `...pdqTNDB`, `...L6jfg` all do `arch read +Junk`. Merge to a single filter:
```
from:(Microsoftstore@microsoftstore.microsoft.com OR no-reply@business.amazon.com OR engage.canva.com OR info.digitalocean.com OR em1.cloudflare.com OR mail.clickup.com OR mail.adobe.com)
```
Also add `Microsoft365@engagement.microsoft.com` — it leaks through today and fits the same bucket.

**Savings: 4 → 1 filter.** Future marketing senders: one-line edit rather than new filter.

### 2. Collapse 4 mark-read-only receipt filters into 1
`...Sc-CWm`, `...MIRMLm`, `...M4dmpa`, `...mh8q0B`, `...inpYgz`, `...N9vGTk` all do just `read`. Could merge (keeping subjects/senders union):
```
Senders: valmar, cardchampgateway, gatewaynotify, uline cash/credit, support@digitalocean.com (w/ subject filter), no-reply@amazon.com / ar-businessworkbench (w/ subject filter)
Subjects: "Payment confirmation" OR "Thank You for Your Payment" OR "Your payment has been processed" OR "Your automatic payment has been scheduled"
```
Tricky because 2 of them are sender-with-subject-constraint (DO, Amazon). Safer to merge the pure-sender ones and leave DO/Amazon separate.

**Savings: 6 → ~3 filters.**

### 3. Filter `...Sc-CWm` (valmar batch/payment → read) is redundant
The two sibling filters `...mhBBkw` (Batch Processing Completed → VMS +read+arch) and `...DmOqmZ` (Payment Received → VMS/PR +read+arch) already mark-read. **Can delete** `...Sc-CWm` entirely.

### 4. Missing exclusion in `...ohyzZ3`
The `from:info@et` fallback filter excludes PandaDoc, Amazon Business, ET Site, Tropics Collective — but **not** `sasha at checkr`. If a checkr message comes via the info@ alias without the exact alias string match, it'll land in Customer Service instead of Checkr. Add `-(sasha at checkr)` to be safe.

### 5. Billing filters `...is5g-A` and `...qqoGQ` share 400+ char negation blocks
Two filters with identical negation bodies — hard to maintain, easy to drift. Consider:
- One merged filter: `(subject:"[Billing]" OR to:billing@et)` with the negation block once.
- Or a separate gmail contact group / label sieve upstream.

### 6. Multi-subject list in filter `...AblZ6g` (11 subject patterns)
This one has 11 hardcoded subject lines (ReadyRefresh, package shipped, rent payment reminder, etc.) that likely originated as "miscellaneous vendor automation." Consider:
- Splitting into themed filters (shipments, rent, SaaS onboarding).
- Or accepting its messy catch-all nature but renaming the filter in your mental model as "vendor-automation-grab-bag."

### 7. Pattern inconsistencies
- `excludeChats: true` — set on post-2025 filters, missing on older ones. No functional impact but worth standardizing.
- Some filters remove `SPAM`, others don't. Keep `unspam` only for senders that frequently get spam-filed (e.g. `wordpress@et`, `valmar`, `ET Site`). Remove from filters where it's noise.
- Star usage is selective (PandaDoc, Tropics, Accounting/Julie). Consistent — no change.

### 8. Action-column "shape" suggests filter families
Most filters fall into five shapes:
1. `arch read +Label` — auto-read + archive to named bucket (receipts, completed automation)
2. `arch +Label` — keep unread but route out of inbox (anything I want to scan on the label)
3. `read` only — leave visible in inbox, mark read
4. `arch +Label star` — promoted to action queue (PandaDoc, Tropics, Julie)
5. `arch read +Junk` — throw away

A sanity rule of thumb going forward: every new filter should fit one of those five shapes. If it doesn't, question whether the action set is intentional.

---

## Suggested next actions (not applied automatically)

1. Delete redundant filter `...Sc-CWm` (valmar mark-read duplicates).
2. Merge 4 Junk filters into 1 and add `Microsoft365@engagement.microsoft.com`.
3. Add `-(sasha at checkr)` to `from:info@et` fallback filter `...ohyzZ3`.
4. Merge the three pure-sender mark-read filters (cardchampgateway, uline, pure-subject payment confirmations).
5. Optionally merge Billing `[Billing]`/`to:billing@et` pair.
