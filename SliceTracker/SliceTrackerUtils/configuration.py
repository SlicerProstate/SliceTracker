import ConfigParser
import inspect, os


class SliceTrackerConfiguration(object):

  def __init__(self, configFile, scope):
    self.configFile = configFile
    self.scope = scope
    self.loadConfiguration()

  def loadConfiguration(self):
    def getClassFromString(name):
      return getattr(self.scope, name)

    config = ConfigParser.RawConfigParser()
    config.read(self.configFile)

    zFrameRegistrationClassName = config.get('ZFrame Registration', 'class')
    self.zFrameRegistrationClass = getClassFromString(zFrameRegistrationClassName)

    self.COVER_PROSTATE = config.get('Series Descriptions', 'COVER_PROSTATE')
    self.COVER_TEMPLATE = config.get('Series Descriptions', 'COVER_TEMPLATE')
    self.NEEDLE_IMAGE = config.get('Series Descriptions', 'NEEDLE_IMAGE')
    self.VIBE_IMAGE = config.get('Series Descriptions', 'VIBE_IMAGE')

    self.ratingEnabled = config.getboolean('Rating', 'Enabled')
    self.maximumRatingScore = config.getint('Rating', 'Maximum_Score')

    colorFilename = config.get('Color File', 'Filename')
    self.colorFile = os.path.join(os.path.dirname(inspect.getfile(self.__class__)),
                                  '../Resources/Colors', colorFilename)