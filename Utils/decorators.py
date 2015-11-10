import logging
from functools import wraps


def logmethod(func):
  """ This decorator can used for logging methods without the need of reimplementing log messages again and again.

    Usage:

    @logmethod
    def sub(x,y, switch=False):
      return x -y if not switch else y-x
  """

  logging.basicConfig(level=logging.DEBUG)

  @wraps(func)
  def wrapper(*args, **kwargs):
    logging.debug("Called {} with args {} and kwargs {}".format(func.__name__, args, kwargs))
    return func(*args, **kwargs)

  return wrapper


def onExceptReturnNone(func):

  @wraps(func)
  def wrapper(*args, **kwargs):
    try:
      return func(*args, **kwargs)
    except (IndexError, AttributeError, KeyError):
      return None
  return wrapper