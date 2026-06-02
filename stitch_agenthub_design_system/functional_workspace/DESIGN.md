---
name: Functional Workspace
colors:
  surface: '#f9f9f8'
  surface-dim: '#dadad9'
  surface-bright: '#f9f9f8'
  surface-container-lowest: '#ffffff'
  surface-container-low: '#f3f4f3'
  surface-container: '#eeeeed'
  surface-container-high: '#e8e8e7'
  surface-container-highest: '#e2e2e2'
  on-surface: '#1a1c1c'
  on-surface-variant: '#58423b'
  inverse-surface: '#2f3130'
  inverse-on-surface: '#f1f1f0'
  outline: '#8b7169'
  outline-variant: '#dfc0b6'
  surface-tint: '#a73a0e'
  primary: '#a3380b'
  on-primary: '#ffffff'
  primary-container: '#c54f23'
  on-primary-container: '#fffbff'
  inverse-primary: '#ffb59c'
  secondary: '#5f5e5e'
  on-secondary: '#ffffff'
  secondary-container: '#e2dfde'
  on-secondary-container: '#636262'
  tertiary: '#006577'
  on-tertiary: '#ffffff'
  tertiary-container: '#008096'
  on-tertiary-container: '#f9fdff'
  error: '#ba1a1a'
  on-error: '#ffffff'
  error-container: '#ffdad6'
  on-error-container: '#93000a'
  primary-fixed: '#ffdbcf'
  primary-fixed-dim: '#ffb59c'
  on-primary-fixed: '#390c00'
  on-primary-fixed-variant: '#832700'
  secondary-fixed: '#e5e2e1'
  secondary-fixed-dim: '#c8c6c5'
  on-secondary-fixed: '#1c1b1b'
  on-secondary-fixed-variant: '#474746'
  tertiary-fixed: '#acecff'
  tertiary-fixed-dim: '#61d5f2'
  on-tertiary-fixed: '#001f26'
  on-tertiary-fixed-variant: '#004e5c'
  background: '#f9f9f8'
  on-background: '#1a1c1c'
  surface-variant: '#e2e2e2'
typography:
  display:
    fontFamily: Inter
    fontSize: 32px
    fontWeight: '600'
    lineHeight: 40px
    letterSpacing: -0.02em
  headline-lg:
    fontFamily: Inter
    fontSize: 24px
    fontWeight: '600'
    lineHeight: 32px
    letterSpacing: -0.01em
  headline-md:
    fontFamily: Inter
    fontSize: 20px
    fontWeight: '600'
    lineHeight: 28px
    letterSpacing: -0.01em
  title-lg:
    fontFamily: Inter
    fontSize: 18px
    fontWeight: '500'
    lineHeight: 26px
  body-lg:
    fontFamily: Inter
    fontSize: 16px
    fontWeight: '400'
    lineHeight: 24px
  body-md:
    fontFamily: Inter
    fontSize: 14px
    fontWeight: '400'
    lineHeight: 20px
  label-md:
    fontFamily: Inter
    fontSize: 12px
    fontWeight: '500'
    lineHeight: 16px
    letterSpacing: 0.01em
  label-sm:
    fontFamily: Inter
    fontSize: 11px
    fontWeight: '600'
    lineHeight: 14px
rounded:
  sm: 0.25rem
  DEFAULT: 0.5rem
  md: 0.75rem
  lg: 1rem
  xl: 1.5rem
  full: 9999px
spacing:
  base: 4px
  xs: 4px
  sm: 8px
  md: 16px
  lg: 24px
  xl: 32px
  gutter: 20px
  margin-mobile: 16px
  margin-desktop: 40px
---

## Brand & Style

The design system is centered on **Utility Minimalism**. It prioritizes the cognitive load of knowledge workers by removing visual noise and focusing on task-oriented layouts. The personality is professional, warm, and highly functional. 

The aesthetic draws from contemporary editorial design and high-end productivity tools, utilizing generous whitespace to separate complex data streams. It avoids the typical "tech-blue" palette in favor of a warm, grounded primary accent. The goal is to create an environment that feels like a clean physical desk—orderly, tactile, and ready for deep work.

## Colors

The palette is anchored by an off-white canvas (`#FAFAF9`) to reduce screen glare during long working sessions. Pure white (`#FFFFFF`) is reserved strictly for elevated containers like cards and sidebars to create a clear "layer" hierarchy.

**Primary Orange (#E96A3C)** is the sole driver of action. It is used for primary buttons, active navigation states, and progress indicators. Use it sparingly to ensure its impact remains high.
**Secondary Neutral (#6B6B6B)** is used for metadata, labels, and helper text to ensure the user's primary focus remains on the content.
**Borders (#E5E5E4)** should be used instead of heavy shadows to define structure.

## Typography

This design system utilizes **Inter** exclusively to maintain a systematic and utilitarian feel. The base size is 14px for maximum information density without sacrificing legibility.

- **Headlines:** Use semi-bold weights with slight negative letter-spacing to appear tighter and more authoritative.
- **Body:** Standardized at 14px (`body-md`) for all agent-generated content and user inputs. 
- **Labels:** Small, uppercase labels should be used for categorizing agent types or status tags.
- **Vertical Rhythm:** Always align text to a 4px baseline grid to maintain scannability across multi-agent chat threads.

## Layout & Spacing

The layout follows a **Fixed-Fluid hybrid** model. Navigation and Inspector panels are fixed-width (260px and 320px respectively), while the central collaboration canvas is fluid.

- **Grid:** Use a 12-column grid for the central canvas with a 20px gutter.
- **Padding:** Maintain a consistent 24px (`lg`) padding inside cards and panels.
- **Breakpoints:** 
  - Mobile (<768px): Single column, hidden sidebars via hamburger menu.
  - Tablet (768px - 1280px): Fixed left sidebar, fluid canvas, hidden right inspector.
  - Desktop (>1280px): All panels visible.

## Elevation & Depth

This system avoids traditional shadows to keep the UI feeling "flat" and fast. Depth is communicated through **Tonal Layering**:

1.  **Level 0 (Canvas):** `#FAFAF9` - The background.
2.  **Level 1 (Cards/Panels):** `#FFFFFF` - The workspace. These use a 1px border (`#E5E5E4`).
3.  **Interaction Level:** When hovering over interactive cards, apply a very subtle shadow: `0 1px 2px rgba(0,0,0,0.04)`. This is the only shadow used in the system.

Do not use blurs, glows, or gradients. If a modal is required, use a solid 40% opacity neutral-dark overlay.

## Shapes

The shape language is controlled and geometric. 
- **Cards & Panels:** Use an 8px radius to feel modern but structured.
- **Buttons & Inputs:** Use a slightly tighter 6px radius. This differentiation helps users visually distinguish between "containers" and "actions."
- **Avatars:** Use a 4px radius for Agent avatars to maintain the geometric theme, while human users can use circular (pill) avatars to differentiate between AI and human actors.

## Components

### Buttons
- **Primary:** Background `#E96A3C`, Text `#FFFFFF`, 6px radius. No gradient.
- **Secondary:** Background `#FFFFFF`, Border 1px `#E5E5E4`, Text `#1A1A1A`. 
- **Ghost:** Background transparent, Text `#6B6B6B`, hover state background `#F4F4F3`.

### Input Fields
- **Default:** White background, 1px border `#E5E5E4`, 6px radius.
- **Focus:** Border changes to `#E96A3C` with no outer glow.
- **Placeholder:** Text color `#A3A3A3`.

### Agent Chips
- Small, 4px rounded rectangles with a light neutral background (`#F4F4F3`) and `label-sm` typography. Used to identify which agent is performing a specific task.

### List Items
- Clean 1px bottom border separator. Hover state uses a subtle `#FAFAF9` background shift.

### Cards
- White background, 8px radius, 1px `#E5E5E4` border. No shadow unless in hover state.