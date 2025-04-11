# PyCon KR Shop Server
## Setup
### 로컬 인프라 (Docker-Compose)
```bash
make docker-compose-up   # PostgreSQL 컨테이너 시작
make docker-compose-down # PostgreSQL 컨테이너 종료
make docker-compose-rm   # PostgreSQL 컨테이너 삭제
```

### pre-commit hook 설정
본 프로젝트에서는 협업 시 코딩 컨벤션을 준수하기 위해 [pre-commit](https://pre-commit.com/)을 사용합니다.  
pre-commit을 설치하려면 다음을 참고해주세요.

```bash
# pre-commit hook 설치
make hooks-install

# 프로젝트 전체 코드 lint 검사 & format
make lint
```

### Django App
본 프로젝트는 [uv](https://github.com/astral-sh/uv)를 사용합니다. uv를 로컬에 설치한 후 아래 명령을 실행해주세요.
```bash
make local-setup
```

## Run
아래 명령어로 서버를 실행할 수 있습니다.  
`.env.local` 파일은 기본적으로 PostgreSQL 컨테이너를 바라보도록 설정되어 있습니다.
```bash
make local-api
```

마지막으로, Docker로도 API 서버를 실행할 수 있습니다.  
단, 이때 API 서버는 AWS Lambda에서 요청을 처리하는 것과 동일하게 동작하므로, API Gateway가 Lambda를 호출할때처럼 `/functions/function/invocations` route에 특정한 Payload로 요청해야 합니다. (Makefile의 `docker-readyz`를 참고하세요.)  
이 방식은 로컬에서 간단한 smoke test 용도로 유용합니다.
```bash
# Docker 이미지 빌드
make docker-build

# Docker 컨테이너 실행
make docker-run

# Docker 컨테이너 종료
make docker-stop

# Docker 컨테이너 삭제
make docker-rm

# Docker로 간단한 smoke test
make docker-test
```
