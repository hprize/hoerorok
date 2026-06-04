from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

app = FastAPI(title="회로록 API")

# CORS 설정 — Phase 4에서 프런트 도메인으로 교체
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
def health():
    # 서버 상태 확인
    return {"status": "ok"}
