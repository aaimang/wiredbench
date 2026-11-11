import { type ClientModuleWindowProps, useApi } from '@nitrodevco/client-module-sdk';
import { Box, Button, Frame, ThemeText } from '@nitrodevco/client-module-sdk/theme';
import { useEffect, useState } from 'react';

import { SANDBOX_KIT, SANDBOX_READ, SANDBOX_RESET, SANDBOX_SAVE, sandboxStore, type SandboxState } from './sandbox';

const WIDTH = 320;
const HEIGHT = 330;

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

    return (
        <Frame
            id={ `${ api.key }-sandbox` }
            variant="3"
            caption={ text('title', 'Sandbox') }
            centered
            resizeDirection="none"
            onClose={ close }
            layout={ { width: WIDTH, height: HEIGHT } }>
            <Box layout={ { flexDirection: 'column', gap: 8, padding: 10, width: WIDTH - 2 } }>
                <ThemeText text={ status } textStyle="u_bold" textOptions={ { wordWrap: true, wordWrapWidth: WIDTH - 24 } } />
                <Box layout={ { flexDirection: 'row', gap: 6 } }>
                    <Button variant="101" disabled={ !canBuild } onPointerTap={ () => send(SANDBOX_SAVE, {}) }>
                        <ThemeText text={ text('save', 'Save room') } textStyle="u_regular" />
                    </Button>
                    <Button variant="101" disabled={ !canBuild || !state.hasSaved } onPointerTap={ () => send(SANDBOX_RESET, { putBackPickedUp: putBack }) }>
                        <ThemeText text={ text('reset', 'Reset room') } textStyle="u_regular" />
                    </Button>
                </Box>
                <Button variant="101" disabled={ !canBuild || !state.hasSaved } onPointerTap={ () => setPutBack(!putBack) }>
                    <ThemeText
                        text={ putBack
                            ? text('put_back_on', '[x] Reset also places picked-up furni from your inventory')
                            : text('put_back_off', '[ ] Reset also places picked-up furni from your inventory') }
                        textStyle="u_regular" />
                </Button>
                { state.canTakeKits && (
                    <>
                        <ThemeText text={ text('kits', 'Wired kits (one of each, to your inventory):') } textStyle="u_regular" />
                        <Box layout={ { flexDirection: 'row', flexWrap: 'wrap', gap: 6, width: WIDTH - 22 } }>
                            { state.kits.map(kit => (
                                <Button key={ kit.kind } variant="101" disabled={ busy || !kit.count } onPointerTap={ () => send(SANDBOX_KIT, { kind: kit.kind }) }>
                                    <ThemeText text={ `${ text(`kit.${ kit.kind }`, kit.kind) } (${ kit.count })` } textStyle="u_regular" />
                                </Button>
                            )) }
                        </Box>
                    </>
                ) }
                { (busy || state.message) && (
                    <ThemeText
                        text={ busy ? text('working', 'Working...') : state.message }
                        textStyle="u_regular"
                        textOptions={ { wordWrap: true, wordWrapWidth: WIDTH - 24 } } />
                ) }
            </Box>
        </Frame>
    );
};
