---
name: Kinetic Logic
colors:
  surface: '#f9f9f9'
  surface-dim: '#dadada'
  surface-bright: '#f9f9f9'
  surface-container-lowest: '#ffffff'
  surface-container-low: '#f3f3f3'
  surface-container: '#eeeeee'
  surface-container-high: '#e8e8e8'
  surface-container-highest: '#e2e2e2'
  on-surface: '#1a1c1c'
  on-surface-variant: '#5a4136'
  inverse-surface: '#2f3131'
  inverse-on-surface: '#f1f1f1'
  outline: '#8e7164'
  outline-variant: '#e3bfb1'
  surface-tint: '#a33e00'
  primary: '#a33e00'
  on-primary: '#ffffff'
  primary-container: '#ff6600'
  on-primary-container: '#561d00'
  inverse-primary: '#ffb596'
  secondary: '#8f4e00'
  on-secondary: '#ffffff'
  secondary-container: '#fe9832'
  on-secondary-container: '#683700'
  tertiary: '#0062a1'
  on-tertiary: '#ffffff'
  tertiary-container: '#009cfc'
  on-tertiary-container: '#003155'
  error: '#ba1a1a'
  on-error: '#ffffff'
  error-container: '#ffdad6'
  on-error-container: '#93000a'
  primary-fixed: '#ffdbcd'
  primary-fixed-dim: '#ffb596'
  on-primary-fixed: '#360f00'
  on-primary-fixed-variant: '#7c2e00'
  secondary-fixed: '#ffdcc2'
  secondary-fixed-dim: '#ffb77a'
  on-secondary-fixed: '#2e1500'
  on-secondary-fixed-variant: '#6d3a00'
  tertiary-fixed: '#d0e4ff'
  tertiary-fixed-dim: '#9ccaff'
  on-tertiary-fixed: '#001d35'
  on-tertiary-fixed-variant: '#00497b'
  background: '#f9f9f9'
  on-background: '#1a1c1c'
  surface-variant: '#e2e2e2'
typography:
  headline-xl:
    fontFamily: Hanken Grotesk
    fontSize: 40px
    fontWeight: '700'
    lineHeight: 48px
    letterSpacing: -0.02em
  headline-lg:
    fontFamily: Hanken Grotesk
    fontSize: 32px
    fontWeight: '600'
    lineHeight: 40px
    letterSpacing: -0.01em
  headline-lg-mobile:
    fontFamily: Hanken Grotesk
    fontSize: 24px
    fontWeight: '600'
    lineHeight: 32px
  headline-md:
    fontFamily: Hanken Grotesk
    fontSize: 24px
    fontWeight: '600'
    lineHeight: 32px
  body-lg:
    fontFamily: Inter
    fontSize: 18px
    fontWeight: '400'
    lineHeight: 28px
  body-md:
    fontFamily: Inter
    fontSize: 16px
    fontWeight: '400'
    lineHeight: 24px
  body-sm:
    fontFamily: Inter
    fontSize: 14px
    fontWeight: '400'
    lineHeight: 20px
  label-md:
    fontFamily: Geist
    fontSize: 14px
    fontWeight: '500'
    lineHeight: 16px
    letterSpacing: 0.02em
  label-sm:
    fontFamily: Geist
    fontSize: 12px
    fontWeight: '600'
    lineHeight: 14px
  code-snippet:
    fontFamily: Geist
    fontSize: 13px
    fontWeight: '400'
    lineHeight: 20px
rounded:
  sm: 0.5rem
  DEFAULT: 1rem
  md: 1.5rem
  lg: 2rem
  xl: 3rem
  full: 9999px
spacing:
  base: 4px
  xs: 8px
  sm: 12px
  md: 16px
  lg: 24px
  xl: 32px
  gutter: 20px
  margin-mobile: 16px
  margin-desktop: 40px
---

## Brand & Style
The design system is engineered for a high-performance AI data analysis environment that balances technical precision with collaborative warmth. The brand personality is "The Intelligent Partner"—authoritative yet accessible, shifting the perception of data analysis from a solitary task to a conversational experience.

The visual style is **Corporate / Modern** with a lean toward **Minimalism**. In this light mode iteration, it prioritizes extreme clarity through high-contrast typography against clean, structured surfaces, ensuring that complex data visualizations remain the focal point. Subtle high-tech accents are introduced through the strategic application of vibrant orange hues against a crisp, technical backdrop, creating a "Laboratory" aesthetic that feels innovative, professional, and reliable.

## Colors
The palette is transitioned to a light mode foundation to provide a clean, high-clarity workspace that feels expansive and professional.

- **Primary Orange (#FF6600):** Reserved for primary actions, critical AI insights, and active states. It serves as the "energy" of the system.
- **Secondary Orange (#FF9933):** Used for supporting elements, hover states on primary buttons, and categorizing specific data streams.
- **Surface Neutrals:** The interface utilizes clean whites and soft grays derived from the neutral seed (#F5F5F5). Backgrounds are bright, while cards and workspace modules use subtle tonal shifts to create elevation and hierarchy.
- **Text & Stroke:** We utilize deep charcoals and slate tones for high-contrast typography, ensuring legibility remains sharp even in dense data views against the light background.

## Typography
The typography strategy employs three distinct typefaces to separate intent:
1. **Hanken Grotesk (Headlines):** A sharp, contemporary grotesque that provides a modern, professional feel.
2. **Inter (Body):** Used for all primary reading, data tables, and chat messages due to its exceptional legibility and systematic neutral tone.
3. **Geist (Labels/UI):** A monospaced-influenced sans-serif used for UI labels, metadata, and AI-generated code snippets to emphasize the technical "Lab" environment.

Use tight letter-spacing for headlines to maintain a compact, authoritative look. For body text, ensure a generous line-height to facilitate long-form data reading in the bright interface.

## Layout & Spacing
The design system utilizes a **Fluid Grid** model based on a 4px baseline. 

- **Desktop:** A 12-column grid with 20px gutters. Workspaces are often split-screen (Chat on the left/right, Data/Viz in the center), requiring flexible container logic.
- **Mobile:** A 4-column grid with 16px margins. Complex data tables should collapse into "card stacks" or provide horizontal scroll with frozen first columns.
- **Spacing Rhythm:** Use 16px (md) for standard padding between elements and 32px (xl) to separate distinct logic sections or modules.

## Elevation & Depth
In this Light Mode environment, the system utilizes **Tonal Layers** and **Low-Contrast Outlines** to define hierarchy, maintaining a clean and flat aesthetic.

Hierarchy is established by:
- **Level 0 (Background):** The base surface (usually white or off-white).
- **Level 1 (Cards/Panels):** A slightly tinted surface with a 1px solid border to define boundaries. Shadows are minimal to non-existent.
- **Level 2 (Modals/Popovers):** Bright white surfaces utilizing soft, light ambient shadows to suggest floating above the workspace.
- **AI Focus:** Elements generated or highlighted by AI use a subtle Primary Orange glow or a light orange tinted background to signify "active intelligence" against the neutral background.

## Shapes
A consistent "Pill-shaped" theme is applied to humanize the data-heavy environment and provide a friendly contrast to structured technical data.
- **Base Components:** Buttons and Input fields use a 1rem (16px) radius.
- **Containers:** Large workspace cards and chat bubbles use a 2rem (32px) radius.
- **Tags/Chips:** Fully pill-shaped to contrast against the structured grid of the data tables.
- **Icons:** Use "Line" style icons with rounded terminals to match the font weight of Inter.

## Components
- **Buttons:** Primary buttons use a solid Primary Orange fill with high-contrast (white) text and a 1rem radius. Secondary buttons use a transparent background with a 1px dark-gray border. "Ghost" buttons are used for utility actions in the toolbar.
- **AI Chat Input:** A floating container with a 24px+ corner radius, featuring a distinct Primary Orange "Send" button and Geist-font placeholder text to signal the AI interface.
- **Data Cards:** Modules containing visualizations should have a 1px border and 2rem corner radius. The header of the card should use a Geist-font label in all-caps (label-sm).
- **Status Chips:** Use desaturated versions of primary colors with a fully pill-shaped profile.
- **Checkboxes/Radios:** Use the Primary Orange for the checked state to ensure the user's focus is captured immediately on selection.
- **Interactive Lists:** List items should feature a subtle hover state with a 4px left-accent border in Primary Orange when selected.