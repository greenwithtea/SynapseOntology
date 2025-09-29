from flask import Flask, request, jsonify
import google.generativeai as genai
import os
#GEMENI_API_KEY 보안 위한 env리딩 라이브러리 추가
from dotenv import load_dotenv
# rdflib, PyPDF2 추가
import rdflib
import json
from PyPDF2 import PdfReader # PdfReader로 임포트 방식 변경
from docx import Document

# --- 1. 기본 설정 ---
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
genai.configure(api_key=GEMINI_API_KEY)

app = Flask(__name__)
# 파일 업로드를 위한 폴더 설정
app.config['UPLOAD_FOLDER'] = 'uploads'
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)


# --- 2. 기본 라우트 (접속 테스트용) ---
@app.route('/')
def index():
    # 프론트엔드 HTML을 이곳에 추후 추가
    return "Ontology Web Tool Server is Running!"


# --- 3. Gemini API 테스트 라우트 ---
@app.route('/test_gemini', methods=['POST'])
def test_gemini():
    # 사용자로부터 텍스트를 받음.
    text_to_analyze = request.json.get('text')
    if not text_to_analyze:
        return jsonify({"error": "No text provided"}), 400

    # Gemini에게 온톨로지 개념 추출을 요청하는 프롬프트
    prompt = f"""
    아래 텍스트를 분석하여 온톨로지 구축에 필요한 클래스, 속성, 인스턴스 관계를 JSON 형식으로 추출해줘. 
    응답은 반드시 JSON 형식으로만 구성되어야 하며, 다른 설명은 포함하지 마.
    
    텍스트: "{text_to_analyze}"
    """
    
    try:
        model = genai.GenerativeModel('gemini-2.0-flash') # 유효한 모델 선택
        response = model.generate_content(prompt)
        
        # 텍스트 응답을 JSON으로 파싱 시도
        json_output = response.text.strip().replace('```json', '').replace('```', '')
        return jsonify({"gemini_response": json_output}), 200

    except Exception as e:
        return jsonify({"error": f"API 호출 실패: {e}"}), 500


if __name__ == '__main__':
    # 서버 실행
    app.run(debug=True)