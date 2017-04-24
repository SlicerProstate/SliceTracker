import vtk
import os
import logging
import slicer
import shutil
import subprocess
import ast
from SlicerDevelopmentToolboxUtils.constants import FileExtension
from SlicerDevelopmentToolboxUtils.widgets import CustomStatusProgressbar

from base import SliceTrackerSegmentationPluginBase
from ...base import SliceTrackerLogicBase


class SliceTrackerAutomaticSegmentationLogic(SliceTrackerLogicBase):

  DeepLearningStartedEvent =  vtk.vtkCommand.UserEvent + 438
  DeepLearningFinishedEvent = vtk.vtkCommand.UserEvent + 439
  DeepLearningStatusChangedEvent = vtk.vtkCommand.UserEvent + 440

  @property
  def inputVolumeFileName(self):
    if not self.inputVolume:
      raise ValueError("InputVolume was not set!")
    return "{}{}".format(self.replaceUnwantedCharacters(self.inputVolume.GetName()), FileExtension.NRRD)

  @property
  def outputLabelFileName(self):
    if not self.inputVolume:
      raise ValueError("InputVolume was not set!")
    return "{}_label{}".format(self.replaceUnwantedCharacters(self.inputVolume.GetName()), FileExtension.NRRD)

  def __init__(self):
    super(SliceTrackerAutomaticSegmentationLogic, self).__init__()
    self.tempDir = os.path.join("/tmp", "SliceTracker")
    self.inputVolume = None
    if not os.path.exists(self.tempDir):
      self.createDirectory(self.tempDir)

  def cleanup(self):
    try:
      shutil.rmtree(self.tempDir)
    except os.error:
      pass
    self.inputVolume = None

  def run(self, inputVolume):
    if not inputVolume:
      raise ValueError("No input volume found for initializing prostate segmentation deep learning.")

    self.inputVolume = inputVolume
    self.saveNodeData(inputVolume, self.tempDir, FileExtension.NRRD, overwrite=True)
    self.invokeEvent(self.DeepLearningStartedEvent)
    self._runDocker()
    success, outputLabel = slicer.util.loadLabelVolume(os.path.join(self.tempDir, self.outputLabelFileName),
                                                       returnNode=True)
    if success:
      self.dilateMask(outputLabel)
      self.smoothSegmentation(outputLabel)
      self.invokeEvent(self.DeepLearningFinishedEvent, outputLabel)

  def _runDocker(self):
    deepInferRemoteDirectory = '/home/deepinfer/data'
    cmd = []
    cmd.extend(('/usr/local/bin/docker', 'run', '-t', '-v')) # TODO: adapt for Windows
    cmd.append(self.tempDir + ':' + deepInferRemoteDirectory)
    cmd.append('deepinfer/prostate-segmenter-cpu')
    cmd.extend(("--InputVolume", os.path.join(deepInferRemoteDirectory, self.inputVolumeFileName)))
    cmd.extend(("--OutputLabel", os.path.join(deepInferRemoteDirectory, self.outputLabelFileName)))
    logging.debug(', '.join(map(str, cmd)).replace(",", ""))
    try:
      p = subprocess.Popen(cmd, stdout=subprocess.PIPE)
      self.invokeEvent(self.DeepLearningStartedEvent)
      progress = 0
      while True:
        progress += 15
        slicer.app.processEvents()
        line = p.stdout.readline()
        if not line:
          break
        self.invokeEvent(self.DeepLearningStatusChangedEvent, str({'text': line, 'value': progress}))
        logging.debug(line)
    except Exception as e:
      logging.debug(e.message)
      raise e


class SliceTrackerAutomaticSegmentationPlugin(SliceTrackerSegmentationPluginBase):

  NAME = "AutomaticSegmentation"
  LogicClass = SliceTrackerAutomaticSegmentationLogic

  def __init__(self):
    super(SliceTrackerAutomaticSegmentationPlugin, self).__init__()

    self.logic.addEventObserver(self.logic.DeepLearningStartedEvent, self.onSegmentationStarted)
    self.logic.addEventObserver(self.logic.DeepLearningFinishedEvent, self.onSegmentationFinished)
    self.logic.addEventObserver(self.logic.DeepLearningStatusChangedEvent, self.onStatusChanged)

  def cleanup(self):
    super(SliceTrackerAutomaticSegmentationPlugin, self).cleanup()
    self.logic.cleanup()

  def setup(self):
    self.startAutomaticSegmentationButton = self.createButton("Run")
    # self.layout().addWidget(self.startAutomaticSegmentationButton)

  def setupConnections(self):
    self.startAutomaticSegmentationButton.clicked.connect(self.startSegmentation)

  def onActivation(self):
    if self.getSetting("Use_Deep_Learning") == "true":
      self.startSegmentation()

  def startSegmentation(self):
    self.logic.run(self.session.fixedVolume)

  @vtk.calldata_type(vtk.VTK_OBJECT)
  def onSegmentationFinished(self, caller, event, labelNode):
    self.onStatusChanged(None, None, str({'text': "Labelmap prediction created", 'value': 100}))
    super(SliceTrackerAutomaticSegmentationPlugin, self).onSegmentationFinished(caller, event, labelNode)

  @vtk.calldata_type(vtk.VTK_STRING)
  def onStatusChanged(self, caller, event, callData):
    statusBar = CustomStatusProgressbar()
    if not statusBar.visible:
      statusBar.show()
    status = ast.literal_eval(str(callData))
    self.updateProgressBar(progress=statusBar, text=status["text"].replace("\n", ""), value=status["value"],
                           maximum = 100)