#!/usr/bin/env python3
from __future__ import annotations

import cgi
import json
import os
import re
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
UPLOAD_DIR = Path(os.environ.get('UPLOAD_DIR', BASE_DIR / 'contest_uploads')).resolve()
PORT = int(os.environ.get('PORT', '8000'))
MAX_BYTES = int(os.environ.get('MAX_BYTES', str(2 * 1024 * 1024 * 1024)))  # 2GB default
ALLOWED_EXTENSIONS = {'.mp4', '.mov'}

UPLOAD_DIR.mkdir(parents=True, exist_ok=True)


def slugify(text: str) -> str:
    text = text.strip()
    text = re.sub(r'\s+', '_', text)
    text = re.sub(r'[^0-9A-Za-z가-힣_.-]+', '_', text)
    return text.strip('._-') or 'participant'


def timestamp() -> str:
    return datetime.now().strftime('%Y%m%d_%H%M%S')


class Handler(BaseHTTPRequestHandler):
    def _json(self, code: int, payload: dict):
        body = json.dumps(payload, ensure_ascii=False).encode('utf-8')
        self.send_response(code)
        self.send_header('Content-Type', 'application/json; charset=utf-8')
        self.send_header('Content-Length', str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if self.path in ('/', '/index.html'):
            html = (BASE_DIR / 'upload-contest-page.html').read_bytes()
            self.send_response(200)
            self.send_header('Content-Type', 'text/html; charset=utf-8')
            self.send_header('Content-Length', str(len(html)))
            self.end_headers()
            self.wfile.write(html)
            return
        self.send_error(404, 'Not Found')

    def do_POST(self):
        if self.path != '/upload':
            self.send_error(404, 'Not Found')
            return

        ctype = self.headers.get_content_type()
        if ctype != 'multipart/form-data':
            self._json(400, {'error': 'multipart/form-data가 필요합니다.'})
            return

        content_length = int(self.headers.get('Content-Length', '0'))
        if content_length > MAX_BYTES:
            self._json(413, {'error': f'파일 크기가 너무 큽니다. 제한: {MAX_BYTES} bytes'})
            return

        form = cgi.FieldStorage(fp=self.rfile, headers=self.headers, environ={
            'REQUEST_METHOD': 'POST',
            'CONTENT_TYPE': self.headers['Content-Type'],
        }, keep_blank_values=True)

        submitter = (form.getvalue('submitter') or '').strip()
        contact = (form.getvalue('contact') or '').strip()
        fileitem = form['video'] if 'video' in form else None

        if not submitter:
            self._json(400, {'error': '참가자명 또는 팀명이 필요합니다.'})
            return
        if not fileitem or not getattr(fileitem, 'filename', None):
            self._json(400, {'error': '영상 파일이 필요합니다.'})
            return

        original_name = Path(fileitem.filename).name
        ext = Path(original_name).suffix.lower()
        if ext not in ALLOWED_EXTENSIONS:
            self._json(400, {'error': '허용 형식은 .mp4, .mov 입니다.'})
            return

        safe_name = slugify(submitter)
        saved_as = f'{timestamp()}_{safe_name}{ext}'
        save_path = UPLOAD_DIR / saved_as

        with open(save_path, 'wb') as f:
            while True:
                chunk = fileitem.file.read(1024 * 1024)
                if not chunk:
                    break
                f.write(chunk)

        meta = {
            'saved_as': saved_as,
            'original_name': original_name,
            'submitter': submitter,
            'contact': contact,
            'saved_at': datetime.now().isoformat(timespec='seconds'),
        }
        (UPLOAD_DIR / f'{save_path.stem}.json').write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding='utf-8')
        self._json(200, meta)

    def log_message(self, format, *args):
        print(f"{self.address_string()} - {format % args}")


if __name__ == '__main__':
    print(f'Upload dir: {UPLOAD_DIR}')
    print(f'Listening on http://0.0.0.0:{PORT}')
    ThreadingHTTPServer(('0.0.0.0', PORT), Handler).serve_forever()
