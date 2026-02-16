import os
import tempfile
import json
import uuid

try:
    from flask import Flask, request, send_file, jsonify
    import ffmpeg
except ImportError:
    os.system('pip install Flask ffmpeg-python werkzeug')
    from flask import Flask, request, send_file, jsonify
    import ffmpeg

app = Flask(__name__)

@app.route('/')
def index():
    return open('index.html', 'r', encoding='utf-8').read()

@app.route('/render', methods=['POST'])
def render_video():
    try:
        composition_data = request.form.get('composition')
        if not composition_data:
            return "Data komposisi (JSON) tidak ditemukan", 400
        comp = json.loads(composition_data)
    except json.JSONDecodeError:
        return "Format JSON komposisi tidak valid", 400

    dur = float(comp.get('dur', 5))
    canvas_w, canvas_h = 1080, 1920

    with tempfile.TemporaryDirectory() as tmpdir:
        out_path = os.path.join(tmpdir, 'final.mp4')
        
        saved_files = {}
        # 1. Simpan SEMUA file layer (video, gambar, dan audio)
        for layer in comp.get('layers', []):
            if layer['type'] in ['video', 'image', 'audio']:
                file_id = layer['id']
                file_obj = request.files.get(file_id)
                if file_obj:
                    ext = '.mp4' if layer['type'] == 'video' else '.png' if layer['type'] == 'image' else '.mp3'
                    filepath = os.path.join(tmpdir, f"{file_id}{ext}")
                    file_obj.save(filepath)
                    saved_files[file_id] = filepath

        text_overlay_file = request.files.get('text_overlay')
        text_overlay_path = None
        if text_overlay_file:
            text_overlay_path = os.path.join(tmpdir, 'text_overlay.png')
            text_overlay_file.save(text_overlay_path)

        try:
            base = ffmpeg.input(f'color=c=black:s={canvas_w}x{canvas_h}:d={dur}', f='lavfi')
            video_stream = base.video
            audio_inputs = []

            layers = sorted(comp.get('layers', []), key=lambda x: x.get('z', 0))

            # 2. Proses SEMUA layer berdasarkan tipenya
            for layer in layers:
                file_id = layer['id']
                l_type = layer['type']
                
                if file_id in saved_files:
                    filepath = saved_files[file_id]
                    
                    # --- JIKA LAYER ADALAH VISUAL (VIDEO/IMAGE) ---
                    if l_type in ['video', 'image']:
                        if l_type == 'video':
                            start_time = float(layer.get('start', 0))
                            inp = ffmpeg.input(filepath, ss=start_time, t=dur)
                            # Ambil audio dari video jika tidak di-mute
                            if not layer.get('muted', False):
                                 audio_inputs.append(inp.audio)
                        else:
                            inp = ffmpeg.input(filepath, loop=1, t=dur)

                        scale_factor = float(layer.get('s', 1))
                        pos_x = float(layer.get('x', 0))
                        pos_y = float(layer.get('y', 0))
                        orig_w = float(layer.get('origW', 100))
                        orig_h = float(layer.get('origH', 100))
                        
                        target_w = int(orig_w * scale_factor)
                        target_h = int(orig_h * scale_factor)
                        
                        target_w = target_w if target_w % 2 == 0 else target_w + 1
                        target_h = target_h if target_h % 2 == 0 else target_h + 1

                        v_layer = inp.video
                        v_layer = ffmpeg.filter(v_layer, 'scale', target_w, target_h)
                        
                        overlay_x = int(pos_x - (target_w / 2))
                        overlay_y = int(pos_y - (target_h / 2))
                        
                        video_stream = ffmpeg.overlay(video_stream, v_layer, x=overlay_x, y=overlay_y, eof_action='pass')

                    # --- JIKA LAYER ADALAH AUDIO ---
                    elif l_type == 'audio':
                        start_time = float(layer.get('start', 0))
                        inp = ffmpeg.input(filepath, ss=start_time, t=dur)
                        audio_inputs.append(inp.audio)

            # 3. Proses Teks Overlay
            if text_overlay_path and os.path.exists(text_overlay_path):
                text_input = ffmpeg.input(text_overlay_path)
                video_stream = ffmpeg.overlay(video_stream, text_input.video, x=0, y=0)

            # 4. Mixing Semua Audio (dari video unmuted & dari layer audio)
            if len(audio_inputs) > 1:
                audio_stream = ffmpeg.filter(audio_inputs, 'amix', inputs=len(audio_inputs), duration='first')
            elif len(audio_inputs) == 1:
                audio_stream = audio_inputs[0]
            else:
                audio_stream = ffmpeg.input('anullsrc', f='lavfi', t=dur).audio

            # 5. Render Output
            out = ffmpeg.output(
                video_stream, 
                audio_stream, 
                out_path, 
                vcodec='libx264', 
                preset='superfast',
                crf=23,
                pix_fmt='yuv420p',
                acodec='aac', 
                t=dur,
                strict='experimental'
            )
            
            ffmpeg.run(out, overwrite_output=True, quiet=True)

            return send_file(out_path, as_attachment=True, download_name='Shorts_Pro_HD.mp4', mimetype='video/mp4')

        except ffmpeg.Error as e:
            err_msg = e.stderr.decode('utf8') if e.stderr else str(e)
            return jsonify({"error": "Terjadi kesalahan saat rendering FFmpeg", "details": err_msg}), 500
        except Exception as e:
            return jsonify({"error": str(e)}), 500

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8080)