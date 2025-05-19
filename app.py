from flask import Flask, render_template, request, jsonify
from utils.audio_processor import process_audio
from utils.llm_handler import generate_tasks
import os
import uuid
from werkzeug.utils import secure_filename


app = Flask(__name__)
app.config['UPLOAD_FOLDER'] = 'static/uploads'
app.config['MAX_CONTENT_LENGTH'] = 100 * 1024 * 1024  # 100MB
app.config['ALLOWED_EXTENSIONS'] = {'wav', 'mp3', 'm4a', 'aac', 'flac'}


def allowed_file(filename):
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in app.config['ALLOWED_EXTENSIONS']


# 確保上傳目錄存在
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)


@app.route('/')
def index():
    return render_template('index.html')


@app.route('/upload', methods=['POST'])
def upload_file():
    try:
        if 'file' not in request.files:
            return jsonify({'error': '未上傳檔案'}), 400

        file = request.files['file']
        if file.filename == '':
            return jsonify({'error': '檔案名稱為空'}), 400

        if not allowed_file(file.filename):
            return jsonify({'error': '不支援的檔案格式'}), 400

        # 使用安全的檔案名稱並加上唯一識別碼避免覆蓋
        filename = secure_filename(file.filename)
        filename = f"{uuid.uuid4()}_{filename}"
        save_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        file.save(save_path)

        # 處理音訊
        try:
            transcription = process_audio(save_path)

            # 生成摘要和待辦事項
            summary, todos = generate_tasks(transcription)

            return render_template(
                'result.html',
                summary=summary,
                todos=todos,
                filename=filename
            )
        except Exception as e:
            return jsonify({'error': f'處理音訊時發生錯誤: {str(e)}'}), 500

    except Exception as e:
        return jsonify({'error': f'上傳過程中發生錯誤: {str(e)}'}), 500


if __name__ == '__main__':
    app.run(debug=False, host='0.0.0.0', port=8080)
