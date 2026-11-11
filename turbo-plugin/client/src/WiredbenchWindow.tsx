import { type ClientModuleWindowProps, useApi } from '@nitrodevco/client-module-sdk';
import { Box, Button, Frame, ThemeText } from '@nitrodevco/client-module-sdk/theme';
import { useEffect, useState } from 'react';

import { HELLO, type Status, statusStore } from './messages';
import { BUTTON } from './theme';

const WIDTH = 300;
const PADDING = 12;
const BUTTON_WIDTH = Math.floor((WIDTH - (PADDING * 2) - 2 - 12) / 3);

/** Wiredbench's window: the plugin's version, and the way into its tools. */
export const WiredbenchWindow = ({ close }: ClientModuleWindowProps) => {
    const api = useApi();
    const [ status, setStatus ] = useState<Status | null>(statusStore.current);

    useEffect(() => {
        const stop = statusStore.listen(setStatus);

        api.messages.send(HELLO, {});

        return stop;
    }, [ api ]);

    const text = (key: string, fallback: string, replacements?: Record<string, string>) => api.texts.get(`wiredbench.window.${ key }`, fallback, replacements);

    return (
        <Frame
            id={ `${ api.key }-main` }
            variant="3"
            caption={ status ? text('title_version', 'Wiredbench %version%', { version: status.version }) : text('title', 'Wiredbench') }
            centered
            resizeDirection="none"
            onClose={ close }
            layout={ { width: WIDTH, height: 150 } }>
            <Box layout={ { flexDirection: 'column', gap: 10, padding: PADDING, width: WIDTH - 2 } }>
                <ThemeText text={ text('body', 'WIRED tools for this room.') } textStyle="u_regular" />
                <ThemeText
                    text={ status
                        ? text('version', 'Version %version%, connected as player %player%.', { version: status.version, player: String(status.playerId) })
                        : text('waiting', 'Waiting for the plugin...') }
                    textStyle="u_bold" />
                <Box layout={ { flexDirection: 'row', gap: 6 } }>
                    <Button variant={ BUTTON.plain } layout={ { width: BUTTON_WIDTH } } onPointerTap={ () => api.windows.open('trace') }>
                        <ThemeText text={ text('open_trace', 'Wired trace') } />
                    </Button>
                    <Button variant={ BUTTON.plain } layout={ { width: BUTTON_WIDTH } } onPointerTap={ () => api.windows.open('sandbox') }>
                        <ThemeText text={ text('open_sandbox', 'Sandbox') } />
                    </Button>
                    <Button variant={ BUTTON.plain } layout={ { width: BUTTON_WIDTH } } onPointerTap={ () => api.windows.open('presets') }>
                        <ThemeText text={ text('open_presets', 'Presets') } />
                    </Button>
                </Box>
            </Box>
        </Frame>
    );
};
