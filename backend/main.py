import base64
import os
import re
import subprocess
import sys
import uuid

import openai
from dotenv import load_dotenv
from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse

# .env 파일에서 환경변수 로드 (로컬 개발용)
load_dotenv()

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
   - Trace the circuit loop(s) carefully before writing code.
   - Each element's .end connects to the next element's start by default.
   - Use .at(node) to branch from an existing node.
6. ALL labels with subscripts, superscripts, or Greek letters MUST be wrapped in $...$
   for matplotlib mathtext rendering.
   CORRECT:   .label('$R_{TH}$')   .label('$V_{TH}$')   .label('$10k\\Omega$')
   INCORRECT: .label('R_{TH}')     .label('V_{TH}')      .label('10kΩ')
   Plain labels without math notation do NOT need $: .label('A')  .label('B')
7. Voltage source selection:
   - If the photo shows a CIRCLE with + and - signs → use elm.SourceV()
   - If the photo shows PARALLEL LINES (battery symbol: long+short line pairs) → use elm.Battery()
8. Use .right() .left() .up() .down() for direction.
9. End with: d.save('output.png', dpi=150, transparent=True)
10. If the image contains equations or formulas, output them separately
    after the code block as: LATEX: <latex string>
    Use standard LaTeX math notation. One formula per line.

--- FEW-SHOT EXAMPLES ---

Example 1: Series loop (battery left, resistor top, load right)
Photo description: Battery on left side (vertical), R1 on top (horizontal), R2 on right side (vertical). Nodes A (top-right) and B (bottom-right).
```python
import schemdraw
import schemdraw.elements as elm
with schemdraw.Drawing() as d:
    bat = d.add(elm.Battery().up().label('$V_s$', loc='left'))
    d.add(elm.Resistor().right().at(bat.end).label('$R_1$', loc='top'))
    d.add(elm.Dot(open=True).label('A', loc='right'))
    d.add(elm.Resistor().down().label('$R_2$', loc='right'))
    d.add(elm.Dot(open=True).label('B', loc='right'))
    d.add(elm.Line().left().to(bat.start))
    d.save('output.png', dpi=150, transparent=True)
```

Example 2: Voltage divider (source left, two resistors in series on right)
Photo description: Voltage source on left (vertical), R1 on top-right (vertical), R2 on bottom-right (vertical). Output taken between R1 and R2.
```python
import schemdraw
import schemdraw.elements as elm
with schemdraw.Drawing() as d:
    src = d.add(elm.SourceV().up().label('$V_{in}$', loc='left'))
    d.add(elm.Line().right().at(src.end))
    r1 = d.add(elm.Resistor().down().label('$R_1$', loc='right'))
    d.add(elm.Dot().label('$V_{out}$', loc='right'))
    r2 = d.add(elm.Resistor().down().label('$R_2$', loc='right'))
    d.add(elm.Line().left().to(src.start))
    d.save('output.png', dpi=150, transparent=True)
```

Example 3: Parallel RLC (source on left, R/L/C in parallel on right)
Photo description: Current source on left (vertical), resistor R, inductor L, and capacitor C all connected in parallel between top and bottom nodes.
```python
import schemdraw
import schemdraw.elements as elm
with schemdraw.Drawing() as d:
    src = d.add(elm.SourceI().up().label('$I_s$', loc='left'))
    top = d.add(elm.Line().right().at(src.end))
    d.add(elm.Resistor().down().at(top.end).label('$R$', loc='right'))
    d.add(elm.Line().right().at(top.end))
    d.add(elm.Inductor().down().label('$L$', loc='right'))
    d.add(elm.Line().right().at(top.end).tox(src.start).right())
    d.add(elm.Capacitor().down().label('$C$', loc='right'))
    d.add(elm.Line().left().at(src.start).tox(src.start))
    d.save('output.png', dpi=150, transparent=True)
```
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

    try:
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
    except openai.AuthenticationError:
        raise HTTPException(500, "OpenAI API 키가 유효하지 않습니다. 서버 환경변수를 확인해주세요.")
    except openai.RateLimitError:
        raise HTTPException(429, "OpenAI API 사용 한도를 초과했습니다. 잠시 후 다시 시도해주세요.")
    except Exception as e:
        raise HTTPException(500, f"AI 호출 중 오류가 발생했습니다: {str(e)}")

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

    # matplotlib GUI 시도 방지 + schemdraw 자동표시 비활성화
    header = (
        "import matplotlib\n"
        "matplotlib.use('Agg')\n"
        "import schemdraw\n"
        "try:\n"
        "    schemdraw.config(show=False)\n"
        "except Exception:\n"
        "    pass\n"
    )
    safe_code = header + safe_code

    # 디버깅: 실행할 코드를 서버 로그에 출력
    print("=== RENDER CODE ===")
    print(safe_code)
    print("===================")

    # subprocess 환경변수에 MPLBACKEND=Agg 명시 (이중 방어)
    env = os.environ.copy()
    env["MPLBACKEND"] = "Agg"

    try:
        # sys.executable: 현재 venv의 python 사용 (schemdraw 등 패키지 보장)
        result = subprocess.run(
            [sys.executable, "-c", safe_code],
            capture_output=True,
            text=True,
            timeout=30,  # 임시로 30초로 늘려 실제 완료 여부 확인
            env=env,
        )
    except subprocess.TimeoutExpired:
        raise HTTPException(408, "렌더링 시간 초과 (30초). 코드를 확인해주세요.")

    # 디버깅: subprocess 결과 로그
    print(f"returncode: {result.returncode}")
    print(f"stdout: {result.stdout[:300]}")
    print(f"stderr: {result.stderr[:300]}")

    if result.returncode != 0:
        raise HTTPException(422, f"코드 실행 오류: {result.stderr[:2000]}")

    if not os.path.exists(output_path):
        raise HTTPException(500, "PNG 파일이 생성되지 않았습니다")

    return FileResponse(
        output_path,
        media_type="image/png",
        headers={"Content-Disposition": f"inline; filename=circuit_{job_id}.png"},
    )
