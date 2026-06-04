import { useEffect, useState } from "react";

const API_BASE = import.meta.env.VITE_API_BASE ?? "";

export default function App() {
  const [serverStatus, setServerStatus] = useState("확인 중...");

  // 마운트 시 백엔드 헬스 체크
  useEffect(() => {
    fetch(`${API_BASE}/health`)
      .then((res) => res.json())
      .then((data) => setServerStatus(data.status === "ok" ? "연결됨 ✓" : "오류"))
      .catch(() => setServerStatus("연결 실패 — 백엔드를 확인해주세요"));
  }, []);

  return (
    <div style={{ padding: 24, fontFamily: "sans-serif", maxWidth: 480, margin: "0 auto" }}>
      <h1 style={{ fontSize: 28, marginBottom: 4 }}>회로록</h1>
      <p style={{ color: "#555", marginTop: 0 }}>
        회로도 사진을 찍어 올리면 편집 가능한 PNG로 변환해드립니다.
      </p>
      <hr />
      <p>
        서버 상태: <strong>{serverStatus}</strong>
      </p>
    </div>
  );
}
