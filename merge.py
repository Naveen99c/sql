#!/usr/bin/env python3
"""
Merge sql_sandbox.html into sql_atlas.html so the atlas becomes a single
self-contained page. Practice pills open an in-page sandbox overlay
instead of navigating to a separate file.

Key design constraint:
  The sandbox body contains multiple nested <template x-if> / <template x-for>
  elements. If we wrap the sandbox body inside an outer <template> tag, the
  first inner </template> closes the OUTER wrapper and the HTML parser
  discards everything after it — that's what was breaking the atlas DOM.

Fix: stash the sandbox markup inside <script type="text/html" id="...">
  Script content is CDATA-like — the parser only looks for a literal
  </script> end tag, so nested <template> and <body>-like tags are safe.
  On demand we read .textContent and innerHTML into a wrapper div that we
  then hand to Alpine.initTree().
"""
import re
from pathlib import Path

ATLAS   = Path("sql_atlas.html.bak")   # always start from clean backup
SANDBOX = Path("sql_sandbox.html")
OUT     = Path("sql_atlas.html")

atlas   = ATLAS.read_text()
sandbox = SANDBOX.read_text()

# ---------------------------------------------------------------------------
# 1. Extract the three interesting regions from the sandbox.
# ---------------------------------------------------------------------------
head_match = re.search(r"</title>(.*?)<style>", sandbox, re.DOTALL)
head_cdn   = head_match.group(1).strip() if head_match else ""

style_match  = re.search(r"<style>(.*?)</style>", sandbox, re.DOTALL)
sandbox_css  = style_match.group(1) if style_match else ""

body_match   = re.search(r"<body[^>]*>(.*?)</body>", sandbox, re.DOTALL)
sandbox_body = body_match.group(1) if body_match else ""

# Strip inline <script> blocks out of the body (extracted separately).
sandbox_body = re.sub(r"<script\b[^>]*>.*?</script>", "", sandbox_body, flags=re.DOTALL)

# Pull the big closing script (PROBLEMS + sqlApp())
last_script_start = sandbox.rfind("<script>")
last_script_end   = sandbox.rfind("</script>")
sandbox_script    = sandbox[last_script_start + len("<script>") : last_script_end]

# Strip the sandbox's own <header> — the overlay has its own chrome.
sandbox_body = re.sub(r"<header\b.*?</header>", "", sandbox_body, count=1, flags=re.DOTALL)

# ---------------------------------------------------------------------------
# 2. Scope-prefix sandbox CSS so it lives under #sandboxOverlay.
# ---------------------------------------------------------------------------
def scope_selectors(css: str, scope: str) -> str:
    result = []
    i = 0
    n = len(css)
    depth = 0
    buf = ""
    while i < n:
        c = css[i]
        if c == "{":
            if depth == 0:
                selector_list = buf.strip()
                buf = ""
                if selector_list.startswith("@"):
                    start = i
                    depth2 = 1
                    i += 1
                    while i < n and depth2 > 0:
                        if css[i] == "{": depth2 += 1
                        elif css[i] == "}": depth2 -= 1
                        i += 1
                    block = css[start + 1 : i - 1]
                    if selector_list.startswith(("@media", "@supports")):
                        result.append(f"{selector_list} {{{scope_selectors(block, scope)}}}")
                    else:
                        result.append(f"{selector_list} {{{block}}}")
                    continue
                parts = []
                for sel in selector_list.split(","):
                    sel = sel.strip()
                    if not sel:
                        continue
                    if sel.startswith(":root") or sel == "*" or sel == "html":
                        parts.append(sel)
                    elif sel.startswith("::-webkit-scrollbar"):
                        parts.append(sel)
                    elif sel == "body":
                        parts.append("body.sandbox-open")
                    else:
                        parts.append(f"{scope} {sel}")
                result.append(", ".join(parts) + " {")
                depth += 1
                i += 1
                continue
            else:
                buf += c
                depth += 1
        elif c == "}":
            if depth == 1:
                result.append(buf + "}")
                buf = ""
                depth -= 1
            else:
                buf += c
                depth -= 1
        else:
            buf += c
        i += 1
    return "".join(result)

scoped_css = scope_selectors(sandbox_css, "#sandboxOverlay")

# ---------------------------------------------------------------------------
# 3. Rewrite deep-link slug reader to point at our bridge variable.
# ---------------------------------------------------------------------------
sandbox_script = sandbox_script.replace(
    "new URLSearchParams(window.location.search).get('slug')",
    "window.__sandboxSlug",
)

# ---------------------------------------------------------------------------
# 4. Overlay chrome + styles.
# ---------------------------------------------------------------------------
overlay_styles = """
<style id="sandboxOverlayCss">
.sandbox-overlay {
  position: fixed; inset: 0; z-index: 9999;
  background: var(--ink);
  display: flex; flex-direction: column;
  overflow: hidden;
}
.sandbox-overlay[hidden] { display: none !important; }
.sandbox-overlay-bar {
  flex: 0 0 44px;
  display: flex; align-items: center; gap: 16px;
  padding: 0 20px;
  border-bottom: 1px solid var(--ink-line);
  background: rgba(10,14,26,0.9);
  backdrop-filter: blur(6px);
}
.sandbox-close-btn {
  border: 1px solid var(--ink-line);
  background: rgba(255,255,255,0.03);
  color: var(--parchment-dim);
  padding: 6px 14px; border-radius: 2px;
  font-family: 'JetBrains Mono', monospace;
  font-size: 0.7rem;
  text-transform: uppercase;
  letter-spacing: 0.14em;
  cursor: pointer;
  transition: all 180ms ease;
}
.sandbox-close-btn:hover {
  color: var(--amber);
  border-color: var(--amber);
  background: rgba(229,166,59,0.06);
}
.sandbox-crumb {
  color: var(--muted);
  font-size: 0.78rem;
  font-family: 'JetBrains Mono', monospace;
  letter-spacing: 0.04em;
}
#sandboxMount {
  flex: 1; min-height: 0;
  display: flex; flex-direction: column;
}
#sandboxMount > div { flex: 1; min-height: 0; display: flex; flex-direction: column; }
/* Override sandbox's viewport-anchored workspace height so it flexes inside the overlay */
#sandboxMount .workspace {
  flex: 1 1 auto !important;
  min-height: 0 !important;
  height: auto !important;
  padding: 0.75rem !important;
  gap: 0.75rem !important;
  display: flex !important;
}
#sandboxMount .left-pane { min-height: 0; }
#sandboxMount .right-pane { min-height: 0; }
#sandboxMount .editor-env { flex: 1 1 55%; min-height: 0; }
#sandboxMount .console-env { flex: 1 1 45%; min-height: 0; }
#sandboxMount #editorWrap {
  flex: 1 1 auto !important;
  min-height: 0 !important;
  height: auto !important;
}
/* Minimal CodeMirror overrides — only size, do NOT touch internal line styles. */
#sandboxMount .CodeMirror {
  height: 100% !important;
  width: 100% !important;
}
body.sandbox-open { overflow: hidden; }
</style>
"""

# The sandbox markup is stashed inside a <script type="text/html"> so nested
# <template> tags inside it don't close any outer HTML element.
overlay_markup = (
    '<!-- ============ EMBEDDED SANDBOX OVERLAY ============ -->\n'
    '<div id="sandboxOverlay" class="sandbox-overlay" hidden>\n'
    '  <div class="sandbox-overlay-bar">\n'
    '    <button id="sandboxClose" class="sandbox-close-btn" title="Close (Esc)">\u2190 Back to Atlas</button>\n'
    '    <span id="sandboxCrumb" class="sandbox-crumb"></span>\n'
    '  </div>\n'
    '  <div id="sandboxMount"></div>\n'
    '</div>\n'
    '<script type="text/html" id="sandboxTemplate">\n'
    + sandbox_body +
    '\n</script>\n'
    '<!-- ============ /EMBEDDED SANDBOX OVERLAY ============ -->\n'
)

# ---------------------------------------------------------------------------
# 5. Inject CDN tags + overlay styles + scoped sandbox CSS into <head>.
#    For <script src="..."> tags we MUST emit the explicit </script> closer —
#    omitting it causes the browser to treat subsequent DOM (up to the next
#    </script>) as the script's body, swallowing everything inside <body>.
# ---------------------------------------------------------------------------
cdn_tags = []
# Script tags: capture the entire <script ...></script> pair.
for m in re.finditer(r'<script\b[^>]*>\s*</script>', head_cdn):
    cdn_tags.append(m.group(0))
# Self-closing <link> tags.
for m in re.finditer(r'<link\b[^>]*/?>', head_cdn):
    cdn_tags.append(m.group(0))

for tag in cdn_tags:
    # Avoid double-adding identical tags that already exist in the atlas head.
    if tag not in atlas:
        atlas = atlas.replace("</head>", tag + "\n</head>", 1)

atlas = atlas.replace("</head>", overlay_styles + "\n</head>", 1)
atlas = atlas.replace(
    "</head>",
    f'<style id="sandboxEmbeddedCss">\n{scoped_css}\n</style>\n</head>',
    1,
)

# ---------------------------------------------------------------------------
# 6. Inject overlay markup + sandbox JS just before </body>.
# ---------------------------------------------------------------------------
atlas = atlas.replace("</body>", overlay_markup + "</body>", 1)

atlas = atlas.replace(
    "</body>",
    f'<script id="sandboxEmbeddedJs">\n{sandbox_script}\n</script>\n</body>',
    1,
)

# ---------------------------------------------------------------------------
# 7. Bridge script: pill click → overlay open, destroy on close.
# ---------------------------------------------------------------------------
bridge_js = """
<script id="sandboxBridge">
(function () {
  const overlay  = document.getElementById('sandboxOverlay');
  const closeBtn = document.getElementById('sandboxClose');
  const crumb    = document.getElementById('sandboxCrumb');
  const tmpl     = document.getElementById('sandboxTemplate');
  const mount    = document.getElementById('sandboxMount');

  function showSandbox(slug, pill) {
    window.__sandboxSlug = slug;
    overlay.hidden = false;
    document.body.classList.add('sandbox-open');

    if (pill) {
      const ph  = pill.closest('.phase-node')?.dataset.title || '';
      const sec = pill.closest('.section-node')?.dataset.title || '';
      const row = pill.closest('tr');
      const name = row?.querySelectorAll('td')?.[1]?.textContent?.trim() || slug;
      crumb.textContent = [ph, sec, name].filter(Boolean).join(' \u203a ');
    } else {
      crumb.textContent = slug;
    }

    // Pull template text and inject; then initialise Alpine on the wrapper.
    mount.innerHTML = '';
    const wrap = document.createElement('div');
    wrap.setAttribute('x-data', 'sqlApp()');
    wrap.innerHTML = tmpl.textContent;
    mount.appendChild(wrap);
    if (window.Alpine && window.Alpine.initTree) window.Alpine.initTree(wrap);

    // Poll briefly for the CodeMirror instance to appear, then force re-measure.
    // This is needed because the editor is created inside Alpine's async init(),
    // and its initial character-width / line-height measurement can be taken
    // against a fallback font or a transient layout. When that happens, the
    // measured row-height is bigger than the rendered line-height and every
    // <Enter> adds a phantom vertical gap.
    const start = Date.now();
    const doHardRefresh = (cmInst) => {
      // setSize('100%', '100%') + refresh is CodeMirror's official supported way
      // to force it to re-measure its container and rebuild the virtual viewport.
      // Plain refresh() on its own wasn't enough — the viewOffset kept latching
      // at (lineCount * lineHeight), leaving a giant blank gap above line 1.
      try { cmInst.setSize('100%', '100%'); } catch (_) {}
      cmInst.refresh();
      cmInst.scrollTo(0, 0);
    };
    const poll = () => {
      const cmEl = mount.querySelector('.CodeMirror');
      const cmInst = cmEl && cmEl.CodeMirror;
      if (cmInst) {
        doHardRefresh(cmInst);
        requestAnimationFrame(() => requestAnimationFrame(() => doHardRefresh(cmInst)));
        setTimeout(() => doHardRefresh(cmInst), 200);
        // Once fonts are ready, blast the cache one final time.
        if (document.fonts && document.fonts.ready) {
          document.fonts.ready.then(() => doHardRefresh(cmInst));
        }
        return;
      }
      if (Date.now() - start < 4000) requestAnimationFrame(poll);
    };
    requestAnimationFrame(poll);
  }

  function hideSandbox() {
    overlay.hidden = true;
    document.body.classList.remove('sandbox-open');
    window.__sandboxSlug = null;
    if (window.Alpine && window.Alpine.destroyTree && mount.firstChild) {
      try { window.Alpine.destroyTree(mount.firstChild); } catch (_) {}
    }
    mount.innerHTML = '';
  }

  closeBtn.addEventListener('click', hideSandbox);
  document.addEventListener('keydown', (e) => {
    if (e.key === 'Escape' && !overlay.hidden) hideSandbox();
  });

  document.addEventListener('click', (e) => {
    // Practice pills inside the guide (have data-slug)
    let a = e.target.closest('a.practice-pill[data-slug]');
    // Also intercept any anchor pointing at sql_sandbox.html?slug=... (e.g. Resume card)
    if (!a) {
      const raw = e.target.closest('a[href*="sql_sandbox.html?slug="]');
      if (raw) {
        const slug = raw.getAttribute('href').match(/slug=([a-z0-9-]+)/)?.[1];
        if (slug) {
          raw.dataset.slug = slug;
          a = raw;
        }
      }
    }
    if (!a) return;
    if (e.metaKey || e.ctrlKey || e.shiftKey || e.button === 1) return;
    e.preventDefault();
    showSandbox(a.dataset.slug, a);
  });

  window.openSandbox  = showSandbox;
  window.closeSandbox = hideSandbox;

  const qSlug = new URLSearchParams(window.location.search).get('slug');
  if (qSlug) {
    window.addEventListener('load', () => setTimeout(() => showSandbox(qSlug), 200));
  }
})();
</script>
"""
atlas = atlas.replace("</body>", bridge_js + "</body>", 1)

# ---------------------------------------------------------------------------
# 8. Write merged file.
# ---------------------------------------------------------------------------
OUT.write_text(atlas)
print(f"[\u2713] merged atlas rewritten ({len(atlas):,} bytes)")
print(f"    sandbox CSS:  {len(sandbox_css):,} bytes")
print(f"    sandbox body: {len(sandbox_body):,} bytes")
print(f"    sandbox JS:   {len(sandbox_script):,} bytes")
