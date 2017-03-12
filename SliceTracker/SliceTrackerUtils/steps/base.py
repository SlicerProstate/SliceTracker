import logging, os
import qt, vtk, slicer
from abc import ABCMeta, abstractmethod

from ..session import SliceTrackerSession

from SlicerProstateUtils.decorators import logmethod, beforeRunProcessEvents
from SlicerProstateUtils.mixins import ModuleLogicMixin, ModuleWidgetMixin, GeneralModuleMixin
from ..constants import SliceTrackerConstants

class StepBase(GeneralModuleMixin):

  MODULE_NAME = "SliceTracker"

  def __init__(self):
    self.modulePath = self.getModulePath()
    self.session = SliceTrackerSession()

  def getModulePath(self):
    return os.path.dirname(slicer.util.modulePath(self.MODULE_NAME))

  def getSetting(self, setting, moduleName=None, default=None):
    return GeneralModuleMixin.getSetting(self, setting, moduleName=self.MODULE_NAME, default=default)

  def setSetting(self, setting, value, moduleName=None):
    return GeneralModuleMixin.setSetting(self, setting, value, moduleName=self.MODULE_NAME)


class SliceTrackerStepLogic(StepBase, ModuleLogicMixin):

  __metaclass__ = ABCMeta

  def __init__(self):
    StepBase.__init__(self)
    self.resourcesPath = os.path.join(self.modulePath, "Resources")
    self.scalarVolumePlugin = slicer.modules.dicomPlugins['DICOMScalarVolumePlugin']()
    self.volumesLogic = slicer.modules.volumes.logic()

  @abstractmethod
  def cleanup(self):
    pass

  def getOrCreateVolumeForSeries(self, series):
    try:
      volume = self.session.alreadyLoadedSeries[series]
    except KeyError:
      files = self.session.loadableList[series]
      loadables = self.scalarVolumePlugin.examine([files])
      success, volume = slicer.util.loadVolume(files[0], returnNode=True)
      volume.SetName(loadables[0].name)
      self.session.alreadyLoadedSeries[series] = volume
    return volume


class SliceTrackerStep(qt.QWidget, StepBase, ModuleWidgetMixin):

  ActivatedEvent = vtk.vtkCommand.UserEvent + 150
  DeactivatedEvent = vtk.vtkCommand.UserEvent + 151

  NAME = None
  LogicClass = None
  viewSettingButtons = []

  @property
  def active(self):
    return self._activated

  @active.setter
  def active(self, value):
    if self.active == value:
      return
    self._activated = value
    logging.debug("%s %s" % ("activated" if self.active else "deactivate", self.NAME))
    self.invokeEvent(self.ActivatedEvent if self.active else self.DeactivatedEvent)
    if self.active:
      self.layoutManager.layoutChanged.connect(self.onLayoutChanged)
      self.onActivation()
    else:
      self.layoutManager.layoutChanged.disconnect(self.onLayoutChanged)
      self.onDeactivation()

  def __init__(self):
    qt.QWidget.__init__(self)
    StepBase.__init__(self)
    self._activated = False
    self.parameterNode.SetAttribute("Name", self.NAME)
    if self.LogicClass:
      self.logic = self.LogicClass()
    self.setLayout(qt.QGridLayout())
    self.setupIcons()
    self.setup()
    self.setupAdditionalViewSettingButtons()
    self.setupSessionObservers()
    self.setupSliceWidgets()
    self.setupConnections()

  def __del__(self):
    self.removeEventObservers()

  def setupIcons(self):
    pass

  def cleanup(self):
    raise NotImplementedError("This method needs to be implemented for %s" % self.NAME)

  def setup(self):
    NotImplementedError("This method needs to be implemented for %s" % self.NAME)

  def setupConnections(self):
    NotImplementedError("This method needs to be implemented for %s" % self.NAME)

  def onLayoutChanged(self):
    raise NotImplementedError("This method needs to be implemented for %s" % self.NAME)

  def setupSessionObservers(self):
    self.session.addEventObserver(self.session.NewCaseStartedEvent, self.onNewCaseStarted)
    self.session.addEventObserver(self.session.CloseCaseEvent, self.onCaseClosed)
    self.session.addEventObserver(self.session.IncomingDataSkippedEvent, self.onIncomingDataSkipped)
    self.session.addEventObserver(self.session.NewImageDataReceivedEvent, self.onNewImageDataReceived)
    self.session.addEventObserver(self.session.CoverTemplateReceivedEvent, self.onCoverTemplateReceived)
    self.session.addEventObserver(self.session.ZFrameRegistrationSuccessfulEvent, self.onZFrameRegistrationSuccessful)
    self.session.addEventObserver(self.session.CurrentSeriesChangedEvent, self.onCurrentSeriesChanged)
    self.session.addEventObserver(self.session.SuccessfullyLoadedMetadataEvent, self.onLoadingMetadataSuccessful)

  def removeSessionEventObservers(self):
    self.session.removeEventObserver(self.session.NewCaseStartedEvent, self.onNewCaseStarted)
    self.session.removeEventObserver(self.session.CloseCaseEvent, self.onCaseClosed)
    self.session.removeEventObserver(self.session.IncomingDataSkippedEvent, self.onIncomingDataSkipped)
    self.session.removeEventObserver(self.session.NewImageDataReceivedEvent, self.onNewImageDataReceived)
    self.session.removeEventObserver(self.session.CoverTemplateReceivedEvent, self.onCoverTemplateReceived)
    self.session.addEventObserver(self.session.ZFrameRegistrationSuccessfulEvent, self.onZFrameRegistrationSuccessful)
    self.session.removeEventObserver(self.session.CurrentSeriesChangedEvent, self.onCurrentSeriesChanged)
    self.session.removeEventObserver(self.session.SuccessfullyLoadedMetadataEvent, self.onLoadingMetadataSuccessful)

  def setupSliceWidgets(self):
    self.createSliceWidgetClassMembers("Red")
    self.createSliceWidgetClassMembers("Yellow")
    self.createSliceWidgetClassMembers("Green")

  def setupAdditionalViewSettingButtons(self):
    pass

  def resetViewSettingButtons(self):
    pass

  def onActivation(self):
    pass

  def onDeactivation(self):
    pass

  @logmethod(logging.INFO)
  def onNewCaseStarted(self, caller, event):
    pass

  @logmethod(logging.INFO)
  def onCaseClosed(self, caller, event):
    pass

  @logmethod(logging.INFO)
  def onIncomingDataSkipped(self, caller, event):
    pass

  @vtk.calldata_type(vtk.VTK_STRING)
  def onNewImageDataReceived(self, caller, event, callData):
    pass

  @logmethod(logging.INFO)
  def onCoverTemplateReceived(self, caller, event):
    pass

  @logmethod(logging.INFO)
  def onZFrameRegistrationSuccessful(self, caller, event):
    pass

  @vtk.calldata_type(vtk.VTK_STRING)
  def onCurrentSeriesChanged(self, caller, event, callData=None):
    pass

  @logmethod(logging.INFO)
  def onLoadingMetadataSuccessful(self, caller, event):
    pass

  def setupFourUpView(self, volume):
    self.setBackgroundToVolumeID(volume.GetID())
    self.layoutManager.setLayout(SliceTrackerConstants.LAYOUT_FOUR_UP)

  def setBackgroundToVolumeID(self, volumeID):
    for compositeNode in self._compositeNodes:
      compositeNode.SetLabelVolumeID(None)
      compositeNode.SetForegroundVolumeID(None)
      compositeNode.SetBackgroundVolumeID(volumeID)
    self.setDefaultOrientation()

  def setDefaultOrientation(self):
    self.redSliceNode.SetOrientationToAxial()
    self.yellowSliceNode.SetOrientationToSagittal()
    self.greenSliceNode.SetOrientationToCoronal()
    self.updateFOV() # TODO: shall not be called here

  def updateFOV(self):
    # if self.getSetting("COVER_TEMPLATE") in self.intraopSeriesSelector.currentText:
    #   self.setDefaultFOV(self.redSliceLogic, 1.0)
    #   self.setDefaultFOV(self.yellowSliceLogic, 1.0)
    #   self.setDefaultFOV(self.greenSliceLogic, 1.0)
    # el
    if self.layoutManager.layout == SliceTrackerConstants.LAYOUT_RED_SLICE_ONLY:
      self.setDefaultFOV(self.redSliceLogic)
    elif self.layoutManager.layout == SliceTrackerConstants.LAYOUT_SIDE_BY_SIDE:
      self.setDefaultFOV(self.redSliceLogic)
      self.setDefaultFOV(self.yellowSliceLogic)
    elif self.layoutManager.layout == SliceTrackerConstants.LAYOUT_FOUR_UP:
      self.setDefaultFOV(self.redSliceLogic)
      self.yellowSliceLogic.FitSliceToAll()
      self.greenSliceLogic.FitSliceToAll()

  @beforeRunProcessEvents
  def setDefaultFOV(self, sliceLogic, factor=0.5):
    sliceLogic.FitSliceToAll()
    FOV = sliceLogic.GetSliceNode().GetFieldOfView()
    self.setFOV(sliceLogic, [FOV[0] * factor, FOV[1] * factor, FOV[2]])