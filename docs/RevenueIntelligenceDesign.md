현대 브로커들의 Revenue Intelligence는 대체로 아래 흐름으로 운영됨.

> **Interaction capture → Service/product valuation → Broker vote / wallet allocation → Revenue attribution → Next best action**

즉, 단순히 “거래 수수료를 받았다”가 아니라 **어떤 고객 접점과 서비스가 향후 commission, wallet share, broker vote에 영향을 주는지**를 데이터화합니다.

## 1. 무엇을 데이터로 잡는가

브로커들은 다음 interaction을 CRM/리서치 플랫폼에 구조화합니다.

| 데이터                  | 예시                                                        |
| -------------------- | --------------------------------------------------------- |
| Sales interaction    | 미팅, 콜, 이메일, 세일즈 노트                                        |
| Research consumption | 리포트 열람, 애널리스트 콜, 모델 요청                                    |
| Corporate access     | CEO/CFO 미팅, NDR, 컨퍼런스, 1:1                                |
| Trading interaction  | liquidity inquiry, block interest, algo/DMA 사용            |
| Client feedback      | broker vote, analyst ranking, 서비스 평가                      |
| Revenue outcome      | commission, execution fee, wallet share, research payment |

Singletrack은 sell-side revenue를 이해하는 핵심 개념으로 **interactions, research valuation, broker vote**를 제시하며, capital markets CRM이 sales & trading, research, corporate access 전반의 workflow와 analytics를 통합한다고 설명합니다. ([Singletrack][1])

## 2. Broker vote를 revenue signal로 본다

기관투자자는 브로커의 리서치, 세일즈, corporate access, liquidity access, 알고리즘 품질 등을 평가해 broker vote를 배분합니다. Greenwich는 기관들이 broker vote를 통해 어떤 브로커를 유지할지와 research/advisory service dollars를 어떻게 배분할지 결정한다고 설명합니다. ([그리니치][2])

S&P Global도 standard broker vote가 corporate access events, research, sales 같은 interaction에 대한 투표를 포함한다고 설명합니다. ([S&P Global][3])

즉 브로커 입장에서는:

```text
interaction quality
→ broker vote
→ future wallet allocation
→ commission / research revenue
```

의 흐름을 추적합니다.

## 3. Interaction과 commission의 관계를 분석한다

학술적으로도 이 관계가 확인됩니다. HBS의 broker votes paper는 기관투자자가 broker vote를 미래 commission budget allocation에 사용하며, 이 vote가 애널리스트의 고객 커뮤니케이션 활동에 반응한다고 설명합니다. ([Harvard Business School][4])

RFS의 “Institutional Brokerage Networks” 논문은 commission 데이터를 활용해 기관과 브로커 간 trading network를 매핑하고, 브로커 네트워크가 유동성 공급과 대형 거래의 market impact 완화에 기여한다고 분석합니다. ([OUP Academic][5])

## 4. 실제 시스템은 어떻게 생겼나

전형적인 구조는 이렇습니다.

```text
Sales Notes / Meetings / Calls / Research Reads / Corporate Access
        ↓
Interaction CRM
        ↓
Product Tagging
        ↓
Client Engagement Score
        ↓
Broker Vote / Wallet Share / Commission Data 연결
        ↓
Revenue Attribution & Product ROI
        ↓
Next Best Product / Next Best Action
```

예를 들어 Commcise의 sell-side research management solution은 invoiced research services와 trading revenue를 모니터링하고, contract consumption, interaction reporting, client/broker pack analysis, resource utilization timeline, peer comparison 등을 제공한다고 설명합니다. ([commcise.com][6])

## 5. 무엇을 분석하나

브로커들은 보통 아래 질문에 답하려고 합니다.

### 고객별 분석

```text
이 고객은 어떤 서비스를 소비했는가?
그 이후 commission이 늘었는가?
broker vote가 개선되었는가?
wallet share가 증가했는가?
```

### Product별 분석

```text
Research call이 revenue로 이어졌는가?
Corporate access가 특정 고객군에서 ROI가 높은가?
Block liquidity 제공이 commission uplift를 만들었는가?
```

### 세일즈별 분석

```text
어떤 세일즈 활동이 실제 주문으로 연결되는가?
어떤 고객에게 follow-up해야 하는가?
어떤 product를 제안해야 하는가?
```

## 6. 비용-매출 분석은 어떻게 하나

완전한 인과관계는 어렵기 때문에, 대부분은 **approximate attribution**으로 시작합니다.

예:

```text
Client A가 최근 30일 동안:
- 애널리스트 콜 2회
- 리서치 리포트 5건 열람
- CEO 1:1 미팅 1회
- 세일즈 콜 3회

이후 $40,000 commission 발생
```

초기 시스템은 다음처럼 배분합니다.

| Interaction   | Attribution |
| ------------- | ----------: |
| CEO 1:1       |         35% |
| Analyst call  |         30% |
| Sales call    |         20% |
| Research read |         15% |

그다음 product별 비용을 붙입니다.

```text
Product ROI =
Attributed Revenue / Product Cost
```

이렇게 하면 “어떤 고객에게 어떤 서비스를 제공하는 것이 수익성이 좋은가”를 볼 수 있습니다.

## 7. AI/LLM은 어디에 쓰이나

최근에는 LLM이 특히 세일즈 노트와 콜 메모를 구조화하는 데 쓰입니다.

예:

```text
Raw note:
Client likes SK Hynix but wants CFO access before increasing position.
Concerned about HBM margin sustainability.
```

AI extraction:

```json
{
  "client_interest": ["SK Hynix", "HBM"],
  "product_interest": ["corporate_access", "research"],
  "trade_intent": "conditional",
  "condition": "CFO access before increasing position",
  "objection": ["margin sustainability"],
  "next_best_action": "Arrange CFO/IR meeting and send HBM margin sensitivity note"
}
```

Singletrack은 AI-backed automation으로 interaction capture를 늘리고 administrative effort를 줄인다고 설명합니다. ([Singletrack][7])

## 8. 결론

현대 브로커의 Revenue Intelligence는 다음을 하는 체계입니다.

```text
1. 고객 interaction을 빠짐없이 수집
2. interaction을 product 단위로 태깅
3. broker vote, wallet share, commission과 연결
4. product별 비용과 revenue를 비교
5. 고객별 next best product/action을 추천
```

핵심은 **execution revenue만 보는 것이 아니라, research·corporate access·sales coverage 같은 high-touch service가 미래 commission과 wallet share에 미치는 영향을 계량화하는 것**입니다.
