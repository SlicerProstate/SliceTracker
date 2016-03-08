import slicer
from mixins import ModuleLogicMixin

class ZFrameRegistrationBase(ModuleLogicMixin):

  ZFRAME_TRANSFORM_NAME = "ZFrameTransform"

  def __init__(self, inputVolume):
    self.inputVolume = inputVolume
    self.outputTransform = None
    self.outputVolume = None

  def getOutputTransformation(self):
    return self.outputTransform

  def getOutputVolume(self):
    return self.outputVolume

  def runRegistration(self):
    raise NotImplementedError


class LineMarkerRegistration(ZFrameRegistrationBase):

  def __init__(self, inputVolume, markerConfigPath):
    super(LineMarkerRegistration, self).__init__(inputVolume)
    self.markerConfigPath = markerConfigPath

  def runRegistration(self):
    volumesLogic = slicer.modules.volumes.logic()
    self.outputVolume = volumesLogic.CreateAndAddLabelVolume(slicer.mrmlScene, self.inputVolume,
                                                             self.inputVolume.GetName() + '-label')
    seriesNumber = self.inputVolume.GetName().split(":")[0]
    self.outputTransform = self.createLinearTransformNode(seriesNumber + "-" + self.ZFRAME_TRANSFORM_NAME)

    params = {'inputVolume': self.inputVolume, 'markerConfigFile': self.markerConfigPath,
              'outputVolume': self.outputVolume, 'markerTransform': self.outputTransform}
    slicer.cli.run(slicer.modules.linemarkerregistration, None, params, wait_for_completion=True)