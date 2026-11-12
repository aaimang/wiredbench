/**
 * The Sandbox window's messages and the state it shows (server/WiredbenchSandbox.cs). Kept free of
 * React and the client so plain tests can cover it.
 */

/** Client to server: the sandbox state of the room I am in. */
export const SANDBOX_READ = 'wiredbench.sandbox.read';

/** Client to server: save the room I am in as it stands. */
export const SANDBOX_SAVE = 'wiredbench.sandbox.save';

/** Client to server: put the room I am in back as saved. */
export const SANDBOX_RESET = 'wiredbench.sandbox.reset';

/** Client to server: give me a kit (`kind`). */
export const SANDBOX_KIT = 'wiredbench.sandbox.kit';

/** Server to client: the sandbox state and what the last request did. */
export const SANDBOX_STATE = 'wiredbench.sandbox.state';

export interface SandboxKit {
    kind: string;
    count: number;
}

export interface SandboxState {
    roomId: number;
    allowed: boolean;
    hasSaved: boolean;
    savedAt: string;
    savedItems: number;
    canTakeKits: boolean;
    kits: SandboxKit[];
    message: string;
}

export const EMPTY_SANDBOX: SandboxState = { roomId: 0, allowed: false, hasSaved: false, savedAt: '', savedItems: 0, canTakeKits: false, kits: [], message: '' };

/** The kits in the order the window lists them; one the plugin adds later goes last. */
export const KIT_ORDER = [ 'triggers', 'effects', 'conditions', 'selectors', 'addons', 'variables', 'furni' ];

const toKit = (data: unknown): SandboxKit | null => {
    if (!data || (typeof data !== 'object')) return null;

    const x = data as Record<string, unknown>;

    return ((typeof x.kind === 'string') && (typeof x.count === 'number')) ? { kind: x.kind, count: x.count } : null;
};

const rank = (kind: string) => {
    const index = KIT_ORDER.indexOf(kind);

    return (index < 0) ? KIT_ORDER.length : index;
};

/** `wiredbench.sandbox.state` as the client hands it over, or null when it is not one. */
export const toSandboxState = (data: Record<string, unknown>): SandboxState | null => {
    if ((typeof data.roomId !== 'number') || (typeof data.allowed !== 'boolean') || (typeof data.hasSaved !== 'boolean') || (typeof data.savedAt !== 'string')) return null;
    if ((typeof data.savedItems !== 'number') || (typeof data.canTakeKits !== 'boolean') || !Array.isArray(data.kits) || (typeof data.message !== 'string')) return null;

    const kits = data.kits.map(toKit);

    if (kits.some(x => x === null)) return null;

    return {
        roomId: data.roomId,
        allowed: data.allowed,
        hasSaved: data.hasSaved,
        savedAt: data.savedAt,
        savedItems: data.savedItems,
        canTakeKits: data.canTakeKits,
        kits: (kits as SandboxKit[]).sort((a, b) => rank(a.kind) - rank(b.kind)),
        message: data.message,
    };
};

type Listener = (state: SandboxState) => void;

/** The last sandbox state the plugin sent, shared by the window and the module's handler. */
export const sandboxStore = (() => {
    let current: SandboxState = EMPTY_SANDBOX;
    const listeners = new Set<Listener>();

    return {
        get current() {
            return current;
        },
        set(next: SandboxState | null) {
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
