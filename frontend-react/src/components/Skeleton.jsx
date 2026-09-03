// 첫 로딩 자리표시자. 프리미티브 하나만 두고 뷰별 모양은 각 파일에서 조합한다 --
// 뷰마다 전용 스켈레톤 컴포넌트를 만들면 실제 레이아웃이 바뀔 때 같이 썩는다.

export default function Skel({ w = "100%", h = 16, r = 6, style }) {
  return <span className="skel" style={{ width: w, height: h, borderRadius: r, ...style }} />;
}

// 표·목록용 n줄. 폭을 조금씩 줄여 문단처럼 보이게.
export function SkelRows({ n = 6, h = 16 }) {
  return Array.from({ length: n }, (_, i) => <Skel key={i} h={h} w={`${92 - i * 5}%`} />);
}

// 스켈레톤 묶음은 항상 이걸로 감싼다: 막대는 스크린리더에서 감추고 상태만 읽히게.
export function SkelBlock({ children, label = "불러오는 중" }) {
  return (
    <div aria-busy="true">
      <span className="sr-only">{label}</span>
      <div aria-hidden="true">{children}</div>
    </div>
  );
}
