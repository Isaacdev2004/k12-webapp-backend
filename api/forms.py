# forms.py

from django import forms
from django.utils.safestring import mark_safe
from .models import SubjectRecordingVideo

class MCQQuestionImportForm(forms.Form):
    file = forms.FileField(
        label='Select a CSV, Excel, or TXT file',
        help_text='Supported formats: .csv, .xls, .xlsx, .txt'
    )


class MockTestQuestionImportForm(forms.Form):
    file = forms.FileField(
        label='Select a CSV, Excel, or TXT file',
        help_text='Supported formats: .csv, .xls, .xlsx, .txt'
    )


class UploadToR2Widget(forms.TextInput):
    def render(self, name, value, attrs=None, renderer=None):
        input_html = super().render(name, value, attrs, renderer)
        # Use a unique container id per field instance to avoid clashes in inlines
        input_id = attrs.get('id') if attrs else None
        container_id = f"r2-upload-widget-{input_id}" if input_id else "r2-upload-widget"
        html = '''
<div id="{CONTAINER_ID}" class="r2-upload-widget" style="border:1px solid #e5e7eb; padding:12px; border-radius:6px; margin-top:6px;">
    <div style="margin-bottom:8px;">
        <label><strong>Direct Upload to R2 (multipart)</strong></label>
    </div>
    <div style="display:flex; gap:8px; align-items:center; flex-wrap:wrap; margin-bottom:8px;">
        <input type="file" class="r2-file" />
        <input type="text" class="r2-key" placeholder="videos/yourfile.mp4" style="min-width:280px;" />
        <button type="button" class="button r2-start">Upload</button>
        <button type="button" class="button r2-abort" disabled>Abort</button>
    </div>
    <progress class="r2-prog" value="0" max="100" style="width:100%; height:14px;"></progress>
    <div class="r2-log" style="white-space:pre; font-family:monospace; font-size:12px; margin-top:8px;"></div>
    <div style="margin-top:8px; color:#6b7280;">After upload completes, the URL will be written into the field above.</div>
</div>
<script>
(function(){
    const root = document.getElementById('{CONTAINER_ID}');
    if (!root) return;
    const logEl = root.querySelector('.r2-log');
    const prog = root.querySelector('.r2-prog');
    const urlInput = document.getElementById('{INPUT_ID}');
    const keyEl = root.querySelector('.r2-key');
    const fileEl = root.querySelector('.r2-file');
    const startBtn = root.querySelector('.r2-start');
    const abortBtn = root.querySelector('.r2-abort');
    let uploadId = null; let parts = []; let aborted = false;

    function log(msg) { if (logEl) { logEl.textContent += msg + "\n"; logEl.scrollTop = logEl.scrollHeight; } }
    function getCookie(name) {
        const value = `; ${document.cookie}`;
        const parts = value.split(`; ${name}=`);
        if (parts.length === 2) return parts.pop().split(';').shift();
    }
    async function postJson(url, body) {
        const res = await fetch(url, { method: 'POST', headers: { 'Content-Type': 'application/json', 'X-CSRFToken': getCookie('csrftoken') }, body: JSON.stringify(body), credentials: 'include' });
        if (!res.ok) throw new Error(await res.text());
        return res.json();
    }
    async function getJson(url) {
        const res = await fetch(url, { credentials: 'include' });
        if (!res.ok) throw new Error(await res.text());
        return res.json();
    }
    function inferKey(file) {
        const safeName = file.name.replace(/[^a-zA-Z0-9._-]+/g, '_');
        return 'videos/' + safeName;
    }
    async function startUpload() {
        aborted = false; parts = []; if (prog) prog.value = 0; if (logEl) logEl.textContent = '';
        const file = fileEl && fileEl.files && fileEl.files[0];
        if (!file) { alert('Choose a file'); return; }
        if (keyEl && !keyEl.value) keyEl.value = inferKey(file);
        if (startBtn) startBtn.disabled = true; if (abortBtn) abortBtn.disabled = false;
        try {
            const init = await postJson('/api/uploads/multipart/initiate/', { key: keyEl.value, contentType: file.type || 'application/octet-stream' });
            uploadId = init.uploadId; log('Initiated ' + uploadId);
            const chunkSize = 25 * 1024 * 1024; // 25MB
            const totalParts = Math.ceil(file.size / chunkSize);
            for (let partNumber = 1; partNumber <= totalParts; partNumber++) {
                if (aborted) throw new Error('aborted');
                const start = (partNumber - 1) * chunkSize;
                const end = Math.min(start + chunkSize, file.size);
                const blob = file.slice(start, end);
                const q = new URLSearchParams({ key: keyEl.value, uploadId, partNumber });
                const data = await getJson('/api/uploads/multipart/sign-part/?' + q.toString());
                const url = data.url;
                const put = await fetch(url, { method: 'PUT', body: blob });
                if (!put.ok) throw new Error('PUT part failed ' + partNumber);
                const headerETag = (put.headers.get('ETag') || put.headers.get('etag') || '');
                const eTag = headerETag ? headerETag.replaceAll('"','') : null;
                parts.push({ ETag: eTag, PartNumber: partNumber });
                if (prog) prog.value = Math.round((partNumber / totalParts) * 100);
                log('Uploaded part ' + partNumber + '/' + totalParts);
            }
            const done = await postJson('/api/uploads/multipart/complete/', { key: keyEl.value, uploadId, parts });
            log('Completed');
            if (done && done.location && urlInput) { urlInput.value = done.location; }
        } catch (e) {
            log('Error: ' + e.message);
            if (uploadId) { try { await postJson('/api/uploads/multipart/abort/', { key: keyEl.value, uploadId }); log('Aborted'); } catch {} }
        } finally {
            if (startBtn) startBtn.disabled = false; if (abortBtn) abortBtn.disabled = true; uploadId = null;
        }
    }
    if (startBtn) startBtn.addEventListener('click', startUpload);
    if (abortBtn) abortBtn.addEventListener('click', () => { aborted = true; });
    if (fileEl) fileEl.addEventListener('change', (e) => {
        const f = e.target.files && e.target.files[0];
        if (!f || !keyEl) return;
        const safe = f.name.replace(/[^a-zA-Z0-9._-]+/g, '_');
        if (!keyEl.value) keyEl.value = 'videos/' + safe;
    });
})();
</script>
        '''
        if input_id:
            html = html.replace('{INPUT_ID}', input_id)
            html = html.replace('{CONTAINER_ID}', container_id)
        return mark_safe(input_html + html)


class SubjectRecordingVideoAdminForm(forms.ModelForm):
    class Meta:
        model = SubjectRecordingVideo
        fields = ['subject', 'title', 'video_url', 'is_free', 'is_active', 'video_description', 'thumbnail', 'video_duration']
        widgets = {
            'video_url': UploadToR2Widget(attrs={'placeholder': 'https://...'})
        }

class SubjectRecordingVideoInlineForm(forms.ModelForm):
    class Meta:
        model = SubjectRecordingVideo
        # Exclude subject because inline sets it automatically
        fields = ['title', 'video_url', 'is_free', 'is_active', 'video_description', 'thumbnail', 'video_duration']
        widgets = {
            'video_url': UploadToR2Widget(attrs={'placeholder': 'https://...'})
        }