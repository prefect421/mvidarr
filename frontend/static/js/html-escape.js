/*
 * Shared output-escaping helpers (#622). Loaded from base.html before any page
 * script, so every template and static script can rely on them.
 *
 * Why this exists: titles, artist names and descriptions come from YouTube,
 * yt-dlp metadata, MusicBrainz and the filesystem, i.e. from people other than
 * the user. They must never reach innerHTML or an HTML attribute unescaped.
 * The old per-page copies used the textContent/innerHTML trick, which leaves
 * `"` and `'` alone and so does not protect attribute values.
 *
 *   escapeHtml(v)       text nodes and quoted attribute values (the default)
 *   escapeHtmlStrict(v) like escapeHtml but ALWAYS encodes `&`
 *   escapeJsArg(v)      a value inside an inline handler: onclick="fn(${escapeJsArg(v)})"
 *   sanitizeMessageHtml(v) toast/dialog messages: everything escaped except <br>
 */
(function (root) {
    'use strict';

    var ENTITY_AMP = /&(?!(?:#[0-9]{1,7}|#[xX][0-9a-fA-F]{1,6}|[A-Za-z][A-Za-z0-9]{1,31});)/g;
    var MAP = { '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;', '`': '&#96;' };

    function toText(value) {
        return value === null || value === undefined ? '' : String(value);
    }

    // Entity-preserving: a well-formed entity such as &quot; or &amp; (already
    // present in stored YouTube titles) is left as is and still displays
    // correctly, while every raw & < > " ' ` is encoded. A valid entity can only
    // ever render as text, never as markup, so this is safe in text nodes and in
    // quoted attribute values. Idempotent: escapeHtml(escapeHtml(x)) === escapeHtml(x).
    function escapeHtml(value) {
        return toText(value).replace(ENTITY_AMP, '&amp;').replace(/[<>"'`]/g, function (c) {
            return MAP[c];
        });
    }

    function escapeHtmlStrict(value) {
        return toText(value).replace(/&/g, '&amp;').replace(/[<>"'`]/g, function (c) {
            return MAP[c];
        });
    }

    // Inside an inline handler the attribute value is entity-DECODED before the
    // JavaScript runs, so `&#39;` would become a live quote in the JS source.
    // Pass the value as a JSON string literal and encode it strictly instead.
    function escapeJsArg(value) {
        return escapeHtmlStrict(JSON.stringify(toText(value)));
    }

    // Messages are text, with a literal <br> allowed for line breaks.
    function sanitizeMessageHtml(value) {
        return escapeHtml(value).replace(/&lt;br\s*\/?&gt;/gi, '<br>');
    }

    var api = {
        escapeHtml: escapeHtml,
        escapeAttr: escapeHtml,
        escapeHtmlStrict: escapeHtmlStrict,
        escapeJsArg: escapeJsArg,
        sanitizeMessageHtml: sanitizeMessageHtml,
    };

    if (typeof module !== 'undefined' && module.exports) {
        module.exports = api;
    }
    for (var key in api) {
        if (Object.prototype.hasOwnProperty.call(api, key)) {
            root[key] = api[key];
        }
    }
})(typeof window !== 'undefined' ? window : globalThis);
