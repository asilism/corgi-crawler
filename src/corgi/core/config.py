"""애플리케이션 설정. Spring의 @ConfigurationProperties에 대응."""

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """환경변수(CORGI_ 접두사) 또는 .env 파일에서 값을 읽는다."""

    model_config = SettingsConfigDict(env_prefix="CORGI_", env_file=".env")

    # 쉼표로 구분된 허용 API 키 목록. 비어 있으면 인증을 건너뛴다(로컬 개발 모드).
    api_keys: str = ""
    http_timeout: float = 10.0
    user_agent: str = (
        "Mozilla/5.0 (compatible; CorgiCrawler/0.1; +https://github.com/asilism/corgi-crawler)"
    )
    max_concurrent_fetches: int = 8

    @property
    def allowed_api_keys(self) -> frozenset[str]:
        # pydantic-settings는 list 필드에 JSON 형식을 요구하므로,
        # 운영에서 다루기 쉬운 쉼표 구분 문자열을 받아 여기서 파싱한다.
        return frozenset(key.strip() for key in self.api_keys.split(",") if key.strip())


# lru_cache: 최초 호출 시 한 번만 생성되는 싱글톤 효과 (Spring의 싱글톤 빈과 유사)
@lru_cache
def get_settings() -> Settings:
    return Settings()
