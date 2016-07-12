import ConfigParser
import inspect, os
from SlicerProstateUtils.mixins import ModuleWidgetMixin


class SliceTrackerConfiguration(ModuleWidgetMixin):

  def __init__(self, moduleName, configFile):
    self.moduleName = moduleName
    self.configFile = configFile
    self.loadConfiguration()

  def loadConfiguration(self):

    config = ConfigParser.RawConfigParser()
    config.read(self.configFile)

    self.setSetting("ZFrame_Registration_Class_Name", config.get('ZFrame Registration', 'class'))
    self.setSetting("COVER_PROSTATE", config.get('Series Descriptions', 'COVER_PROSTATE'))
    self.setSetting("COVER_TEMPLATE", config.get('Series Descriptions', 'COVER_TEMPLATE'))
    self.setSetting("NEEDLE_IMAGE", config.get('Series Descriptions', 'NEEDLE_IMAGE'))
    self.setSetting("VIBE_IMAGE", config.get('Series Descriptions', 'VIBE_IMAGE'))
    self.setSetting("Rating_Enabled", config.getboolean('Rating', 'Enabled'))
    self.setSetting("Maximum_Rating_Score", config.getint('Rating', 'Maximum_Score'))

    colorFilename = config.get('Color File', 'Filename')
    self.setSetting("Color_File_Name", os.path.join(os.path.dirname(inspect.getfile(self.__class__)),
                                                      '../Resources/Colors', colorFilename))