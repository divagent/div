// main: "#F28500",

/**
 * Design System: Editorial Finance - "The Warm Architect"
 * 
 * A high-end editorial experience rejecting the "cold calculator" aesthetic
 * Uses warm neutrals and vibrant oranges for approachable, authoritative feel
 */

// ============================================
// 1. Primary Colors - The "Solar" Palette
// ============================================

export const primary = {
    /** Deep, grounding orange - used for hover states and heavy emphasis */
    main: '#904d00',
    /** Vibrant, sun-drenched orange - used for primary CTAs and accent elements */
    container: '#f28500',
    /** Darkest shade for text on primary backgrounds */
    onPrimaryContainer: '#582d00',
} as const;

// ============================================
// 2. Surface Colors - Tonal Layering
// ============================================

export const surface = {
    /** Base background - warm off-white "living" neutral */
    base: '#fcf9f5',
    /** Low container - for sections and subtle separation (no borders!) */
    containerLow: '#f6f3ef',
    /** Highest container - for input fields and interactive elements */
    containerHighest: '#e5e2de',
    /** Lightest container - for cards and elevated elements (pure white) */
    containerLowest: '#ffffff',
    /** Dimmed variant - for background utility areas */
    dim: '#dcdad6',
} as const;

// ============================================
// 3. Text Colors - Editorial Hierarchy
// ============================================

export const text = {
    /** Primary text color - darkest neutral for critical data */
    primary: '#1c1c19',
    /** Secondary text color - softer for supporting information */
    secondary: '#564335',
    /** Tertiary text color - for disabled or very low emphasis */
    tertiary: '#8b7a6b',
} as const;

// ============================================
// 4. Border & Outline - "Ghost Border" System
// ============================================

export const outline = {
    /** Default outline variant - subtle, almost invisible stroke */
    variant: '#dcc1ae',
    /** Ghost border for secondary buttons and subtle separation */
    ghost: 'rgba(220, 193, 174, 0.2)',
    /** Ultra-subtle divider - 15% opacity for minimal visual noise */
    divider: 'rgba(220, 193, 174, 0.15)',
} as const;

// ============================================
// 5. Status Colors - Sophisticated Feedback
// ============================================

export const status = {
    /** Success/verified state - cool blue for contrast against warm orange */
    success: '#006496',
    /** Error container - soft, less alarming red */
    errorContainer: '#ffdad6',
    /** Text color for error states */
    onErrorContainer: '#8b3a2e',
} as const;

// ============================================
// 6. Gradients - The "Solar Gradient" Signature
// ============================================

export const gradients = {
    /** Primary CTA gradient - adds physical "soul" to buttons */
    primary: 'linear-gradient(135deg, #904d00 0%, #f28500 100%)',
    /** Optional secondary gradient for subtle accents */
    secondary: 'linear-gradient(135deg, #f6f3ef 0%, #ffffff 100%)',
} as const;

// ============================================
// 7. Shadows - "Sunlight Shadow" System
// ============================================

export const shadows = {
    /** Soft ambient shadow - looks like a soft hum of light */
    ambient: {
        boxShadow: '0 8px 32px rgba(28, 28, 25, 0.06)',
        blur: '32px',
        yOffset: '8px',
        color: 'rgba(28, 28, 25, 0.06)',
    },
    /** Card elevation - subtle lift for interactive elements */
    card: '0 4px 16px rgba(28, 28, 25, 0.04), 0 1px 2px rgba(28, 28, 25, 0.02)',
    /** Modal/dropdown - deeper shadow for floating elements */
    elevated: '0 20px 40px rgba(28, 28, 25, 0.08), 0 4px 12px rgba(28, 28, 25, 0.04)',
} as const;

// ============================================
// 8. Border Radius - Architectural Edges
// ============================================

export const radius = {
    /** Small radius - for buttons and compact elements */
    sm: '0.375rem', // 6px
    /** Medium radius - for cards and containers */
    md: '0.5rem',   // 8px
    /** Large radius - for modals and panels */
    lg: '0.75rem',  // 12px
    /** Full radius - for avatars and circular elements */
    full: '9999px',
} as const;

// ============================================
// 9. Spacing Scale - Premium, Unhurried Layout
// ============================================

export const spacing = {
    0: '0',
    1: '0.25rem',   // 4px
    2: '0.5rem',    // 8px
    3: '0.75rem',   // 12px
    4: '1rem',      // 16px
    5: '1.25rem',   // 20px
    6: '1.5rem',    // 24px
    8: '2rem',      // 32px
    10: '2.5rem',   // 40px
    12: '3rem',     // 48px - major section breaks
    16: '4rem',     // 64px
    20: '5rem',     // 80px
    24: '6rem',     // 96px
} as const;

// ============================================
// 10. Typography - Editorial Scale
// ============================================

export const typography = {
    /** Display/Headline font - clean financial UI stack */
    display: {
        fontFamily: '"IBM Plex Sans", Arial, sans-serif',
        /** Large display - 3.5rem for big financial totals */
        lg: {
            fontSize: '3.5rem',   // 56px
            lineHeight: '1.2',
            fontWeight: 600,
        },
        /** Medium display */
        md: {
            fontSize: '2.5rem',   // 40px
            lineHeight: '1.25',
            fontWeight: 600,
        },
    },
    /** Body/UI font - clean financial UI stack */
    body: {
        fontFamily: '"IBM Plex Sans", Arial, sans-serif',
        /** Large body text */
        lg: {
            fontSize: '1.125rem', // 18px
            lineHeight: '1.5',
            fontWeight: 400,
        },
        /** Medium body text - default */
        md: {
            fontSize: '1rem',     // 16px
            lineHeight: '1.5',
            fontWeight: 400,
        },
        /** Small body text - labels and supporting text */
        sm: {
            fontSize: '0.875rem', // 14px
            lineHeight: '1.5',
            fontWeight: 400,
        },
        /** Extra small - captions and metadata */
        xs: {
            fontSize: '0.75rem',  // 12px
            lineHeight: '1.5',
            fontWeight: 400,
        },
    },
    /** Label text - uppercase tracking for form labels */
    label: {
        fontFamily: '"IBM Plex Sans", Arial, sans-serif',
        fontSize: '0.75rem',    // 12px
        lineHeight: '1.5',
        fontWeight: 500,
        letterSpacing: '0',
        textTransform: 'uppercase' as const,
    },
} as const;

// ============================================
// 11. Glass Effect - Softened Backdrop Blur
// ============================================

export const glass = {
    /** For floating navigation and modals */
    effect: {
        backgroundColor: 'rgba(246, 243, 239, 0.8)', // surface-container-low at 80%
        backdropFilter: 'blur(24px)',
    },
} as const;

// ============================================
// 12. Complete Theme Object
// ============================================

export const theme = {
    colors: {
        primary,
        surface,
        text,
        outline,
        status,
    },
    gradients,
    shadows,
    radius,
    spacing,
    typography,
    glass,
} as const;

// ============================================
// 13. Type Definitions for Theme Usage
// ============================================

export type Theme = typeof theme;
export type PrimaryColor = keyof typeof primary;
export type SurfaceColor = keyof typeof surface;
export type TextColor = keyof typeof text;
export type StatusColor = keyof typeof status;

// ============================================
// 14. Utility Functions
// ============================================

/**
 * Get a specific surface color value
 * @param layer - The surface layer name
 * @returns The hex color value
 */
export const getSurfaceColor = (layer: SurfaceColor): string => {
    return surface[layer];
};

/**
 * Get a specific text color value
 * @param type - The text type
 * @returns The hex color value
 */
export const getTextColor = (type: TextColor): string => {
    return text[type];
};

/**
 * Generate a ghost border style with optional opacity override
 * @param opacity - Optional custom opacity (0-1)
 * @returns CSS border style string
 */
export const ghostBorder = (opacity: number = 0.2): string => {
    return `1px solid rgba(220, 193, 174, ${opacity})`;
};

// ============================================
// 15. Design Tokens Reference (Quick Lookup)
// ============================================

/**
 * Quick reference for common design tokens
 * Use these in inline styles or CSS-in-JS
 */
export const tokens = {
    // Most commonly used colors
    bgPrimary: surface.base,
    bgSection: surface.containerLow,
    bgCard: surface.containerLowest,
    bgInput: surface.containerHighest,

    textPrimary: text.primary,
    textSecondary: text.secondary,

    brandOrange: primary.container,
    brandOrangeDark: primary.main,

    borderSubtle: outline.ghost,
    borderDivider: outline.divider,

    // Common gradients
    ctaGradient: gradients.primary,

    // Common shadows
    cardShadow: shadows.card,
    modalShadow: shadows.elevated,

    // Common radii
    buttonRadius: radius.sm,
    cardRadius: radius.md,
    modalRadius: radius.lg,
} as const;
