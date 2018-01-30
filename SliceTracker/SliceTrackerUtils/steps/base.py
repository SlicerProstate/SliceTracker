import vtk
from SlicerDevelopmentToolboxUtils.decorators import beforeRunProcessEvents, onModuleSelected
from SlicerDevelopmentToolboxUtils.module.base import WidgetBase
from SlicerDevelopmentToolboxUtils.module.logic import SessionBasedLogicBase

from ..constants import SliceTrackerConstants as constants
from ..session import SliceTrackerSession


class SliceTrackerWidgetBase(WidgetBase):

  MODULE_NAME = constants.MODULE_NAME

  SessionClass = SliceTrackerSession

  AvailableLayoutsChangedEvent = vtk.vtkCommand.UserEvent + 4233

  def __init__(self):
    super(SliceTrackerWidgetBase, self).__init__()

  def setup(self):
    self.setupSliceWidgets()
    self.setupAdditionalViewSettingButtons()

  def setupSliceWidgets(self):
    self.createSliceWidgetClassMembers("Red")
    self.createSliceWidgetClassMembers("Yellow")
    self.createSliceWidgetClassMembers("Green")

  def setupAdditionalViewSettingButtons(self):
    pass

  def addSessionObservers(self):
    super(SliceTrackerWidgetBase, self).addSessionObservers()
    self.session.addEventObserver(self.session.NewImageSeriesReceivedEvent, self.onNewImageSeriesReceived)
    self.session.addEventObserver(self.session.CurrentSeriesChangedEvent, self.onCurrentSeriesChanged)
    self.session.addEventObserver(self.session.LoadingMetadataSuccessfulEvent, self.onLoadingMetadataSuccessful)
    self.session.addEventObserver(self.session.PreprocessingSuccessfulEvent, self.onPreprocessingSuccessful)

  def removeSessionEventObservers(self):
    super(SliceTrackerWidgetBase, self).removeSessionEventObservers()
    self.session.removeEventObserver(self.session.NewImageSeriesReceivedEvent, self.onNewImageSeriesReceived)
    self.session.removeEventObserver(self.session.CurrentSeriesChangedEvent, self.onCurrentSeriesChanged)
    self.session.removeEventObserver(self.session.LoadingMetadataSuccessfulEvent, self.onLoadingMetadataSuccessful)
    self.session.removeEventObserver(self.session.PreprocessingSuccessfulEvent, self.onPreprocessingSuccessful)

  def onActivation(self):
    self.layoutManager.layoutChanged.connect(self.onLayoutChanged)
    self.session.addEventObserver(self.session.CurrentResultChangedEvent, self.onCurrentResultChanged)
    super(SliceTrackerWidgetBase, self).onActivation()

  def onDeactivation(self):
    self.layoutManager.layoutChanged.disconnect(self.onLayoutChanged)
    self.session.removeEventObserver(self.session.CurrentResultChangedEvent, self.onCurrentResultChanged)
    super(SliceTrackerWidgetBase, self).onDeactivation()

  def onCurrentResultChanged(self, caller, event):
    pass

  @onModuleSelected(constants.MODULE_NAME)
  def onLayoutChanged(self, layout=None):
    pass

  def setAvailableLayouts(self, layouts):
    if not all([l in constants.ALLOWED_LAYOUTS for l in layouts]):
      raise ValueError("Not all of the delivered layouts are allowed to be used in SliceTracker")
    self.invokeEvent(self.AvailableLayoutsChangedEvent, str(layouts))

  def addPlugin(self, plugin):
    super(SliceTrackerWidgetBase, self).addPlugin(plugin)
    plugin.addEventObserver(self.AvailableLayoutsChangedEvent, self.onPluginAvailableLayoutChanged)

  @vtk.calldata_type(vtk.VTK_STRING)
  def onPluginAvailableLayoutChanged(self, caller, event, callData):
    self.invokeEvent(self.AvailableLayoutsChangedEvent, callData)

  def resetViewSettingButtons(self):
    pass

  @vtk.calldata_type(vtk.VTK_STRING)
  def onNewImageSeriesReceived(self, caller, event, callData):
    pass

  @vtk.calldata_type(vtk.VTK_STRING)
  def onCurrentSeriesChanged(self, caller, event, callData=None):
    pass

  def onLoadingMetadataSuccessful(self, caller, event):
    pass

  def onPreprocessingSuccessful(self, caller, event):
    pass

  def setupFourUpView(self, volume, clearLabels=True):
    self.layoutManager.setLayout(constants.LAYOUT_FOUR_UP_QUANTITATIVE)
    self.setBackgroundToVolumeID(volume, clearLabels)

  def setBackgroundToVolumeID(self, volume, clearLabels=True, showLabelOutline=True):
    super(SliceTrackerWidgetBase, self).setBackgroundToVolumeID(volume, clearLabels, showLabelOutline)
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
    if self.layoutManager.layout == constants.LAYOUT_RED_SLICE_ONLY:
      self.setDefaultFOV(self.redSliceLogic)
    elif self.layoutManager.layout == constants.LAYOUT_SIDE_BY_SIDE:
      self.setDefaultFOV(self.redSliceLogic)
      self.setDefaultFOV(self.yellowSliceLogic)
    elif self.layoutManager.layout == constants.LAYOUT_FOUR_UP:
      self.setDefaultFOV(self.redSliceLogic)
      self.yellowSliceLogic.FitSliceToAll()
      self.greenSliceLogic.FitSliceToAll()

  @beforeRunProcessEvents
  def setDefaultFOV(self, sliceLogic, factor=0.5):
    sliceLogic.FitSliceToAll()
    FOV = sliceLogic.GetSliceNode().GetFieldOfView()
    self.setFOV(sliceLogic, [FOV[0] * factor, FOV[1] * factor, FOV[2]])

  def setupRedSlicePreview(self, selectedSeries):
    self.layoutManager.setLayout(constants.LAYOUT_RED_SLICE_ONLY)
    self.hideAllFiducialNodes()
    try:
      result = self.session.data.getResultsBySeries(selectedSeries)[0]
      volume = result.volumes.fixed
    except IndexError:
      volume = self.session.getOrCreateVolumeForSeries(selectedSeries)
    self.setBackgroundToVolumeID(volume)


class SliceTrackerStep(SliceTrackerWidgetBase):

  def __init__(self):
    self.viewSettingButtons = []
    self.parameterNode.SetAttribute("Name", self.NAME)
    super(SliceTrackerStep, self).__init__()


class SliceTrackerLogicBase(SessionBasedLogicBase):

  MODULE_NAME = constants.MODULE_NAME
  SessionClass = SliceTrackerSession

  def __init__(self):
    super(SliceTrackerLogicBase, self).__init__()


class SliceTrackerPlugin(SliceTrackerWidgetBase):

  def __init__(self):
    super(SliceTrackerPlugin, self).__init__()

  def clearData(self):
    pass