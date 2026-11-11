/**
 * Wiredbench's client module: the hotel builds it from client/src into `wiredbench.js`, and every
 * client that runs modules loads it.
 *
 * - a toolbar icon (wwwroot/wiredbench.png) and the `wiredbench/open` link open the window;
 * - the window asks the plugin for its status (`wiredbench.hello`) and shows the answer.
 */
import { assetUrl, defineModule } from '@nitrodevco/client-module-sdk';

import { STATUS, statusStore, toStatus } from './messages';
import { WiredbenchWindow } from './WiredbenchWindow';

export default defineModule({
    activate(api) {
        api.messages.on(STATUS, data => statusStore.set(toStatus(data)));

        api.windows.register('main', WiredbenchWindow);
        api.toolbar.add({
            id: 'wiredbench',
            icon: assetUrl('wiredbench.png'),
            tooltip: api.texts.get('wiredbench.toolbar.tooltip', 'Wiredbench'),
            onClick: () => api.windows.toggle('main'),
        });
        api.links.handle('wiredbench', (link) => {
            if (link === 'wiredbench/open') api.windows.open('main');
        });
    },
});
