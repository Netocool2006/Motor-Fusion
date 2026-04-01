# SAP CRM WebUI - Internal JavaScript API Reference
**Extracted from:** wdp-sap.gbm.net:8105 (SAP CRM 7.0)
**Date:** 2026-03-27
**Source files:** events.js, scripts.js, crmuifServer.js, crmuifclient.js, event_dictionary.js

---

## Architecture Overview

SAP CRM WebUI uses a form-based submit model with optional AJAX delta handling:

```
User Action → onclick handler → htmlbSL() or htmlbEL()
  → htmlbSubmitLib() → htmlbSubmit()
    → htmlbSubmitForm()
      ├─ AJAX mode:  htmlbSubmitFormAjax() → AjaxRequest → deltaRenderingCallback()
      └─ Full mode:  form.submit() (full page reload)
```

### Key Global Variables
- `isAjaxEnabled` — whether AJAX delta handling is active
- `ajax_submit` — flag set by preAjaxRequest() before submit
- `submissionInProgress` — prevents double-submit
- `thLast_objectID` / `thLast_eventName` — last submitted event info
- `htmlbEDIC[]` — event dictionary array (maps index to event type string)
- `bindOnlyEvent` — if true, AJAX only sends event data (not full form)

---

## Core Functions

### 1. `htmlbSL(elem, eventType_idx, objectID_plus_eventName, eventDef, param1, param2)`
**Purpose:** Shorthand submit — most common entry point for button clicks, links, etc.
**Flow:** Resolves event type from dictionary → splits objectID:eventName → calls htmlbSubmitLib()

```javascript
// Example: simulate a button click
htmlbSL(document.body, 0, 'OBJECT_ID:eventName', null);
```

### 2. `htmlbEL(elem, eventType_idx, objectID_plus_eventName, eventDef, param1, param2)`
**Purpose:** Shorthand event — like htmlbSL but fires client-side event handler first.
**Flow:** Same as htmlbSL but routes through htmlbEventLib() → htmlbEvent() which checks for cancelSubmit.

### 3. `htmlbSubmitLib(library, elem, eventType, formID, objectID, eventName, paramCount, param1..9)`
**Purpose:** Sets the `onInputProcessing` field to the library name, then calls htmlbSubmit().
**Key:** `library` is almost always `'htmlb'`.

```javascript
// Direct call example
var formId = document.getElementById("htmlb_first_form_id").value;
htmlbSubmitLib('htmlb', document.body, 'htmlb:link:click:null', formId, objectID, eventName, 0);
```

### 4. `htmlbSubmit(elem, eventType, formID, objectID, eventName, paramCount, param1..9)`
**Purpose:** Core submit function. Validates form, populates hidden fields, then submits.
**Important fields it sets on the form:**
- `form.htmlbevt_ty` = eventType
- `form.htmlbevt_oid` = objectID
- `form.htmlbevt_id` = eventName
- `form.htmlbevt_cnt` = paramCount
- `form.htmlbevt_par1..9` = params

**Guard:** Checks `formID + "_complete"` has attribute `code="OK"` before proceeding.

### 5. `htmlbSubmitForm(form)`
**Purpose:** Actual form submission. Tries AJAX first, falls back to full submit.
**Flow:**
1. `processDataLossDialog()` — checks for unsaved changes
2. Guards against `submissionInProgress`
3. Tries `htmlbSubmitFormAjax(form)` — if returns true, AJAX was used
4. If AJAX fails/disabled, does `form.submit()` (full page reload)

### 6. `htmlbSubmitFormAjax(form)`
**Purpose:** AJAX submit via XHR. Only works if `isAjaxEnabled && ajax_submit`.
**Creates:** `new AjaxRequest(form.action, { method:'post', onComplete: deltaRenderingCallback, ... })`

### 7. `htmlbEvent(elem, eventClass, eventType, formID, objectID, eventName, paramCount, param1..9)`
**Purpose:** Fires client-side event handler before submitting.
**Checks:** `window[formID + "_" + objectID + "_" + eventClass]` — if exists, calls it with htmlbevent object. If `htmlbevent.cancelSubmit == true`, aborts.

---

## Navigation Functions

### 8. `thtmlbNavigateToLogicalLink(iv_link_id)`
**Purpose:** Navigate to a logical link (menu item) in SAP CRM.
**Calls:** `crmFrwNavigateToLogicalLink(iv_link_id, "KBD")`

### 9. `menu_navigate(pagecontext, link)`
**Purpose:** Trigger menu navigation via form submit.
```javascript
// Navigate to a menu item
menu_navigate('PageContext', 'LogicalLinkId');
```

---

## AJAX / Delta Handling

### 10. `preAjaxRequest(target)`
**Purpose:** Prepares for AJAX submit by setting the target element ID.
**Sets:** `sap-ajaxtarget` hidden field value, enables `ajax_submit` flag.

### 11. `AjaxRequest(targetUrl, reqOptions)`
**Purpose:** XHR wrapper. Creates XMLHttpRequest, sends POST.
**Options:** `{ method, asynchronous, parameters, bindingMode, onComplete, submittedFormId, sapAjaxtarget, postProcess }`

### 12. `deltaRenderingCallback(reqObj)`
**Purpose:** Processes AJAX response. Replaces target DOM elements with new HTML.
**Handles:**
- HTTP redirects via `sap-ajax_http_redirect` header
- Multiple targets via `sap-ajax-targets` header (auto mode)
- Script extraction and deferred execution
- CSS injection
- WorkAreaFrame1/WorkAreaFrame2 switching

### 13. `isDeltaHandlingAutoMode()` / `setDeltaHandlingMode(mode)`
**Purpose:** Check/set delta handling mode. AUTO = server decides targets.

### 14. `cancelAjaxRequest()` / `isAjaxActive()`
**Purpose:** Disable AJAX / check if AJAX is available.

---

## Event Dictionary

The `htmlbEDIC[]` array maps numeric indices to event type strings. Used by htmlbSL/htmlbEL:
```
eventType_idx → htmlbEDIC[eventType_idx] → e.g., "htmlb:link:click"
```

The full event type format is: `library:control:event:eventDef`
Example: `htmlb:link:click:null`, `htmlb:button:click:null`

---

## Practical Usage for Automation

### Instead of simulating clicks, you can call htmlbSL directly:

```javascript
// 1. Get the form ID (always available)
var formId = document.getElementById("htmlb_first_form_id").value;

// 2. Find the objectID from the element's onclick handler
// Example onclick: htmlbSL(this, 0, 'C27_W77_V79_Searchbtn:search', null)
// objectID = 'C27_W77_V79_Searchbtn', eventName = 'search'

// 3. Call directly (bypasses need to find/click the actual button)
htmlbSL(document.body, 0, 'OBJECT_ID:EVENT_NAME', null);
```

### For navigation:
```javascript
// Navigate to Opportunities
thtmlbNavigateToLogicalLink('OPPORTUNITIES_LINK_ID');

// Or via menu
menu_navigate('PageContext', 'LinkId');
```

### For AJAX-aware field changes:
```javascript
// Set field value and trigger server validation
var field = document.querySelector("[id$='inputfield_suffix']");
field.value = 'new_value';
// Trigger SAP's onchange handling
field.onchange && field.onchange();
// Then submit the form to process server-side
htmlbSL(field, 0, 'OBJECT_ID:eventName', null);
```

---

## Files in this directory

| File | Size | Contents |
|------|------|----------|
| `sap_internal_functions.js` | 26KB | 22 core functions (source code) |
| `API_REFERENCE.md` | this file | Analysis and usage guide |

## SAP JS Files Loaded (15 total)

| Path | Purpose |
|------|---------|
| `thtmlb_scripts/events.js` | Core event/submit functions |
| `thtmlb_scripts/scripts.js` | 2.1MB mega-bundle (1009 functions) — AJAX, delta handling, UI |
| `htmlb/event_dictionary.js` | Event type mappings |
| `crm_ui_start/crmuifServer.js` | Server communication framework |
| `crm_ui_start/crmuifclient.js` | Client-side CRM framework |
| `crm_ui_start/crmuifsessiontimeout.js` | Session timeout handling |
| `system/inputvalidation.js` | Input validation |
| `wcf_jquery/jquery-3.7.1.min.js` | jQuery 3.7.1 |
| `bc/ur/sap_secu.js` | Security functions |
| `ic_base/scripts/common/ic_base_utils_map.js` | [iframe] IC utilities |
| `uicmp_ltx/LaunchTransactionAdmin.js` | [iframe] Transaction launcher |
| `crm_ui_frame/crm_ui_frame_async_sender.js` | [iframe] Async communication |
| `crm_ui_frame/asynchronApplWindowAccess.js` | [iframe] Cross-window access |
