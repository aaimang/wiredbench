import { type ClientModuleWindowProps, useApi } from '@nitrodevco/client-module-sdk';
import { Box, Button, Frame, ThemeText } from '@nitrodevco/client-module-sdk/theme';
import { useEffect, useState } from 'react';

import { SANDBOX_KIT, SANDBOX_READ, SANDBOX_RESET, SANDBOX_SAVE, sandboxStore, type SandboxState } from './sandbox';
import { BUTTON, TEXT } from './theme';
import { Hint, Section, WindowHeader } from './ui';

const WIDTH = 360;
const HEIGHT = 440;
const PADDING = 12;
const INNER = WIDTH - (PADDING * 2) - 2;
const SECTION_INNER = INNER - 16;
const GAP = 6;
const HALF = Math.floor((SECTION_INNER - GAP) / 2);

/** A kit's name when the hotel's texts do not have it, singular and plural. */
const KIT_LABELS: Record<string, [ string, string ]> = {
    triggers: [ 'trigger', 'triggers' ],
    effects: [ 'effect', 'effects' ],
    conditions: [ 'condition', 'conditions' ],
    selectors: [ 'selector', 'selectors' ],
    addons: [ 'add-on', 'add-ons' ],
    variables: [ 'variable', 'variables' ],
    furni: [ 'wired furni', 'wired furni' ],
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

    const subtitle = !state.roomId
        ? text('no_room', 'Enter a room to use it as a sandbox.')
        : !state.allowed
            ? text('not_allowed', 'You may not change the wired of room %room%.', { room: String(state.roomId) })
            : text('subtitle', 'Room %room%: build, save, test, reset.', { room: String(state.roomId) });

    const saved = state.hasSaved
        ? text('saved', '%count% furni saved, %at%', { count: String(state.savedItems), at: state.savedAt })
        : text('not_saved', 'Nothing saved yet');

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
                <WindowHeader icon="sandbox" title={ text('header', 'Sandbox') } subtitle={ subtitle } width={ INNER } onIcon={ () => api.windows.open('main') } />
                <Section title={ text('layout', 'Room layout') } width={ INNER }>
                    <ThemeText text={ saved } textStyle="u_bold" textOptions={ { fill: state.hasSaved ? TEXT.good : TEXT.hint } } />
                    <Box layout={ { flexDirection: 'row', gap: GAP } }>
                        <Box layout={ { flexDirection: 'column', gap: 3, width: HALF } }>
                            <Button variant={ BUTTON.green } disabled={ !canBuild } tooltip={ text('save_tip', 'Store where every floor furni stands, and its state') } layout={ { width: HALF } } onPointerTap={ () => send(SANDBOX_SAVE, {}) }>
                                <ThemeText text={ text('save', 'Save room') } />
                            </Button>
                            <Hint text={ text('save_hint', 'Remember this layout.') } width={ HALF } />
                        </Box>
                        <Box layout={ { flexDirection: 'column', gap: 3, width: HALF } }>
                            <Button variant={ BUTTON.dark } disabled={ !canReset } tooltip={ text('reset_tip', 'Move, turn and switch furni back as saved') } layout={ { width: HALF } } onPointerTap={ () => send(SANDBOX_RESET, { putBackPickedUp: putBack }) }>
                                <ThemeText text={ text('reset', 'Reset room') } />
                            </Button>
                            <Hint text={ text('reset_hint', 'Put it back after a test.') } width={ HALF } />
                        </Box>
                    </Box>
                    <Box layout={ { flexDirection: 'row', gap: 8, alignItems: 'center' } }>
                        <Button variant={ BUTTON.plain } disabled={ !canReset } tooltip={ text('put_back_tip', 'Also place saved furni you picked up, from your inventory') } layout={ { width: 22 } } onPointerTap={ () => setPutBack(!putBack) }>
                            <ThemeText text={ putBack ? 'x' : ' ' } />
                        </Button>
                        <Hint text={ text('put_back', 'Reset also places furni I picked up') } width={ SECTION_INNER - 30 } fill={ TEXT.title } />
                    </Box>
                </Section>
                { state.canTakeKits && (
                    <Section title={ text('kits', 'Wired kits') } width={ INNER }>
                        <Hint text={ text('kits_hint', 'One of each box, to your inventory.') } width={ SECTION_INNER } />
                        <Box layout={ { flexDirection: 'row', flexWrap: 'wrap', gap: GAP, width: SECTION_INNER } }>
                            { state.kits.map(kit => {
                                const [ one, many ] = KIT_LABELS[kit.kind] ?? [ kit.kind, kit.kind ];
                                const label = text(`kit.${ kit.kind }`, `%count% ${ kit.count === 1 ? one : many }`, { count: String(kit.count) });

                                return (
                                    <Button
                                        key={ kit.kind }
                                        variant={ BUTTON.plain }
                                        disabled={ busy || !kit.count }
                                        tooltip={ text('kit_tip', 'Give me %count% %kind%, one of each', { count: String(kit.count), kind: many }) }
                                        layout={ { width: HALF } }
                                        onPointerTap={ () => send(SANDBOX_KIT, { kind: kit.kind }) }>
                                        <ThemeText text={ label } />
                                    </Button>
                                );
                            }) }
                        </Box>
                    </Section>
                ) }
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
