import logging, os
import qt, vtk, slicer
from abc import ABCMeta, abstractmethod

from ..session import SliceTrackerSession

from SlicerProstateUtils.decorators import logmethod, beforeRunProcessEvents, onModuleSelected
from SlicerProstateUtils.mixins import ModuleLogicMixin, ModuleWidgetMixin, GeneralModuleMixin
from ..constants import SliceTrackerConstants

class StepBase(GeneralModuleMixin):

  MODULE_NAME = "SliceTracker"

  @property
  def currentResult(self):
    return self.session.activeResult

  @currentResult.setter
  def currentResult(self, value):
    self.session.activeResult = value

  def __init__(self):
    self.modulePath = self.getModulePath()
    self.resourcesPath = os.path.join(self.modulePath, "Resources")
    self.session = SliceTrackerSession()

  def getModulePath(self):
    return os.path.dirname(slicer.util.modulePath(self.MODULE_NAME))

  def getSetting(self, setting, moduleName=None, default=None):
    return GeneralModuleMixin.getSetting(self, setting, moduleName=moduleName if moduleName else self.MODULE_NAME,
                                         default=default)

  def setSetting(self, setting, value, moduleName=None):
    return GeneralModuleMixin.setSetting(self, setting, value,
                                         moduleName=moduleName if moduleName else self.MODULE_NAME)


class SliceTrackerWidgetBase(qt.QWidget, StepBase, ModuleWidgetMixin):

  ActivatedEvent = vtk.vtkCommand.UserEvent + 150
  DeactivatedEvent = vtk.vtkCommand.UserEvent + 151

  NAME = None
  LogicClass = None

  @property
  def active(self):
    self._activated = getattr(self, "_activated", False)
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
    if self.LogicClass:
      self.logic = self.LogicClass()
    self.setLayout(qt.QGridLayout())
    self.setupIcons()
    self.setup()
    self.setupAdditionalViewSettingButtons()
    self.setupSliceWidgets()
    self.setupSessionObservers()
    self.setupConnections()

  def __del__(self):
    self.removeSessionEventObservers()

  def setupIcons(self):
    pass

  def cleanup(self):
    raise NotImplementedError("This method needs to be implemented for %s" % self.NAME)

  def setup(self):
    NotImplementedError("This method needs to be implemented for %s" % self.NAME)

  def setupConnections(self):
    NotImplementedError("This method needs to be implemented for %s" % self.NAME)

  def onActivation(self):
    raise NotImplementedError("This method needs to be implemented for %s" % self.NAME)

  def onDeactivation(self):
    raise NotImplementedError("This method needs to be implemented for %s" % self.NAME)

  def setupSliceWidgets(self):
    self.createSliceWidgetClassMembers("Red")
    self.createSliceWidgetClassMembers("Yellow")
    self.createSliceWidgetClassMembers("Green")

  def setupSessionObservers(self):
    self.session.addEventObserver(self.session.NewCaseStartedEvent, self.onNewCaseStarted)
    self.session.addEventObserver(self.session.CaseOpenedEvent, self.onCaseOpened)
    self.session.addEventObserver(self.session.CloseCaseEvent, self.onCaseClosed)
    self.session.addEventObserver(self.session.NewImageSeriesReceivedEvent, self.onNewImageSeriesReceived)
    self.session.addEventObserver(self.session.CurrentSeriesChangedEvent, self.onCurrentSeriesChanged)
    self.session.addEventObserver(self.session.LoadingMetadataSuccessfulEvent, self.onLoadingMetadataSuccessful)
    self.session.addEventObserver(self.session.PreprocessingSuccessfulEvent, self.onPreprocessingSuccessful)

  def removeSessionEventObservers(self):
    self.session.removeEventObserver(self.session.NewCaseStartedEvent, self.onNewCaseStarted)
    self.session.removeEventObserver(self.session.CaseOpenedEvent, self.onCaseOpened)
    self.session.removeEventObserver(self.session.CloseCaseEvent, self.onCaseClosed)
    self.session.removeEventObserver(self.session.NewImageSeriesReceivedEvent, self.onNewImageSeriesReceived)
    self.session.removeEventObserver(self.session.CurrentSeriesChangedEvent, self.onCurrentSeriesChanged)
    self.session.removeEventObserver(self.session.LoadingMetadataSuccessfulEvent, self.onLoadingMetadataSuccessful)
    self.session.removeEventObserver(self.session.PreprocessingSuccessfulEvent, self.onPreprocessingSuccessful)

  @onModuleSelected(SliceTrackerPlugin.MODULE_NAME)
  def onLayoutChanged(self, layout=None):
    pass

  def setupAdditionalViewSettingButtons(self):
    pass

  def resetViewSettingButtons(self):
    pass

  @logmethod(logging.INFO)
  def onNewCaseStarted(self, caller, event):
    pass

  def onCaseOpened(self, caller, event):
    pass

  @vtk.calldata_type(vtk.VTK_STRING)
  def onCaseClosed(self, caller, event, callData):
    pass

  @vtk.calldata_type(vtk.VTK_STRING)
  def onNewImageSeriesReceived(self, caller, event, callData):
    pass

  @vtk.calldata_type(vtk.VTK_STRING)
  def onCurrentSeriesChanged(self, caller, event, callData=None):
    pass

  @logmethod(logging.INFO)
  def onLoadingMetadataSuccessful(self, caller, event):
    pass

  def onPreprocessingSuccessful(self, caller, event):
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

  def setAxialOrientation(self):
    for sliceNode in self._sliceNodes:
      sliceNode.SetOrientationToAxial()
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

  def setupRedSlicePreview(self, selectedSeries):
    self.layoutManager.setLayout(SliceTrackerConstants.LAYOUT_RED_SLICE_ONLY)
    self.hideAllFiducialNodes()
    try:
      result = self.session.data.getResultsBySeries(selectedSeries)[0]
      volume = result.volumes.fixed
    except IndexError:
      volume = self.session.getOrCreateVolumeForSeries(selectedSeries)
    self.setBackgroundToVolumeID(volume.GetID())


class SliceTrackerStep(SliceTrackerWidgetBase):

  def __init__(self):
    self.viewSettingButtons = []
    self._plugins = []
    self.parameterNode.SetAttribute("Name", self.NAME)
    super(SliceTrackerStep, self).__init__()

  @logmethod(logging.INFO)
  def addPlugin(self, plugin):
    assert hasattr(plugin, "active"), "Plugin needs to be a subclass of %s" % SliceTrackerPlugin.__class__.__name__
    self._plugins.append(plugin)

  def onActivation(self):
    self._activatePlugins()

  def onDeactivation(self):
    self._deactivatePlugins()

  def _activatePlugins(self):
    self.__setPluginsActivated(True)

  def _deactivatePlugins(self):
    self.__setPluginsActivated(False)

  def __setPluginsActivated(self, activated):
    for plugin in self._plugins:
      plugin.active = activated

  def __del__(self):
    self.removeEventObservers()


class SliceTrackerLogicBase(StepBase, ModuleLogicMixin):

  __metaclass__ = ABCMeta

  def __init__(self):
    StepBase.__init__(self)

  @abstractmethod
  def cleanup(self):
    pass


class SliceTrackerPlugin(SliceTrackerWidgetBase):

  def __init__(self):
    super(SliceTrackerPlugin, self).__init__()