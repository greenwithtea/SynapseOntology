from flask import Flask, request, jsonify, render_template, session, send_file
import io #io 모듈 추가
import google.generativeai as genai
import os
import json
from docx import Document
from dotenv import load_dotenv
import pdfplumber
import rdflib # rdflib은 현재 다운로드 기능 구현 시 필요
from collections import defaultdict
import traceback # 상세 오류 출력을 위해 추가
import re # 안전한 ID 생성을 위해 추가

# --- 0. 환경 변수 로드 및 초기 설정 ---
load_dotenv()
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

# Gemini API 설정
# API 키가 있는지 확인
if not GEMINI_API_KEY:
    print("오류: GEMINI_API_KEY 환경 변수가 설정되지 않았습니다.")
    # 실제 배포 시에는 여기서 애플리케이션을 종료하거나 기본 키를 사용하도록 처리
    # exit() # 예를 들어, 종료 처리

try:
    genai.configure(api_key=GEMINI_API_KEY)
except Exception as e:
    print(f"Gemini API 설정 오류: {e}")
    # API 키 설정 실패 시 처리

app = Flask(__name__)
app.config['SECRET_KEY'] = 'synapse_key_for_session_2025_2'
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
            # pdfplumber를 사용한 추출
            with pdfplumber.open(file_path) as pdf:
                for page in pdf.pages:
                    page_text = page.extract_text()
                    if page_text:
                        text += page_text + "\n"

        elif file_type == "docx":
            doc = Document(file_path)
            for para in doc.paragraphs:
                text += para.text + "\n"

        return text[:30000] # Gemini API의 토큰 제한 고려

    except Exception as e:
        # 파일 인코딩 오류나 라이브러리 오류 발생 시 터미널에 출력
        print(f"❌ 텍스트 추출 중 치명적 오류 발생: {e}")
        return ""


# --- 2. 기본 라우트 (프론트엔드 로드) ---
@app.route('/')
def index():
    # templates 폴더의 index.html 파일을 렌더링
    return render_template('index.html')


# --- 3. 핵심 기능: 파일 분석 및 개념 추출 (JSON-LD 요청 프롬프트 유지 + 추가 분석 프롬프트) ---
@app.route('/analyze_file', methods=['POST'])
def analyze_file():
    # 1. 파일 수신 및 유효성 검사
    if 'file' not in request.files:
        return jsonify({"error": "파일이 첨부되지 않았습니다."}), 400
    file = request.files['file']
    if file.filename == '':
        return jsonify({"error": "유효한 파일이 선택되지 않았습니다."}), 400

    file_ext = ""
    if '.' in file.filename:
        file_ext = file.filename.rsplit('.', 1)[1].lower()

    if file_ext not in ['pdf', 'docx']:
        return jsonify({"error": "PDF 또는 DOCX 파일만 지원됩니다."}), 400

    file_path = os.path.join(UPLOAD_FOLDER, file.filename)
    try:
        file.save(file_path)
    except Exception as e:
        print(f"파일 저장 오류: {e}")
        return jsonify({"error": f"파일 저장 중 오류 발생: {e}"}), 500

    extracted_text = extract_text_from_file(file_path, file_ext)

    if not extracted_text:
        if os.path.exists(file_path):
            try: os.remove(file_path)
            except Exception as e: print(f"임시 파일 삭제 오류: {e}")
        return jsonify({"error": "파일에서 텍스트를 추출하지 못했습니다."}), 500

    # --- 2. Gemini API 호출  ---
    # ⚠️ 중요: JSON 예시의 중괄호를 {{ }} 로 이스케이프 처리
    prompt = f"""
    Analyze the text below and extract an OWL ontology in JSON-LD format.
    The response MUST be ONLY a JSON-LD array, with no other explanatory text.

    Each element must include the following properties:
    - Classes: `@id` (unique URI), `@type: ["owl:Class"]`
    - Object Properties: `@id`, `@type: ["owl:ObjectProperty"]`, `rdfs:domain` (class URI), `rdfs:range` (class URI), `owl:inverseOf` (URI if applicable)
    - Datatype Properties: `@id`, `@type: ["owl:DatatypeProperty"]`, `rdfs:domain` (class URI), `rdfs:range` (XSD datatype URI, e.g., "xsd:string")
    - Individuals (Instances): `@id`, `@type: ["owl:NamedIndividual", "Specific Class URI"]`, object property values (URI references), and datatype property values (using `@value`).

    All `@id` URIs MUST use the namespace "http://www.semanticweb.org/my-ontology#".

    Example JSON-LD structure:
    [
      {{{{  # 중괄호 두 번 사용
        "@id": "http://www.semanticweb.org/my-ontology#Department",
        "@type": ["owl:Class"]
      }}}}, # 중괄호 두 번 사용
      {{{{
        "@id": "http://www.semanticweb.org/my-ontology#hasProfessor",
        "@type": ["owl:ObjectProperty"],
        "rdfs:domain": [{{{{ "@id": "http://www.semanticweb.org/my-ontology#Department" }}}}],
        "rdfs:range": [{{{{ "@id": "http://www.semanticweb.org/my-ontology#Professor" }}}}]
      }}}},
      {{{{
        "@id": "http://www.semanticweb.org/my-ontology#deptName",
        "@type": ["owl:DatatypeProperty"],
        "rdfs:domain": [{{{{ "@id": "http://www.semanticweb.org/my-ontology#Department" }}}}],
        "rdfs:range": [{{{{ "@id": "xsd:string" }}}}]
      }}}},
      {{{{
        "@id": "http://www.semanticweb.org/my-ontology#Dept001",
        "@type": ["owl:NamedIndividual", "http://www.semanticweb.org/my-ontology#Department"],
        "http://www.semanticweb.org/my-ontology#deptName": [{{{{ "@value": "Computer Science" }}}}],
        "http://www.semanticweb.org/my-ontology#hasProfessor": [{{{{ "@id": "http://www.semanticweb.org/my-ontology#Prof001" }}}}]
      }}}}
    ]

    Text to analyze:
    {extracted_text}
    """
    try:
        if not GEMINI_API_KEY:
             raise ValueError("Gemini API Key is not configured.")

        model = genai.GenerativeModel('gemini-2.0-flash') # 모델 유지
        response = model.generate_content(prompt)

        # JSON 정제 및 파싱
        # 응답 텍스트가 비어있는 경우 처리
        if not response.text:
            raise ValueError("Gemini API returned an empty response.")

        json_output_str = response.text.strip()
        # 마크다운 코드 블록 제거
        if json_output_str.startswith("```json"):
            json_output_str = json_output_str[7:]
        if json_output_str.endswith("```"):
            json_output_str = json_output_str[:-3]

        # --- 세션에 원본 JSON-LD (문자열) 저장 ---
        session['ontology_jsonld_string'] = json_output_str

        # ⚠️ 중요: Gemini 응답이 이제 단순 딕셔너리가 아닌 JSON-LD 배열일 수 있음
        ontology_jsonld = json.loads(json_output_str) # JSON-LD 데이터를 파이썬 리스트/딕셔너리로 변환

        # --- 3. 추가: JSON-LD + PDF 텍스트 기반 온톨로지 분석 요청 (새 프롬프트) ---
        # 분석 프롬프트는 아래처럼 상세히 작성하여 핵심 클래스, 관계, 도메인 활용, 확장 모델, 요약 등을 출력하도록 지시합니다.
        analysis_prompt = f"""
You are an ontology and knowledge-organization expert. Given the extracted document text and the OWL ontology (in JSON-LD) generated from it, produce a concise and structured ontology analysis in Korean and English (Korean primary, English secondary for technical labels).
The output MUST use Markdown formatting (headers, bullet points, bold), but NO code fences. Follow this structure exactly:

1) Title: A single H2 header containing the Korean title followed by the English title, separated by a HTML line break tag (<br>). Format it exactly like: `## [Korean Title] <br> [English Title]`
2) 주요 클래스 (Key Classes): list top-level classes with a short (1-sentence) description for each.
3) 주요 관계 (Key Relationships): list important object properties between classes and what they mean (1-2 sentences each).
4) 도메인별 활용 사례 (Domain Use Cases): at least 3 concrete examples mapping ontology elements to real-world systems (e.g., libraries, music platforms, academic repositories).
5) 제언된 확장 모델 (Proposed Extension Model): practical recommendations (3-5 bullet points) for consortium/policy/data-fusion steps to maximize interoperability and governance.
6) 한줄 요약 (One-line summary): a single Korean sentence summarizing the whole analysis.

Important instructions for the generator:
- Use the provided JSON-LD as the authoritative ontology structure. When naming classes or properties, prefer the local fragment identifier (the part after '#') if available.
- If the JSON-LD lacks explicit labels or domains, infer reasonable names from URIs and the document text, but mark inferred items with "(inferred)".
- Keep the overall analysis readable (use short paragraphs and bullet-like lines). Do not output JSON or machine-readable formats — produce human-readable analysis text.
- If you mention external systems (e.g., ISNI, ORCID, VIAF), explain briefly how they map to ontology classes or properties.

Use Markdown formatting with hierarchical headings:
- Use `##` for the document title. ENSURE you use the `<br>` tag inside the header for the line break.
- Use `###` for each major section
- Use bullet lists (`- item`) inside sections
- Use **bold** to emphasize important ontology terms
Do NOT wrap the response in code fences.


Document text:
{extracted_text}

Generated ontology (JSON-LD):
{json_output_str}

Produce the analysis now.
"""
        analysis_response = model.generate_content(analysis_prompt)
        ontology_analysis = analysis_response.text.strip() if analysis_response and analysis_response.text else ""

        # --- 4. 시각화 데이터 생성 로직 (JSON-LD 파싱) ---
        class_elements = []
        instance_elements = []
        instance_map = {} # 인스턴스 URI와 클래스 URI 매핑
        all_class_uris = set() # 모든 고유 클래스 URI를 저장할 세트
        class_relations_map = defaultdict(lambda: defaultdict(set)) # 클래스 간 관계 추론용

        # 안전한 ID 생성을 위한 함수 정의
        def make_safe_id(uri_or_label):
             # URI에서 '#' 이후 부분 추출, 없으면 전체 사용
            name_part = uri_or_label.split('#')[-1] if isinstance(uri_or_label, str) and '#' in uri_or_label else uri_or_label
            # ID에 사용할 수 없는 문자(공백, :, / 등)를 '_'로 변경
            safe_name = re.sub(r'[^a-zA-Z0-9_-]', '_', str(name_part)) # 문자열로 변환
            # 숫자로 시작하는 ID 방지
            if safe_name and safe_name[0].isdigit():
                safe_name = '_' + safe_name
            # 빈 ID 또는 너무 짧은 ID 방지
            return safe_name if safe_name else f"id_{os.urandom(4).hex()}"

        # --- JSON-LD 파싱 및 데이터 구조화 시작 ---
        for item in ontology_jsonld:
            if not isinstance(item, dict):
                print(f"경고: 유효하지 않은 JSON-LD 요소 (딕셔너리 아님): {item}")
                continue

            item_id = item.get("@id", f"bnode_{os.urandom(4).hex()}")
            item_types = item.get("@type", [])
            if not isinstance(item_types, list):
                print(f"경고: '{item_id}'의 @type이 리스트가 아님: {item_types}")
                item_types = []

            # --- 클래스 URI 수집 (명시적 정의) ---
            if "owl:Class" in item_types:
                if isinstance(item_id, str) and item_id.startswith("http"): # 유효한 URI인지 확인
                    all_class_uris.add(item_id)
                # Subclass 관계도 클래스 URI로 추가
                subclass_of = item.get("rdfs:subClassOf", [])
                if isinstance(subclass_of, list):
                    for parent in subclass_of:
                        if isinstance(parent, dict) and parent.get("@id") and parent.get("@id").startswith("http"):
                             all_class_uris.add(parent.get("@id"))


            # --- 인스턴스 처리 및 클래스 URI 수집 ---
            elif "owl:NamedIndividual" in item_types:
                class_uri = next((t for t in item_types if t != "owl:NamedIndividual" and isinstance(t, str) and t.startswith("http")), None)
                if class_uri:
                    all_class_uris.add(class_uri)
                    instance_map[item_id] = class_uri
                else:
                    default_class_uri = "http://www.semanticweb.org/network-ontology#Unknown"
                    instance_map[item_id] = default_class_uri
                    all_class_uris.add(default_class_uri)
                    print(f"경고: 인스턴스 '{item_id}'에 유효한 클래스 URI가 없습니다. 'Unknown'으로 처리.")

                label = item_id.split('#')[-1] if '#' in item_id else item_id
                class_name = class_uri.split('#')[-1] if class_uri and '#' in class_uri else "Unknown"
                safe_class_name = make_safe_id(class_name) # 안전한 클래스 이름

                node_data = {
                    'id': item_id, # Cytoscape ID는 전체 URI 사용
                    'label': label,
                    'class_name': class_name,
                    'level': 'instance',
                    'uri': item_id
                }

                # 데이터 속성 추가
                for key, values in item.items():
                    if key not in ["@id", "@type"] and isinstance(key, str) and key.startswith("http"):
                        if isinstance(values, list) and values and isinstance(values[0], dict) and "@value" in values[0]:
                            prop_name = key.split('#')[-1] if '#' in key else key
                            safe_prop_name = make_safe_id(prop_name)
                            node_data[safe_prop_name] = values[0]["@value"]

                instance_elements.append({
                    'group': 'nodes',
                    'data': node_data,
                    'classes': f'cls_{safe_class_name}' # CSS 클래스명도 안전하게
                })

            # 속성 정의에서 클래스 URI 수집
            elif "owl:ObjectProperty" in item_types or "owl:DatatypeProperty" in item_types:
                 domain_uris = [d.get("@id") for d in item.get("rdfs:domain", []) if isinstance(d, dict) and d.get("@id")]
                 range_uris = [r.get("@id") for r in item.get("rdfs:range", []) if isinstance(r, dict) and r.get("@id") and not r.get("@id").startswith("xsd:")]
                 all_class_uris.update(u for u in domain_uris if isinstance(u, str) and u.startswith("http"))
                 all_class_uris.update(u for u in range_uris if isinstance(u, str) and u.startswith("http"))


        # 인스턴스 관계 (엣지) 처리 및 클래스 관계 추론
        edge_count_instance = 0
        for item in ontology_jsonld:
            if not isinstance(item, dict): continue
            item_id = item.get("@id")
            item_types = item.get("@type", [])
            if not isinstance(item_types, list): item_types = []

            if "owl:NamedIndividual" in item_types and item_id:
                for prop_uri, targets in item.items():
                    if isinstance(prop_uri, str) and prop_uri.startswith("http") and prop_uri not in ["@id", "@type"]:
                         if isinstance(targets, list) and targets and isinstance(targets[0], dict) and "@id" in targets[0]:
                            prop_label = prop_uri.split('#')[-1] if '#' in prop_uri else prop_uri
                            safe_prop_label = make_safe_id(prop_label) # 안전한 라벨

                            for target_ref in targets:
                                target_id = target_ref.get("@id")
                                if target_id and item_id in instance_map and target_id in instance_map:
                                    safe_source_label = make_safe_id(item_id)
                                    safe_target_label = make_safe_id(target_id)
                                    # 엣지 ID에 랜덤 요소 추가하여 고유성 보장
                                    edge_id = f"e{edge_count_instance}_{safe_source_label}_{safe_target_label}_{os.urandom(2).hex()}"

                                    instance_elements.append({
                                        'group': 'edges',
                                        'data': {
                                            'id': edge_id,
                                            'source': item_id, # Cytoscape ID는 전체 URI
                                            'target': target_id, # Cytoscape ID는 전체 URI
                                            'label': prop_label # 표시는 원래 라벨
                                        }
                                    })
                                    edge_count_instance += 1

                                    source_class_uri = instance_map.get(item_id)
                                    target_class_uri = instance_map.get(target_id)
                                    if source_class_uri and target_class_uri and isinstance(source_class_uri, str) and isinstance(target_class_uri, str):
                                        class_relations_map[source_class_uri][target_class_uri].add(prop_uri)

            # ObjectProperty 정의에서 직접 클래스 관계 추가
            elif "owl:ObjectProperty" in item_types and item_id:
                 domain_uris = [d.get("@id") for d in item.get("rdfs:domain", []) if isinstance(d, dict) and d.get("@id")]
                 range_uris = [r.get("@id") for r in item.get("rdfs:range", []) if isinstance(r, dict) and r.get("@id")]
                 for domain_uri in domain_uris:
                     for range_uri in range_uris:
                          if isinstance(domain_uri, str) and isinstance(range_uri, str) and domain_uri.startswith("http") and range_uri.startswith("http"):
                            class_relations_map[domain_uri][range_uri].add(item_id)


        # --- 클래스 레벨 요소 생성 (보강된 로직) ---
        class_node_map = {} # 클래스 URI와 노드 ID 매핑
        # 모든 수집된 클래스 URI로 노드 생성
        for cls_uri in all_class_uris:
            if isinstance(cls_uri, str) and cls_uri.startswith("http"):
                cls_label = cls_uri.split('#')[-1] if '#' in cls_uri else cls_uri
                if not cls_label: continue

                safe_cls_label = make_safe_id(cls_label)
                cls_node_id = f"cls_{safe_cls_label}" # Cytoscape ID

                class_node_map[cls_uri] = cls_node_id # 맵에 저장
                class_elements.append({
                    'group': 'nodes',
                    'data': {
                        'id': cls_node_id, # 안전한 ID 사용
                        'label': cls_label,
                        'class_name': cls_label,
                        'level': 'class',
                        'uri': cls_uri
                    },
                    'classes': f'cls_{safe_cls_label}' # CSS 클래스 적용
                })

        # 클래스 관계(subClassOf 포함) 및 ObjectProperty 정의를 엣지로 추가
        edge_count_class = 0
        processed_class_edges = set()

        # 1. SubClassOf 관계 추가
        for item in ontology_jsonld:
             if not isinstance(item, dict): continue
             item_id = item.get("@id")
             item_types = item.get("@type", [])
             if not isinstance(item_types, list): item_types = []

             if "owl:Class" in item_types and item_id:
                 subclass_of_list = item.get("rdfs:subClassOf", [])
                 if isinstance(subclass_of_list, list):
                     for parent_ref in subclass_of_list:
                         if isinstance(parent_ref, dict) and parent_ref.get("@id"):
                             parent_uri = parent_ref.get("@id")
                             src_node_id = class_node_map.get(item_id) # 하위 클래스
                             tgt_node_id = class_node_map.get(parent_uri) # 상위 클래스
                             if src_node_id and tgt_node_id:
                                 edge_label = "subClassOf"
                                 # 엣지 ID에 랜덤 요소 추가 (같은 클래스 간 여러 subClassOf 방지 위해)
                                 edge_signature = tuple(sorted((src_node_id, tgt_node_id))) + (edge_label,)
                                 if edge_signature not in processed_class_edges:
                                     safe_src_label = src_node_id.replace('cls_', '')
                                     safe_tgt_label = tgt_node_id.replace('cls_', '')
                                     edge_id = f"sub{edge_count_class}_{safe_src_label}_{safe_tgt_label}_{os.urandom(2).hex()}"
                                     class_elements.append({'group': 'edges','data': {'id': edge_id,'source': src_node_id,'target': tgt_node_id,'label': edge_label}})
                                     processed_class_edges.add(edge_signature)
                                     edge_count_class += 1


        # 2. ObjectProperty 기반 관계 추가 (추론된 것 + 정의된 것)
        for src_cls_uri, targets in class_relations_map.items():
             for tgt_cls_uri, prop_uris in targets.items():
                 if isinstance(src_cls_uri, str) and isinstance(tgt_cls_uri, str):
                     src_node_id = class_node_map.get(src_cls_uri)
                     tgt_node_id = class_node_map.get(tgt_cls_uri)
                     if src_node_id and tgt_node_id:
                         # 관계 라벨 생성 (URI 유효성 검사 추가)
                         prop_labels = sorted([p.split('#')[-1] for p in prop_uris if isinstance(p, str) and '#' in p])
                         edge_label = ", ".join(prop_labels) if prop_labels else "relatedTo" # 라벨 없으면 기본값
                         edge_signature = tuple(sorted((src_node_id, tgt_node_id))) + (edge_label,)
                         if edge_signature not in processed_class_edges:
                             safe_src_label = src_node_id.replace('cls_', '')
                             safe_tgt_label = tgt_node_id.replace('cls_', '')
                             # 엣지 ID에 랜덤 요소 추가
                             edge_id = f"clse{edge_count_class}_{safe_src_label}_{safe_tgt_label}_{os.urandom(2).hex()}"
                             class_elements.append({'group': 'edges','data': {'id': edge_id,'source': src_node_id,'target': tgt_node_id,'label': edge_label}})
                             processed_class_edges.add(edge_signature)
                             edge_count_class += 1

        # 5. 프론트엔드로 분석 결과 및 시각화용 데이터를 JSON 객체로 반환
        return jsonify({
            "message": "분석 성공 및 Ontograf 데이터 생성 완료",
            "ontology_jsonld": ontology_jsonld,
            "class_elements": class_elements,
            "instance_elements": instance_elements,
            "ontology_analysis": ontology_analysis  # 새로 추가된 분석 텍스트
        }), 200

    except ValueError as ve:
         print(f"데이터 처리 오류: {ve}")
         return jsonify({"error": f"데이터 처리 중 오류 발생: {ve}"}), 500
    except json.JSONDecodeError as je:
        print(f"JSON 파싱 오류: {je}")
        try:
            print(f"Gemini 원본 응답:\n{response.text}") # 디버깅을 위해 원본 응답 출력
        except:
            pass
        return jsonify({"error": f"Gemini 응답 JSON 파싱 실패: {je}. 원본 응답을 확인하세요."}), 500
    except Exception as e:
        print(f"❌ API 호출 또는 서버 오류 발생: {e}")
        traceback.print_exc() # 상세 스택 트레이스 출력
        return jsonify({"error": f"API 호출 또는 서버 오류 발생: {e}"}), 500
    finally:
        # 작업 완료 후 임시 파일 삭제
        if os.path.exists(file_path):
            try:
                os.remove(file_path)
            except Exception as e:
                print(f"임시 파일 삭제 오류: {e}")


# --- 4. 파일 다운로드 기능 엔드포인트 (수정됨) ---
@app.route('/download/<string:file_format>')
def download_ontology_file(file_format):
    # 1. 세션에서 분석 결과(JSON-LD 문자열) 가져오기
    jsonld_string = session.get('ontology_jsonld_string', None)
    
    if not jsonld_string:
        return jsonify({"error": "먼저 파일을 분석해야 합니다. 세션 데이터가 없습니다."}), 400

    try:
        # 2. 요청된 파일 형식에 따라 데이터 변환
        
        # JSON-LD 형식 (.jsonld) 요청 시 (원본 그대로 반환)
        if file_format == 'jsonld':
            file_data = io.BytesIO(jsonld_string.encode('utf-8'))
            mimetype = 'application/ld+json'
            filename = 'ontology.jsonld'

        # OWL, RDF, Turtle 형식 요청 시 (rdflib 변환)
        else:
            # rdflib 그래프 생성
            g = rdflib.Graph()
            # 세션의 JSON-LD 문자열을 그래프로 파싱
            # (네임스페이스 바인딩을 위해 원본 JSON-LD 파싱)
            try:
                g.parse(data=jsonld_string, format='json-ld')
            except Exception as e:
                print(f"rdflib 파싱 오류: {e}. 원본 JSON-LD를 확인하세요.")
                # 파싱 실패 시 기본 그래프 반환 (또는 오류 처리)
                pass # 빈 그래프라도 직렬화 시도
            
            # --- 💡 수정된 부분 시작 💡 ---
            
            # 요청 형식에 맞게 직렬화(serialize) 포맷 및 파일 이름 결정
            if file_format == 'owl':
                # OWL (RDF/XML 형식으로 직렬화, 확장자만 .owl)
                output_format = 'xml' 
                mimetype = 'application/rdf+xml'
                filename = 'ontology.owl' # <--- .owl로 변경
                
            elif file_format == 'rdf':
                # RDF/XML 형식
                output_format = 'xml' 
                mimetype = 'application/rdf+xml'
                filename = 'ontology.rdf' # <--- .rdf 유지
                
            # --- 💡 수정된 부분 끝 💡 ---
                
            elif file_format == 'ttl':
                # Turtle 형식
                output_format = 'turtle'
                mimetype = 'text/turtle'
                filename = 'ontology.ttl'
            else:
                return jsonify({"error": "지원하지 않는 형식입니다."}), 400

            # 3. 그래프를 메모리 버퍼에 직렬화
            file_data = io.BytesIO()
            try:
                # rdflib이 지원하는 네임스페이스 자동 바인딩을 위해 'xml' 대신 'pretty-xml' 사용 고려
                if output_format == 'xml':
                    output_format = 'pretty-xml' # 더 읽기 좋은 XML 형식
                    
                g.serialize(destination=file_data, format=output_format, encoding='utf-8')
            except Exception as e:
                 print(f"rdflib 직렬화 오류: {e}")
                 # 직렬화 실패 시 (예: 'pretty-xml' 미지원 시) 기본 'xml'로 재시도
                 file_data = io.BytesIO() # 버퍼 초기화
                 g.serialize(destination=file_data, format='xml', encoding='utf-8')
                 
            file_data.seek(0) # 버퍼의 처음으로 포인터 이동

        # 4. 파일 전송
        return send_file(
            file_data,
            mimetype=mimetype,
            as_attachment=True, # 첨부 파일로 다운로드하도록 설정
            download_name=filename # 사용자에게 보여질 파일 이름
        )

    except Exception as e:
        print(f"❌ 파일 변환/전송 오류: {e}")
        traceback.print_exc()
        return jsonify({"error": f"파일 생성 중 오류 발생: {e}"}), 500

if __name__ == '__main__':
    # debug=True는 개발 중에만 사용하고, 실제 배포 시에는 False로 변경
    app.run(debug=True)
