# UI guidelines

The console is an internal tool for office and IT staff. It should feel calm,
predictable and safe: a person must always know what will happen before it
happens. The layout follows Proxmox VE (top bar, navigation + resource tree on
the left, panels with title bars) in a light theme by default, with an optional
dark theme (moon/sun button, remembered per browser).

## Colour means something

| Colour | Only for | Token |
|---|---|---|
| Blue | The one primary action of a screen, selection, links, focus | `--primary`, `--sel`, `--link` |
| Green | Success | `--ok-fg`, `--ok-bg` |
| Amber | Warnings and things waiting for a person | `--warn-fg`, `--warn-bg` |
| Red | Destructive actions, failures, Production markers | `--err-fg`, `--err-bg`, `--danger` |

Colour is never the only signal: every status has an icon and a word (`Badge`,
`StatusCard`). Text contrast is at least 4.5:1 in both themes (values are listed
at the top of `frontend/src/styles.css`). Never write raw hex values in
components; use the tokens.

## One primary action

Each screen has at most one `.btn.primary`, and it is the next sensible step
(Create VM → Create plan → Deploy to Test → Validate → Request production
approval → Review and approve). Everything else is a secondary `.btn`, a
`.btn.quiet`, or `.btn.danger` for destructive actions, placed apart from the
primary one.

## Progressive disclosure

Show the decision, hide the mechanics:

- Wizards (Create VM: Describe → Basics → Software → Review and deploy; Create
  stack: Describe → Architecture → Review and deploy). Rarely used fields sit
  under **Advanced options** (`Expandable`, closed).
- Plans are shown as a sentence and a list of changes with a risk badge; the AI
  reasoning is behind **Why?**, the raw plan behind **View full plan** (drawer).
- Validation shows one line per check; individual tests are behind **Show details**.
- Errors say what failed, what to check and whether retrying helps; the raw
  error and job ID are behind **Show technical details** (`ErrorPanel`).

## Feedback patterns

| Situation | Pattern |
|---|---|
| Something finished well | Toast, auto-dismiss after 5 s |
| Something failed | Persistent toast with **View details** (opens the job log), plus an inline `ErrorPanel` where it happened |
| Something is running / waiting | Inline `StatusCard` (Pending, Running, Success, Failed, Awaiting approval) with **Show details** |
| Plans, logs, API output, AI explanations, drafts | `Drawer`: side panel, closable with Esc, copyable, syntax highlighted |
| Critical or destructive action | `Modal` (see below) |

Never use a toast to confirm a production change.

## Modals for critical actions only

`ask()` from `components/ui/modal.js` opens a native `<dialog>` (focus trap,
Escape, focus returns to the trigger). Every modal has a title, a short
explanation, a **What will happen** list, Cancel (focused first) and a confirm
button. Production changes add the checkbox *"I understand this will affect the
production environment."* and a typed word (`PROMOTE`, `RECREATE`); the confirm
button stays disabled until both are done. The backend enforces the same rules
independently.

## Writing

- Plain language, sentence case, verbs on buttons: *Deploy to Test*, *Request
  production approval*, *Review and approve*, *Reject request*.
- Say what will happen and what it affects, not how it is implemented:
  "Destroy the machine and everything on its disk" instead of "terraform -replace".
- Errors: what failed + what to check + whether to retry. No stack traces in the
  main text.
- Name things consistently: *machine* (VM or container), *Test*, *Production*,
  *stack*, *software profile*, *review queue*.

## Accessibility and layout

- Keyboard: everything reachable with Tab, visible focus ring (`--focus`), skip
  link, focus moves to the content on navigation, Escape closes drawers and modals.
- Labels on every control (`Field` links label, hint and error via `aria-describedby`);
  errors appear under the field and are announced (`role="alert"`).
- Icon-only buttons have `aria-label`. Status changes use `aria-live`.
- Touch targets are 44 px on touch devices; the layout works from 375 px wide
  (navigation becomes a slide-in panel, tables become cards).
- `prefers-reduced-motion` turns animations off.

## Component library (`frontend/src/components/ui`)

| Component | Use |
|---|---|
| `Card` | Panel with title bar, actions slot, footer |
| `.btn` classes | Buttons: `primary`, default, `quiet`, `danger`, `danger solid`, `sm`, `icon` |
| `Badge` | Status with icon + text |
| `Field` | Label, required marker, hint, error for one control |
| `modal.js` + `ModalHost` | Critical confirmations |
| `drawer.js` + `DrawerHost` | Plans, logs (live), YAML/JSON, AI output |
| `toast.js` + `ToastHost` | Short feedback |
| `DataTable` | Tables with loading and empty states, cards on phones |
| `EmptyState` | What this area is for and the first action |
| `ProgressSteps` | Lifecycle and wizard steps |
| `Expandable` | Advanced options, "Why?", details |
| `CodeView` | Highlighted, copyable plan / log / YAML / JSON |
| `StatusCard` | Inline state of an operation |
| `ErrorPanel` | Friendly error with technical details |
| `Skeleton` | Loading placeholders |
