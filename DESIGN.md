---
name: "Altvia Workspace"
description: "A restrained operational workspace inspired by Twenty CRM."
colors:
  ground: "#f7f7f6"
  surface: "#ffffff"
  ink: "#262626"
  muted: "#646464"
  line: "#e1e1df"
  control-line: "#a6a6a3"
  primary: "#245bb2"
  primary-hover: "#19478e"
  primary-ink: "#ffffff"
  focus: "#2866c0"
  error: "#a42f3b"
  error-ground: "#fcf0f1"
  notice-ground: "#f0f4fa"
  selected: "#eaeae8"
  success: "#286247"
  success-ground: "#edf5ef"
  warning: "#825b1a"
  warning-ground: "#fbf3df"
  dark-ground: "#202020"
  dark-surface: "#252525"
  dark-ink: "#ededeb"
  dark-muted: "#adadaa"
  dark-line: "#3e3e3c"
  dark-control-line: "#777773"
  dark-primary: "#9ec3ff"
  dark-primary-hover: "#bdd5ff"
  dark-primary-ink: "#17283f"
  dark-focus: "#9ec3ff"
  dark-error: "#ffb7bf"
  dark-error-ground: "#402b2e"
  dark-notice-ground: "#2c3541"
  dark-selected: "#363635"
  dark-success: "#a4d5b4"
  dark-success-ground: "#293b30"
  dark-warning: "#e9ca86"
  dark-warning-ground: "#403827"
typography:
  headline:
    fontFamily: "\"Segoe UI\", -apple-system, BlinkMacSystemFont, Arial, sans-serif"
    fontSize: "26px"
    fontWeight: 650
    lineHeight: 1.25
    letterSpacing: "-0.025em"
  headline-mobile:
    fontFamily: "\"Segoe UI\", -apple-system, BlinkMacSystemFont, Arial, sans-serif"
    fontSize: "24px"
    fontWeight: 650
    lineHeight: 1.25
    letterSpacing: "-0.025em"
  section-title:
    fontFamily: "\"Segoe UI\", -apple-system, BlinkMacSystemFont, Arial, sans-serif"
    fontSize: "18px"
    fontWeight: 650
    lineHeight: 1.35
  subheading:
    fontFamily: "\"Segoe UI\", -apple-system, BlinkMacSystemFont, Arial, sans-serif"
    fontSize: "16px"
    fontWeight: 650
    lineHeight: 1.5
  body:
    fontFamily: "\"Segoe UI\", -apple-system, BlinkMacSystemFont, Arial, sans-serif"
    fontSize: "15px"
    fontWeight: 400
    lineHeight: 1.5
  label:
    fontFamily: "\"Segoe UI\", -apple-system, BlinkMacSystemFont, Arial, sans-serif"
    fontSize: "14px"
    fontWeight: 600
    lineHeight: 1.5
  navigation:
    fontFamily: "\"Segoe UI\", -apple-system, BlinkMacSystemFont, Arial, sans-serif"
    fontSize: "13px"
    fontWeight: 400
    lineHeight: 1.5
  metadata:
    fontFamily: "\"Segoe UI\", -apple-system, BlinkMacSystemFont, Arial, sans-serif"
    fontSize: "12px"
    fontWeight: 400
    lineHeight: 1.5
rounded:
  status: "4px"
  navigation: "5px"
  control: "6px"
  surface: "8px"
spacing:
  "4": "4px"
  "8": "8px"
  "10": "10px"
  "12": "12px"
  "16": "16px"
  "20": "20px"
  "24": "24px"
  "28": "28px"
  "32": "32px"
  "36": "36px"
  "48": "48px"
components:
  button-primary:
    backgroundColor: "{colors.primary}"
    textColor: "{colors.primary-ink}"
    typography: "{typography.label}"
    rounded: "{rounded.control}"
    padding: "7px 12px"
  button-primary-hover:
    backgroundColor: "{colors.primary-hover}"
  button-outline:
    backgroundColor: "transparent"
    textColor: "{colors.ink}"
    rounded: "{rounded.control}"
    padding: "7px 12px"
  button-ghost:
    backgroundColor: "transparent"
    rounded: "{rounded.control}"
    padding: "7px 12px"
  input:
    backgroundColor: "{colors.surface}"
    textColor: "{colors.ink}"
    rounded: "{rounded.control}"
    padding: "8px 10px"
  navigation-link:
    textColor: "{colors.muted}"
    typography: "{typography.navigation}"
    rounded: "{rounded.navigation}"
    padding: "8px 10px"
  navigation-link-current:
    backgroundColor: "{colors.selected}"
    textColor: "{colors.ink}"
  status-chip:
    backgroundColor: "{colors.ground}"
    textColor: "{colors.muted}"
    rounded: "{rounded.status}"
    padding: "3px 8px"
  working-surface:
    backgroundColor: "{colors.surface}"
    textColor: "{colors.ink}"
    rounded: "{rounded.surface}"
    padding: "36px"
  notice:
    backgroundColor: "{colors.notice-ground}"
    textColor: "{colors.ink}"
    rounded: "{rounded.control}"
    padding: "12px"
  error-message:
    backgroundColor: "{colors.error-ground}"
    textColor: "{colors.error}"
    rounded: "{rounded.control}"
    padding: "12px"
---

# Design System: Altvia Workspace

## Overview

**Creative North Star: "The Daily Operations Desk"**

The Daily Operations Desk makes repeated work legible through a quiet sidebar, a continuous working field and aligned records. The user-selected Twenty CRM reference informs the restraint, density and navigation; Altvia keeps its own name, real capabilities and resource boundaries. This replaces the former navy service-desk wayfinding world.

Offwhite and white planes become neutral charcoal in dark mode. System sans, small line icons and deliberate blue actions keep attention on records and their next action. This is a product UI direction, not approved corporate branding: no corporate logo or typeface was supplied.

**Key Characteristics:**

- Neutral sidebar and continuous content with shared desktop alignment.
- Compact system typography, labeled native fields and line icons.
- Blue actions and soft semantic chips with explicit state wording.
- Flat section rules, responsive labeled records and deliberate inline recovery.

## Colors

The palette is predominantly neutral, with an operational blue and soft semantic feedback. Frontmatter records the exact light tokens and their `dark-` counterparts from the stylesheet. At runtime the dark theme overrides the same semantic CSS properties.

### Primary

- **Operational Blue** (`primary`, `primary-hover`): deliberate actions and links; pale blue in dark mode uses the separate `primary-ink` foreground.
- **Focus Blue** (`focus`): visible keyboard outline, independent of current navigation selection.

### Neutral

- **Offwhite Ground** (`ground`): sidebar, board columns and quiet secondary regions; charcoal in dark mode.
- **Working Surface** (`surface`): continuous operational field, native inputs and bounded identity surfaces.
- **Record Ink / Quiet Metadata** (`ink`, `muted`): primary text and readable secondary context.
- **Hairline / Control Stroke** (`line`, `control-line`): section separation versus the stronger outline needed to recognize fields.
- **Current Context** (`selected`): navigation hover/current state and ghost-control hover.
- **Notice Ground** (`notice-ground`): quiet informational feedback, inline confirmations and active operational-state backgrounds.

Error, success and warning pairs are semantic feedback, not additional brand accents. Error uses `error` / `error-ground`; active/completed records use `success` / `success-ground`; blocked and waiting records use `warning` / `warning-ground`. State words remain visible. New/open/in-progress records use the action color on notice ground. Unmapped states keep the neutral chip.

**The Neutral Context Rule.** Use neutral selection for the current destination; reserve blue for actions and the operational states already mapped to it.

## Typography

**Body and UI Font:** Segoe UI, with -apple-system, BlinkMacSystemFont, Arial and sans-serif fallbacks. There is no separate display face or downloaded font. System typography is part of the chosen operational world.

### Hierarchy

- **Headline:** semibold (650), compact (26px), line-height (1.25), tracking (-0.025em); narrow screens use (24px) at the 540px breakpoint.
- **Section title:** semibold (650), (18px), line-height (1.35).
- **Subheading:** semibold (650), (16px).
- **Body:** regular (400), (15px), line-height (1.5). Narrative work text preserves whitespace and wraps, with a (75ch) maximum; introductions and incoming text use (72ch).
- **Labels and actions:** (14px), semibold (600). Record cells and secondary metadata also use (14px) with their observed regular weight.
- **Navigation:** (13px), regular at rest and semibold (600) for the current destination; mobile links use (14px).
- **Small metadata:** (12px), including table headings, navigation groups, status chips and footer. Chips use medium weight (500).

Use sentence-case operational names and tabular numerals for pagination. No decorative display hierarchy is established.

## Layout

Desktop authenticated pages use a fixed left sidebar (232px) and a context bar with a minimum height of (56px). The continuous content field starts after the sidebar and takes (28px 32px 48px) padding. Operational content fills the available width up to (1440px); the main element and retained private wrapper both stretch to the track. Account content remains a deliberate narrower exception (640px), with a flat interior rather than an identity card. Unauthenticated identity states use a centered, bounded surface (440px).

Sections use horizontal rules and (24px) vertical padding. Forms use wrapping action rows and adaptive grids, with repeated gaps of (12px), (16px), (20px), (24px), (28px) and (32px). Two-column roster work stacks at (900px). Ticket rows align subject/client, queue/priority, responsible person and state; task rows align title, state and deadline. Text may wrap without moving the corresponding column origins.

At or below (900px), the sidebar becomes a named in-flow navigation disclosure, opened by a (44px) trigger. It expands above route content; it is not a modal drawer. Content padding becomes (24px 20px 40px), table headings disappear, record fields gain visible mobile labels and ticket filters stack. At or below (360px), horizontal content padding becomes (16px). The document supports a minimum width of (320px).

At or below (540px), and for coarse pointers, buttons and native fields gain (44px) minimum heights, fields use (16px) type, and the password reveal remains a separate (40px) control. Identity surfaces use (28px 24px) padding, reduced to (24px 20px) below (360px).

Kanban is a named, focusable bounded horizontal scroll region, not stacked columns: columns are (240px), with a (16px) gap and maximum region height of (560px). At (1500px) and above, columns use `minmax(220px, 1fr)`. Each column keeps independent paging. Prose has its own measure regardless of the surrounding working track.

**The Shared Track Rule.** Operational headings, facts, forms and section rules fill the shared content track; bound prose independently.

## Elevation & Depth

Depth comes from neutral plane changes and one-pixel borders. The shipping stylesheet has no box-shadow vocabulary. Section boundaries stay flat; the sidebar and context bar establish location through tone, position and rules. Confirmation panels use notice ground and a border, while private note/composer regions use ground tone.

**The Flat Working Field Rule.** Separate work with surface tones and hairlines, without decorative shadows.

Motion is limited to existing loading indicators (`spin 1s linear infinite`). Reduced-motion preference disables that animation. There is no transition or decorative entrance system.

## Shapes

Use modest corners: status chips (4px), navigation links (5px), controls/feedback/board cards (6px), bounded identity surfaces (8px). Operational sections remain continuous rectangular planes. The simple square Altvia letter mark uses (6px) corners and the current ink/surface pair; it is a UI identifier, not an approved corporate logo. Tiny state dots and spinner geometry are functional exceptions to the mostly rectangular form language.

## Components

### Buttons

Compact and explicit. Primary buttons use the action/foreground pair; hover uses the dedicated action-hover token. Outline buttons use ink, a hairline border and notice-ground hover. Ghost buttons are transparent with selected-ground hover; the theme control supplies muted foreground. Shared padding is (7px 12px), radius (6px), and minimum height (36px), with the responsive target rule from Layout. Login submit is full width with a (48px) minimum height. Disabled controls use opacity (.65) and a waiting cursor. Keyboard focus uses a (2px) outline with a (3px) offset.

### Chips

State is a readable word on a soft semantic ground, not a clickable badge. Neutral chips use muted/ground; mapped colors follow Colors. Type is (12px), weight (500), padding (3px 8px), radius (4px). Preserve wrapping and maximum width rather than truncating state meaning.

### Cards / Containers

The identity form is the bounded working surface, with a hairline, (8px) radius and (36px) padding. Authenticated operational content uses continuous flat sections, not repeated cards. Board columns use ground and (12px) padding; task cards use surface, a hairline, (6px) corners and (12px) padding. Inline confirmations use notice ground, a border, (6px) corners and (20px) padding.

### Inputs / Fields

Native labeled fields use surface/ink, the stronger control-line border, (6px) radius, (8px 10px) padding and a (40px) minimum height before responsive adaptation. Labels are explicit and sit (8px) above controls. Placeholders use muted ink; invalid input borders use error ink with explanatory text. Preserve keyboard focus, select semantics and resizable textareas.

### Navigation

The fixed desktop sidebar groups real destinations with small Lucide line icons (18px, stroke width 1.7), quiet group labels and the account region at its bottom. Links use (8px 10px) padding and a (36px) minimum height; current and hover states use selected ground and ink. Current state also uses semibold type and `aria-current`. Below (900px), links grow to (44px). Opening the disclosure focuses its first link; Escape closes it and returns focus to the trigger. Selecting the exact current destination restores trigger focus; real route changes retain the page-heading focus owner. The authenticated skip link targets route content after navigation. Link visibility follows capabilities while API resource scope remains authoritative.

### Records, Facts and Recovery

List rows use hairlines, neutral linked titles and muted scope metadata. Desktop column alignment becomes labeled wrapped fields on mobile. Fact grids use adaptive tracks with (240px) minimums bounded by available width. Recovery feedback retains status/alert text and actual next actions. Public responses, private notes and received text remain visibly separate even when they share typography and section rhythm. Received text uses a bounded scroll area (22rem), a hairline, ground tone and preserved whitespace; it is not HTML rendering.

## Do's and Don'ts

### Do:

- **Do** use semantic light/dark tokens for surfaces, controls, feedback and state.
- **Do** align operational headings and section rules on the shared content track while keeping prose readable.
- **Do** preserve explicit labels, visible keyboard focus and text alongside state color.
- **Do** wrap long records, retain mobile field labels and keep Kanban overflow inside its named region.
- **Do** keep exact review, uncertain-result recovery and session-ending confirmations legible beside the action.

### Don't:

- **Don't** restore the former navy masthead or cool-blue page ground.
- **Don't** invent metrics, CRM features, imagery or an approved Altvia logo from the reference.
- **Don't** replace native semantic controls or named actions with decorative glyphs.
- **Don't** turn each operational section into an elevated card or add decorative motion.
- **Don't** use a navigation destination, assignment or visual state as an access grant.
