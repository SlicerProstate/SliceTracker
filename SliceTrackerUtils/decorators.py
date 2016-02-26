import logging
from functools import wraps


def logmethod(level=logging.DEBUG):
  """ This decorator can used for logging methods without the need of reimplementing log messages again and again.

    Usage:

    @logmethod()
    def sub(x,y, switch=False):
      return x -y if not switch else y-x

    @logmethod(level=logging.INFO)
    def sub(x,y, switch=False):
      return x -y if not switch else y-x
  """

  def decorator(func):
    @wraps(func)
    def wrapper(*args, **kwargs):
      logging.log(level, "Called {} with args {} and kwargs {}".format(func.__name__, args, kwargs))
      return func(*args, **kwargs)
    return wrapper
  return decorator


def onExceptionReturnNone(func):

  @wraps(func)
  def wrapper(*args, **kwargs):
    try:
      return func(*args, **kwargs)
    except (IndexError, AttributeError, KeyError):
      return None
  return wrapper