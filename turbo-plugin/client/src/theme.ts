/**
 * The look every Wiredbench window shares: the theme's `button` variants (the client's own 22 px
 * Habbo buttons; the `100`-range are Illumina's large ones), the colours that say what a button
 * does, and the text colours of the headers, section labels and hints.
 */
export const BUTTON = {
    /** Grey: the usual button. */
    plain: '0',
    /** Shiny green, white caption: what a window is for (save, start, select, import). */
    green: '6',
    /** Shiny black, white caption: an action that changes a lot at once (reset). */
    dark: '4',
    /** Shiny, white caption; give it `tintColor`: TINT.red for stop and remove. */
    shiny: '5',
} as const;

export const TINT = {
    /** Stop, delete: the Wiredbench mark's red. */
    red: '#c8321e',
    /** Refresh and other harmless actions: the window header's blue, so a white glyph shows. */
    blue: '#2b7aa0',
} as const;

export const TEXT = {
    /** Headers. */
    title: '#1c211c',
    /** A section's label: the mark's red. */
    section: '#b02a17',
    /** Hints and what a number means. */
    hint: '#6b6b6b',
    /** A good result. */
    good: '#2e7d32',
    /** A bad one. */
    bad: '#c62828',
} as const;

/** A section's background: a shade off the window's, so the parts of a window read apart. */
export const SECTION_BACKGROUND = '#ecebe2';
