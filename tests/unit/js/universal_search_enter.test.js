// The live search box is the inline UniversalSearch class in base.html (not
// static/js/universal-search.js, which is never loaded). It must search only
// when Enter is pressed: every search also queries YouTube (100 API quota
// units), so searching per keystroke exhausted the daily quota.
//
// Runs under node's built-in runner: node --test tests/unit/js/
const test = require('node:test');
const assert = require('node:assert');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

const HTML = fs.readFileSync(
    path.join(__dirname, '../../../frontend/templates/base.html'),
    'utf8'
);
const start = HTML.indexOf('class UniversalSearch {');
const end = HTML.indexOf('\n        }\n', start) + '\n        }\n'.length;
const SRC = HTML.slice(start, end);

function stubElement() {
    const handlers = {};
    return {
        style: {},
        value: '',
        handlers,
        addEventListener(type, fn) { handlers[type] = fn; },
        querySelector: () => null,
        querySelectorAll: () => [],
    };
}

function load(fetchImpl) {
    const elements = {};
    const context = {
        document: { getElementById: (id) => (elements[id] ||= stubElement()), addEventListener() {} },
        fetch: fetchImpl,
        console,
        showToast() {},
    };
    vm.createContext(context);
    vm.runInContext(SRC + '\nglobalThis.UniversalSearch = UniversalSearch;', context);
    const search = new context.UniversalSearch();
    search.displayed = [];
    search.displayResults = (data) => search.displayed.push(data.tag);
    search.showError = () => {};
    return { search, input: elements.universalSearchInput };
}

function controlledFetch() {
    const calls = [];
    const fetchImpl = (url) =>
        new Promise((resolve) => {
            calls.push({ url, resolve: (tag) => resolve({ ok: true, json: async () => ({ tag }) }) });
        });
    return { fetchImpl, calls };
}

const tick = () => new Promise((r) => setImmediate(r));
const type = (input, value) => {
    input.value = value;
    input.handlers.input({ target: input });
};
const enter = (input) => input.handlers.keydown({ key: 'Enter', preventDefault() {} });

test('typing never triggers a search', async () => {
    const { fetchImpl, calls } = controlledFetch();
    const { input } = load(fetchImpl);

    for (const v of ['al', 'ali', 'alie', 'alien ant farm']) type(input, v);
    await new Promise((r) => setTimeout(r, 400)); // longer than the old 300ms debounce

    assert.strictEqual(calls.length, 0);
});

test('Enter searches once with the typed query', async () => {
    const { fetchImpl, calls } = controlledFetch();
    const { input } = load(fetchImpl);

    type(input, 'Alien Ant Farm');
    enter(input);
    await tick();

    assert.strictEqual(calls.length, 1);
    assert.ok(calls[0].url.endsWith('q=' + encodeURIComponent('Alien Ant Farm')));
});

test('Enter on a single character does not search', async () => {
    const { fetchImpl, calls } = controlledFetch();
    const { input } = load(fetchImpl);

    type(input, 'a');
    enter(input);
    await tick();

    assert.strictEqual(calls.length, 0);
});

test('Enter pressed during an in-flight search searches the latest query', async () => {
    const { fetchImpl, calls } = controlledFetch();
    const { search, input } = load(fetchImpl);

    type(input, 'moon');
    enter(input);
    await tick();
    type(input, 'moon river');
    enter(input);
    await tick();
    assert.strictEqual(calls.length, 2, 'the second Enter must not be dropped');

    calls[1].resolve('latest');
    await tick();
    calls[0].resolve('stale');
    await tick();

    assert.deepStrictEqual(search.displayed, ['latest']);
});

test('clearing the box cancels a pending result', async () => {
    const { fetchImpl, calls } = controlledFetch();
    const { search, input } = load(fetchImpl);

    type(input, 'moon');
    enter(input);
    await tick();
    type(input, '');
    calls[0].resolve('late');
    await tick();

    assert.deepStrictEqual(search.displayed, []);
});
