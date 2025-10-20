# SynapseOntology
2025 Fall term Graduation Project #2


## 1. 프로젝트 개요

사용자가 논문 파일을 업로드하면 AI를 활용해 텍스트를 분석하고 온톨로지를 자동 구축하여 시각화 및 OWL, RDF, XML 파일 다운로드가 가능한 웹 서비스를 개발합니다.

## 2. 단계별 개발 가이드

### 1) 파일 업로드 및 전처리

- PDF, DOCX 등 파일을 업로드 받고, Python의 PyMuPDF, pdfminer.six, JavaScript의 pdf.js 등으로 텍스트를 추출 및 정제합니다. 혹은 Gemini API를 활용해 텍스트 추출, 개념 및 관계 도출을 진행합니다.

### 2) AI 기반 온톨로지 구축

- 자연어처리(NLP) 모델을 이용해 개체명 인식(NER), 관계 추출, 주요 개념 도출을 진행합니다.
- Python의 rdflib를 사용해 RDF/OWL 포맷으로 온톨로지를 생성합니다.

### 3) 온톨로지 시각화

- d3.js, vis.js, **Cytoscape.js** 같은 JavaScript 시각화 라이브러리를 통해 인터랙티브 그래프를 구현합니다.

### 4) 파일 다운로드 기능

- OWL, RDF, XML 온톨로지 파일을 백엔드에서 생성 후 사용자에게 다운로드를 제공합니다.

### 5) 웹 서비스 배포

- Python Django, Flask, Node.js, React, Vue 등의 기술로 프론트엔드와 백엔드를 구현하며 AWS, GCP 등 클라우드 환경에 배포합니다.

## 3. 플랫폼의 의의 및 가치

- 비정형 논문 데이터를 구조화된 온톨로지로 자동 변환하여 연구자들의 탐색 및 이해를 지원합니다.
- AI 학습 데이터 생성 및 지능형 서비스의 기초 기반을 마련합니다.
- 연구 협업 촉진 및 표준화된 온톨로지 공유를 가능하게 합니다.
- 산업 및 학술 활용도를 높여 경제적 가치 창출에 기여합니다.

## 4. 구체적 구현 방향 및 추천 오픈소스

### 1) 파일 처리 및 텍스트 추출

- PyMuPDF, pdfminer.six, pdf.js / Gemini API 활용

### 2) NLP 및 온톨로지 구축

- SpaCy, Hugging Face Transformers, **rdflib**

### 3) 온톨로지 저장 및 관리

- Neo4j, Stardog

### 4) 온톨로지 시각화

- d3.js, vis.js, Cytoscape.js

### 5) 웹 개발 프레임워크

- React, Vue, Django, Flask, Node.js

### 6) 배포 플랫폼

- AWS, GCP, Azure, Docker, Kubernetes

## 5. 차별점

- 통합 자동화 도구
- 기존 Protegé는 cvs 파일을 자동으로 owl로 바꿔주지 못함
- Gemini, Chatgpt와 같은 LLM 도구들로 owl, xml, rdf 파일을 생성할 수는 있지만, 인터렉티브 시각화를 제공하진 않음.
