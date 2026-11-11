/**
 * Wiredbench's client module: the hotel builds it from client/src into `wiredbench.js`, and every
 * client that runs modules loads it.
 *
 * - a toolbar icon (wwwroot/wiredbench.png) and the `wiredbench/open` link open the window;
 * - the window asks the plugin for its status (`wiredbench.hello`) and shows the answer;
 * - the Trace window (its button, or the `wiredbench/trace` link) shows the room's wired trace.
 */
import { assetUrl, defineModule } from '@nitrodevco/client-module-sdk';

import { STATUS, statusStore, toStatus } from './messages';
import { TRACE_STATE, traceStore, toTraceState } from './trace';
import { TraceWindow } from './TraceWindow';
import { WiredbenchWindow } from './WiredbenchWindow';

export default defineModule({
    activate(api) {
        api.messages.on(STATUS, data => statusStore.set(toStatus(data)));

        api.messages.on(TRACE_STATE, data => traceStore.apply(toTraceState(data)));

        api.windows.register('main', WiredbenchWindow);
        api.windows.register('trace', TraceWindow);
        api.toolbar.add({
            id: 'wiredbench',
            icon: assetUrl('wiredbench.png'),
            tooltip: api.texts.get('wiredbench.toolbar.tooltip', 'Wiredbench'),
            onClick: () => api.windows.toggle('main'),
        });
        api.links.handle('wiredbench', (link) => {
            if (link === 'wiredbench/open') api.windows.open('main');
            if (link === 'wiredbench/trace') api.windows.open('trace');
        });
    },
});
