import { type ClientModuleWindowProps, useApi } from '@nitrodevco/client-module-sdk';
import { Box, Frame, ThemeText } from '@nitrodevco/client-module-sdk/theme';
import { useEffect, useState } from 'react';

import { HELLO, type Status, statusStore } from './messages';

/** Wiredbench's window. For now it shows that the client module and the plugin reach each other. */
export const WiredbenchWindow = ({ close }: ClientModuleWindowProps) => {
    const api = useApi();
    const [ status, setStatus ] = useState<Status | null>(statusStore.current);

    useEffect(() => {
        const stop = statusStore.listen(setStatus);

        api.messages.send(HELLO, {});

        return stop;
    }, [ api ]);

    const text = (key: string, fallback: string, replacements?: Record<string, string>) => api.texts.get(`wiredbench.window.${key}`, fallback, replacements);

    return (
        <Frame
            id={`${api.key}-main`}
            variant="3"
            caption={text('title', 'Wiredbench')}
            centered
            resizeDirection="none"
            onClose={close}
            layout={{ width: 280, height: 120 }}>
            <Box layout={{ flexDirection: 'column', gap: 8, padding: 10, width: 278 }}>
                <ThemeText
                    text={text('body', 'WIRED tools for this room.')}
                    textStyle="u_regular" />
                <ThemeText
                    text={status
                        ? text('connected', 'Plugin %version% answered player %player%.', { version: status.version, player: String(status.playerId) })
                        : text('waiting', 'Waiting for the plugin...')}
                    textStyle="u_bold" />
            </Box>
        </Frame>
    );
};
