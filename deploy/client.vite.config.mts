/**
 * The Nitro client's own Vite config (vendor/nitro-next, unchanged) plus a proxy: `/gamedata` on
 * the client's origin goes to Turbo's gamedata host. Turbo hands out gamedata and client module
 * addresses on the origin a request came to, so the plugin's module is then same-origin and the
 * client runs it without listing another host in `client.modules.hosts`. The page also reads
 * this hotel's furnidata and product data from it (`hotelGamedata`).
 *
 * It imports nothing by package name: deploy/ has no node_modules, and the client's config brings
 * its own imports from where it lives.
 */
import nitro from '../vendor/nitro-next/packages/nitro-react/vite.config.ts';

type Env = { command: 'build' | 'serve'; mode: string; isSsrBuild?: boolean; isPreview?: boolean };
type Config = { server?: { proxy?: Record<string, unknown> } & Record<string, unknown> } & Record<string, unknown>;

const gamedata = process.env.WB_GAMEDATA_PROXY || 'http://127.0.0.1:8094';

/**
 * The gamedata files the client reads from this hotel (through the `/gamedata` proxy) instead of
 * the config's nitrodev.co: the furnidata carries this hotel's catalogue offer ids, which the
 * infostand's Buy and Builders Club "Place more" send, and the product data its names. Set
 * `WB_HOTEL_GAMEDATA` to a comma list to change it (`furnidata,productdata,texts`), or to `none`.
 */
const HOTEL_FILES: Record<string, [ string, string ]> = {
    furnidata: [ 'furnituredata.url', '/gamedata/furnidata_json/0' ],
    productdata: [ 'productdata.url', '/gamedata/productdata_json/0' ],
    texts: [ 'gamedata.urls.externalTexts', '/gamedata/external_flash_texts/0' ],
};

const hotelConfig = (): Record<string, string> => {
    const wanted = (process.env.WB_HOTEL_GAMEDATA ?? 'furnidata,productdata').split(',').map(x => x.trim()).filter(Boolean);

    return Object.fromEntries(wanted.flatMap(name => (HOTEL_FILES[name] ? [ HOTEL_FILES[name] ] : [])));
};

/** `window.NitroConfig` wins over the loaded config (useConfigLoader), so the page adds to it. */
const hotelGamedata = () => ({
    name: 'wiredbench-hotel-gamedata',
    transformIndexHtml: () => {
        const config = hotelConfig();

        if (!Object.keys(config).length) return [];

        return [ {
            tag: 'script',
            // After index.html's own `window.NitroConfig = {...}`, before the deferred module reads it.
            injectTo: 'body',
            children: `window.NitroConfig = Object.assign(window.NitroConfig || {}, ${ JSON.stringify(config) });`,
        } ];
    },
});

export default async (env: Env): Promise<Config> => {
    const base: Config = typeof nitro === 'function' ? await (nitro as (env: Env) => Config | Promise<Config>)(env) : await (nitro as Config);

    return {
        ...base,
        plugins: [ ...((base.plugins as unknown[]) ?? []), hotelGamedata() ],
        server: {
            ...base.server,
            proxy: {
                ...base.server?.proxy,
                '/gamedata': { target: gamedata, changeOrigin: true },
            },
        },
    };
};
