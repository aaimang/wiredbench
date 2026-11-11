/**
 * The Trace window's messages and the trace it has read (server/WiredbenchTrace.cs). Kept free of
 * React and the client so plain tests can cover it.
 */

/** Client to server: turn the trace of the room I am in on or off. */
export const TRACE_SET = 'wiredbench.trace.set';

/** Client to server: the steps of the room I am in after `afterId`. */
export const TRACE_READ = 'wiredbench.trace.read';

/** Server to client: the trace state and the steps asked for. */
export const TRACE_STATE = 'wiredbench.trace.state';

/** `WiredTraceStepType`. */
export const STEP = { stack: 0, condition: 1, effect: 2 } as const;

/** `WiredTraceOutcomeType`, by its value. */
export const OUTCOMES = [ 'Passed', 'Failed', 'Stopped', 'Dropped', 'Ran', 'No effect', 'Threw', 'Delayed', 'Cancelled' ] as const;

export interface TraceStep {
    id: number;
    runId: number;
    stackId: number;
    step: number;
    outcome: number;
    boxId: number;
    boxLogic: string;
    boxCode: number;
    detail: string;
}

export interface TraceState {
    roomId: number;
    allowed: boolean;
    enabled: boolean;
    lastId: number;
    steps: TraceStep[];
}

const isNumber = (value: unknown): value is number => typeof value === 'number';

const toStep = (data: unknown): TraceStep | null => {
    if (!data || (typeof data !== 'object')) return null;

    const x = data as Record<string, unknown>;

    if (!isNumber(x.id) || !isNumber(x.runId) || !isNumber(x.stackId) || !isNumber(x.step) || !isNumber(x.outcome) || !isNumber(x.boxId) || !isNumber(x.boxCode)) return null;
    if ((typeof x.boxLogic !== 'string') || (typeof x.detail !== 'string')) return null;

    return { id: x.id, runId: x.runId, stackId: x.stackId, step: x.step, outcome: x.outcome, boxId: x.boxId, boxLogic: x.boxLogic, boxCode: x.boxCode, detail: x.detail };
};

/** `wiredbench.trace.state` as the client hands it over, or null when it is not one. */
export const toTraceState = (data: Record<string, unknown>): TraceState | null => {
    if (!isNumber(data.roomId) || (typeof data.allowed !== 'boolean') || (typeof data.enabled !== 'boolean') || !isNumber(data.lastId) || !Array.isArray(data.steps)) return null;

    const steps = data.steps.map(toStep);

    if (steps.some(x => x === null)) return null;

    return { roomId: data.roomId, allowed: data.allowed, enabled: data.enabled, lastId: data.lastId, steps: steps as TraceStep[] };
};

/** One stack run as the window shows it: its stack line, the conditions asked and the effects. */
export interface TraceRun {
    runId: number;
    stack: TraceStep | null;
    conditions: TraceStep[];
    effects: TraceStep[];
}

/** The steps grouped by run, oldest run first. */
export const toRuns = (steps: readonly TraceStep[]): TraceRun[] => {
    const runs = new Map<number, TraceRun>();

    for (const step of steps) {
        let run = runs.get(step.runId);

        if (!run) {
            run = { runId: step.runId, stack: null, conditions: [], effects: [] };
            runs.set(step.runId, run);
        }

        if (step.step === STEP.stack) run.stack = step;
        else if (step.step === STEP.condition) run.conditions.push(step);
        else run.effects.push(step);
    }

    return [ ...runs.values() ];
};

export const outcomeName = (outcome: number) => OUTCOMES[outcome] ?? `#${ outcome }`;

/** A box as a line names it. */
export const boxName = (step: TraceStep) => (step.boxLogic ? `${ step.boxLogic } #${ step.boxId }` : 'a stack call');

/** What the window keeps: the room's latest steps, at most `MAX_KEPT_STEPS`. */
export const MAX_KEPT_STEPS = 400;

export interface TraceView {
    roomId: number;
    allowed: boolean;
    enabled: boolean;
    lastId: number;
    steps: TraceStep[];
}

export const EMPTY_VIEW: TraceView = { roomId: 0, allowed: false, enabled: false, lastId: 0, steps: [] };

/** The view after a state message: a new room starts over, the same room adds the new steps. */
export const applyState = (view: TraceView, state: TraceState): TraceView => {
    const sameRoom = view.roomId === state.roomId;
    const kept = sameRoom ? view.steps : [];
    const fresh = state.steps.filter(x => !kept.length || (x.id > kept[kept.length - 1].id));
    const steps = [ ...kept, ...fresh ].slice(-MAX_KEPT_STEPS);

    return { roomId: state.roomId, allowed: state.allowed, enabled: state.enabled, lastId: Math.max(sameRoom ? view.lastId : 0, state.lastId), steps };
};

type Listener = (view: TraceView) => void;

/** The trace the window shows, shared by the window and the module's message handler. */
export const traceStore = (() => {
    let current: TraceView = EMPTY_VIEW;
    const listeners = new Set<Listener>();

    const set = (next: TraceView) => {
        current = next;

        for (const listener of listeners) listener(next);
    };

    return {
        get current() {
            return current;
        },
        apply(state: TraceState | null) {
            if (state) set(applyState(current, state));
        },
        /** Forgets the steps shown; the next read starts after the last one the room has. */
        clear() {
            set({ ...current, steps: [] });
        },
        listen(listener: Listener) {
            listeners.add(listener);

            return () => void listeners.delete(listener);
        },
    };
})();
