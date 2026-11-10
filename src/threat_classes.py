"""위협 탐지 대상 (YOLOE에 글로 지정).

- prompt: 모델에 넣는 영어 문구
- label: 화면에 보이는 한국어 이름
- threat: 0 = 위협 아님(민간·구분용), 1 = 주의, 2 = 경계, 3 = 위험
- kind: 위협 종류 (보고서 분류)

민간 차량·사람 문구는 위협이 아니지만 함께 넣어 둡니다. 그래야 모델이 민간 차량을 전차로 잘못 고르는 일이 줄어듭니다.
"""

THREAT_CLASSES = [
    {"prompt": "battle tank", "label": "전차", "threat": 3, "kind": "기갑"},
    {"prompt": "armored personnel carrier", "label": "장갑차", "threat": 3, "kind": "기갑"},
    {"prompt": "self-propelled artillery", "label": "자주포", "threat": 3, "kind": "화력"},
    {"prompt": "rocket launcher vehicle", "label": "다연장로켓", "threat": 3, "kind": "화력"},
    {"prompt": "military truck", "label": "군용 트럭", "threat": 2, "kind": "기동·보급"},
    {"prompt": "military jeep", "label": "군용 전술차량", "threat": 2, "kind": "기동·보급"},
    {"prompt": "soldier", "label": "병력(인원)", "threat": 2, "kind": "병력"},
    {"prompt": "roadblock barricade", "label": "도로 장애물", "threat": 3, "kind": "장애물"},
    {"prompt": "destroyed burnt vehicle", "label": "파괴·전소 차량", "threat": 2, "kind": "장애물"},
    {"prompt": "bomb crater", "label": "도로 파손(구덩이)", "threat": 3, "kind": "장애물"},
    {"prompt": "smoke plume", "label": "연기", "threat": 1, "kind": "징후"},
    {"prompt": "fire", "label": "화재", "threat": 1, "kind": "징후"},
    # 구분용 (위협 아님)
    {"prompt": "civilian car", "label": "민간 승용차", "threat": 0, "kind": "민간"},
    {"prompt": "civilian bus", "label": "민간 버스", "threat": 0, "kind": "민간"},
    {"prompt": "civilian pickup truck", "label": "민간 트럭", "threat": 0, "kind": "민간"},
    {"prompt": "civilian pedestrian", "label": "민간인", "threat": 0, "kind": "민간"},
]

THREAT_LEVELS = {0: "없음", 1: "주의", 2: "경계", 3: "위험"}
