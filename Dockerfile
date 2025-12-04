# 1. 파이썬 3.9 버전의 가벼운 이미지 사용
FROM python:3.9-slim

# 2. 서버 내 작업 폴더 설정
ENV APP_HOME /app
WORKDIR $APP_HOME

# 3. 필수 파일들 복사 (requirements.txt 먼저 복사해서 캐시 효율 높임)
COPY requirements.txt ./

# 4. 라이브러리 설치
RUN pip install --no-cache-dir -r requirements.txt

# 5. 나머지 소스 코드 복사
COPY . ./

# 6. 업로드 폴더가 없다면 생성 (에러 방지용)
RUN mkdir -p uploads

# 7. 서버 실행 명령어 (Gunicorn 사용)
# app:app 은 "app.py 파일의 app 변수"를 의미함
CMD exec gunicorn --bind :$PORT --workers 1 --threads 8 --timeout 0 app:app