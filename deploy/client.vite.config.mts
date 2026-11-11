/**
 * The Nitro client's own Vite config (vendor/nitro-next, unchanged) plus one proxy: `/gamedata` on
 * the client's origin goes to Turbo's gamedata host. Turbo hands out gamedata and client module
 * addresses on the origin a request came to, so the plugin's module is then same-origin and the
 * client runs it without listing another host in `client.modules.hosts`.
 *
 * It imports nothing by package name: deploy/ has no node_modules, and the client's config brings
 * its own imports from where it lives.
 */
import nitro from '../vendor/nitro-next/packages/nitro-react/vite.config.ts';

type Env = { command: 'build' | 'serve'; mode: string; isSsrBuild?: boolean; isPreview?: boolean };
type Config = { server?: { proxy?: Record<string, unknown> } & Record<string, unknown> } & Record<string, unknown>;

const gamedata = process.env.WB_GAMEDATA_PROXY || 'http://127.0.0.1:8094';

export default async (env: Env): Promise<Config> => {
    const base: Config = typeof nitro === 'function' ? await (nitro as (env: Env) => Config | Promise<Config>)(env) : await (nitro as Config);

    return {
        ...base,
        server: {
            ...base.server,
            proxy: {
                ...base.server?.proxy,
                '/gamedata': { target: gamedata, changeOrigin: true },
            },
        },
    };
};
