---
title: Military Mobility Situation Assessment
emoji: 🛰️
colorFrom: green
colorTo: gray
sdk: docker
app_port: 7860
pinned: false
license: agpl-3.0
short_description: AI route mobility assessment from public CCTV and ISR imagery
---

# 지능형 기동지원 군사상황 정보판단 프로그램 (공개 시연판)

출발점과 도착점을 정하면, 기동로 위 공개 도로 CCTV와 ISR·UAV 영상을 AI로 분석합니다.
구간별 기동 가능성(Go / Slow-Go / No-Go)과 우회로·조치 건의를 만듭니다.

- **교통:** YOLO11n + ByteTrack으로 차량 탐지·추적 → 정체·돌발상황 판단
- **위협:** YOLOE(글로 대상 지정)로 기갑·화력 차량, 군용 차량, 도로 장애물 등 위협 후보 탐지
- **지점 주변 분석:** 기준 지점 반경 안의 CCTV와 ISR(방위·거리)을 융합해 판단

## 공개 시연판 안내

- **시연 모드로만 동작합니다.**
  - 실시간 모드(국가교통정보센터 API)는 호출 한도 때문에 잠겨 있습니다.
  - 저장해 둔 실제 경부선 CCTV 영상(재생 가능할 때)과 공개 샘플 영상, 공개 훈련 사진(ISR 시연용)을 씁니다.
  - 저장한 실제 CCTV 영상이 만료됐거나 해외 서버에서 열리지 않으면 자동으로 샘플 영상으로 대신합니다.
- **분석 속도:** 무료 CPU라 기동로 분석에 1~3분 걸릴 수 있습니다. 한동안 접속이 없으면 서버가 잠들어 첫 접속이 느립니다.
- **판단 보조용:** AI 분석은 판단 보조용이며 최종 판단은 사람이 합니다.
  - 사격·타격 지정 기능이 없습니다.
  - 얼굴·번호판 인식을 하지 않으며, 사람 영역은 모자이크 처리합니다.

## 출처·라이선스

- 탐지 모델: Ultralytics YOLO11n, YOLOE-26s (AGPL-3.0)
- CCTV 영상: 국가교통정보센터(its.go.kr) CCTV 화상자료 Open API
- 시연용 영상·사진: `data/videos/SOURCES.md`, `data/isr/SOURCES.md` (Wikimedia Commons, Intel 공개 자료)
- 지도: OpenStreetMap, Esri World Imagery / 경로: OSRM
