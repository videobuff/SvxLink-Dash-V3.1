from pathlib import Path
import re,sys,ast
for directory in sys.argv[1:]:
    root=Path(directory)
    p=root/'pi3twe/runtime.py'; s=p.read_text()
    s=''.join(line for line in s.splitlines(keepends=True) if not any(token in line for token in ['from .controller.rf_monitor import', 'from .controller.stream_source import', 'self.stream = StreamSource(', 'self.rf = RfMonitor(']))
    s=s.replace("[('audio', self.mixer), ('stream', self.stream), ('rf', self.rf)]", "[('audio', self.mixer)]")
    ast.parse(s); p.write_text(s)
    p=root/'pi3twe/routes.py'; s=p.read_text()
    if "@bp.put('/api/stream')" in s:
        start=s.index("@bp.put('/api/stream')")
        marker="@bp.get('/dtmf-test')" if "@bp.get('/dtmf-test')" in s[start:] else 'def register(app):'
        end=s.index(marker,start)
        s=s[:start]+s[end:]
    ast.parse(s); p.write_text(s)
    p=root/'static/pi3twe.js'; s=p.read_text()
    s=''.join(line for line in s.splitlines(keepends=True) if not any(token in line for token in ["getElementById('rf-info')", "getElementById('stream-form')", "getElementById('rf-form')", "querySelector('#rf-form", "if (name === 'rf')"]))
    s=s.replace("['logic', 'audio', 'stream', 'rf']", "['logic', 'audio']"); p.write_text(s)
    p=root/'templates/pi3twe.html'; s=p.read_text()
    s=re.sub(r'        <form id="stream-form".*?</form>\n', '',s,flags=re.S)
    s=re.sub(r'    <details class="status-box status-box-soft">\s*<summary>SDR / RF-monitor</summary>.*?</details>\n', '',s,flags=re.S)
    p.write_text(s)
