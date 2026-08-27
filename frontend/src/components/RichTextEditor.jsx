// Lightweight HTML rich-text editor for admin-authored copy (Risk Email
// Templates and the Students at Risk "Log as emailed" modal) — no external
// editor dependency, same "build it small, dependency-free" approach as
// AIChatbox's renderMarkdownLite. A toolbar drives document.execCommand
// (still broadly supported for these basic commands despite being
// deprecated — there is no fully-shipped replacement API yet) over a
// contentEditable surface, plus a raw "HTML Code" toggle for anyone who'd
// rather edit the markup directly.
//
// contentEditable is managed imperatively via a ref, not React's
// dangerouslySetInnerHTML — re-rendering the div's children on every
// keystroke would reset the caret to the start of the field.
import { useRef, useEffect, useState } from 'react';
import DOMPurify from 'dompurify';

const FONT_SIZES = [
  { label: 'Small',   value: '2' },
  { label: 'Normal',  value: '3' },
  { label: 'Medium',  value: '4' },
  { label: 'Large',   value: '5' },
  { label: 'X-Large', value: '6' },
];

const BLOCK_FORMATS = [
  { label: 'Paragraph', value: 'p' },
  { label: 'Heading 1', value: 'h1' },
  { label: 'Heading 2', value: 'h2' },
  { label: 'Heading 3', value: 'h3' },
  { label: 'Quote',     value: 'blockquote' },
];

export default function RichTextEditor({ value, onChange, minHeight = 170, placeholder }) {
  const editorRef = useRef(null);
  const domHtmlRef = useRef(null); // null sentinel forces the initial sync on mount
  const [showCode, setShowCode] = useState(false);

  useEffect(() => {
    // Only push `value` into the DOM when it actually differs from what's
    // already displayed (switching templates, or coming back from HTML
    // Code view) — never on every keystroke, or the caret would jump to
    // the start of the field on each character typed.
    //
    // Sanitized, not raw: `value` can come from a saved template (shared,
    // stored data any Head of Technology / Head of School can create) or
    // from someone typing raw markup in HTML Code view — an unsanitized
    // innerHTML assignment here would execute an event-handler attribute
    // like `onerror=` the instant it's inserted (script tags alone don't
    // run via innerHTML, but that does), the moment anyone reopens that
    // template to edit it.
    if (!showCode && editorRef.current && value !== domHtmlRef.current) {
      const clean = DOMPurify.sanitize(value || '');
      editorRef.current.innerHTML = clean;
      domHtmlRef.current = clean;
    }
  }, [value, showCode]);

  const handleInput = () => {
    if (!editorRef.current) return;
    const html = editorRef.current.innerHTML;
    domHtmlRef.current = html;
    onChange(html);
  };

  const exec = (command, arg = null) => {
    editorRef.current?.focus();
    document.execCommand(command, false, arg);
    handleInput();
  };

  const handleSelectCommand = (command) => (e) => {
    const v = e.target.value;
    e.target.value = '';
    if (v) exec(command, v);
  };

  // Prevents the toolbar button from stealing focus off the editor before
  // execCommand runs — without this, the browser's current selection
  // (what the command should act on) is lost the instant the button is
  // clicked.
  const noFocusSteal = (e) => e.preventDefault();

  return (
    <div style={s.wrap}>
      <div style={s.toolbar}>
        <button type="button" style={s.btn} onMouseDown={noFocusSteal} onClick={() => exec('bold')} title="Bold"><b>B</b></button>
        <button type="button" style={{ ...s.btn, fontStyle: 'italic' }} onMouseDown={noFocusSteal} onClick={() => exec('italic')} title="Italic">I</button>
        <button type="button" style={{ ...s.btn, textDecoration: 'underline' }} onMouseDown={noFocusSteal} onClick={() => exec('underline')} title="Underline">U</button>
        <span style={s.sep} />
        <select style={s.select} defaultValue="" onMouseDown={noFocusSteal} onChange={handleSelectCommand('fontSize')} disabled={showCode}>
          <option value="" disabled>Font Size</option>
          {FONT_SIZES.map(f => <option key={f.value} value={f.value}>{f.label}</option>)}
        </select>
        <select style={s.select} defaultValue="" onMouseDown={noFocusSteal} onChange={handleSelectCommand('formatBlock')} disabled={showCode}>
          <option value="" disabled>Paragraph</option>
          {BLOCK_FORMATS.map(f => <option key={f.value} value={f.value}>{f.label}</option>)}
        </select>
        <span style={s.sep} />
        <button type="button" style={s.btn} onMouseDown={noFocusSteal} onClick={() => exec('insertUnorderedList')} title="Bullet list">• ≡</button>
        <button type="button" style={s.btn} onMouseDown={noFocusSteal} onClick={() => exec('insertOrderedList')} title="Numbered list">1. ≡</button>
        <button
          type="button" style={s.btn} onMouseDown={noFocusSteal}
          onClick={() => { const url = window.prompt('Link URL:'); if (url) exec('createLink', url); }}
          title="Insert link"
        >
          Link
        </button>
        <button type="button" style={s.btn} onMouseDown={noFocusSteal} onClick={() => exec('removeFormat')} title="Clear formatting">Clear</button>
        <span style={{ flex: 1 }} />
        <button
          type="button"
          style={{ ...s.btn, ...(showCode ? s.btnActive : {}) }}
          onClick={() => setShowCode(sc => !sc)}
        >
          {showCode ? 'Rich Text' : 'HTML Code'}
        </button>
      </div>

      {showCode ? (
        <textarea
          style={{ ...s.editor, ...s.codeEditor }}
          value={value || ''}
          onChange={e => { domHtmlRef.current = null; onChange(e.target.value); }}
          placeholder={placeholder}
        />
      ) : (
        <div
          ref={editorRef}
          contentEditable
          suppressContentEditableWarning
          style={{ ...s.editor, minHeight }}
          onInput={handleInput}
          onBlur={handleInput}
        />
      )}
    </div>
  );
}

const s = {
  wrap: { border: '0.5px solid #C5D2DC', borderRadius: 8, overflow: 'hidden' },
  toolbar: {
    display: 'flex', alignItems: 'center', flexWrap: 'wrap', gap: 4,
    padding: '6px 8px', background: '#F8FAFC', borderBottom: '0.5px solid #C5D2DC',
  },
  btn: {
    minWidth: 28, height: 28, padding: '0 8px', borderRadius: 6,
    border: '0.5px solid #DDE4EA', background: '#fff', color: '#1E293B',
    fontSize: 12.5, fontWeight: 600, cursor: 'pointer',
  },
  btnActive: { background: '#2E6E8E', color: '#fff', borderColor: '#2E6E8E' },
  sep: { width: 1, height: 20, background: '#DDE4EA', margin: '0 2px' },
  select: {
    height: 28, padding: '0 6px', borderRadius: 6, border: '0.5px solid #DDE4EA',
    background: '#fff', fontSize: 12, color: '#1E293B', cursor: 'pointer',
  },
  editor: {
    padding: '10px 12px', fontSize: 13, color: '#1E293B',
    outline: 'none', overflowY: 'auto', maxHeight: 360,
  },
  codeEditor: {
    width: '100%', minHeight: 170, boxSizing: 'border-box', border: 'none',
    fontFamily: "'SF Mono','Fira Code',monospace", fontSize: 12.5, resize: 'vertical',
  },
};
