from flask import Flask, request, jsonify, render_template, send_from_directory
import google.generativeai as genai
import os
import json
from docx import Document
from dotenv import load_dotenv 
import pdfplumber
import rdflib 
# from pdf2image import convert_from_path # OCR 사용 시 필요 (지금은 주석 처리)

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


# --- 1. 텍스트 추출 함수 (pdfplumber 사용) ---
def extract_text_from_file(file_path, file_type):
    """PDF 또는 DOCX 파일에서 텍스트를 추출합니다."""
    text = ""
    try:
        if file_type == "pdf":
            # pdfplumber를 사용한 추출 (안정성 높음)
            with pdfplumber.open(file_path) as pdf:
                for page in pdf.pages:
                    page_text = page.extract_text()
                    if page_text:
                        text += page_text + "\n"
                        # 첫 페이지 텍스트의 일부를 출력하여 추출 성공 여부 확인
                        print(f"페이지 {i+1} 추출 성공: {page_text[:50]}...")
                    else:
                        print(f"페이지 {i+1} 텍스트 추출 실패 (빈 페이지일 수 있음)")
        
        elif file_type == "docx":
            doc = Document(file_path)
            for para in doc.paragraphs:
                text += para.text + "\n"

        # API 호출 제한을 고려하여 텍스트 길이를 제한합니다.
        return text[:30000] 
        
    except Exception as e:
        # 파일 인코딩 오류나 라이브러리 오류 발생 시 터미널에 출력
        print(f"❌ 텍스트 추출 중 치명적 오류 발생: {e}")
        return ""


# --- 2. 기본 라우트 (프론트엔드 로드) ---
@app.route('/')
def index():
    # templates 폴더의 index.html 파일을 렌더링
    return render_template('index.html') 


# --- 3. 핵심 기능: 파일 분석 및 개념 추출 (그래프 데이터 생성 로직 통합) ---
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
        return jsonify({"error": "파일에서 텍스트를 추출하지 못했습니다. (빈 문서이거나 스캔된 이미지 기반 PDF일 수 있습니다.)"}), 500

    # 3. Gemini API 호출
    prompt = f"""
    아래 텍스트를 분석하여 온톨로지 구축에 필요한 클래스, 속성, 인스턴스 관계를 JSON 형식으로 추출해줘. 
    응답은 반드시 JSON 형식으로만 구성되어야 하며, 다른 설명은 포함하지 마.

    예시 JSON 구조는 다음과 같습니다:
    {{
        "classes": ["Author", "Institution"],
        "properties": [
            {{"name": "hasWritten", "domain": "Author", "range": "Paper"}},
            {{"name": "registeredBy", "domain": "Institution", "range": "ISNI"}}
        ],
        "relationships": [
            {{"source": "NationalLibraryOfKorea", "target": "ISNI", "property": "manages"}},
            {{"source": "SeungminLee", "target": "JournalPaper", "property": "hasWritten"}}
        ],
        "instances": [
            {{"name": "NationalLibraryOfKorea", "class": "Institution"}},
            {{"name": "SeungminLee", "class": "Author"}}
        ]
    }}
    
    텍스트: 
    {extracted_text}
    """
    
    try:
        model = genai.GenerativeModel('gemini-2.0-flash')
        response = model.generate_content(prompt)
        
        # JSON 정제 및 파싱
        json_output_str = response.text.strip().replace('```json', '').replace('```', '')
        ontology_data = json.loads(json_output_str) # Python 딕셔너리로 변환

        # --- Cytoscape.js 시각화를 위한 데이터 구조 생성 ---
        graph_elements = []
        node_ids = set() # 노드 ID 중복을 방지하기 위한 세트
        
        # 클래스 정보 맵 생성 (노드 생성 시 클래스 이름 매핑을 위해)
        instance_map = {inst.get('name'): inst.get('class') for inst in ontology_data.get('instances', []) if inst.get('name')}
        
        # 'relationships'를 순회하며 노드와 엣지를 동시에 생성 (가장 확실한 방법)
        for i, rel in enumerate(ontology_data.get('relationships', [])):
            source = rel.get('source')
            target = rel.get('target')
            property_name = rel.get('property')
            
            if source and target and property_name:
                
                # --- Source Node 추가 ---
                if source not in node_ids:
                    class_name = instance_map.get(source, "Unknown")
                    graph_elements.append({
                        'group': 'nodes',
                        'data': {
                            'id': source,
                            'label': source,
                            'class_name': class_name
                        },
                        # 클래스 이름으로 CSS 클래스를 지정하여 프론트엔드에서 스타일 적용
                        'classes': f'cls_{class_name.replace(" ", "_")}' 
                    })
                    node_ids.add(source)
                
                # --- Target Node 추가 ---
                if target not in node_ids:
                    class_name = instance_map.get(target, "Unknown")
                    graph_elements.append({
                        'group': 'nodes',
                        'data': {
                            'id': target,
                            'label': target,
                            'class_name': class_name
                        },
                        'classes': f'cls_{class_name.replace(" ", "_")}'
                    })
                    node_ids.add(target)

                # --- Edge (관계) 추가 ---
                edge_id = f"e{i}_{source}_{target}"
                graph_elements.append({
                    'group': 'edges',
                    'data': {
                        'id': edge_id,
                        'source': source,
                        'target': target,
                        'label': property_name
                    }
                })

        # 4. 프론트엔드로 분석 결과 및 시각화용 데이터를 JSON 객체로 반환
        return jsonify({
            "message": "분석 성공 및 그래프 데이터 생성 완료",
            "ontology_data": ontology_data, # Gemini 원본 JSON
            "graph_elements": graph_elements # Cytoscape.js가 바로 사용할 수 있는 노드/엣지 배열
        }), 200

    except Exception as e:
        # API 호출 오류, JSON 파싱 오류 등을 처리
        print(f"❌ API 호출 중 오류 발생: {e}")
        return jsonify({"error": f"API 호출 또는 JSON 파싱 오류가 발생했습니다. (내용: {e})"}), 500


if __name__ == '__main__':
    # .env 파일에서 환경 변수를 로드하도록 load_dotenv()가 이미 실행되었으므로 키를 안전하게 사용 가능.
    app.run(debug=True)
