---
name: Altvia Workspace
description: A clear entrance to an internal workplace.
colors:
  ground: "#edf3fa"
  surface: "#ffffff"
  ink: "#14243b"
  muted: "#52657e"
  line: "#b7c6d9"
  primary: "#2459ca"
  primary-hover: "#1746ab"
  focus: "#2563eb"
  error: "#a72336"
  error-ground: "#fff0f2"
  notice-ground: "#e9f2ff"
  header: "#142c4d"
  header-text: "#f3f7ff"
  header-muted: "#c0d2ec"
  dark-ground: "#101f32"
  dark-surface: "#192e48"
  dark-ink: "#f1f6ff"
  dark-muted: "#b5c8e2"
  dark-line: "#526b8a"
  dark-primary: "#a7c6ff"
  dark-primary-hover: "#c1d7ff"
  dark-focus: "#a7c6ff"
  dark-error: "#ffc0ca"
  dark-error-ground: "#492333"
  dark-notice-ground: "#233f60"
  dark-header: "#0c192a"
  location-divider: "#5c7596"
  location-marker: "#a7c6ff"
  ghost-hover: "#7b9cc226"
typography:
  headline:
    fontFamily: '"Segoe UI", -apple-system, BlinkMacSystemFont, Arial, sans-serif'
    fontSize: "28px"
    fontWeight: 650
    lineHeight: 1.2
    letterSpacing: "-0.025em"
  headline-mobile:
    fontFamily: '"Segoe UI", -apple-system, BlinkMacSystemFont, Arial, sans-serif'
    fontSize: "26px"
    fontWeight: 650
    lineHeight: 1.2
    letterSpacing: "-0.025em"
  body:
    fontFamily: '"Segoe UI", -apple-system, BlinkMacSystemFont, Arial, sans-serif'
    fontSize: "16px"
    fontWeight: 400
    lineHeight: 1.5
  label:
    fontFamily: '"Segoe UI", -apple-system, BlinkMacSystemFont, Arial, sans-serif'
    fontSize: "14px"
    fontWeight: 600
    lineHeight: 1.5
  secondary:
    fontFamily: '"Segoe UI", -apple-system, BlinkMacSystemFont, Arial, sans-serif'
    fontSize: "14px"
    fontWeight: 400
    lineHeight: 1.5
  footer:
    fontFamily: '"Segoe UI", -apple-system, BlinkMacSystemFont, Arial, sans-serif'
    fontSize: "12px"
    fontWeight: 400
    lineHeight: 1.5
rounded:
  control: "6px"
  surface: "12px"
spacing:
  micro: "4px"
  compact: "8px"
  control-y: "10px"
  inset: "12px"
  control-x: "16px"
  edge: "20px"
  group: "24px"
  separation: "32px"
  surface: "36px"
components:
  button-primary:
    backgroundColor: "{colors.primary}"
    textColor: "{colors.surface}"
    typography: "{typography.label}"
    rounded: "{rounded.control}"
    padding: "10px 16px"
  button-primary-hover:
    backgroundColor: "{colors.primary-hover}"
  button-outline:
    backgroundColor: "transparent"
    textColor: "{colors.ink}"
    typography: "{typography.label}"
    rounded: "{rounded.control}"
    padding: "10px 16px"
  button-ghost:
    backgroundColor: "transparent"
    rounded: "{rounded.control}"
    typography: "{typography.label}"
    padding: "10px 16px"
  input:
    backgroundColor: "{colors.surface}"
    textColor: "{colors.ink}"
    typography: "{typography.body}"
    rounded: "{rounded.control}"
    padding: "10px 12px"
    width: "100%"
  working-surface:
    backgroundColor: "{colors.surface}"
    textColor: "{colors.ink}"
    rounded: "{rounded.surface}"
    padding: "36px"
    width: "100%"
  notice:
    backgroundColor: "{colors.notice-ground}"
    textColor: "{colors.ink}"
    typography: "{typography.secondary}"
    rounded: "{rounded.control}"
    padding: "12px"
  error-message:
    backgroundColor: "{colors.error-ground}"
    textColor: "{colors.error}"
    typography: "{typography.secondary}"
    rounded: "{rounded.control}"
    padding: "12px"
---

# Design System: Altvia Workspace

## Overview

**Creative North Star: "Service Desk Wayfinding"**

A clear entrance to an internal workplace. A navy masthead establishes identity,
a cool blue ground separates the working surface, and a compact location marker
names the current place. The character is calm, readable and operational.

This is the provisional visual system extracted from the browser identity
implementation, not approved corporate branding. System typography and familiar
controls support repeated use in Portuguese. The current surface contains real
login, account and logout behavior; its composition is recorded in the surface
brief rather than imposed on future product screens.

**Key Characteristics:**
- Navy identity band and cool blue ground.
- Flat, bordered working surfaces with a compact control scale.
- Cobalt action in light mode and pale blue action in dark mode.
- Explicit labels, visible focus and a state-bearing location marker.

## Colors

The palette uses a blue primary family, cool neutrals and distinct error colors.
The frontmatter records the source CSS values; dark-prefixed entries are the
overrides applied to the same semantic properties by the dark theme.

### Primary

- **Cobalt Action:** primary and primary-hover identify the main action; the dark
  equivalents become pale blue while preserving surface-colored button text.
- **Focus Blue:** focus supplies the keyboard outline. The masthead theme control
  uses header-muted for its outline against the dark band.

### Neutral

- **Cool Ground:** ground is the page canvas; surface is the working plane.
- **Navy Ink:** ink carries content; muted carries supporting text and metadata.
- **Blue Boundary:** line separates fields, surfaces and session actions.
- **Masthead Navy:** header anchors identity; header-text and header-muted separate
  the name from the current location. These two text colors persist in dark mode.
- **Location Blue:** location-marker and location-divider define the small marker
  and desktop separator. Ghost-hover supplies a translucent interactive wash.
- **Notice Blue:** notice-ground supports session status without competing with
  primary actions. Error and error-ground pair text and field borders with an
  error message background in each theme.

**The Semantic Theme Rule.** Change semantic colors together through the theme;
retain the relationship between ground, surface, text, boundary and state.

## Typography

The body, controls and operational headings share the system sans stack in the
frontmatter. There is no decorative display face. Brand text is a wordmark-like
text treatment, not a supplied logo asset.

### Hierarchy

- **Headline:** short operational headings use the headline role and switch to
  headline-mobile at the narrow breakpoint. Balanced wrapping avoids isolated
  short lines.
- **Body:** instructions, field values and account data use the body role;
  account values add semibold emphasis.
- **Label:** field names and compact buttons use the label role. The full-width
  login action uses body-sized text with semibold weight.
- **Secondary:** location, validation, notices and supporting help use smaller
  text. Help uses a more open line height (1.7).
- **Footer:** quiet product and environment identification uses the footer role.
- **Brand:** the name uses a compact bold treatment (24px, weight 700,
  letter spacing -0.025em); Workspace is regular. Narrow screens reduce it to
  20px. This is identity text, not an additional display hierarchy.

## Layout

The shell fills the viewport with a masthead, flexible main region and footer.
The identity working surface is centered, left-aligned internally and limited to
440px. Its desktop inset uses the surface spacing token. The main region uses
64px vertical and 20px horizontal padding. The masthead is at least 80px tall;
its horizontal inset scales from 20px through 5vw to 72px.

Related fields are separated by the group token. Introductory text and session
action regions use the separation token. Labels sit above their controls with
the compact gap. Account values and long error content wrap rather than widening
the surface.

At a maximum viewport width of 540px, the masthead wraps and the location moves
to its own row. Its divider disappears. The theme control becomes icon-only,
the masthead minimum height becomes 72px, the main vertical inset becomes 32px,
and working-surface padding becomes 28px vertically and 24px horizontally. The
footer can wrap. The supported CSS minimum width is 320px.

## Elevation & Depth

The implemented interface has no shadows. Tonal planes, one-pixel borders and
spacing establish hierarchy. Focus outlines communicate keyboard position rather
than simulated elevation. There are no gradients, backdrop effects or decorative
animations in the identity surface.

**The Flat Working Plane Rule.** Use the established tonal and border hierarchy
for working surfaces; do not introduce shadow elevation as an inherited default.

## Shapes

Controls and messages use the control radius; working surfaces use the larger
surface radius. Borders are one pixel. The location marker is a small circle
(6px by 6px), aligned with its current-place label. It communicates place through
the adjacent words, not through color alone. Icons are conventional line SVGs.

## Components

### Buttons

Buttons are compact, explicit and familiar. Their shared minimum height is 44px;
the login action is full-width and at least 48px tall. Primary uses the action
colors, outline uses the boundary color and a notice-colored hover, and ghost
uses a translucent hover wash. Disabled controls reduce opacity to 0.65 and use
a waiting cursor. Hover does not change disabled buttons.

Keyboard focus uses a solid 3px outline offset by 4px. There is no animated hover
transition. Loading actions retain descriptive text and may add the spinner.

### Cards / Containers

The working surface is a bounded task container with a surface-colored fill,
one-pixel boundary and larger radius. It has no shadow. Identity content uses
the centered maximum width and responsive insets described in Layout. The
session-ending action sits below its own divider and spacing.

### Inputs / Fields

Fields have explicit labels, surface fill, ink text, a one-pixel boundary and a
minimum height of 48px. Placeholder text uses muted ink. Invalid fields use the
error boundary and adjacent explanatory text; global failures use a colored
message block. The password control reserves 56px for its 44px reveal action,
which has an accessible name and pressed state.

### Masthead and Location Marker

The masthead pairs the text identity with a current-place label, separated on
desktop by a line. The marker reads Acesso before authentication and Minha conta
after it. This is a state-bearing identity pattern, not a navigation menu. The
theme control stays at the trailing edge and retains its accessible name when
the visible label is hidden on mobile.

### Notices and Recovery

Session notices use the notice plane and ink text. Errors pair the error plane
with error text, expose an alert and explain the next action. Connection failure
offers Tentar novamente. New login, account and connection views move focus to
their heading. Ordinary query refreshes do not move focus out of an active field.
The skip link becomes visible on focus and targets the main content.

### Motion

Only loading indicators rotate: one full turn over one second, linear and
repeating. Reduced-motion preference disables the rotation while descriptive
loading text remains visible.

## Do's and Don'ts

### Do:

- **Do** use the semantic theme relationships for every state and control.
- **Do** preserve visible keyboard focus and labeled controls in both themes.
- **Do** keep the location label tied to the real identity state.
- **Do** wrap long account values and messages within the available width.
- **Do** keep session-ending actions visibly separated from account data.

### Don't:

- **Don't** present this provisional palette or text identity as approved corporate branding.
- **Don't** replace explicit state and error wording with color or icons alone.
- **Don't** inherit decorative shadows or motion into the flat working surfaces.
- **Don't** move focus during an ordinary background identity refresh.
