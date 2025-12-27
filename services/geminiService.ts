
import { GoogleGenAI, Type } from "@google/genai";
import { StockData } from "../types";

const ai = new GoogleGenAI({ apiKey: process.env.API_KEY });

export const fetchStockDataBulk = async (inputNames: string[]): Promise<Partial<StockData>[]> => {
  const prompt = `다음 주식 종목명 또는 약어를 분석해주세요: ${inputNames.join(", ")}. 
  각 종목에 대해 가장 정확한 공식 회사명과 티커(심볼)를 찾으세요. 
  다음 재무 및 시장 지표를 추출하거나 최신 데이터를 바탕으로 추정하세요:
  1. PER (주가수익비율) - 숫자
  2. PBR (주가순자산비율) - 숫자
  3. EPS (주당순이익) - 숫자
  4. 유통주식수 ("1.2억 주"와 같은 한국어 형식)
  5. 최대주주지분율 (백분율 숫자)
  6. 시가총액 ("1.2조 원" 형식)
  7. 거래량 (최근 일평균, "50만 주" 형식)
  8. 거래대금 (최근 일평균, "200억 원" 형식)
  9. 외국인 보유비율 (백분율 숫자)
  10. 분기별 영업이익률 추이 (최근 4분기, 백분율)
  11. 현재 근사 주가 (숫자 형식)`;

  const response = await ai.models.generateContent({
    model: "gemini-3-flash-preview",
    contents: prompt,
    config: {
      responseMimeType: "application/json",
      responseSchema: {
        type: Type.ARRAY,
        items: {
          type: Type.OBJECT,
          properties: {
            symbol: { type: Type.STRING },
            name: { type: Type.STRING },
            currentPrice: { type: Type.NUMBER },
            per: { type: Type.NUMBER },
            pbr: { type: Type.NUMBER },
            eps: { type: Type.NUMBER },
            floatingShares: { type: Type.STRING },
            majorShareholderStake: { type: Type.NUMBER },
            marketCap: { type: Type.STRING },
            tradingVolume: { type: Type.STRING },
            transactionAmount: { type: Type.STRING },
            foreignOwnership: { type: Type.NUMBER },
            quarterlyMargins: {
              type: Type.ARRAY,
              items: {
                type: Type.OBJECT,
                properties: {
                  quarter: { type: Type.STRING },
                  margin: { type: Type.NUMBER }
                },
                required: ["quarter", "margin"]
              }
            }
          },
          required: [
            "symbol", "name", "currentPrice", "per", "pbr", "eps", 
            "floatingShares", "majorShareholderStake", "marketCap", 
            "tradingVolume", "transactionAmount", "foreignOwnership", "quarterlyMargins"
          ]
        }
      }
    }
  });

  try {
    return JSON.parse(response.text);
  } catch (e) {
    console.error("주식 데이터 파싱 실패:", e);
    return [];
  }
};
