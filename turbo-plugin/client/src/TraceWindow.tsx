import { type ClientModuleWindowProps, useApi } from '@nitrodevco/client-module-sdk';
import { Box, Button, Frame, ThemeText } from '@nitrodevco/client-module-sdk/theme';
import { useEffect, useState } from 'react';

import { BUTTON } from './theme';
import { boxName, outcomeName, toRuns, TRACE_READ, TRACE_SET, type TraceStep, traceStore, type TraceView } from './trace';

const WIDTH = 460;
const HEIGHT = 380;

// How often the window asks for the steps after the last one it has.
const READ_EVERY_MS = 1000;

// The newest runs the window lists; there is no scrolling, so the rest are left off.
const SHOWN_RUNS = 8;

const COLORS: Record<string, string> = {
    Passed: '#2e7d32',
    Ran: '#2e7d32',
    Failed: '#c62828',
    Threw: '#c62828',
    Stopped: '#e65100',
    Dropped: '#e65100',
    Cancelled: '#e65100',
};

const escape = (text: string) => text.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');

const outcome = (step: TraceStep) => {
    const name = outcomeName(step.outcome);

    return `<font color="${ COLORS[name] ?? '#616161' }">${ name }</font>`;
};

const listed = (steps: TraceStep[]) => steps.map(x => `${ escape(boxName(x)) } ${ outcome(x) }${ x.detail ? ` (${ escape(x.detail) })` : '' }`).join(', ');

/** The trace as markup: the newest runs, newest first, each with its conditions and effects. */
const toMarkup = (view: TraceView) => toRuns(view.steps)
    .slice(-SHOWN_RUNS)
    .reverse()
    .map(run => {
        const head = run.stack
            ? `<b>#${ run.runId }</b> stack ${ run.stack.stackId } by ${ escape(boxName(run.stack)) }: ${ outcome(run.stack) }${ run.stack.detail ? `, ${ escape(run.stack.detail) }` : '' }`
            : `<b>#${ run.runId }</b>`;
        const lines = [ head ];

        if (run.conditions.length) lines.push(`&nbsp;&nbsp;if ${ listed(run.conditions) }`);
        if (run.effects.length) lines.push(`&nbsp;&nbsp;then ${ listed(run.effects) }`);

        return lines.join('<br>');
    })
    .join('<br>');

/** The wired trace of the room the player is in: turn it on, then watch each stack run. */
export const TraceWindow = ({ close }: ClientModuleWindowProps) => {
    const api = useApi();
    const [ view, setView ] = useState<TraceView>(traceStore.current);

    useEffect(() => {
        const stop = traceStore.listen(setView);

        api.messages.send(TRACE_READ, { afterId: 0 });

        const timer = setInterval(() => api.messages.send(TRACE_READ, { afterId: traceStore.current.lastId }), READ_EVERY_MS);

        return () => {
            clearInterval(timer);
            stop();
        };
    }, [ api ]);

    const text = (key: string, fallback: string, replacements?: Record<string, string>) => api.texts.get(`wiredbench.trace.${ key }`, fallback, replacements);

    const status = !view.roomId
        ? text('no_room', 'Enter a room to trace its wired.')
        : !view.allowed
            ? text('not_allowed', 'You may not read the wired of this room.')
            : view.enabled
                ? text('on', 'Tracing room %room%. Fire a stack to see it here.', { room: String(view.roomId) })
                : text('off', 'The trace of room %room% is off.', { room: String(view.roomId) });

    const markup = toMarkup(view);

    return (
        <Frame
            id={ `${ api.key }-trace` }
            variant="3"
            caption={ text('title', 'Wired trace') }
            centered
            resizeDirection="none"
            onClose={ close }
            layout={ { width: WIDTH, height: HEIGHT } }>
            <Box layout={ { flexDirection: 'column', gap: 10, padding: 12, width: WIDTH - 2 } }>
                <Box layout={ { flexDirection: 'row', gap: 6, alignItems: 'center' } }>
                    <Button
                        variant={ view.enabled ? BUTTON.dark : BUTTON.green }
                        layout={ { width: 80 } }
                        disabled={ !view.roomId || !view.allowed }
                        onPointerTap={ () => api.messages.send(TRACE_SET, { enabled: !view.enabled }) }>
                        <ThemeText text={ view.enabled ? text('turn_off', 'Stop') : text('turn_on', 'Start') } />
                    </Button>
                    <Button variant={ BUTTON.plain } layout={ { width: 80 } } onPointerTap={ () => traceStore.clear() }>
                        <ThemeText text={ text('clear', 'Clear') } />
                    </Button>
                </Box>
                <ThemeText text={ status } textStyle="u_bold" />
                <ThemeText
                    text={ markup || text('empty', 'No stack has run since.') }
                    markup={ !!markup }
                    textStyle="u_regular"
                    textOptions={ { wordWrap: true, wordWrapWidth: WIDTH - 24 } } />
            </Box>
        </Frame>
    );
};
