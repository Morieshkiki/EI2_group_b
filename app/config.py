import os

MONGO_DB_NAME = os.getenv('MONGO_DB_NAME', 'exercise_1')
MONGO_DB_ADMIN = os.getenv('MONGO_DB_ADMIN', 'root')
MONGO_DB_PASSWORD = os.getenv('MONGO_DB_PASSWORD', 'example')
MONGO_HOST = os.getenv('MONGO_HOST', '127.0.0.1')
MONGO_PORT = os.getenv('MONGO_PORT', '27017')
MONGO_ADDRESS = os.getenv(
    'MONGO_ADDRESS',
    f'mongodb://{MONGO_DB_ADMIN}:{MONGO_DB_PASSWORD}@{MONGO_HOST}:{MONGO_PORT}/',
)