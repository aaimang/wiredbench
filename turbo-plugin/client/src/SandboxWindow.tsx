import { type ClientModuleWindowProps, useApi } from '@nitrodevco/client-module-sdk';
import { Box, Button, Frame, ThemeText } from '@nitrodevco/client-module-sdk/theme';
import { useEffect, useState } from 'react';

import { SANDBOX_KIT, SANDBOX_READ, SANDBOX_RESET, SANDBOX_SAVE, sandboxStore, type SandboxState } from './sandbox';
import { BUTTON } from './theme';

const WIDTH = 340;
const HEIGHT = 330;
const PADDING = 12;
const INNER = WIDTH - (PADDING * 2) - 2;
const KIT_COLUMNS = 2;
const GAP = 6;
const KIT_WIDTH = Math.floor((INNER - (GAP * (KIT_COLUMNS - 1))) / KIT_COLUMNS);

/** A kit's name when the hotel's texts do not have it. */
const KIT_LABELS: Record<string, string> = {
    triggers: 'Triggers',
    effects: 'Effects',
    conditions: 'Conditions',
    selectors: 'Selectors',
    addons: 'Add-ons',
    variables: 'Variables',
    furni: 'Wired furni',
};

/**
 * The sandbox of the room the player is in: save it as built, put it back after a test, and take
 * kits of wired furni.
 */
export const SandboxWindow = ({ close }: ClientModuleWindowProps) => {
    const api = useApi();
    const [ state, setState ] = useState<SandboxState>(sandboxStore.current);
    const [ busy, setBusy ] = useState(false);
    const [ putBack, setPutBack ] = useState(false);

    useEffect(() => {
        const stop = sandboxStore.listen(next => {
            setState(next);
            setBusy(false);
        });

        api.messages.send(SANDBOX_READ, {});

        return stop;
    }, [ api ]);

    const text = (key: string, fallback: string, replacements?: Record<string, string>) => api.texts.get(`wiredbench.sandbox.${ key }`, fallback, replacements);

    const send = (name: string, data: Record<string, unknown>) => {
        setBusy(true);
        api.messages.send(name, data);
    };

    const status = !state.roomId
        ? text('no_room', 'Enter a room to use it as a sandbox.')
        : !state.allowed
            ? text('not_allowed', 'You may not change the wired of this room.')
            : state.hasSaved
                ? text('saved', 'Saved %at%: %count% furni.', { at: state.savedAt, count: String(state.savedItems) })
                : text('not_saved', 'Not saved yet. Build the room, then save it.');

    const canBuild = !busy && !!state.roomId && state.allowed;
    const canReset = canBuild && state.hasSaved;

    return (
        <Frame
            id={ `${ api.key }-sandbox` }
            variant="3"
            caption={ text('title', 'Sandbox') }
            centered
            resizeDirection="none"
            onClose={ close }
            layout={ { width: WIDTH, height: HEIGHT } }>
            <Box layout={ { flexDirection: 'column', gap: 10, padding: PADDING, width: WIDTH - 2 } }>
                <ThemeText text={ status } textStyle="u_bold" textOptions={ { wordWrap: true, wordWrapWidth: INNER } } />
                <Box layout={ { flexDirection: 'row', gap: GAP } }>
                    <Button variant={ BUTTON.green } disabled={ !canBuild } layout={ { width: KIT_WIDTH } } onPointerTap={ () => send(SANDBOX_SAVE, {}) }>
                        <ThemeText text={ text('save', 'Save room') } />
                    </Button>
                    <Button variant={ BUTTON.dark } disabled={ !canReset } layout={ { width: KIT_WIDTH } } onPointerTap={ () => send(SANDBOX_RESET, { putBackPickedUp: putBack }) }>
                        <ThemeText text={ text('reset', 'Reset room') } />
                    </Button>
                </Box>
                <Box layout={ { flexDirection: 'row', gap: 8, alignItems: 'center' } }>
                    <Button variant={ BUTTON.plain } disabled={ !canReset } layout={ { width: 22 } } onPointerTap={ () => setPutBack(!putBack) }>
                        <ThemeText text={ putBack ? 'x' : ' ' } />
                    </Button>
                    <ThemeText
                        text={ text('put_back', 'Reset also places furni I picked up') }
                        textStyle="u_regular"
                        textOptions={ { wordWrap: true, wordWrapWidth: INNER - 30 } } />
                </Box>
                { state.canTakeKits && (
                    <Box layout={ { flexDirection: 'column', gap: GAP, marginTop: 4 } }>
                        <ThemeText text={ text('kits', 'Wired kits: one of each, to your inventory') } textStyle="u_bold" />
                        <Box layout={ { flexDirection: 'row', flexWrap: 'wrap', gap: GAP, width: INNER } }>
                            { state.kits.map(kit => (
                                <Button
                                    key={ kit.kind }
                                    variant={ BUTTON.plain }
                                    disabled={ busy || !kit.count }
                                    layout={ { width: KIT_WIDTH } }
                                    onPointerTap={ () => send(SANDBOX_KIT, { kind: kit.kind }) }>
                                    <ThemeText text={ `${ text(`kit.${ kit.kind }`, KIT_LABELS[kit.kind] ?? kit.kind) } (${ kit.count })` } />
                                </Button>
                            )) }
                        </Box>
                    </Box>
                ) }
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
