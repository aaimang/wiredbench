import { type ClientModuleWindowProps, useApi } from '@nitrodevco/client-module-sdk';
import { Box, Button, Frame, ThemeText } from '@nitrodevco/client-module-sdk/theme';
import { useEffect, useState } from 'react';

import { BUTTON, TINT } from './theme';
import { Hint, Section, WindowHeader } from './ui';
import { boxName, outcomeName, toRuns, TRACE_PAUSE, TRACE_READ, TRACE_SET, TRACE_STEP, type TraceStep, traceStore, type TraceView } from './trace';

const WIDTH = 480;
const HEIGHT = 540;
const PADDING = 12;
const INNER = WIDTH - (PADDING * 2) - 2;

// How often the window asks for the steps after the last one it has.
const READ_EVERY_MS = 1000;

// The newest runs the window lists; there is no scrolling, so the rest are left off.
const SHOWN_RUNS = 8;

// The held effects the window lists.
const SHOWN_HELD = 4;

const COLORS: Record<string, string> = {
    Passed: '#2e7d32',
    Ran: '#2e7d32',
    Failed: '#c62828',
    Threw: '#c62828',
    Stopped: '#e65100',
    Dropped: '#e65100',
    Cancelled: '#e65100',
    Held: '#1565c0',
};

const escape = (text: string) => text.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');

const outcome = (step: TraceStep) => {
    const name = outcomeName(step.outcome);

    return `<font color="${ COLORS[name] ?? '#616161' }">${ name }</font>`;
};

const listed = (steps: TraceStep[]) => steps.map(x => `${ escape(boxName(x)) } ${ outcome(x) }${ x.detail ? ` (${ escape(x.detail) })` : '' }`).join(', ');

/** The trace as markup: the newest runs, newest first, each with its time, conditions and effects. */
const toMarkup = (view: TraceView) => toRuns(view.steps)
    .slice(-SHOWN_RUNS)
    .reverse()
    .map(run => {
        const time = run.stack?.time || run.effects[0]?.time || run.conditions[0]?.time;
        const stamp = time ? `<font color="#6b6b6b">[${ time }]</font> ` : '';
        const head = run.stack
            ? `${ stamp }<b>#${ run.runId }</b> stack ${ run.stack.stackId } by ${ escape(boxName(run.stack)) }: ${ outcome(run.stack) }${ run.stack.detail ? `, ${ escape(run.stack.detail) }` : '' }`
            : `${ stamp }<b>#${ run.runId }</b>`;
        const lines = [ head ];

        if (run.conditions.length) lines.push(`&nbsp;&nbsp;<b>if</b> ${ listed(run.conditions) }`);
        if (run.effects.length) lines.push(`&nbsp;&nbsp;<b>then</b> ${ listed(run.effects) }`);

        return lines.join('<br>');
    })
    .join('<br>');

/** What a paused room holds: the effect the next step runs, then the rest, each with its chain's effects left. */
const toHeldMarkup = (view: TraceView) => view.held
    .slice(0, SHOWN_HELD)
    .map((x, i) => `${ i === 0 ? '<b>next</b> ' : '' }${ escape(x.boxLogic ? `${ x.boxLogic } #${ x.boxId }` : 'an effect') } <font color="#6b6b6b">(stack ${ x.stackId }, ${ x.remaining } left)</font>`)
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

    const room = { room: String(view.roomId), name: view.roomName };
    const subtitle = !view.roomId
        ? text('no_room', 'Enter a room to trace its wired.')
        : !view.allowed
            ? text('not_allowed', 'You may not read the wired of room %room% %name%.', room)
            : view.paused
                ? text('paused', 'Paused room : %room% %name%', room)
            : view.enabled
                ? text('on', 'Tracing room : %room% %name%', room)
                : text('off', 'Trace off for room : %room% %name%', room);

    const markup = toMarkup(view);
    const canTrace = !!view.roomId && view.allowed;

    return (
        <Frame
            id={ `${ api.key }-trace` }
            variant="3"
            caption={ text('title', 'Wired trace') }
            centered
            resizeDirection="none"
            onClose={ close }
            layout={ { width: WIDTH, height: HEIGHT } }>
            <Box layout={ { flexDirection: 'column', gap: 10, padding: PADDING, width: WIDTH - 2 } }>
                <WindowHeader icon="trace" title={ text('header', 'Wired trace') } subtitle={ subtitle } width={ INNER } onIcon={ () => api.windows.open('main') } />
                <Box layout={ { flexDirection: 'row', gap: 6, alignItems: 'center' } }>
                    <Button
                        variant={ view.enabled ? BUTTON.shiny : BUTTON.green }
                        tintColor={ view.enabled ? TINT.red : undefined }
                        tooltip={ view.enabled ? text('turn_off_tip', 'Stop recording this room\'s stacks') : text('turn_on_tip', 'Record every stack run in this room') }
                        layout={ { width: 90 } }
                        disabled={ !canTrace }
                        onPointerTap={ () => api.messages.send(TRACE_SET, { enabled: !view.enabled }) }>
                        <ThemeText text={ view.enabled ? text('turn_off', 'Stop') : text('turn_on', 'Start') } />
                    </Button>
                    <Button variant={ BUTTON.plain } tooltip={ text('clear_tip', 'Empty this list; the room keeps recording') } layout={ { width: 90 } } onPointerTap={ () => traceStore.clear() }>
                        <ThemeText text={ text('clear', 'Clear') } />
                    </Button>
                    { view.timeZone && <Hint text={ text('time_zone', 'Times in %zone%', { zone: view.timeZone }) } width={ INNER - 196 } /> }
                </Box>
                <Box layout={ { flexDirection: 'row', gap: 6, alignItems: 'center' } }>
                    <Button
                        variant={ view.paused ? BUTTON.green : BUTTON.plain }
                        tooltip={ view.paused ? text('resume_tip', 'Run what is held, then let the room run on') : text('pause_tip', 'Hold each stack\'s effects until you step them') }
                        layout={ { width: 90 } }
                        disabled={ !canTrace }
                        onPointerTap={ () => api.messages.send(TRACE_PAUSE, { paused: !view.paused, afterId: view.lastId }) }>
                        <ThemeText text={ view.paused ? text('resume', 'Resume') : text('pause', 'Pause') } />
                    </Button>
                    <Button
                        variant={ BUTTON.plain }
                        tooltip={ text('step_tip', 'Run the next held effect') }
                        layout={ { width: 90 } }
                        disabled={ !canTrace || !view.paused || !view.held.length }
                        onPointerTap={ () => api.messages.send(TRACE_STEP, { count: 1, afterId: view.lastId }) }>
                        <ThemeText text={ text('step', 'Step') } />
                    </Button>
                    { view.paused && <Hint text={ text('held', '%count% held', { count: String(view.held.length) }) } width={ INNER - 196 } /> }
                </Box>
                { view.paused && (
                    <Section title={ text('held_title', 'Held effects') } width={ INNER }>
                        <ThemeText
                            text={ toHeldMarkup(view) || text('held_empty', 'Nothing held. Fire a stack.') }
                            markup={ !!view.held.length }
                            textStyle="u_regular"
                            textOptions={ { wordWrap: true, wordWrapWidth: INNER - 16 } } />
                    </Section>
                ) }
                <Section title={ text('runs', 'Latest stack runs') } width={ INNER }>
                    <ThemeText
                        text={ markup || text('empty', 'No stack has run since.') }
                        markup={ !!markup }
                        textStyle="u_regular"
                        textOptions={ { wordWrap: true, wordWrapWidth: INNER - 16 } } />
                </Section>
            </Box>
        </Frame>
    );
};
