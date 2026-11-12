import { type ClientModuleWindowProps, useApi } from '@nitrodevco/client-module-sdk';
import { Box, Button, Frame, ThemeText } from '@nitrodevco/client-module-sdk/theme';
import { useEffect, useState } from 'react';

import { CHECK_RUN, type CheckState, checkStore } from './check';
import { BUTTON, TEXT } from './theme';
import { Hint, Section, WindowHeader } from './ui';

const WIDTH = 400;
const HEIGHT = 470;
const PADDING = 12;
const INNER = WIDTH - (PADDING * 2) - 2;
const SECTION_INNER = INNER - 16;
const TILE_WIDTH = 52;

// The issues listed; there is no scrolling, and errors come first.
const SHOWN = 8;

/**
 * Checks the wired of the room the player is in without running it: stacks that cannot work as
 * built (errors) and usual mistakes (warnings), each with the tile its box stands on.
 */
export const CheckWindow = ({ close }: ClientModuleWindowProps) => {
    const api = useApi();
    const [ state, setState ] = useState<CheckState>(checkStore.current);
    const [ busy, setBusy ] = useState(false);

    useEffect(() => {
        const stop = checkStore.listen(next => {
            setState(next);
            setBusy(false);
        });

        return stop;
    }, []);

    const text = (key: string, fallback: string, replacements?: Record<string, string>) => api.texts.get(`wiredbench.check.${ key }`, fallback, replacements);

    const run = () => {
        setBusy(true);
        api.messages.send(CHECK_RUN, {});
    };

    const checked = !!state.message;
    const hidden = state.issues.length - SHOWN;

    return (
        <Frame
            id={ `${ api.key }-check` }
            variant="3"
            caption={ text('title', 'Check room') }
            centered
            resizeDirection="none"
            onClose={ close }
            layout={ { width: WIDTH, height: HEIGHT } }>
            <Box layout={ { flexDirection: 'column', gap: 10, padding: PADDING, width: WIDTH - 2 } }>
                <WindowHeader
                    icon="check"
                    title={ text('header', 'Check room') }
                    subtitle={ state.roomId ? text('subtitle_room', 'Room %room%: wired that cannot work as built.', { room: String(state.roomId) }) : text('subtitle', 'Wired that cannot work as built, found without running it.') }
                    width={ INNER }
                    onIcon={ () => api.windows.open('main') } />
                <Box layout={ { flexDirection: 'row', gap: 8, alignItems: 'center' } }>
                    <Button variant={ BUTTON.green } disabled={ busy } tooltip={ text('run_tip', 'Read every wired box in this room and check how they fit together') } layout={ { width: 130 } } onPointerTap={ run }>
                        <ThemeText text={ checked ? text('run_again', 'Check again') : text('run', 'Check this room') } />
                    </Button>
                    <ThemeText
                        text={ busy ? text('working', 'Checking...') : state.message }
                        textStyle="u_bold"
                        textOptions={ { wordWrap: true, wordWrapWidth: INNER - 140, fill: !checked || busy ? TEXT.title : state.issues.length ? TEXT.bad : TEXT.good } } />
                </Box>
                <Section title={ text('issues', 'Issues') } width={ INNER }>
                    { !state.issues.length && (
                        <Hint text={ checked ? text('none', 'Nothing found. Every stack can run as built.') : text('how', 'Errors stop a box working. Warnings are usually mistakes, but can be meant.') } width={ SECTION_INNER } />
                    ) }
                    { state.issues.slice(0, SHOWN).map(issue => (
                        <Box key={ `${ issue.boxId }-${ issue.code }` } layout={ { flexDirection: 'row', gap: 6, width: SECTION_INNER } }>
                            <Box layout={ { flexDirection: 'column', width: TILE_WIDTH } }>
                                <ThemeText text={ issue.severity === 'error' ? text('error', 'Error') : text('warning', 'Warning') } textStyle="u_bold" textOptions={ { fill: issue.severity === 'error' ? TEXT.bad : TEXT.section } } />
                                <Hint text={ `${ issue.x }, ${ issue.y }` } width={ TILE_WIDTH } />
                            </Box>
                            <Box layout={ { flexDirection: 'column', width: SECTION_INNER - TILE_WIDTH - 6 } }>
                                <ThemeText text={ issue.logic || text('box', 'Box %id%', { id: String(issue.boxId) }) } textStyle="u_bold" textOptions={ { fill: TEXT.title } } />
                                <Hint text={ issue.message } width={ SECTION_INNER - TILE_WIDTH - 6 } />
                            </Box>
                        </Box>
                    )) }
                    { hidden > 0 && (
                        <Hint text={ text('more', 'And %count% more. Fix these, then check again.', { count: String(hidden) }) } width={ SECTION_INNER } />
                    ) }
                </Section>
            </Box>
        </Frame>
    );
};
