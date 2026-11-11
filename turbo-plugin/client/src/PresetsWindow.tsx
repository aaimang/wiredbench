import { type ClientModuleWindowProps, useApi } from '@nitrodevco/client-module-sdk';
import { Box, Button, Frame, ThemeText } from '@nitrodevco/client-module-sdk/theme';
import { useEffect, useState } from 'react';

import { exportName, PRESETS_EXPORT, PRESETS_IMPORT, PRESETS_PICK, PRESETS_READ, presetsStore, type PresetsState } from './presets';
import { BUTTON } from './theme';

const WIDTH = 460;
const HEIGHT = 420;
const PADDING = 12;
const INNER = WIDTH - (PADDING * 2) - 2;
const GAP = 6;
const ACTION_WIDTH = 72;
const ACTIONS = 3;

// The newest presets listed; there is no scrolling, and the panel lists them all.
const SHOWN = 8;

/**
 * The preset library: import a G-Presets file into the room the player is in or a new room, and
 * export the room to the library. Files are added, downloaded and deleted in the admin panel.
 */
export const PresetsWindow = ({ close }: ClientModuleWindowProps) => {
    const api = useApi();
    const [ state, setState ] = useState<PresetsState>(presetsStore.current);
    const [ busy, setBusy ] = useState(false);

    useEffect(() => {
        const stop = presetsStore.listen(next => {
            setState(next);
            setBusy(false);
        });

        api.messages.send(PRESETS_READ, {});

        return stop;
    }, [ api ]);

    const text = (key: string, fallback: string, replacements?: Record<string, string>) => api.texts.get(`wiredbench.presets.${ key }`, fallback, replacements);

    const send = (name: string, data: Record<string, unknown>) => {
        setBusy(true);
        api.messages.send(name, data);
    };

    const inRoom = !!state.roomId;

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
                <ThemeText
                    text={ text('body', 'G-Presets files from the library. Pick tile places a preset at the next floor tile you click, as G-Presets does; Same tiles uses the file\'s own tiles; New room makes a room from its floor plan.') }
                    textStyle="u_regular"
                    textOptions={ { wordWrap: true, wordWrapWidth: INNER } } />
                <Box layout={ { flexDirection: 'column', gap: GAP } }>
                    { !state.presets.length && (
                        <ThemeText text={ text('empty', 'The library is empty. Add files in the admin panel, or export this room.') } textStyle="u_regular" textOptions={ { wordWrap: true, wordWrapWidth: INNER } } />
                    ) }
                    { state.presets.slice(0, SHOWN).map(preset => (
                        <Box key={ preset.id } layout={ { flexDirection: 'row', gap: GAP, alignItems: 'center', width: INNER } }>
                            <Box layout={ { flexDirection: 'column', width: INNER - (ACTION_WIDTH * ACTIONS) - (GAP * ACTIONS) } }>
                                <ThemeText text={ preset.name } textStyle="u_bold" />
                                <ThemeText text={ text('counts', '%furni% furni, %boxes% wired', { furni: String(preset.furni), boxes: String(preset.boxes) }) } textStyle="u_regular" />
                            </Box>
                            <Button variant={ BUTTON.green } disabled={ busy || !inRoom } layout={ { width: ACTION_WIDTH } } onPointerTap={ () => send(PRESETS_PICK, { id: preset.id }) }>
                                <ThemeText text={ text('pick', 'Pick tile') } />
                            </Button>
                            <Button variant={ BUTTON.plain } disabled={ busy || !inRoom } layout={ { width: ACTION_WIDTH } } onPointerTap={ () => send(PRESETS_IMPORT, { id: preset.id, newRoom: false }) }>
                                <ThemeText text={ text('same_tiles', 'Same tiles') } />
                            </Button>
                            <Button variant={ BUTTON.plain } disabled={ busy } layout={ { width: ACTION_WIDTH } } onPointerTap={ () => send(PRESETS_IMPORT, { id: preset.id, newRoom: true }) }>
                                <ThemeText text={ text('new_room', 'New room') } />
                            </Button>
                        </Box>
                    )) }
                </Box>
                <Button variant={ BUTTON.dark } disabled={ busy || !inRoom } layout={ { width: 160 } } onPointerTap={ () => send(PRESETS_EXPORT, { name: exportName(state.roomId, new Date()) }) }>
                    <ThemeText text={ text('export', 'Export this room') } />
                </Button>
                { (busy || state.message) && (
                    <ThemeText
                        text={ busy ? text('working', 'Working...') : state.message }
                        textStyle="u_regular"
                        textOptions={ { wordWrap: true, wordWrapWidth: INNER } } />
                ) }
            </Box>
        </Frame>
    );
};
