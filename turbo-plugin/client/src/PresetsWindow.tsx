import { type ClientModuleWindowProps, useApi } from '@nitrodevco/client-module-sdk';
import { Box, Button, Frame, ThemeText } from '@nitrodevco/client-module-sdk/theme';
import { useEffect, useState } from 'react';

import { exportName, PRESETS_DELETE, PRESETS_EXPORT, PRESETS_IMPORT, PRESETS_PICK, PRESETS_READ, presetsStore, type PresetsState } from './presets';
import { BUTTON, TEXT, TINT } from './theme';
import { Hint, IconButton, Section, WindowHeader } from './ui';

const WIDTH = 500;
const HEIGHT = 470;
const PADDING = 12;
const INNER = WIDTH - (PADDING * 2) - 2;
const SECTION_INNER = INNER - 16;
const GAP = 6;
const ACTION_WIDTH = 70;

// The newest presets listed; there is no scrolling, and the panel lists them all.
const SHOWN = 7;

// How often an open window looks for presets added elsewhere (the panel, another player's export).
const REFRESH_EVERY_MS = 10_000;

/**
 * The preset library: import a G-Presets file at a picked tile, on its own tiles or into a new
 * room, export the room, and delete presets. New presets show without reopening the window.
 */
export const PresetsWindow = ({ close }: ClientModuleWindowProps) => {
    const api = useApi();
    const [ state, setState ] = useState<PresetsState>(presetsStore.current);
    const [ busy, setBusy ] = useState(false);
    const [ confirmDelete, setConfirmDelete ] = useState<number | null>(null);

    useEffect(() => {
        const stop = presetsStore.listen(next => {
            setState(next);
            setBusy(false);
        });

        api.messages.send(PRESETS_READ, {});

        const timer = setInterval(() => api.messages.send(PRESETS_READ, {}), REFRESH_EVERY_MS);

        return () => {
            clearInterval(timer);
            stop();
        };
    }, [ api ]);

    const text = (key: string, fallback: string, replacements?: Record<string, string>) => api.texts.get(`wiredbench.presets.${ key }`, fallback, replacements);

    const send = (name: string, data: Record<string, unknown>) => {
        setBusy(true);
        setConfirmDelete(null);
        api.messages.send(name, data);
    };

    const inRoom = !!state.roomId;
    const nameWidth = SECTION_INNER - (ACTION_WIDTH * 3) - (GAP * 4) - (state.canDelete ? 26 + GAP : 0);

    return (
        <Frame
            id={ `${ api.key }-presets` }
            variant="3"
            caption={ text('title', 'Presets') }
            centered
            resizeDirection="none"
            onClose={ close }
            layout={ { width: WIDTH, height: HEIGHT } }>
            <Box layout={ { flexDirection: 'column', gap: 10, padding: PADDING, width: WIDTH - 2 } }>
                <WindowHeader
                    icon="presets"
                    title={ text('header', 'G-Presets') }
                    subtitle={ text('subtitle', '%count% presets in the library', { count: String(state.presets.length) }) }
                    width={ INNER }
                    onIcon={ () => api.windows.open('main') } />
                <Box layout={ { flexDirection: 'row', gap: GAP, alignItems: 'center' } }>
                    <IconButton glyph="icon-refresh" tintColor={ TINT.blue } tooltip={ text('refresh_tip', 'Reload the library') } disabled={ busy } onTap={ () => send(PRESETS_READ, {}) } />
                    <Button variant={ BUTTON.dark } disabled={ busy || !inRoom } tooltip={ text('export_tip', 'Save this room to the library as a G-Presets file') } layout={ { width: 150 } } onPointerTap={ () => send(PRESETS_EXPORT, { name: exportName(state.roomId, new Date()) }) }>
                        <ThemeText text={ text('export', 'Export this room') } />
                    </Button>
                    <Hint text={ text('how', 'Pick tile, then click a floor tile.') } width={ INNER - 150 - 26 - (GAP * 2) } />
                </Box>
                <Section title={ text('library', 'Library') } width={ INNER }>
                    { !state.presets.length && (
                        <Hint text={ text('empty', 'Empty. Add files in the admin panel, or export this room.') } width={ SECTION_INNER } />
                    ) }
                    { state.presets.slice(0, SHOWN).map(preset => (
                        <Box key={ preset.id } layout={ { flexDirection: 'row', gap: GAP, alignItems: 'center', width: SECTION_INNER } }>
                            <Box layout={ { flexDirection: 'column', width: nameWidth } }>
                                <ThemeText text={ preset.name } textStyle="u_bold" textOptions={ { fill: TEXT.title } } />
                                <Hint text={ text('counts', '%furni% furni, %boxes% wired boxes, %at%', { furni: String(preset.furni), boxes: String(preset.boxes), at: preset.savedAt }) } width={ nameWidth } />
                            </Box>
                            <Button variant={ BUTTON.green } disabled={ busy || !inRoom } tooltip={ text('pick_tip', 'Place it at the next floor tile you click') } layout={ { width: ACTION_WIDTH } } onPointerTap={ () => send(PRESETS_PICK, { id: preset.id }) }>
                                <ThemeText text={ text('pick', 'Pick tile') } />
                            </Button>
                            <Button variant={ BUTTON.plain } disabled={ busy || !inRoom } tooltip={ text('same_tiles_tip', 'Place it on the file\'s own tiles') } layout={ { width: ACTION_WIDTH } } onPointerTap={ () => send(PRESETS_IMPORT, { id: preset.id, newRoom: false }) }>
                                <ThemeText text={ text('same_tiles', 'Same tiles') } />
                            </Button>
                            <Button variant={ BUTTON.plain } disabled={ busy } tooltip={ text('new_room_tip', 'Make a new room and import it there') } layout={ { width: ACTION_WIDTH } } onPointerTap={ () => send(PRESETS_IMPORT, { id: preset.id, newRoom: true }) }>
                                <ThemeText text={ text('new_room', 'New room') } />
                            </Button>
                            { state.canDelete && (
                                <IconButton
                                    glyph="icon-delete"
                                    tintColor={ TINT.red }
                                    tooltip={ confirmDelete === preset.id ? text('delete_confirm', 'Click again to delete "%name%"', { name: preset.name }) : text('delete_tip', 'Delete from the library') }
                                    disabled={ busy }
                                    onTap={ () => (confirmDelete === preset.id ? send(PRESETS_DELETE, { id: preset.id }) : setConfirmDelete(preset.id)) } />
                            ) }
                        </Box>
                    )) }
                    { confirmDelete !== null && (
                        <Hint text={ text('delete_again', 'Click the red bin again to delete. It cannot be undone.') } width={ SECTION_INNER } fill={ TEXT.bad } />
                    ) }
                </Section>
                { (busy || state.message) && (
                    <ThemeText
                        text={ busy ? text('working', 'Working...') : state.message }
                        textStyle="u_bold"
                        textOptions={ { wordWrap: true, wordWrapWidth: INNER } } />
                ) }
            </Box>
        </Frame>
    );
};
