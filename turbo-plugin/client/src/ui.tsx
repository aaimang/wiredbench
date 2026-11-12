/**
 * The parts every Wiredbench window is built from, so the windows read alike: a header with the
 * window's icon, title and subtitle, labelled sections, hints under actions, and icon buttons.
 * Pictures are drawn with the theme's `RichText` (the module's own files, `assetUrl`).
 */
import { assetUrl } from '@nitrodevco/client-module-sdk';
import { Box, Button, type ClientModulePointerHandler, Region, RichText, ThemeText } from '@nitrodevco/client-module-sdk/theme';
import type { ReactNode } from 'react';

import { BUTTON, SECTION_BACKGROUND, TEXT } from './theme';

/** One of the module's pictures (wwwroot/<name>.png) at <size> pixels. */
export const Icon = ({ name, size = 32 }: { name: string; size?: number }) => (
    <RichText
        html={ `<img src="${ assetUrl(`${ name }.png`) }" width="${ size }" height="${ size }">` }
        width={ size } />
);

const HEADER_ICON = 32;

/**
 * A window's header: its icon (pressing it does `onIcon`, opening the Wiredbench window from the
 * others), its title in capitals and a line saying what it is about.
 */
export const WindowHeader = ({ icon, title, subtitle, width, onIcon }: { icon: string; title: string; subtitle?: string; width: number; onIcon?: ClientModulePointerHandler }) => (
    <Box layout={ { flexDirection: 'row', gap: 10, alignItems: 'center', width } }>
        { /* Sized itself: the picture's RichText gives the row no width, so the title sat on it. */ }
        <Box layout={ { width: HEADER_ICON, height: HEADER_ICON, flexShrink: 0 } } onPointerTap={ onIcon }>
            <Icon name={ icon } size={ HEADER_ICON } />
        </Box>
        <Box layout={ { flexDirection: 'column', gap: 2, width: width - 42 } }>
            <ThemeText text={ title.toUpperCase() } textStyle="u_bold" textOptions={ { fill: TEXT.title, fontSize: 13 } } />
            { subtitle && (
                <ThemeText text={ subtitle } textStyle="u_regular" textOptions={ { fill: TEXT.hint, wordWrap: true, wordWrapWidth: width - 42 } } />
            ) }
        </Box>
    </Box>
);

/** A labelled part of a window, on a shade of its own. */
export const Section = ({ title, width, children }: { title: string; width: number; children: ReactNode }) => (
    <Region backgroundColor={ SECTION_BACKGROUND } layout={ { flexDirection: 'column', gap: 6, padding: 8, width } }>
        <ThemeText text={ title.toUpperCase() } textStyle="u_bold" textOptions={ { fill: TEXT.section, fontSize: 10 } } />
        { children }
    </Region>
);

/** A short line under an action saying what it does. */
export const Hint = ({ text, width, fill = TEXT.hint }: { text: string; width: number; fill?: string }) => (
    <ThemeText text={ text } textStyle="u_regular" textOptions={ { fill, fontSize: 10, wordWrap: true, wordWrapWidth: width } } />
);

/** A small square button showing one of the module's white glyphs (icon-delete, icon-refresh). */
export const IconButton = ({ glyph, tooltip, tintColor, disabled, onTap }: { glyph: string; tooltip: string; tintColor?: string; disabled?: boolean; onTap: () => void }) => (
    <Button variant={ BUTTON.shiny } tintColor={ tintColor } tooltip={ tooltip } disabled={ disabled } layout={ { width: 26 } } onPointerTap={ onTap }>
        <Icon name={ glyph } size={ 14 } />
    </Button>
);
