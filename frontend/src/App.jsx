import { useRef, useState } from "react";

const API_BASE = import.meta.env.VITE_API_BASE ?? "";

const STATUS = {
  IDLE: "idle",
  CONVERTING: "converting",
  RENDERING: "rendering",
  DONE: "done",
  ERROR: "error",
};

const SCHEMDRAW_REF = `# 주요 elements
elm.Resistor()     저항 (R)
elm.Capacitor()    커패시터 (C)
elm.Inductor()     인덕터 (L)
elm.SourceV()      전압원 (원형 +/-)
elm.Battery()      배터리 (평행선)
elm.SourceI()      전류원
elm.Ground()       접지
elm.Dot()          노드점
elm.Line()         도선

# 방향
.right()  .left()  .up()  .down()

# 레이블 (첨자는 반드시 $...$로 감싸기)
.label('$R_{TH}$')
.label('$V_s$', loc='left')
.label('A', loc='top')`;

export default function App() {
  const [status, setStatus] = useState(STATUS.IDLE);
  const [originalUrl, setOriginalUrl] = useState(null);
  const [circuitUrl, setCircuitUrl] = useState(null);
  const [editableCode, setEditableCode] = useState("");
  const [errorMsg, setErrorMsg] = useState("");
  const [refOpen, setRefOpen] = useState(false);
  const fileInputRef = useRef(null);

  // 파일 선택 시 변환 파이프라인 시작
  async function handleFileSelect(e) {
    const file = e.target.files?.[0];
    if (!file) return;

    setOriginalUrl(URL.createObjectURL(file));
    setCircuitUrl(null);
    setEditableCode("");
    setErrorMsg("");
    setStatus(STATUS.CONVERTING);

    try {
      // Step 1: 이미지 → GPT → SchemDraw 코드
      const formData = new FormData();
      formData.append("file", file);
      const convertRes = await fetch(`${API_BASE}/api/convert`, {
        method: "POST",
        body: formData,
      });

      if (!convertRes.ok) {
        let detail;
        try { detail = (await convertRes.json()).detail; }
        catch { detail = await convertRes.text(); }
        throw { status: convertRes.status, detail };
      }

      const { schemdraw_code } = await convertRes.json();

      if (!schemdraw_code) {
        throw { detail: "회로도 코드를 추출하지 못했어요. 사진을 다시 찍어보세요." };
      }

      setEditableCode(schemdraw_code);
      await renderCode(schemdraw_code);
    } catch (e) {
      showError(e);
    }

    e.target.value = "";
  }

  // 코드 → PNG 렌더링 (신규 업로드 및 편집기 재렌더링 공용)
  async function renderCode(code) {
    setStatus(STATUS.RENDERING);
    setErrorMsg("");

    try {
      const renderRes = await fetch(`${API_BASE}/api/render`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ code }),
      });

      if (!renderRes.ok) {
        let detail;
        try { detail = (await renderRes.json()).detail; }
        catch { detail = await renderRes.text(); }
        throw { status: renderRes.status, detail };
      }

      const blob = await renderRes.blob();
      setCircuitUrl(URL.createObjectURL(blob));
      setStatus(STATUS.DONE);
    } catch (e) {
      showError(e);
    }
  }

  // 에러를 한국어로 상태에 저장
  function showError(e) {
    if (e.name === "TypeError") {
      setErrorMsg("서버에 연결할 수 없어요. 인터넷을 확인해주세요.");
    } else if (e.status === 408) {
      setErrorMsg("처리 시간이 너무 오래 걸렸어요. 사진이 복잡하면 나눠서 찍어보세요.");
    } else if (e.status === 422) {
      setErrorMsg(`코드 오류: ${e.detail}\n코드를 수정해보세요.`);
    } else {
      setErrorMsg(e.detail || e.message || "알 수 없는 오류가 발생했어요.");
    }
    setStatus(STATUS.ERROR);
  }

  const isLoading = status === STATUS.CONVERTING || status === STATUS.RENDERING;

  return (
    <div style={styles.container}>
      {/* 헤더 */}
      <h1 style={styles.title}>회로록</h1>
      <p style={styles.subtitle}>회로도 사진을 찍으면 편집 가능한 PNG로 변환해드립니다</p>

      {/* 업로드 버튼 */}
      <label style={{ ...styles.uploadBtn, opacity: isLoading ? 0.5 : 1, cursor: isLoading ? "not-allowed" : "pointer" }}>
        {isLoading ? "처리 중..." : "📷  사진 촬영 / 갤러리에서 선택"}
        <input
          ref={fileInputRef}
          type="file"
          accept="image/*"
          capture="environment"
          onChange={handleFileSelect}
          disabled={isLoading}
          style={{ display: "none" }}
        />
      </label>

      {/* 로딩 상태 */}
      {status === STATUS.CONVERTING && (
        <div style={styles.statusBox}>
          <Spinner />
          <p style={{ margin: 0 }}>GPT가 회로를 분석하고 있어요...<br /><small>(보통 10~20초 소요)</small></p>
        </div>
      )}
      {status === STATUS.RENDERING && (
        <div style={styles.statusBox}>
          <Spinner />
          <p style={{ margin: 0 }}>회로도를 그리는 중...</p>
        </div>
      )}

      {/* 에러 메시지 */}
      {status === STATUS.ERROR && (
        <div style={styles.errorBox}>
          <strong>오류</strong>
          <p style={{ margin: "4px 0 0", whiteSpace: "pre-wrap", fontSize: 13 }}>{errorMsg}</p>
        </div>
      )}

      {/* 결과 영역 */}
      {(originalUrl || circuitUrl) && (
        <div style={styles.resultSection}>
          {/* 원본 + 결과 나란히 */}
          <div style={styles.imageRow}>
            {originalUrl && (
              <div style={styles.imageCard}>
                <p style={styles.imageLabel}>원본 사진</p>
                <img src={originalUrl} alt="원본" style={styles.image} />
              </div>
            )}
            {circuitUrl && (
              <div style={styles.imageCard}>
                <p style={styles.imageLabel}>생성된 회로도</p>
                <img src={circuitUrl} alt="회로도" style={{ ...styles.image, background: "#f5f5f5" }} />
              </div>
            )}
          </div>

          {/* 다운로드 버튼 */}
          {circuitUrl && (
            <a href={circuitUrl} download="circuit.png" style={styles.downloadBtn}>
              PNG 다운로드
            </a>
          )}

          {/* 코드 편집기 */}
          {editableCode !== "" && (
            <div style={styles.editorSection}>
              <p style={styles.editorTitle}>SchemDraw 코드 편집</p>

              {/* SchemDraw 참조 카드 (접힘) */}
              <div style={styles.accordion}>
                <button
                  onClick={() => setRefOpen(o => !o)}
                  style={styles.accordionBtn}
                >
                  {refOpen ? "▲" : "▼"} SchemDraw 빠른 참조
                </button>
                {refOpen && (
                  <pre style={styles.refCard}>{SCHEMDRAW_REF}</pre>
                )}
              </div>

              <textarea
                value={editableCode}
                onChange={e => setEditableCode(e.target.value)}
                style={styles.textarea}
                spellCheck={false}
                autoCapitalize="none"
                autoCorrect="off"
              />

              <button
                onClick={() => renderCode(editableCode)}
                disabled={isLoading}
                style={{ ...styles.rerenderBtn, opacity: isLoading ? 0.5 : 1 }}
              >
                {isLoading ? "렌더링 중..." : "다시 렌더링"}
              </button>
            </div>
          )}
        </div>
      )}
    </div>
  );
}

function Spinner() {
  return (
    <div style={{
      width: 24, height: 24, border: "3px solid #ddd",
      borderTop: "3px solid #333", borderRadius: "50%",
      animation: "spin 0.8s linear infinite", flexShrink: 0,
    }} />
  );
}

const styles = {
  container: {
    padding: "24px 16px",
    fontFamily: "-apple-system, BlinkMacSystemFont, sans-serif",
    maxWidth: 600,
    margin: "0 auto",
    boxSizing: "border-box",
  },
  title: {
    fontSize: 28,
    fontWeight: 700,
    margin: "0 0 4px",
  },
  subtitle: {
    color: "#666",
    margin: "0 0 24px",
    fontSize: 15,
  },
  uploadBtn: {
    display: "flex",
    alignItems: "center",
    justifyContent: "center",
    minHeight: 56,
    padding: "0 24px",
    background: "#111",
    color: "#fff",
    borderRadius: 12,
    fontSize: 17,
    fontWeight: 600,
    userSelect: "none",
    WebkitUserSelect: "none",
    touchAction: "manipulation",
  },
  statusBox: {
    display: "flex",
    alignItems: "center",
    gap: 12,
    marginTop: 20,
    padding: "14px 16px",
    background: "#f7f7f7",
    borderRadius: 10,
    fontSize: 15,
  },
  errorBox: {
    marginTop: 20,
    padding: "14px 16px",
    background: "#fff0f0",
    border: "1px solid #ffb3b3",
    borderRadius: 10,
    fontSize: 15,
    color: "#c00",
  },
  resultSection: {
    marginTop: 24,
  },
  imageRow: {
    display: "flex",
    gap: 12,
    flexWrap: "wrap",
  },
  imageCard: {
    flex: "1 1 140px",
    minWidth: 0,
  },
  imageLabel: {
    fontSize: 13,
    color: "#888",
    margin: "0 0 6px",
    fontWeight: 600,
    textTransform: "uppercase",
    letterSpacing: "0.04em",
  },
  image: {
    width: "100%",
    borderRadius: 8,
    border: "1px solid #e5e5e5",
    touchAction: "pinch-zoom",
  },
  downloadBtn: {
    display: "flex",
    alignItems: "center",
    justifyContent: "center",
    minHeight: 52,
    marginTop: 16,
    background: "#0070f3",
    color: "#fff",
    borderRadius: 12,
    fontSize: 17,
    fontWeight: 600,
    textDecoration: "none",
    touchAction: "manipulation",
  },
  editorSection: {
    marginTop: 24,
    borderTop: "1px solid #e5e5e5",
    paddingTop: 20,
  },
  editorTitle: {
    fontSize: 13,
    fontWeight: 600,
    color: "#888",
    textTransform: "uppercase",
    letterSpacing: "0.04em",
    margin: "0 0 10px",
  },
  accordion: {
    marginBottom: 10,
  },
  accordionBtn: {
    background: "none",
    border: "1px solid #ddd",
    borderRadius: 8,
    padding: "8px 14px",
    fontSize: 14,
    cursor: "pointer",
    width: "100%",
    textAlign: "left",
    color: "#444",
  },
  refCard: {
    marginTop: 6,
    padding: "12px 14px",
    background: "#f7f7f7",
    borderRadius: 8,
    fontSize: 13,
    lineHeight: 1.6,
    overflowX: "auto",
    whiteSpace: "pre",
    color: "#333",
  },
  textarea: {
    width: "100%",
    minHeight: 220,
    padding: "12px 14px",
    fontFamily: "ui-monospace, monospace",
    fontSize: 13,
    lineHeight: 1.6,
    border: "1px solid #ddd",
    borderRadius: 8,
    resize: "vertical",
    boxSizing: "border-box",
    color: "#222",
    background: "#fafafa",
  },
  rerenderBtn: {
    display: "flex",
    alignItems: "center",
    justifyContent: "center",
    minHeight: 48,
    marginTop: 10,
    width: "100%",
    background: "#111",
    color: "#fff",
    border: "none",
    borderRadius: 10,
    fontSize: 16,
    fontWeight: 600,
    cursor: "pointer",
    touchAction: "manipulation",
  },
};

const styleTag = document.createElement("style");
styleTag.textContent = "@keyframes spin { to { transform: rotate(360deg); } }";
document.head.appendChild(styleTag);
