# ScienceON API 개발 가이드

> KISTI ScienceON API Gateway 호출 규격 — **라이브 검증 완료**(공식 매뉴얼 v2.4 + 공식 Python 샘플 기준).
> 공식 매뉴얼·샘플코드 원본은 `reference/`(비공개, gitignore).

## 1. 인증 흐름
```
[1] 인증키로 AES256 암호화 → 토큰 발급(access/refresh)
[2] access_token 으로 데이터 호출(검색/상세)
[3] access 만료 시 refreshToken 으로 재발급 (refresh 만료 시 [1] 재수행)
```

## 2. 토큰 발급 (검증됨)
```
GET https://apigateway.kisti.re.kr/tokenrequest.do?client_id=<CLIENT_ID>&accounts=<enc>
```
- **평문**: `{"datetime":"YYYYMMDDHHMMSS","mac_address":"AA-BB-CC-DD-EE-FF"}` (compact, 공백 제거)
- **암호화**: AES-256-**CBC** / key=인증키(UTF-8 32바이트) / **IV=`jvHJ1EFA0IXBrxxz`(고정 16바이트)** / PKCS7
- **인코딩**: `urlsafe base64` → URL 인코딩 → `accounts`
- **응답(JSON)**: `access_token`, `access_token_expire`, `refresh_token`, `refresh_token_expire`, `client_id`, `issued_at`
- **만료**: Access 2시간 / Refresh 2주
- **재발급**: `GET tokenrequest.do?refreshToken=<RT>&client_id=<ID>` (실패 시 errorCode → 신규 발급)

> 구현: [src/scienceon_mcp/auth.py](../src/scienceon_mcp/auth.py). 고정 IV 는 공식 샘플(AES256Util)로만 확인 가능했음.

## 3. 데이터 호출
```
GET https://apigateway.kisti.re.kr/openapicall.do
    ?client_id=&token=&version=1.0&action=search|browse&target=<티켓>
    &searchQuery={"필드":"검색어"}(URL인코딩)&sortField=&curPage=&rowCount=&include=&grouping=
```
- **검색**: `action=search` + `searchQuery`  /  **상세**: `action=browse` + `cn=<CN>`
- `include=Publisher,Pubyear,Abstract,...`(출력 항목 추가, 선택), `grouping=Y`(그룹핑, 선택)
- 응답: **XML**(UTF-8)

## 4. searchQuery 문법 / 검색필드(searchField)
ARTI 기준(REPORT 등 대체로 공통): `BI` 전체 · `TI` 제목 · `AU` 저자 · `AB` 초록 · `KW` 키워드 ·
`PB` 발행기관 · `PY` 발행년도 · `CN` 문헌번호 · `DI` DOI · `SN` ISSN · `BN` ISBN
- **다중 조건(AND)**: `{"BI":"학습부진","PY":"2020"}`
- **연도 범위**: PY 에 **틸드 `~`** → `{"PY":"2015~2024"}`  ⚠️ 하이픈(`-`)은 0건 반환됨!
- **다건 CN(OR)**: `{"CN":"JAKO...|JAKO...|JAKO..."}` (파이프 `|`)
- **텍스트 OR**: 파이프 `|` 동작(예: `경계선지능|경계선지적기능`). 단 **공백 포함 용어는 토큰 분리로
  과대매칭**(`경계선 지능`→`지능`까지) → 여러 용어 합집합은 수집기 `terms`(용어별 개별검색 후 CN 합집합) 권장.
- **와일드카드 `*`** (동작 확인): 색인 안 되는 토큰을 접두 매칭. 예) `TI 느린*`=205건(정밀).
  `느린` 단독검색은 0건이라 **`느린*` 로만 '느린 학습자'류 회수 가능**.
- ⚠️ **연산자 적용 범위**: `()`·공백(AND)·`!`(NOT)·`""`(구문)는 ScienceON **웹 검색 UI** 도움말 기준이며
  **OpenAPI 엔드포인트·공식 샘플엔 연산자 문서/사용 없음**. 실측상 API에서 신뢰 가능한 건 **`*`·`|`** 뿐
  (`""`·공백 AND 는 무시됨 — 한국어 토큰화). 정밀 필터가 필요하면 **검색 후 `contains` substring 후처리**.
- **정렬 sortField**: `pubyear`(발행일, 기본 내림차순) · `title` · `jtitle` · (미지정 시 정확도)

## 5. 콘텐츠 티켓(target)
| 구독(현재 계정) | 기타(계정/별도) |
|---|---|
| `ARTI` 논문 · `REPORT` 보고서 · `ATT` 동향 · `RESEARCHER` 연구자 · `ORGAN` 연구기관 | `PATENT` `SCENT` `TREND` `SNEWS` `APPLICANT` `AUTHOR` `RESOLVER` `VOLUME` `FUNCTION` `SERVICE` `DDC` `KACADEMY` `RECOMMEND` |

## 6. 응답 XML 구조
```xml
<MetaData>
  <resultSummary><TotalCount>17982</TotalCount><statusCode>200</statusCode></resultSummary>
  <parameterData>...요청 파라미터 에코...</parameterData>
  <recordList>
    <record><item metaCode="CN">JAKO...</item><item metaCode="Title">...</item> ...</record>
  </recordList>
</MetaData>
```
- 레코드는 **`recordList/record` 에만** 존재 — `parameterData` 의 item 을 레코드로 오인 금지(0건 응답 빈레코드 버그 주의).
- 필드는 `item[@metaCode]`. 총건수는 `resultSummary/TotalCount`.

**ARTI 출력 metaCode**: `CN` `DBCode` `JournalId` `Publisher` `JournalName` `ISSN` `ISBN` `VolNo1/2`
`Pubyear` `Pubdate` `Title`(+`Title2` 영문) `Abstract`(+2) `Author`(+2) `Affiliation` `Keyword`(+2)
`DOI` `FulltextURL` `ContentURL` `PageInfo` …

**정규화 매핑**([src/scienceon_mcp/parser.py](../src/scienceon_mcp/parser.py)): control_no=`CN`, title=`Title`,
authors=`Author`, pub_year=`Pubyear`, publisher=`Publisher`, journal=`JournalName`, abstract=`Abstract`,
keywords=`Keyword`, doi=`DOI`, url=`ContentURL`/`FulltextURL`. (원본 전체는 `raw` 보존)

## 7. 오류코드 (발췌)
| 코드 | 의미 |
|------|------|
| E4002 | 필수 항목 미입력 |
| **E4006** | (토큰)accounts 에서 MAC 추출 불가 = **암호화 오류** |
| E4007 / E4008 / E4009 | searchField / target / action 값 오류 |
| E4103 | Access Token 오류·만료 |
| E4104 | 신청정보 미승인 상태 |
| E4105 / E4106 / **E4107** | (토큰) client_id / Refresh Token 오류 / **MAC 불일치** |
| 429 | Too Many Requests(한도 초과) |
- 재시도: 429·5xx 지수 백오프(최대 3회); 4xx 인증/파라미터 오류는 즉시 중단.

## 8. 운영 주의 (대량 수집)
- 트래픽 한도는 제공기관 정책 → 대량 전 helpdesk(080-969-4114, helpdesk@kisti.re.kr) 확인.
- throttle(기본 0.5s)·동시성 1~2·정중한 호출. 토큰 캐시 `~/.scienceon_token_cache.json`.
- 페이지네이션: `TotalCount` 기준 순회 + **새 레코드 0이면 종료**(무한루프 방지), `CN` 중복제거.
- 호출 IP 는 포털 **IP관리**에 등록·활성화 필수(미등록 시 토큰 발급 E4006).
