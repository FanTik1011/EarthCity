from itsdangerous import URLSafeTimedSerializer

def make_serializer(secret_key: str, salt: str) -> URLSafeTimedSerializer:
    return URLSafeTimedSerializer(secret_key=secret_key, salt=salt)
