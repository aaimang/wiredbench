/**
 * The plugin's named messages, read and sent by name (server/WiredbenchMessages.cs). Kept free of
 * React and the client so plain tests can cover it.
 */
import type { ClientModuleMessageOf } from '@nitrodevco/client-module-sdk';

/** Client to server: the window opened and wants the plugin's status. */
export const HELLO = 'wiredbench.hello';

/** Server to client: the plugin's version and the player it answered. */
export const STATUS = 'wiredbench.status';

/** `wiredbench.status`'s fields, as the server sends its schema (`StatusMessage`, camelCase). */
export const STATUS_SCHEMA = [ [ 'version', 'string' ], [ 'playerId', 'int' ], [ 'playerName', 'string' ] ] as const;

export type Status = ClientModuleMessageOf<typeof STATUS_SCHEMA>;

/** `wiredbench.status` as the client hands it over, or null when it is not one. */
export const toStatus = (data: Record<string, unknown>): Status | null => {
    if ((typeof data.version !== 'string') || (typeof data.playerId !== 'number')) return null;

    return { version: data.version, playerId: data.playerId, playerName: (typeof data.playerName === 'string') ? data.playerName : '' };
};

type Listener = (status: Status | null) => void;

/** The last status the plugin sent, shared by the window and the module's message handler. */
export const statusStore = (() => {
    let current: Status | null = null;
    const listeners = new Set<Listener>();

    return {
        get current() {
            return current;
        },
        set(next: Status | null) {
            current = next;

            for (const listener of listeners) listener(next);
        },
        listen(listener: Listener) {
            listeners.add(listener);

            return () => void listeners.delete(listener);
        },
    };
})();
