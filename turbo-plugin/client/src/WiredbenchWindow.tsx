import { type ClientModuleWindowProps, useApi } from '@nitrodevco/client-module-sdk';
import { Box, Button, Frame, ThemeText } from '@nitrodevco/client-module-sdk/theme';
import { useEffect, useState } from 'react';

import { HELLO, type Status, statusStore } from './messages';
import { BUTTON } from './theme';
import { Hint, Icon, Section, WindowHeader } from './ui';

const WIDTH = 330;
const PADDING = 12;
const INNER = WIDTH - (PADDING * 2) - 2;
const TILE = Math.floor((INNER - 16 - 12) / 3);

/** The Wiredbench window: who the plugin answered, and the way into its tools. */
export const WiredbenchWindow = ({ close }: ClientModuleWindowProps) => {
    const api = useApi();
    const [ status, setStatus ] = useState<Status | null>(statusStore.current);

    useEffect(() => {
        const stop = statusStore.listen(setStatus);

        api.messages.send(HELLO, {});

        return stop;
    }, [ api ]);

    const text = (key: string, fallback: string, replacements?: Record<string, string>) => api.texts.get(`wiredbench.window.${ key }`, fallback, replacements);

    const tools = [
        { window: 'trace', icon: 'trace', label: text('open_trace', 'Wired trace'), tooltip: text('open_trace_tip', 'Follow each stack run: its conditions and effects') },
        { window: 'sandbox', icon: 'sandbox', label: text('open_sandbox', 'Sandbox'), tooltip: text('open_sandbox_tip', 'Save this room, reset it, take wired kits') },
        { window: 'presets', icon: 'presets', label: text('open_presets', 'Presets'), tooltip: text('open_presets_tip', 'Import and export G-Presets files') },
    ];

    return (
        <Frame
            id={ `${ api.key }-main` }
            variant="3"
            caption={ status ? text('title_version', 'Wiredbench %version%', { version: status.version }) : text('title', 'Wiredbench') }
            centered
            resizeDirection="none"
            onClose={ close }
            layout={ { width: WIDTH, height: 228 } }>
            <Box layout={ { flexDirection: 'column', gap: 10, padding: PADDING, width: WIDTH - 2 } }>
                <WindowHeader
                    icon="wiredbench"
                    title={ text('header', 'Wiredbench') }
                    width={ INNER }
                    subtitle={ status
                        ? text('version', 'Version %version%, connected as %name% (%player%)', { version: status.version, name: status.playerName || '?', player: String(status.playerId) })
                        : text('waiting', 'Waiting for the plugin...') } />
                <Section title={ text('tools', 'Tools') } width={ INNER }>
                    <Box layout={ { flexDirection: 'row', gap: 6 } }>
                        { tools.map(tool => (
                            <Button key={ tool.window } variant={ BUTTON.plain } tooltip={ tool.tooltip } layout={ { width: TILE, height: 58, flexDirection: 'column', gap: 2 } } onPointerTap={ () => api.windows.open(tool.window) }>
                                <Icon name={ tool.icon } size={ 28 } />
                                <ThemeText text={ tool.label } textStyle="u_bold" />
                            </Button>
                        )) }
                    </Box>
                    <Hint text={ text('tools_hint', 'WIRED tools for the room you are in.') } width={ INNER - 16 } />
                </Section>
            </Box>
        </Frame>
    );
};
