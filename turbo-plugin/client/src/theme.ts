/**
 * The theme's `button` variants the windows use: the client's own 22 px Habbo buttons (the
 * `100`-range are Illumina's large ones). A button's caption takes the variant's text style.
 */
export const BUTTON = {
    /** Grey: the usual button. */
    plain: '0',
    /** Shiny green, white caption: the action a window is for. */
    green: '6',
    /** Shiny black, white caption: an action that changes a lot at once. */
    dark: '4',
} as const;
