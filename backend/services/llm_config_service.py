from dataclasses import dataclass
from typing import Literal

from fastapi import HTTPException
from sqlalchemy.orm import Session

from config import Settings
from models import LLMSetting

LLM_SETTING_ID = "global"
LLM_CONFIG_SOURCES = Literal["database", "env"]


@dataclass
class EffectiveLLMSettings:
    LLM_BASE_URL: str
    LLM_MODEL: str
    LLM_API_KEY: str
    source: LLM_CONFIG_SOURCES


@dataclass
class LLMSettingsSummary:
    base_url: str
    model: str
    api_key_configured: bool
    api_key_masked: str | None
    source: LLM_CONFIG_SOURCES


class LLMConfigurationError(ValueError):
    pass


def mask_api_key(api_key: str | None) -> str | None:
    if not api_key:
        return None
    if len(api_key) <= 8:
        return "*" * len(api_key)
    return f"{api_key[:4]}{'*' * max(4, len(api_key) - 8)}{api_key[-4:]}"


def get_llm_setting(db: Session) -> LLMSetting | None:
    return db.query(LLMSetting).filter(LLMSetting.id == LLM_SETTING_ID).first()


def _is_complete(base_url: str | None, model: str | None, api_key: str | None) -> bool:
    return bool((base_url or "").strip() and (model or "").strip() and (api_key or "").strip())


def resolve_effective_llm_settings(db: Session, settings: Settings) -> EffectiveLLMSettings:
    llm_setting = get_llm_setting(db)
    if llm_setting and _is_complete(llm_setting.base_url, llm_setting.model, llm_setting.api_key):
        return EffectiveLLMSettings(
            LLM_BASE_URL=llm_setting.base_url.strip(),
            LLM_MODEL=llm_setting.model.strip(),
            LLM_API_KEY=llm_setting.api_key.strip(),
            source="database",
        )
    return EffectiveLLMSettings(
        LLM_BASE_URL=settings.LLM_BASE_URL,
        LLM_MODEL=settings.LLM_MODEL,
        LLM_API_KEY=settings.LLM_API_KEY,
        source="env",
    )


def require_effective_llm_settings(db: Session, settings: Settings) -> EffectiveLLMSettings:
    effective = resolve_effective_llm_settings(db, settings)
    missing = []
    if not (effective.LLM_BASE_URL or "").strip():
        missing.append("Base URL")
    if not (effective.LLM_MODEL or "").strip():
        missing.append("模型名称")
    if not (effective.LLM_API_KEY or "").strip():
        missing.append("API Key")
    if missing:
        raise LLMConfigurationError(
            f"模型配置未完成：请填写{'、'.join(missing)}。"
            "可在后台管理的模型配置中保存，或在根目录 .env 中配置后重启服务。"
        )
    return effective


def summarize_effective_llm_settings(db: Session, settings: Settings) -> LLMSettingsSummary:
    effective = resolve_effective_llm_settings(db, settings)
    return LLMSettingsSummary(
        base_url=effective.LLM_BASE_URL,
        model=effective.LLM_MODEL,
        api_key_configured=bool(effective.LLM_API_KEY),
        api_key_masked=mask_api_key(effective.LLM_API_KEY),
        source=effective.source,
    )


def update_llm_settings(
    db: Session,
    settings: Settings,
    base_url: str,
    model: str,
    api_key: str | None,
) -> LLMSettingsSummary:
    trimmed_base_url = base_url.strip()
    trimmed_model = model.strip()
    trimmed_api_key = api_key.strip() if api_key is not None else ""

    if not trimmed_base_url or not trimmed_model:
        raise HTTPException(status_code=400, detail="Base URL 和模型名称不能为空")

    llm_setting = get_llm_setting(db)
    existing_api_key = (llm_setting.api_key or "").strip() if llm_setting else ""
    fallback_api_key = (settings.LLM_API_KEY or "").strip()
    final_api_key = trimmed_api_key or existing_api_key or fallback_api_key
    if not final_api_key:
        raise HTTPException(status_code=400, detail="请填写 API Key 后再保存模型配置")

    if not llm_setting:
        llm_setting = LLMSetting(id=LLM_SETTING_ID)
        db.add(llm_setting)

    llm_setting.base_url = trimmed_base_url
    llm_setting.model = trimmed_model
    llm_setting.api_key = final_api_key
    db.commit()
    db.refresh(llm_setting)

    return LLMSettingsSummary(
        base_url=llm_setting.base_url,
        model=llm_setting.model,
        api_key_configured=bool(llm_setting.api_key),
        api_key_masked=mask_api_key(llm_setting.api_key),
        source="database",
    )
