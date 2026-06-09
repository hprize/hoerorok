import base64
import os
import re
import subprocess
import uuid

import openai
from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse

app = FastAPI(title="회로록 API")

# CORS 설정 — Phase 4에서 프런트 도메인으로 교체
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# GPT에게 전달할 시스템 프롬프트 — SchemDraw 코드만 출력하도록 엄격히 지시
SYSTEM_PROMPT = """
You are a circuit diagram transcription expert.
When given a photo of a hand-drawn or whiteboard circuit diagram,
you output ONLY valid SchemDraw Python code that recreates it accurately.

Rules:
1. Output ONLY a Python code block. No explanation, no markdown, just code.
2. Start with: import schemdraw; import schemdraw.elements as elm
3. Use `with schemdraw.Drawing() as d:` context manager.
4. Identify every component: resistor, capacitor, inductor, voltage source,
   current source, ground, wire, op-amp, diode, transistor, switch, etc.
5. Match the topology exactly — the same nodes must be connected.
6. Use .label() to add component values if visible in the photo (e.g., '10kΩ', '100μF').
7. Use .right() .left() .up() .down() for direction.
8. End with: d.save('output.png', dpi=150, transparent=True)
9. If the image contains equations or formulas, output them separately
   after the code block as: LATEX: <latex string>
   Use standard LaTeX math notation. One formula per line.
"""


@app.get("/health")
def health():
    # 서버 상태 확인
    return {"status": "ok"}


@app.post("/api/convert")
async def convert(file: UploadFile = File(...)):
    # 파일 크기 제한 (10MB)
    contents = await file.read()
    if len(contents) > 10 * 1024 * 1024:
        raise HTTPException(400, "파일이 너무 큽니다 (최대 10MB)")

    # 지원 MIME 타입 확인
    allowed = ["image/jpeg", "image/png", "image/webp", "image/heic"]
    if file.content_type not in allowed:
        raise HTTPException(400, "JPG, PNG, WEBP, HEIC 이미지만 지원합니다")

    image_data = base64.standard_b64encode(contents).decode("utf-8")
    # HEIC는 base64 전송 시 jpeg로 처리
    media_type = "image/jpeg" if file.content_type == "image/heic" else file.content_type

    # OPENAI_API_KEY 환경변수 자동 사용
    client = openai.OpenAI()

    response = client.chat.completions.create(
        model="gpt-4.1-mini",
        max_tokens=4096,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {
                "role": "user",
                "content": [
                    {
                        "type": "image_url",
                        "image_url": {"url": f"data:{media_type};base64,{image_data}"},
                    },
                    {
                        "type": "text",
                        "text": "이 사진의 회로도를 SchemDraw 코드로 변환해줘. 수식이 있으면 LaTeX도 출력해줘.",
                    },
                ],
            },
        ],
    )

    raw_output = response.choices[0].message.content
    schemdraw_code, latex_list = parse_ai_output(raw_output)

    return {
        "schemdraw_code": schemdraw_code,
        "latex_formulas": latex_list,
        "raw_output": raw_output,  # 디버깅용
    }


def parse_ai_output(raw: str) -> tuple[str, list[str]]:
    # AI 출력에서 SchemDraw 코드와 LaTeX 수식 분리
    code_match = re.search(r"```python\n(.*?)```", raw, re.DOTALL)
    if not code_match:
        # 코드 블록 마커 없이 import로 시작하는 경우 처리
        code_match = re.search(r"(import schemdraw.*)", raw, re.DOTALL)

    code = code_match.group(1).strip() if code_match else ""
    latex_lines = re.findall(r"^LATEX:\s*(.+)$", raw, re.MULTILINE)

    return code, latex_lines


def is_safe_code(code: str) -> bool:
    # 위험한 패턴 사전 차단 — AI 생성 코드 실행 전 필수 검증
    dangerous = [
        "os.", "sys.", "subprocess", "open(",
        "__import__", "eval(", "exec(", "importlib", "shutil", "socket",
    ]
    return not any(d in code for d in dangerous)


@app.post("/api/render")
async def render_circuit(payload: dict):
    # SchemDraw 코드를 받아 PNG로 렌더링
    code = payload.get("code", "").strip()

    if not code:
        raise HTTPException(400, "코드가 비어있습니다")

    if not is_safe_code(code):
        raise HTTPException(400, "허용되지 않는 코드 패턴이 포함되어 있습니다")

    job_id = str(uuid.uuid4())[:8]
    output_path = f"/tmp/circuit_{job_id}.png"

    # AI가 지정한 저장 경로를 안전한 임시 경로로 강제 교체
    safe_code = re.sub(
        r"d\.save\(['\"].*?['\"](,.*?)?\)",
        f"d.save('{output_path}', dpi=150, transparent=True)",
        code,
    )

    # d.save() 호출이 없는 경우 코드 끝에 추가
    if "d.save(" not in safe_code:
        safe_code += f"\nd.save('{output_path}', dpi=150, transparent=True)"

    try:
        result = subprocess.run(
            ["python3", "-c", safe_code],
            capture_output=True,
            text=True,
            timeout=10,
        )
    except subprocess.TimeoutExpired:
        raise HTTPException(408, "렌더링 시간 초과 (10초). 코드를 확인해주세요.")

    if result.returncode != 0:
        raise HTTPException(422, f"코드 실행 오류: {result.stderr[:500]}")

    if not os.path.exists(output_path):
        raise HTTPException(500, "PNG 파일이 생성되지 않았습니다")

    return FileResponse(
        output_path,
        media_type="image/png",
        headers={"Content-Disposition": f"inline; filename=circuit_{job_id}.png"},
    )
