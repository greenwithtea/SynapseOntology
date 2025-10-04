from flask import Flask, request, jsonify, render_template
import google.generativeai as genai
import os
#GEMENI_API_KEY 보안 위한 env리딩 라이브러리 추가
from dotenv import load_dotenv
# rdflib, PyPDF2 추가
import rdflib
import json
from PyPDF2 import PdfReader # PdfReader로 임포트 방식 변경
from docx import Document

# --- 0. 환경 변수 로드 및 초기 설정 ---
load_dotenv() 
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

# Gemini API 설정
genai.configure(api_key=GEMINI_API_KEY)

app = Flask(__name__)
# 파일 업로드 및 다운로드를 위한 폴더 설정
UPLOAD_FOLDER = 'uploads'
DOWNLOAD_FOLDER = 'downloads'
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
os.makedirs(DOWNLOAD_FOLDER, exist_ok=True)


# --- 1. 텍스트 추출 함수 ---
def extract_text_from_file(file_path, file_type):
    """PDF 또는 DOCX 파일에서 텍스트를 추출합니다."""
    text = ""
    try:
        if file_type == "pdf":
            with open(file_path, 'rb') as f:
                reader = PdfReader(f)
                for page in reader.pages:
                    # 빈 페이지 또는 추출 오류를 방지하기 위해 조건문 추가
                    page_text = page.extract_text()
                    if page_text:
                        text += page_text + "\n"
        elif file_type == "docx":
            doc = Document(file_path)
            for para in doc.paragraphs:
                text += para.text + "\n"
        
        # API 호출 제한을 고려하여 텍스트 길이를 제한합니다.
        return text[:30000] 
        
    except Exception as e:
        print(f"텍스트 추출 중 오류 발생: {e}")
        return ""


# --- 2. 기본 라우트 (프론트엔드 로드) ---
@app.route('/')
def index():
    # 수정된 부분: 텍스트 대신 index.html 파일을 찾아 렌더링하도록 지시
    return render_template('index.html') 


# --- 3. 핵심 기능: 파일 분석 및 개념 추출 ---
@app.route('/analyze_file', methods=['POST'])
def analyze_file():
    # 1. 파일 수신 및 유효성 검사
    if 'file' not in request.files:
        return jsonify({"error": "파일이 첨부되지 않았습니다."}), 400
    file = request.files['file']
    if file.filename == '':
        return jsonify({"error": "유효한 파일이 선택되지 않았습니다."}), 400

    file_ext = file.filename.rsplit('.', 1)[1].lower()
    if file_ext not in ['pdf', 'docx']:
        return jsonify({"error": "PDF 또는 DOCX 파일만 지원됩니다."}), 400

    # 파일 저장 및 경로 설정
    file_path = os.path.join(UPLOAD_FOLDER, file.filename)
    file.save(file_path)

    # 2. 텍스트 추출
    extracted_text = extract_text_from_file(file_path, file_ext)

    if not extracted_text:
        return jsonify({"error": "파일에서 텍스트를 추출하지 못했습니다. 파일 형식을 확인하세요."}), 500

    # 3. Gemini API 호출
    prompt = f"""
    아래 텍스트를 분석하여 온톨로지 구축에 필요한 클래스, 속성, 인스턴스 관계를 JSON 형식으로 추출해줘. 
    응답은 반드시 JSON 형식으로만 구성되어야 하며, 다른 설명은 포함하지 마.
    
    텍스트: 
    {extracted_text}
    """
    
    try:
        model = genai.GenerativeModel('gemini-2.0-flash')
        response = model.generate_content(prompt)
        
        # JSON 정제 (마크다운 코드 블록 제거)
        json_output_str = response.text.strip().replace('```json', '').replace('```', '')
        ontology_data = json.loads(json_output_str) # Python 딕셔너리로 변환

        # 4. 프론트엔드로 분석 결과를 JSON 객체로 반환
        return jsonify({"message": "분석 성공", "ontology_data": ontology_data}), 200

    except Exception as e:
        # API 키 오류, JSON 파싱 오류 등을 처리
        return jsonify({"error": f"API 호출 또는 JSON 파싱 오류: {e}"}), 500


if __name__ == '__main__':
    # .env 파일에서 환경 변수를 로드하도록 load_dotenv()가 이미 실행되었으므로 키를 안전하게 사용 가능합니다.
    app.run(debug=True)
