import os
import logging
import json
import vtk
from collections import OrderedDict

import slicer
import DeepInfer

from SlicerDevelopmentToolboxUtils.mixins import  ModuleLogicMixin


class AutomaticSegmentationLogic(ModuleLogicMixin):

  DeepLearningStartedEvent =  vtk.vtkCommand.UserEvent + 438
  DeepLearningFinishedEvent = vtk.vtkCommand.UserEvent + 439
  DeepLearningFailedEvent = vtk.vtkCommand.UserEvent + 441
  # DeepLearningStatusChangedEvent = vtk.vtkCommand.UserEvent + 440

  def __init__(self):
    self.inputVolume = None
    self.colorNode = None

  def cleanup(self):
    self.inputVolume = None

  def run(self, inputVolume, domain, colorNode=None):

    self.colorNode = colorNode
    if not inputVolume:
      raise ValueError("No input volume found for initializing prostate segmentation deep learning.")

    self.inputVolume = inputVolume
    self.invokeEvent(self.DeepLearningStartedEvent)
    outputLabel = self._runDocker(domain)

    if outputLabel:
      self.invokeEvent(self.DeepLearningFinishedEvent, outputLabel)
    else:
      self.invokeEvent(self.DeepLearningFailedEvent)

    return outputLabel

  def _runDocker(self, domain):
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

    outputLabel = slicer.mrmlScene.AddNewNodeByClass("vtkMRMLLabelMapVolumeNode")
    outputLabel.SetName(self.inputVolume.GetName()+"-label")
    outputs = {
      'OutputLabel': outputLabel
    }

    params = dict()
    params['Domain'] = domain
    params['OutputSmoothing'] = 0
    params['ProcessingType'] = 'Fast'
    params['InferenceType'] = 'Single'
    params['verbose'] = 1

    logic.executeDocker(dockerName, modelName, dataPath, iodict, inputs, params)

    if logic.abort:
      return None

    logic.updateOutput(iodict, outputs)

    if self.colorNode:
      displayNode = outputLabel.GetDisplayNode()
      displayNode.SetAndObserveColorNodeID(self.colorNode.GetID())

    return outputLabel