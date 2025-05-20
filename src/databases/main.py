from functools import wraps
from os import getenv

import redis
from pymongo import MongoClient, errors
from redis import Redis, exceptions


def get_mongodb():
    try:
        mongo_client = MongoClient(getenv('MONGO_URI'))
        db = mongo_client[getenv('DB_NAME')]
        yield db
    except errors.ServerSelectionTimeoutError as error:
        raise ValueError('MongoDB connection failed') from error
    except errors.PyMongoError as error:
        raise ValueError('MongoDB connection failed') from error
    finally:
        mongo_client.close()


def get_redis():
    redis_client = None
    try:
        redis_uri = getenv('REDIS_URI')
        redis_client = Redis.from_url(redis_uri)
        return redis_client
    except exceptions.RedisError as error:
        raise ValueError('RedisDB connection failed') from error
    except Exception as error:
        raise ValueError('RedisDB connection failed') from error
    finally:
        if redis_client:
            redis_client.close()


def with_mongodb(func):
    @wraps(func)
    def wrapper(*args, **kwargs):
        mongo_generator = get_mongodb()
        try:
            mongo_db = next(mongo_generator)
            return func(mongo_db, *args, **kwargs)
        except Exception as error:
            raise error
        finally:
            mongo_generator.close()

    return wrapper
