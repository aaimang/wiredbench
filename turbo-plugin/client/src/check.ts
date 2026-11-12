/**
 * The Check window's messages and what it shows (server/RoomCheck.cs). Kept free of React and the
 * client so plain tests can cover it.
 */

/** Client to server: check the wired of the room I am in. */
export const CHECK_RUN = 'wiredbench.check.run';

/** Server to client: the room checked, what was found and a line to show. */
export const CHECK_STATE = 'wiredbench.check.state';

export interface RoomIssue {
    /** `error` when a box cannot work as built, `warning` when it is usually a mistake. */
    severity: string;
    code: string;
    boxId: number;
    logic: string;
    x: number;
    y: number;
    message: string;
}

export interface CheckState {
    /** The room checked; 0 when the player was in none. */
    roomId: number;
    boxes: number;
    issues: RoomIssue[];
    message: string;
}

export const EMPTY_CHECK: CheckState = { roomId: 0, boxes: 0, issues: [], message: '' };

const toIssue = (data: unknown): RoomIssue | null => {
    if (!data || (typeof data !== 'object')) return null;

    const x = data as Record<string, unknown>;

    if ((typeof x.severity !== 'string') || (typeof x.code !== 'string') || (typeof x.boxId !== 'number') || (typeof x.x !== 'number') || (typeof x.y !== 'number') || (typeof x.message !== 'string')) return null;

    return { severity: x.severity, code: x.code, boxId: x.boxId, logic: (typeof x.logic === 'string') ? x.logic : '', x: x.x, y: x.y, message: x.message };
};

/** `wiredbench.check.state` as the client hands it over, or null when it is not one. */
export const toCheckState = (data: Record<string, unknown>): CheckState | null => {
    if ((typeof data.roomId !== 'number') || !Array.isArray(data.issues) || (typeof data.message !== 'string')) return null;

    const issues = data.issues.map(toIssue);

    if (issues.some(x => x === null)) return null;

    return { roomId: data.roomId, boxes: (typeof data.boxes === 'number') ? data.boxes : 0, issues: issues as RoomIssue[], message: data.message };
};

type Listener = (state: CheckState) => void;

/** The last check the plugin sent, shared by the window and the module's handler. */
export const checkStore = (() => {
    let current: CheckState = EMPTY_CHECK;
    const listeners = new Set<Listener>();

    return {
        get current() {
            return current;
        },
        set(next: CheckState | null) {
            if (!next) return;

            current = next;

            for (const listener of listeners) listener(next);
        },
        listen(listener: Listener) {
            listeners.add(listener);

            return () => void listeners.delete(listener);
        },
    };
})();
