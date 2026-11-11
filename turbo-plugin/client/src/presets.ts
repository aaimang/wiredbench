/**
 * The Presets window's messages and the library it shows (server/Presets/PresetMessages.cs). Kept
 * free of React and the client so plain tests can cover it.
 */

/** Client to server: the library, and the room I am in. */
export const PRESETS_READ = 'wiredbench.presets.read';

/** Client to server: import preset `id` into the room I am in, or a new room (`newRoom`). */
export const PRESETS_IMPORT = 'wiredbench.presets.import';

/** Client to server: import preset `id` at the next floor tile I click. */
export const PRESETS_PICK = 'wiredbench.presets.pick';

/** Client to server: save the room I am in to the library as `name`. */
export const PRESETS_EXPORT = 'wiredbench.presets.export';

/** Server to client: the library and what the last request did. */
export const PRESETS_STATE = 'wiredbench.presets.state';

export interface PresetItem {
    id: number;
    name: string;
    furni: number;
    boxes: number;
    savedAt: string;
}

export interface PresetsState {
    roomId: number;
    presets: PresetItem[];
    message: string;
}

export const EMPTY_PRESETS: PresetsState = { roomId: 0, presets: [], message: '' };

const toItem = (data: unknown): PresetItem | null => {
    if (!data || (typeof data !== 'object')) return null;

    const x = data as Record<string, unknown>;

    if ((typeof x.id !== 'number') || (typeof x.name !== 'string') || (typeof x.furni !== 'number') || (typeof x.boxes !== 'number') || (typeof x.savedAt !== 'string')) return null;

    return { id: x.id, name: x.name, furni: x.furni, boxes: x.boxes, savedAt: x.savedAt };
};

/** `wiredbench.presets.state` as the client hands it over, or null when it is not one. */
export const toPresetsState = (data: Record<string, unknown>): PresetsState | null => {
    if ((typeof data.roomId !== 'number') || !Array.isArray(data.presets) || (typeof data.message !== 'string')) return null;

    const presets = data.presets.map(toItem);

    if (presets.some(x => x === null)) return null;

    return { roomId: data.roomId, presets: presets as PresetItem[], message: data.message };
};

/** The name an export is saved under: there is no text input in a module window. */
export const exportName = (roomId: number, now: Date) => {
    const pad = (n: number) => String(n).padStart(2, '0');

    return `Room ${ roomId }, ${ now.getFullYear() }-${ pad(now.getMonth() + 1) }-${ pad(now.getDate()) } ${ pad(now.getHours()) }:${ pad(now.getMinutes()) }`;
};

type Listener = (state: PresetsState) => void;

/** The last library the plugin sent, shared by the window and the module's handler. */
export const presetsStore = (() => {
    let current: PresetsState = EMPTY_PRESETS;
    const listeners = new Set<Listener>();

    return {
        get current() {
            return current;
        },
        set(next: PresetsState | null) {
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
