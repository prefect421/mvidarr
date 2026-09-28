// Regression test for #545: UniversalSearch must always search the latest
// typed query. Previously performSearch() returned early while any earlier
// request was in flight, so later keystrokes were silently dropped and the
// results shown were for a truncated query.
//
// Runs under node's built-in runner: node --test tests/unit/js/
const test = require('node:test');
const assert = require('node:assert');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

const SRC = fs.readFileSync(
    path.join(__dirname, '../../../frontend/static/js/universal-search.js'),
    'utf8'
);

function stubElement() {
    return {
        style: {},
        addEventListener() {},
        querySelector: () => null,
        querySelectorAll: () => [],
    };
}

function loadUniversalSearch(fetchImpl) {
    const context = {
        document: {
            readyState: 'complete',
            getElementById: () => null, // module-level auto-init is skipped
            addEventListener() {},
            createElement: () => ({ set textContent(v) { this._t = v; }, get innerHTML() { return this._t; } }),
        },
        window: {},
        fetch: fetchImpl,
        AbortController,
        // unref so the source's long cache-expiry timers don't hold node open
        setTimeout: (fn, ms) => setTimeout(fn, ms).unref(),
        clearTimeout,
        requestAnimationFrame: (fn) => fn(),
        console,
    };
    vm.createContext(context);
    vm.runInContext(SRC + '\nglobalThis.UniversalSearch = UniversalSearch;', context);

    // Build an instance with stubbed DOM by giving the constructor elements.
    context.document.getElementById = () => stubElement();
    const search = new context.UniversalSearch();
    search.displayed = [];
    search.displayResults = (data) => search.displayed.push(data.tag);
    search.showError = () => {};
    return search;
}

// A fetch stub whose responses the test resolves by hand, in any order.
function controlledFetch() {
    const calls = [];
    const fetchImpl = (url, { signal } = {}) =>
        new Promise((resolve, reject) => {
            const call = {
                url,
                resolve: (tag) => resolve({ ok: true, json: async () => ({ tag }) }),
            };
            signal?.addEventListener('abort', () => {
                const err = new Error('aborted');
                err.name = 'AbortError';
                reject(err);
            });
            calls.push(call);
        });
    return { fetchImpl, calls };
}

const tick = () => new Promise((r) => setImmediate(r));

test('a query typed while a search is in flight is still searched', async () => {
    const { fetchImpl, calls } = controlledFetch();
    const search = loadUniversalSearch(fetchImpl);

    search.performSearch('led zepp');
    await tick();
    search.performSearch('led zeppelin whole lotta love');
    await tick();

    assert.strictEqual(calls.length, 2, 'the later query must not be dropped');
    assert.ok(
        calls[1].url.endsWith('q=' + encodeURIComponent('led zeppelin whole lotta love'))
    );
});

test('a stale response never overwrites the latest query results', async () => {
    const { fetchImpl, calls } = controlledFetch();
    const search = loadUniversalSearch(fetchImpl);

    const first = search.performSearch('led zepp');
    await tick();
    const second = search.performSearch('led zeppelin whole lotta love');
    await tick();

    calls[1].resolve('full');
    await second;
    calls[0]?.resolve('partial'); // stale response arrives late
    await first;

    assert.deepStrictEqual(search.displayed, ['full']);
});
