import enum


class CodeAudiences(str, enum.Enum):
    ACCESS_TOKEN = "ACCESS_TOKEN"
    REFRESH_TOKEN = "REFRESH_TOKEN"
    EMAIL_CHANGE = "EMAIL_CHANGE"
    EMAIL_RESET = "EMAIL_RESET"
    PASSWORD_RESET = "PASSWORD_RESET"
