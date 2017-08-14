import vtk
import os
import logging
import slicer
import DeepInfer
from collections import OrderedDict
import json


from base import SliceTrackerSegmentationPluginBase
from ...base import SliceTrackerLogicBase


class SliceTrackerAutomaticSegmentationLogic(SliceTrackerLogicBase):

  DeepLearningStartedEvent =  vtk.vtkCommand.UserEvent + 438
  DeepLearningFinishedEvent = vtk.vtkCommand.UserEvent + 439
  DeepLearningFailedEvent = vtk.vtkCommand.UserEvent + 441
  # DeepLearningStatusChangedEvent = vtk.vtkCommand.UserEvent + 440

  def __init__(self):
    super(SliceTrackerAutomaticSegmentationLogic, self).__init__()
    self.inputVolume = None

  def cleanup(self):
    super(SliceTrackerAutomaticSegmentationLogic, self).cleanup()
    self.inputVolume = None

  def run(self, inputVolume):
    if not inputVolume:
      raise ValueError("No input volume found for initializing prostate segmentation deep learning.")

    self.inputVolume = inputVolume
    self.invokeEvent(self.DeepLearningStartedEvent)
    outputLabel = self._runDocker()

    if outputLabel:
      self.dilateMask(outputLabel)
      self.invokeEvent(self.DeepLearningFinishedEvent, outputLabel)
    else:
      self.invokeEvent(self.DeepLearningFailedEvent)

  def _runDocker(self):
    logic = DeepInfer.DeepInferLogic()
    parameters = DeepInfer.ModelParameters()
    with open(os.path.join(DeepInfer.JSON_LOCAL_DIR, "ProstateSegmenter.json"), "r") as fp:
      j = json.load(fp, object_pairs_hook=OrderedDict)

    iodict = parameters.create_iodict(j)
    dockerName, modelName, dataPath = parameters.create_model_info(j)
    logging.debug(iodict)

    inputs = {
      'InputVolume' : self.inputVolume
    }

    outputLabel = slicer.vtkMRMLLabelMapVolumeNode()
    outputLabel.SetName(self.inputVolume.GetName()+"-label")
    slicer.mrmlScene.AddNode(outputLabel)
    outputs = {'OutputLabel': outputLabel}

    params = dict()
    params['Domain'] = 'BWH_WITHOUT_ERC'
    params['OutputSmoothing'] = 1
    params['ProcessingType'] = 'Fast'
    params['InferenceType'] = 'Single'
    params['verbose'] = 1

    logic.executeDocker(dockerName, modelName, dataPath, iodict, inputs, params)

    if logic.abort:
      return None

    logic.updateOutput(iodict, outputs)

    displayNode = outputLabel.GetDisplayNode()
    displayNode.SetAndObserveColorNodeID(self.session.mpReviewColorNode.GetID())

    return outputLabel


class SliceTrackerAutomaticSegmentationPlugin(SliceTrackerSegmentationPluginBase):

  NAME = "AutomaticSegmentation"
  LogicClass = SliceTrackerAutomaticSegmentationLogic

  def __init__(self):
    super(SliceTrackerAutomaticSegmentationPlugin, self).__init__()
    self.logic.addEventObserver(self.logic.DeepLearningStartedEvent, self._onSegmentationStarted)
    self.logic.addEventObserver(self.logic.DeepLearningFinishedEvent, self._onSegmentationFinished)
    # self.logic.addEventObserver(self.logic.DeepLearningStatusChangedEvent, self.onStatusChanged)
    self.logic.addEventObserver(self.logic.DeepLearningFailedEvent, self._onSegmentationFailed)

  def cleanup(self):
    super(SliceTrackerAutomaticSegmentationPlugin, self).cleanup()
    self.logic.cleanup()

  def setup(self):
    super(SliceTrackerAutomaticSegmentationPlugin, self).setup()

  def onActivation(self):
    if self.getSetting("Use_Deep_Learning") == "true":
      self.startSegmentation()

  def startSegmentation(self):
    self.logic.run(self.session.fixedVolume)

  @vtk.calldata_type(vtk.VTK_OBJECT)
  def _onSegmentationFinished(self, caller, event, labelNode):
    # self.onStatusChanged(None, None, str({'text': "Labelmap prediction created", 'value': 100}))
    super(SliceTrackerAutomaticSegmentationPlugin, self)._onSegmentationFinished(caller, event, labelNode)

  # @vtk.calldata_type(vtk.VTK_STRING)
  # def onStatusChanged(self, caller, event, callData):
  #   from SlicerDevelopmentToolboxUtils.widgets import CustomStatusProgressbar
  #   statusBar = CustomStatusProgressbar()
  #   if not statusBar.visible:
  #     statusBar.show()
  #   import ast
  #   status = ast.literal_eval(str(callData))
  #   self.updateProgressBar(progress=statusBar, text=status["text"].replace("\n", ""), value=status["value"],
  #                          maximum = 100)