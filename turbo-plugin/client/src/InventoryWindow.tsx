import { type ClientModuleWindowProps, useApi } from '@nitrodevco/client-module-sdk';
import { Box, Button, Frame, ThemeText } from '@nitrodevco/client-module-sdk/theme';
import { useEffect, useState } from 'react';

import { INVENTORY_CANCEL, INVENTORY_CONFIRM, type InventoryState, inventoryStore } from './inventory';
import { BUTTON, TEXT } from './theme';
import { Hint } from './ui';

const WIDTH = 360;
const HEIGHT = 230;
const PADDING = 14;
const INNER = WIDTH - (PADDING * 2) - 2;

/**
 * The two questions `:deleteinventory` asks before it deletes anything, one popup after the other,
 * then what it did. Closing the window at a question is a no.
 */
export const InventoryWindow = ({ close }: ClientModuleWindowProps) => {
    const api = useApi();
    const [ state, setState ] = useState<InventoryState>(inventoryStore.current);
    const [ busy, setBusy ] = useState(false);

    useEffect(() => inventoryStore.listen(next => {
        setState(next);
        setBusy(false);
    }), []);

    const text = (key: string, fallback: string, replacements?: Record<string, string>) => api.texts.get(`wiredbench.inventory.${ key }`, fallback, replacements);

    const cancel = () => {
        // A question left open is a no; once it is over there is nothing to tell the server.
        if (state.step > 0) api.messages.send(INVENTORY_CANCEL, {});

        close();
    };

    const confirm = () => {
        setBusy(true);
        api.messages.send(INVENTORY_CONFIRM, {});
    };

    const second = state.step === 2;
    const over = state.step === 0;

    return (
        <Frame
            id={ `${ api.key }-inventory` }
            variant="3"
            caption={ text('title', 'Delete inventory') }
            centered
            resizeDirection="none"
            onClose={ cancel }
            layout={ { width: WIDTH, height: HEIGHT } }>
            <Box layout={ { flexDirection: 'column', gap: 12, padding: PADDING, width: WIDTH - 2 } }>
                { over ? (
                    <ThemeText text={ state.message || text('over', 'Nothing was deleted.') } textStyle="u_bold" textOptions={ { wordWrap: true, wordWrapWidth: INNER, fill: state.deleted ? TEXT.good : TEXT.title } } />
                ) : (
                    <>
                        <ThemeText
                            text={ second ? text('second_title', 'Are you really sure?') : text('first_title', 'Delete your whole inventory?') }
                            textStyle="u_bold"
                            textOptions={ { wordWrap: true, wordWrapWidth: INNER, fill: second ? TEXT.bad : TEXT.title } } />
                        <Hint
                            width={ INNER }
                            text={ second
                                ? text('second_body', 'This deletes all %count% furni in your inventory for good. They cannot be given back. Furni standing in rooms are not touched.', { count: String(state.count) })
                                : text('first_body', 'This will delete all %count% furni in your inventory. You will be asked once more before anything is deleted.', { count: String(state.count) }) } />
                        <Hint width={ INNER } text={ text('timeout', 'If you do not answer within %seconds% seconds, nothing is deleted.', { seconds: String(state.seconds) }) } />
                    </>
                ) }
                <Box layout={ { flexDirection: 'row', gap: 8, justifyContent: 'flex-end' } }>
                    { over ? (
                        <Button variant={ BUTTON.green } layout={ { width: 110 } } onPointerTap={ close }>
                            <ThemeText text={ text('ok', 'Close') } />
                        </Button>
                    ) : (
                        <>
                            <Button variant={ BUTTON.plain } disabled={ busy } layout={ { width: 110 } } onPointerTap={ cancel }>
                                <ThemeText text={ text('cancel', 'Cancel') } />
                            </Button>
                            <Button variant={ second ? BUTTON.dark : BUTTON.green } disabled={ busy } layout={ { width: 150 } } onPointerTap={ confirm }>
                                <ThemeText text={ second ? text('delete', 'Delete everything') : text('continue', 'Yes, continue') } />
                            </Button>
                        </>
                    ) }
                </Box>
            </Box>
        </Frame>
    );
};
