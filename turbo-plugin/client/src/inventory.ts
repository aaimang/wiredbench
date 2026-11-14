/**
 * The Delete inventory popups' messages and what they show (server/Inventory/InventoryWipe.cs).
 * Kept free of React and the client so plain tests can cover it.
 */

/** Server to client: ask the player to confirm, step 1 or 2 of 2. */
export const INVENTORY_ASK = 'wiredbench.inventory.ask';

/** Server to client: it is over: how many were deleted, and a line to show. */
export const INVENTORY_DONE = 'wiredbench.inventory.done';

/** Client to server: yes, go on to the second question, or delete after it. */
export const INVENTORY_CONFIRM = 'wiredbench.inventory.confirm';

/** Client to server: no, leave the inventory as it is. */
export const INVENTORY_CANCEL = 'wiredbench.inventory.cancel';

export interface InventoryState {
    /** 1 or 2 while a question is open, 0 once it is over. */
    step: number;
    count: number;
    seconds: number;
    deleted: number;
    message: string;
}

export const EMPTY_INVENTORY: InventoryState = { step: 0, count: 0, seconds: 0, deleted: 0, message: '' };

/** `wiredbench.inventory.ask` as the client hands it over, or null when it is not one. */
export const toAsk = (data: Record<string, unknown>): InventoryState | null => {
    if ((typeof data.step !== 'number') || (typeof data.count !== 'number')) return null;

    return { step: data.step, count: data.count, seconds: (typeof data.seconds === 'number') ? data.seconds : 0, deleted: 0, message: '' };
};

/** `wiredbench.inventory.done` as the client hands it over, or null when it is not one. */
export const toDone = (data: Record<string, unknown>): InventoryState | null => {
    if ((typeof data.deleted !== 'number') || (typeof data.message !== 'string')) return null;

    return { step: 0, count: 0, seconds: 0, deleted: data.deleted, message: data.message };
};

type Listener = (state: InventoryState) => void;

/** The question the plugin last asked, shared by the window and the module's handlers. */
export const inventoryStore = (() => {
    let current: InventoryState = EMPTY_INVENTORY;
    const listeners = new Set<Listener>();

    return {
        get current() {
            return current;
        },
        set(next: InventoryState | null) {
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
