# Snapshot format

Write one UTF-8 JSON object from your own script, then point `server.py --data` at that file. That is the entire integration: no agent framework, database, account, or extra Python package is required. The server reads the file on every `/pad.json` request; the display polls once a minute.

Start with [the English demo](../demo/demo.json) or [the Korean demo](../demo/demo.ko.json). Both contain invented work and amounts. The `lang=en` or `lang=ko` query chooses interface labels only. Text inside your snapshot stays as written.

## Top-level fields

Every field in this table is required. A genuinely empty section is `[]`, never an omitted field. Unknown extra fields are ignored.

| Field | Type | Example | Meaning |
| --- | --- | --- | --- |
| `at` | string | `"09:00"` | Human-readable snapshot time, shown unchanged in the header. Include a date when helpful. |
| `now` | finite number | `1908003600` | Snapshot time as Unix seconds. Update it whenever you produce a new snapshot. |
| `head` | object | `{"members":8,"working":6}` | Agent counts, excluding the human owner. |
| `decisions` | array of decision objects | `[{"id":"choice-a","what":"Choose the launch bundle"}]` | Owner choices, most urgent first. |
| `hands` | array of hand objects | `[{"id":"hand-a","title":"Photograph the sample","when":"10:30"}]` | Work that needs the owner in person. |
| `notices` | array of notice objects | `[{"id":"note-a","title":"Guide draft is ready"}]` | Things the owner should know. |
| `schedule` | array of event objects | `[{"id":"event-a","time":"09:30","title":"Daily plan"}]` | Remaining events in the intended display order. |
| `requests` | array of request objects | `[]` | Open delegations in the intended display order. |
| `teams` | array of team objects | `[{"name":"Sales","task":"Price the launch bundle","worker":"agent-07 Pricing"}]` | Teams in your order, without predefined names. |
| `money` | string or null | `"2030-06-18 / Demo sales $1,234 / 7 orders"` | One complete money line. `null` or `""` means not yet tallied. Never replace unknown money with zero. |

`head.members` and `head.working` are required nonnegative integers. The display shows both without guessing counts from team labels.

## Row fields

Required fields are marked **required**. Every row has a stable, nonempty identity: `id` for most sections, `name` for teams. Identities must be unique within each section. Keep them unchanged when a title changes so that the display can mark just the changed value.

### Decisions

| Field | Type | Example | Meaning |
| --- | --- | --- | --- |
| `id` | string, required | `"choice-a"` | Stable identity. |
| `what` | string, required | `"Choose the launch bundle"` | Choice, up to two visible lines. |
| `by` | string | `"11:30"` | Deadline, shown with a translated “Due” label. |
| `stops` | string | `"The product page needs a final choice."` | Consequence of waiting. |

Only the first decision is shown. Additional decisions appear as `+N more` and are available by opening the section. There are no approval buttons or write requests.

### Hands

| Field | Type | Example | Meaning |
| --- | --- | --- | --- |
| `id` | string, required | `"hand-a"` | Stable identity. |
| `title` | string, required | `"Photograph the sample"` | One visible line. |
| `when` | string, required | `"10:30"` | Short deadline, kept intact at the right. Use `""` when unknown. |

Three rows are shown, with `+N more` for the rest. Long titles use an ellipsis; deadlines do not.

### Notices

| Field | Type | Example | Meaning |
| --- | --- | --- | --- |
| `id` | string, required | `"note-a"` | Stable identity. |
| `title` | string, required | `"Preview build is blocked"` | Main notice. |
| `extra` | string | `"Waiting for a sample image"` | Supporting text in the detail view. |
| `blocked` | boolean | `true` | Red status dot plus a “Blocked” label. Otherwise the label is “On track”. |
| `work_id` | string | `"preview-build"` | Optional shared work identity. Notices about the same work merge into one visible row; a blocked notice takes priority. |

Up to three distinct work items are shown, with `+N more` for the rest. Supply short main titles; full text stays available in the detail view.

### Schedule

| Field | Type | Example | Meaning |
| --- | --- | --- | --- |
| `id` | string, required | `"event-a"` | Stable identity. |
| `time` | string, required | `"09:30"` | Use `HH:MM` so it fits the dedicated time column. |
| `title` | string, required | `"Daily plan"` | One visible line. |
| `extra` | string | `"Review the sample"` | Optional second line. |
| `done` | boolean | `false` | Completed events are hidden. Defaults to false. |

The next four unfinished events are shown, or fewer if second lines need room. Keep overdue unfinished events in your array: the display never removes an event just because its time has passed. The producer chooses event order; times are not interpreted across time zones.

### Delegated requests

| Field | Type | Example | Meaning |
| --- | --- | --- | --- |
| `id` | string, required | `"request-a"` | Stable delegation identity. |
| `fromId` | string, required | `"owner"` | Short sender label. |
| `toId` | string, required | `"agent-07"` | Short recipient label. |
| `title` | string, required | `"Compare bundle prices"` | Work title; this column can use an ellipsis. |
| `stage` | string, required | `"running"` | `waiting`, `running`, or `received` use translated labels. Any other short label is shown unchanged. |
| `t` | finite number, required | `1907999040` | Unix seconds when this request started. |
| `blocked` | boolean | `false` | Red dot plus “Blocked”; takes precedence over a long wait. |
| `done` | boolean | `false` | Completed work is hidden. `received` alone does not mean complete. |

Three open rows are shown, with `+N more` for the rest. Waiting time is calculated from `now - t`, then advances on each minute boundary while this snapshot remains loaded. A snapshot with the same `now` keeps its existing timer on refresh. Change `now` when writing a new snapshot. This also lets an invented demo retain its intended waiting times when opened later.

Waits over 60 minutes get an amber dot and the words “Long wait”. Values of 1,000 minutes or more use whole hours to fit. Keep sender, recipient, and custom stage labels short; these columns are not shortened with an ellipsis.

### Teams

| Field | Type | Example | Meaning |
| --- | --- | --- | --- |
| `name` | string, required | `"Sales"` | Stable team identity and visible name. |
| `task` | string, required | `"Price the launch bundle"` | One current task. An empty string shows “Resting”. |
| `worker` | string, required | `"agent-07 Pricing"` | Worker doing this task. Use `""` if idle. |
| `ids` | array of strings | `["agent-07","agent-08"]` | Optional secondary list of team members. Hidden in portrait to preserve space. |
| `more` | nonnegative integer | `1` | Other work in the team, shown beside the worker as `+N more`. When present, the worker label uses its first word to preserve space. Defaults to zero. |
| `blocked` | boolean | `false` | Red status dot with “Blocked”. Defaults to false. |

Up to six team rows are reserved. Their order always follows your array; extra teams use `+N more`. A missing current task means resting, not a load error.

### Shared optional text

Every row may include `original` (string, for example `"Compare the three draft bundle prices before lunch."`) and `updated` (string, for example `"09:00"`). Both are displayed unchanged in the detail view. Click or tap a section, or focus it and press Enter, to see full text. Escape or Close returns to the board; an untouched detail view closes after 90 seconds.

## Empty and failed data

| Section | English empty label | Korean empty label |
| --- | --- | --- |
| Decisions | Nothing to decide | 정하실 것 없음 |
| Hands | Nothing needs your hands | 직접 하실 일 없음 |
| Notices | Nothing new to report | 새로 알려 드릴 일 없음 |
| Schedule | No remaining events | 남은 일정 없음 |
| Requests | No replies pending | 기다리는 답 없음 |
| Teams | Resting | 쉬는 중 |
| Money | Not yet tallied | 집계 전 |

If the file is missing, unreadable, invalid UTF-8, invalid JSON, or missing required fields, `/pad.json` returns HTTP 200 with an error object such as `{"error":"data_unavailable","at":"09:01"}`. The screen shows “Could not load(09:01)” or “불러오지 못함(09:01)”. It retains the last successful snapshot if there is one. On a cold failure it shows the warning without claiming that the work queues are empty. The next successful poll restores the normal display.

`/healthz` returns `{"ok":true}` while the server is running. It reports server availability; `/pad.json` reports data availability. Filesystem paths and parser errors are not exposed.

Write to a temporary file in the same directory, then rename it over the live JSON file to publish each snapshot in one step. This avoids partial reads. Store private snapshots in `data/` or in a `*.local.json` file; both are ignored by version control. Serve only information you want visible on the display.
