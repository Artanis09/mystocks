#!/bin/bash
# .env 파일 위치 (절대 경로)
ENV_PATH="/home/exedev/mystocks/.env"

# .env 파일에서 필요한 값 추출 (주석 제외하고 추출)
get_env_val() {
    grep "^$1=" "$ENV_PATH" | cut -d '=' -f2- | sed 's/\r//g'
}

# KIS_MOCK 여부에 따라 키 선택
IS_MOCK=$(get_env_val "KIS_MOCK")

if [ "$IS_MOCK" = "true" ]; then
    export KIS_API_KEY=$(get_env_val "KIS_APP_KEY")
    export KIS_API_SECRET=$(get_env_val "KIS_APP_SECRET")
    FULL_ACC=$(get_env_val "KIS_ACCOUNT_NO")
    export KIS_TYPE="virtual"
else
    export KIS_API_KEY=$(get_env_val "KIS_REAL_APP_KEY")
    export KIS_API_SECRET=$(get_env_val "KIS_REAL_APP_SECRET")
    FULL_ACC=$(get_env_val "KIS_REAL_ACCOUNT_NO")
    export KIS_TYPE="real"
fi

export KIS_CANO=$(echo $FULL_ACC | cut -d '-' -f1)
export KIS_ACNT_PRDT_CD=$(echo $FULL_ACC | cut -d '-' -f2)

# MCP 서버 실행
npx -y @kis-programming-helper/mcp-server
